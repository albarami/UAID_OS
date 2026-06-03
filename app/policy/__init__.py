"""Autonomy policy engine (Slice 3, §5 / §2.6).

Deterministic, deny-by-default authority decisions: ``check_authority(action,
level, overrides) -> Decision`` over a code-defined authority matrix, with
tighten-only per-project overrides. §2.6 mandatory-approval actions are
structurally non-bypassable.
"""

from app.policy.engine import Decision, PolicyOverrideError, check_authority
from app.policy.levels import AutonomyLevel
from app.policy.matrix import MATRIX, validate_overrides

__all__ = [
    "AutonomyLevel",
    "Decision",
    "PolicyOverrideError",
    "check_authority",
    "MATRIX",
    "validate_overrides",
]
