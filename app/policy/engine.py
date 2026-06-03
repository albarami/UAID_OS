"""Pure authority decision (spec §5.2). Deny-by-default; tighten-only overrides.

``check_authority`` is pure (no I/O) and MAY raise ``PolicyOverrideError`` on an
invalid/relaxing override (for test visibility). The fail-closed wrapper lives in
the repository (``decision_for`` catches it and returns DENY).
"""

from enum import Enum

from app.policy.levels import AutonomyLevel
from app.policy.matrix import MATRIX, PolicyOverrideError, apply_overrides

__all__ = ["Decision", "PolicyOverrideError", "check_authority"]


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


def check_authority(
    action: str,
    level: AutonomyLevel | int,
    overrides: dict | None = None,
) -> Decision:
    base = MATRIX.get(action)
    if base is None:
        return Decision.DENY  # deny-by-default for unknown actions
    rule = apply_overrides(base, (overrides or {}).get(action))  # may raise
    if rule.disabled:
        return Decision.DENY
    if int(level) < rule.min_level:
        return Decision.DENY
    if rule.requires_approval:
        return Decision.NEEDS_APPROVAL
    return Decision.ALLOW
