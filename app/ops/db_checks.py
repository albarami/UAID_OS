"""Postgres CHECK expressions for Slice-56 child rows.

Shared by the ORM and migration ``0055`` so the class/source/metric/threshold
matrix cannot drift. Presence of a passing CHECK is not monitoring adequacy.
"""

from __future__ import annotations

METRIC_SHAPE_SQL = (
    "(metric_kind='none' AND metric_int IS NULL AND metric_ratio IS NULL "
    "AND metric_money IS NULL) OR "
    "(metric_kind='count' AND metric_int IS NOT NULL AND metric_ratio IS NULL "
    "AND metric_money IS NULL) OR "
    "(metric_kind='milliseconds' AND metric_int IS NOT NULL AND metric_ratio IS NULL "
    "AND metric_money IS NULL) OR "
    "(metric_kind='ratio' AND metric_ratio IS NOT NULL AND metric_int IS NULL "
    "AND metric_money IS NULL) OR "
    "(metric_kind='money' AND metric_money IS NOT NULL AND metric_int IS NULL "
    "AND metric_ratio IS NULL)"
)

THRESHOLD_SHAPE_SQL = (
    "(threshold_kind='none' AND threshold_int IS NULL AND threshold_ratio IS NULL "
    "AND threshold_money IS NULL AND threshold_money_daily IS NULL) OR "
    "(threshold_kind='caller_count' AND threshold_int IS NOT NULL "
    "AND threshold_ratio IS NULL AND threshold_money IS NULL "
    "AND threshold_money_daily IS NULL) OR "
    "(threshold_kind='caller_ms' AND threshold_int IS NOT NULL "
    "AND threshold_ratio IS NULL AND threshold_money IS NULL "
    "AND threshold_money_daily IS NULL) OR "
    "(threshold_kind='caller_ratio' AND threshold_ratio IS NOT NULL "
    "AND threshold_int IS NULL AND threshold_money IS NULL "
    "AND threshold_money_daily IS NULL) OR "
    "(threshold_kind='cost_stop' AND threshold_money IS NOT NULL "
    "AND threshold_int IS NULL AND threshold_ratio IS NULL)"
)

JOB_FAILURES_SHAPE_SQL = (
    "(signal_class<>'job_failures') OR ("
    "source_kind='uaid_runtime' AND source_table='run_steps' "
    "AND metric_kind='count' AND reason_code='uaid_runtime_failed_run_count' "
    "AND threshold_kind='none' AND threshold_provenance='none' "
    "AND threshold_state='not_evaluable')"
)

COST_ANOMALIES_SHAPE_SQL = (
    "(signal_class<>'cost_anomalies') OR ("
    "source_kind='cost_ledger' AND source_table='cost_events_and_budgets' "
    "AND metric_kind='money' AND ("
    "(reason_code='cost_no_budget' AND threshold_kind='none' "
    "AND threshold_provenance='none' AND threshold_state='not_evaluable' "
    "AND threshold_money IS NULL AND threshold_money_daily IS NULL) OR "
    "(reason_code='cost_budget_exceeded' AND threshold_kind='cost_stop' "
    "AND threshold_provenance='recorded_budget' AND threshold_state='breached' "
    "AND threshold_money IS NOT NULL AND metric_money >= threshold_money) OR "
    "(reason_code='cost_daily_budget_exceeded' AND threshold_kind='cost_stop' "
    "AND threshold_provenance='recorded_budget' AND threshold_state='breached' "
    "AND threshold_money IS NOT NULL AND threshold_money_daily IS NOT NULL "
    "AND metric_money < threshold_money "
    "AND metric_money_daily >= threshold_money_daily) OR "
    "(reason_code='cost_within_budget' AND threshold_kind='cost_stop' "
    "AND threshold_provenance='recorded_budget' AND threshold_state='ok' "
    "AND threshold_money IS NOT NULL AND metric_money < threshold_money AND "
    "(threshold_money_daily IS NULL OR metric_money_daily < threshold_money_daily))"
    "))"
)

CALLER_RATIO_SHAPE_SQL = (
    "(signal_class NOT IN ('error_rates','model_output_drift')) "
    "OR observation_status='not_observed' OR ("
    "observation_status='caller_supplied_unverified' AND "
    "metric_kind='ratio' AND threshold_kind='caller_ratio' "
    "AND metric_ratio IS NOT NULL AND threshold_ratio IS NOT NULL AND "
    "((threshold_state='ok' AND metric_ratio <= threshold_ratio) OR "
    "(threshold_state='breached' AND metric_ratio > threshold_ratio)))"
)

CALLER_MS_SHAPE_SQL = (
    "(signal_class<>'latency') OR observation_status='not_observed' OR ("
    "observation_status='caller_supplied_unverified' AND "
    "metric_kind='milliseconds' AND threshold_kind='caller_ms' "
    "AND metric_int IS NOT NULL AND threshold_int IS NOT NULL AND "
    "((threshold_state='ok' AND metric_int <= threshold_int) OR "
    "(threshold_state='breached' AND metric_int > threshold_int)))"
)

