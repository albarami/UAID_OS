"""Read helpers for the Slice-57 incident ledger. Not an HTTP surface."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops_incident import (
    OpsIncident,
    OpsIncidentActionEvaluation,
    OpsIncidentActionResult,
    OpsIncidentTicket,
    OpsSupportHandover,
)
from app.ops.incidents import (
    HISTORY_LIMIT_DEFAULT,
    OPEN_WORKFLOW_STATUSES,
    ActionChild,
    HandoverRecord,
    IncidentSnapshot,
    validate_history_limit,
)
from app.tenancy import TenantContext


def child_from_orm(row: OpsIncidentActionResult) -> ActionChild:
    """Copy one persisted action row into the pure contract object."""
    return ActionChild(
        seq=row.seq,
        action=row.action,
        matrix_action=row.matrix_action,
        policy_decision=row.policy_decision,
        execution_posture=row.execution_posture,
        reason_code=row.reason_code,
        ticket_id=row.ticket_id,
    )


class OpsIncidentReadMixin:
    """Latest-wins and list queries over incidents, evaluations, and handovers."""

    session: AsyncSession
    context: TenantContext

    async def ticket_for(self, incident_id: uuid.UUID) -> OpsIncidentTicket | None:
        stmt = select(OpsIncidentTicket).where(
            OpsIncidentTicket.tenant_id == self.context.tenant_id,
            OpsIncidentTicket.incident_id == incident_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def latest_evaluation(self, incident_id: uuid.UUID) -> OpsIncidentActionEvaluation | None:
        stmt = (
            select(OpsIncidentActionEvaluation)
            .where(
                OpsIncidentActionEvaluation.tenant_id == self.context.tenant_id,
                OpsIncidentActionEvaluation.incident_id == incident_id,
            )
            .order_by(
                OpsIncidentActionEvaluation.created_at.desc(),
                OpsIncidentActionEvaluation.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def results_for(self, evaluation_id: uuid.UUID) -> list[OpsIncidentActionResult]:
        stmt = (
            select(OpsIncidentActionResult)
            .where(
                OpsIncidentActionResult.tenant_id == self.context.tenant_id,
                OpsIncidentActionResult.evaluation_id == evaluation_id,
            )
            .order_by(OpsIncidentActionResult.seq.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def snapshot_of(self, incident: OpsIncident) -> IncidentSnapshot:
        ticket = await self.ticket_for(incident.id)
        evaluation = await self.latest_evaluation(incident.id)
        actions: tuple[ActionChild, ...] = ()
        if evaluation is not None:
            actions = tuple(child_from_orm(row) for row in await self.results_for(evaluation.id))
        return IncidentSnapshot(
            id=incident.id,
            project_id=incident.project_id,
            status=incident.status,
            category=incident.category,
            severity=incident.severity,
            ruleset_version=incident.ruleset_version,
            request_digest=incident.request_digest,
            source_signal_id=incident.source_signal_id,
            ticket_id=ticket.id if ticket is not None else None,
            latest_evaluation_id=evaluation.id if evaluation is not None else None,
            actions=actions,
        )

    async def latest(self, project_id: uuid.UUID) -> IncidentSnapshot | None:
        stmt = (
            select(OpsIncident)
            .where(
                OpsIncident.tenant_id == self.context.tenant_id,
                OpsIncident.project_id == project_id,
            )
            .order_by(OpsIncident.created_at.desc(), OpsIncident.id.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return await self.snapshot_of(row)

    async def list_open(
        self, project_id: uuid.UUID, *, limit: int = HISTORY_LIMIT_DEFAULT
    ) -> list[IncidentSnapshot]:
        bounded = validate_history_limit(limit)
        stmt = (
            select(OpsIncident)
            .where(
                OpsIncident.tenant_id == self.context.tenant_id,
                OpsIncident.project_id == project_id,
                OpsIncident.status.in_(OPEN_WORKFLOW_STATUSES),
            )
            .order_by(OpsIncident.created_at.desc(), OpsIncident.id.desc())
            .limit(bounded)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return [await self.snapshot_of(row) for row in rows]

    async def history(
        self, project_id: uuid.UUID, *, limit: int = HISTORY_LIMIT_DEFAULT
    ) -> list[IncidentSnapshot]:
        bounded = validate_history_limit(limit)
        stmt = (
            select(OpsIncident)
            .where(
                OpsIncident.tenant_id == self.context.tenant_id,
                OpsIncident.project_id == project_id,
            )
            .order_by(OpsIncident.created_at.desc(), OpsIncident.id.desc())
            .limit(bounded)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return [await self.snapshot_of(row) for row in rows]

    async def latest_handover(self, project_id: uuid.UUID) -> HandoverRecord | None:
        stmt = (
            select(OpsSupportHandover)
            .where(
                OpsSupportHandover.tenant_id == self.context.tenant_id,
                OpsSupportHandover.project_id == project_id,
            )
            .order_by(OpsSupportHandover.created_at.desc(), OpsSupportHandover.id.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return HandoverRecord(
            id=row.id,
            project_id=row.project_id,
            status=row.status,
            recorded_by_provenance=row.recorded_by_provenance,
            handed_over_by=row.handed_over_by,
            received_by=row.received_by,
        )
