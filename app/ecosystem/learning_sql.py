"""Source queries and expected-count SQL for Slice 62 learning.

The seven query strings are the single allowlist. Each string is a substring
of ``expected_counts_function_body``.
"""

from __future__ import annotations

from app.ecosystem.learning import (
    CONNECTOR_BUCKET_KEYS,
    COST_KEYS,
    EVAL_KEYS,
    FAILURE_KEYS,
    FINDING_TYPES,
    FORBIDDEN_SOURCE_COLUMNS,
    LATENCY_KEYS,
    REVIEWER_STATUSES,
    TOOL_BUCKET_KEYS,
)

FORBIDDEN_COLUMNS: tuple[str, ...] = FORBIDDEN_SOURCE_COLUMNS

_DENIED = (
    "'denied_unknown_tool','denied_invalid_params','denied_not_allowlisted',"
    "'denied_policy','denied_unknown_agent','denied_unqualified_agent'"
)


def _values(keys: tuple[str, ...]) -> str:
    return ", ".join("('" + key.replace("'", "''") + "')" for key in keys)


def _eval_sql() -> str:
    return (
        "SELECT 'aggregate_eval_failure_rates'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "CASE WHEN COALESCE(s.n_events, 0) = 0 THEN NULL ELSE s.metric_sum END "
        "AS metric_sum, 'count'::text AS metric_unit "
        f"FROM (VALUES {_values(EVAL_KEYS)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT archetype AS bucket_key, COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants, "
        "COUNT(*) FILTER (WHERE verdict = 'failed')::numeric AS metric_sum "
        "FROM public.qualification_runs GROUP BY archetype"
        ") s ON s.bucket_key = u.bucket_key"
    )


def _reviewer_sql() -> str:
    return (
        "SELECT 'aggregate_reviewer_miss_patterns'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "NULL::numeric AS metric_sum, 'count'::text AS metric_unit "
        f"FROM (VALUES {_values(REVIEWER_STATUSES)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT quality_status AS bucket_key, COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants "
        "FROM public.reviewer_quality_records "
        "WHERE quality_status IN "
        "('challenge_qualified','threshold_breached','inconclusive') "
        "GROUP BY quality_status"
        ") s ON s.bucket_key = u.bucket_key"
    )


def _cost_latency_sql() -> str:
    cost = (
        "SELECT 'anonymized_cost_and_latency_benchmarks'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "CASE WHEN COALESCE(s.n_events, 0) = 0 THEN NULL ELSE s.metric_sum END "
        "AS metric_sum, 'usd'::text AS metric_unit "
        f"FROM (VALUES {_values(COST_KEYS)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT 'cost:' || component AS bucket_key, COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants, "
        "SUM(amount_usd) AS metric_sum FROM public.cost_events GROUP BY component"
        ") s ON s.bucket_key = u.bucket_key"
    )
    latency = (
        "SELECT 'anonymized_cost_and_latency_benchmarks'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "CASE WHEN COALESCE(s.n_events, 0) = 0 THEN NULL ELSE s.metric_sum END "
        "AS metric_sum, 'milliseconds'::text AS metric_unit "
        f"FROM (VALUES {_values(LATENCY_KEYS)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT 'latency:qa_harness:' || f.challenge_family AS bucket_key, "
        "COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT r.project_id)::int AS n_projects, "
        "COUNT(DISTINCT r.tenant_id)::int AS n_tenants, "
        "SUM(r.latency_ms)::numeric AS metric_sum "
        "FROM public.reviewer_quality_case_results r "
        "JOIN public.reviewer_qa_fixture_cases f ON f.id = r.fixture_case_id "
        "WHERE r.execution_status = 'succeeded' "
        "GROUP BY f.challenge_family"
        ") s ON s.bucket_key = u.bucket_key"
    )
    return f"{cost} UNION ALL {latency}"


