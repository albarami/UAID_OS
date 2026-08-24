"""Tenant-scoped repository for `autonomy_policies` + policy decisions.

`decision_for` is the fail-closed entry point: missing policy row ⇒ DENY, and an
invalid/relaxing persisted override ⇒ DENY (caught defensively). Policy writes
go through ``app.admin.policy_admin.apply_policy_change``; this repository no
longer writes ``autonomy_policies``.

Must be used inside ``tenant_scope`` (the ``app.current_tenant`` GUC must be set).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.autonomy_policy import AutonomyPolicy
from app.policy.engine import Decision, check_authority
from app.policy.matrix import PolicyOverrideError, validate_overrides
from app.tenancy import TenantContext, TenantScopedRepository


@dataclass(frozen=True)
class PolicyDecisionSnapshot:
    """One locked policy row plus in-process decisions. Not a live re-read."""

    policy_present: bool
    policy_id: uuid.UUID | None
    autonomy_level: int | None
    overrides: Mapping[str, Any]
    decisions: Mapping[str, Decision]


class AutonomyPolicyRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AutonomyPolicy)

    async def get_for_project(self, project_id: uuid.UUID) -> AutonomyPolicy | None:
        stmt = select(AutonomyPolicy).where(
            AutonomyPolicy.project_id == project_id,
            AutonomyPolicy.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def decision_for(self, project_id: uuid.UUID, action: str) -> Decision:
        """Fail-closed authority decision for a project's stored policy."""
        policy = await self.get_for_project(project_id)
        if policy is None:
            return Decision.DENY  # no policy ⇒ deny everything
        try:
            # Validate the WHOLE persisted override map (not just the queried
            # action) so an invalid/relaxing override on any action fails closed.
            validate_overrides(policy.overrides)
            return check_authority(action, policy.autonomy_level, policy.overrides)
        except PolicyOverrideError:
            return Decision.DENY  # fail-closed on any invalid persisted override

    async def snapshot_decisions(
        self, project_id: uuid.UUID, actions: Sequence[str]
    ) -> PolicyDecisionSnapshot:
        """Load one policy row and decide every action in-process.

        Runtime ``uaid_app`` has SELECT only, so this is a plain read — not
        ``FOR SHARE`` (PostgreSQL requires UPDATE for any row-lock clause).
        Missing or invalid policy fails closed to DENY for every requested action.
        """
        stmt = select(AutonomyPolicy).where(
            AutonomyPolicy.project_id == project_id,
            AutonomyPolicy.tenant_id == self.context.tenant_id,
        )
        policy = (await self.session.execute(stmt)).scalar_one_or_none()
        if policy is None:
            return PolicyDecisionSnapshot(
                policy_present=False,
                policy_id=None,
                autonomy_level=None,
                overrides={},
                decisions={action: Decision.DENY for action in actions},
            )
        try:
            validate_overrides(policy.overrides)
            decisions = {
                action: check_authority(action, policy.autonomy_level, policy.overrides)
                for action in actions
            }
        except PolicyOverrideError:
            decisions = {action: Decision.DENY for action in actions}
        return PolicyDecisionSnapshot(
            policy_present=True,
            policy_id=policy.id,
            autonomy_level=int(policy.autonomy_level),
            overrides=dict(policy.overrides or {}),
            decisions=decisions,
        )
