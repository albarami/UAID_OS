"""Deterministic Slice-51 cost-forecast contracts — pure, no DB or I/O.

A forecast is a system-derived projection over exact recorded and declared inputs. It is not
future truth, a provider quote, or verified finance/procurement authority. Persistence and A5
selection live in ``app.repositories.cost_forecasts``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Sequence

from app.cost import COST_COMPONENTS, InvalidAmount, to_decimal
from app.llm.pricing import ModelPrice

COST_POLICY_CONTRACT_VERSION = "slice51.cost_policy.v1"
COST_FORECAST_INPUT_CONTRACT_VERSION = "slice51.cost_forecast_input.v1"
COST_FORECAST_CONTRACT_VERSION = "slice51.cost_forecast.v1"
COST_POLICY_CONTRACT_HASH = "sha256:067a1078f436686629e777384c70734eb0c7197554c8b637ea1784587ef2e7d5"
COST_FORECAST_INPUT_CONTRACT_HASH = (
    "sha256:421c35ca34b48aebdaa404404a60ab4b18b9de81608ee754798f6719613aca6d"
)
COST_FORECAST_CONTRACT_HASH = "sha256:b853aecc7bfd79c5e061a22651285b0c3f1eaa56412c5cb9bddca314f040d705"

POLICY_PROVENANCE = "caller_supplied_unverified_structured_cost_policy"
ASSUMPTION_PROVENANCE = "reported_cost_forecast_assumption"
PRICE_PROVENANCE = "operator_configured_price_card_snapshot"
LEDGER_PROVENANCE = "db_bound_incurred_cost_events"
EXECUTION_PROVENANCE = "system_derived_cost_forecast"

DIMENSION_CODES = (
    "all_cost_total_usd",
    "all_cost_daily_usd",
    "model_cost_total_usd",
    "model_cost_daily_usd",
    "cloud_spend_total_usd",
    "ci_minutes_daily",
)

_POLICY_FIELDS = {
    "max_total_model_cost_usd",
    "max_daily_model_cost_usd",
    "max_cloud_spend_usd",
    "max_ci_minutes_per_day",
    "require_approval_above_forecast_percentage",
    "model_routing",
    "stop_conditions",
}
_ROUTING_FIELDS = {
    "cheap_first_for_low_risk",
    "frontier_for_high_risk",
    "use_cached_context_when_possible",
}
_STOP_CONDITIONS = (
    "budget_exceeded",
    "repeated_failure_without_new_strategy",
    "tool_loop_detected",
    "model_provider_outage_extended",
)
_STOP_REASONS = {"ok", "no_budget", "budget_exceeded", "daily_budget_exceeded"}
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MONEY_MAX = Decimal("999999999999.999999")
_MONEY_QUANTUM = Decimal("0.000001")
_PERCENT_QUANTUM = Decimal("0.0001")
_THOUSAND = Decimal(1000)
_INTEGER_MAX = 2_147_483_647
_MAX_LEDGER_LINES = 50_000
_MAX_MODEL_LINES = 128


class CostForecastError(ValueError):
    """A forecast input cannot support the ruled deterministic contract."""


def _decimal(value, field_name: str, *, positive: bool = False) -> Decimal:
    try:
        parsed = to_decimal(value, field_name)
    except InvalidAmount as exc:
        raise CostForecastError(str(exc)) from exc
    if parsed > _MONEY_MAX:
        raise CostForecastError(f"{field_name}: exceeds NUMERIC(18,6)")
    if positive and parsed <= 0:
        raise CostForecastError(f"{field_name}: must be positive")
    return parsed


def _bounded_int(value, field_name: str, *, maximum: int = _INTEGER_MAX) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CostForecastError(f"{field_name}: must be an integer")
    if value < 0 or value > maximum:
        raise CostForecastError(f"{field_name}: outside permitted range")
    return value


def _json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def canonical_digest(value) -> str:
    encoded = json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class StructuredCostPolicy:
    max_total_model_cost_usd: Decimal
    max_daily_model_cost_usd: Decimal
    max_cloud_spend_usd: Decimal
    max_ci_minutes_per_day: Decimal
    require_approval_above_forecast_percentage: Decimal
    cheap_first_for_low_risk: bool
    frontier_for_high_risk: bool
    use_cached_context_when_possible: bool
    stop_conditions: tuple[str, ...]
    policy_digest: str
    source_provenance: str = POLICY_PROVENANCE
    contract_version: str = COST_POLICY_CONTRACT_VERSION


@dataclass(frozen=True)
class ComponentAssumption:
    component: str
    remaining_total_usd: Decimal
    remaining_today_usd: Decimal
    source_provenance: str = ASSUMPTION_PROVENANCE


@dataclass(frozen=True)
class LedgerCostLine:
    event_id: str
    component: str
    amount_usd: Decimal
    occurred_at: datetime
    material_digest: str
    source_provenance: str = LEDGER_PROVENANCE


@dataclass(frozen=True)
class ModelForecastLine:
    model_route_hash: str
    remaining_input_tokens: int
    remaining_output_tokens: int
    remaining_today_input_tokens: int
    remaining_today_output_tokens: int
    price: ModelPrice
    source_provenance: str = PRICE_PROVENANCE


@dataclass(frozen=True)
class ForecastInput:
    policy: StructuredCostPolicy
    budget_total_usd: Decimal
    budget_daily_usd: Decimal
    ledger_lines: Sequence[LedgerCostLine]
    assumptions: Sequence[ComponentAssumption]
    model_lines: Sequence[ModelForecastLine]
    forecast_ci_minutes_today: int
    stop_reason: str
    as_of: datetime


@dataclass(frozen=True)
class ForecastDimensionResult:
    dimension_code: str
    forecast_value: Decimal
    policy_limit: Decimal
    utilization_percent: Decimal
    within_limit: bool
    approval_triggered: bool
    result_code: str


@dataclass(frozen=True)
class CostForecastDecision:
    outcome: str
    reason_code: str
    dimensions: tuple[ForecastDimensionResult, ...]
    all_dimensions_within: bool
    approval_required: bool
    evidence_consistent: bool
    gate_eligible: bool
    policy_digest: str
    ledger_digest: str
    assumption_digest: str
    price_digest: str
    result_digest: str
    input_digest: str
    execution_provenance: str = EXECUTION_PROVENANCE
    contract_version: str = COST_FORECAST_CONTRACT_VERSION
    input_contract_version: str = COST_FORECAST_INPUT_CONTRACT_VERSION


def parse_structured_policy(payload: Mapping) -> StructuredCostPolicy:
    if not isinstance(payload, Mapping) or set(payload) != {"cost_and_resource_policy"}:
        raise CostForecastError("policy root must be exactly cost_and_resource_policy")
    raw = payload["cost_and_resource_policy"]
    if not isinstance(raw, Mapping) or set(raw) != _POLICY_FIELDS:
        raise CostForecastError("policy fields must match canonical file-21 exactly")
    routing = raw["model_routing"]
    if not isinstance(routing, Mapping) or set(routing) != _ROUTING_FIELDS:
        raise CostForecastError("model_routing fields must match canonical file-21 exactly")
    if any(type(routing[key]) is not bool for key in _ROUTING_FIELDS):
        raise CostForecastError("model_routing values must be booleans")
    stops = raw["stop_conditions"]
    if not isinstance(stops, list) or tuple(stops) != _STOP_CONDITIONS:
        raise CostForecastError("stop_conditions must match canonical file-21 exactly")

    model_total = _decimal(raw["max_total_model_cost_usd"], "max_total_model_cost_usd", positive=True)
    model_daily = _decimal(raw["max_daily_model_cost_usd"], "max_daily_model_cost_usd", positive=True)
    cloud = _decimal(raw["max_cloud_spend_usd"], "max_cloud_spend_usd", positive=True)
    ci_minutes = _decimal(raw["max_ci_minutes_per_day"], "max_ci_minutes_per_day", positive=True)
    approval = _decimal(
        raw["require_approval_above_forecast_percentage"],
        "require_approval_above_forecast_percentage",
    )
    if approval > 100:
        raise CostForecastError("require_approval_above_forecast_percentage: must be <= 100")

    material = {
        "max_total_model_cost_usd": model_total,
        "max_daily_model_cost_usd": model_daily,
        "max_cloud_spend_usd": cloud,
        "max_ci_minutes_per_day": ci_minutes,
        "require_approval_above_forecast_percentage": approval,
        "model_routing": dict(routing),
        "stop_conditions": stops,
        "contract_version": COST_POLICY_CONTRACT_VERSION,
    }
    return StructuredCostPolicy(
        max_total_model_cost_usd=model_total,
        max_daily_model_cost_usd=model_daily,
        max_cloud_spend_usd=cloud,
        max_ci_minutes_per_day=ci_minutes,
        require_approval_above_forecast_percentage=approval,
        cheap_first_for_low_risk=routing["cheap_first_for_low_risk"],
        frontier_for_high_risk=routing["frontier_for_high_risk"],
        use_cached_context_when_possible=routing["use_cached_context_when_possible"],
        stop_conditions=tuple(stops),
        policy_digest=canonical_digest(material),
    )


def _validate_assumptions(lines: Sequence[ComponentAssumption]) -> dict[str, ComponentAssumption]:
    if len(lines) != len(COST_COMPONENTS):
        raise CostForecastError("every cost component must appear exactly once")
    by_component: dict[str, ComponentAssumption] = {}
    for line in lines:
        if line.component not in COST_COMPONENTS or line.component in by_component:
            raise CostForecastError("every cost component must appear exactly once")
        if line.source_provenance != ASSUMPTION_PROVENANCE:
            raise CostForecastError("assumption provenance is not permitted")
        total = _decimal(line.remaining_total_usd, f"{line.component}.remaining_total_usd")
        today = _decimal(line.remaining_today_usd, f"{line.component}.remaining_today_usd")
        if today > total:
            raise CostForecastError("remaining_today_usd cannot exceed remaining_total_usd")
        if line.component == "model_inference" and (total != 0 or today != 0):
            raise CostForecastError("model_inference remaining USD must be derived from token prices")
        by_component[line.component] = ComponentAssumption(line.component, total, today)
    return by_component


def _validate_ledger(
    lines: Sequence[LedgerCostLine], as_of: datetime
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    if not lines:
        raise CostForecastError("cost history is required")
    if len(lines) > _MAX_LEDGER_LINES:
        raise CostForecastError("ledger event inventory exceeds 50000")
    seen: set[str] = set()
    totals = {component: Decimal(0) for component in COST_COMPONENTS}
    today = {component: Decimal(0) for component in COST_COMPONENTS}
    for line in lines:
        if line.event_id in seen:
            raise CostForecastError("duplicate ledger event")
        seen.add(line.event_id)
        if line.component not in COST_COMPONENTS:
            raise CostForecastError("unknown ledger component")
        if line.source_provenance != LEDGER_PROVENANCE or not _SHA256.fullmatch(
            line.material_digest
        ):
            raise CostForecastError("ledger provenance or digest is invalid")
        if line.occurred_at.tzinfo is None:
            raise CostForecastError("ledger occurred_at must be timezone-aware")
        occurred = line.occurred_at.astimezone(timezone.utc)
        if occurred > as_of:
            raise CostForecastError("future-dated incurred event")
        amount = _decimal(line.amount_usd, "ledger amount")
        totals[line.component] = _decimal(
            totals[line.component] + amount, f"{line.component}.incurred_total"
        )
        if occurred.date() == as_of.date():
            today[line.component] = _decimal(
                today[line.component] + amount, f"{line.component}.incurred_today"
            )
    return totals, today


def _model_remaining(lines: Sequence[ModelForecastLine]) -> tuple[Decimal, Decimal, list[dict]]:
    if len(lines) > _MAX_MODEL_LINES:
        raise CostForecastError("model price inventory exceeds 128")
    total = Decimal(0)
    today = Decimal(0)
    material: list[dict] = []
    seen: set[str] = set()
    for line in lines:
        if not _SHA256.fullmatch(line.model_route_hash) or line.model_route_hash in seen:
            raise CostForecastError("model route hash must be unique canonical sha256")
        seen.add(line.model_route_hash)
        quantities = (
            _bounded_int(line.remaining_input_tokens, "remaining_input_tokens"),
            _bounded_int(line.remaining_output_tokens, "remaining_output_tokens"),
            _bounded_int(line.remaining_today_input_tokens, "remaining_today_input_tokens"),
            _bounded_int(line.remaining_today_output_tokens, "remaining_today_output_tokens"),
        )
        if quantities[2] > quantities[0] or quantities[3] > quantities[1]:
            raise CostForecastError("today model tokens cannot exceed total model tokens")
        input_rate = _decimal(line.price.input_usd_per_1k, "input price")
        output_rate = _decimal(line.price.output_usd_per_1k, "output price")
        if any(quantities) and input_rate == 0 and output_rate == 0:
            raise CostForecastError("nonzero planned tokens require a nonzero price")
        line_total = ((
            Decimal(quantities[0]) * input_rate + Decimal(quantities[1]) * output_rate
        ) / _THOUSAND).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        line_today = ((
            Decimal(quantities[2]) * input_rate + Decimal(quantities[3]) * output_rate
        ) / _THOUSAND).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        total = _decimal(total + line_total, "model remaining total")
        today = _decimal(today + line_today, "model remaining today")
        material.append(
            {
                "model_route_hash": line.model_route_hash,
                "tokens": quantities,
                "input_rate": input_rate,
                "output_rate": output_rate,
                "source_provenance": PRICE_PROVENANCE,
            }
        )
    return total, today, material


def derive_forecast(inputs: ForecastInput) -> CostForecastDecision:
    if inputs.as_of.tzinfo is None:
        raise CostForecastError("as_of must be timezone-aware")
    as_of = inputs.as_of.astimezone(timezone.utc)
    budget_total = _decimal(inputs.budget_total_usd, "budget_total_usd", positive=True)
    budget_daily = _decimal(inputs.budget_daily_usd, "budget_daily_usd", positive=True)
    if inputs.stop_reason not in _STOP_REASONS:
        raise CostForecastError("unknown STOP reason")
    ci_minutes = _bounded_int(inputs.forecast_ci_minutes_today, "forecast_ci_minutes_today")
    assumptions = _validate_assumptions(inputs.assumptions)
    incurred_total, incurred_today = _validate_ledger(inputs.ledger_lines, as_of)
    model_remaining, model_remaining_today, model_material = _model_remaining(inputs.model_lines)

    forecast_total: dict[str, Decimal] = {}
    forecast_today: dict[str, Decimal] = {}
    for component in COST_COMPONENTS:
        extra_total = assumptions[component].remaining_total_usd
        extra_today = assumptions[component].remaining_today_usd
        if component == "model_inference":
            extra_total = model_remaining
            extra_today = model_remaining_today
        forecast_total[component] = _decimal(
            incurred_total[component] + extra_total, f"{component}.forecast_total"
        )
        forecast_today[component] = _decimal(
            incurred_today[component] + extra_today, f"{component}.forecast_today"
        )

    values_limits = (
        ("all_cost_total_usd", sum(forecast_total.values(), Decimal(0)), budget_total),
        ("all_cost_daily_usd", sum(forecast_today.values(), Decimal(0)), budget_daily),
        (
            "model_cost_total_usd",
            forecast_total["model_inference"],
            inputs.policy.max_total_model_cost_usd,
        ),
        (
            "model_cost_daily_usd",
            forecast_today["model_inference"],
            inputs.policy.max_daily_model_cost_usd,
        ),
        (
            "cloud_spend_total_usd",
            forecast_total["cloud_runtime"],
            inputs.policy.max_cloud_spend_usd,
        ),
        ("ci_minutes_daily", Decimal(ci_minutes), inputs.policy.max_ci_minutes_per_day),
    )
    dimensions: list[ForecastDimensionResult] = []
    approval_threshold = inputs.policy.require_approval_above_forecast_percentage
    for code, value, limit in values_limits:
        value = _decimal(value, f"{code}.forecast_value")
        limit = _decimal(limit, f"{code}.policy_limit", positive=True)
        utilization = ((value / limit) * Decimal(100)).quantize(
            _PERCENT_QUANTUM, rounding=ROUND_HALF_UP
        )
        within = value < limit
        approval = utilization > approval_threshold
        result = (
            "limit_reached_or_exceeded"
            if not within
            else "approval_required"
            if approval
            else "within_limit"
        )
        dimensions.append(
            ForecastDimensionResult(code, value, limit, utilization, within, approval, result)
        )

    all_within = all(row.within_limit for row in dimensions)
    approval_required = any(row.approval_triggered for row in dimensions)
    if inputs.stop_reason != "ok":
        reason = "cost_stop_active"
    elif not all_within:
        reason = "limit_reached_or_exceeded"
    elif approval_required:
        reason = "approval_required"
    else:
        reason = "within_recorded_policy"

    ledger_material = [
        {
            "event_id": line.event_id,
            "component": line.component,
            "amount_usd": line.amount_usd,
            "occurred_at": line.occurred_at,
            "material_digest": line.material_digest,
        }
        for line in sorted(inputs.ledger_lines, key=lambda item: item.event_id)
    ]
    assumption_material = [
        {
            "component": component,
            "remaining_total_usd": assumptions[component].remaining_total_usd,
            "remaining_today_usd": assumptions[component].remaining_today_usd,
        }
        for component in sorted(COST_COMPONENTS)
    ]
    result_material = [
        {
            "dimension_code": row.dimension_code,
            "forecast_value": row.forecast_value,
            "policy_limit": row.policy_limit,
            "utilization_percent": row.utilization_percent,
            "within_limit": row.within_limit,
            "approval_triggered": row.approval_triggered,
            "result_code": row.result_code,
        }
        for row in dimensions
    ]
    ledger_digest = canonical_digest(ledger_material)
    assumption_digest = canonical_digest(assumption_material)
    price_digest = canonical_digest(model_material)
    result_digest = canonical_digest(result_material)
    input_digest = canonical_digest(
        {
            "as_of": as_of,
            "forecast_utc_date": as_of.date().isoformat(),
            "policy_digest": inputs.policy.policy_digest,
            "budget_total_usd": budget_total,
            "budget_daily_usd": budget_daily,
            "ledger_digest": ledger_digest,
            "assumption_digest": assumption_digest,
            "price_digest": price_digest,
            "ci_minutes": ci_minutes,
            "stop_reason": inputs.stop_reason,
            "input_contract_version": COST_FORECAST_INPUT_CONTRACT_VERSION,
        }
    )
    return CostForecastDecision(
        outcome="succeeded",
        reason_code=reason,
        dimensions=tuple(dimensions),
        all_dimensions_within=all_within,
        approval_required=approval_required,
        evidence_consistent=True,
        gate_eligible=reason == "within_recorded_policy",
        policy_digest=inputs.policy.policy_digest,
        ledger_digest=ledger_digest,
        assumption_digest=assumption_digest,
        price_digest=price_digest,
        result_digest=result_digest,
        input_digest=input_digest,
    )
