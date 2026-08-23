"""Tenant-scoped Slice-59 stabilization-window persistence.

Records an assessment against an immutable §27.13 snapshot. Seq 5 is the only
pass path. Does not close §25.4 or §26.6. Never brokers, never deploys.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.config import settings
from app.models.cost_forecast import CostForecastRun
from app.models.ops_incident import OpsIncident
from app.models.ops_stabilization import (
    OpsImprovementResult,
    OpsStabilizationClosureAttempt,
    OpsStabilizationCriterionResult,
    OpsStabilizationWindow,
)
from app.ops.stabilization import (
    CLOCK_BASIS,
    CRITERION_COUNT,
    FOLLOW_UP_REQUIRED,
    IMPROVEMENT_COUNT,
    RULESET_VERSION,
    WINDOW_STATUS,
    AssessorIdentity,
    ClosureAttemptRecord,
    CriterionChild,
    ImprovementChild,
    StabilizationError,
    StabilizationIdempotencyConflict,
    StabilizationSnapshot,
    assessor_identity,
    input_digest,
    request_digest,
    validate_actor_label,
    validate_age_hours,
    validate_idempotency_key,
)
from app.ops.stabilization_criteria import (
    assemble_criteria,
    assemble_improvements,
    closure_result,
    compute_status_counters,
    evaluate_handover_criterion,
    evaluate_monitoring_criterion,
    evaluate_rollback_criterion,
    oracle_gap_count,
)
from app.release.project_repo import (
    resolve_declared_monitoring_target,
    resolve_declared_stabilization_window,
)
from app.repositories.cost_forecasts import CostForecastRepository
from app.repositories.emergency_controls import latest_stop_event, lock_project_row
from app.repositories.findings import FindingsRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.monitoring_evidence import MonitoringEvidenceRepository
from app.repositories.ops_incidents import OpsIncidentRepository
from app.repositories.ops_stabilization_reads import OpsStabilizationReadMixin
from app.repositories.rollback_verifications import RollbackVerificationRepository
from app.tenancy import TenantContext, TenantScopedRepository


def assert_digest_match(window: OpsStabilizationWindow, digest: str) -> None:
    """Raise when an idempotency winner used a different request digest."""
    if window.request_digest != digest:
        raise StabilizationIdempotencyConflict(
            "idempotency key reused with a different request digest"
        )


class OpsStabilizationRepository(OpsStabilizationReadMixin, TenantScopedRepository):
    """Persist stabilization-window assessments inside an open tenant transaction."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, OpsStabilizationWindow)

    async def assess(
        self,
        project_id: uuid.UUID,
        *,
        actor: str,
        idempotency_key: str,
        extends_window_id: uuid.UUID | None = None,
    ) -> StabilizationSnapshot | None:
        """Insert one assessment. Returns None on idempotent conflict-do-nothing."""
        actor_label = validate_actor_label(actor)
        key = validate_idempotency_key(idempotency_key)
        identity = assessor_identity(self.context.actor, actor_label)
        digest = request_digest(
            project_id=project_id,
            extends_window_id=extends_window_id,
            assessor_subject=identity.subject,
            assessor_actor_type=identity.actor_type,
            assessor_provenance=identity.provenance,
        )
        resolved = await resolve_declared_stabilization_window(
            self.session, self.context, project_id
        )
        if resolved is None:
            raise StabilizationError("no_window_declaration")
        category_id, policy = resolved
        as_of = await self.session.scalar(select(func.transaction_timestamp()))
        if as_of is None:
            raise StabilizationError("transaction_timestamp required")
        monitoring_age = validate_age_hours(
            settings.monitoring_evidence_max_age_hours, name="monitoring_max_age_hours"
        )
        deployment_age = validate_age_hours(
            settings.deployment_evidence_max_age_hours, name="deployment_max_age_hours"
        )
        criteria, improvements, target_ref = await self._observe(
            project_id, as_of=as_of, monitoring_age=monitoring_age
        )
        passed, failed, missing, unevaluable = compute_status_counters(criteria)
        policy_hash = await self._policy_digest_sql(policy)
        snapshot_digest = input_digest(
            as_of=as_of,
            policy_digest_value=policy_hash,
            monitoring_max_age_hours=monitoring_age,
            deployment_max_age_hours=deployment_age,
            criteria=criteria,
            improvements=improvements,
        )
        inserted = await self._try_insert_window(
            project_id=project_id,
            category_id=category_id,
            policy=policy,
            policy_digest_value=policy_hash,
            monitoring_target_ref=target_ref,
            monitoring_age=monitoring_age,
            deployment_age=deployment_age,
            identity=identity,
            extends_window_id=extends_window_id,
            passed=passed,
            failed=failed,
            missing=missing,
            unevaluable=unevaluable,
            request_digest_value=digest,
            input_digest_value=snapshot_digest,
            idempotency_key=key,
        )
        if inserted is None:
            return None
        window = await self._load_window(inserted)
        await self._insert_children(window, criteria, improvements)
        await self._audit_assess(window, actor_label)
        await self.session.flush()
        return await self.snapshot_of(window)

    async def attempt_closure(self, project_id: uuid.UUID, *, actor: str) -> ClosureAttemptRecord:
        """Persist a closure refusal. Window status never changes."""
        actor_label = validate_actor_label(actor)
        await lock_project_row(self.session, self.context, project_id)
        window = await self._latest_row(project_id)
        if window is None:
            raise StabilizationError("no_stabilization_window")
        head = await latest_stop_event(self.session, self.context, project_id)
        latch_active = head is not None and head.state_after == "active"
        result_code = closure_result(
            latch_active=latch_active,
            actor=self.context.actor,
            window_assessor_subject=window.assessor_subject,
            window_assessor_provenance=window.assessor_provenance,
        )
        row = OpsStabilizationClosureAttempt(
            project_id=project_id,
            window_id=window.id,
            result_code=result_code,
            actor=actor_label,
        )
        await self.add(row)
        await self.session.flush()
        await audit_record(
            self.session,
            action="ops_stabilization.closure_attempted",
            actor=actor_label,
            target=f"ops_stabilization_closure_attempt:{row.id}",
            payload={
                "project_id": str(project_id),
                "window_id": str(window.id),
                "attempt_id": str(row.id),
                "result_code": result_code,
                "status": window.status,
            },
        )
        return ClosureAttemptRecord(
            id=row.id,
            window_id=window.id,
            project_id=project_id,
            result_code=result_code,
        )

    async def _policy_digest_sql(self, policy: dict[str, object]) -> str:
        stmt = text("SELECT public.stabilization_policy_digest(:p)").bindparams(
            bindparam("p", value=policy, type_=JSONB)
        )
        digest = await self.session.scalar(stmt)
        if not isinstance(digest, str):
            raise StabilizationError("policy_digest could not be computed")
        return digest

    async def _observe(
        self,
        project_id: uuid.UUID,
        *,
        as_of: datetime,
        monitoring_age: int,
    ) -> tuple[tuple[CriterionChild, ...], tuple[ImprovementChild, ...], str | None]:
        monitoring = await resolve_declared_monitoring_target(
            self.session, self.context, project_id
        )
        target_ref = monitoring[0] if monitoring is not None else None
        snapshot = None
        if target_ref is not None:
            snapshot = await MonitoringEvidenceRepository(
                self.session, self.context
            ).latest_monitoring_for_ref(project_id, "generic_monitoring_api", target_ref)
        coverage, rollback_run = await RollbackVerificationRepository(
            self.session, self.context
        ).coverage_with_run(project_id, as_of=as_of)
        run_id = rollback_run.id if rollback_run is not None else None
        handover = await OpsIncidentRepository(self.session, self.context).latest_handover(
            project_id
        )
        criteria = assemble_criteria(
            evaluate_monitoring_criterion(
                declared_target=target_ref,
                snapshot=snapshot,
                as_of=as_of,
                max_age_hours=monitoring_age,
            ),
            evaluate_rollback_criterion(coverage, run_id),
            evaluate_handover_criterion(handover),
        )
        recurrence = await self._recurrence_count(project_id)
        domain = await IntakeCategoryRepository(self.session, self.context).get_category(
            project_id, "domain_pack"
        )
        findings = await FindingsRepository(self.session, self.context).latest(project_id)
        forecast = await CostForecastRepository(self.session, self.context).coverage_for_project(
            project_id, as_of=as_of
        )
        forecast_id = None
        if forecast.run_present:
            forecast_id = await self._latest_forecast_run_id(project_id)
        improvements = assemble_improvements(
            recurrence_count=recurrence,
            domain_pack_declared=domain is not None and domain.status == "declared",
            findings_report_id=findings.id if findings is not None else None,
            oracle_gap_count=oracle_gap_count(findings) if findings is not None else None,
            forecast_run_id=forecast_id,
            forecast_run_present=forecast.run_present,
        )
        return criteria, improvements, target_ref

    async def _recurrence_count(self, project_id: uuid.UUID) -> int:
        grouped = (
            select(OpsIncident.category)
            .where(
                OpsIncident.tenant_id == self.context.tenant_id,
                OpsIncident.project_id == project_id,
            )
            .group_by(OpsIncident.category)
            .having(func.count() >= 2)
            .subquery()
        )
        value = await self.session.scalar(select(func.count()).select_from(grouped))
        return int(value or 0)

    async def _latest_forecast_run_id(self, project_id: uuid.UUID) -> uuid.UUID | None:
        stmt = (
            select(CostForecastRun.id)
            .where(
                CostForecastRun.tenant_id == self.context.tenant_id,
                CostForecastRun.project_id == project_id,
            )
            .order_by(CostForecastRun.created_at.desc(), CostForecastRun.id.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def _try_insert_window(
        self,
        *,
        project_id: uuid.UUID,
        category_id: uuid.UUID,
        policy: dict[str, object],
        policy_digest_value: str,
        monitoring_target_ref: str | None,
        monitoring_age: int,
        deployment_age: int,
        identity: AssessorIdentity,
        extends_window_id: uuid.UUID | None,
        passed: int,
        failed: int,
        missing: int,
        unevaluable: int,
        request_digest_value: str,
        input_digest_value: str,
        idempotency_key: str,
    ) -> uuid.UUID | None:
        stmt = (
            pg_insert(OpsStabilizationWindow)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                ruleset_version=RULESET_VERSION,
                status=WINDOW_STATUS,
                as_of=func.transaction_timestamp(),
                clock_basis=CLOCK_BASIS,
                category_id=category_id,
                policy_snapshot=policy,
                policy_digest=policy_digest_value,
                monitoring_target_ref=monitoring_target_ref,
                monitoring_max_age_hours=monitoring_age,
                deployment_max_age_hours=deployment_age,
                assessor_subject=identity.subject,
                assessor_actor_type=identity.actor_type,
                assessor_provenance=identity.provenance,
                follow_up_posture=FOLLOW_UP_REQUIRED,
                extension_required=True,
                extends_window_id=extends_window_id,
                criterion_count=CRITERION_COUNT,
                improvement_count=IMPROVEMENT_COUNT,
                passed_count=passed,
                failed_count=failed,
                not_observed_count=missing,
                not_evaluable_count=unevaluable,
                request_digest=request_digest_value,
                input_digest=input_digest_value,
                idempotency_key=idempotency_key,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "project_id", "idempotency_key"],
            )
            .returning(OpsStabilizationWindow.id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _insert_children(
        self,
        window: OpsStabilizationWindow,
        criteria: tuple[CriterionChild, ...],
        improvements: tuple[ImprovementChild, ...],
    ) -> None:
        for child in criteria:
            await self.add(
                OpsStabilizationCriterionResult(
                    project_id=window.project_id,
                    window_id=window.id,
                    seq=child.seq,
                    criterion_key=child.criterion_key,
                    status=child.status,
                    reason=child.reason,
                    monitoring_snapshot_id=child.monitoring_snapshot_id,
                    rollback_verification_run_id=child.rollback_verification_run_id,
                    handover_id=child.handover_id,
                )
            )
        for child in improvements:
            await self.add(
                OpsImprovementResult(
                    project_id=window.project_id,
                    window_id=window.id,
                    seq=child.seq,
                    improvement_class=child.improvement_class,
                    status=child.status,
                    reason=child.reason,
                    findings_report_id=child.findings_report_id,
                    cost_forecast_run_id=child.cost_forecast_run_id,
                    metric_int=child.metric_int,
                    refresh_posture=child.refresh_posture,
                )
            )

    async def _audit_assess(self, window: OpsStabilizationWindow, actor: str) -> None:
        await audit_record(
            self.session,
            action="ops_stabilization.recorded",
            actor=actor,
            target=f"ops_stabilization_window:{window.id}",
            payload={
                "project_id": str(window.project_id),
                "window_id": str(window.id),
                "status": window.status,
                "passed_count": window.passed_count,
                "failed_count": window.failed_count,
                "not_observed_count": window.not_observed_count,
                "not_evaluable_count": window.not_evaluable_count,
                "policy_digest": window.policy_digest,
                "request_digest": window.request_digest,
                "input_digest": window.input_digest,
                "monitoring_target_bound": window.monitoring_target_ref is not None,
                "assessor_provenance": window.assessor_provenance,
                "extension_required": window.extension_required,
            },
        )
