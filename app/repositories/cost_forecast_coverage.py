"""Coverage-read mixin for Slice-51 cost-forecast evidence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cost import BudgetCeilings, evaluate_stop
from app.cost_forecast import LedgerCostLine
from app.models.budget import Budget
from app.models.cost_event import CostEvent
from app.models.cost_forecast import CostForecastRun
from app.models.evidence_pack import EvidencePack
from app.repositories.cost_forecast_types import (
    CostForecastCoverage,
    _money,
    _storage_hash,
    _utc_text,
)
from app.repositories.evidence_packs import EvidencePackRepository, EvidencePackRepositoryError
from app.repositories.release_candidates import ReleaseCandidateRepository
from app.tenancy import TenantContext


class _CostForecastCoverageMixin:
    session: AsyncSession
    context: TenantContext

    async def _latest_pack(self, candidate_id: uuid.UUID) -> EvidencePack | None:
        stmt = (
            select(EvidencePack)
            .where(
                EvidencePack.tenant_id == self.context.tenant_id,
                EvidencePack.release_candidate_id == candidate_id,
                EvidencePack.assembly_status == "complete",
            )
            .order_by(EvidencePack.created_at.desc(), EvidencePack.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def _events(self, project_id: uuid.UUID) -> list[CostEvent]:
        stmt = (
            select(CostEvent)
            .where(
                CostEvent.tenant_id == self.context.tenant_id,
                CostEvent.project_id == project_id,
            )
            .order_by(CostEvent.occurred_at, CostEvent.id)
            .limit(50_001)
        )
        return list((await self.session.execute(stmt)).scalars())

    def _event_line(self, event: CostEvent) -> LedgerCostLine:
        digest = _storage_hash(
            str(event.id),
            str(event.tenant_id),
            str(event.project_id),
            event.component,
            _money(event.amount_usd),
            _utc_text(event.occurred_at),
        )
        return LedgerCostLine(
            event_id=str(event.id),
            component=event.component,
            amount_usd=event.amount_usd,
            occurred_at=event.occurred_at,
            material_digest=digest,
        )

    async def coverage_for_project(
        self, project_id: uuid.UUID, *, as_of: datetime | None = None
    ) -> CostForecastCoverage:
        as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidate = await ReleaseCandidateRepository(self.session, self.context).latest_frozen(
            project_id
        )
        policy = await self._latest_policy(project_id)
        budget = (
            await self.session.execute(
                select(Budget).where(
                    Budget.tenant_id == self.context.tenant_id, Budget.project_id == project_id
                )
            )
        ).scalar_one_or_none()
        events = await self._events(project_id)
        pack = await self._latest_pack(candidate.id) if candidate else None
        scope_resolved = candidate is not None and pack is not None
        if pack is not None:
            try:
                await EvidencePackRepository(self.session, self.context).audit_pack(pack.id)
            except EvidencePackRepositoryError:
                scope_resolved = False
        run = (
            (
                await self.session.execute(
                    select(CostForecastRun)
                    .where(
                        CostForecastRun.tenant_id == self.context.tenant_id,
                        CostForecastRun.project_id == project_id,
                    )
                    .order_by(CostForecastRun.created_at.desc(), CostForecastRun.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        budget_valid = bool(
            budget
            and budget.max_total_cost_usd > 0
            and budget.max_daily_cost_usd is not None
            and budget.max_daily_cost_usd > 0
        )
        policy_valid = bool(
            policy
            and policy.max_total_model_cost_usd > 0
            and policy.max_daily_model_cost_usd > 0
            and policy.max_cloud_spend_usd > 0
            and policy.max_ci_minutes_per_day > 0
        )
        total = sum((event.amount_usd for event in events), Decimal(0))
        daily = sum(
            (
                event.amount_usd
                for event in events
                if event.occurred_at.astimezone(timezone.utc).date() == as_of.date()
            ),
            Decimal(0),
        )
        stop = evaluate_stop(
            total_spent=total,
            daily_spent=daily,
            budget=(
                BudgetCeilings(budget.max_total_cost_usd, budget.max_daily_cost_usd)
                if budget_valid
                else None
            ),
        )
        current_event_lines = [self._event_line(event) for event in events]
        current_ledger_digest = _storage_hash(
            *(line.material_digest for line in current_event_lines)
        )
        current_budget_digest = (
            _storage_hash(
                str(budget.id),
                _money(budget.max_total_cost_usd),
                _money(budget.max_daily_cost_usd),
            )
            if budget_valid and budget is not None
            else None
        )
        current = bool(
            run
            and run.outcome == "succeeded"
            and candidate
            and pack
            and policy
            and budget
            and run.release_candidate_id == candidate.id
            and run.evidence_pack_id == pack.id
            and run.policy_version_id == policy.id
            and run.budget_id == budget.id
            and run.core_content_hash == pack.core_content_hash
            and run.budget_total_usd == budget.max_total_cost_usd
            and run.budget_daily_usd == budget.max_daily_cost_usd
            and run.budget_digest == current_budget_digest
            and run.ledger_digest == current_ledger_digest
            and run.event_ref_count == len(events)
            and run.forecast_utc_date == as_of.date()
        )
        return CostForecastCoverage(
            scope_resolved=scope_resolved,
            policy_present=policy is not None,
            policy_valid=policy_valid,
            budget_present=budget is not None,
            budget_valid=budget_valid,
            history_count=len(events),
            run_present=run is not None,
            attempt_failed=bool(run and run.outcome in {"failed", "refused"}),
            binding_current=current,
            input_coverage_complete=bool(
                current and run and run.input_line_count >= 9 and run.event_ref_count > 0
            ),
            price_coverage_complete=bool(current and run and run.model_line_count >= 0),
            evidence_consistent=bool(current and run and run.evidence_consistent),
            stop_active=stop.stop,
            all_dimensions_within=bool(current and run and run.all_dimensions_within),
            approval_required=bool(current and run and run.approval_required),
            gate_eligible=bool(current and run and run.gate_eligible and not stop.stop),
            dimension_count=run.dimension_count if run else 0,
            forecast_utc_date=run.forecast_utc_date.isoformat() if run else None,
            execution_provenance=run.execution_provenance if run else None,
        )
