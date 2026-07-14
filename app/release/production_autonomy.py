"""A5 production-autonomy evaluator skeleton (Slice 21..26 + 28 + 30 + 31, spec §5.1 + App. B) — pure.

Scores the **13 Appendix-B A5 gates** and emits a ``ProductionAutonomyReport`` that is **fail-closed
and non-authorizing**. Every gate carries ``status``, ``reason``, and a ``context`` dict
(default ``{}``, serialized on every gate):

- **Gate #1 (R5 intake complete)** passes at ``R5``; **gate #2 (deployment target, Slice 30)**, **gate #3
  (branch protection, Slice 28)**, and **gate #11 (monitoring/alerts, Slice 31)** are **PASS-capable**
  — each via a binding-bound, latest-wins, connector_verified + fresh ladder (see below).
- **Slice 51 (#9 cost forecast — PASS-capable):** evaluates the latest current, exact-bound,
  system-derived projection over recorded spend and declared remaining-work assumptions. All six
  budget/policy dimensions must be strictly within their caps, with no STOP or approval trigger.
- Gate #12 remains a partial-context ``insufficient_evidence`` gate.
- **Slice 50 (#7 release issue disposition — PASS-capable):** evaluates a generated DB-bound verdict
  over one re-audited Slice-49 core and its exact frozen candidate. Only a current, consistent,
  gate-eligible ``passed``/``passed_with_limitations`` attestation can pass; no caller verdict or
  legacy Slice-47 counts can do so. Its scope is only ``known_bound_issue_disposition``.
- **Slice 28 (#3 branch protection — PASS-capable):** gate #3 evaluates the latest snapshot for the
  project's **currently declared** repo/branch (B1-cont) via a latest-wins ladder —
  ``branch_protection_repo_unbound`` → ``no_branch_protection_evidence`` →
  ``branch_protection_observed_unverified`` → ``branch_protection_evidence_stale`` →
  ``branch_protection_insufficient`` → **``passed``** when the latest is ``connector_verified`` +
  protection-enabled + PR-reviews + ≥1 required check + fresh. It is the **first non-#1 gate that can
  PASS**; counts are context only; the report carries ``branch_protection_repo_bound`` (never raw
  ``repo_ref``).
- **Gate #11 (monitoring/alerts active — PASS-capable, Slice 31):** evaluates the latest snapshot for
  the project's **currently declared** monitoring ``status_url`` (B2) via a latest-wins ladder —
  ``no_monitoring_declaration`` → ``monitoring_declared_but_no_evidence`` →
  ``monitoring_observed_unverified`` → ``monitoring_evidence_stale`` → ``monitoring_evidence_unreadable``
  (a verified+fresh but unreadable provider — **honest, never "inactive"**, B4) →
  ``monitoring_or_alerts_inactive`` → **``passed``** when the latest is ``connector_verified`` +
  valid-read + ``overall_active`` + fresh. Context carries the read-state (never a URL/host).
- **Slice 43 (#4 test-oracle execution — PASS-capable):** evaluates every structurally valid canonical
  project test oracle under a conservative scope, using one selected declared-repo + commit binding and
  exact-definition latest-wins runs. Empty, invalid, unrun, failed, untrusted, incomplete, or inadequate
  judgment evidence fails closed; only complete non-vacuous coverage passes.
- **Slice 44 (#5 security scan provenance — PASS-capable):** evaluates connector-observed exact-binding
  coverage for all five mandatory categories and then blocks on every open critical security finding,
  regardless of its provenance.
- **Slice 45 (#6 shortcut detector execution — PASS-capable):** evaluates system-executed deterministic
  and blind independent-review coverage for all twelve mandatory categories over a connector-verified
  exact-commit corpus, then blocks on every open critical shortcut finding regardless of provenance.
- The **two** remaining sourceless gates (#10, #13) return ``no_evidence_source:<subsystem>``.

``a5_satisfied`` is true only if **all 13** gates pass (still impossible with remaining unmet gates).
``can_go_live_autonomously`` is **hard-false always** — go-live
additionally requires a request-authenticated, verified A5 pre-approval that does not exist yet. This
module never authorizes production: it only reports the gate structure honestly. ``ruleset_version`` is
``slice52.v1``. Gate #8 is PASS-capable only through complete DB-bound acceptance-authorship evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.release.ci_evidence import gate3_protection_sufficient

A5_RULESET_VERSION = "slice52.v1"

# The only three permitted gate statuses (subsystem detail goes in ``reason``, never the status).
STATUS_PASSED = "passed"
STATUS_INSUFFICIENT = "insufficient_evidence"
STATUS_NO_SOURCE = "no_evidence_source"

NO_GO_LIVE_REASONS = (
    "a5_gates_not_all_satisfied",
    "request_authenticated_a5_preapproval_not_implemented",
)


@dataclass(frozen=True)
class GateResult:
    number: int
    gate: str
    status: str
    reason: str
    # Slice 22: optional per-gate context (e.g. counts). Always serialized ({} when none).
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "gate": self.gate,
            "status": self.status,
            "reason": self.reason,
            "context": dict(self.context),
        }


@dataclass
class ProductionAutonomyReport:
    project_id: str
    gates: list[GateResult] = field(default_factory=list)

    @property
    def a5_satisfied(self) -> bool:
        # All 13 gates must pass. Non-authorizing skeleton ⇒ false this slice.
        return bool(self.gates) and all(g.status == STATUS_PASSED for g in self.gates)

    def to_dict(self) -> dict:
        unmet = [g for g in self.gates if g.status != STATUS_PASSED]
        return {
            "project_id": self.project_id,
            "a5_satisfied": self.a5_satisfied,
            # ALWAYS false: go-live needs A5 satisfied AND a verified, request-authenticated
            # pre-approval (not implemented). Never derived solely from a5_satisfied.
            "can_go_live_autonomously": False,
            "can_go_live_reasons": list(NO_GO_LIVE_REASONS),
            "gates": [g.to_dict() for g in self.gates],
            "passed_gate_count": sum(1 for g in self.gates if g.status == STATUS_PASSED),
            "unmet_gates": [g.to_dict() for g in unmet],
            "ruleset_version": A5_RULESET_VERSION,
        }


def _no_source(number: int, gate: str, subsystem: str) -> GateResult:
    return GateResult(number, gate, STATUS_NO_SOURCE, f"{STATUS_NO_SOURCE}:{subsystem}")


def _insufficient(number: int, gate: str, reason: str, context: dict | None = None) -> GateResult:
    return GateResult(number, gate, STATUS_INSUFFICIENT, reason, context or {})


def evaluate_production_autonomy(
    project_id,
    *,
    readiness_level: str,
    autonomy_policy_present: bool = False,
    cost_policy_present: bool = False,
    # Slice 51 — exact release/core/input-bound system-derived cost forecast evidence.
    cost_forecast_scope_resolved: bool = False,
    cost_forecast_policy_present: bool = False,
    cost_forecast_policy_valid: bool = False,
    cost_forecast_budget_present: bool = False,
    cost_forecast_budget_valid: bool = False,
    cost_forecast_history_count: int = 0,
    cost_forecast_run_present: bool = False,
    cost_forecast_attempt_failed: bool = False,
    cost_forecast_binding_current: bool = False,
    cost_forecast_input_coverage_complete: bool = False,
    cost_forecast_price_coverage_complete: bool = False,
    cost_forecast_evidence_consistent: bool = False,
    cost_forecast_stop_active: bool = False,
    cost_forecast_all_dimensions_within: bool = False,
    cost_forecast_approval_required: bool = False,
    cost_forecast_gate_eligible: bool = False,
    cost_forecast_dimension_count: int = 0,
    cost_forecast_utc_date: str | None = None,
    cost_forecast_execution_provenance: str | None = None,
    environments_declared: bool = False,
    acceptance_scope_resolved: bool = True,
    acceptance_binding_resolved: bool = False,
    acceptance_scope_count: int = 0,
    acceptance_verification_run_present: bool = False,
    acceptance_verification_failed: bool = False,
    acceptance_missing_authorship_count: int = 0,
    acceptance_untrusted_count: int = 0,
    acceptance_disputed_count: int = 0,
    acceptance_unapproved_count: int = 0,
    acceptance_controls_failed_count: int = 0,
    acceptance_eligible_count: int = 0,
    acceptance_evidence_consistent: bool = False,
    active_risk_acceptance_count: int = 0,
    open_issue_count: int = 0,
    open_blocking_issue_count: int = 0,
    open_unaccepted_blocking_issue_count: int = 0,
    frozen_release_candidate_count: int = 0,
    latest_frozen_release_candidate_id: str | None = None,
    latest_frozen_release_ref: str | None = None,
    bound_open_issue_count: int = 0,
    bound_open_blocking_issue_count: int = 0,
    bound_open_unaccepted_blocking_issue_count: int = 0,
    bound_issue_count: int = 0,
    bound_trusted_issue_count: int = 0,
    bound_untrusted_issue_count: int = 0,
    bound_finding_bridge_issue_count: int = 0,
    bound_security_bridge_issue_count: int = 0,
    bound_shortcut_bridge_issue_count: int = 0,
    bound_accepted_issue_count: int = 0,
    bound_release_consistent_accepted_issue_count: int = 0,
    release_bound_active_risk_acceptance_count: int = 0,
    legacy_unbound_risk_acceptance_count: int = 0,
    # Slice 50 — exact frozen-candidate/core/input-bound release verdict evidence.
    release_evidence_core_present: bool = False,
    release_evidence_core_audited: bool = False,
    release_verdict_run_present: bool = False,
    release_verdict_attempt_failed: bool = False,
    release_verdict_binding_current: bool = False,
    release_verdict_evidence_consistent: bool = False,
    release_verdict_spec_verdict: str | None = None,
    release_verdict_gate_eligible: bool = False,
    release_verdict_reason_code: str | None = None,
    release_verdict_decision_scope: str | None = None,
    release_verdict_execution_provenance: str | None = None,
    open_security_finding_count: int = 0,
    open_unaccepted_critical_security_finding_count: int = 0,
    open_shortcut_finding_count: int = 0,
    open_unaccepted_critical_shortcut_finding_count: int = 0,
    branch_protection_snapshot_count: int = 0,
    connector_verified_branch_protection_count: int = 0,
    latest_branch_protection_provenance: str | None = None,
    latest_branch_protection_enabled: bool | None = None,
    latest_required_status_check_count: int = 0,
    branch_protection_repo_bound: bool = False,
    latest_branch_protection_required_pull_request_reviews: bool | None = None,
    latest_branch_protection_fresh: bool = False,
    # Slice 30 — gate #2 deployment-target evidence (repo-bound, latest-wins).
    deployment_target_bound: bool = False,
    latest_deployment_target_provenance: str | None = None,
    latest_deployment_target_available: bool | None = None,
    latest_deployment_target_fresh: bool = False,
    # Slice 52 — exact candidate/core/commit/target-bound connector-observed staging rollback drill.
    rollback_scope_resolved: bool = False,
    rollback_core_present: bool = False,
    rollback_core_reaudited: bool = False,
    rollback_repo_binding_agreed: bool = False,
    rollback_staging_target_valid: bool = False,
    rollback_staging_snapshot_present: bool = False,
    rollback_staging_snapshot_available: bool = False,
    rollback_staging_snapshot_fresh: bool = False,
    rollback_run_present: bool = False,
    rollback_attempt_failed: bool = False,
    rollback_artifact_trusted: bool = False,
    rollback_binding_current: bool = False,
    rollback_phase_coverage_complete: bool = False,
    rollback_evidence_consistent: bool = False,
    rollback_drill_passed: bool = False,
    rollback_gate_eligible: bool = False,
    rollback_phase_count: int = 0,
    rollback_execution_observation: str | None = None,
    # Slice 31 — gate #11 monitoring/alerts evidence (binding-bound, latest-wins).
    monitoring_bound: bool = False,
    latest_monitoring_provenance: str | None = None,
    latest_monitoring_response_valid: bool | None = None,
    latest_monitoring_overall_active: bool | None = None,
    latest_monitoring_fresh: bool = False,
    latest_monitoring_failure_kind: str | None = None,
    # Slice 43 — gate #4 conservative canonical-oracle scope and exact-binding coverage.
    test_oracle_scope_resolved: bool = True,
    test_oracle_scope_count: int = 0,
    test_oracle_valid_definition_count: int = 0,
    test_oracle_invalid_definition_count: int = 0,
    test_oracle_binding_present: bool = False,
    test_oracle_unrun_count: int = 0,
    test_oracle_untrusted_count: int = 0,
    test_oracle_incomplete_count: int = 0,
    test_oracle_execution_failed_count: int = 0,
    test_oracle_judgment_control_failed_count: int = 0,
    test_oracle_failed_count: int = 0,
    test_oracle_passed_count: int = 0,
    # Slice 44 — gate #5 connector-observed exact-binding security coverage.
    security_scan_scope_resolved: bool = True,
    security_scan_binding_resolved: bool = False,
    security_scan_run_present: bool = False,
    security_scan_artifact_trusted: bool = False,
    security_scan_execution_failed: bool = False,
    security_scan_coverage_complete: bool = False,
    security_scan_evidence_consistent: bool = False,
    security_scan_mandatory_category_count: int = 5,
    security_scan_completed_category_count: int = 0,
    security_scan_failed_category_count: int = 0,
    security_scan_finding_count: int = 0,
    # Slice 45 — gate #6 hybrid exact-binding shortcut-review coverage.
    shortcut_review_scope_resolved: bool = True,
    shortcut_review_binding_resolved: bool = False,
    shortcut_review_run_present: bool = False,
    shortcut_review_corpus_trusted: bool = False,
    shortcut_review_execution_failed: bool = False,
    shortcut_review_independence_resolved: bool = False,
    shortcut_review_coverage_complete: bool = False,
    shortcut_review_evidence_consistent: bool = False,
    shortcut_review_mandatory_category_count: int = 12,
    shortcut_review_completed_category_count: int = 0,
    shortcut_review_failed_category_count: int = 0,
    shortcut_review_reviewer_count: int = 0,
    shortcut_review_finding_count: int = 0,
) -> ProductionAutonomyReport:
    """Deterministic, fail-closed A5 evaluation. Context booleans are recorded as *context only* —
    they never flip a gate to ``passed`` (deny-by-default). Defaults are False (fail-closed)."""

    # Gate #1 — the only gate with a real, gate-passing source today (the R5 readiness auditor).
    if readiness_level == "R5":
        gate1 = GateResult(1, "r5_intake_complete", STATUS_PASSED, "readiness_r5")
    else:
        gate1 = _insufficient(1, "r5_intake_complete", f"readiness_below_r5:{readiness_level}")

    # Gate #2 (Slice 30) — production deployment-target availability, repo-bound latest-wins ladder.
    # PASSes only on the latest connector_verified + available + fresh snapshot for the CURRENTLY
    # declared target. ``environments_declared`` is retained as context only (never passes a gate).
    _gate2_name = "production_deployment_target_available"
    if not deployment_target_bound:
        gate2 = _insufficient(2, _gate2_name, "no_environment_declaration")
    elif latest_deployment_target_provenance is None:
        gate2 = _insufficient(2, _gate2_name, "environments_declared_but_no_target_evidence")
    elif latest_deployment_target_provenance != "connector_verified":
        gate2 = _insufficient(2, _gate2_name, "deployment_target_observed_unverified")
    elif not latest_deployment_target_fresh:
        gate2 = _insufficient(2, _gate2_name, "deployment_target_evidence_stale")
    elif not latest_deployment_target_available:
        gate2 = _insufficient(2, _gate2_name, "deployment_target_unavailable")
    else:
        gate2 = GateResult(
            2, _gate2_name, STATUS_PASSED, "production_deployment_target_available_verified"
        )
    _gate8_name = "no_unapproved_generated_ac_in_critical_gates"
    _gate8_ctx = {
        "acceptance_scope_resolved": acceptance_scope_resolved,
        "acceptance_binding_resolved": acceptance_binding_resolved,
        "acceptance_scope_count": acceptance_scope_count,
        "acceptance_verification_run_present": acceptance_verification_run_present,
        "acceptance_verification_failed": acceptance_verification_failed,
        "acceptance_missing_authorship_count": acceptance_missing_authorship_count,
        "acceptance_untrusted_count": acceptance_untrusted_count,
        "acceptance_disputed_count": acceptance_disputed_count,
        "acceptance_unapproved_count": acceptance_unapproved_count,
        "acceptance_controls_failed_count": acceptance_controls_failed_count,
        "acceptance_eligible_count": acceptance_eligible_count,
        "acceptance_evidence_consistent": acceptance_evidence_consistent,
        "approval_provenance_tier": "db_verified_independent_agent_lineage",
        "human_owner_approval_gate_eligible": False,
    }
    if not acceptance_scope_resolved:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:acceptance_scope_unresolved", _gate8_ctx)
    elif not acceptance_binding_resolved:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:acceptance_binding_unresolved", _gate8_ctx)
    elif acceptance_scope_count <= 0:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:no_proven_release_gating_acceptance_scope", _gate8_ctx)
    elif not acceptance_verification_run_present:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:acceptance_verification_not_run", _gate8_ctx)
    elif acceptance_verification_failed:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:acceptance_verification_failed", _gate8_ctx)
    elif acceptance_missing_authorship_count > 0:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:acceptance_authorship_missing", _gate8_ctx)
    elif acceptance_untrusted_count > 0:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:authorship_approval_unverified", _gate8_ctx)
    elif acceptance_disputed_count > 0:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:disputed_acceptance_criteria_in_release_scope", _gate8_ctx)
    elif acceptance_unapproved_count > 0:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:unapproved_generated_acceptance_criteria_in_release_scope", _gate8_ctx)
    elif acceptance_controls_failed_count > 0:
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:acceptance_authorship_controls_failed", _gate8_ctx)
    elif (
        not acceptance_evidence_consistent
        or acceptance_eligible_count != acceptance_scope_count
        or any(count < 0 for count in (
            acceptance_scope_count, acceptance_missing_authorship_count, acceptance_untrusted_count,
            acceptance_disputed_count, acceptance_unapproved_count, acceptance_controls_failed_count,
            acceptance_eligible_count,
        ))
    ):
        gate8 = _insufficient(8, _gate8_name, "insufficient_evidence:acceptance_evidence_inconsistent", _gate8_ctx)
    else:
        gate8 = GateResult(8, _gate8_name, STATUS_PASSED, "passed:no_unapproved_generated_acceptance_criteria_in_critical_gates_verified", _gate8_ctx)
    _gate9_name = "cost_forecast_within_policy"
    _gate9_ctx = {
        "scope_resolved": cost_forecast_scope_resolved,
        "structured_policy_present": cost_forecast_policy_present,
        "structured_policy_valid": cost_forecast_policy_valid,
        "budget_present": cost_forecast_budget_present,
        "budget_valid": cost_forecast_budget_valid,
        "ledger_event_count": cost_forecast_history_count,
        "run_present": cost_forecast_run_present,
        "latest_attempt_failed_or_refused": cost_forecast_attempt_failed,
        "binding_current": cost_forecast_binding_current,
        "input_coverage_complete": cost_forecast_input_coverage_complete,
        "price_coverage_complete": cost_forecast_price_coverage_complete,
        "evidence_consistent": cost_forecast_evidence_consistent,
        "stop_active": cost_forecast_stop_active,
        "all_dimensions_within": cost_forecast_all_dimensions_within,
        "approval_required": cost_forecast_approval_required,
        "gate_eligible": cost_forecast_gate_eligible,
        "dimension_count": cost_forecast_dimension_count,
        "forecast_utc_date": cost_forecast_utc_date,
        "execution_provenance": cost_forecast_execution_provenance,
    }
    _gate9_structurally_consistent = (
        cost_forecast_evidence_consistent
        and cost_forecast_history_count >= 0
        and cost_forecast_dimension_count == 6
        and cost_forecast_execution_provenance == "system_derived_cost_forecast"
        and not (
            cost_forecast_gate_eligible
            and (
                cost_forecast_stop_active
                or not cost_forecast_all_dimensions_within
                or cost_forecast_approval_required
            )
        )
    )
    if not cost_forecast_scope_resolved:
        gate9 = _insufficient(9, _gate9_name, "no_current_release_scope", _gate9_ctx)
    elif not cost_forecast_policy_present:
        gate9 = _insufficient(9, _gate9_name, "no_current_structured_cost_policy", _gate9_ctx)
    elif not cost_forecast_policy_valid:
        gate9 = _insufficient(9, _gate9_name, "cost_policy_invalid", _gate9_ctx)
    elif not cost_forecast_budget_present:
        gate9 = _insufficient(9, _gate9_name, "no_current_cost_budget", _gate9_ctx)
    elif not cost_forecast_budget_valid:
        gate9 = _insufficient(9, _gate9_name, "cost_budget_invalid", _gate9_ctx)
    elif cost_forecast_history_count <= 0:
        gate9 = _insufficient(9, _gate9_name, "no_cost_history", _gate9_ctx)
    elif not cost_forecast_run_present:
        gate9 = _insufficient(9, _gate9_name, "cost_forecast_not_run", _gate9_ctx)
    elif cost_forecast_attempt_failed:
        gate9 = _insufficient(
            9, _gate9_name, "cost_forecast_latest_attempt_failed_or_refused", _gate9_ctx
        )
    elif not cost_forecast_binding_current:
        gate9 = _insufficient(9, _gate9_name, "cost_forecast_binding_stale", _gate9_ctx)
    elif not cost_forecast_input_coverage_complete or not cost_forecast_price_coverage_complete:
        gate9 = _insufficient(
            9, _gate9_name, "cost_forecast_input_or_price_coverage_incomplete", _gate9_ctx
        )
    elif not _gate9_structurally_consistent:
        gate9 = _insufficient(9, _gate9_name, "cost_forecast_evidence_inconsistent", _gate9_ctx)
    elif cost_forecast_stop_active:
        gate9 = _insufficient(9, _gate9_name, "cost_stop_active", _gate9_ctx)
    elif not cost_forecast_all_dimensions_within:
        gate9 = _insufficient(
            9, _gate9_name, "cost_forecast_limit_reached_or_exceeded", _gate9_ctx
        )
    elif cost_forecast_approval_required:
        gate9 = _insufficient(9, _gate9_name, "cost_forecast_requires_approval", _gate9_ctx)
    elif not cost_forecast_gate_eligible:
        gate9 = _insufficient(9, _gate9_name, "cost_forecast_evidence_inconsistent", _gate9_ctx)
    else:
        gate9 = GateResult(
            9,
            _gate9_name,
            STATUS_PASSED,
            "passed:system_derived_cost_forecast_within_recorded_policy",
            _gate9_ctx,
        )
    gate12 = _insufficient(
        12,
        "production_deploy_preapproved_under_conditions",
        "a5_policy_primitive_but_no_preapproved_release"
        if autonomy_policy_present
        else "no_a5_preapproved_release",
    )
    # Slice 50: a verdict is a bounded, system-derived disposition over one exact frozen candidate
    # and re-audited Slice-49 core.  It does not prove issue-set completeness or authorize go-live.
    gate7_counts_consistent = (
        all(
            count >= 0
            for count in (
                bound_issue_count,
                bound_trusted_issue_count,
                bound_untrusted_issue_count,
                bound_finding_bridge_issue_count,
                bound_security_bridge_issue_count,
                bound_shortcut_bridge_issue_count,
                bound_accepted_issue_count,
                bound_release_consistent_accepted_issue_count,
                release_bound_active_risk_acceptance_count,
                legacy_unbound_risk_acceptance_count,
            )
        )
        and bound_trusted_issue_count + bound_untrusted_issue_count == bound_issue_count
        and bound_finding_bridge_issue_count == bound_trusted_issue_count
        and bound_security_bridge_issue_count + bound_shortcut_bridge_issue_count
        == bound_finding_bridge_issue_count
        and bound_release_consistent_accepted_issue_count <= bound_accepted_issue_count
        and bound_accepted_issue_count <= bound_issue_count
    )
    _gate7_name = "approved_risk_acceptance_records"
    _gate7_ctx = {
        "active_risk_acceptance_count": active_risk_acceptance_count,
        "open_issue_count": open_issue_count,
        "open_blocking_issue_count": open_blocking_issue_count,
        "open_unaccepted_blocking_issue_count": open_unaccepted_blocking_issue_count,
        "frozen_release_candidate_count": frozen_release_candidate_count,
        "latest_frozen_release_candidate_id": latest_frozen_release_candidate_id,
        "latest_frozen_release_ref": latest_frozen_release_ref,
        "bound_open_issue_count": bound_open_issue_count,
        "bound_open_blocking_issue_count": bound_open_blocking_issue_count,
        "bound_open_unaccepted_blocking_issue_count": bound_open_unaccepted_blocking_issue_count,
        "bound_issue_count": bound_issue_count,
        "bound_trusted_issue_count": bound_trusted_issue_count,
        "bound_untrusted_issue_count": bound_untrusted_issue_count,
        "bound_finding_bridge_issue_count": bound_finding_bridge_issue_count,
        "bound_security_bridge_issue_count": bound_security_bridge_issue_count,
        "bound_shortcut_bridge_issue_count": bound_shortcut_bridge_issue_count,
        "bound_accepted_issue_count": bound_accepted_issue_count,
        "bound_release_consistent_accepted_issue_count": (
            bound_release_consistent_accepted_issue_count
        ),
        "release_bound_active_risk_acceptance_count": (release_bound_active_risk_acceptance_count),
        "legacy_unbound_risk_acceptance_count": legacy_unbound_risk_acceptance_count,
        "issue_provenance_consistent": gate7_counts_consistent,
        "evidence_core_present": release_evidence_core_present,
        "evidence_core_audited": release_evidence_core_audited,
        "verdict_run_present": release_verdict_run_present,
        "verdict_attempt_failed": release_verdict_attempt_failed,
        "verdict_binding_current": release_verdict_binding_current,
        "verdict_evidence_consistent": release_verdict_evidence_consistent,
        "spec_verdict": release_verdict_spec_verdict,
        "verdict_reason_code": release_verdict_reason_code,
        "verdict_execution_provenance": release_verdict_execution_provenance,
        "decision_scope": release_verdict_decision_scope,
        "verdict_gate_eligible": release_verdict_gate_eligible,
    }
    _verdict_shape_valid = (
        release_verdict_decision_scope == "known_bound_issue_disposition"
        and release_verdict_execution_provenance == "system_derived_release_verdict"
        and release_verdict_spec_verdict
        in {
            "passed",
            "passed_with_limitations",
            "failed_blocking_issue",
            "failed_missing_evidence",
            "requires_human_decision",
            "not_applicable",
        }
    )
    if frozen_release_candidate_count <= 0:
        gate7 = _insufficient(
            7,
            _gate7_name,
            "insufficient_evidence:no_issue_provenance_or_release_binding",
            _gate7_ctx,
        )
    elif not release_evidence_core_present or not release_evidence_core_audited:
        gate7 = _insufficient(
            7, _gate7_name, "insufficient_evidence:no_audited_release_evidence_core", _gate7_ctx
        )
    elif release_verdict_run_present and (
        release_verdict_attempt_failed
        or not release_verdict_binding_current
        or not release_verdict_evidence_consistent
        or not gate7_counts_consistent
        or (release_verdict_spec_verdict is not None and not _verdict_shape_valid)
    ):
        gate7 = _insufficient(
            7,
            _gate7_name,
            "insufficient_evidence:release_verdict_evidence_incomplete_or_stale",
            _gate7_ctx,
        )
    elif not release_verdict_run_present or release_verdict_spec_verdict is None:
        gate7 = _insufficient(
            7,
            _gate7_name,
            "insufficient_evidence:verified_known_issue_set_but_no_release_verdict",
            _gate7_ctx,
        )
    elif release_verdict_spec_verdict == "failed_missing_evidence":
        gate7 = _insufficient(
            7,
            _gate7_name,
            "insufficient_evidence:release_verdict_failed_missing_evidence",
            _gate7_ctx,
        )
    elif release_verdict_spec_verdict == "failed_blocking_issue":
        gate7 = _insufficient(
            7,
            _gate7_name,
            "insufficient_evidence:release_verdict_failed_blocking_issue",
            _gate7_ctx,
        )
    elif release_verdict_spec_verdict == "requires_human_decision":
        gate7 = _insufficient(
            7,
            _gate7_name,
            "insufficient_evidence:release_verdict_requires_human_decision",
            _gate7_ctx,
        )
    elif release_verdict_spec_verdict == "not_applicable":
        gate7 = _insufficient(
            7, _gate7_name, "insufficient_evidence:release_verdict_not_applicable", _gate7_ctx
        )
    elif not release_verdict_gate_eligible:
        gate7 = _insufficient(
            7,
            _gate7_name,
            "insufficient_evidence:release_limitations_not_authoritatively_accepted",
            _gate7_ctx,
        )
    else:
        gate7 = GateResult(
            7,
            _gate7_name,
            STATUS_PASSED,
            "passed:bound_release_issue_disposition_verdict_current",
            _gate7_ctx,
        )

    # Slice 44: coverage proves that all five mandatory scanner categories ran for one exact
    # connector-observed repo/commit/manifest binding. It cannot prove universal absence. Any open
    # critical security finding remains blocking regardless of whether it came from a scan.
    _gate5_name = "no_unaccepted_critical_security_findings"
    _gate5_counts_consistent = (
        security_scan_mandatory_category_count == 5
        and security_scan_completed_category_count >= 0
        and security_scan_failed_category_count >= 0
        and security_scan_completed_category_count + security_scan_failed_category_count
        == security_scan_mandatory_category_count
        and security_scan_finding_count >= 0
        and open_security_finding_count >= 0
        and open_unaccepted_critical_security_finding_count >= 0
        and open_unaccepted_critical_security_finding_count <= open_security_finding_count
        and (
            not security_scan_coverage_complete
            or (
                security_scan_completed_category_count == security_scan_mandatory_category_count
                and security_scan_failed_category_count == 0
            )
        )
    )
    _gate5_evidence_consistent = (
        security_scan_evidence_consistent and _gate5_counts_consistent
    )
    _gate5_ctx = {
        "security_scan_scope_resolved": security_scan_scope_resolved,
        "security_scan_binding_resolved": security_scan_binding_resolved,
        "security_scan_run_present": security_scan_run_present,
        "security_scan_artifact_trusted": security_scan_artifact_trusted,
        "security_scan_execution_failed": security_scan_execution_failed,
        "security_scan_coverage_complete": security_scan_coverage_complete,
        "security_scan_evidence_consistent": _gate5_evidence_consistent,
        "security_scan_mandatory_category_count": security_scan_mandatory_category_count,
        "security_scan_completed_category_count": security_scan_completed_category_count,
        "security_scan_failed_category_count": security_scan_failed_category_count,
        "security_scan_finding_count": security_scan_finding_count,
        "open_security_finding_count": open_security_finding_count,
        "open_unaccepted_critical_security_finding_count": (
            open_unaccepted_critical_security_finding_count
        ),
    }
    if not security_scan_scope_resolved:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:security_scan_scope_unresolved", _gate5_ctx
        )
    elif not security_scan_binding_resolved:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:security_scan_binding_unresolved", _gate5_ctx
        )
    elif not security_scan_run_present:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:security_scan_not_executed", _gate5_ctx
        )
    elif not security_scan_artifact_trusted:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:security_scan_observed_unverified", _gate5_ctx
        )
    elif security_scan_execution_failed:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:security_scan_execution_failed", _gate5_ctx
        )
    elif not security_scan_coverage_complete:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:security_scan_coverage_incomplete", _gate5_ctx
        )
    elif not _gate5_evidence_consistent:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:security_scan_evidence_inconsistent", _gate5_ctx
        )
    elif open_unaccepted_critical_security_finding_count > 0:
        gate5 = _insufficient(
            5, _gate5_name, "insufficient_evidence:critical_security_findings_open", _gate5_ctx
        )
    else:
        gate5 = GateResult(
            5,
            _gate5_name,
            STATUS_PASSED,
            "passed:no_unaccepted_critical_security_findings_verified",
            _gate5_ctx,
        )
    # Slice 45: all twelve mandatory §13.4 categories require trusted exact-binding hybrid
    # execution and DB-provable registered-builder/reviewer separation. Any open critical
    # shortcut finding blocks regardless of provenance.
    _gate6_name = "no_unaccepted_critical_shortcut_findings"
    _gate6_counts_consistent = (
        shortcut_review_mandatory_category_count == 12
        and shortcut_review_completed_category_count >= 0
        and shortcut_review_failed_category_count >= 0
        and shortcut_review_reviewer_count >= 0
        and shortcut_review_finding_count >= 0
        and open_shortcut_finding_count >= 0
        and open_unaccepted_critical_shortcut_finding_count >= 0
        and open_unaccepted_critical_shortcut_finding_count <= open_shortcut_finding_count
        and (
            not shortcut_review_coverage_complete
            or (
                shortcut_review_completed_category_count
                == shortcut_review_mandatory_category_count
                and shortcut_review_failed_category_count == 0
                and shortcut_review_reviewer_count >= 2
            )
        )
    )
    _gate6_evidence_consistent = (
        shortcut_review_evidence_consistent and _gate6_counts_consistent
    )
    _gate6_ctx = {
        "shortcut_review_scope_resolved": shortcut_review_scope_resolved,
        "shortcut_review_binding_resolved": shortcut_review_binding_resolved,
        "shortcut_review_run_present": shortcut_review_run_present,
        "shortcut_review_corpus_trusted": shortcut_review_corpus_trusted,
        "shortcut_review_execution_failed": shortcut_review_execution_failed,
        "shortcut_review_independence_resolved": shortcut_review_independence_resolved,
        "shortcut_review_coverage_complete": shortcut_review_coverage_complete,
        "shortcut_review_evidence_consistent": _gate6_evidence_consistent,
        "shortcut_review_mandatory_category_count": shortcut_review_mandatory_category_count,
        "shortcut_review_completed_category_count": shortcut_review_completed_category_count,
        "shortcut_review_failed_category_count": shortcut_review_failed_category_count,
        "shortcut_review_reviewer_count": shortcut_review_reviewer_count,
        "shortcut_review_finding_count": shortcut_review_finding_count,
        "open_shortcut_finding_count": open_shortcut_finding_count,
        "open_unaccepted_critical_shortcut_finding_count": (
            open_unaccepted_critical_shortcut_finding_count
        ),
    }
    if not shortcut_review_scope_resolved:
        gate6 = _insufficient(
            6, _gate6_name, "insufficient_evidence:shortcut_review_scope_unresolved", _gate6_ctx
        )
    elif not shortcut_review_binding_resolved:
        gate6 = _insufficient(
            6,
            _gate6_name,
            "insufficient_evidence:shortcut_review_binding_unresolved",
            _gate6_ctx,
        )
    elif not shortcut_review_run_present:
        gate6 = _insufficient(
            6, _gate6_name, "insufficient_evidence:shortcut_review_not_executed", _gate6_ctx
        )
    elif not shortcut_review_corpus_trusted:
        gate6 = _insufficient(
            6,
            _gate6_name,
            "insufficient_evidence:shortcut_review_observed_unverified",
            _gate6_ctx,
        )
    elif shortcut_review_execution_failed:
        gate6 = _insufficient(
            6,
            _gate6_name,
            "insufficient_evidence:shortcut_review_execution_failed",
            _gate6_ctx,
        )
    elif not shortcut_review_independence_resolved:
        gate6 = _insufficient(
            6,
            _gate6_name,
            "insufficient_evidence:shortcut_review_independence_unproven",
            _gate6_ctx,
        )
    elif not shortcut_review_coverage_complete:
        gate6 = _insufficient(
            6,
            _gate6_name,
            "insufficient_evidence:shortcut_review_coverage_incomplete",
            _gate6_ctx,
        )
    elif not _gate6_evidence_consistent:
        gate6 = _insufficient(
            6,
            _gate6_name,
            "insufficient_evidence:shortcut_review_evidence_inconsistent",
            _gate6_ctx,
        )
    elif open_unaccepted_critical_shortcut_finding_count > 0:
        gate6 = _insufficient(
            6,
            _gate6_name,
            "insufficient_evidence:critical_shortcut_findings_open",
            _gate6_ctx,
        )
    else:
        gate6 = GateResult(
            6,
            _gate6_name,
            STATUS_PASSED,
            "passed:no_unaccepted_critical_shortcut_findings_verified",
            _gate6_ctx,
        )

    # Slice 28: gate #3 is PASS-capable. The "latest" inputs are the snapshot for the CURRENTLY
    # DECLARED repo/branch (B1-cont — bound by the repo at evaluation time); the ladder is keyed ONLY
    # off that latest snapshot. A 200-verified, active, fresh snapshot PASSES; everything else fails
    # closed. Counts are context only. The report carries branch_protection_repo_bound, never repo_ref.
    _gate3_name = "branch_protection_and_required_checks_active"
    _gate3_ctx = {
        "branch_protection_repo_bound": branch_protection_repo_bound,
        "branch_protection_snapshot_count": branch_protection_snapshot_count,
        "connector_verified_branch_protection_count": connector_verified_branch_protection_count,
        "latest_branch_protection_provenance": latest_branch_protection_provenance,
        "latest_branch_protection_enabled": latest_branch_protection_enabled,
        "latest_required_status_check_count": latest_required_status_check_count,
    }
    if not branch_protection_repo_bound:
        gate3 = _insufficient(3, _gate3_name, "branch_protection_repo_unbound", _gate3_ctx)
    elif latest_branch_protection_provenance is None:
        gate3 = _insufficient(3, _gate3_name, "no_branch_protection_evidence", _gate3_ctx)
    elif latest_branch_protection_provenance != "connector_verified":
        gate3 = _insufficient(3, _gate3_name, "branch_protection_observed_unverified", _gate3_ctx)
    elif not latest_branch_protection_fresh:
        gate3 = _insufficient(3, _gate3_name, "branch_protection_evidence_stale", _gate3_ctx)
    elif not gate3_protection_sufficient(
        protection_enabled=latest_branch_protection_enabled,
        required_pull_request_reviews=latest_branch_protection_required_pull_request_reviews,
        required_status_check_count=latest_required_status_check_count,
    ):
        gate3 = _insufficient(3, _gate3_name, "branch_protection_insufficient", _gate3_ctx)
    else:
        gate3 = GateResult(
            3,
            _gate3_name,
            STATUS_PASSED,
            "branch_protection_and_required_checks_active_verified",
            _gate3_ctx,
        )

    # Slice 31: gate #11 is PASS-capable. The "latest" inputs are the snapshot for the project's
    # CURRENTLY DECLARED monitoring status_url (B2 — bound at evaluation time); the ladder is keyed
    # ONLY off that latest snapshot. A connector_verified + valid-read + active + fresh snapshot
    # PASSES; everything else fails closed. **Honesty (B4):** an unreadable verified+fresh snapshot is
    # ``monitoring_evidence_unreadable`` — NEVER "inactive". Context carries the read-state (no URL/host).
    _gate11_name = "monitoring_and_alerts_active"
    _gate11_ctx = {
        "monitoring_bound": monitoring_bound,
        "latest_monitoring_provenance": latest_monitoring_provenance,
        "latest_monitoring_response_valid": latest_monitoring_response_valid,
        "latest_monitoring_overall_active": latest_monitoring_overall_active,
        "latest_monitoring_failure_kind": latest_monitoring_failure_kind,
    }
    if not monitoring_bound:
        gate11 = _insufficient(11, _gate11_name, "no_monitoring_declaration", _gate11_ctx)
    elif latest_monitoring_provenance is None:
        gate11 = _insufficient(11, _gate11_name, "monitoring_declared_but_no_evidence", _gate11_ctx)
    elif latest_monitoring_provenance != "connector_verified":
        gate11 = _insufficient(11, _gate11_name, "monitoring_observed_unverified", _gate11_ctx)
    elif not latest_monitoring_fresh:
        gate11 = _insufficient(11, _gate11_name, "monitoring_evidence_stale", _gate11_ctx)
    elif not latest_monitoring_response_valid:
        # B4: the provider was unreadable — do NOT claim alerts are inactive.
        gate11 = _insufficient(11, _gate11_name, "monitoring_evidence_unreadable", _gate11_ctx)
    elif not latest_monitoring_overall_active:
        gate11 = _insufficient(11, _gate11_name, "monitoring_or_alerts_inactive", _gate11_ctx)
    else:
        gate11 = GateResult(
            11, _gate11_name, STATUS_PASSED, "monitoring_and_alerts_active_verified", _gate11_ctx
        )

    # Slice 43: Appendix-B gate #4, conservatively scoped to ALL structurally valid canonical
    # project test_oracle artifacts (OD-43-1). Counts are safe metadata only. A pass requires a
    # non-empty scope and complete exact-repo+commit latest-wins coverage; no vacuous truth.
    _gate4_name = "all_critical_test_oracles_pass"
    _gate4_ctx = {
        "scope_resolved": test_oracle_scope_resolved,
        "scoped_oracle_count": test_oracle_scope_count,
        "valid_definition_count": test_oracle_valid_definition_count,
        "invalid_definition_count": test_oracle_invalid_definition_count,
        "binding_present": test_oracle_binding_present,
        "unrun_count": test_oracle_unrun_count,
        "untrusted_count": test_oracle_untrusted_count,
        "incomplete_count": test_oracle_incomplete_count,
        "execution_failed_count": test_oracle_execution_failed_count,
        "judgment_control_failed_count": test_oracle_judgment_control_failed_count,
        "failed_count": test_oracle_failed_count,
        "passed_count": test_oracle_passed_count,
    }
    if not test_oracle_scope_resolved:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_scope_unresolved",
            _gate4_ctx,
        )
    elif test_oracle_scope_count <= 0:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:no_proven_critical_oracle_scope",
            _gate4_ctx,
        )
    elif (
        test_oracle_valid_definition_count < 0
        or test_oracle_invalid_definition_count < 0
        or test_oracle_valid_definition_count + test_oracle_invalid_definition_count
        != test_oracle_scope_count
    ):
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_evidence_inconsistent",
            _gate4_ctx,
        )
    elif test_oracle_invalid_definition_count > 0:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_feature_without_valid_oracle",
            _gate4_ctx,
        )
    elif not test_oracle_binding_present:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_binding_unresolved",
            _gate4_ctx,
        )
    elif any(
        count < 0
        for count in (
            test_oracle_unrun_count,
            test_oracle_untrusted_count,
            test_oracle_incomplete_count,
            test_oracle_execution_failed_count,
            test_oracle_judgment_control_failed_count,
            test_oracle_failed_count,
            test_oracle_passed_count,
        )
    ) or (
        test_oracle_unrun_count
        + test_oracle_untrusted_count
        + test_oracle_incomplete_count
        + test_oracle_execution_failed_count
        + test_oracle_judgment_control_failed_count
        + test_oracle_failed_count
        + test_oracle_passed_count
        != test_oracle_valid_definition_count
    ):
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_evidence_inconsistent",
            _gate4_ctx,
        )
    elif test_oracle_unrun_count > 0:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_not_executed",
            _gate4_ctx,
        )
    elif test_oracle_untrusted_count > 0:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_observation_untrusted",
            _gate4_ctx,
        )
    elif test_oracle_incomplete_count > 0:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_incomplete",
            _gate4_ctx,
        )
    elif test_oracle_execution_failed_count > 0:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_execution_failed",
            _gate4_ctx,
        )
    elif test_oracle_judgment_control_failed_count > 0:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_judgment_controls_failed",
            _gate4_ctx,
        )
    elif test_oracle_failed_count > 0 or test_oracle_passed_count != test_oracle_scope_count:
        gate4 = _insufficient(
            4,
            _gate4_name,
            "insufficient_evidence:critical_oracle_failed",
            _gate4_ctx,
        )
    else:
        gate4 = GateResult(
            4,
            _gate4_name,
            STATUS_PASSED,
            "passed:all_critical_test_oracles_pass_verified",
            _gate4_ctx,
        )

    # Gate #10 — Slice 52 exact release/core/target-bound connector-observed staging rollback drill.
    gate10_context = {
        "scope_resolved": rollback_scope_resolved,
        "core_present": rollback_core_present,
        "core_reaudited": rollback_core_reaudited,
        "repo_binding_agreed": rollback_repo_binding_agreed,
        "staging_target_valid": rollback_staging_target_valid,
        "staging_snapshot_present": rollback_staging_snapshot_present,
        "staging_snapshot_available": rollback_staging_snapshot_available,
        "staging_snapshot_fresh": rollback_staging_snapshot_fresh,
        "run_present": rollback_run_present,
        "attempt_failed": rollback_attempt_failed,
        "artifact_trusted": rollback_artifact_trusted,
        "binding_current": rollback_binding_current,
        "phase_coverage_complete": rollback_phase_coverage_complete,
        "evidence_consistent": rollback_evidence_consistent,
        "drill_passed": rollback_drill_passed,
        "gate_eligible": rollback_gate_eligible,
        "phase_count": rollback_phase_count,
        "execution_observation": rollback_execution_observation,
    }
    if not rollback_scope_resolved:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:no_current_frozen_release_candidate",
            gate10_context,
        )
    elif not rollback_core_present:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:no_complete_reauditable_evidence_core",
            gate10_context,
        )
    elif not rollback_core_reaudited:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:release_core_reaudit_failed",
            gate10_context,
        )
    elif not rollback_repo_binding_agreed:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:release_repo_commit_binding_missing_or_disagreed",
            gate10_context,
        )
    elif not rollback_staging_target_valid:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:staging_target_declaration_missing_or_invalid",
            gate10_context,
        )
    elif not rollback_staging_snapshot_present:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:no_current_connector_verified_staging_target",
            gate10_context,
        )
    elif not rollback_staging_snapshot_available or not rollback_staging_snapshot_fresh:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:staging_target_unavailable_or_stale",
            gate10_context,
        )
    elif not rollback_run_present:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:rollback_verification_not_run_for_current_binding",
            gate10_context,
        )
    elif rollback_attempt_failed:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:latest_rollback_attempt_failed_or_refused",
            gate10_context,
        )
    elif not rollback_artifact_trusted or rollback_execution_observation != "connector_observed_ci":
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:rollback_artifact_provenance_untrusted",
            gate10_context,
        )
    elif not rollback_binding_current:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:rollback_binding_stale_or_inconsistent",
            gate10_context,
        )
    elif not rollback_phase_coverage_complete or rollback_phase_count != 5:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:rollback_phase_coverage_incomplete",
            gate10_context,
        )
    elif not rollback_evidence_consistent:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:rollback_phase_evidence_inconsistent",
            gate10_context,
        )
    elif not rollback_drill_passed or not rollback_gate_eligible:
        gate10 = _insufficient(
            10,
            "rollback_verified",
            "insufficient_evidence:rollback_drill_failed",
            gate10_context,
        )
    else:
        gate10 = GateResult(
            10,
            "rollback_verified",
            STATUS_PASSED,
            "passed:connector_observed_staging_rollback_drill_verified",
            gate10_context,
        )

    # Gates with no evidence source at all (await Phase 5/6 subsystems).
    gates = [
        gate1,
        gate2,
        gate3,
        gate4,
        gate5,
        gate6,
        gate7,
        gate8,
        gate9,
        gate10,
        gate11,
        gate12,
        _no_source(13, "emergency_stop_rollback_authority", "emergency_stop"),
    ]
    gates.sort(key=lambda g: g.number)
    return ProductionAutonomyReport(project_id=str(project_id), gates=gates)
