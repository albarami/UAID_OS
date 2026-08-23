"""Slice 62 tenant-safe learning vocabulary and bucket validation.

A bucket is published only when contributing projects and tenants clear the
named publication threshold. That threshold is not a privacy proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

RULESET_VERSION = "slice62.v1"
CONTRACT_VERSION = "slice62.aggregates.v1"
PUBLISHER = "slice62.learning_publish"

SIGNAL_CLASSES: tuple[str, ...] = (
    "aggregate_eval_failure_rates",
    "aggregate_reviewer_miss_patterns",
    "anonymized_cost_and_latency_benchmarks",
    "generic_tool_reliability",
    "generic_connector_failure_categories",
    "failure_mode_frequency_counts",
    "security_safe_statistics",
)

MIN_CONTRIBUTING_PROJECTS = 3
MIN_CONTRIBUTING_TENANTS = 2
EXPECTED_BUCKET_COUNT = 62

COST_COMPONENT_ORDER: tuple[str, ...] = (
    "model_inference",
    "tool_execution",
    "cloud_runtime",
    "ci_cd",
    "storage_retrieval",
    "monitoring",
    "human_review",
    "rework",
)

TOOL_BUCKET_KEYS: tuple[str, ...] = (
    "pm.create_issue",
    "source_control.create_branch",
    "source_control.read_branch_protection",
    "source_control.read_pull_request",
    "deployment.read_target_status",
    "monitoring.read_status",
    "secrets.verify_reference",
    "pm.read_issues",
    "source_control.open_pull_request",
    "ci.run_tests",
    "ci.deploy_staging",
    "ci.deploy_production",
    "source_control.merge_to_protected",
)

CONNECTOR_BUCKET_KEYS: tuple[str, ...] = (
    "secrets:resolved",
    "secrets:not_found",
    "secrets:unsupported_manager",
    "secrets:probe_error",
    "monitoring:unreachable",
    "monitoring:http_error",
    "monitoring:content_type",
    "monitoring:oversize",
    "monitoring:malformed",
    "monitoring:valid_read",
    "deploy:available",
    "deploy:unavailable",
)

REVIEWER_STATUSES: tuple[str, ...] = (
    "challenge_qualified",
    "threshold_breached",
    "inconclusive",
)

FINDING_TYPES: tuple[str, ...] = ("security", "shortcut")

DENIED_DECISIONS: tuple[str, ...] = (
    "denied_unknown_tool",
    "denied_invalid_params",
    "denied_not_allowlisted",
    "denied_policy",
    "denied_unknown_agent",
    "denied_unqualified_agent",
)

# Sorted §9.5.1 archetypes. Equality with live ARCHETYPES is asserted in P-1.
EVAL_KEYS: tuple[str, ...] = (
    "ai_evaluation",
    "builder",
    "data_engineer",
    "deployment_sre",
    "domain_reasoner",
    "evidence_auditor",
    "integration_connector",
    "knowledge_graph_rag",
    "prompt_engineer",
    "reviewer",
    "security_reviewer",
)
COST_KEYS: tuple[str, ...] = tuple(f"cost:{component}" for component in COST_COMPONENT_ORDER)
# Live CHALLENGE_FAMILIES / FAILURE_PATTERNS equality is asserted in P-1.
CHALLENGE_FAMILY_KEYS: tuple[str, ...] = (
    "defect",
    "shortcut",
    "weakened_test",
    "fake_integration",
    "missing_evidence",
)
FAILURE_KEYS: tuple[str, ...] = (
    "missing_skill",
    "weak_instructions",
    "wrong_tools",
    "poor_model_performance",
    "context_overload",
    "repeated_reviewer_rejection",
    "safety_authority_violation",
    "persistent_inability",
)
LATENCY_KEYS: tuple[str, ...] = tuple(
    f"latency:qa_harness:{family}" for family in CHALLENGE_FAMILY_KEYS
)

BUCKET_KEYS_BY_CLASS: dict[str, tuple[str, ...]] = {
    "aggregate_eval_failure_rates": EVAL_KEYS,
    "aggregate_reviewer_miss_patterns": REVIEWER_STATUSES,
    "anonymized_cost_and_latency_benchmarks": COST_KEYS + LATENCY_KEYS,
    "generic_tool_reliability": TOOL_BUCKET_KEYS,
    "generic_connector_failure_categories": CONNECTOR_BUCKET_KEYS,
    "failure_mode_frequency_counts": FAILURE_KEYS,
    "security_safe_statistics": FINDING_TYPES,
}

METRIC_UNITS = ("usd", "milliseconds", "count")

COUNT_WITH_SUM_CLASSES = frozenset(
    {"aggregate_eval_failure_rates", "generic_tool_reliability"}
)
NULL_SUM_CLASSES = frozenset(
    {
        "aggregate_reviewer_miss_patterns",
        "generic_connector_failure_categories",
        "failure_mode_frequency_counts",
        "security_safe_statistics",
    }
)

FORBIDDEN_SOURCE_COLUMNS: tuple[str, ...] = (
    "description",
    "params",
    "summary",
    "detail",
    "body",
    "title",
    "content",
    "prompt",
    "target_ref",
    "reference_name",
    "repo_ref",
    "actor",
    "external_ref",
    "reason",
    "agent_id",
)

CONNECTOR_FORBIDDEN_COLUMNS: tuple[str, ...] = (
    "target_ref",
    "reference_name",
    "manager",
    "repo_ref",
)


class LearningError(Exception):
    """Fail-closed learning validation error."""


@dataclass(frozen=True)
class PublicationThreshold:
    """Publication threshold. Not a privacy proof."""

    min_projects: int = MIN_CONTRIBUTING_PROJECTS
    min_tenants: int = MIN_CONTRIBUTING_TENANTS

    def is_published(self, n_projects: int, n_tenants: int) -> bool:
        """Return True when both contributing floors are met."""
        return n_projects >= self.min_projects and n_tenants >= self.min_tenants


@dataclass(frozen=True)
class BucketRow:
    """One universe row ready for persist."""

    signal_class: str
    bucket_key: str
    n_events: int
    n_projects: int
    n_tenants: int
    metric_sum: Decimal | None
    metric_unit: str


def validate_bucket(row: BucketRow) -> BucketRow:
    """Fail-closed shape check for one aggregate bucket."""
    if row.signal_class not in SIGNAL_CLASSES:
        raise LearningError("unknown_signal_class")
    allowed = BUCKET_KEYS_BY_CLASS[row.signal_class]
    if row.bucket_key not in allowed:
        raise LearningError("unknown_bucket_key")
    if row.n_events < 0 or row.n_projects < 0 or row.n_tenants < 0:
        raise LearningError("negative_count")
    if row.n_tenants > row.n_projects or row.n_projects > row.n_events:
        raise LearningError("count_shape")
    if row.metric_unit not in METRIC_UNITS:
        raise LearningError("unknown_metric_unit")
    _validate_metric(row)
    return row


def _validate_metric(row: BucketRow) -> None:
    if row.signal_class == "anonymized_cost_and_latency_benchmarks":
        if row.bucket_key.startswith("cost:"):
            if row.metric_unit != "usd":
                raise LearningError("metric_unit")
        elif row.bucket_key.startswith("latency:"):
            if row.metric_unit != "milliseconds":
                raise LearningError("metric_unit")
        else:
            raise LearningError("unknown_bucket_key")
        _sum_null_rule(row, bounded=False)
        return
    if row.signal_class in COUNT_WITH_SUM_CLASSES:
        if row.metric_unit != "count":
            raise LearningError("metric_unit")
        _sum_null_rule(row, bounded=True)
        return
    if row.signal_class in NULL_SUM_CLASSES:
        if row.metric_unit != "count" or row.metric_sum is not None:
            raise LearningError("metric_shape")
        return
    raise LearningError("unknown_signal_class")


def _sum_null_rule(row: BucketRow, *, bounded: bool) -> None:
    if row.n_events == 0:
        if row.metric_sum is not None:
            raise LearningError("metric_shape")
        return
    if row.metric_sum is None or row.metric_sum < 0:
        raise LearningError("metric_shape")
    if bounded and row.metric_sum > row.n_events:
        raise LearningError("metric_shape")
