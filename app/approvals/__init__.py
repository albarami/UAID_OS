"""Approval engine (Slice 4, §18).

Pure state machine + non-response policy + gate (:mod:`app.approvals.states`).
Persistence and lifecycle are in :mod:`app.repositories.approvals`.

NOTE: until the request-auth slice exists, ``requested_by``/``resolved_by`` are
UNTRUSTED caller labels (``approver_provenance='caller_supplied_unverified'``).
These records are NOT verified human approvals and must not be treated as
satisfying a §2.6 requirement by future enforcement until provenance is
authenticated.
"""

from app.approvals.states import (
    InvalidApprovalRequest,
    InvalidApprovalTransition,
    RiskTier,
    Status,
    auto_transition,
    compute_deadline,
    is_blocked,
    validate_transition,
)

__all__ = [
    "RiskTier",
    "Status",
    "InvalidApprovalTransition",
    "InvalidApprovalRequest",
    "validate_transition",
    "compute_deadline",
    "auto_transition",
    "is_blocked",
]
