"""Pure Slice 62 cost-optimizer recommendation. Decision-only. No session."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.cost import CostStopDecision
from app.ecosystem.learning import TOOL_BUCKET_KEYS

RULESET_VERSION = "slice62.v1"
EXECUTION_PROVENANCE = "system_derived_cost_recommendation"

TASK_CLASSES: tuple[str, ...] = (
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

RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high")

TIER_ORDER: tuple[str, ...] = (
    "cost_efficient",
    "mid_quality",
    "high_quality",
    "frontier",
)

POLICY_TIER: dict[str, str] = {
    "document_classification": "cost_efficient",
    "requirements_extraction": "mid_quality",
    "architecture_decisions": "frontier",
    "routine_code_generation": "cost_efficient",
    "complex_ai_security_domain": "frontier",
    "code_review": "mid_quality",
    "shortcut_detection": "high_quality",
    "acceptance_verification": "high_quality",
    "judgment_oracle_review": "mid_quality",
}

REVIEW_TASK_CLASSES: frozenset[str] = frozenset(
    {
        "code_review",
        "shortcut_detection",
        "acceptance_verification",
        "judgment_oracle_review",
    }
)

FRONTIER_FLOOR: frozenset[str] = frozenset(
    {"architecture_decisions", "complex_ai_security_domain"}
)
HIGH_FLOOR: frozenset[str] = frozenset(
    {"shortcut_detection", "acceptance_verification"}
)

TOOL_DENY_HOLD_RATIO = Decimal("0.50")
REWORK_TO_INFERENCE_BUMP_RATIO = Decimal("1")

OVERLAY_NONE = "none"
OVERLAY_BUDGET = "budget_hold"
OVERLAY_TOOL = "tool_deny_hold"
OVERLAY_REWORK = "rework_intensity_bump"
TIER_HOLD = "hold"


class CostOptimizerError(Exception):
    """Fail-closed optimizer error. The string is the machine reason."""


@dataclass(frozen=True)
class RoutingFlags:
    """Three recorded or caller-supplied routing booleans."""

    cheap_first_for_low_risk: bool
    frontier_for_high_risk: bool
    use_cached_context_when_possible: bool


@dataclass(frozen=True)
class PublishedBucket:
    """A published aggregate row. Construction refuses unpublished rows."""

    signal_class: str
    bucket_key: str
    n_events: int
    n_projects: int
    n_tenants: int
    metric_sum: Decimal | None
    metric_unit: str
    published: bool
    bucket_id: object | None = None

    def __post_init__(self) -> None:
        if self.published is not True:
            raise CostOptimizerError("unpublished_bucket")


@dataclass(frozen=True)
class RecommendInput:
    """RO-RO input for ``evaluate_recommendation``."""

    task_class: str
    risk_level: str
    ambiguity_high: bool
    flags: RoutingFlags
    tool_name: str | None = None
    stop: CostStopDecision | None = None
    buckets: tuple[PublishedBucket, ...] = ()


@dataclass(frozen=True)
class Recommendation:
    """App-derived tier recommendation plus overlay and citations."""

    base_policy_tier: str
    clamped_policy_tier: str
    recommended_tier: str
    overlay_applied: str
    cache_hint: bool
    requires_multiple_reviewers: bool
    requires_model_diversity: bool
    cited: tuple[PublishedBucket, ...]


def evaluate_recommendation(inp: RecommendInput) -> Recommendation:
    """Return a tier recommendation. Never opens a session."""
    if inp.task_class not in TASK_CLASSES:
        raise CostOptimizerError("unknown_task_class")
    if inp.risk_level not in RISK_LEVELS:
        raise CostOptimizerError("unknown_risk_level")
    if inp.tool_name is not None and inp.tool_name not in TOOL_BUCKET_KEYS:
        raise CostOptimizerError("unknown_tool_name")
    for bucket in inp.buckets:
        if bucket.published is not True:
            raise CostOptimizerError("unpublished_bucket")

    base = _base_tier(inp.task_class, inp.ambiguity_high)
    clamped = _clamp(base, inp)
    overlay, cited, recommended = _apply_overlays(clamped, inp)
    is_judgment = inp.task_class == "judgment_oracle_review"
    return Recommendation(
        base_policy_tier=base,
        clamped_policy_tier=clamped,
        recommended_tier=recommended,
        overlay_applied=overlay,
        cache_hint=inp.flags.use_cached_context_when_possible,
        requires_multiple_reviewers=is_judgment,
        requires_model_diversity=is_judgment,
        cited=cited,
    )


def _base_tier(task_class: str, ambiguity_high: bool) -> str:
    if task_class == "document_classification" and ambiguity_high:
        return "mid_quality"
    return POLICY_TIER[task_class]


def _demote(tier: str) -> str:
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[0] if idx == 0 else TIER_ORDER[idx - 1]


def _promote(tier: str) -> str:
    idx = TIER_ORDER.index(tier)
    last = len(TIER_ORDER) - 1
    return TIER_ORDER[last] if idx == last else TIER_ORDER[idx + 1]


def _at_least(tier: str, floor: str) -> str:
    if TIER_ORDER.index(tier) < TIER_ORDER.index(floor):
        return floor
    return tier


def _clamp(base: str, inp: RecommendInput) -> str:
    clamped = base
    if inp.flags.cheap_first_for_low_risk and inp.risk_level == "low":
        clamped = _demote(clamped)
        if inp.task_class in FRONTIER_FLOOR:
            clamped = _at_least(clamped, "frontier")
        elif inp.task_class in HIGH_FLOOR:
            clamped = _at_least(clamped, "high_quality")
        elif inp.task_class == "document_classification" and inp.ambiguity_high:
            clamped = _at_least(clamped, "mid_quality")
    if inp.flags.frontier_for_high_risk and inp.risk_level == "high":
        if inp.task_class == "code_review":
            clamped = "frontier"
        else:
            clamped = _promote(clamped)
    return clamped


def _apply_overlays(
    clamped: str, inp: RecommendInput
) -> tuple[str, tuple[PublishedBucket, ...], str]:
    if inp.stop is not None and inp.stop.stop:
        return OVERLAY_BUDGET, (), TIER_HOLD
    tool_hit = _tool_deny_bucket(inp)
    if tool_hit is not None:
        return OVERLAY_TOOL, (tool_hit,), TIER_HOLD
    rework_pair = _rework_pair(inp)
    if rework_pair is not None:
        return OVERLAY_REWORK, rework_pair, _promote(clamped)
    return OVERLAY_NONE, (), clamped


def _tool_deny_bucket(inp: RecommendInput) -> PublishedBucket | None:
    if not inp.tool_name:
        return None
    for bucket in inp.buckets:
        if (
            bucket.signal_class == "generic_tool_reliability"
            and bucket.bucket_key == inp.tool_name
            and bucket.n_events > 0
            and bucket.metric_sum is not None
        ):
            ratio = bucket.metric_sum / Decimal(bucket.n_events)
            if ratio >= TOOL_DENY_HOLD_RATIO:
                return bucket
    return None


def _rework_pair(inp: RecommendInput) -> tuple[PublishedBucket, PublishedBucket] | None:
    if inp.task_class not in REVIEW_TASK_CLASSES:
        return None
    rework = _cost_bucket(inp.buckets, "cost:rework")
    inference = _cost_bucket(inp.buckets, "cost:model_inference")
    if rework is None or inference is None:
        return None
    if rework.n_events <= 0 or inference.n_events <= 0:
        return None
    if rework.metric_sum is None or inference.metric_sum is None:
        return None
    rework_mean = rework.metric_sum / Decimal(rework.n_events)
    inference_mean = inference.metric_sum / Decimal(inference.n_events)
    if rework_mean >= REWORK_TO_INFERENCE_BUMP_RATIO * inference_mean:
        return (rework, inference)
    return None


def _cost_bucket(
    buckets: tuple[PublishedBucket, ...], key: str
) -> PublishedBucket | None:
    for bucket in buckets:
        if (
            bucket.signal_class == "anonymized_cost_and_latency_benchmarks"
            and bucket.bucket_key == key
        ):
            return bucket
    return None
