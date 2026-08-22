"""Tenant-scoped Slice-57 incident workflow persistence.

Local tickets and prescriptions only. Never brokers, never diagnoses logs,
never executes a hotfix or production deploy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.ops_incident import (
    OpsIncident,
    OpsIncidentActionEvaluation,
    OpsIncidentActionResult,
    OpsIncidentEvent,
    OpsIncidentTicket,
    OpsSupportHandover,
)
from app.models.ops_signal import OpsSignalResult
from app.models.pm_issue_mapping import PMIssueMapping
from app.ops.incidents import (
    ACTION_COUNT,
    GATED_MATRIX_ACTIONS,
    RULESET_VERSION,
    ActionChild,
    ActionPrescriptionSet,
    HandoverPayload,
    HandoverRecord,
    IncidentError,
    IncidentIdempotencyConflict,
    IncidentPayload,
    IncidentSnapshot,
    PolicySnapshot,
    bind_seq1_ticket,
    evaluate_actions,
    policy_input_digest,
    request_digest,
    ticket_should_exist,
    validate_handover,
    validate_idempotency_key,
    validate_new_incident,
    validate_transition,
)
from app.policy.engine import Decision
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.ops_incident_reads import OpsIncidentReadMixin
from app.tenancy import TenantContext, TenantScopedRepository


class OpsIncidentRepository(OpsIncidentReadMixin, TenantScopedRepository):
    """Persist incidents inside an open tenant transaction."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, OpsIncident)

    async def get_incident(
        self, project_id: uuid.UUID, incident_id: uuid.UUID
    ) -> OpsIncident | None:
        stmt = select(OpsIncident).where(
            OpsIncident.tenant_id == self.context.tenant_id,
            OpsIncident.project_id == project_id,
            OpsIncident.id == incident_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_idempotency(
        self, project_id: uuid.UUID, idempotency_key: str
    ) -> OpsIncident | None:
        stmt = select(OpsIncident).where(
            OpsIncident.tenant_id == self.context.tenant_id,
            OpsIncident.project_id == project_id,
            OpsIncident.idempotency_key == idempotency_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def resolve_mapping(self, project_id: uuid.UUID, mapping_id: uuid.UUID) -> None:
        stmt = select(PMIssueMapping.id).where(
            PMIssueMapping.tenant_id == self.context.tenant_id,
            PMIssueMapping.project_id == project_id,
            PMIssueMapping.id == mapping_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none() is None:
            raise IncidentError("pm_issue_mapping_id is not a same-project mapping")

    async def resolve_signal(self, project_id: uuid.UUID, signal_id: uuid.UUID) -> None:
        stmt = select(OpsSignalResult.id).where(
            OpsSignalResult.tenant_id == self.context.tenant_id,
            OpsSignalResult.project_id == project_id,
            OpsSignalResult.id == signal_id,
        )
        if (await self.session.execute(stmt)).scalar_one_or_none() is None:
            raise IncidentError("source_signal_id is not a same-project ops signal")

    async def load_policy_snapshot(self, project_id: uuid.UUID) -> PolicySnapshot:
        policy = await AutonomyPolicyRepository(self.session, self.context).get_for_project(
            project_id
        )
        if policy is None:
            return PolicySnapshot(False, None, None, {})
        return PolicySnapshot(
            True, policy.id, int(policy.autonomy_level), dict(policy.overrides or {})
        )

    async def load_policy_decisions(self, project_id: uuid.UUID) -> dict[str, Decision]:
        """Authorize gated §25.2 actions through the real ``decision_for`` boundary."""
        policies = AutonomyPolicyRepository(self.session, self.context)
        return {
            action: await policies.decision_for(project_id, action)
            for action in GATED_MATRIX_ACTIONS
        }

    async def try_insert_incident(
        self,
        *,
        project_id: uuid.UUID,
        payload: IncidentPayload,
        idempotency_key: str,
        digest: str,
    ) -> uuid.UUID | None:
        stmt = (
            pg_insert(OpsIncident)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                ruleset_version=RULESET_VERSION,
                category=payload.category,
                severity=payload.severity,
                status="open",
                summary=payload.summary,
                detail=payload.detail,
                source_provenance="caller_supplied_unverified",
                source_signal_id=payload.source_signal_id,
                idempotency_key=idempotency_key,
                request_digest=digest,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "project_id", "idempotency_key"],
            )
            .returning(OpsIncident.id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _insert_ticket(
        self,
        incident: OpsIncident,
        mapping_id: uuid.UUID | None,
    ) -> OpsIncidentTicket:
        ticket = OpsIncidentTicket(
            project_id=incident.project_id,
            incident_id=incident.id,
            ticket_kind="bug",
            delivery="local_record",
            status="open",
            pm_issue_mapping_id=mapping_id,
        )
        await self.add(ticket)
        await self.session.flush()
        return ticket

    async def _append_event(self, incident: OpsIncident, event_type: str, actor: str) -> None:
        await self.add(
            OpsIncidentEvent(
                project_id=incident.project_id,
                incident_id=incident.id,
                event_type=event_type,
                actor=actor,
            )
        )

    async def insert_evaluation(
        self,
        incident: OpsIncident,
        snapshot: PolicySnapshot,
        children: Sequence[ActionChild],
    ) -> ActionPrescriptionSet:
        digest = policy_input_digest(snapshot)
        evaluation = OpsIncidentActionEvaluation(
            project_id=incident.project_id,
            incident_id=incident.id,
            ruleset_version=RULESET_VERSION,
            action_count=ACTION_COUNT,
            policy_present=snapshot.policy_present,
            policy_id=snapshot.policy_id,
            autonomy_level_snapshot=snapshot.autonomy_level,
            policy_input_digest=digest,
        )
        await self.add(evaluation)
        await self.session.flush()
        for child in children:
            await self.add(
                OpsIncidentActionResult(
                    project_id=incident.project_id,
                    incident_id=incident.id,
                    evaluation_id=evaluation.id,
                    seq=child.seq,
                    action=child.action,
                    matrix_action=child.matrix_action,
                    policy_decision=child.policy_decision,
                    execution_posture=child.execution_posture,
                    reason_code=child.reason_code,
                    ticket_id=child.ticket_id,
                )
            )
        await self.session.flush()
        return ActionPrescriptionSet(
            evaluation_id=evaluation.id,
            incident_id=incident.id,
            policy_present=snapshot.policy_present,
            policy_id=snapshot.policy_id,
            autonomy_level=snapshot.autonomy_level,
            policy_input_digest=digest,
            actions=tuple(children),
        )

    async def _audit(
        self, action: str, actor: str, target: str, payload: dict[str, object]
    ) -> None:
        await audit_record(self.session, action=action, actor=actor, target=target, payload=payload)

    async def open(
        self,
        project_id: uuid.UUID,
        *,
        actor: str,
        payload: IncidentPayload,
        idempotency_key: str,
    ) -> IncidentSnapshot | None:
        parsed = validate_new_incident(payload)
        key = validate_idempotency_key(idempotency_key)
        digest = request_digest(parsed)
        existing = await self.get_by_idempotency(project_id, key)
        if existing is not None:
            if existing.request_digest != digest:
                raise IncidentIdempotencyConflict(
                    "idempotency key reused with a different request digest"
                )
            return await self.snapshot_of(existing)
        if parsed.pm_issue_mapping_id is not None:
            await self.resolve_mapping(project_id, parsed.pm_issue_mapping_id)
        if parsed.source_signal_id is not None:
            await self.resolve_signal(project_id, parsed.source_signal_id)
        policy = await self.load_policy_snapshot(project_id)
        children = evaluate_actions(await self.load_policy_decisions(project_id))
        new_id = await self.try_insert_incident(
            project_id=project_id, payload=parsed, idempotency_key=key, digest=digest
        )
        if new_id is None:
            return None
        incident = await self.get_incident(project_id, new_id)
        if incident is None:
            raise IncidentError("inserted incident was not readable")
        ticket_id = None
        if ticket_should_exist(children):
            ticket = await self._insert_ticket(incident, parsed.pm_issue_mapping_id)
            ticket_id = ticket.id
            children = bind_seq1_ticket(children, ticket.id)
        await self._append_event(incident, "opened", actor)
        evaluation = await self.insert_evaluation(incident, policy, children)
        await self._audit(
            "ops_incidents.opened",
            actor,
            f"ops_incident:{incident.id}",
            {
                "project_id": str(project_id),
                "incident_id": str(incident.id),
                "status": incident.status,
                "category": incident.category,
                "severity": incident.severity,
                "ticket_written": ticket_id is not None,
                "evaluation_id": str(evaluation.evaluation_id),
                "policy_present": policy.policy_present,
            },
        )
        return await self.snapshot_of(incident)

    async def transition(
        self,
        project_id: uuid.UUID,
        incident_id: uuid.UUID,
        *,
        actor: str,
        to_status: str,
    ) -> IncidentSnapshot:
        incident = await self.get_incident(project_id, incident_id)
        if incident is None:
            raise IncidentError("incident not found")
        current = incident.status
        validate_transition(current, to_status)
        incident.status = to_status
        incident.updated_at = datetime.now(UTC)
        await self._append_event(incident, f"transitioned:{to_status}", actor)
        await self._audit(
            "ops_incidents.transitioned",
            actor,
            f"ops_incident:{incident.id}",
            {
                "project_id": str(project_id),
                "incident_id": str(incident.id),
                "from_status": current,
                "to_status": to_status,
            },
        )
        await self.session.flush()
        return await self.snapshot_of(incident)

    async def record_log_diagnosis_unavailable(
        self, project_id: uuid.UUID, incident_id: uuid.UUID, *, actor: str
    ) -> IncidentSnapshot:
        incident = await self.get_incident(project_id, incident_id)
        if incident is None:
            raise IncidentError("incident not found")
        await self._append_event(incident, "log_diagnosis_unavailable", actor)
        await self._audit(
            "ops_incidents.log_diagnosis_unavailable",
            actor,
            f"ops_incident:{incident.id}",
            {
                "project_id": str(project_id),
                "incident_id": str(incident.id),
                "reason_code": "no_log_source",
            },
        )
        await self.session.flush()
        return await self.snapshot_of(incident)

    async def evaluate_now(
        self, project_id: uuid.UUID, incident_id: uuid.UUID, *, actor: str
    ) -> ActionPrescriptionSet:
        incident = await self.get_incident(project_id, incident_id)
        if incident is None:
            raise IncidentError("incident not found")
        policy = await self.load_policy_snapshot(project_id)
        children = evaluate_actions(await self.load_policy_decisions(project_id))
        existing_ticket = await self.ticket_for(incident.id)
        if ticket_should_exist(children):
            if existing_ticket is None:
                existing_ticket = await self._insert_ticket(incident, None)
            children = bind_seq1_ticket(children, existing_ticket.id)
        await self._append_event(incident, "actions_evaluated", actor)
        evaluation = await self.insert_evaluation(incident, policy, children)
        await self._audit(
            "ops_incidents.actions_evaluated",
            actor,
            f"ops_incident:{incident.id}",
            {
                "project_id": str(project_id),
                "incident_id": str(incident.id),
                "evaluation_id": str(evaluation.evaluation_id),
                "policy_present": policy.policy_present,
                "decisions": [
                    {
                        "seq": child.seq,
                        "action": child.action,
                        "policy_decision": child.policy_decision,
                        "execution_posture": child.execution_posture,
                        "reason_code": child.reason_code,
                    }
                    for child in children
                ],
            },
        )
        return evaluation

    async def record_handover(
        self, project_id: uuid.UUID, *, actor: str, payload: HandoverPayload
    ) -> HandoverRecord:
        if self.context.actor is not None:
            provenance = "request_authenticated"
            subject = self.context.actor.subject
        else:
            provenance = "caller_supplied_unverified"
            subject = None
        validate_handover(
            handed_over_by=payload.handed_over_by,
            received_by=payload.received_by,
            status=payload.status,
            provenance=provenance,
            actor_subject=subject,
        )
        row = OpsSupportHandover(
            project_id=project_id,
            status=payload.status,
            handed_over_by=payload.handed_over_by.strip(),
            received_by=payload.received_by.strip(),
            recorded_by_provenance=provenance,
        )
        await self.add(row)
        await self.session.flush()
        await self._audit(
            "ops_incidents.handover_recorded",
            actor,
            f"ops_support_handover:{row.id}",
            {
                "project_id": str(project_id),
                "handover_id": str(row.id),
                "status": row.status,
                "recorded_by_provenance": provenance,
            },
        )
        return HandoverRecord(
            id=row.id,
            project_id=row.project_id,
            status=row.status,
            recorded_by_provenance=row.recorded_by_provenance,
            handed_over_by=row.handed_over_by,
            received_by=row.received_by,
        )
