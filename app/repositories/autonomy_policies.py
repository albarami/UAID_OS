"""Tenant-scoped repository for `autonomy_policies` + policy decisions.

`decision_for` is the fail-closed entry point: missing policy row ⇒ DENY, and an
invalid/relaxing persisted override ⇒ DENY (caught defensively). `upsert`
validates overrides at write time (rejecting relaxing ones) and records an audit
event in the same tenant-scoped transaction.

Must be used inside ``tenant_scope`` (the ``app.current_tenant`` GUC must be set;
the audit append derives the tenant from it and fails closed otherwise).
"""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.autonomy_policy import AutonomyPolicy
from app.policy.engine import Decision, check_authority
from app.policy.matrix import PolicyOverrideError, validate_overrides
from app.tenancy import TenantContext, TenantScopedRepository


class AutonomyPolicyRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AutonomyPolicy)

    async def get_for_project(self, project_id: uuid.UUID) -> AutonomyPolicy | None:
        stmt = select(AutonomyPolicy).where(
            AutonomyPolicy.project_id == project_id,
            AutonomyPolicy.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        *,
        project_id: uuid.UUID,
        autonomy_level: int,
        overrides: Mapping[str, Any] | None = None,
        actor: str,
    ) -> AutonomyPolicy:
        """Create or update a project's policy. Rejects relaxing overrides; audits.

        ``actor`` is an UNTRUSTED, caller-supplied label (not authenticated
        identity) until the request-auth slice — do not treat it as verified.
        """
        overrides = dict(overrides or {})
        validate_overrides(overrides)  # raises PolicyOverrideError on relaxing/invalid

        existing = await self.get_for_project(project_id)
        previous_level = existing.autonomy_level if existing else None
        if existing is not None:
            existing.autonomy_level = int(autonomy_level)
            existing.overrides = overrides
            policy = existing
        else:
            policy = AutonomyPolicy(
                project_id=project_id,
                autonomy_level=int(autonomy_level),
                overrides=overrides,
            )
            await self.add(policy)  # stamps tenant_id from the context
        await self.session.flush()

        # Audit the change in the same tenant-scoped transaction (tenant from GUC).
        # Safe metadata only: no secret values, only changed override KEYS.
        await audit_record(
            self.session,
            action="autonomy_policy.upserted",
            actor=actor,
            target=f"project:{project_id}",
            payload={
                "project_id": str(project_id),
                "previous_level": previous_level,
                "new_level": int(autonomy_level),
                "changed_override_keys": sorted(overrides.keys()),
            },
        )
        return policy

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
