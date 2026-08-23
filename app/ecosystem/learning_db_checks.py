"""CHECK fragments for Slice 62 tables. Consumed by ORM and migration ``0061``."""

from __future__ import annotations

from app.ecosystem.learning import (
    BUCKET_KEYS_BY_CLASS,
    CONNECTOR_BUCKET_KEYS,
    CONTRACT_VERSION,
    COST_KEYS,
    EXPECTED_BUCKET_COUNT,
    LATENCY_KEYS,
    PUBLISHER,
    RULESET_VERSION,
    SIGNAL_CLASSES,
    TOOL_BUCKET_KEYS,
)

# Local copies so this module stays a leaf (models import it).
_TASK_CLASSES = (
    "document_classification",
    "requirements_extraction",
    "architecture_decisions",
    "routine_code_generation",
    "complex_ai_security_domain",
    "code_review",
    "shortcut_detection",
    "acceptance_verification",
    "judgment_oracle_review",
)
_TIER_ORDER = ("cost_efficient", "mid_quality", "high_quality", "frontier")

_SIGNAL_IN = ", ".join(f"'{name}'" for name in SIGNAL_CLASSES)
_TOOL_IN = ", ".join(f"'{name}'" for name in TOOL_BUCKET_KEYS)
_TIER_IN = ", ".join(f"'{name}'" for name in _TIER_ORDER)
_TASK_IN = ", ".join(f"'{name}'" for name in _TASK_CLASSES)
_HOLD_TIERS = _TIER_IN + ", 'hold'"


def _in_keys(keys: tuple[str, ...]) -> str:
    return ", ".join(f"'{key}'" for key in keys)


def _class_key_clause() -> str:
    parts = []
    for signal, keys in BUCKET_KEYS_BY_CLASS.items():
        parts.append(f"(signal_class = '{signal}' AND bucket_key IN ({_in_keys(keys)}))")
    return " OR ".join(parts)


_COST_IN = _in_keys(COST_KEYS)
_LAT_IN = _in_keys(LATENCY_KEYS)

RUN_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_cpar_ruleset", f"ruleset_version = '{RULESET_VERSION}'"),
    ("ck_cpar_contract", f"contract_version = '{CONTRACT_VERSION}'"),
    ("ck_cpar_bucket_count", f"bucket_count = {EXPECTED_BUCKET_COUNT}"),
    (
        "ck_cpar_published_count",
        f"published_bucket_count BETWEEN 0 AND {EXPECTED_BUCKET_COUNT}",
    ),
    ("ck_cpar_publisher", f"publisher = '{PUBLISHER}'"),
)

BUCKET_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_cpab_signal", f"signal_class IN ({_SIGNAL_IN})"),
    ("ck_cpab_key_universe", _class_key_clause()),
    ("ck_cpab_n_events", "n_events >= 0"),
    ("ck_cpab_n_projects", "n_projects >= 0"),
    ("ck_cpab_n_tenants", "n_tenants >= 0"),
    ("ck_cpab_tenant_le_project", "n_tenants <= n_projects"),
    ("ck_cpab_project_le_events", "n_projects <= n_events"),
    ("ck_cpab_unit", "metric_unit IN ('usd','milliseconds','count')"),
    (
        "ck_cpab_metric_shape",
        "("
        "signal_class = 'anonymized_cost_and_latency_benchmarks' "
        f"AND bucket_key IN ({_COST_IN}) AND metric_unit = 'usd' "
        "AND ((n_events = 0 AND metric_sum IS NULL) OR "
        "(n_events > 0 AND metric_sum IS NOT NULL AND metric_sum >= 0))"
        ") OR ("
        "signal_class = 'anonymized_cost_and_latency_benchmarks' "
        f"AND bucket_key IN ({_LAT_IN}) AND metric_unit = 'milliseconds' "
        "AND ((n_events = 0 AND metric_sum IS NULL) OR "
        "(n_events > 0 AND metric_sum IS NOT NULL AND metric_sum >= 0))"
        ") OR ("
        "signal_class IN ('aggregate_eval_failure_rates','generic_tool_reliability') "
        "AND metric_unit = 'count' "
        "AND ((n_events = 0 AND metric_sum IS NULL) OR "
        "(n_events > 0 AND metric_sum IS NOT NULL AND metric_sum >= 0 "
        "AND metric_sum <= n_events))"
        ") OR ("
        "signal_class IN ('aggregate_reviewer_miss_patterns',"
        "'generic_connector_failure_categories',"
        "'failure_mode_frequency_counts',"
        "'security_safe_statistics') "
        "AND metric_unit = 'count' AND metric_sum IS NULL"
        ")",
    ),
)

