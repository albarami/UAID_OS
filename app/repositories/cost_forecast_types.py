"""Shared Slice-51 cost-forecast types and storage formatters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


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
