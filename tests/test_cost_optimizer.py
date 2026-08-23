"""Slice 62 pure optimizer probes."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.cost import CostStopDecision, StopReason
from app.ecosystem import cost_optimizer as opt
from app.ecosystem.cost_optimizer import (
    POLICY_TIER,
    CostOptimizerError,
    PublishedBucket,
    RecommendInput,
    RoutingFlags,
    evaluate_recommendation,
)

_CHEAP = RoutingFlags(True, False, False)
_FRONTIER = RoutingFlags(False, True, False)
_NEUTRAL = RoutingFlags(False, False, False)


def _pub(
    *,
    signal_class: str,
    bucket_key: str,
    n_events: int,
    metric_sum: Decimal | None,
    metric_unit: str = "count",
    n_projects: int = 3,
    n_tenants: int = 2,
) -> PublishedBucket:
    return PublishedBucket(
        signal_class=signal_class,
        bucket_key=bucket_key,
        n_events=n_events,
        n_projects=n_projects,
        n_tenants=n_tenants,
        metric_sum=metric_sum,
        metric_unit=metric_unit,
        published=True,
        bucket_id=None,
    )


def test_p2_policy_tier_table() -> None:
    assert POLICY_TIER["document_classification"] == "cost_efficient"
    assert POLICY_TIER["requirements_extraction"] == "mid_quality"
    assert POLICY_TIER["architecture_decisions"] == "frontier"
    assert POLICY_TIER["routine_code_generation"] == "cost_efficient"
    assert POLICY_TIER["complex_ai_security_domain"] == "frontier"
    assert POLICY_TIER["code_review"] == "mid_quality"
    assert POLICY_TIER["shortcut_detection"] == "high_quality"
    assert POLICY_TIER["acceptance_verification"] == "high_quality"
    assert POLICY_TIER["judgment_oracle_review"] == "mid_quality"
    assert "hold" not in POLICY_TIER.values()


def test_p3_unknown_inputs_refused() -> None:
    with pytest.raises(CostOptimizerError, match="unknown_task_class"):
        evaluate_recommendation(
            RecommendInput("not_a_class", "low", False, _NEUTRAL)
        )
    with pytest.raises(CostOptimizerError, match="unknown_risk_level"):
        evaluate_recommendation(
            RecommendInput("code_review", "production", False, _NEUTRAL)
        )


def test_p_opt_cheap_and_review_high() -> None:
    cheap_low = evaluate_recommendation(
        RecommendInput("document_classification", "low", False, _CHEAP)
    )
    assert cheap_low.recommended_tier == "cost_efficient"
    assert cheap_low.clamped_policy_tier == "cost_efficient"
    high = evaluate_recommendation(
        RecommendInput("document_classification", "high", False, _FRONTIER)
    )
    assert high.recommended_tier == "mid_quality"
    arch = evaluate_recommendation(
        RecommendInput("architecture_decisions", "low", False, _CHEAP)
    )
    assert arch.recommended_tier == "frontier"
    amb = evaluate_recommendation(
        RecommendInput("document_classification", "low", True, _CHEAP)
    )
    assert amb.recommended_tier == "mid_quality"
    shortcut = evaluate_recommendation(
        RecommendInput("shortcut_detection", "low", False, _CHEAP)
    )
    assert shortcut.recommended_tier == "high_quality"
    review_high = evaluate_recommendation(
        RecommendInput("code_review", "high", False, _FRONTIER)
    )
    assert review_high.clamped_policy_tier == "frontier"
    assert review_high.recommended_tier == "frontier"
    review_high_off = evaluate_recommendation(
        RecommendInput("code_review", "high", False, _NEUTRAL)
    )
    assert review_high_off.recommended_tier == "mid_quality"
    order = ("cost_efficient", "mid_quality", "high_quality", "frontier")
    assert order.index(cheap_low.recommended_tier) <= order.index(high.recommended_tier)


def test_p_opt_learn(monkeypatch: pytest.MonkeyPatch) -> None:
    rework = _pub(
        signal_class="anonymized_cost_and_latency_benchmarks",
        bucket_key="cost:rework",
        n_events=2,
        metric_sum=Decimal("4"),
        metric_unit="usd",
    )
    inference = _pub(
        signal_class="anonymized_cost_and_latency_benchmarks",
        bucket_key="cost:model_inference",
        n_events=2,
        metric_sum=Decimal("2"),
        metric_unit="usd",
    )
    buckets = (rework, inference)
    baseline = evaluate_recommendation(
        RecommendInput("document_classification", "low", False, _CHEAP)
    )
    assert baseline.recommended_tier == "cost_efficient"
    assert baseline.overlay_applied == "none"
    classified = evaluate_recommendation(
        RecommendInput("document_classification", "low", False, _CHEAP, buckets=buckets)
    )
    assert classified.recommended_tier == "cost_efficient"
    assert classified.overlay_applied == "none"
    bumped = evaluate_recommendation(
        RecommendInput("code_review", "low", False, _CHEAP, buckets=buckets)
    )
    assert bumped.base_policy_tier == "mid_quality"
    assert bumped.clamped_policy_tier == "cost_efficient"
    assert bumped.recommended_tier == "mid_quality"
    assert bumped.overlay_applied == "rework_intensity_bump"
    monkeypatch.setattr(opt, "REWORK_TO_INFERENCE_BUMP_RATIO", Decimal("999"))
    disabled = evaluate_recommendation(
        RecommendInput("code_review", "low", False, _CHEAP, buckets=buckets)
    )
    assert disabled.overlay_applied == "none"
    assert disabled.recommended_tier == "cost_efficient"


def test_p_opt_hold_budget_outranks_rework() -> None:
    rework = _pub(
        signal_class="anonymized_cost_and_latency_benchmarks",
        bucket_key="cost:rework",
        n_events=2,
        metric_sum=Decimal("4"),
        metric_unit="usd",
    )
    inference = _pub(
        signal_class="anonymized_cost_and_latency_benchmarks",
        bucket_key="cost:model_inference",
        n_events=2,
        metric_sum=Decimal("2"),
        metric_unit="usd",
    )
    rec = evaluate_recommendation(
        RecommendInput(
            "code_review",
            "low",
            False,
            _CHEAP,
            stop=CostStopDecision.stopped(StopReason.BUDGET_EXCEEDED),
            buckets=(rework, inference),
        )
    )
    assert rec.recommended_tier == "hold"
    assert rec.overlay_applied == "budget_hold"
    assert rec.cited == ()


def test_p_opt_hold_tool_ratio() -> None:
    hold = _pub(
        signal_class="generic_tool_reliability",
        bucket_key="pm.read_issues",
        n_events=100,
        metric_sum=Decimal("50"),
    )
    miss = _pub(
        signal_class="generic_tool_reliability",
        bucket_key="pm.read_issues",
        n_events=100,
        metric_sum=Decimal("49"),
    )
    held = evaluate_recommendation(
        RecommendInput(
            "code_review", "low", False, _CHEAP, tool_name="pm.read_issues", buckets=(hold,)
        )
    )
    assert held.recommended_tier == "hold"
    assert held.overlay_applied == "tool_deny_hold"
    skipped = evaluate_recommendation(
        RecommendInput(
            "code_review", "low", False, _CHEAP, tool_name="pm.read_issues", buckets=(miss,)
        )
    )
    assert skipped.overlay_applied == "none"


def test_p_opt_unpub_hand_built_refused() -> None:
    with pytest.raises(CostOptimizerError, match="unpublished_bucket"):
        PublishedBucket(
            signal_class="generic_tool_reliability",
            bucket_key="pm.read_issues",
            n_events=10,
            n_projects=1,
            n_tenants=1,
            metric_sum=Decimal("10"),
            metric_unit="count",
            published=False,
        )


def test_p_opt_judgment_flags() -> None:
    judged = evaluate_recommendation(
        RecommendInput("judgment_oracle_review", "medium", False, _NEUTRAL)
    )
    assert judged.requires_multiple_reviewers is True
    assert judged.requires_model_diversity is True
    review = evaluate_recommendation(RecommendInput("code_review", "medium", False, _NEUTRAL))
    assert review.requires_multiple_reviewers is False
    assert review.requires_model_diversity is False
