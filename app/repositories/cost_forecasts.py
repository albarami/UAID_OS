"""Tenant-scoped Slice-51 cost-policy and deterministic forecast persistence."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.cost import BudgetCeilings, evaluate_stop
from app.cost_forecast import (
    ASSUMPTION_PROVENANCE,
    COST_FORECAST_CONTRACT_HASH,
    COST_FORECAST_CONTRACT_VERSION,
    COST_FORECAST_INPUT_CONTRACT_HASH,
    COST_FORECAST_INPUT_CONTRACT_VERSION,
    COST_POLICY_CONTRACT_HASH,
    COST_POLICY_CONTRACT_VERSION,
    EXECUTION_PROVENANCE,
    LEDGER_PROVENANCE,
    POLICY_PROVENANCE,
    PRICE_PROVENANCE,
    ComponentAssumption,
    CostForecastError,
    ForecastInput,
    LedgerCostLine,
    ModelForecastLine,
    StructuredCostPolicy,
    derive_forecast,
    parse_structured_policy,
)
from app.llm.pricing import ModelPrice, UnpricedModelError, get_price
from app.models.budget import Budget
from app.models.cost_event import CostEvent
from app.models.cost_forecast import (
    CostForecastDimensionResult,
    CostForecastInputLine,
    CostForecastLedgerEventRef,
    CostForecastPolicyVersion,
    CostForecastRun,
)
from app.models.evidence_pack import EvidencePack
from app.models.release_candidate import ReleaseCandidate
from app.repositories.evidence_packs import EvidencePackRepository, EvidencePackRepositoryError
from app.repositories.release_candidates import ReleaseCandidateRepository
from app.tenancy import TenantContext


class CostForecastRepositoryError(ValueError):
    """The exact evidence required for a forecast is missing or inconsistent."""


@dataclass(frozen=True)
class ReportedModelPlan:
    model_route: str
    remaining_input_tokens: int
    remaining_output_tokens: int
    remaining_today_input_tokens: int
    remaining_today_output_tokens: int


@dataclass(frozen=True)
class CostForecastCoverage:
    scope_resolved: bool = False
    policy_present: bool = False
    policy_valid: bool = False
    budget_present: bool = False
    budget_valid: bool = False
    history_count: int = 0
    run_present: bool = False
    attempt_failed: bool = False
    binding_current: bool = False
    input_coverage_complete: bool = False
    price_coverage_complete: bool = False
    evidence_consistent: bool = False
    stop_active: bool = False
    all_dimensions_within: bool = False
    approval_required: bool = False
    gate_eligible: bool = False
    dimension_count: int = 0
    forecast_utc_date: str | None = None
    execution_provenance: str | None = None

    def gate_kwargs(self) -> dict:
        return {
            "cost_forecast_scope_resolved": self.scope_resolved,
            "cost_forecast_policy_present": self.policy_present,
            "cost_forecast_policy_valid": self.policy_valid,
            "cost_forecast_budget_present": self.budget_present,
            "cost_forecast_budget_valid": self.budget_valid,
            "cost_forecast_history_count": self.history_count,
            "cost_forecast_run_present": self.run_present,
            "cost_forecast_attempt_failed": self.attempt_failed,
            "cost_forecast_binding_current": self.binding_current,
            "cost_forecast_input_coverage_complete": self.input_coverage_complete,
            "cost_forecast_price_coverage_complete": self.price_coverage_complete,
            "cost_forecast_evidence_consistent": self.evidence_consistent,
            "cost_forecast_stop_active": self.stop_active,
            "cost_forecast_all_dimensions_within": self.all_dimensions_within,
            "cost_forecast_approval_required": self.approval_required,
            "cost_forecast_gate_eligible": self.gate_eligible,
            "cost_forecast_dimension_count": self.dimension_count,
            "cost_forecast_utc_date": self.forecast_utc_date,
            "cost_forecast_execution_provenance": self.execution_provenance,
        }


def _storage_hash(*parts: str) -> str:
    return "sha256:" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _money(value: Decimal) -> str:
    return format(value, ".6f")


def _percent(value: Decimal) -> str:
    return format(value, ".4f")


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _route_hash(route: str) -> str:
    if not isinstance(route, str) or not route.strip() or len(route) > 255:
        raise CostForecastRepositoryError("model_route_invalid")
    return "sha256:" + hashlib.sha256(route.encode("utf-8")).hexdigest()


class CostForecastRepository:
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
            .order_by(CostForecastPolicyVersion.created_at.desc(), CostForecastPolicyVersion.id.desc())
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
        row = CostForecastPolicyVersion(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            policy_contract_version=COST_POLICY_CONTRACT_VERSION,
            policy_contract_hash=COST_POLICY_CONTRACT_HASH,
            policy_digest=digest,
            max_total_model_cost_usd=parsed.max_total_model_cost_usd,
            max_daily_model_cost_usd=parsed.max_daily_model_cost_usd,
            max_cloud_spend_usd=parsed.max_cloud_spend_usd,
            max_ci_minutes_per_day=parsed.max_ci_minutes_per_day,
            require_approval_above_forecast_percentage=parsed.require_approval_above_forecast_percentage,
            cheap_first_for_low_risk=parsed.cheap_first_for_low_risk,
            frontier_for_high_risk=parsed.frontier_for_high_risk,
            use_cached_context_when_possible=parsed.use_cached_context_when_possible,
            stop_conditions=list(parsed.stop_conditions),
            stop_condition_count=4,
            source_provenance=POLICY_PROVENANCE,
            source_label=source_label,
            evidence_ref=evidence_ref,
        )
        self.session.add(row)
        await self.session.flush()
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
        candidate = await ReleaseCandidateRepository(
            self.session, self.context
        ).latest_frozen(project_id)
        if candidate is None:
            return await self._record_refusal(project_id, as_of, "no_current_release_scope", actor)
        pack = await self._latest_pack(candidate.id)
        if pack is None:
            return await self._record_refusal(
                project_id, as_of, "no_complete_reauditable_evidence_core", actor, candidate=candidate
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

    async def _record_refusal(
        self,
        project_id: uuid.UUID,
        as_of: datetime,
        reason: str,
        actor: str,
        candidate: ReleaseCandidate | None = None,
        pack: EvidencePack | None = None,
        policy: CostForecastPolicyVersion | None = None,
        budget: Budget | None = None,
        *,
        detail_code: str | None = None,
    ) -> CostForecastRun:
        failure_digest = _storage_hash(
            str(project_id), reason, detail_code or "none", as_of.date().isoformat()
        )
        row = CostForecastRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_candidate_id=candidate.id if candidate else None,
            evidence_pack_id=pack.id if pack else None,
            policy_version_id=policy.id if policy else None,
            budget_id=budget.id if budget else None,
            as_of=as_of,
            forecast_utc_date=as_of.date(),
            policy_contract_version=COST_POLICY_CONTRACT_VERSION,
            input_contract_version=COST_FORECAST_INPUT_CONTRACT_VERSION,
            forecast_contract_version=COST_FORECAST_CONTRACT_VERSION,
            policy_contract_hash=COST_POLICY_CONTRACT_HASH,
            input_contract_hash=COST_FORECAST_INPUT_CONTRACT_HASH,
            forecast_contract_hash=COST_FORECAST_CONTRACT_HASH,
            core_content_hash=pack.core_content_hash if pack else None,
            budget_total_usd=budget.max_total_cost_usd if budget else None,
            budget_daily_usd=budget.max_daily_cost_usd if budget else None,
            budget_digest=None,
            ledger_digest=None,
            assumption_digest=None,
            price_digest=None,
            result_digest=None,
            input_digest=failure_digest,
            stop_reason="no_budget" if budget is None else "ok",
            outcome="refused",
            reason_code=reason,
            execution_provenance=EXECUTION_PROVENANCE,
            event_ref_count=0,
            input_line_count=0,
            model_line_count=0,
            dimension_count=0,
            all_dimensions_within=False,
            approval_required=False,
            evidence_consistent=False,
            gate_eligible=False,
        )
        self.session.add(row)
        await self.session.flush()
        await audit_record(
            self.session,
            action="cost_forecast.attempt_recorded",
            actor=actor,
            target=str(row.id),
            payload={
                "project_id": str(project_id),
                "run_id": str(row.id),
                "outcome": "refused",
                "reason_code": reason,
                "forecast_utc_date": as_of.date().isoformat(),
                "input_digest": failure_digest,
                "detail_code": detail_code,
            },
        )
        return row

    async def _persist_success(
        self,
        *,
        project_id: uuid.UUID,
        candidate: ReleaseCandidate,
        pack: EvidencePack,
        policy: CostForecastPolicyVersion,
        budget: Budget,
        events: Sequence[CostEvent],
        assumptions: Sequence[ComponentAssumption],
        model_lines: Sequence[ModelForecastLine],
        forecast_ci_minutes_today: int,
        decision,
        stop_reason: str,
        as_of: datetime,
        actor: str,
    ) -> CostForecastRun:
        event_lines = [self._event_line(event) for event in events]
        ledger_digest = _storage_hash(*(line.material_digest for line in event_lines))
        input_rows: list[dict] = []
        ordinal = 1
        for assumption in sorted(assumptions, key=lambda item: item.component):
            parts = (
                "component_remaining",
                assumption.component,
                _money(assumption.remaining_total_usd),
                _money(assumption.remaining_today_usd),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                ASSUMPTION_PROVENANCE,
            )
            input_rows.append(
                dict(
                    ordinal=ordinal,
                    line_kind="component_remaining",
                    component=assumption.component,
                    remaining_total_usd=assumption.remaining_total_usd,
                    remaining_today_usd=assumption.remaining_today_usd,
                    source_provenance=ASSUMPTION_PROVENANCE,
                    line_digest=_storage_hash(*parts),
                )
            )
            ordinal += 1
        for line in sorted(model_lines, key=lambda item: item.model_route_hash):
            parts = (
                "model_price",
                "",
                "",
                "",
                line.model_route_hash,
                str(line.remaining_input_tokens),
                str(line.remaining_output_tokens),
                str(line.remaining_today_input_tokens),
                str(line.remaining_today_output_tokens),
                _money(line.price.input_usd_per_1k),
                _money(line.price.output_usd_per_1k),
                "",
                PRICE_PROVENANCE,
            )
            input_rows.append(
                dict(
                    ordinal=ordinal,
                    line_kind="model_price",
                    model_route_hash=line.model_route_hash,
                    remaining_input_tokens=line.remaining_input_tokens,
                    remaining_output_tokens=line.remaining_output_tokens,
                    remaining_today_input_tokens=line.remaining_today_input_tokens,
                    remaining_today_output_tokens=line.remaining_today_output_tokens,
                    input_rate_usd_per_1k=line.price.input_usd_per_1k,
                    output_rate_usd_per_1k=line.price.output_usd_per_1k,
                    source_provenance=PRICE_PROVENANCE,
                    line_digest=_storage_hash(*parts),
                )
            )
            ordinal += 1
        ci_parts = (
            "ci_minutes_today",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            str(forecast_ci_minutes_today),
            ASSUMPTION_PROVENANCE,
        )
        input_rows.append(
            dict(
                ordinal=ordinal,
                line_kind="ci_minutes_today",
                ci_minutes=forecast_ci_minutes_today,
                source_provenance=ASSUMPTION_PROVENANCE,
                line_digest=_storage_hash(*ci_parts),
            )
        )
        assumption_digest = _storage_hash(
            *(row["line_digest"] for row in input_rows if row["line_kind"] != "model_price")
        )
        price_lines = [row["line_digest"] for row in input_rows if row["line_kind"] == "model_price"]
        price_digest = _storage_hash(*price_lines) if price_lines else _storage_hash("")
        dimension_rows: list[dict] = []
        for index, dimension in enumerate(decision.dimensions, start=1):
            digest = _storage_hash(
                dimension.dimension_code,
                _money(dimension.forecast_value),
                _money(dimension.policy_limit),
                _percent(policy.require_approval_above_forecast_percentage),
            )
            dimension_rows.append(
                dict(
                    ordinal=index,
                    dimension_code=dimension.dimension_code,
                    forecast_value=dimension.forecast_value,
                    policy_limit=dimension.policy_limit,
                    approval_threshold=policy.require_approval_above_forecast_percentage,
                    dimension_digest=digest,
                )
            )
        result_digest = _storage_hash(*(row["dimension_digest"] for row in dimension_rows))
        budget_digest = _storage_hash(
            str(budget.id), _money(budget.max_total_cost_usd), _money(budget.max_daily_cost_usd)
        )
        input_digest = _storage_hash(
            pack.core_content_hash,
            policy.policy_digest,
            budget_digest,
            ledger_digest,
            assumption_digest,
            price_digest,
            result_digest,
            as_of.date().isoformat(),
            stop_reason,
            COST_FORECAST_INPUT_CONTRACT_VERSION,
            COST_FORECAST_CONTRACT_VERSION,
        )
        run = CostForecastRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_candidate_id=candidate.id,
            evidence_pack_id=pack.id,
            policy_version_id=policy.id,
            budget_id=budget.id,
            as_of=as_of,
            forecast_utc_date=as_of.date(),
            policy_contract_version=COST_POLICY_CONTRACT_VERSION,
            input_contract_version=COST_FORECAST_INPUT_CONTRACT_VERSION,
            forecast_contract_version=COST_FORECAST_CONTRACT_VERSION,
            policy_contract_hash=COST_POLICY_CONTRACT_HASH,
            input_contract_hash=COST_FORECAST_INPUT_CONTRACT_HASH,
            forecast_contract_hash=COST_FORECAST_CONTRACT_HASH,
            core_content_hash=pack.core_content_hash,
            budget_total_usd=budget.max_total_cost_usd,
            budget_daily_usd=budget.max_daily_cost_usd,
            budget_digest=budget_digest,
            ledger_digest=ledger_digest,
            assumption_digest=assumption_digest,
            price_digest=price_digest,
            result_digest=result_digest,
            input_digest=input_digest,
            stop_reason=stop_reason,
            outcome="succeeded",
            reason_code=decision.reason_code,
            execution_provenance=EXECUTION_PROVENANCE,
            event_ref_count=len(event_lines),
            input_line_count=len(input_rows),
            model_line_count=len(model_lines),
            dimension_count=6,
            all_dimensions_within=decision.all_dimensions_within,
            approval_required=decision.approval_required,
            evidence_consistent=True,
            gate_eligible=decision.gate_eligible,
        )
        self.session.add(run)
        await self.session.flush()
        for index, (event, line) in enumerate(zip(events, event_lines, strict=True), start=1):
            self.session.add(
                CostForecastLedgerEventRef(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    run_id=run.id,
                    cost_event_id=event.id,
                    ordinal=index,
                    component=event.component,
                    amount_usd=event.amount_usd,
                    occurred_at=event.occurred_at,
                    material_digest=line.material_digest,
                    source_provenance=LEDGER_PROVENANCE,
                )
            )
        for values in input_rows:
            self.session.add(
                CostForecastInputLine(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    run_id=run.id,
                    **values,
                )
            )
        for values in dimension_rows:
            self.session.add(
                CostForecastDimensionResult(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    run_id=run.id,
                    **values,
                )
            )
        await self.session.flush()
        await audit_record(
            self.session,
            action="cost_forecast.attempt_recorded",
            actor=actor,
            target=str(run.id),
            payload={
                "project_id": str(project_id),
                "run_id": str(run.id),
                "release_candidate_id": str(candidate.id),
                "evidence_pack_id": str(pack.id),
                "policy_version_id": str(policy.id),
                "outcome": run.outcome,
                "reason_code": run.reason_code,
                "forecast_utc_date": as_of.date().isoformat(),
                "event_ref_count": run.event_ref_count,
                "input_line_count": run.input_line_count,
                "dimension_count": run.dimension_count,
                "input_digest": input_digest,
                "gate_eligible": run.gate_eligible,
                "execution_provenance": EXECUTION_PROVENANCE,
            },
        )
        return run

    async def coverage_for_project(
        self, project_id: uuid.UUID, *, as_of: datetime | None = None
    ) -> CostForecastCoverage:
        as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidate = await ReleaseCandidateRepository(
            self.session, self.context
        ).latest_frozen(project_id)
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
            await self.session.execute(
                select(CostForecastRun)
                .where(
                    CostForecastRun.tenant_id == self.context.tenant_id,
                    CostForecastRun.project_id == project_id,
                )
                .order_by(CostForecastRun.created_at.desc(), CostForecastRun.id.desc())
                .limit(1)
            )
        ).scalars().first()
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