CALLER_COUNT_SHAPE_SQL = (
    "(signal_class NOT IN ('user_journey_failures','data_quality_issues')) "
    "OR observation_status='not_observed' OR ("
    "observation_status='caller_supplied_unverified' AND "
    "metric_kind='count' AND threshold_kind='caller_count' "
    "AND metric_int IS NOT NULL AND threshold_int IS NOT NULL AND "
    "((threshold_state='ok' AND metric_int <= threshold_int) OR "
    "(threshold_state='breached' AND metric_int > threshold_int)))"
)

SAMPLEABLE_NOT_LEDGER_SQL = (
    "(signal_class NOT IN ('error_rates','latency','user_journey_failures',"
    "'data_quality_issues','model_output_drift')) OR "
    "observation_status IN ('not_observed','caller_supplied_unverified')"
)

NOT_OBSERVED_REASON_SQL = (
    "(observation_status<>'not_observed') OR ("
    "(signal_class='uptime' AND reason_code='no_uptime_source') OR "
    "(signal_class='error_rates' AND reason_code='no_error_rate_source') OR "
    "(signal_class='latency' AND reason_code='no_latency_source') OR "
    "(signal_class='security_alerts' AND reason_code='no_post_launch_security_alert_source') OR "
    "(signal_class='user_journey_failures' AND reason_code='no_journey_failure_source') OR "
    "(signal_class='data_quality_issues' AND reason_code='no_data_quality_source') OR "
    "(signal_class='model_output_drift' AND reason_code='no_model_drift_source') OR "
    "(signal_class='support_tickets' AND reason_code='no_support_ticket_source') OR "
    "(signal_class='incident_reports' AND reason_code='no_incident_store'))"
)

THRESHOLD_MONEY_NONNEG_SQL = (
    "threshold_money IS NULL OR (threshold_money >= 0 "
    "AND threshold_money < 'Infinity'::numeric)"
)
THRESHOLD_MONEY_DAILY_NONNEG_SQL = (
    "threshold_money_daily IS NULL OR (threshold_money_daily >= 0 "
    "AND threshold_money_daily < 'Infinity'::numeric)"
)
METRIC_RATIO_BOUNDS_SQL = "metric_ratio IS NULL OR metric_ratio BETWEEN 0 AND 1"
THRESHOLD_RATIO_BOUNDS_SQL = "threshold_ratio IS NULL OR threshold_ratio BETWEEN 0 AND 1"
METRIC_INT_BOUNDS_SQL = "metric_int IS NULL OR metric_int BETWEEN 0 AND 2147483647"
THRESHOLD_INT_BOUNDS_SQL = "threshold_int IS NULL OR threshold_int BETWEEN 0 AND 2147483647"
METRIC_MONEY_NONNEG_SQL = (
    "metric_money IS NULL OR (metric_money >= 0 AND metric_money < 'Infinity'::numeric)"
)
METRIC_MONEY_DAILY_NONNEG_SQL = (
    "metric_money_daily IS NULL OR (metric_money_daily >= 0 "
    "AND metric_money_daily < 'Infinity'::numeric)"
)

CHILD_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("metric_shape", METRIC_SHAPE_SQL),
    ("threshold_shape", THRESHOLD_SHAPE_SQL),
    ("job_failures_shape", JOB_FAILURES_SHAPE_SQL),
    ("cost_anomalies_shape", COST_ANOMALIES_SHAPE_SQL),
    ("caller_ratio_shape", CALLER_RATIO_SHAPE_SQL),
    ("caller_ms_shape", CALLER_MS_SHAPE_SQL),
    ("caller_count_shape", CALLER_COUNT_SHAPE_SQL),
    ("sampleable_not_ledger", SAMPLEABLE_NOT_LEDGER_SQL),
    ("not_observed_reason", NOT_OBSERVED_REASON_SQL),
    ("metric_ratio_bounds", METRIC_RATIO_BOUNDS_SQL),
    ("threshold_ratio_bounds", THRESHOLD_RATIO_BOUNDS_SQL),
    ("metric_int_bounds", METRIC_INT_BOUNDS_SQL),
    ("threshold_int_bounds", THRESHOLD_INT_BOUNDS_SQL),
    ("metric_money_nonneg", METRIC_MONEY_NONNEG_SQL),
    ("metric_money_daily_nonneg", METRIC_MONEY_DAILY_NONNEG_SQL),
    ("threshold_money_nonneg", THRESHOLD_MONEY_NONNEG_SQL),
    ("threshold_money_daily_nonneg", THRESHOLD_MONEY_DAILY_NONNEG_SQL),
)
