"""Risk-acceptance record validation + lifecycle (Slice 22, spec §24.1 / §27.10) — pure, no I/O.

A risk-acceptance record lets a release proceed with a *known, non-blocking* open issue, signed by
the approvers named in the approval matrix (§24.1). This module is **fail-closed and
non-authorizing**:

- **Hard-refusal categories** (§24.1, spec:2271) can never be risk-accepted in this slice — the
  spec's "unless human authority explicitly accepts AND the autonomy policy permits" override needs
  verified authority + an autonomy-override path that do not exist yet, so they are blocked outright.
- **Required fields** (the §27.10 / §24.1 authority fields) must all be present; ``expiry_date`` is
  required (no indefinite/silent waiver); ``accepted_by`` must be non-empty; ``approval_authority_source``
  must be ``approval_matrix``.
- **Lifecycle** is one-way: ``active`` → ``expired`` | ``revoked`` | ``superseded``; terminal states
  never transition again.

Signer identity is **not verified** here (the repository stamps
``approver_provenance="caller_supplied_unverified"`` until request-auth exists). Records never enable
go-live.
"""

from __future__ import annotations

SEVERITIES = ("low", "medium", "high", "critical")

# §24.1 (spec:2271): risk acceptance is NOT allowed for these — blocked outright this slice.
HARD_REFUSAL_CATEGORIES = (
    "critical_security_blocker",
    "fake_done_finding",
    "missing_production_rollback",
    "missing_regulated_or_safety_authority",
)

STATUSES = ("active", "expired", "revoked", "superseded")
TERMINAL_STATUSES = ("expired", "revoked", "superseded")
APPROVAL_AUTHORITY_SOURCE = "approval_matrix"

# One-way transitions from active only.
_ALLOWED_TRANSITIONS = {
    ("active", "expired"),
    ("active", "revoked"),
    ("active", "superseded"),
}

# §27.10 / §24.1 authority fields that must be present + non-empty.
REQUIRED_FIELDS = (
    "release_id",
    "issue_id",
    "severity",
    "reason_for_acceptance",
    "business_impact",
    "rollback_or_mitigation_plan",
    "required_follow_up_ticket",
    "expiry_date",
    "owner",
    "approver",
    "accepted_by",
    "approval_authority_source",
)


class InvalidRiskAcceptance(ValueError):
    """Raised when a risk-acceptance record or lifecycle transition is invalid (fail-closed)."""


def is_hard_refusal(category: str | None) -> bool:
    return category in HARD_REFUSAL_CATEGORIES


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return True
    return False


def validate_new_record(record: dict) -> None:
    """Fail-closed validation of a new record. Raises ``InvalidRiskAcceptance`` on any violation."""
    for field in REQUIRED_FIELDS:
        if field not in record or _is_empty(record[field]):
            raise InvalidRiskAcceptance(f"missing or empty required field: {field}")
    if record["severity"] not in SEVERITIES:
        raise InvalidRiskAcceptance(f"invalid severity: {record['severity']!r}")
    if not isinstance(record["accepted_by"], list) or len(record["accepted_by"]) == 0:
        raise InvalidRiskAcceptance("accepted_by must be a non-empty list")
    if record["approval_authority_source"] != APPROVAL_AUTHORITY_SOURCE:
        raise InvalidRiskAcceptance(
            f"approval_authority_source must be {APPROVAL_AUTHORITY_SOURCE!r}"
        )
    blocking = record.get("blocking_category")
    if blocking is not None and is_hard_refusal(blocking):
        raise InvalidRiskAcceptance(
            f"hard-refusal category cannot be risk-accepted: {blocking}"
        )


def validate_transition(from_status: str, to_status: str) -> None:
    """Fail-closed: only active → {expired, revoked, superseded} is allowed."""
    if (from_status, to_status) not in _ALLOWED_TRANSITIONS:
        raise InvalidRiskAcceptance(f"invalid transition: {from_status} -> {to_status}")
