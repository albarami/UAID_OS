"""A5 production-autonomy evaluator skeleton (Slice 21, spec §5.1 + Appendix B) — pure, no I/O, no LLM.

Scores the **13 Appendix-B A5 gates** and emits a ``ProductionAutonomyReport`` that is **fail-closed
and non-authorizing**:

- **Only gate #1 (R5 intake complete)** can ``pass`` today — and only when readiness is ``R5``.
- The four partial-context gates (#2, #8, #9, #12) return ``insufficient_evidence``: the system has a
  *primitive* (an environment declaration, AC provenance, a cost stop-decision, the A5 policy enum +
  approval engine) but **no production-autonomy evidence**, so they never pass.
- The eight sourceless gates (#3, #4, #5, #6, #7, #10, #11, #13) return
  ``no_evidence_source:<subsystem>`` — they await Phase 3/5/6 evidence subsystems.

``a5_satisfied`` is true only if **all 13** gates pass (impossible this slice).
``can_go_live_autonomously`` is **hard-false always** — go-live additionally requires a
request-authenticated, verified A5 pre-approval that does not exist yet. This module never authorizes
production: it only reports the gate structure honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

A5_RULESET_VERSION = "slice21.v1"

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

    def to_dict(self) -> dict:
        return {"number": self.number, "gate": self.gate, "status": self.status, "reason": self.reason}


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


def _insufficient(number: int, gate: str, reason: str) -> GateResult:
    return GateResult(number, gate, STATUS_INSUFFICIENT, reason)


def evaluate_production_autonomy(
    project_id,
    *,
    readiness_level: str,
    autonomy_policy_present: bool = False,
    cost_policy_present: bool = False,
    environments_declared: bool = False,
    generated_ac_provenance_ok: bool = False,
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
        2, "production_deployment_target_available",
        "environments_declared_but_no_live_target" if environments_declared
        else "no_environment_declaration_and_no_live_target",
    )
    gate8 = _insufficient(
        8, "no_unapproved_generated_ac_in_critical_gates",
        "ac_provenance_present_but_no_release_gate_binding" if generated_ac_provenance_ok
        else "ac_provenance_context_only_no_release_gate_binding",
    )
    gate9 = _insufficient(
        9, "cost_forecast_within_policy",
        "cost_stop_decision_only_no_forecast" if cost_policy_present
        else "no_cost_policy_and_no_forecast",
    )
    gate12 = _insufficient(
        12, "production_deploy_preapproved_under_conditions",
        "a5_policy_primitive_but_no_preapproved_release" if autonomy_policy_present
        else "no_a5_preapproved_release",
    )

    # Gates with no evidence source at all (await Phase 3/5/6 subsystems).
    gates = [
        gate1,
        gate2,
        _no_source(3, "branch_protection_and_required_checks_active", "ci_branch_protection"),
        _no_source(4, "all_critical_test_oracles_pass", "test_oracle_execution"),
        _no_source(5, "no_unaccepted_critical_security_findings", "security_findings"),
        _no_source(6, "no_unaccepted_critical_shortcut_findings", "shortcut_findings"),
        _no_source(7, "approved_risk_acceptance_records", "risk_acceptance_records"),
        gate8,
        gate9,
        _no_source(10, "rollback_verified", "rollback_verification"),
        _no_source(11, "monitoring_and_alerts_active", "monitoring"),
        gate12,
        _no_source(13, "emergency_stop_rollback_authority", "emergency_stop"),
    ]
    gates.sort(key=lambda g: g.number)
    return ProductionAutonomyReport(project_id=str(project_id), gates=gates)
