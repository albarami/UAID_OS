"""Release findings validation + lifecycle (Slice 23, spec §13.4 / §916-920) — pure, no I/O.

Security and shortcut/fake-done findings that gate a release (Appendix B #5/#6, §24.1). Fail-closed
and **non-authorizing**:

- ``finding_type ∈ {security, shortcut}``; ``severity ∈ {low, medium, high, critical}``.
- ``category`` is validated against the selected type's set (§916-920 security, §13.4 shortcut).
  ``other`` is **not a silent escape hatch** — it requires non-empty ``summary`` and ``detail``.
- Lifecycle is one-way: ``open`` → ``resolved`` | ``false_positive`` | ``accepted`` | ``superseded``.
  **Critical findings can never be accepted** (§24.1: critical security blockers / fake-done findings
  are not risk-acceptable without a verified human-authority override that does not exist yet) — they
  may only become ``resolved``/``false_positive``/``superseded``. Acceptance of non-critical findings
  is gated on a usable risk-acceptance record (enforced by the repository + DB guard).
"""

from __future__ import annotations

FINDING_TYPES = ("security", "shortcut")
SEVERITIES = ("low", "medium", "high", "critical")

# §916-920 security-reviewer categories.
SECURITY_CATEGORIES = (
    "authz",
    "injection",
    "secrets_exposure",
    "unsafe_tool",
    "supply_chain",
    "other",
)
# §13.4 shortcut-detection checklist.
SHORTCUT_CATEGORIES = (
    "hardcoded_value",
    "static_response",
    "fake_integration",
    "disabled_validation",
    "weakened_tests",
    "error_swallowing",
    "placeholder_ui",
    "todo_in_required_path",
    "local_only_substitute",
    "acceptance_silently_skipped",
    "tests_check_implementation",
    "readiness_without_evidence",
    "other",
)
_CATEGORIES_BY_TYPE = {
    "security": frozenset(SECURITY_CATEGORIES),
    "shortcut": frozenset(SHORTCUT_CATEGORIES),
}

STATUSES = ("open", "resolved", "false_positive", "accepted", "superseded")
TERMINAL_STATUSES = ("resolved", "false_positive", "accepted", "superseded")
_ALLOWED_TRANSITIONS = {("open", t) for t in TERMINAL_STATUSES}

REQUIRED_CREATE_FIELDS = ("finding_type", "category", "severity", "summary", "source")


class InvalidFinding(ValueError):
    """Raised when a finding payload or lifecycle transition is invalid (fail-closed)."""


def is_critical(severity: str) -> bool:
    return severity == "critical"


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_new_finding(record: dict) -> None:
    """Fail-closed validation of a new finding. Raises ``InvalidFinding`` on any violation."""
    for field in REQUIRED_CREATE_FIELDS:
        if field not in record or _empty(record[field]):
            raise InvalidFinding(f"missing or empty required field: {field}")
    ftype = record["finding_type"]
    if ftype not in FINDING_TYPES:
        raise InvalidFinding(f"invalid finding_type: {ftype!r}")
    if record["severity"] not in SEVERITIES:
        raise InvalidFinding(f"invalid severity: {record['severity']!r}")
    if record["category"] not in _CATEGORIES_BY_TYPE[ftype]:
        raise InvalidFinding(
            f"category {record['category']!r} is not valid for finding_type {ftype!r}"
        )
    # 'other' must not be a silent escape hatch (also DB-guard-enforced).
    if record["category"] == "other" and (_empty(record.get("summary")) or _empty(record.get("detail"))):
        raise InvalidFinding("category='other' requires non-empty summary and detail")


def validate_transition(from_status: str, to_status: str) -> None:
    """Fail-closed: only open → {resolved, false_positive, accepted, superseded} is allowed."""
    if (from_status, to_status) not in _ALLOWED_TRANSITIONS:
        raise InvalidFinding(f"invalid transition: {from_status} -> {to_status}")
