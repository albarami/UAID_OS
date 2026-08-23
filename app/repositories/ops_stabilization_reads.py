"""Read helpers for the Slice-59 stabilization-window store. Not an HTTP surface."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops_stabilization import (
    OpsImprovementResult,
    OpsStabilizationCriterionResult,
    OpsStabilizationWindow,
)
from app.ops.stabilization import (
    HISTORY_LIMIT_DEFAULT,
    CriterionChild,
    ImprovementChild,
    StabilizationSnapshot,
    validate_history_limit,
)
from app.tenancy import TenantContext


class OpsStabilizationReadMixin:
    """Latest-wins and history queries over recorded stabilization windows."""

    session: AsyncSession
    context: TenantContext

    async def get_by_idempotency(
        self, project_id: uuid.UUID, idempotency_key: str
    ) -> OpsStabilizationWindow | None:
        """Return the window for an idempotency key, or ``None``."""
        stmt = select(OpsStabilizationWindow).where(
            OpsStabilizationWindow.tenant_id == self.context.tenant_id,
            OpsStabilizationWindow.project_id == project_id,
            OpsStabilizationWindow.idempotency_key == idempotency_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def snapshot_of(self, window: OpsStabilizationWindow) -> StabilizationSnapshot:
        """Load child rows and return the safe snapshot surface."""
        criteria = (
            (
                await self.session.execute(
                    select(OpsStabilizationCriterionResult)
                    .where(
                        OpsStabilizationCriterionResult.tenant_id == self.context.tenant_id,
                        OpsStabilizationCriterionResult.window_id == window.id,
                    )
                    .order_by(OpsStabilizationCriterionResult.seq)
                )
            )
            .scalars()
            .all()
        )
        improvements = (
            (
                await self.session.execute(
                    select(OpsImprovementResult)
                    .where(
                        OpsImprovementResult.tenant_id == self.context.tenant_id,
                        OpsImprovementResult.window_id == window.id,
                    )
                    .order_by(OpsImprovementResult.seq)
                )
            )
            .scalars()
            .all()
        )
        return StabilizationSnapshot(
            id=window.id,
            project_id=window.project_id,
            ruleset_version=window.ruleset_version,
            status=window.status,
            as_of=window.as_of,
            clock_basis=window.clock_basis,
            policy_digest=window.policy_digest,
            monitoring_target_bound=window.monitoring_target_ref is not None,
            extension_required=window.extension_required,
            follow_up_posture=window.follow_up_posture,
            extends_window_id=window.extends_window_id,
            passed_count=window.passed_count,
            failed_count=window.failed_count,
            not_observed_count=window.not_observed_count,
            not_evaluable_count=window.not_evaluable_count,
            request_digest=window.request_digest,
            input_digest=window.input_digest,
            assessor_provenance=window.assessor_provenance,
            criteria=tuple(
                CriterionChild(
                    seq=row.seq,
                    criterion_key=row.criterion_key,
                    status=row.status,
                    reason=row.reason,
                    monitoring_snapshot_id=row.monitoring_snapshot_id,
                    rollback_verification_run_id=row.rollback_verification_run_id,
                    handover_id=row.handover_id,
                )
                for row in criteria
            ),
            improvements=tuple(
                ImprovementChild(
                    seq=row.seq,
                    improvement_class=row.improvement_class,
                    status=row.status,
                    reason=row.reason,
                    findings_report_id=row.findings_report_id,
                    cost_forecast_run_id=row.cost_forecast_run_id,
                    metric_int=row.metric_int,
                    refresh_posture=row.refresh_posture,
                )
                for row in improvements
            ),
        )

    async def latest(self, project_id: uuid.UUID) -> StabilizationSnapshot | None:
        """Return the newest window for the project, or ``None``."""
        window = await self._latest_row(project_id)
        if window is None:
            return None
        return await self.snapshot_of(window)

    async def history(
        self, project_id: uuid.UUID, *, limit: int = HISTORY_LIMIT_DEFAULT
    ) -> list[StabilizationSnapshot]:
        """Return newest-first history for the project."""
        bounded = validate_history_limit(limit)
        stmt = (
            select(OpsStabilizationWindow)
            .where(
                OpsStabilizationWindow.tenant_id == self.context.tenant_id,
                OpsStabilizationWindow.project_id == project_id,
            )
            .order_by(OpsStabilizationWindow.created_at.desc(), OpsStabilizationWindow.id.desc())
            .limit(bounded)
        )
        windows = (await self.session.execute(stmt)).scalars().all()
        return [await self.snapshot_of(window) for window in windows]

    async def _latest_row(self, project_id: uuid.UUID) -> OpsStabilizationWindow | None:
        stmt = (
            select(OpsStabilizationWindow)
            .where(
                OpsStabilizationWindow.tenant_id == self.context.tenant_id,
                OpsStabilizationWindow.project_id == project_id,
            )
            .order_by(OpsStabilizationWindow.created_at.desc(), OpsStabilizationWindow.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _load_window(self, window_id: uuid.UUID) -> OpsStabilizationWindow:
        stmt = select(OpsStabilizationWindow).where(
            OpsStabilizationWindow.tenant_id == self.context.tenant_id,
            OpsStabilizationWindow.id == window_id,
        )
        return (await self.session.execute(stmt)).scalar_one()
