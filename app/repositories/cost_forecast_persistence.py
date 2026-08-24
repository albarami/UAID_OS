"""Persistence mixin for Slice-51 cost-forecast runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
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
    PRICE_PROVENANCE,
    ComponentAssumption,
    ModelForecastLine,
)
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
from app.repositories.cost_forecast_types import _money, _percent, _storage_hash
from app.tenancy import TenantContext


class _CostForecastPersistenceMixin:
    session: AsyncSession
    context: TenantContext

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
        price_lines = [
            row["line_digest"] for row in input_rows if row["line_kind"] == "model_price"
        ]
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
