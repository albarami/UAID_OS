"""Connector orchestration (Slice 28) — broker-gated, repo-bound, fail-closed.

``refresh_branch_protection``: resolve the project's OWN declared repo (D-28-11) → broker decision with
**safe params** (no raw ``repo_ref``, D-28-12) → fetch via the injected connector (Fake in tests) → on
a verified GitHub 200, write a ``connector_verified`` snapshot (D-28-4/8). Any missing config /
non-ALLOW / fetch failure / no-protection ⇒ **no write** (audited failure, safe metadata only).
Admin/internal — **no HTTP endpoint** (D-28-7). ``actor`` is an untrusted caller label.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.release.project_repo import has_declared_credential, resolve_declared_repo
from app.release.scm_connector import SCMConnector, SCMConnectorError
from app.repositories.ci_evidence import CIEvidenceRepository
from app.tenancy import TenantContext
from app.tools.broker import BrokerDecision, broker_call_service

_ALLOWED = (BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,)
_TOOL = "source_control.read_branch_protection"


@dataclass
class RefreshResult:
    wrote: bool
    reason: str
    decision: BrokerDecision | None = None
    snapshot_id: uuid.UUID | None = None


async def _audit_failure(
    session: AsyncSession, actor: str, project_id: uuid.UUID, branch: str | None, reason: str
) -> None:
    # Safe metadata only — NEVER repo_ref / token / URL.
    await audit_record(
        session,
        action="ci.branch_protection_fetch_failed",
        actor=actor,
        target=f"project:{project_id}",
        payload={"project_id": str(project_id), "branch": branch, "reason": reason},
    )


async def refresh_branch_protection(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    agent_id: str,
    actor: str,
    connector: SCMConnector,
) -> RefreshResult:
    """Broker-gated, repo-bound branch-protection refresh. Returns a ``RefreshResult``; writes a
    ``connector_verified`` snapshot only on a clean verified fetch."""
    # 1. Resolve the project's OWN declared repo + credential source (fail-closed).
    resolved = await resolve_declared_repo(session, context, project_id)
    if resolved is None:
        await _audit_failure(session, actor, project_id, None, "repo_unbound")
        return RefreshResult(False, "repo_unbound")
    repo_ref, branch = resolved
    if not await has_declared_credential(session, context, project_id):
        await _audit_failure(session, actor, project_id, branch, "credential_unbound")
        return RefreshResult(False, "credential_unbound")

    # 2. Broker decision — SAFE params only (no raw repo_ref enters tool_calls.params).
    decision = await broker_call_service(
        session,
        context,
        project_id=project_id,
        service_id=agent_id,
        tool_name=_TOOL,
        params={"provider": "github", "branch": branch, "repo_ref_present": True},
    )
    if decision not in _ALLOWED:
        return RefreshResult(False, "broker_denied", decision=decision)

    # 3. Fetch (Fake in tests). Any failure / no-protection ⇒ no verified write.
    try:
        mapped = await connector.fetch_branch_protection(repo_ref=repo_ref, branch=branch)
    except SCMConnectorError:
        await _audit_failure(session, actor, project_id, branch, "connector_error")
        return RefreshResult(False, "connector_error", decision=decision)
    if mapped is None:
        await _audit_failure(session, actor, project_id, branch, "no_protection")
        return RefreshResult(False, "no_protection", decision=decision)

    # 4. Verify + write a connector_verified snapshot (repo_ref/branch from the declaration, not params).
    payload = {
        **mapped,
        "repo_ref": repo_ref,
        "branch": branch,
        "observed_at": datetime.now(timezone.utc),
    }
    row = await CIEvidenceRepository(session, context).record_connector_verified_branch_protection(
        project_id=project_id, payload=payload, actor=actor
    )
    return RefreshResult(True, "verified", decision=decision, snapshot_id=row.id)
