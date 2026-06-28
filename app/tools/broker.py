"""The tool broker decision pipeline (Slice 5 §11; Slice 39 broker↔instance wiring). Deny-by-default.

Two entry points share one fail-closed pipeline (``_broker``):
- ``broker_call`` — the **agent** path: ``agent_id`` MUST resolve to a real, SAME-PROJECT
  ``agent_instance`` (D-39-3/B7) and the instance must be **qualified** (D-39-4; qualification is
  Slice 40, so this always denies for now). A free-string / cross-project / unknown agent ⇒
  ``DENIED_UNKNOWN_AGENT``; a realized-but-unqualified agent ⇒ ``DENIED_UNQUALIFIED_AGENT``.
- ``broker_call_service`` — the **platform-service** path (release connectors): ``service_id`` is a
  service identity (e.g. ``service:ci_evidence``), NOT an agent. It SKIPS the agent identity +
  qualification gates but keeps every safety gate (sanitize → known-tool → allowlist → policy →
  approval → success). This is service authority, not agent authority.

Shared safety: params sanitized/redacted before any recording; unverified approval never authorizes
(``NEEDS_AUTHENTICATED_APPROVAL``); the success terminal is ``ALLOWED_UNVERIFIED_IDENTITY`` (never bare
ALLOWED). Records EVERY attempt to ``tool_calls`` + the audit log. No real execution.
"""

import uuid
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_instance import AgentInstance
from app.policy.engine import Decision
from app.repositories.agent_realizations import AgentRealizationRepository
from app.repositories.approvals import ApprovalRepository
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.tools import ToolAllowlistRepository, ToolCallRepository
from app.tenancy import TenantContext
from app.tools.registry import InvalidParams, get_contract, sanitize_params

_APPROVED = "approved"
# Provenance values that count as authenticated human approval. EMPTY: the broker is NOT wired to
# Slice 27 request-auth identity (D-27-4), so every approval — even the `request_authenticated`
# tier — is treated as unverified (fail-closed) ⇒ NEEDS_AUTHENTICATED_APPROVAL.
_AUTHENTICATED_APPROVAL_PROVENANCES: frozenset[str] = frozenset()
_RESOLVABLE_INSTANCE_STATUSES = ("registered", "active")


class BrokerDecision(Enum):
    ALLOWED_UNVERIFIED_IDENTITY = "allowed_unverified_identity"
    NEEDS_APPROVAL = "needs_approval"
    NEEDS_AUTHENTICATED_APPROVAL = "needs_authenticated_approval"
    DENIED_UNKNOWN_TOOL = "denied_unknown_tool"
    DENIED_INVALID_PARAMS = "denied_invalid_params"
    DENIED_NOT_ALLOWLISTED = "denied_not_allowlisted"
    DENIED_POLICY = "denied_policy"
    # Slice 39 — broker↔instance wiring (agent identity + qualification gates).
    DENIED_UNKNOWN_AGENT = "denied_unknown_agent"
    DENIED_UNQUALIFIED_AGENT = "denied_unqualified_agent"


async def _resolve_instance(session, context, agent_id, project_id):
    """Resolve agent_id → a real SAME-PROJECT instance (B7): id + tenant + project + active status.
    A same-tenant/different-project instance (or a non-UUID / suspended / retired) yields None."""
    try:
        iid = uuid.UUID(agent_id)
    except (ValueError, AttributeError, TypeError):
        return None
    stmt = select(AgentInstance).where(
        AgentInstance.id == iid,
        AgentInstance.tenant_id == context.tenant_id,
        AgentInstance.project_id == project_id,
        AgentInstance.status.in_(_RESOLVABLE_INSTANCE_STATUSES),
    )
    return (await session.execute(stmt)).scalars().first()


async def broker_call(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    agent_id: str,
    tool_name: str,
    params: Any = None,
) -> BrokerDecision:
    """AGENT path — agent_id must be a real, same-project, qualified instance. Run inside tenant_scope."""
    return await _broker(
        session,
        context,
        project_id=project_id,
        actor_id=agent_id,
        tool_name=tool_name,
        params=params,
        resolve_agent=True,
    )


