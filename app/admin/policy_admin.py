"""Runtime service for role-gated autonomy-policy changes (Slice 63)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.rbac import (
    AdminActionRequest,
    AuthorizationDecision,
    evaluate_authorization,
    required_role_for,
    validate_action_kind,
)
from app.audit import record as audit_record
from app.identity import CALLER_SUPPLIED_UNVERIFIED, REQUEST_AUTHENTICATED
from app.policy.matrix import validate_overrides
from app.repositories.admin import (
    AdminActionRepository,
    AdminGrantRepository,
    AdminPolicyChangeRepository,
)
from app.tenancy import TenantContext, tenant_scope


@dataclass(frozen=True)
class PolicyChangeResult:
    """Outcome of one ``apply_policy_change`` call."""

    decision: AuthorizationDecision
    admin_action_id: uuid.UUID
    autonomy_policy_id: uuid.UUID | None
    admin_policy_change_id: uuid.UUID | None


def _actor_fields(ctx: TenantContext) -> tuple[str, str]:
    if ctx.actor is not None:
        return ctx.actor.subject, REQUEST_AUTHENTICATED
    return "", CALLER_SUPPLIED_UNVERIFIED


async def apply_policy_change(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    project_id: uuid.UUID,
    action_kind: str,
    autonomy_level: int,
    overrides: Mapping[str, Any] | None = None,
) -> PolicyChangeResult:
    """Evaluate, record, and (if allowed) write a policy change.

    ``validate_overrides`` runs before any row is recorded. A relaxing map
    raises ``PolicyOverrideError`` with no ``admin_actions`` residue.
    """
    kind = validate_action_kind(action_kind)
    override_map = dict(overrides or {})
    validate_overrides(override_map)
    principal, provenance = _actor_fields(ctx)
    grants = await AdminGrantRepository(session, ctx).active_for_principal(principal)
    decision = evaluate_authorization(
        AdminActionRequest(
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            action_kind=kind,
            actor_principal=principal or "unauthenticated",
            actor_provenance=provenance,
        ),
        grants,
    )
    action = await AdminActionRepository(session, ctx).record(
        project_id=project_id,
        action_kind=kind,
        actor_principal=principal or "unauthenticated",
        actor_provenance=provenance,
        required_role=required_role_for(kind),
        actor_role=decision.actor_role,
        decision=decision.decision,
    )
    await audit_record(
        session,
        action="admin_action.recorded",
        actor=principal or "unauthenticated",
        target=f"project:{project_id}",
        payload={
            "admin_action_id": str(action.id),
            "action_kind": kind,
            "decision": decision.decision,
            "required_role": decision.required_role,
            "actor_role": decision.actor_role,
            "actor_provenance": provenance,
        },
    )
    if decision.decision != "allowed":
        return PolicyChangeResult(
            decision=decision,
            admin_action_id=action.id,
            autonomy_policy_id=None,
            admin_policy_change_id=None,
        )
    changes = AdminPolicyChangeRepository(session, ctx)
    policy_id, change_id = await changes.write_autonomy_policy(
        admin_action_id=action.id,
        project_id=project_id,
        autonomy_level=int(autonomy_level),
        overrides=override_map,
    )
    ledger = await changes.for_action(action.id)
    await audit_record(
        session,
        action="admin_policy_change.recorded",
        actor=principal,
        target=f"project:{project_id}",
        payload={
            "admin_policy_change_id": str(change_id),
            "autonomy_policy_id": str(policy_id),
            "previous_autonomy_level": (
                ledger.previous_autonomy_level if ledger is not None else None
            ),
            "new_autonomy_level": (
                ledger.new_autonomy_level if ledger is not None else int(autonomy_level)
            ),
            "override_key_count": (
                ledger.override_key_count if ledger is not None else len(override_map)
            ),
        },
    )
    return PolicyChangeResult(
        decision=decision,
        admin_action_id=action.id,
        autonomy_policy_id=policy_id,
        admin_policy_change_id=change_id,
    )


async def apply_policy_change_in_scope(
    ctx: TenantContext,
    *,
    project_id: uuid.UUID,
    action_kind: str,
    autonomy_level: int,
    overrides: Mapping[str, Any] | None = None,
) -> PolicyChangeResult:
    """Open ``tenant_scope`` and apply a policy change."""
    async with tenant_scope(ctx) as session:
        return await apply_policy_change(
            session,
            ctx,
            project_id=project_id,
            action_kind=action_kind,
            autonomy_level=autonomy_level,
            overrides=overrides,
        )
