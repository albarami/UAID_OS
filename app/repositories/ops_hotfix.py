"""Tenant-scoped Slice-58 hotfix-intent persistence.

Local A2 plans only. Never brokers, never writes git, never deploys, never
rolls back production. Does not close §26.6.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.ops_hotfix import OpsHotfixPlan, OpsSelfHealingResult, OpsSelfHealingRun
from app.models.ops_incident import OpsIncident
from app.ops.hotfix import (
    ACTION_COUNT,
    MATRIX_ACTIONS,
    RULESET_VERSION,
    HotfixChild,
    HotfixError,
    HotfixIdempotencyConflict,
    HotfixIntentSnapshot,
    authorization_matches,
    bind_plans,
    decision_snapshot_payload,
    evaluate_hotfix_actions,
    gate10_conjunction_passed,
    incident_is_evaluable,
    local_intended_ref,
    policy_input_digest,
    request_digest,
    rollback_coverage_digest,
    validate_history_limit,
    validate_idempotency_key,
)
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.emergency_controls import (
    EmergencyControlRepository,
    assert_project_not_stopped,
)
from app.repositories.rollback_verifications import RollbackVerificationRepository
from app.tenancy import TenantContext, TenantScopedRepository


class OpsHotfixRepository(TenantScopedRepository):
    """Persist hotfix-intent evaluations inside an open tenant transaction."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, OpsSelfHealingRun)

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
        self, project_id: uuid.UUID, incident_id: uuid.UUID, idempotency_key: str
    ) -> OpsSelfHealingRun | None:
        stmt = select(OpsSelfHealingRun).where(
            OpsSelfHealingRun.tenant_id == self.context.tenant_id,
            OpsSelfHealingRun.project_id == project_id,
            OpsSelfHealingRun.incident_id == incident_id,
            OpsSelfHealingRun.idempotency_key == idempotency_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _current_context_fks(
        self, project_id: uuid.UUID
    ) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None, str]:
        coverage, latest = await RollbackVerificationRepository(
            self.session, self.context
        ).coverage_with_run(project_id)
        coverage_digest = rollback_coverage_digest(coverage)
        run_id = latest.id if latest is not None and gate10_conjunction_passed(coverage) else None
        emergency = EmergencyControlRepository(self.session, self.context)
        binding = await emergency.latest_binding(project_id)
        binding_id = binding.id if binding is not None else None
        auth_id: uuid.UUID | None = None
        if binding is not None:
            candidate, core, rb_run, digest = await emergency.current_release_binding_context(
                project_id
            )
            if (
                candidate is not None
                and core is not None
                and rb_run is not None
                and digest is not None
            ):
                auth = await emergency.matching_rollback_authorization(
                    binding=binding,
                    candidate_id=getattr(candidate, "id"),
                    evidence_pack_id=getattr(core, "id"),
                    rollback_verification_run_id=rb_run.id,
                    release_rollback_binding_digest=digest,
                )
                if auth is not None and authorization_matches(
                    binding_id=binding.id,
                    candidate_id=getattr(candidate, "id"),
                    evidence_pack_id=getattr(core, "id"),
                    rollback_run_id=rb_run.id,
                    binding_digest=digest,
                    authorization_binding_id=auth.binding_id,
                    authorization_candidate_id=auth.release_candidate_id,
                    authorization_pack_id=auth.evidence_pack_id,
                    authorization_run_id=auth.rollback_verification_run_id,
                    authorization_digest=auth.release_rollback_binding_digest,
                    result_code=auth.result_code,
                ):
                    auth_id = auth.id
        return run_id, binding_id, auth_id, coverage_digest

    async def snapshot_of(self, run: OpsSelfHealingRun) -> HotfixIntentSnapshot:
        rows = (
            (
                await self.session.execute(
                    select(OpsSelfHealingResult)
                    .where(
                        OpsSelfHealingResult.tenant_id == self.context.tenant_id,
                        OpsSelfHealingResult.run_id == run.id,
                    )
                    .order_by(OpsSelfHealingResult.seq)
                )
            )
            .scalars()
            .all()
        )
        children = tuple(
            HotfixChild(
                seq=row.seq,
                action=row.action,
                matrix_action=row.matrix_action,
                policy_decision=row.policy_decision,
                execution_posture=row.execution_posture,
                reason_code=row.reason_code,
                plan_id=row.plan_id,
                plan_kind=row.plan_kind,
            )
            for row in rows
        )
        return HotfixIntentSnapshot(
            id=run.id,
            project_id=run.project_id,
            incident_id=run.incident_id,
            ruleset_version=run.ruleset_version,
            request_digest=run.request_digest,
            policy_present=run.policy_present,
            policy_id=run.policy_id,
            autonomy_level=run.autonomy_level_snapshot,
            policy_input_digest=run.policy_input_digest,
            rollback_verification_run_id=run.rollback_verification_run_id,
            emergency_control_binding_id=run.emergency_control_binding_id,
            emergency_rollback_authorization_id=run.emergency_rollback_authorization_id,
            rollback_run_present=run.rollback_verification_run_id is not None,
            standing_binding_present=run.emergency_control_binding_id is not None,
            rollback_authorization_present=run.emergency_rollback_authorization_id is not None,
            actions=children,
        )

    async def latest(
        self, project_id: uuid.UUID, incident_id: uuid.UUID
    ) -> HotfixIntentSnapshot | None:
        stmt = (
            select(OpsSelfHealingRun)
            .where(
                OpsSelfHealingRun.tenant_id == self.context.tenant_id,
                OpsSelfHealingRun.project_id == project_id,
                OpsSelfHealingRun.incident_id == incident_id,
            )
            .order_by(OpsSelfHealingRun.created_at.desc(), OpsSelfHealingRun.id.desc())
            .limit(1)
        )
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if run is None:
            return None
        return await self.snapshot_of(run)

    async def history(
        self, project_id: uuid.UUID, incident_id: uuid.UUID, *, limit: int
    ) -> list[HotfixIntentSnapshot]:
        bounded = validate_history_limit(limit)
        stmt = (
            select(OpsSelfHealingRun)
            .where(
                OpsSelfHealingRun.tenant_id == self.context.tenant_id,
                OpsSelfHealingRun.project_id == project_id,
                OpsSelfHealingRun.incident_id == incident_id,
            )
            .order_by(OpsSelfHealingRun.created_at.desc(), OpsSelfHealingRun.id.desc())
            .limit(bounded)
        )
        runs = (await self.session.execute(stmt)).scalars().all()
        return [await self.snapshot_of(run) for run in runs]

    async def evaluate(
        self,
        project_id: uuid.UUID,
        incident_id: uuid.UUID,
        *,
        actor: str,
        idempotency_key: str,
    ) -> HotfixIntentSnapshot | None:
        """Insert one evaluation. Returns None on idempotent conflict-do-nothing."""
        key = validate_idempotency_key(idempotency_key)
        digest = request_digest(incident_id)
        await assert_project_not_stopped(self.session, self.context, project_id)
        incident = await self.get_incident(project_id, incident_id)
        if incident is None or not incident_is_evaluable(incident.status):
            raise HotfixError("incident is not evaluable")
        snapshot = await AutonomyPolicyRepository(self.session, self.context).snapshot_decisions(
            project_id, MATRIX_ACTIONS
        )
        children = evaluate_hotfix_actions(snapshot.decisions)
        run_id, binding_id, auth_id, coverage_digest = await self._current_context_fks(project_id)
        inserted = await self._try_insert_run(
            project_id=project_id,
            incident_id=incident_id,
            snapshot=snapshot,
            digest=digest,
            idempotency_key=key,
            run_fk=run_id,
            binding_id=binding_id,
            auth_id=auth_id,
            coverage_digest=coverage_digest,
        )
        if inserted is None:
            return None
        run = await self._load_run(inserted)
        branch_plan_id, pr_plan_id = await self._insert_plans(run, children)
        bound = bind_plans(children, branch_plan_id=branch_plan_id, pr_plan_id=pr_plan_id)
        await self._insert_children(run, bound)
        await self._audit(run, actor, bound)
        await self.session.flush()
        return await self.snapshot_of(run)

    async def _load_run(self, run_id: uuid.UUID) -> OpsSelfHealingRun:
        stmt = select(OpsSelfHealingRun).where(
            OpsSelfHealingRun.tenant_id == self.context.tenant_id,
            OpsSelfHealingRun.id == run_id,
        )
        run = (await self.session.execute(stmt)).scalar_one()
        return run

    async def _try_insert_run(
        self,
        *,
        project_id: uuid.UUID,
        incident_id: uuid.UUID,
        snapshot,
        digest: str,
        idempotency_key: str,
        run_fk: uuid.UUID | None,
        binding_id: uuid.UUID | None,
        auth_id: uuid.UUID | None,
        coverage_digest: str,
    ) -> uuid.UUID | None:
        stmt = (
            pg_insert(OpsSelfHealingRun)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                incident_id=incident_id,
                ruleset_version=RULESET_VERSION,
                action_count=ACTION_COUNT,
                policy_present=snapshot.policy_present,
                policy_id=snapshot.policy_id,
                autonomy_level_snapshot=snapshot.autonomy_level,
                policy_input_digest=policy_input_digest(
                    policy_present=snapshot.policy_present,
                    policy_id=snapshot.policy_id,
                    autonomy_level=snapshot.autonomy_level,
                    overrides=snapshot.overrides,
                ),
                request_digest=digest,
                decision_snapshot=decision_snapshot_payload(snapshot.decisions),
                idempotency_key=idempotency_key,
                rollback_verification_run_id=run_fk,
                emergency_control_binding_id=binding_id,
                emergency_rollback_authorization_id=auth_id,
                rollback_coverage_digest=coverage_digest,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "project_id", "incident_id", "idempotency_key"],
            )
            .returning(OpsSelfHealingRun.id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _insert_plans(
        self, run: OpsSelfHealingRun, children: Sequence[HotfixChild]
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        mapped = {child.seq: child for child in children}
        branch_id: uuid.UUID | None = None
        pr_id: uuid.UUID | None = None
        if mapped[3].reason_code == "plan_written":
            plan = OpsHotfixPlan(
                project_id=run.project_id,
                incident_id=run.incident_id,
                run_id=run.id,
                plan_kind="patch_branch",
                intended_ref=local_intended_ref("patch_branch", run.incident_id),
            )
            await self.add(plan)
            await self.session.flush()
            branch_id = plan.id
        if mapped[4].reason_code == "plan_written":
            plan = OpsHotfixPlan(
                project_id=run.project_id,
                incident_id=run.incident_id,
                run_id=run.id,
                plan_kind="hotfix_pr",
                intended_ref=local_intended_ref("hotfix_pr", run.incident_id),
            )
            await self.add(plan)
            await self.session.flush()
            pr_id = plan.id
        return branch_id, pr_id

    async def _insert_children(
        self, run: OpsSelfHealingRun, children: Sequence[HotfixChild]
    ) -> None:
        for child in children:
            await self.add(
                OpsSelfHealingResult(
                    project_id=run.project_id,
                    incident_id=run.incident_id,
                    run_id=run.id,
                    seq=child.seq,
                    action=child.action,
                    matrix_action=child.matrix_action,
                    policy_decision=child.policy_decision,
                    execution_posture=child.execution_posture,
                    reason_code=child.reason_code,
                    plan_id=child.plan_id,
                    plan_kind=child.plan_kind,
                )
            )

    async def _audit(
        self, run: OpsSelfHealingRun, actor: str, children: Sequence[HotfixChild]
    ) -> None:
        await audit_record(
            self.session,
            action="ops_hotfix_intent.recorded",
            actor=actor,
            target=f"ops_self_healing_run:{run.id}",
            payload={
                "project_id": str(run.project_id),
                "incident_id": str(run.incident_id),
                "run_id": str(run.id),
                "policy_present": run.policy_present,
                "rollback_run_present": run.rollback_verification_run_id is not None,
                "standing_binding_present": run.emergency_control_binding_id is not None,
                "rollback_authorization_present": (
                    run.emergency_rollback_authorization_id is not None
                ),
                "plan_count": sum(1 for child in children if child.plan_id is not None),
                "decisions": [
                    {
                        "seq": child.seq,
                        "policy_decision": child.policy_decision,
                        "execution_posture": child.execution_posture,
                        "reason_code": child.reason_code,
                    }
                    for child in children
                ],
            },
        )


def assert_digest_match(run: OpsSelfHealingRun, digest: str) -> None:
    """Raise when an idempotency winner used a different request digest."""
    if run.request_digest != digest:
        raise HotfixIdempotencyConflict("idempotency key reused with a different request digest")
