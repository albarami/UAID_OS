"""Open-issue / blocker validation + lifecycle (Slice 24, spec §24.1 / §24.2 / Appendix B #7) —
pure, no I/O.

A ``release_issues`` row is a known release blocker/issue. The store gives A5 gate #7 ("any remaining
open issues have approved risk-acceptance records") a real evidence base and gives the Slice-22
risk-acceptance ``issue_id`` a real referent. **Fail-closed and non-authorizing:**

- ``issue_category`` ∈ a coarse §24.1/Appendix-B gate-axis set; ``other`` is **not** a silent escape
  hatch — it requires non-empty ``summary`` + ``detail``.
- ``severity ∈ {low, medium, high, critical}``. **Hard blockers (``critical`` OR a hard-refusal
  ``blocking_category``) imply ``blocking``** — they cannot be created non-blocking (a hard blocker
  cannot masquerade its way out of the open-blocking count and past the gate).
- Lifecycle is one-way: ``open`` → ``resolved`` | ``accepted`` | ``superseded`` (no
  ``false_positive`` — an issue is an asserted blocker, not a detector signal).
- A **hard blocker** (``severity == "critical"`` OR a ``blocking_category`` in the §24.1 hard-refusal
  set) can **never** be ``accepted``. Acceptance of any issue requires a usable risk-acceptance
  record (enforced by the repository + DB guard). Issues never enable go-live.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Mapping

from app.release.findings import SECURITY_CATEGORIES, SHORTCUT_CATEGORIES
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

TRUSTED_FINDING_PROVENANCE = "db_verified_trusted_release_finding"
FINDING_BRIDGE_SOURCE = "slice47.finding_bridge.v1"
FINDING_BRIDGE_CONTRACT = "slice47.finding_bridge.v1"
MAX_RECONCILIATION_FINDINGS = 10_000
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class TrustedFindingIssueDerivation:
    """Code-owned issue fields derived from one stored trusted finding (Slice 47)."""

    source_finding_id: uuid.UUID
    issue_category: str
    severity: str
    blocking: bool
    blocking_category: str | None
    summary: str
    detail: None
    source: str
    source_provenance: str


class InvalidIssue(ValueError):
    """Raised when an issue payload or lifecycle transition is invalid (fail-closed)."""


def derive_issue_from_finding(record: Mapping) -> TrustedFindingIssueDerivation:
    """Derive the conservative Slice-47 issue shape from stored trusted-finding structure.

    This function accepts no caller-supplied trust or blocker decision: every returned field is
    derived from the finding's guarded type/category/severity/provenance/attachment shape.
    """

    finding_id = record.get("id")
    if not isinstance(finding_id, uuid.UUID):
        raise InvalidIssue("trusted finding id must be a UUID")
    if record.get("status") != "open":
        raise InvalidIssue("only open findings may be bridged")
    finding_type = record.get("finding_type")
    category = record.get("category")
    severity = record.get("severity")
    if severity not in SEVERITIES:
        raise InvalidIssue("trusted finding severity is invalid")

    if finding_type == "security":
        valid = (
            record.get("source_provenance") == "connector_verified_security_scan"
            and category in SECURITY_CATEGORIES[:-1]
            and isinstance(record.get("security_scan_category_result_id"), uuid.UUID)
            and _FINGERPRINT_RE.fullmatch(record.get("scan_finding_fingerprint") or "") is not None
            and record.get("shortcut_detector_category_result_id") is None
            and record.get("shortcut_finding_fingerprint") is None
        )
        blocking_category = "critical_security_blocker" if severity == "critical" else None
    elif finding_type == "shortcut":
        valid = (
            record.get("source_provenance") == "system_executed_shortcut_review"
            and category in SHORTCUT_CATEGORIES[:-1]
            and isinstance(record.get("shortcut_detector_category_result_id"), uuid.UUID)
            and _FINGERPRINT_RE.fullmatch(record.get("shortcut_finding_fingerprint") or "")
            is not None
            and record.get("security_scan_category_result_id") is None
            and record.get("scan_finding_fingerprint") is None
        )
        blocking_category = "fake_done_finding"
    else:
        valid = False
        blocking_category = None
    if not valid:
        raise InvalidIssue("finding lacks trusted Slice-44/45 attachment provenance")

    summary = f"Trusted {finding_type} finding ({category}) requires release disposition"
    if len(summary.encode("utf-8")) > 500:
        raise InvalidIssue("derived issue summary exceeds 500 bytes")
    return TrustedFindingIssueDerivation(
        source_finding_id=finding_id,
        issue_category=finding_type,
        severity=severity,
        blocking=True,
        blocking_category=blocking_category,
        summary=summary,
        detail=None,
        source=FINDING_BRIDGE_SOURCE,
        source_provenance=TRUSTED_FINDING_PROVENANCE,
    )


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
    # hard blockers (critical OR a hard-refusal blocking_category) must be blocking — a hard blocker
    # cannot masquerade as non-blocking and slip out of the open-blocking count (fail-closed; also
    # DB-guard-enforced).
    if (
        is_hard_blocker(record["severity"], record.get("blocking_category"))
        and record["blocking"] is not True
    ):
        raise InvalidIssue(
            "hard-blocker issues (critical or hard-refusal category) must be blocking"
        )


def validate_transition(from_status: str, to_status: str) -> None:
    """Fail-closed: only open → {resolved, accepted, superseded} is allowed."""
    if (from_status, to_status) not in _ALLOWED_TRANSITIONS:
        raise InvalidIssue(f"invalid transition: {from_status} -> {to_status}")