def _tool_sql() -> str:
    return (
        "SELECT 'generic_tool_reliability'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "CASE WHEN COALESCE(s.n_events, 0) = 0 THEN NULL ELSE s.metric_sum END "
        "AS metric_sum, 'count'::text AS metric_unit "
        f"FROM (VALUES {_values(TOOL_BUCKET_KEYS)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT tool_name AS bucket_key, COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants, "
        f"COUNT(*) FILTER (WHERE decision IN ({_DENIED}))::numeric AS metric_sum "
        "FROM public.tool_calls GROUP BY tool_name"
        ") s ON s.bucket_key = u.bucket_key"
    )


def _connector_sql() -> str:
    return (
        "SELECT 'generic_connector_failure_categories'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "NULL::numeric AS metric_sum, 'count'::text AS metric_unit "
        f"FROM (VALUES {_values(CONNECTOR_BUCKET_KEYS)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT 'secrets:' || outcome AS bucket_key, COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants "
        "FROM public.secret_reference_checks GROUP BY outcome "
        "UNION ALL "
        "SELECT CASE WHEN failure_kind IS NULL THEN 'monitoring:valid_read' "
        "ELSE 'monitoring:' || failure_kind END AS bucket_key, "
        "COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants "
        "FROM public.monitoring_status_snapshots GROUP BY 1 "
        "UNION ALL "
        "SELECT CASE WHEN target_available THEN 'deploy:available' "
        "ELSE 'deploy:unavailable' END AS bucket_key, "
        "COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants "
        "FROM public.deployment_target_snapshots GROUP BY 1"
        ") s ON s.bucket_key = u.bucket_key"
    )


def _failure_sql() -> str:
    return (
        "SELECT 'failure_mode_frequency_counts'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "NULL::numeric AS metric_sum, 'count'::text AS metric_unit "
        f"FROM (VALUES {_values(FAILURE_KEYS)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT failure_pattern AS bucket_key, COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants "
        "FROM public.agent_failure_events GROUP BY failure_pattern"
        ") s ON s.bucket_key = u.bucket_key"
    )


def _finding_sql() -> str:
    return (
        "SELECT 'security_safe_statistics'::text AS signal_class, "
        "u.bucket_key, COALESCE(s.n_events, 0)::int AS n_events, "
        "COALESCE(s.n_projects, 0)::int AS n_projects, "
        "COALESCE(s.n_tenants, 0)::int AS n_tenants, "
        "NULL::numeric AS metric_sum, 'count'::text AS metric_unit "
        f"FROM (VALUES {_values(FINDING_TYPES)}) AS u(bucket_key) "
        "LEFT JOIN ("
        "SELECT finding_type AS bucket_key, COUNT(*)::int AS n_events, "
        "COUNT(DISTINCT project_id)::int AS n_projects, "
        "COUNT(DISTINCT tenant_id)::int AS n_tenants "
        "FROM public.release_findings GROUP BY finding_type"
        ") s ON s.bucket_key = u.bucket_key"
    )


SOURCE_QUERIES: dict[str, str] = {
    "aggregate_eval_failure_rates": _eval_sql(),
    "aggregate_reviewer_miss_patterns": _reviewer_sql(),
    "anonymized_cost_and_latency_benchmarks": _cost_latency_sql(),
    "generic_tool_reliability": _tool_sql(),
    "generic_connector_failure_categories": _connector_sql(),
    "failure_mode_frequency_counts": _failure_sql(),
    "security_safe_statistics": _finding_sql(),
}


def expected_counts_function_body() -> str:
    """SQL function source. Each SOURCE_QUERIES value is a substring."""
    unioned = " UNION ALL ".join(SOURCE_QUERIES.values())
    return (
        "SELECT q.n_events, q.n_projects, q.n_tenants, q.metric_sum "
        f"FROM ({unioned}) AS q "
        "WHERE q.signal_class = p_signal_class AND q.bucket_key = p_bucket_key"
    )
