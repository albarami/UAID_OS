"""Tenant-scoped repositories for the tool broker (Slice 5).

`ToolAllowlistRepository` is an append-only grant/revoke ledger; `is_allowed`
reads the latest event. `ToolCallRepository.record` writes the immutable tool-call
record and an audit-log entry (never including params). Both run inside
``tenant_scope`` (GUC set). `agent_id`/`actor` are untrusted caller labels.
"""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.agent_tool_allowlist import AgentToolAllowlist
from app.models.tool_call import ToolCall
from app.tenancy import TenantContext, TenantScopedRepository


class ToolAllowlistRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AgentToolAllowlist)

    async def grant(self, *, agent_id: str, tool_name: str, actor: str, reason: str | None = None):
        await self._event(agent_id, tool_name, "grant", actor, reason)

    async def revoke(self, *, agent_id: str, tool_name: str, actor: str, reason: str | None = None):
        await self._event(agent_id, tool_name, "revoke", actor, reason)

    async def is_allowed(self, agent_id: str, tool_name: str) -> bool:
        stmt = (
            select(AgentToolAllowlist.event_type)
            .where(
                AgentToolAllowlist.tenant_id == self.context.tenant_id,
                AgentToolAllowlist.agent_id == agent_id,
                AgentToolAllowlist.tool_name == tool_name,
            )
            .order_by(desc(AgentToolAllowlist.seq))
            .limit(1)
        )
        latest = (await self.session.execute(stmt)).scalar_one_or_none()
        return latest == "grant"  # deny-by-default when no events

    async def _event(self, agent_id, tool_name, event_type, actor, reason):
        row = AgentToolAllowlist(
            agent_id=agent_id,
            tool_name=tool_name,
            event_type=event_type,
            actor=actor,
            reason=reason,
        )
        await self.add(row)  # stamps tenant_id
        await self.session.flush()
        await audit_record(
            self.session,
            action=f"tool_allowlist.{event_type}",
            actor=actor,
            target=f"agent:{agent_id}/tool:{tool_name}",
            payload={"agent_id": agent_id, "tool_name": tool_name, "event_type": event_type},
        )


class ToolCallRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ToolCall)

    async def record(
        self,
        *,
        project_id: uuid.UUID,
        agent_id: str,
        tool_name: str,
        action: str | None,
        decision: str,
        reason: str | None,
        params: Mapping[str, Any],
    ) -> ToolCall:
        call = ToolCall(
            project_id=project_id,
            agent_id=agent_id,
            tool_name=tool_name,
            action=action,
            decision=decision,
            reason=reason,
            params=dict(params),
        )
        await self.add(call)  # stamps tenant_id
        await self.session.flush()
        # Audit every brokered call. NEVER include params in the audit payload.
        await audit_record(
            self.session,
            action=f"tool_call.{decision}",
            actor=agent_id,
            target=f"tool:{tool_name}",
            payload={
                "project_id": str(project_id),
                "agent_id": agent_id,
                "agent_provenance": call.agent_provenance,
                "tool_name": tool_name,
                "action": action,
                "decision": decision,
                "reason": reason,
            },
        )
        return call
