"""Tenant-scoped Slice-51 cost-policy and deterministic forecast persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.concurrency import ConcurrentWriteUnresolved
from app.cost import BudgetCeilings, evaluate_stop
from app.cost_forecast import (
    COST_POLICY_CONTRACT_HASH,
    COST_POLICY_CONTRACT_VERSION,
    POLICY_PROVENANCE,
    ComponentAssumption,
    CostForecastError,
    ForecastInput,
    ModelForecastLine,
    StructuredCostPolicy,
    derive_forecast,
    parse_structured_policy,
)
from app.llm.pricing import ModelPrice, UnpricedModelError, get_price
from app.models.budget import Budget
from app.models.cost_forecast import CostForecastPolicyVersion, CostForecastRun
from app.repositories.cost_forecast_coverage import _CostForecastCoverageMixin
from app.repositories.cost_forecast_persistence import _CostForecastPersistenceMixin
from app.repositories.cost_forecast_types import (
    CostForecastCoverage,
    CostForecastRepositoryError,
    ReportedModelPlan,
    _percent,
    _route_hash,
    _storage_hash,
    _money,
)
from app.repositories.evidence_packs import EvidencePackRepository, EvidencePackRepositoryError
from app.repositories.release_candidates import ReleaseCandidateRepository
from app.tenancy import TenantContext

__all__ = [
    "CostForecastCoverage",
    "CostForecastRepository",
    "CostForecastRepositoryError",
    "ReportedModelPlan",
]


class CostForecastRepository(_CostForecastPersistenceMixin, _CostForecastCoverageMixin):
    def __init__(self, session: AsyncSession, context: TenantContext):
        self.session = session
        self.context = context

    async def _latest_policy(self, project_id: uuid.UUID) -> CostForecastPolicyVersion | None:
        stmt = (
            select(CostForecastPolicyVersion)
            .where(
                CostForecastPolicyVersion.tenant_id == self.context.tenant_id,
                CostForecastPolicyVersion.project_id == project_id,
            )
            .order_by(
                CostForecastPolicyVersion.created_at.desc(), CostForecastPolicyVersion.id.desc()
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def record_policy_version(
        self,
        *,
        project_id: uuid.UUID,
        payload: Mapping,
        source_label: str | None,
        evidence_ref: str | None,
        actor: str,
    ) -> CostForecastPolicyVersion:
        parsed = parse_structured_policy(payload)
        if source_label is not None and (not source_label.strip() or len(source_label) > 255):
            raise CostForecastRepositoryError("source_label_invalid")
        if evidence_ref is not None and (not evidence_ref.strip() or len(evidence_ref) > 500):
            raise CostForecastRepositoryError("evidence_ref_invalid")
        digest = _storage_hash(
            COST_POLICY_CONTRACT_VERSION,
            _money(parsed.max_total_model_cost_usd),
            _money(parsed.max_daily_model_cost_usd),
            _money(parsed.max_cloud_spend_usd),
            _money(parsed.max_ci_minutes_per_day),
            _percent(parsed.require_approval_above_forecast_percentage),
            str(parsed.cheap_first_for_low_risk).lower(),
            str(parsed.frontier_for_high_risk).lower(),
            str(parsed.use_cached_context_when_possible).lower(),
            ",".join(parsed.stop_conditions),
            POLICY_PROVENANCE,
        )
        existing = (
            await self.session.execute(
                select(CostForecastPolicyVersion).where(
                    CostForecastPolicyVersion.tenant_id == self.context.tenant_id,
                    CostForecastPolicyVersion.project_id == project_id,
                    CostForecastPolicyVersion.policy_digest == digest,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        stmt = (
            pg_insert(CostForecastPolicyVersion)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                policy_contract_version=COST_POLICY_CONTRACT_VERSION,
                policy_contract_hash=COST_POLICY_CONTRACT_HASH,
                policy_digest=digest,
                max_total_model_cost_usd=parsed.max_total_model_cost_usd,
                max_daily_model_cost_usd=parsed.max_daily_model_cost_usd,
                max_cloud_spend_usd=parsed.max_cloud_spend_usd,
                max_ci_minutes_per_day=parsed.max_ci_minutes_per_day,
                require_approval_above_forecast_percentage=(
                    parsed.require_approval_above_forecast_percentage
                ),
                cheap_first_for_low_risk=parsed.cheap_first_for_low_risk,
                frontier_for_high_risk=parsed.frontier_for_high_risk,
                use_cached_context_when_possible=parsed.use_cached_context_when_possible,
                stop_conditions=list(parsed.stop_conditions),
                stop_condition_count=4,
                source_provenance=POLICY_PROVENANCE,
                source_label=source_label,
                evidence_ref=evidence_ref,
            )
            .on_conflict_do_nothing(constraint="uq_cfpv_project_digest")
            .returning(CostForecastPolicyVersion.id)
        )
        new_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if new_id is None:
            winner = (
                await self.session.execute(
                    select(CostForecastPolicyVersion).where(
                        CostForecastPolicyVersion.tenant_id == self.context.tenant_id,
                        CostForecastPolicyVersion.project_id == project_id,
                        CostForecastPolicyVersion.policy_digest == digest,
                    )
                )
            ).scalar_one_or_none()
            if winner is None:
                raise ConcurrentWriteUnresolved("uq_cfpv_project_digest")
            return winner
        row = (
            await self.session.execute(
                select(CostForecastPolicyVersion).where(CostForecastPolicyVersion.id == new_id)
            )
        ).scalar_one()
        await audit_record(
            self.session,
            action="cost_forecast.policy_recorded",
            actor=actor,
            target=str(row.id),
            payload={
                "project_id": str(project_id),
                "policy_version_id": str(row.id),
                "policy_digest": digest,
                "contract_version": COST_POLICY_CONTRACT_VERSION,
                "source_provenance": POLICY_PROVENANCE,
            },
        )
        return row

    @staticmethod
    def _policy_value(row: CostForecastPolicyVersion) -> StructuredCostPolicy:
        return StructuredCostPolicy(
            max_total_model_cost_usd=row.max_total_model_cost_usd,
            max_daily_model_cost_usd=row.max_daily_model_cost_usd,
            max_cloud_spend_usd=row.max_cloud_spend_usd,
            max_ci_minutes_per_day=row.max_ci_minutes_per_day,
            require_approval_above_forecast_percentage=row.require_approval_above_forecast_percentage,
            cheap_first_for_low_risk=row.cheap_first_for_low_risk,
            frontier_for_high_risk=row.frontier_for_high_risk,
            use_cached_context_when_possible=row.use_cached_context_when_possible,
            stop_conditions=tuple(row.stop_conditions),
            policy_digest=row.policy_digest,
        )

    async def generate_forecast(
        self,
        *,
        project_id: uuid.UUID,
        assumptions: Sequence[ComponentAssumption],
        model_plans: Sequence[ReportedModelPlan],
        price_card: dict[str, ModelPrice] | None,
        forecast_ci_minutes_today: int,
        actor: str,
        as_of: datetime | None = None,
    ) -> CostForecastRun:
        as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidate = await ReleaseCandidateRepository(self.session, self.context).latest_frozen(
            project_id
        )
        if candidate is None:
            return await self._record_refusal(project_id, as_of, "no_current_release_scope", actor)
        pack = await self._latest_pack(candidate.id)
        if pack is None:
            return await self._record_refusal(
                project_id,
                as_of,
                "no_complete_reauditable_evidence_core",
                actor,
                candidate=candidate,
            )
        try:
            await EvidencePackRepository(self.session, self.context).audit_pack(pack.id)
        except EvidencePackRepositoryError:
            return await self._record_refusal(
                project_id,
                as_of,
                "evidence_core_reaudit_failed",
                actor,
                candidate=candidate,
                pack=pack,
            )
        policy = await self._latest_policy(project_id)
        if policy is None:
            return await self._record_refusal(
                project_id, as_of, "no_current_structured_cost_policy", actor, candidate, pack
            )
        budget = (
            await self.session.execute(
                select(Budget).where(
                    Budget.tenant_id == self.context.tenant_id, Budget.project_id == project_id
                )
            )
        ).scalar_one_or_none()
        if budget is None or budget.max_daily_cost_usd is None:
            return await self._record_refusal(
                project_id,
                as_of,
                "no_current_cost_budget",
                actor,
                candidate,
                pack,
                policy,
            )
        events = await self._events(project_id)
        if not events:
            return await self._record_refusal(
                project_id,
                as_of,
                "no_cost_history",
                actor,
                candidate,
                pack,
                policy,
                budget,
            )
        model_lines: list[ModelForecastLine] = []
        try:
            if len(events) > 50_000:
                raise CostForecastError("ledger event inventory exceeds 50000")
            if len(model_plans) > 128:
                raise CostForecastError("model price inventory exceeds 128")
            for plan in model_plans:
                price = get_price(plan.model_route, price_card)
                model_lines.append(
                    ModelForecastLine(
                        model_route_hash=_route_hash(plan.model_route),
                        remaining_input_tokens=plan.remaining_input_tokens,
                        remaining_output_tokens=plan.remaining_output_tokens,
                        remaining_today_input_tokens=plan.remaining_today_input_tokens,
                        remaining_today_output_tokens=plan.remaining_today_output_tokens,
                        price=price,
                    )
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
                budget=BudgetCeilings(budget.max_total_cost_usd, budget.max_daily_cost_usd),
            )
            decision = derive_forecast(
                ForecastInput(
                    policy=self._policy_value(policy),
                    budget_total_usd=budget.max_total_cost_usd,
                    budget_daily_usd=budget.max_daily_cost_usd,
                    ledger_lines=tuple(self._event_line(event) for event in events),
                    assumptions=tuple(assumptions),
                    model_lines=tuple(model_lines),
                    forecast_ci_minutes_today=forecast_ci_minutes_today,
                    stop_reason=stop.reason.value if stop.stop else "ok",
                    as_of=as_of,
                )
            )
        except (CostForecastError, UnpricedModelError, CostForecastRepositoryError) as exc:
            return await self._record_refusal(
                project_id,
                as_of,
                "cost_forecast_input_or_price_invalid",
                actor,
                candidate,
                pack,
                policy,
                budget,
                detail_code=type(exc).__name__,
            )
        return await self._persist_success(
            project_id=project_id,
            candidate=candidate,
            pack=pack,
            policy=policy,
            budget=budget,
            events=events,
            assumptions=assumptions,
            model_lines=model_lines,
            forecast_ci_minutes_today=forecast_ci_minutes_today,
            decision=decision,
            stop_reason=stop.reason.value if stop.stop else "ok",
            as_of=as_of,
            actor=actor,
        )
