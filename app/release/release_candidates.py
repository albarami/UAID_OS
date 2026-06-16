"""Release-candidate validation + lifecycle (Slice 25, spec §24.1 / §24.2 / Appendix B #7) —
pure, no I/O.

A ``release_candidates`` row is the deterministic release namespace that can **later** become the
authoritative referent for Slice-22 ``risk_acceptance_records.release_id`` and future evidence packs;
its freeze-locked issue bindings let "remaining open issues **for this release**" be scoped. **This
slice does not FK or validate ``risk_acceptance_records.release_id``, assert issue completeness,
approve a release, or enable go-live.**

- Lifecycle is one-way: ``draft`` → ``frozen`` | ``canceled``; ``frozen`` → ``superseded`` |
  ``canceled``. ``superseded``/``canceled`` are terminal. There is **no** approval/go-live state.
- ``frozen_at`` is set iff a candidate enters ``frozen`` (enforced by the DB guard).
"""

from __future__ import annotations

STATUSES = ("draft", "frozen", "superseded", "canceled")
TERMINAL_STATUSES = ("superseded", "canceled")

# One-way transitions.
_ALLOWED_TRANSITIONS = {
    ("draft", "frozen"),
    ("draft", "canceled"),
    ("frozen", "superseded"),
    ("frozen", "canceled"),
}

REQUIRED_CREATE_FIELDS = ("release_ref",)


class InvalidReleaseCandidate(ValueError):
    """Raised when a release-candidate payload or lifecycle transition is invalid (fail-closed)."""


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_new_candidate(record: dict) -> None:
    """Fail-closed validation of a new release candidate. Raises ``InvalidReleaseCandidate``."""
    for field in REQUIRED_CREATE_FIELDS:
        if field not in record or _empty(record[field]):
            raise InvalidReleaseCandidate(f"missing or empty required field: {field}")
    title = record.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidReleaseCandidate("title must be a string when present")


def validate_transition(from_status: str, to_status: str) -> None:
    """Fail-closed: only draft→{frozen,canceled} and frozen→{superseded,canceled} are allowed."""
    if (from_status, to_status) not in _ALLOWED_TRANSITIONS:
        raise InvalidReleaseCandidate(f"invalid transition: {from_status} -> {to_status}")
