"""§12.3-subset lifecycle + §13.3 verdicts + the per-registration done-gate (Slice 42) — pure.

The honesty model: the system RUNS no review. Verdicts are **REPORTED** (content
``caller_supplied_unverified`` — the Slice-41 provenance model); ``can_merge`` is
**DB-GENERATED** from the verdict and is deliberately NOT an input anywhere in this module
(V2-B2). The done-gate is the §12.3 ``spec:1207`` rule made structural, option (b): ``done``
requires **every registered (reviewer, layer) registration's OWN latest verdict to be
``approved``** — a later same-layer approval by a different reviewer can never bury a
standing rejection. Status vocabulary (V2-B1): only the five BOARD statuses take their names
from the §12.3 columns (``app/release/pm_issues.py:22-40``); ``draft`` is an INTERNAL
pre-board status and ``canceled``/``superseded`` are lifecycle TERMINALS — none of the three
is a §12.3 column.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.review.task_contracts import (
    MAX_ITEM_CHARS,
    MAX_LIST_ITEMS,
    REVIEW_LAYERS,
    require_text,
    require_text_list,
)

RULESET_VERSION = "slice42.v1"

# V2-B1 — three disjoint vocabularies; only BOARD_STATUSES are §12.3 columns.
INTERNAL_STATUSES = ("draft",)
BOARD_STATUSES = (
    "ready_for_development",
    "in_progress",
    "specialist_review",
    "changes_requested",
    "done",
)
TERMINAL_STATUSES = ("canceled", "superseded")
CONTRACT_STATUSES = INTERNAL_STATUSES + BOARD_STATUSES + TERMINAL_STATUSES

# D-42-5 — the transition matrix. ``done`` is NOT terminal: exactly one outgoing
# (done→superseded); terminals have no outgoing; same-status no-ops are refused.
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("ready_for_development", "canceled"),
    "ready_for_development": ("in_progress", "canceled"),
    "in_progress": ("specialist_review", "canceled"),
    "specialist_review": ("changes_requested", "done", "canceled"),
    "changes_requested": ("in_progress", "canceled"),
    "done": ("superseded",),
    "canceled": (),
    "superseded": (),
}

# §13.3 — the two machine verdicts; ``can_merge`` is GENERATED from the verdict at the DB.
VERDICTS = ("approved", "rejected_with_required_changes")

# Reports are recordable only while the work can still be reviewed (D-42-4).
REPORTABLE_STATUSES = ("in_progress", "specialist_review", "changes_requested")

# B1 (Slice-41 model) — the only writable provenance tier this slice.
SOURCE_PROVENANCES = ("caller_supplied_unverified",)

MAX_SUMMARY = 2000
MAX_REPORT_SOURCE = 100


def validate_transition(current, new) -> None:
    """Fail-closed D-42-5 matrix check (same-status refused; terminals final)."""
    if current not in CONTRACT_STATUSES:
        raise ValueError(f"unknown status: {current!r}")
    if new not in CONTRACT_STATUSES:
        raise ValueError(f"unknown status: {new!r}")
    if new == current:
        raise ValueError(f"same-status transition refused: {current!r}")
    if new not in _TRANSITIONS[current]:
        raise ValueError(f"illegal transition: {current!r} -> {new!r}")


def validate_review_report(
    *,
    verdict,
    summary,
    failed_criteria,
    suspected_shortcuts,
    required_changes,
    source,
    source_provenance="caller_supplied_unverified",
) -> None:
    """Fail-closed §13.3 verdict-shape validation. NO ``can_merge`` input (V2-B2 — it is
    DB-generated from the verdict, never caller-writable)."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict: {verdict!r}")
    if source_provenance not in SOURCE_PROVENANCES:
        raise ValueError(f"unsupported source_provenance: {source_provenance!r}")
    require_text("summary", summary, MAX_SUMMARY)
    require_text("source", source, MAX_REPORT_SOURCE)
    for name, value in (
        ("failed_criteria", failed_criteria),
        ("suspected_shortcuts", suspected_shortcuts),
        ("required_changes", required_changes),
    ):
        require_text_list(name, value, max_items=MAX_LIST_ITEMS, max_chars=MAX_ITEM_CHARS)
    if verdict == "approved":
        # A suspected shortcut or a required change is not an approval (§2.1/§13.4).
        if failed_criteria or suspected_shortcuts or required_changes:
            raise ValueError("approved requires empty failed/shortcut/change lists")
    else:  # rejected_with_required_changes (spec:1279-1295)
        if not failed_criteria or not required_changes:
            raise ValueError(
                "rejected_with_required_changes requires failed_criteria and required_changes"
            )


@dataclass(frozen=True)
class RegistrationView:
    """One (layer, reviewer) registration with that reviewer's OWN latest verdict (or None)."""

    layer: str
    reviewer_ref: str
    latest_verdict: str | None


@dataclass(frozen=True)
class DoneGateDecision:
    """The compute-on-read §12.3 done-gate decision (D-42-6) — non-authorizing; the DB
    transition guard is the authoritative backstop of the same rule."""

    eligible: bool
    missing_layers: tuple[str, ...]
    pending_registrations: tuple[tuple[str, str], ...]
    rejected_registrations: tuple[tuple[str, str], ...]
    ruleset_version: str = RULESET_VERSION

    def to_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "missing_layers": list(self.missing_layers),
            "pending_registrations": [list(p) for p in self.pending_registrations],
            "rejected_registrations": [list(r) for r in self.rejected_registrations],
            "ruleset_version": self.ruleset_version,
        }


def evaluate_done_gate(registrations: Sequence[RegistrationView]) -> DoneGateDecision:
    """Option (b): eligible iff every layer is covered AND every registration's own latest
    verdict is ``approved`` (no pending, no rejected). Fail-closed on unknown vocab."""
    covered: set[str] = set()
    pending: list[tuple[str, str]] = []
    rejected: list[tuple[str, str]] = []
    for reg in registrations:
        if reg.layer not in REVIEW_LAYERS:
            raise ValueError(f"unknown layer: {reg.layer!r}")
        if reg.latest_verdict is not None and reg.latest_verdict not in VERDICTS:
            raise ValueError(f"unknown verdict: {reg.latest_verdict!r}")
        covered.add(reg.layer)
        if reg.latest_verdict is None:
            pending.append((reg.layer, reg.reviewer_ref))
        elif reg.latest_verdict != "approved":
            rejected.append((reg.layer, reg.reviewer_ref))
    missing = tuple(layer for layer in REVIEW_LAYERS if layer not in covered)
    return DoneGateDecision(
        eligible=not missing and not pending and not rejected,
        missing_layers=missing,
        pending_registrations=tuple(pending),
        rejected_registrations=tuple(rejected),
    )
