"""Eleven-class §25.1 matrix builders (Slice 56). Pure; no DB."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from app.cost import StopReason
from app.ops.signals import (
    ALLOWED_SAMPLE_CLASSES,
    CLASS_SEQ,
    LEDGER_CLASSES,
    NOT_OBSERVED_REASONS,
    SIGNAL_CLASSES,
    STRUCTURALLY_UNOBSERVED,
    CallerSample,
    CostObservation,
    OpsSignalError,
    SignalRow,
    canonical_digest,
    compute_counters,
    evaluate_caller_threshold,
    format_utc,
    money_str,
)


def not_observed_row(signal_class: str) -> SignalRow:
    """Successful empty/absent source for a class with no live collector this slice."""
    if signal_class not in NOT_OBSERVED_REASONS:
        raise OpsSignalError(f"{signal_class} is not a default not_observed class")
    return SignalRow(
        seq=CLASS_SEQ[signal_class],
        signal_class=signal_class,
        observation_status="not_observed",
        truth_tier="none",
        source_kind="none",
        source_table="none",
        source_ref=None,
        source_digest=None,
        window_kind="none",
        window_start=None,
        window_end=None,
        reason_code=NOT_OBSERVED_REASONS[signal_class],
        threshold_provenance="none",
        threshold_kind="none",
        threshold_int=None,
        threshold_ratio=None,
        threshold_money=None,
        threshold_money_daily=None,
        metric_kind="none",
        metric_int=None,
        metric_ratio=None,
        metric_money=None,
        metric_money_daily=None,
        threshold_state="not_evaluable",
    )


def job_failures_row(
    *,
    project_id: uuid.UUID,
    as_of: datetime,
    failed_run_ids: Sequence[uuid.UUID],
) -> SignalRow:
    """UAID-runtime distinct failed-run count. Not a customer job SLO."""
    ordered = tuple(sorted(failed_run_ids))
    digest = canonical_digest(
        {
            "as_of": format_utc(as_of),
            "count": len(ordered),
            "failed_run_ids": [str(run_id) for run_id in ordered],
            "project_id": str(project_id),
        }
    )
    return SignalRow(
        seq=CLASS_SEQ["job_failures"],
        signal_class="job_failures",
        observation_status="observed",
        truth_tier="system_derived_ledger",
        source_kind="uaid_runtime",
        source_table="run_steps",
        source_ref=None,
        source_digest=digest,
        window_kind="cumulative_project",
        window_start=None,
        window_end=as_of,
        reason_code="uaid_runtime_failed_run_count",
        threshold_provenance="none",
        threshold_kind="none",
        threshold_int=None,
        threshold_ratio=None,
        threshold_money=None,
        threshold_money_daily=None,
        metric_kind="count",
        metric_int=len(ordered),
        metric_ratio=None,
        metric_money=None,
        metric_money_daily=None,
        threshold_state="not_evaluable",
    )


def cost_anomalies_row(
    *, project_id: uuid.UUID, as_of: datetime, cost: CostObservation
) -> SignalRow:
    """Ledger-derived cost class. Missing budget is observed + not_evaluable, not a breach."""
    total_cap = None if cost.budget is None else cost.budget.max_total_cost_usd
    daily_cap = None if cost.budget is None else cost.budget.max_daily_cost_usd
    digest = canonical_digest(
        {
            "as_of": format_utc(as_of),
            "daily_cap": money_str(daily_cap),
            "daily_spent": str(cost.daily_spent),
            "project_id": str(project_id),
            "reason": None if cost.decision.reason is None else cost.decision.reason.value,
            "stop": cost.decision.stop,
            "total_cap": money_str(total_cap),
            "total_spent": str(cost.total_spent),
            "utc_midnight": format_utc(cost.utc_midnight),
        }
    )
    if cost.budget is None:
        threshold_kind, provenance, state, reason = (
            "none",
            "none",
            "not_evaluable",
            "cost_no_budget",
        )
        threshold_money = threshold_money_daily = None
    elif cost.decision.reason is StopReason.BUDGET_EXCEEDED:
        threshold_kind, provenance, state, reason = (
            "cost_stop",
            "recorded_budget",
            "breached",
            "cost_budget_exceeded",
        )
        threshold_money, threshold_money_daily = total_cap, daily_cap
    elif cost.decision.reason is StopReason.DAILY_BUDGET_EXCEEDED:
        threshold_kind, provenance, state, reason = (
            "cost_stop",
            "recorded_budget",
            "breached",
            "cost_daily_budget_exceeded",
        )
        threshold_money, threshold_money_daily = total_cap, daily_cap
    else:
        threshold_kind, provenance, state, reason = (
            "cost_stop",
            "recorded_budget",
            "ok",
            "cost_within_budget",
        )
        threshold_money, threshold_money_daily = total_cap, daily_cap
    return SignalRow(
        seq=CLASS_SEQ["cost_anomalies"],
        signal_class="cost_anomalies",
        observation_status="observed",
        truth_tier="system_derived_ledger",
        source_kind="cost_ledger",
        source_table="cost_events_and_budgets",
        source_ref=None,
        source_digest=digest,
        window_kind="cumulative_project",
        window_start=None,
        window_end=as_of,
        reason_code=reason,
        threshold_provenance=provenance,
        threshold_kind=threshold_kind,
        threshold_int=None,
        threshold_ratio=None,
        threshold_money=threshold_money,
        threshold_money_daily=threshold_money_daily,
        metric_kind="money",
        metric_int=None,
        metric_ratio=None,
        metric_money=cost.total_spent,
        metric_money_daily=cost.daily_spent,
        threshold_state=state,
    )


def merge_samples(
    rows: Sequence[SignalRow],
    samples: Sequence[CallerSample],
    as_of: datetime,
) -> tuple[SignalRow, ...]:
    """Overlay accepted samples onto not_observed classes only."""
    by_class = {row.signal_class: row for row in rows}
    for sample in samples:
        if sample.signal_class not in ALLOWED_SAMPLE_CLASSES:
            raise OpsSignalError(f"sample class {sample.signal_class} is not allowed")
        if sample.signal_class in STRUCTURALLY_UNOBSERVED or sample.signal_class in LEDGER_CLASSES:
            raise OpsSignalError(f"sample class {sample.signal_class} is not allowed")
        current = by_class[sample.signal_class]
        if current.observation_status != "not_observed":
            raise OpsSignalError(f"sample cannot overwrite {sample.signal_class}")
        by_class[sample.signal_class] = evaluate_caller_threshold(sample, as_of)
    return tuple(by_class[name] for name in SIGNAL_CLASSES)


def build_assessment(
    *,
    project_id: uuid.UUID,
    as_of: datetime,
    failed_run_ids: Sequence[uuid.UUID],
    cost: CostObservation,
    samples: Sequence[CallerSample] = (),
) -> tuple[SignalRow, ...]:
    """Build the eleven-class assessment. Samples cannot overwrite ledger or locked classes."""
    by_class: dict[str, SignalRow] = {name: not_observed_row(name) for name in NOT_OBSERVED_REASONS}
    by_class["job_failures"] = job_failures_row(
        project_id=project_id, as_of=as_of, failed_run_ids=failed_run_ids
    )
    by_class["cost_anomalies"] = cost_anomalies_row(project_id=project_id, as_of=as_of, cost=cost)
    rows = merge_samples(tuple(by_class[name] for name in SIGNAL_CLASSES), samples, as_of)
    compute_counters(rows)
    return rows
