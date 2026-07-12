"""Tenant-scoped risk-acceptance repository (Slice 22, §24.1/§27.10).

``create`` validates the record (fail-closed; hard-refusal categories rejected at store time, §24.1)
and persists an ``active`` record + a ``created`` lifecycle event. ``revoke``/``supersede``/
``expire_if_overdue`` perform one-way transitions (validated by ``app.release.risk_acceptance``),
each writing an append-only event and an audit entry with **safe metadata only** (ids/severity/status
— never reason/business_impact/evidence prose). Slice 27: ``approver_provenance`` is stamped
``request_authenticated`` only when ``context.actor`` IS the signer (actor-bound: principal == payload
``approver`` and in ``accepted_by``), else ``caller_supplied_unverified`` — key-custody, **not** a human
signature. Records never enable go-live. Run inside ``tenant_scope``; the ``actor`` arg is an untrusted
label, while ``context.actor`` (if set) is the verified principal. Slice 47 requires new records to
resolve one exact frozen candidate and one bound issue or uniquely bridged finding; historical NULL
``subject_type`` rows remain visibly legacy-unbound.
"""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.identity import CALLER_SUPPLIED_UNVERIFIED, REQUEST_AUTHENTICATED
from app.models.release_candidate import ReleaseCandidate
from app.models.release_candidate_issue_binding import ReleaseCandidateIssueBinding
from app.models.release_issue import ReleaseIssue
from app.models.risk_acceptance_event import RiskAcceptanceEvent
from app.models.risk_acceptance_record import RiskAcceptanceRecord
from app.release.risk_acceptance import (
    InvalidRiskAcceptance,
    validate_new_record,
    validate_transition,
)
from app.tenancy import TenantContext, TenantScopedRepository


class RiskAcceptanceRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, RiskAcceptanceRecord)

    async def create(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> RiskAcceptanceRecord:
        validate_new_record(payload)  # fail-closed: required fields + hard-refusal rejection
        await self._require_subject_binding(project_id, payload)
        # Slice 27: stamp the verified tier ONLY when the authenticated principal IS the signer
        # (actor-bound). A claimed-verified acceptance for someone else is refused, never downgraded.
        approver_provenance = CALLER_SUPPLIED_UNVERIFIED
        if self.context.actor is not None:
            subject = self.context.actor.subject
            if payload["approver"] != subject or subject not in (payload.get("accepted_by") or []):
                raise InvalidRiskAcceptance(
                    "verified signer must equal payload approver and appear in accepted_by (§24.1)"
                )
            approver_provenance = REQUEST_AUTHENTICATED
        row = RiskAcceptanceRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_id=payload["release_id"],
            issue_id=payload["issue_id"],
            subject_type=payload["subject_type"],
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
            approver_provenance=approver_provenance,
        )
        self.session.add(row)
        await self.session.flush()
        await self._event(row, "created", actor)
        await self._audit(row, "intake.risk_acceptance_created", actor)
        return row

    async def _require_subject_binding(self, project_id: uuid.UUID, payload: dict) -> None:
        """Require one frozen exact-release candidate containing the ruled subject."""

        try:
            subject_id = uuid.UUID(payload["issue_id"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise InvalidRiskAcceptance("issue_id must be a UUID for a new bound record") from exc
        candidate_id = (
            await self.session.execute(
                select(ReleaseCandidate.id).where(
                    ReleaseCandidate.tenant_id == self.context.tenant_id,
                    ReleaseCandidate.project_id == project_id,
                    ReleaseCandidate.release_ref == payload["release_id"],
                    ReleaseCandidate.status == "frozen",
                )
            )
        ).scalar_one_or_none()
        if candidate_id is None:
            raise InvalidRiskAcceptance("release_id must resolve to one same-project frozen candidate")

        conditions = [
            ReleaseCandidateIssueBinding.tenant_id == self.context.tenant_id,
            ReleaseCandidateIssueBinding.project_id == project_id,
            ReleaseCandidateIssueBinding.release_candidate_id == candidate_id,
        ]
        if payload["subject_type"] == "release_issue":
            conditions.append(ReleaseCandidateIssueBinding.release_issue_id == subject_id)
        else:
            conditions.extend(
                (
                    ReleaseIssue.id == ReleaseCandidateIssueBinding.release_issue_id,
                    ReleaseIssue.tenant_id == ReleaseCandidateIssueBinding.tenant_id,
                    ReleaseIssue.project_id == project_id,
                    ReleaseIssue.source_finding_id == subject_id,
                    ReleaseIssue.blocking_category.is_(None),
                    ReleaseIssue.severity != "critical",
                )
            )
        count = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(ReleaseCandidateIssueBinding)
                    .outerjoin(
                        ReleaseIssue,
                        (ReleaseIssue.id == ReleaseCandidateIssueBinding.release_issue_id)
                        & (
                            ReleaseIssue.tenant_id
                            == ReleaseCandidateIssueBinding.tenant_id
                        ),
                    )
                    .where(*conditions)
                )
            ).scalar_one()
        )
        if count != 1:
            raise InvalidRiskAcceptance("release/subject binding is not exact")

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

    async def count_release_bound_active(self, project_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            RiskAcceptanceRecord.tenant_id == self.context.tenant_id,
            RiskAcceptanceRecord.project_id == project_id,
            RiskAcceptanceRecord.subject_type.is_not(None),
            RiskAcceptanceRecord.status == "active",
            RiskAcceptanceRecord.blocking_category.is_(None),
            RiskAcceptanceRecord.expiry_date >= date.today(),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_legacy_unbound(self, project_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            RiskAcceptanceRecord.tenant_id == self.context.tenant_id,
            RiskAcceptanceRecord.project_id == project_id,
            RiskAcceptanceRecord.subject_type.is_(None),
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
                "subject_type": row.subject_type,
                "release_id": row.release_id,
                "severity": row.severity,
                "status": row.status,
                "has_blocking_category": row.blocking_category is not None,
            },
        )
