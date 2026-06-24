"""PR-evidence connector orchestration (Slice 29) — broker-gated, repo-bound, fail-closed.

``refresh_pull_request_evidence``: resolve the project's OWN declared repo (D-29-3) → broker decision
with **safe params** (no raw ``repo_ref``; ``pr_number`` is safe) → fetch via the injected connector
(Fake in tests) → on a verified PR+reviews fetch, write a ``connector_verified`` snapshot. Any missing
config / non-ALLOW / fetch failure (incl. a mandatory PR/reviews-endpoint failure, B-29-7) ⇒ **no write**
(audited failure, safe metadata only). Optional caller-supplied ``presence_flags`` / ``traceability_refs``
are validated + written with their ``caller_declared`` source labels preserved (B-29-4) — a
``connector_verified`` snapshot NEVER promotes a caller_declared §12.4 flag to provider-verified adequacy.
Admin/internal — **no HTTP endpoint** (D-29-7). Store-only: no A5 gate flip / ``production_autonomy``
change. ``actor`` is an untrusted caller label.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.release.project_repo import has_declared_credential, resolve_declared_repo
from app.release.scm_connector import SCMConnector, SCMConnectorError
from app.repositories.pr_evidence import PullRequestEvidenceRepository
from app.tenancy import TenantContext
from app.tools.broker import BrokerDecision, broker_call

_ALLOWED = (BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,)
_TOOL = "source_control.read_pull_request"


@dataclass
class RefreshResult:
    wrote: bool
    reason: str
    decision: BrokerDecision | None = None
    snapshot_id: uuid.UUID | None = None


async def _audit_failure(
    session: AsyncSession, actor: str, project_id: uuid.UUID, pr_number: int, reason: str
) -> None:
    # Safe metadata only — NEVER repo_ref / token / URL / principals.
    await audit_record(
        session,
        action="pr.evidence_fetch_failed",
        actor=actor,
        target=f"project:{project_id}",
        payload={"project_id": str(project_id), "pr_number": pr_number, "reason": reason},
    )


async def refresh_pull_request_evidence(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    pr_number: int,
    agent_id: str,
    actor: str,
    connector: SCMConnector,
    presence_flags: dict | None = None,
    traceability_refs: dict | None = None,
) -> RefreshResult:
    """Broker-gated, repo-bound PR-evidence refresh. Writes a ``connector_verified`` snapshot only on a
    clean verified fetch; every failure path is fail-closed + audited (safe metadata only)."""
    # 1. Resolve the project's OWN declared repo + credential source (fail-closed).
    resolved = await resolve_declared_repo(session, context, project_id)
    if resolved is None:
        await _audit_failure(session, actor, project_id, pr_number, "repo_unbound")
        return RefreshResult(False, "repo_unbound")
    repo_ref, _branch = resolved
    if not await has_declared_credential(session, context, project_id):
        await _audit_failure(session, actor, project_id, pr_number, "credential_unbound")
        return RefreshResult(False, "credential_unbound")

    # 2. Broker decision — SAFE params only (no raw repo_ref; pr_number is not a secret).
    decision = await broker_call(
        session,
        context,
        project_id=project_id,
        agent_id=agent_id,
        tool_name=_TOOL,
        params={"provider": "github", "pr_number": pr_number, "repo_ref_present": True},
    )
    if decision not in _ALLOWED:
        return RefreshResult(False, "broker_denied", decision=decision)

    # 3. Fetch (Fake in tests). A PR/reviews failure (B-29-7) ⇒ SCMConnectorError ⇒ no write.
    try:
        mapped = await connector.fetch_pull_request(repo_ref=repo_ref, pr_number=pr_number)
    except SCMConnectorError:
        await _audit_failure(session, actor, project_id, pr_number, "connector_error")
        return RefreshResult(False, "connector_error", decision=decision)
    if mapped is None:
        await _audit_failure(session, actor, project_id, pr_number, "no_pull_request")
        return RefreshResult(False, "no_pull_request", decision=decision)

    # 4. Write a connector_verified snapshot (repo_ref/pr_number from the binding, not params).
    payload = {
        **mapped,
        "provider": "github",
        "repo_ref": repo_ref,
        "pr_number": pr_number,
        "observed_at": datetime.now(timezone.utc),
        "presence_flags": presence_flags or {},
        "traceability_refs": traceability_refs or {},
    }
    row = await PullRequestEvidenceRepository(
        session, context
    ).record_connector_verified_pull_request(project_id=project_id, payload=payload, actor=actor)
    return RefreshResult(True, "verified", decision=decision, snapshot_id=row.id)
