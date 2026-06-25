"""Authority matrix (spec §5.2 + §2.6) and tighten-only override rules.

The matrix is code-defined and version-controlled (security-critical, fixed).
Per-project overrides may only TIGHTEN policy — they can raise ``min_level``, add
an approval requirement, or disable an action; they can never relax it or turn a
§2.6 mandatory-approval action into ALLOW.
"""

from dataclasses import dataclass

from app.policy.levels import AutonomyLevel as L


class PolicyOverrideError(ValueError):
    """Raised when an override is invalid or attempts to relax policy."""


@dataclass(frozen=True)
class AuthorityRule:
    min_level: int
    requires_approval: bool
    mandatory_approval: bool = False  # §2.6: approval can never be cleared


@dataclass(frozen=True)
class EffectiveRule:
    min_level: int
    requires_approval: bool
    disabled: bool = False


def _r(min_level: int, *, approval: bool = False, mandatory: bool = False) -> AuthorityRule:
    return AuthorityRule(int(min_level), approval, mandatory)


# Build/flow actions (no approval) + §2.6 mandatory-approval actions.
MATRIX: dict[str, AuthorityRule] = {
    "read_docs": _r(L.A0),
    # Slice 28: read-only source-control config fetch (branch protection). A read, never a mutation.
    "read_source_control_config": _r(L.A1),
    # Slice 29: read-only pull-request fetch (PR/reviews/checks). A read, never a mutation.
    "read_pull_requests": _r(L.A1),
    # Slice 30: read-only deployment-target status probe (generic_https). A read, never a deploy.
    "read_deployment_target": _r(L.A1),
    # Slice 31: read-only monitoring/alerts status read (generic_monitoring_api). A read, never a write.
    "read_monitoring_status": _r(L.A1),
    # Slice 32: read-only secret-reference existence check (verify exists, spec:1094). A read, never a
    # rotation/mutation (that is the mandatory-approval change_secrets below).
    "verify_secret_reference": _r(L.A1),
    "create_draft_prd": _r(L.A1),
    "create_project_tasks": _r(L.A1),
    "create_repository": _r(L.A2),
    "create_branches": _r(L.A2),
    "commit_code": _r(L.A2),
    "open_pull_requests": _r(L.A2),
    "run_tests": _r(L.A2),
    "deploy_staging": _r(L.A3),
    # §2.6 mandatory-approval (non-relaxable):
    "merge_to_protected": _r(L.A4, approval=True, mandatory=True),
    "deploy_production": _r(L.A4, approval=True, mandatory=True),
    "delete_resources": _r(L.A1, approval=True, mandatory=True),
    "change_secrets": _r(L.A1, approval=True, mandatory=True),
    "modify_billing_or_paid_resources": _r(L.A1, approval=True, mandatory=True),
    "send_external_communications": _r(L.A1, approval=True, mandatory=True),
    "access_sensitive_data": _r(L.A1, approval=True, mandatory=True),
    "accept_risk": _r(L.A1, approval=True, mandatory=True),
    "override_failed_gate": _r(L.A1, approval=True, mandatory=True),
    "weaken_test_or_review_standards": _r(L.A1, approval=True, mandatory=True),
}

_ALLOWED_OVERRIDE_KEYS = {"min_level", "requires_approval", "allow"}


def apply_overrides(base: AuthorityRule, ov: dict | None) -> EffectiveRule:
    """Apply a single action's tighten-only override; raise on relaxing/invalid."""
    if ov is None:
        return EffectiveRule(base.min_level, base.requires_approval, False)
    if not isinstance(ov, dict):
        raise PolicyOverrideError(f"override must be a mapping, got {type(ov).__name__}")
    unknown = set(ov) - _ALLOWED_OVERRIDE_KEYS
    if unknown:
        raise PolicyOverrideError(f"unknown override keys: {sorted(unknown)}")

    min_level = base.min_level
    if "min_level" in ov:
        raw = ov["min_level"]
        # Reject bool explicitly (bool is an int subclass) and any non-int type,
        # so malformed persisted values raise PolicyOverrideError (fail-closed),
        # never a raw TypeError/ValueError that would escape decision_for.
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise PolicyOverrideError("override 'min_level' must be an integer")
        if raw < base.min_level:
            raise PolicyOverrideError("override may not lower min_level")
        if raw > int(L.A5):
            raise PolicyOverrideError("override 'min_level' may not exceed A5")
        min_level = raw

    requires_approval = base.requires_approval
    if "requires_approval" in ov:
        if ov["requires_approval"] is not True:
            raise PolicyOverrideError("override 'requires_approval' may only be set True")
        requires_approval = True

    disabled = False
    if "allow" in ov:
        if ov["allow"] is not False:
            raise PolicyOverrideError("override 'allow' may only be set False (to disable)")
        disabled = True

    return EffectiveRule(min_level, requires_approval, disabled)


def is_mandatory_action(action: str) -> bool:
    """True if `action` is a §2.6 mandatory-approval action (canonical source).

    Additive helper so other slices (e.g. the approval engine) derive the §2.6
    set from this one matrix instead of duplicating a drift-prone list.
    """
    rule = MATRIX.get(action)
    return bool(rule and rule.mandatory_approval)


def validate_overrides(overrides: dict | None) -> None:
    """Validate a whole overrides map (write-time). Raise on unknown action key
    or any invalid/relaxing per-action override."""
    if overrides is None:
        return
    if not isinstance(overrides, dict):
        raise PolicyOverrideError("overrides must be a mapping")
    for action, ov in overrides.items():
        base = MATRIX.get(action)
        if base is None:
            raise PolicyOverrideError(f"unknown action in overrides: {action!r}")
        apply_overrides(base, ov)  # raises on relaxing/invalid
