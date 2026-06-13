"""Deterministic build-readiness auditor (Slice 12 base; Slice 16 R3 rules; §4.3/§4.4/§4.5).

Pure, no DB, no LLM. Reads a snapshot of canonical-intake artifacts plus the project's
declared intake categories (Slice 15) and produces the §4.5 intake validation report.
**Fail-closed and honest.**

Readiness ladder:
- R0: no requirements; R1: requirements but no valid requirement→acceptance chain;
  R2: ≥1 valid requirement→acceptance chain (parent-kind validated).
- **R3 (Slice 16): the R2 base PLUS the three §4.3 technical categories — architecture/stack
  (``architecture_and_technology_constraints``), data (``data_model_and_contracts``), and
  workflows (``user_journeys_and_workflows``) — each DECLARED via Slice 15.** The auditor is
  **capped at R3**: R4/R5 require the gated autonomy/approval/cost/production-authority
  engines + secrets/tooling/go-live/test-coverage rules that are NOT yet evaluated.
- The R3 rule checks the **presence of a provenance-backed declaration**, not content
  quality — "declared", not "verified".

``can_build_to_staging`` is true only at R3 AND when ``environments_and_deployment_targets``
is declared. ``can_go_live_autonomously`` is always false (capped below R5; gated categories
unevaluated). Parent-kind validation does NOT trust the DB FK alone: an acceptance_criterion
satisfies a requirement only if its parent IS a requirement; a test_oracle satisfies an
acceptance criterion only if its parent IS that acceptance criterion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.intake.categories import CANONICAL_READINESS_CATEGORY_UNIVERSE, SPINE_CATEGORIES

RULESET_VERSION = "slice16.v1"

READINESS_CAP = "R3"
READINESS_CAP_REASON = (
    "slice_16_rules_consume_declared_r3_categories_only; "
    "r4_r5_require_gated_engine_evaluation_secrets_tooling_go_live_and_test_coverage_rules"
)
NO_GO_LIVE_REASONS = (
    "readiness_capped_below_R5",
    "gated_engine_categories_not_evaluated:"
    "autonomy_policy,human_approval_policy,cost_and_resource_policy,production_authority",
)
# can_build_to_staging reasons (exact, stable strings).
STAGING_TRUE_REASON = "r3_with_environments_and_deployment_targets_declared"
STAGING_R3_NO_ENV_REASON = "r3_but_environments_and_deployment_targets_not_declared"
STAGING_BELOW_R3_REASON = "readiness_below_R3"

# §4.3 R3 technical categories (in canonical §4.2 file order: 05, 11, 14).
R3_TECHNICAL_CATEGORIES = (
    "user_journeys_and_workflows",
    "data_model_and_contracts",
    "architecture_and_technology_constraints",
)
STAGING_ENVIRONMENT_CATEGORY = "environments_and_deployment_targets"

# Canonical §4.2 file order (00..25) + the Appendix-A production_authority condition last.
# This is the ordering source for not_assessed_categories; a test asserts its set equals
# the Slice-15 universe (single source of truth).
_CANONICAL_FILE_ORDER = (
    "project_manifest",                          # 00
    "product_brief",                             # 01
    "business_objectives",                       # 02
    "scope_and_boundaries",                      # 03
    "users_roles_permissions",                   # 04
    "user_journeys_and_workflows",               # 05
    "functional_requirements",                   # 06 (spine)
    "non_functional_requirements",               # 07
    "acceptance_criteria",                       # 08 (spine)
    "test_oracles",                              # 09 (spine)
    "domain_pack",                               # 10
    "data_model_and_contracts",                  # 11
    "integrations_and_external_systems",         # 12
    "existing_assets_and_repositories",          # 13
    "architecture_and_technology_constraints",   # 14
    "security_privacy_compliance",               # 15
    "environments_and_deployment_targets",       # 16
    "secrets_and_credentials_manifest",          # 17
    "tool_access_manifest",                      # 18
    "autonomy_policy",                           # 19 (gated)
    "human_approval_policy",                     # 20 (gated)
    "cost_and_resource_policy",                  # 21 (gated)
    "operations_observability_support",          # 22
    "go_live_checklist",                         # 23
    "risk_register_and_assurance_requirements",  # 24
    "prior_decisions_and_architecture_log",      # 25
    "production_authority",                      # Appendix A condition
)
# Categories now consumed by a rule: spine (ladder) + R3 trio + the staging environment gate.
_CONSUMED_CATEGORIES = (
    frozenset(SPINE_CATEGORIES)
    | set(R3_TECHNICAL_CATEGORIES)
    | {STAGING_ENVIRONMENT_CATEGORY}
)
# Deterministic: §4.2 file order minus everything a rule consumes (20 items).
NOT_ASSESSED_CATEGORIES = tuple(
    c for c in _CANONICAL_FILE_ORDER if c not in _CONSUMED_CATEGORIES
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


@dataclass(frozen=True)
class CategoryDeclarationView:
    """A DB-free view of one declared intake category (Slice 15) for the R3 rule."""

    category: str
    status: str  # 'declared' | 'not_applicable'


@dataclass
class ReadinessReport:
    project_id: str
    readiness_level: str
    can_build_to_staging: bool
    can_go_live_autonomously: bool
    production_authority_decision: str
    can_build_to_staging_reason: str
    spine_gaps: list[dict] = field(default_factory=list)
    safe_assumptions: list[dict] = field(default_factory=list)
    blocked_assumptions: list[dict] = field(default_factory=list)
    missing_r3_categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            # §4.5 keys
            "project_id": self.project_id,
            "readiness_level": self.readiness_level,
            "can_build_to_staging": self.can_build_to_staging,
            "can_go_live_autonomously": self.can_go_live_autonomously,
            "missing_for_go_live": [g["summary"] for g in self.spine_gaps]
            + [f"r3_category_not_declared:{c}" for c in self.missing_r3_categories]
            + list(NOT_ASSESSED_CATEGORIES),
            "safe_assumptions": self.safe_assumptions,
            "blocked_assumptions": self.blocked_assumptions,
            # deterministic extensions
            "readiness_cap": READINESS_CAP,
            "readiness_cap_reason": READINESS_CAP_REASON,
            "can_build_to_staging_reason": self.can_build_to_staging_reason,
            "can_go_live_autonomously_reasons": list(NO_GO_LIVE_REASONS),
            "not_assessed_categories": list(NOT_ASSESSED_CATEGORIES),
            "spine_gaps": self.spine_gaps,
            "missing_r3_categories": self.missing_r3_categories,
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
    declarations: tuple[CategoryDeclarationView, ...] = (),
) -> ReadinessReport:
    """Deterministic, fail-closed readiness evaluation over the spine + declared categories.

    ``declarations`` defaults to empty, so callers that pass no categories get the exact
    R0/R1/R2 ladder semantics (R3 is unreachable without declared technical categories).
    """
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

    # Spine ladder (fail-closed).
    if not requirements:
        level = "R0"
    elif not covered_req_ids:
        level = "R1"
    else:
        level = "R2"

    # Slice 16 — R3: R2 base + the three technical categories DECLARED.
    declared = {d.category for d in declarations if d.status == "declared"}
    missing_r3 = [c for c in R3_TECHNICAL_CATEGORIES if c not in declared]
    if level == "R2" and not missing_r3:
        level = "R3"

    # Staging facet (D-3b): R3 AND environments declared.
    if level == "R3" and STAGING_ENVIRONMENT_CATEGORY in declared:
        can_build_to_staging = True
        staging_reason = STAGING_TRUE_REASON
    elif level == "R3":
        can_build_to_staging = False
        staging_reason = STAGING_R3_NO_ENV_REASON
    else:
        can_build_to_staging = False
        staging_reason = STAGING_BELOW_R3_REASON

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
        can_build_to_staging=can_build_to_staging,
        can_go_live_autonomously=False,  # always false: capped < R5; gated categories unevaluated
        production_authority_decision=production_authority_decision,
        can_build_to_staging_reason=staging_reason,
        spine_gaps=spine_gaps,
        safe_assumptions=safe_assumptions,
        blocked_assumptions=blocked_assumptions,
        missing_r3_categories=missing_r3,
    )


# Defensive single-source-of-truth check: the not-assessed list must be exactly the
# Slice-15 universe minus the rule-consumed categories.
assert set(NOT_ASSESSED_CATEGORIES) == set(CANONICAL_READINESS_CATEGORY_UNIVERSE) - set(
    _CONSUMED_CATEGORIES
), "NOT_ASSESSED_CATEGORIES drifted from the §4.2 universe"
