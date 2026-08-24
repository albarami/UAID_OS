"""Pure RBAC vocabulary and authorization (§OD-1/§OD-2/§OD-3).

A decision is a ranking aid over recorded grants. It is not a human signature,
organizational authority, or go-live authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

ADMIN_ROLES = ("tenant_viewer", "tenant_operator", "tenant_admin")
ROLE_RANKS = {"tenant_viewer": 1, "tenant_operator": 2, "tenant_admin": 3}
ADMIN_ACTION_KINDS = ("set_autonomy_policy", "tighten_autonomy_overrides")
ACTION_REQUIRED_ROLE = {
    "set_autonomy_policy": "tenant_admin",
    "tighten_autonomy_overrides": "tenant_operator",
}
DECISIONS = (
    "allowed",
    "refused_unauthenticated_actor",
    "refused_no_grant",
    "refused_insufficient_role",
)
RULESET_VERSION = "slice63.v1"
REQUEST_AUTHENTICATED = "request_authenticated"
CALLER_SUPPLIED_UNVERIFIED = "caller_supplied_unverified"
ACTOR_PROVENANCES = (CALLER_SUPPLIED_UNVERIFIED, REQUEST_AUTHENTICATED)
OPERATOR_PROVENANCE = "operator_admin_session_unverified"
PRINCIPAL_MAX_LEN = 255
GRANTED_BY_MAX_LEN = 200
PERFORMED_BY_MAX_LEN = 200


class AdminRbacError(ValueError):
    """Raised when an RBAC input is unknown or out of bounds."""


@dataclass(frozen=True)
class AdminActionRequest:
    """One requested admin action. ``actor_role`` is not caller-chosen here."""

    tenant_id: UUID
    project_id: UUID
    action_kind: str
    actor_principal: str
    actor_provenance: str


@dataclass(frozen=True)
class RoleGrantView:
    """One recorded grant. Only ``status='active'`` grants count."""

    tenant_id: UUID
    principal_subject: str
    admin_role: str
    status: str


@dataclass(frozen=True)
class AuthorizationDecision:
    """Frozen §OD-3 partition. ``ruleset_version`` is always ``slice63.v1``."""

    decision: str
    required_role: str
    actor_role: str | None
    ruleset_version: str = RULESET_VERSION


def validate_principal(
    value: object, *, field: str = "actor_principal", max_len: int = PRINCIPAL_MAX_LEN
) -> str:
    """Return a bounded non-blank principal, or raise ``AdminRbacError``."""
    if not isinstance(value, str):
        raise AdminRbacError(f"{field} must be a non-empty string")
    stripped = value.strip()
    if not stripped or len(value) > max_len:
        raise AdminRbacError(f"{field} must be 1..{max_len} non-blank characters")
    return value


def validate_action_kind(action_kind: object) -> str:
    """Return a known action kind, or raise."""
    if action_kind not in ADMIN_ACTION_KINDS:
        raise AdminRbacError(f"unknown action_kind: {action_kind!r}")
    return str(action_kind)


def validate_admin_role(admin_role: object) -> str:
    """Return a known admin role, or raise."""
    if admin_role not in ADMIN_ROLES:
        raise AdminRbacError(f"unknown admin_role: {admin_role!r}")
    return str(admin_role)


def required_role_for(action_kind: str) -> str:
    """Return the required role for ``action_kind``."""
    return ACTION_REQUIRED_ROLE[validate_action_kind(action_kind)]


def evaluate_authorization(
    request: AdminActionRequest, grants: tuple[RoleGrantView, ...]
) -> AuthorizationDecision:
    """Partition the real grant state (§OD-3). Unknown inputs raise."""
    kind = validate_action_kind(request.action_kind)
    principal = validate_principal(request.actor_principal)
    if request.actor_provenance not in ACTOR_PROVENANCES:
        raise AdminRbacError(f"unknown actor_provenance: {request.actor_provenance!r}")
    required = ACTION_REQUIRED_ROLE[kind]
    if request.actor_provenance != REQUEST_AUTHENTICATED:
        return AuthorizationDecision(
            decision="refused_unauthenticated_actor",
            required_role=required,
            actor_role=None,
        )
    active = [
        grant
        for grant in grants
        if grant.tenant_id == request.tenant_id
        and grant.principal_subject == principal
        and grant.status == "active"
    ]
    for grant in active:
        validate_admin_role(grant.admin_role)
    if not active:
        return AuthorizationDecision(
            decision="refused_no_grant", required_role=required, actor_role=None
        )
    held = max(active, key=lambda grant: ROLE_RANKS[grant.admin_role])
    if ROLE_RANKS[held.admin_role] < ROLE_RANKS[required]:
        return AuthorizationDecision(
            decision="refused_insufficient_role",
            required_role=required,
            actor_role=held.admin_role,
        )
    return AuthorizationDecision(
        decision="allowed", required_role=required, actor_role=held.admin_role
    )
