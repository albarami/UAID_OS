"""Canonical intake compiler — pure validation + the Sanad source gate (Slice 11, §3.4/§4.4).

Deterministic, no LLM. This module holds the in-code rules for the canonical intake
spine: the allowed artifact kinds and §4.4 assumption classifications, and the
**fail-closed** source gate. ``assert_sources`` reuses ``app.core.provenance`` — a
fact (artifact) with no source raises :class:`NoFreeFactsError`. The database is the
backstop (a deferrable constraint trigger), but the rule lives here too so callers
fail before touching the DB. The persistence/audit path is in
``app.repositories.intake``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.provenance import Fact, Source

ARTIFACT_KINDS = (
    "requirement",
    "acceptance_criterion",
    "test_oracle",
    "assumption",
)

# §4.4 assumption labels — precise machine values (no lossy abbreviations).
ASSUMPTION_CLASSIFICATIONS = (
    "safe_assumption",
    "needs_approval",
    "unsafe_assumption_blocked",
    "unknown_cannot_proceed",
)


class InvalidArtifact(ValueError):
    """Raised when an artifact's kind or classification is invalid."""


@dataclass(frozen=True)
class SourceInput:
    """One Sanad source for an artifact. ``document_id`` (when set) must reference an
    accepted document of the same tenant/project (enforced at the DB + repository)."""

    origin: str
    locator: str | None = None
    document_id: uuid.UUID | None = None


def validate_kind(kind: str) -> None:
    if kind not in ARTIFACT_KINDS:
        raise InvalidArtifact(f"unknown artifact kind: {kind!r}")


def validate_classification(kind: str, classification: str | None) -> None:
    """Mirror the DB CHECK: only ``assumption`` may (and must) carry a classification;
    every other kind must have ``classification IS NULL``."""
    if kind == "assumption":
        if classification not in ASSUMPTION_CLASSIFICATIONS:
            raise InvalidArtifact(
                f"assumption requires a classification in {ASSUMPTION_CLASSIFICATIONS}, "
                f"got {classification!r}"
            )
    elif classification is not None:
        raise InvalidArtifact(f"{kind!r} must not carry a classification (got {classification!r})")


def assert_sources(title: str, sources: list[SourceInput]) -> None:
    """Fail closed if an artifact has no provenance (Sanad / No-Free-Facts, §2.4)."""
    # Building a Fact reuses the primitive's ``NoFreeFactsError`` on empty sources.
    Fact(claim=title, sources=[Source(origin=s.origin, locator=s.locator or "") for s in sources])
