"""A5 production-autonomy evaluator skeleton (Slice 21..26 + 28 + 30 + 31, spec §5.1 + App. B) — pure.

Scores the **13 Appendix-B A5 gates** and emits a ``ProductionAutonomyReport`` that is **fail-closed
and non-authorizing**. Every gate carries ``status``, ``reason``, and a ``context`` dict
(default ``{}``, serialized on every gate):

- **Gate #1 (R5 intake complete)** passes at ``R5``; **gate #2 (deployment target, Slice 30)**, **gate #3
  (branch protection, Slice 28)**, and **gate #11 (monitoring/alerts, Slice 31)** are **PASS-capable**
  — each via a binding-bound, latest-wins, connector_verified + fresh ladder (see below).
- Gates #7, #9, and #12 remain partial-context ``insufficient_evidence`` gates:
  the system has a *primitive* (
  **Slice-22 risk-acceptance store, #7**; AC provenance;
  cost stop-decision; A5 policy enum + approval engine) but **no production-autonomy evidence**, so
  they never pass. #7 (**Slice-24 open-issue +
  Slice-25 release-binding stores**) is ``insufficient_evidence`` — its reason narrows from
  ``no_issue_provenance_or_release_binding`` to ``no_issue_provenance`` once a FROZEN release
  candidate exists (the release-binding half is satisfied), but issue provenance/completeness still
  does not exist, so it never passes. Their counts are context only and never authorize.
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

``a5_satisfied`` is true only if **all 13** gates pass (still impossible with remaining unmet gates even
when #1/#2/#3/#4/#11 pass). ``can_go_live_autonomously`` is **hard-false always** — go-live
additionally requires a request-authenticated, verified A5 pre-approval that does not exist yet. This
module never authorizes production: it only reports the gate structure honestly. ``ruleset_version`` is
``slice46.v1``. Gate #8 is PASS-capable only through complete DB-bound acceptance-authorship evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.release.ci_evidence import gate3_protection_sufficient

A5_RULESET_VERSION = "slice46.v1"

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
    gate9 = _insufficient(
        9,
        "cost_forecast_within_policy",
        "cost_stop_decision_only_no_forecast"
        if cost_policy_present
        else "no_cost_policy_and_no_forecast",
    )
    gate12 = _insufficient(
        12,
        "production_deploy_preapproved_under_conditions",
        "a5_policy_primitive_but_no_preapproved_release"
        if autonomy_policy_present
        else "no_a5_preapproved_release",
    )
    # Slice 24 added the open-issue store; Slice 25 adds the release-binding store. When a FROZEN
    # release candidate exists, the *release-binding* half is satisfied, so the reason narrows from
    # no_issue_provenance_or_release_binding → no_issue_provenance. The *issue-provenance* half
    # (reviewer/CI/verifier completeness) still does not exist, so gate #7 NEVER passes — the counts
    # are context only and never flip the status.
    gate7_reason = (
        "no_issue_provenance"
        if frozen_release_candidate_count > 0
        else "no_issue_provenance_or_release_binding"
    )
    gate7 = _insufficient(
        7,
        "approved_risk_acceptance_records",
        gate7_reason,
        {
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
        },
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
        _no_source(10, "rollback_verified", "rollback_verification"),
        gate11,
        gate12,
        _no_source(13, "emergency_stop_rollback_authority", "emergency_stop"),
    ]
    gates.sort(key=lambda g: g.number)
    return ProductionAutonomyReport(project_id=str(project_id), gates=gates)
