"""Deployment-target verification orchestration (Slice 30) — broker-gated, SSRF-safe, fail-closed.

``refresh_deployment_target_evidence``: resolve the project's OWN declared production target
(``resolve_declared_production_target``) → broker decision with **safe params only** (no raw domain) →
SSRF-safe probe via the injected connector (Fake in tests) → **write a ``connector_verified`` snapshot
for every safely-attempted outcome** (positive when serving, verified-negative when unavailable — B-30-9),
so latest-wins gate #2 can't keep a stale passing snapshot active. **NO write** only for: target unbound/
malformed (resolver ``None``), broker deny, or SSRF reject (``DeploySSRFRejected``) — these are failures to
*attempt*, not observations. Admin/internal — **no HTTP endpoint**. Verification-only — never deploys,
never authorizes production, never enables go-live. ``actor`` is an untrusted caller label.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.release.deploy_connector import DeployTargetConnector
from app.release.deploy_evidence import DeploySSRFRejected
from app.release.project_repo import resolve_declared_production_target
from app.repositories.deployments import DeploymentTargetRepository
from app.tenancy import TenantContext
from app.tools.broker import BrokerDecision, broker_call_service

_ALLOWED = (BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,)
_TOOL = "deployment.read_target_status"


@dataclass
class RefreshResult:
    wrote: bool
    reason: str
    decision: BrokerDecision | None = None
    snapshot_id: uuid.UUID | None = None


async def _audit_failure(
    session: AsyncSession, actor: str, project_id: uuid.UUID, reason: str
) -> None:
    # Safe metadata only — NEVER target_ref / domain / URL / resolved IPs.
    await audit_record(
        session,
        action="deploy.target_fetch_failed",
        actor=actor,
        target=f"project:{project_id}",
        payload={"project_id": str(project_id), "reason": reason},
    )


async def refresh_deployment_target_evidence(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    agent_id: str,  # legacy backward-compatible param: a platform-SERVICE identity (not an agent), routed to broker_call_service
    actor: str,
    connector: DeployTargetConnector,
) -> RefreshResult:
    """Broker-gated, target-bound, SSRF-safe deployment-target refresh. Writes a ``connector_verified``
    snapshot for every safely-attempted outcome; fail-closed (no write) only for unbound/deny/ssrf. The legacy ``agent_id`` parameter is a platform-SERVICE identity (not an agent)."""
    # 1. Resolve the project's OWN declared production target (fail-closed).
    host = await resolve_declared_production_target(session, context, project_id)
    if host is None:
        await _audit_failure(session, actor, project_id, "target_unbound")
        return RefreshResult(False, "target_unbound")

    # 2. Broker decision — SAFE params only (no raw domain/target_ref).
    decision = await broker_call_service(
        session,
        context,
        project_id=project_id,
        service_id=agent_id,
        tool_name=_TOOL,
        params={"provider": "generic_https", "environment": "production", "target_present": True},
    )
    if decision not in _ALLOWED:
        await _audit_failure(session, actor, project_id, "broker_denied")
        return RefreshResult(False, "broker_denied", decision=decision)

    # 3. Probe (Fake in tests). An SSRF reject is a refusal to ATTEMPT ⇒ no write.
    try:
        observation = await connector.probe_target(host=host)
    except DeploySSRFRejected:
        await _audit_failure(session, actor, project_id, "ssrf_reject")
        return RefreshResult(False, "ssrf_reject", decision=decision)

    # 4. Write a connector_verified snapshot for the safely-attempted outcome (positive OR negative).
    payload = {
        **observation,
        "provider": "generic_https",
        "environment": "production",
        "target_ref": host,
        "observed_at": datetime.now(timezone.utc),
    }
    row = await DeploymentTargetRepository(
        session, context
    ).record_connector_verified_deployment_target(
        project_id=project_id, payload=payload, actor=actor
    )
    return RefreshResult(True, "observed", decision=decision, snapshot_id=row.id)
