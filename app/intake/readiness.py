"""Deterministic build-readiness auditor (Slice 12, §4.3/§4.4/§4.5).

Pure, no DB, no LLM. Reads a snapshot of canonical-intake artifacts and produces the
§4.5 intake validation report. **Fail-closed and honest:** the Slice-11 spine models
only requirement / acceptance_criterion / test_oracle / assumption, while §4.3 R3+
requires architecture/stack/data/workflows (and Appendix A R5 needs ~22 further
categories) that are **not modeled** — so this auditor is **capped at R2**, sets
``can_build_to_staging`` and ``can_go_live_autonomously`` to **false** with recorded
reasons, and enumerates everything it could not assess.

Parent-kind validation does NOT trust the DB FK alone (the triple-FK only pins a
parent to the same project+tenant, not its kind): an acceptance_criterion satisfies a
requirement only if its parent IS a requirement; a test_oracle satisfies an acceptance
criterion only if its parent IS that acceptance criterion. Orphan/wrong-kind links
become ``spine_gaps`` and never raise the readiness level.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

RULESET_VERSION = "slice12.v1"

READINESS_CAP = "R2"
READINESS_CAP_REASON = (
    "slice_12_current_spine_lacks_architecture_stack_data_workflow_environment_authority_categories"
)
CANNOT_STAGE_REASON = (
    "slice_12_spine_cannot_prove_technical_environment_tooling_prerequisites"
)
NO_GO_LIVE_REASONS = (
    "readiness_capped_below_R5",
    "production_deployment_authority_and_gates_not_modeled",
)

# Appendix A R5 categories the current spine does NOT model (Appendix A minus the
# spine-covered functional requirements / acceptance criteria / test oracles).
NOT_ASSESSED_CATEGORIES = (
    "product_purpose",
    "scope_and_out_of_scope",
    "users_and_roles",
    "permission_matrix",
    "core_workflows",
    "non_functional_requirements",
    "domain_pack",
    "data_model_and_contracts",
    "required_integrations",
    "environments",
    "secrets",
    "tool_access",
    "autonomy_policy_approved",
    "human_approval_policy_approved",
    "cost_policy_approved",
    "security_privacy_requirements",
    "go_live_checklist",
    "rollback_criteria",
    "monitoring_expectations",
    "risk_register",
    "prior_decisions_and_architecture_log",
    "production_authority",
)

_SAFE = "safe_assumption"


@dataclass(frozen=True)
class ArtifactView:
    """A DB-free view of one intake artifact (the repository maps ORM rows to these)."""

    id: uuid.UUID
    kind: str
    ref: str
    title: str
    parent_id: uuid.UUID | None = None
    classification: str | None = None


@dataclass
class ReadinessReport:
    project_id: str
    readiness_level: str
    can_build_to_staging: bool
    can_go_live_autonomously: bool
    production_authority_decision: str
    spine_gaps: list[dict] = field(default_factory=list)
    safe_assumptions: list[dict] = field(default_factory=list)
    blocked_assumptions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            # §4.5 keys
            "project_id": self.project_id,
            "readiness_level": self.readiness_level,
            "can_build_to_staging": self.can_build_to_staging,
            "can_go_live_autonomously": self.can_go_live_autonomously,
            "missing_for_go_live": [g["summary"] for g in self.spine_gaps]
            + list(NOT_ASSESSED_CATEGORIES),
            "safe_assumptions": self.safe_assumptions,
            "blocked_assumptions": self.blocked_assumptions,
            # deterministic extensions
            "readiness_cap": READINESS_CAP,
            "readiness_cap_reason": READINESS_CAP_REASON,
            "can_build_to_staging_reason": CANNOT_STAGE_REASON,
            "can_go_live_autonomously_reasons": list(NO_GO_LIVE_REASONS),
            "not_assessed_categories": list(NOT_ASSESSED_CATEGORIES),
            "spine_gaps": self.spine_gaps,
            "production_authority_decision": self.production_authority_decision,
            "ruleset_version": RULESET_VERSION,
        }

    @property
    def readiness_cap(self) -> str:
        return READINESS_CAP


def evaluate_readiness(
    project_id,
    artifacts: list[ArtifactView],
    *,
    production_authority_decision: str,
) -> ReadinessReport:
    """Deterministic, fail-closed readiness evaluation over the spine snapshot."""
    by_id = {a.id: a for a in artifacts}
    requirements = [a for a in artifacts if a.kind == "requirement"]
    acceptance = [a for a in artifacts if a.kind == "acceptance_criterion"]
    oracles = [a for a in artifacts if a.kind == "test_oracle"]
    assumptions = [a for a in artifacts if a.kind == "assumption"]

    def _parent(a: ArtifactView) -> ArtifactView | None:
        return by_id.get(a.parent_id) if a.parent_id is not None else None

    # An acceptance criterion is VALID only if its parent is a requirement.
    valid_ac = [a for a in acceptance if (p := _parent(a)) is not None and p.kind == "requirement"]
    covered_req_ids = {a.parent_id for a in valid_ac}
    # An oracle is VALID only if its parent is an acceptance criterion.
    valid_oracle = [
        o for o in oracles if (p := _parent(o)) is not None and p.kind == "acceptance_criterion"
    ]
    ac_with_oracle = {o.parent_id for o in valid_oracle}

    spine_gaps: list[dict] = []
    for r in requirements:
        if r.id not in covered_req_ids:
            spine_gaps.append(
                {"kind": "requirement_without_acceptance_criterion", "ref": r.ref,
                 "summary": f"requirement {r.ref} has no acceptance criterion"}
            )
    for a in acceptance:
        if a not in valid_ac:
            spine_gaps.append(
                {"kind": "acceptance_criterion_invalid_parent", "ref": a.ref,
                 "summary": f"acceptance criterion {a.ref} has a missing or wrong-kind parent "
                            "(must be a requirement)"}
            )
        elif a.id not in ac_with_oracle:
            spine_gaps.append(
                {"kind": "acceptance_criterion_without_test_oracle", "ref": a.ref,
                 "summary": f"acceptance criterion {a.ref} has no test oracle"}
            )
    for o in oracles:
        if o not in valid_oracle:
            spine_gaps.append(
                {"kind": "test_oracle_invalid_parent", "ref": o.ref,
                 "summary": f"test oracle {o.ref} has a missing or wrong-kind parent "
                            "(must be an acceptance criterion)"}
            )

    # Readiness level — fail-closed, capped at R2.
    if not requirements:
        level = "R0"
    elif not covered_req_ids:
        level = "R1"
    else:
        level = "R2"

    safe_assumptions = [
        {"ref": a.ref, "title": a.title, "classification": a.classification}
        for a in assumptions
        if a.classification == _SAFE
    ]
    # Fail-closed: anything not explicitly safe is reported as not-auto-safe (label preserved).
    blocked_assumptions = [
        {"ref": a.ref, "title": a.title, "classification": a.classification}
        for a in assumptions
        if a.classification != _SAFE
    ]

    return ReadinessReport(
        project_id=str(project_id),
        readiness_level=level,
        can_build_to_staging=False,  # Slice 12: hard-false (cannot prove R3+ prerequisites)
        can_go_live_autonomously=False,  # Slice 12: hard-false (capped < R5; gates unmodeled)
        production_authority_decision=production_authority_decision,
        spine_gaps=spine_gaps,
        safe_assumptions=safe_assumptions,
        blocked_assumptions=blocked_assumptions,
    )