OPT_RUN_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_cor_task", f"task_class IN ({_TASK_IN})"),
    ("ck_cor_risk", "risk_level IN ('low','medium','high')"),
    ("ck_cor_tool", f"tool_name IS NULL OR tool_name IN ({_TOOL_IN})"),
    (
        "ck_cor_flags_source",
        "flags_source IN ('recorded_cost_policy','caller_supplied')",
    ),
    (
        "ck_cor_flags_policy_iff",
        "(flags_source = 'recorded_cost_policy' AND policy_version_id IS NOT NULL) "
        "OR (flags_source = 'caller_supplied' AND policy_version_id IS NULL)",
    ),
    ("ck_cor_base_tier", f"base_policy_tier IN ({_TIER_IN})"),
    ("ck_cor_clamped_tier", f"clamped_policy_tier IN ({_TIER_IN})"),
    ("ck_cor_recommended", f"recommended_tier IN ({_HOLD_TIERS})"),
    (
        "ck_cor_overlay",
        "overlay_applied IN "
        "('none','budget_hold','tool_deny_hold','rework_intensity_bump')",
    ),
    (
        "ck_cor_hold_duality",
        "(recommended_tier = 'hold' AND overlay_applied IN "
        "('budget_hold','tool_deny_hold')) OR "
        "(recommended_tier <> 'hold' AND overlay_applied NOT IN "
        "('budget_hold','tool_deny_hold'))",
    ),
    (
        "ck_cor_none_equals_clamped",
        "overlay_applied <> 'none' OR recommended_tier = clamped_policy_tier",
    ),
    (
        "ck_cor_rework_not_hold",
        "overlay_applied <> 'rework_intensity_bump' OR recommended_tier <> 'hold'",
    ),
    (
        "ck_cor_overlay_cite_n",
        "(overlay_applied IN ('none','budget_hold') AND citation_count = 0) OR "
        "(overlay_applied = 'tool_deny_hold' AND citation_count = 1) OR "
        "(overlay_applied = 'rework_intensity_bump' AND citation_count = 2)",
    ),
    (
        "ck_cor_tool_deny_name",
        "overlay_applied <> 'tool_deny_hold' OR tool_name IS NOT NULL",
    ),
    (
        "ck_cor_judgment",
        "(task_class = 'judgment_oracle_review' AND requires_multiple_reviewers "
        "AND requires_model_diversity) OR "
        "(task_class <> 'judgment_oracle_review' AND NOT requires_multiple_reviewers "
        "AND NOT requires_model_diversity)",
    ),
    ("ck_cor_published_count", "published_bucket_count >= 0"),
    ("ck_cor_citation_count", "citation_count >= 0"),
    (
        "ck_cor_aggregate_shape",
        "(aggregate_run_id IS NULL AND published_bucket_count = 0 "
        "AND citation_count = 0) OR aggregate_run_id IS NOT NULL",
    ),
    ("ck_cor_ruleset", f"ruleset_version = '{RULESET_VERSION}'"),
    (
        "ck_cor_provenance",
        "execution_provenance = 'system_derived_cost_recommendation'",
    ),
)

# Connector universe probe (P-23b) — exact 12 keys.
CONNECTOR_KEY_SQL = _in_keys(CONNECTOR_BUCKET_KEYS)
