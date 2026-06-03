"""Pure approval state machine, non-response policy, and gate (§18).

No I/O. The security-critical rule (a §2.6 / policy `NEEDS_APPROVAL` action can
never be unblocked by non-response) lives in :func:`is_blocked` and
:func:`auto_transition`: when ``requires_explicit_approval`` is True, only
``APPROVED`` unblocks and no auto-transition occurs.
"""

from datetime import datetime, timedelta
from enum import Enum

NON_RESPONSE_WINDOW = timedelta(hours=24)  # §18.5 "...after_24h"


class InvalidApprovalTransition(Exception):
    """Raised on a forbidden state transition (terminal states are immutable)."""


class InvalidApprovalRequest(Exception):
    """Raised when a request is internally inconsistent (e.g. loosening a §2.6 action)."""


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PRODUCTION = "production"


class Status(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"  # blocking (medium-risk timeout / pause persisted)
    PROCEEDED_BY_POLICY = "proceeded_by_policy"  # unblocking, non-explicit low-risk only


_TERMINAL = {
    Status.APPROVED,
    Status.REJECTED,
    Status.CANCELLED,
    Status.EXPIRED,
    Status.PROCEEDED_BY_POLICY,
}
_ALLOWED: dict[Status, set[Status]] = {Status.PENDING: set(_TERMINAL)}


def validate_transition(current: Status, target: Status) -> None:
    if target not in _ALLOWED.get(current, set()):
        raise InvalidApprovalTransition(f"cannot transition {current.value} -> {target.value}")


def compute_deadline(
    requested_at: datetime, tier: RiskTier, *, requires_explicit: bool
) -> datetime | None:
    """Non-response deadline — only for low/medium, non-explicit approvals."""
    if requires_explicit:
        return None
    if tier in (RiskTier.LOW, RiskTier.MEDIUM):
        return requested_at + NON_RESPONSE_WINDOW
    return None  # high / production never lapse


def auto_transition(
    tier: RiskTier, requires_explicit: bool, requested_at: datetime, now: datetime
) -> Status | None:
    """Target status for an overdue PENDING approval, or None (stay pending).

    Never transitions explicit-approval or high/production approvals.
    """
    if requires_explicit:
        return None
    if now < requested_at + NON_RESPONSE_WINDOW:
        return None
    if tier is RiskTier.LOW:
        return Status.PROCEEDED_BY_POLICY
    if tier is RiskTier.MEDIUM:
        return Status.EXPIRED
    return None  # high / production


def is_blocked(status: Status | None, *, requires_explicit: bool) -> bool:
    """Fail-closed gate: the dependent action is blocked unless explicitly cleared."""
    if status is Status.APPROVED:
        return False
    if status is Status.PROCEEDED_BY_POLICY and not requires_explicit:
        return False
    return True
