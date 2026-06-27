"""Tenant-scoped agent-realization repository (Slice 39, §9.4 bind + register).

``realize`` writes **tenant rows only** (B1 — blueprint/version registration is an admin-path
precondition): it reuses ``AgentInstanceRepository.instantiate`` to create the instance for an
already-registered ``version_id``, grants the instance-scoped tool allowlist via the existing
``ToolAllowlistRepository`` (keyed by ``str(instance.id)``), inserts an ``agent_realizations`` record
stamped ``unqualified`` (B4 — qualification is Slice 40), and inserts FK-backed reviewer links (the DB
self-review guard refuses a reviewer equal to the realized blueprint, §2.2/B3). Audit safe-metadata only.
Run inside ``tenant_scope``. ``realized_by`` is an UNTRUSTED label.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.factory import REALIZE_INSERT_STATUS, validate_realization_request
from app.agents.registry import AgentInstanceRepository
from app.audit import record as audit_record
from app.models.agent_realization import AgentRealization, AgentRealizationReviewer
from app.repositories.tools import ToolAllowlistRepository
from app.tenancy import TenantContext, TenantScopedRepository


class AgentRealizationRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AgentRealization)

    async def realize(
        self,
        *,
        project_id: uuid.UUID,
        version_id: uuid.UUID,
        instance_key: str,
        tool_allowlist: Sequence[str],
        reviewer_blueprint_ids: Sequence[uuid.UUID],
        realized_by: str,
    ) -> AgentRealization:
        validate_realization_request(
            instance_key=instance_key,
            tool_allowlist=tool_allowlist,
            reviewer_blueprint_ids=reviewer_blueprint_ids,
        )
        instance = await AgentInstanceRepository(self.session, self.context).instantiate(
            project_id=project_id,
            version_id=version_id,
            instance_key=instance_key,
            actor=realized_by,
        )
        allowlist = ToolAllowlistRepository(self.session, self.context)
        for tool in tool_allowlist:
            await allowlist.grant(
                agent_id=str(instance.id), tool_name=tool, actor=realized_by, reason="realized"
            )
        realization = AgentRealization(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            instance_id=instance.id,
            qualification_status=REALIZE_INSERT_STATUS,
            realized_by=realized_by,
        )
        self.session.add(realization)
        await self.session.flush()
        for bp_id in reviewer_blueprint_ids:
            self.session.add(
                AgentRealizationReviewer(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    realization_id=realization.id,
                    reviewer_blueprint_id=uuid.UUID(str(bp_id)),
                )
            )
        await self.session.flush()
        await audit_record(
            self.session,
            action="agent.realized",
            actor=realized_by,
            target=f"agent_realization:{realization.id}",
            payload={
                "agent_realization_id": str(realization.id),
                "instance_id": str(instance.id),
                "project_id": str(project_id),
                "version_id": str(version_id),
                "qualification_status": REALIZE_INSERT_STATUS,
                "tool_count": len(list(tool_allowlist)),
                "reviewer_count": len(list(reviewer_blueprint_ids)),
            },
        )
        return realization

    async def for_instance(self, instance_id: uuid.UUID) -> AgentRealization | None:
        stmt = select(AgentRealization).where(
            AgentRealization.tenant_id == self.context.tenant_id,
            AgentRealization.instance_id == instance_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def for_project(self, project_id: uuid.UUID) -> Sequence[AgentRealization]:
        stmt = (
            select(AgentRealization)
            .where(
                AgentRealization.tenant_id == self.context.tenant_id,
                AgentRealization.project_id == project_id,
            )
            .order_by(AgentRealization.created_at.desc(), AgentRealization.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def reviewers_of(self, realization_id: uuid.UUID) -> Sequence[AgentRealizationReviewer]:
        stmt = (
            select(AgentRealizationReviewer)
            .where(
                AgentRealizationReviewer.tenant_id == self.context.tenant_id,
                AgentRealizationReviewer.realization_id == realization_id,
            )
            .order_by(AgentRealizationReviewer.created_at, AgentRealizationReviewer.id)
        )
        return (await self.session.execute(stmt)).scalars().all()