async def broker_call_service(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    service_id: str,
    tool_name: str,
    params: Any = None,
) -> BrokerDecision:
    """PLATFORM-SERVICE path (release connectors) — service_id is a service identity (not an agent).
    Skips the agent identity + qualification gates; keeps sanitize/known-tool/allowlist/policy/approval.
    Run inside tenant_scope."""
    return await _broker(
        session,
        context,
        project_id=project_id,
        actor_id=service_id,
        tool_name=tool_name,
        params=params,
        resolve_agent=False,
    )


async def _broker(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    actor_id: str,
    tool_name: str,
    params: Any,
    resolve_agent: bool,
) -> BrokerDecision:
    calls = ToolCallRepository(session, context)
    allowlist = ToolAllowlistRepository(session, context)
    autonomy = AutonomyPolicyRepository(session, context)
    approvals = ApprovalRepository(session, context)

    async def _decide(
        decision: BrokerDecision, *, action, reason, params_to_store
    ) -> BrokerDecision:
        # ToolCall.agent_id is the legacy actor column — it carries the agent_id (agent path) or the
        # service_id (service path); both are unverified caller-supplied labels.
        await calls.record(
            project_id=project_id,
            agent_id=actor_id,
            tool_name=tool_name,
            action=action,
            decision=decision.value,
            reason=reason,
            params=params_to_store,
        )
        return decision

    # 1. Validate/redact params before ANY recording.
    try:
        clean = sanitize_params(params if params is not None else {})
    except InvalidParams as exc:
        return await _decide(
            BrokerDecision.DENIED_INVALID_PARAMS,
            action=None,
            reason=f"invalid_params:{exc.kind}",
            params_to_store={},
        )

    # 2. Deny-by-default unknown tool.
    contract = get_contract(tool_name)
    if contract is None:
        return await _decide(
            BrokerDecision.DENIED_UNKNOWN_TOOL,
            action=None,
            reason="unknown_tool",
            params_to_store=clean,
        )
    action = contract.required_action

    # 3-4. Agent path only: resolve a real same-project instance + the qualification gate.
    if resolve_agent:
        instance = await _resolve_instance(session, context, actor_id, project_id)
        if instance is None:
            return await _decide(
                BrokerDecision.DENIED_UNKNOWN_AGENT,
                action=action,
                reason="unknown_agent",
                params_to_store=clean,
            )
        realization = await AgentRealizationRepository(session, context).for_instance(instance.id)
        if realization is None or realization.qualification_status != "qualified":
            return await _decide(
                BrokerDecision.DENIED_UNQUALIFIED_AGENT,
                action=action,
                reason="unqualified_agent",
                params_to_store=clean,
            )
        allowlist_key = str(instance.id)  # instance-scoped (D-39-5)
    else:
        allowlist_key = actor_id  # service-scoped

    # 5. Allowlist (instance-scoped for agents, service-scoped for services).
    if not await allowlist.is_allowed(allowlist_key, tool_name):
        return await _decide(
            BrokerDecision.DENIED_NOT_ALLOWLISTED,
            action=action,
            reason="not_allowlisted",
            params_to_store=clean,
        )

    # 6. Authority (Slice 3).
    decision = await autonomy.decision_for(project_id, action)
    if decision is Decision.DENY:
        return await _decide(
            BrokerDecision.DENIED_POLICY, action=action, reason="policy_deny", params_to_store=clean
        )

    # 7. Approval gate (Slice 4), tool-scoped + provenance-aware.
    if contract.requires_approval or decision is Decision.NEEDS_APPROVAL:
        approval = await approvals.latest_for(project_id, action, subject_ref=f"tool:{tool_name}")
        if approval is None or approval.status != _APPROVED:
            return await _decide(
                BrokerDecision.NEEDS_APPROVAL,
                action=action,
                reason="approval_required",
                params_to_store=clean,
            )
        if approval.approver_provenance not in _AUTHENTICATED_APPROVAL_PROVENANCES:
            # Fail-closed: ANY provenance not on the (empty) authenticated allowlist is unverified.
            return await _decide(
                BrokerDecision.NEEDS_AUTHENTICATED_APPROVAL,
                action=action,
                reason="approval_provenance_unverified",
                params_to_store=clean,
            )

    # 8. Identity is unverified in this skeleton ⇒ never bare ALLOWED.
    return await _decide(
        BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,
        action=action,
        reason="ok",
        params_to_store=clean,
    )
