"""Tenant-scoped risk-acceptance repository (Slice 22, §24.1/§27.10).

``create`` validates the record (fail-closed; hard-refusal categories rejected at store time, §24.1)
and persists an ``active`` record + a ``created`` lifecycle event. ``revoke``/``supersede``/
``expire_if_overdue`` perform one-way transitions (validated by ``app.release.risk_acceptance``),
each writing an append-only event and an audit entry with **safe metadata only** (ids/severity/status
— never reason/business_impact/evidence prose). Signer identity is stamped
``approver_provenance='caller_supplied_unverified'`` (not a verified human signature). Records never
enable go-live. Run inside ``tenant_scope`` (GUC set). ``actor`` is an untrusted caller label.
"""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.risk_acceptance_event import RiskAcceptanceEvent
from app.models.risk_acceptance_record import RiskAcceptanceRecord
from app.release.risk_acceptance import validate_new_record, validate_transition
from app.tenancy import TenantContext, TenantScopedRepository


class RiskAcceptanceRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, RiskAcceptanceRecord)

    async def create(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> RiskAcceptanceRecord:
        validate_new_record(payload)  # fail-closed: required fields + hard-refusal rejection
        row = RiskAcceptanceRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_id=payload["release_id"],
            issue_id=payload["issue_id"],
            severity=payload["severity"],
            affected_requirements=list(payload.get("affected_requirements") or []),
            reason_for_acceptance=payload["reason_for_acceptance"],
            business_impact=payload["business_impact"],
            compensating_controls=list(payload.get("compensating_controls") or []),
            rollback_or_mitigation_plan=payload["rollback_or_mitigation_plan"],
            evidence_links=list(payload.get("evidence_links") or []),
            required_follow_up_ticket=payload["required_follow_up_ticket"],
            included_in_release_notes=bool(payload.get("included_in_release_notes", False)),
            expiry_date=payload["expiry_date"],
            owner=payload["owner"],
            approver=payload["approver"],
            accepted_by=list(payload["accepted_by"]),
            approval_authority_source=payload["approval_authority_source"],
            blocking_category=payload.get("blocking_category"),
            status="active",
        )
        self.session.add(row)
        await self.session.flush()
        await self._event(row, "created", actor)
        await self._audit(row, "intake.risk_acceptance_created", actor)
        return row

    async def revoke(self, *, record_id: uuid.UUID, actor: str) -> RiskAcceptanceRecord:
        return await self._transition(record_id, "revoked", "revoked", actor)

    async def supersede(self, *, record_id: uuid.UUID, actor: str) -> RiskAcceptanceRecord:
        return await self._transition(record_id, "superseded", "superseded", actor)

    async def expire_if_overdue(
        self, *, record_id: uuid.UUID, actor: str
    ) -> RiskAcceptanceRecord:
        row = await self._get_or_raise(record_id)
        if row.status == "active" and row.expiry_date < date.today():
            return await self._transition(record_id, "expired", "expired", actor)
        return row

    async def get(self, record_id: uuid.UUID) -> RiskAcceptanceRecord | None:
        stmt = select(RiskAcceptanceRecord).where(
            RiskAcceptanceRecord.id == record_id,
            RiskAcceptanceRecord.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_project(
        self, project_id: uuid.UUID
    ) -> Sequence[RiskAcceptanceRecord]:
        stmt = select(RiskAcceptanceRecord).where(
            RiskAcceptanceRecord.tenant_id == self.context.tenant_id,
            RiskAcceptanceRecord.project_id == project_id,
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def count_active_nonblocking(self, project_id: uuid.UUID) -> int:
        """Active + future-expiry + non-blocking records — the only ones the A5 hook may count."""
        stmt = select(func.count()).where(
            RiskAcceptanceRecord.tenant_id == self.context.tenant_id,
            RiskAcceptanceRecord.project_id == project_id,
            RiskAcceptanceRecord.status == "active",
            RiskAcceptanceRecord.blocking_category.is_(None),
            RiskAcceptanceRecord.expiry_date >= date.today(),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def _get_or_raise(self, record_id: uuid.UUID) -> RiskAcceptanceRecord:
        row = await self.get(record_id)
        if row is None:
            raise LookupError(f"risk_acceptance_record {record_id} not found in tenant scope")
        return row

    async def _transition(
        self, record_id: uuid.UUID, to_status: str, event_type: str, actor: str
    ) -> RiskAcceptanceRecord:
        row = await self._get_or_raise(record_id)
        validate_transition(row.status, to_status)  # fail-closed one-way transition
        row.status = to_status
        row.updated_at = func.clock_timestamp()
        await self.session.flush()
        await self._event(row, event_type, actor)
        await self._audit(row, f"intake.risk_acceptance_{event_type}", actor)
        return row

    async def _event(self, row: RiskAcceptanceRecord, event_type: str, actor: str) -> None:
        self.session.add(
            RiskAcceptanceEvent(
                tenant_id=self.context.tenant_id,
                record_id=row.id,
                event_type=event_type,
                actor=actor,
            )
        )
        await self.session.flush()

    async def _audit(self, row: RiskAcceptanceRecord, action: str, actor: str) -> None:
        # Safe metadata only — NEVER reason/business_impact/evidence prose.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"risk_acceptance_record:{row.id}",
            payload={
                "risk_acceptance_record_id": str(row.id),
                "project_id": str(row.project_id),
                "issue_id": row.issue_id,
                "release_id": row.release_id,
                "severity": row.severity,
                "status": row.status,
                "has_blocking_category": row.blocking_category is not None,
            },
        )
