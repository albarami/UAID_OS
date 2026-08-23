"""Slice-59 criterion and improvement ladders. Seq 5 is the only pass path."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from app.identity import REQUEST_AUTHENTICATED, AuthenticatedActor
from app.ops.hotfix import gate10_conjunction_passed
from app.ops.stabilization import (
    CRITERION_COUNT,
    PASSABLE_SEQS,
    REFRESH_POSTURE,
    CriterionChild,
    ImprovementChild,
    StabilizationError,
)


def _monitoring_stale(snapshot: object, *, as_of: datetime, max_age_hours: int) -> bool:
    observed_at = getattr(snapshot, "observed_at", None)
    if observed_at is None:
        return True
    observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
    now = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    return (now - observed) > timedelta(hours=max_age_hours)


def evaluate_monitoring_criterion(
    *,
    declared_target: str | None,
    snapshot: object | None,
    as_of: datetime,
    max_age_hours: int,
) -> CriterionChild:
    """Seq 3 ladder. Never returns ``passed``."""
    key = "monitoring_confirmed_active"
    if declared_target is None:
        return CriterionChild(3, key, "not_observed", "no_monitoring_declaration")
    if snapshot is None:
        return CriterionChild(3, key, "not_observed", "monitoring_declared_but_no_evidence")
    snap_id = getattr(snapshot, "id")
    if not isinstance(snap_id, uuid.UUID):
        raise StabilizationError("monitoring snapshot id is required")
    if getattr(snapshot, "provenance") != "connector_verified":
        return CriterionChild(3, key, "failed", "monitoring_observed_unverified", snap_id)
    if _monitoring_stale(snapshot, as_of=as_of, max_age_hours=max_age_hours):
        return CriterionChild(3, key, "failed", "monitoring_evidence_stale", snap_id)
    if getattr(snapshot, "response_valid") is False:
        return CriterionChild(3, key, "not_evaluable", "monitoring_evidence_unreadable", snap_id)
    if getattr(snapshot, "overall_active") is False:
        return CriterionChild(3, key, "failed", "monitoring_or_alerts_inactive", snap_id)
    return CriterionChild(
        3, key, "not_evaluable", "monitoring_active_app_derived_not_db_provable", snap_id
    )


def evaluate_rollback_criterion(coverage: object, run_id: uuid.UUID | None) -> CriterionChild:
    """Seq 4 ladder. Never returns ``passed``."""
    key = "rollback_blockers_open"
    if run_id is None:
        return CriterionChild(4, key, "not_observed", "no_rollback_run")
    if not gate10_conjunction_passed(coverage):
        return CriterionChild(
            4,
            key,
            "failed",
            "rollback_path_not_current",
            rollback_verification_run_id=run_id,
        )
    return CriterionChild(
        4,
        key,
        "not_evaluable",
        "rollback_currency_app_derived_not_db_provable",
        rollback_verification_run_id=run_id,
    )


def evaluate_handover_criterion(handover: object | None) -> CriterionChild:
    """Seq 5 — the only passable criterion, scoped to the latest recorded row."""
    key = "support_handover_complete"
    if handover is None:
        return CriterionChild(5, key, "not_observed", "no_handover_record")
    handover_id = getattr(handover, "id")
    status = getattr(handover, "status")
    if not isinstance(handover_id, uuid.UUID):
        raise StabilizationError("handover id is required")
    if status == "recorded_complete":
        return CriterionChild(
            5, key, "passed", "handover_recorded_complete", handover_id=handover_id
        )
    return CriterionChild(5, key, "failed", "handover_recorded_incomplete", handover_id=handover_id)


def _fixed_criterion(seq: int) -> CriterionChild:
    locked = {
        1: (
            "zero_open_critical_incidents_for_days",
            "not_evaluable",
            "no_production_coverage_clock",
        ),
        2: (
            "error_budget_under_threshold",
            "not_evaluable",
            "error_budget_threshold_unparsed_string",
        ),
        6: ("backup_restore_validated", "not_observed", "no_backup_restore_source"),
        7: ("p95_latency_within_slo", "not_observed", "no_latency_slo_source"),
        8: (
            "no_unresolved_security_alerts",
            "not_observed",
            "no_post_launch_security_alert_source",
        ),
    }
    key, status, reason = locked[seq]
    return CriterionChild(seq, key, status, reason)


def assemble_criteria(
    monitoring: CriterionChild, rollback: CriterionChild, handover: CriterionChild
) -> tuple[CriterionChild, ...]:
    """Return the exact seq 1–8 set. Seq 3 and 4 cannot be ``passed``."""
    children = (
        _fixed_criterion(1),
        _fixed_criterion(2),
        monitoring,
        rollback,
        handover,
        _fixed_criterion(6),
        _fixed_criterion(7),
        _fixed_criterion(8),
    )
    for child in children:
        if child.status == "passed" and child.seq not in PASSABLE_SEQS:
            raise StabilizationError("only seq 5 can be passed")
    return children


def assemble_improvements(
    *,
    recurrence_count: int,
    domain_pack_declared: bool,
    findings_report_id: uuid.UUID | None,
    oracle_gap_count: int | None,
    forecast_run_id: uuid.UUID | None,
    forecast_run_present: bool,
) -> tuple[ImprovementChild, ...]:
    """Return the exact seq 1–8 improvement inventory. No source-system writes."""
    if not isinstance(recurrence_count, int) or isinstance(recurrence_count, bool):
        raise StabilizationError("recurrence_count must be an int")
    if recurrence_count < 0:
        raise StabilizationError("recurrence_count must be >= 0")
    seq6_observed = findings_report_id is not None
    seq7_observed = forecast_run_present
    if seq7_observed and forecast_run_id is None:
        raise StabilizationError("cost forecast run id required when run_present")
    if seq6_observed and oracle_gap_count is None:
        raise StabilizationError("oracle gap count required when a findings report exists")
    return (
        ImprovementChild(1, "lessons_learned", "not_observed", "no_lessons_store"),
        ImprovementChild(
            2,
            "recurring_failure_patterns",
            "observed",
            "incident_category_recurrence",
            metric_int=recurrence_count,
        ),
        ImprovementChild(3, "agent_evals", "not_observed", "no_live_eval_update"),
        ImprovementChild(4, "prompt_templates", "not_observed", "no_prompt_store"),
        ImprovementChild(
            5,
            "domain_pack_gaps",
            "observed" if domain_pack_declared else "not_observed",
            "domain_pack_declared" if domain_pack_declared else "no_domain_pack_declaration",
        ),
        ImprovementChild(
            6,
            "test_oracle_gaps",
            "observed" if seq6_observed else "not_observed",
            "acceptance_without_oracle_count" if seq6_observed else "no_findings_report",
            findings_report_id=findings_report_id if seq6_observed else None,
            metric_int=oracle_gap_count if seq6_observed else None,
        ),
        ImprovementChild(
            7,
            "cost_forecasts",
            "observed" if seq7_observed else "not_observed",
            "forecast_cited_not_refreshed" if seq7_observed else "no_cost_forecast_run",
            cost_forecast_run_id=forecast_run_id if seq7_observed else None,
            refresh_posture=REFRESH_POSTURE if seq7_observed else None,
        ),
        ImprovementChild(
            8, "connector_reliability_scores", "not_observed", "no_connector_score_store"
        ),
    )


def compute_status_counters(criteria: Sequence[CriterionChild]) -> tuple[int, int, int, int]:
    """Return ``(passed, failed, not_observed, not_evaluable)`` over eight children."""
    if len(criteria) != CRITERION_COUNT:
        raise StabilizationError("criterion set must contain 8 rows")
    passed = sum(1 for child in criteria if child.status == "passed")
    failed = sum(1 for child in criteria if child.status == "failed")
    missing = sum(1 for child in criteria if child.status == "not_observed")
    unevaluable = sum(1 for child in criteria if child.status == "not_evaluable")
    if passed + failed + missing + unevaluable != CRITERION_COUNT:
        raise StabilizationError("criterion statuses are not a partition of 8")
    return passed, failed, missing, unevaluable


def closure_result(
    *,
    latch_active: bool,
    actor: AuthenticatedActor | None,
    window_assessor_subject: str,
    window_assessor_provenance: str,
) -> str:
    """First-match closure ladder. There is no approved or closed result."""
    if latch_active:
        return "refused_latch_active"
    if actor is None:
        return "refused_unauthenticated"
    if (
        actor.subject == window_assessor_subject
        and actor.provenance == REQUEST_AUTHENTICATED
        and window_assessor_provenance == REQUEST_AUTHENTICATED
    ):
        return "refused_same_actor"
    return "refused_incomplete_criteria"


def oracle_gap_count(report: object) -> int:
    """Count ``G_ACCEPTANCE_WITHOUT_ORACLE`` entries in a findings report body."""
    payload = getattr(report, "report", report)
    if not isinstance(payload, dict):
        return 0
    gaps = payload.get("gaps")
    if not isinstance(gaps, list):
        return 0
    return sum(
        1
        for gap in gaps
        if isinstance(gap, dict) and gap.get("kind") == "G_ACCEPTANCE_WITHOUT_ORACLE"
    )
