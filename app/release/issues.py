"""Open-issue / blocker validation + lifecycle (Slice 24, spec §24.1 / §24.2 / Appendix B #7) —
pure, no I/O.

A ``release_issues`` row is a known release blocker/issue. The store gives A5 gate #7 ("any remaining
open issues have approved risk-acceptance records") a real evidence base and gives the Slice-22
risk-acceptance ``issue_id`` a real referent. **Fail-closed and non-authorizing:**

- ``issue_category`` ∈ a coarse §24.1/Appendix-B gate-axis set; ``other`` is **not** a silent escape
  hatch — it requires non-empty ``summary`` + ``detail``.
- ``severity ∈ {low, medium, high, critical}``. **``critical`` implies ``blocking``** — a critical
  issue cannot be created non-blocking (it cannot masquerade its way past the gate).
- Lifecycle is one-way: ``open`` → ``resolved`` | ``accepted`` | ``superseded`` (no
  ``false_positive`` — an issue is an asserted blocker, not a detector signal).
- A **hard blocker** (``severity == "critical"`` OR a ``blocking_category`` in the §24.1 hard-refusal
  set) can **never** be ``accepted``. Acceptance of any issue requires a usable risk-acceptance
  record (enforced by the repository + DB guard). Issues never enable go-live.
"""

from __future__ import annotations

from app.release.risk_acceptance import HARD_REFUSAL_CATEGORIES

SEVERITIES = ("low", "medium", "high", "critical")

# Coarse blocker dimensions mapped to the §24.1 / Appendix-B gate axes (D-OI-2). 'blocker' is NOT a
# category — blocking is a separate boolean axis (see ``blocking``).
ISSUE_CATEGORIES = (
    "security",
    "shortcut",
    "test_or_acceptance",
    "cost",
    "deployment",
    "rollback",
    "monitoring",
    "evidence",
    "approval",
    "other",
)

STATUSES = ("open", "resolved", "accepted", "superseded")
TERMINAL_STATUSES = ("resolved", "accepted", "superseded")
_ALLOWED_TRANSITIONS = {("open", t) for t in TERMINAL_STATUSES}

REQUIRED_CREATE_FIELDS = ("issue_category", "severity", "blocking", "summary", "source")


class InvalidIssue(ValueError):
    """Raised when an issue payload or lifecycle transition is invalid (fail-closed)."""


def is_critical(severity: str) -> bool:
    return severity == "critical"


def is_hard_blocker(severity: str, blocking_category: str | None) -> bool:
    """A hard blocker can never be risk-accepted (spec:2271): critical severity OR a hard-refusal
    blocking category."""
    return is_critical(severity) or blocking_category in HARD_REFUSAL_CATEGORIES


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_new_issue(record: dict) -> None:
    """Fail-closed validation of a new issue. Raises ``InvalidIssue`` on any violation."""
    for field in REQUIRED_CREATE_FIELDS:
        if field not in record:
            raise InvalidIssue(f"missing required field: {field}")
    # ``blocking`` is a bool axis — must be a real bool, not a truthy string/None.
    if not isinstance(record["blocking"], bool):
        raise InvalidIssue("blocking must be a boolean")
    for field in ("issue_category", "severity", "summary", "source"):
        if _empty(record[field]):
            raise InvalidIssue(f"missing or empty required field: {field}")
    if record["issue_category"] not in ISSUE_CATEGORIES:
        raise InvalidIssue(f"invalid issue_category: {record['issue_category']!r}")
    if record["severity"] not in SEVERITIES:
        raise InvalidIssue(f"invalid severity: {record['severity']!r}")
    # 'other' must not be a silent escape hatch (also DB-guard-enforced).
    if record["issue_category"] == "other" and (
        _empty(record.get("summary")) or _empty(record.get("detail"))
    ):
        raise InvalidIssue("issue_category='other' requires non-empty summary and detail")
    # critical ⇒ blocking (fail-closed; also DB-guard-enforced).
    if is_critical(record["severity"]) and record["blocking"] is not True:
        raise InvalidIssue("critical issues must be blocking")


def validate_transition(from_status: str, to_status: str) -> None:
    """Fail-closed: only open → {resolved, accepted, superseded} is allowed."""
    if (from_status, to_status) not in _ALLOWED_TRANSITIONS:
        raise InvalidIssue(f"invalid transition: {from_status} -> {to_status}")
