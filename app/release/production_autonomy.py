"""A5 production-autonomy evaluator skeleton (Slice 21 + 22 + 23 + 24 + 25, spec §5.1 + App. B) — pure.

Scores the **13 Appendix-B A5 gates** and emits a ``ProductionAutonomyReport`` that is **fail-closed
and non-authorizing**. Every gate carries ``status``, ``reason``, and a ``context`` dict
(default ``{}``, serialized on every gate):

- **Only gate #1 (R5 intake complete)** can ``pass`` today — and only when readiness is ``R5``.
- The **seven** partial-context gates (#2, #5, #6, #7, #8, #9, #12) return ``insufficient_evidence``:
  the system has a *primitive* (env declaration; **Slice-23 security findings store, #5**;
  **Slice-23 shortcut findings store, #6**; **Slice-22 risk-acceptance store, #7**; AC provenance;
  cost stop-decision; A5 policy enum + approval engine) but **no production-autonomy evidence**, so
  they never pass. #5/#6 are ``insufficient_evidence:no_finding_provenance_or_scan_source`` (a store
  can't prove absence of findings without authoritative scan coverage); #7 (**Slice-24 open-issue +
  Slice-25 release-binding stores**) is ``insufficient_evidence`` — its reason narrows from
  ``no_issue_provenance_or_release_binding`` to ``no_issue_provenance`` once a FROZEN release
  candidate exists (the release-binding half is satisfied), but issue provenance/completeness still
  does not exist, so it never passes. Their counts are context only and never authorize.
- **Slice 26 (#3 branch protection):** the ``branch_protection_snapshots`` store now exists, so gate #3
  moves from ``no_evidence_source`` to ``insufficient_evidence`` (reason narrows from
  ``no_branch_protection_evidence`` to ``branch_protection_observed_unverified`` once a snapshot exists),
  with snapshot/verified counts as context. It **never passes** — Slice 26 writes only
  ``caller_supplied_unverified`` evidence and implements no PASS path (that lands with the real
  connector, Slice 28).
- The **four** sourceless gates (#4, #10, #11, #13) return ``no_evidence_source:<subsystem>`` —
  they await Phase 5/6 evidence subsystems.

``a5_satisfied`` is true only if **all 13** gates pass (impossible this slice).
``can_go_live_autonomously`` is **hard-false always** — go-live additionally requires a
request-authenticated, verified A5 pre-approval that does not exist yet. This module never authorizes
production: it only reports the gate structure honestly. ``ruleset_version`` is ``slice25.v1``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

A5_RULESET_VERSION = "slice26.v1"

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
    generated_ac_provenance_ok: bool = False,
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
) -> ProductionAutonomyReport:
    """Deterministic, fail-closed A5 evaluation. Context booleans are recorded as *context only* —
    they never flip a gate to ``passed`` (deny-by-default). Defaults are False (fail-closed)."""

    # Gate #1 — the only gate with a real, gate-passing source today (the R5 readiness auditor).
    if readiness_level == "R5":
        gate1 = GateResult(1, "r5_intake_complete", STATUS_PASSED, "readiness_r5")
    else:
        gate1 = _insufficient(1, "r5_intake_complete", f"readiness_below_r5:{readiness_level}")

    # Gates #2/#8/#9/#12 — partial *context* primitives exist, but no production-autonomy evidence.
    gate2 = _insufficient(
        2,
        "production_deployment_target_available",
        "environments_declared_but_no_live_target"
        if environments_declared
        else "no_environment_declaration_and_no_live_target",
    )
    gate8 = _insufficient(
        8,
        "no_unapproved_generated_ac_in_critical_gates",
        "ac_provenance_present_but_no_release_gate_binding"
        if generated_ac_provenance_ok
        else "ac_provenance_context_only_no_release_gate_binding",
    )
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

    # Slice 23: the security/shortcut finding STORES now exist, but authoritative scan coverage does
    # not — an empty store can't prove "no findings exist". Gates #5/#6 move from no_evidence_source
    # to insufficient_evidence; the counts are context only and never flip the status.
    gate5 = _insufficient(
        5,
        "no_unaccepted_critical_security_findings",
        "no_finding_provenance_or_scan_source",
        {
            "open_security_finding_count": open_security_finding_count,
            "open_unaccepted_critical_security_finding_count": open_unaccepted_critical_security_finding_count,
        },
    )
    gate6 = _insufficient(
        6,
        "no_unaccepted_critical_shortcut_findings",
        "no_finding_provenance_or_scan_source",
        {
            "open_shortcut_finding_count": open_shortcut_finding_count,
            "open_unaccepted_critical_shortcut_finding_count": open_unaccepted_critical_shortcut_finding_count,
        },
    )

    # Slice 26: the branch-protection snapshot store now exists, so gate #3 moves from
    # no_evidence_source to insufficient_evidence. It NEVER passes — Slice 26 writes only
    # caller_supplied_unverified evidence (the verified tier is unwritable) and implements no PASS
    # path (that lands with the real connector, Slice 28). The reason narrows once a snapshot exists.
    gate3_reason = (
        "no_branch_protection_evidence"
        if branch_protection_snapshot_count == 0
        else "branch_protection_observed_unverified"
    )
    gate3 = _insufficient(
        3,
        "branch_protection_and_required_checks_active",
        gate3_reason,
        {
            "branch_protection_snapshot_count": branch_protection_snapshot_count,
            "connector_verified_branch_protection_count": connector_verified_branch_protection_count,
            "latest_branch_protection_provenance": latest_branch_protection_provenance,
            # observed, UNVERIFIED — never an assertion that protection is on; never flips the gate.
            "latest_branch_protection_enabled": latest_branch_protection_enabled,
            "latest_required_status_check_count": latest_required_status_check_count,
        },
    )

    # Gates with no evidence source at all (await Phase 5/6 subsystems).
    gates = [
        gate1,
        gate2,
        gate3,
        _no_source(4, "all_critical_test_oracles_pass", "test_oracle_execution"),
        gate5,
        gate6,
        gate7,
        gate8,
        gate9,
        _no_source(10, "rollback_verified", "rollback_verification"),
        _no_source(11, "monitoring_and_alerts_active", "monitoring"),
        gate12,
        _no_source(13, "emergency_stop_rollback_authority", "emergency_stop"),
    ]
    gates.sort(key=lambda g: g.number)
    return ProductionAutonomyReport(project_id=str(project_id), gates=gates)
