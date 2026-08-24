"""Tenant-scoped admin grant/action/ledger repositories (Slice 63)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.rbac import RULESET_VERSION, RoleGrantView
from app.models.admin_policy import AdminPolicyChange
from app.models.admin_rbac import AdminAction, AdminRoleGrant
from app.tenancy import TenantContext, TenantScopedRepository


class AdminGrantRepository(TenantScopedRepository):
    """Runtime-readable grants. The runtime role cannot mint rows."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AdminRoleGrant)

    async def active_for_principal(self, principal: str) -> tuple[RoleGrantView, ...]:
        """Return active grants for ``principal`` in this tenant."""
        stmt = select(AdminRoleGrant).where(
            AdminRoleGrant.tenant_id == self.context.tenant_id,
            AdminRoleGrant.principal_subject == principal,
            AdminRoleGrant.status == "active",
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return tuple(
            RoleGrantView(
                tenant_id=row.tenant_id,
                principal_subject=row.principal_subject,
                admin_role=row.admin_role,
                status=row.status,
            )
            for row in rows
        )

    async def list_for_principal(self, principal: str) -> Sequence[AdminRoleGrant]:
        """Return every grant row for ``principal`` in this tenant."""
        stmt = select(AdminRoleGrant).where(
            AdminRoleGrant.tenant_id == self.context.tenant_id,
            AdminRoleGrant.principal_subject == principal,
        )
        return (await self.session.execute(stmt)).scalars().all()


class AdminActionRepository(TenantScopedRepository):
    """Inserts and reads ``admin_actions``."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AdminAction)

    async def record(
        self,
        *,
        project_id: uuid.UUID,
        action_kind: str,
        actor_principal: str,
        actor_provenance: str,
        required_role: str,
        actor_role: str | None,
        decision: str,
    ) -> AdminAction:
        """Persist one authorization decision row."""
        row = AdminAction(
            project_id=project_id,
            action_kind=action_kind,
            actor_principal=actor_principal,
            actor_provenance=actor_provenance,
            required_role=required_role,
            actor_role=actor_role,
            decision=decision,
            ruleset_version=RULESET_VERSION,
        )
        await self.add(row)
        await self.session.flush()
        return row


class AdminPolicyChangeRepository(TenantScopedRepository):
    """Reads the ledger and is the only caller of the gated writer."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AdminPolicyChange)

    async def write_autonomy_policy(
        self,
        *,
        admin_action_id: uuid.UUID,
        project_id: uuid.UUID,
        autonomy_level: int,
        overrides: Mapping[str, Any],
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """Call ``admin_write_autonomy_policy`` and return both ids."""
        result = await self.session.execute(
            text(
                "SELECT * FROM public.admin_write_autonomy_policy("
                ":action_id, :project_id, :level, CAST(:overrides AS jsonb))"
            ),
            {
                "action_id": admin_action_id,
                "project_id": project_id,
                "level": int(autonomy_level),
                "overrides": json.dumps(dict(overrides)),
            },
        )
        row = result.one()
        return row.o_autonomy_policy_id, row.o_admin_policy_change_id

    async def for_action(self, admin_action_id: uuid.UUID) -> AdminPolicyChange | None:
        """Return the ledger row that spent ``admin_action_id``, if any."""
        stmt = select(AdminPolicyChange).where(
            AdminPolicyChange.tenant_id == self.context.tenant_id,
            AdminPolicyChange.admin_action_id == admin_action_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
