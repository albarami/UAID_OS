"""Tenant-scoped release findings repository (Slice 23, §13.4/§916-920/§24.1).

``create`` validates the finding (fail-closed; category-per-type + `other` rule) and persists an
``open`` finding + a ``created`` event. ``resolve``/``mark_false_positive``/``supersede`` set the
resolution metadata; ``accept`` (non-critical only) links a usable risk-acceptance record. Every
transition writes an append-only event + an audit entry with **safe metadata only**
(ids/type/severity/status/category — never summary/detail/resolution prose). The DB guard
(migration ``0022``) is the authoritative backstop for all invariants. Findings never enable go-live.
Run inside ``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.release_finding import ReleaseFinding
from app.models.release_finding_event import ReleaseFindingEvent
from app.release.findings import InvalidFinding, is_critical, validate_new_finding, validate_transition
from app.tenancy import TenantContext, TenantScopedRepository


class ReleaseFindingRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ReleaseFinding)

    async def create(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> ReleaseFinding:
        validate_new_finding(payload)
        row = ReleaseFinding(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            finding_type=payload["finding_type"],
            category=payload["category"],
            severity=payload["severity"],
            summary=payload["summary"],
            detail=payload.get("detail"),
            source=payload["source"],
            status="open",
        )
        self.session.add(row)
        await self.session.flush()
        await self._event(row, "created", actor)
        await self._audit(row, "release.finding_created", actor)
        return row

    async def resolve(
        self, *, finding_id: uuid.UUID, resolution_note: str, resolved_by: str, actor: str
    ) -> ReleaseFinding:
        return await self._resolve_like(finding_id, "resolved", resolution_note, resolved_by, actor)

    async def mark_false_positive(
        self, *, finding_id: uuid.UUID, resolution_note: str, resolved_by: str, actor: str
    ) -> ReleaseFinding:
        return await self._resolve_like(
            finding_id, "false_positive", resolution_note, resolved_by, actor
        )

    async def supersede(
        self, *, finding_id: uuid.UUID, resolution_note: str, resolved_by: str, actor: str
    ) -> ReleaseFinding:
        return await self._resolve_like(
            finding_id, "superseded", resolution_note, resolved_by, actor
        )

    async def accept(
        self, *, finding_id: uuid.UUID, risk_acceptance_record_id: uuid.UUID, actor: str
    ) -> ReleaseFinding:
        row = await self._get_or_raise(finding_id)
        validate_transition(row.status, "accepted")
        if is_critical(row.severity):
            raise InvalidFinding("critical findings cannot be accepted")
        row.status = "accepted"
        row.risk_acceptance_record_id = risk_acceptance_record_id
        row.updated_at = func.clock_timestamp()
        # The DB guard validates the referenced record is usable (active/non-expired/non-blocking/
        # same tenant+project/issue_id==finding.id) on flush.
        await self.session.flush()
        await self._event(row, "accepted", actor)
        await self._audit(row, "release.finding_accepted", actor)
        return row

    async def get(self, finding_id: uuid.UUID) -> ReleaseFinding | None:
        stmt = select(ReleaseFinding).where(
            ReleaseFinding.id == finding_id,
            ReleaseFinding.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_open(self, project_id: uuid.UUID, finding_type: str) -> int:
        stmt = select(func.count()).where(
            ReleaseFinding.tenant_id == self.context.tenant_id,
            ReleaseFinding.project_id == project_id,
            ReleaseFinding.finding_type == finding_type,
            ReleaseFinding.status == "open",
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_open_unaccepted_critical(
        self, project_id: uuid.UUID, finding_type: str
    ) -> int:
        """Critical findings cannot be accepted, so all open criticals are unaccepted blockers."""
        stmt = select(func.count()).where(
            ReleaseFinding.tenant_id == self.context.tenant_id,
            ReleaseFinding.project_id == project_id,
            ReleaseFinding.finding_type == finding_type,
            ReleaseFinding.status == "open",
            ReleaseFinding.severity == "critical",
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def _resolve_like(
        self, finding_id: uuid.UUID, to_status: str, resolution_note: str, resolved_by: str,
        actor: str,
    ) -> ReleaseFinding:
        row = await self._get_or_raise(finding_id)
        validate_transition(row.status, to_status)
        row.status = to_status
        row.resolution_note = resolution_note
        row.resolved_by = resolved_by
        row.resolved_at = func.clock_timestamp()
        row.updated_at = func.clock_timestamp()
        await self.session.flush()
        await self._event(row, to_status, actor)
        await self._audit(row, f"release.finding_{to_status}", actor)
        return row

    async def _get_or_raise(self, finding_id: uuid.UUID) -> ReleaseFinding:
        row = await self.get(finding_id)
        if row is None:
            raise LookupError(f"release_finding {finding_id} not found in tenant scope")
        return row

    async def _event(self, row: ReleaseFinding, event_type: str, actor: str) -> None:
        self.session.add(
            ReleaseFindingEvent(
                tenant_id=self.context.tenant_id,
                finding_id=row.id,
                event_type=event_type,
                actor=actor,
            )
        )
        await self.session.flush()

    async def _audit(self, row: ReleaseFinding, action: str, actor: str) -> None:
        # Safe metadata only — NEVER summary/detail/resolution prose.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"release_finding:{row.id}",
            payload={
                "release_finding_id": str(row.id),
                "project_id": str(row.project_id),
                "finding_type": row.finding_type,
                "category": row.category,
                "severity": row.severity,
                "status": row.status,
            },
        )
