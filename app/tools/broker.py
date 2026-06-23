"""The tool broker decision pipeline (Slice 5, §11). Deny-by-default, fail-closed.

Composes the Slice 3 policy engine and Slice 4 approval engine. Records EVERY
attempt (allowed or denied) to `tool_calls` + the audit log. No real execution.

Two provenance gates keep this a safe skeleton:
- approval: an unverified approval never authorizes ⇒ NEEDS_AUTHENTICATED_APPROVAL;
- identity: the success terminal is ALLOWED_UNVERIFIED_IDENTITY, not bare ALLOWED.
"""

import uuid
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.engine import Decision
from app.repositories.approvals import ApprovalRepository
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.tools import ToolAllowlistRepository, ToolCallRepository
from app.tenancy import TenantContext
from app.tools.registry import InvalidParams, get_contract, sanitize_params

_APPROVED = "approved"
# Provenance values that count as authenticated human approval. EMPTY: the broker is NOT
# wired to Slice 27 request-auth identity (D-27-4), so every approval — even the
# `request_authenticated` tier — is treated as unverified (fail-closed):
# any provenance not in this set ⇒ NEEDS_AUTHENTICATED_APPROVAL.
_AUTHENTICATED_APPROVAL_PROVENANCES: frozenset[str] = frozenset()


class BrokerDecision(Enum):
    ALLOWED_UNVERIFIED_IDENTITY = "allowed_unverified_identity"
    NEEDS_APPROVAL = "needs_approval"
    NEEDS_AUTHENTICATED_APPROVAL = "needs_authenticated_approval"
    DENIED_UNKNOWN_TOOL = "denied_unknown_tool"
    DENIED_INVALID_PARAMS = "denied_invalid_params"
    DENIED_NOT_ALLOWLISTED = "denied_not_allowlisted"
    DENIED_POLICY = "denied_policy"


async def broker_call(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    agent_id: str,
    tool_name: str,
    params: Any = None,
) -> BrokerDecision:
    """Brokered tool-call decision. Must run inside ``tenant_scope`` (GUC set)."""
    calls = ToolCallRepository(session, context)
    allowlist = ToolAllowlistRepository(session, context)
    autonomy = AutonomyPolicyRepository(session, context)
    approvals = ApprovalRepository(session, context)

    async def _decide(
        decision: BrokerDecision, *, action, reason, params_to_store
    ) -> BrokerDecision:
        await calls.record(
            project_id=project_id,
            agent_id=agent_id,
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

    # 3. Per-agent allowlist.
    if not await allowlist.is_allowed(agent_id, tool_name):
        return await _decide(
            BrokerDecision.DENIED_NOT_ALLOWLISTED,
            action=action,
            reason="not_allowlisted",
            params_to_store=clean,
        )

    # 4. Authority (Slice 3).
    decision = await autonomy.decision_for(project_id, action)
    if decision is Decision.DENY:
        return await _decide(
            BrokerDecision.DENIED_POLICY, action=action, reason="policy_deny", params_to_store=clean
        )

    # 5. Approval gate (Slice 4), tool-scoped + provenance-aware.
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
            # Fail-closed: ANY provenance not on the authenticated allowlist (which
            # is empty in Slice 5) is treated as unverified — including arbitrary or
            # malformed values. Never let a non-default string masquerade as authority.
            return await _decide(
                BrokerDecision.NEEDS_AUTHENTICATED_APPROVAL,
                action=action,
                reason="approval_provenance_unverified",
                params_to_store=clean,
            )
        # (authenticated APPROVED — not reachable until request-auth defines a
        #  provenance value and adds it to _AUTHENTICATED_APPROVAL_PROVENANCES)

    # 6. Identity is unverified in this skeleton ⇒ never bare ALLOWED.
    return await _decide(
        BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,
        action=action,
        reason="ok",
        params_to_store=clean,
    )
