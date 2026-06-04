"""Deterministic gap & structural contradiction detector (Slice 13, §4.4/§14.4/§16.5).

Pure, no DB, no LLM, no semantic analysis. Reads a STRUCTURAL view of the Slice-11
intake spine and reports **gaps** (missing coverage / unresolved decisions) and
**structural contradictions** (invalid/conflicting structure). It is purely
descriptive — it computes NO readiness level and makes no R0–R5 claim.

The input type :class:`StructuralArtifactView` carries only structural fields
(``id``/``kind``/``ref``/``parent_id``/``classification``) — never ``title``/``body``/
``data`` — so "structural fields only / no tenant prose" is enforced by the type shape.
Findings reference ``ref`` handles only and are deterministically sorted.

Note on cycles: ``intake_artifacts`` is append-only and a ``parent_id`` must reference a
pre-existing artifact at insert, so multi-node parent cycles are structurally
impossible; only a self-parent (``parent_id == id``, reachable via a raw insert) is
detected, as a defensive guard.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

RULESET_VERSION = "slice13.v1"

_SAFE = "safe_assumption"


@dataclass(frozen=True)
class StructuralArtifactView:
    """Structural-only view of one intake artifact (no tenant content by construction)."""

    id: uuid.UUID
    kind: str
    ref: str
    parent_id: uuid.UUID | None = None
    classification: str | None = None


@dataclass
class FindingsReport:
    project_id: str
    gaps: list[dict] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "gaps": self.gaps,
            "contradictions": self.contradictions,
            "gap_count": len(self.gaps),
            "contradiction_count": len(self.contradictions),
            "ruleset_version": RULESET_VERSION,
        }


def detect_findings(
    project_id, artifacts: list[StructuralArtifactView]
) -> FindingsReport:
    """Deterministic gap + structural-contradiction detection over the spine snapshot."""
    by_id = {a.id: a for a in artifacts}
    requirements = [a for a in artifacts if a.kind == "requirement"]
    acceptance = [a for a in artifacts if a.kind == "acceptance_criterion"]
    oracles = [a for a in artifacts if a.kind == "test_oracle"]
    assumptions = [a for a in artifacts if a.kind == "assumption"]

    def parent_of(a: StructuralArtifactView) -> StructuralArtifactView | None:
        return by_id.get(a.parent_id) if a.parent_id is not None else None

    gaps: list[dict] = []
    contradictions: list[dict] = []

    def gap(kind: str, ref: str, summary: str, **extra) -> None:
        gaps.append({"kind": kind, "ref": ref, "summary": summary, **extra})

    def contradiction(kind: str, refs: list[str], summary: str) -> None:
        contradictions.append({"kind": kind, "refs": refs, "summary": summary})

    # --- gaps -----------------------------------------------------------------
    if not requirements:
        gap("G_NO_REQUIREMENTS", "", "project has no requirement artifacts")

    # A requirement is covered only by an acceptance_criterion whose parent IS that requirement.
    valid_ac = [
        a for a in acceptance if (p := parent_of(a)) is not None and p.kind == "requirement"
    ]
    covered_req_ids = {a.parent_id for a in valid_ac}
    for r in requirements:
        if r.id not in covered_req_ids:
            gap(
                "G_REQUIREMENT_WITHOUT_ACCEPTANCE",
                r.ref,
                f"requirement {r.ref} has no acceptance criterion",
            )

    # An oracle covers an acceptance criterion only if its parent IS that acceptance criterion.
    valid_oracle = [
        o for o in oracles if (p := parent_of(o)) is not None and p.kind == "acceptance_criterion"
    ]
    ac_with_oracle = {o.parent_id for o in valid_oracle}
    for a in valid_ac:
        if a.id not in ac_with_oracle:
            gap(
                "G_ACCEPTANCE_WITHOUT_ORACLE",
                a.ref,
                f"acceptance criterion {a.ref} has no test oracle",
            )

    for a in assumptions:
        if a.classification != _SAFE:
            gap(
                "G_UNRESOLVED_ASSUMPTION",
                a.ref,
                f"assumption {a.ref} is unresolved ({a.classification})",
                classification=a.classification,
            )

    # --- structural contradictions --------------------------------------------
    # Generic self-parent (parent_id == id) across ALL kinds — a reachable raw-insert
    # contradiction. Detected once here so the kind-specific checks below neither
    # shadow it (e.g. as C_REQUIREMENT_HAS_PARENT) nor duplicate it.
    self_parent_ids: set[uuid.UUID] = set()
    for a in artifacts:
        if a.parent_id is not None and a.parent_id == a.id:
            contradiction("C_SELF_PARENT", [a.ref], f"{a.ref} is its own parent")
            self_parent_ids.add(a.id)

    for r in requirements:
        if r.id in self_parent_ids:
            continue
        if r.parent_id is not None:
            contradiction(
                "C_REQUIREMENT_HAS_PARENT",
                [r.ref],
                f"requirement {r.ref} must be top-level but has a parent",
            )

    for a in acceptance:
        if a.id in self_parent_ids:
            continue
        if a.parent_id is None:
            contradiction(
                "C_ORPHAN_ACCEPTANCE", [a.ref], f"acceptance criterion {a.ref} has no parent"
            )
        elif (p := parent_of(a)) is None or p.kind != "requirement":
            contradiction(
                "C_WRONG_KIND_PARENT",
                [a.ref],
                f"acceptance criterion {a.ref} parent is not a requirement",
            )

    for o in oracles:
        if o.id in self_parent_ids:
            continue
        if o.parent_id is None:
            contradiction("C_ORPHAN_ORACLE", [o.ref], f"test oracle {o.ref} has no parent")
        elif (p := parent_of(o)) is None or p.kind != "acceptance_criterion":
            contradiction(
                "C_WRONG_KIND_PARENT",
                [o.ref],
                f"test oracle {o.ref} parent is not an acceptance criterion",
            )

    # Deterministic ordering: gaps by (kind, ref); contradictions by (kind, refs).
    gaps.sort(key=lambda g: (g["kind"], g["ref"]))
    contradictions.sort(key=lambda c: (c["kind"], tuple(c["refs"])))
    return FindingsReport(project_id=str(project_id), gaps=gaps, contradictions=contradictions)
