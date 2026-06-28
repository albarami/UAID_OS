"""Monitoring/alerts verification orchestration (Slice 31) — broker-gated, SSRF-safe, fail-closed.

``refresh_monitoring_evidence``: resolve the project's OWN declared monitoring binding
(``resolve_declared_monitoring_target``) → broker decision with **safe params only** (no raw
URL/host/path) → SSRF-safe, **unauthenticated**, bounded read via the injected connector (Fake in tests)
→ **write a ``connector_verified`` snapshot for every safely-attempted outcome** (valid OR an honest
failed read — B-30-9), so latest-wins gate #11 can't keep a stale passing snapshot active. **NO write**
only for: monitoring unbound/malformed (resolver ``None``), broker deny, or SSRF reject
(``DeploySSRFRejected``) — failures to *attempt*, not observations. The snapshot ``target_ref`` is the full
declared ``status_url`` (binding key, B2). Admin/internal — **no HTTP endpoint**. Verification-only — never
enables go-live. ``actor`` is an untrusted caller label.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.release.deploy_evidence import DeploySSRFRejected
from app.release.monitoring_connector import MonitoringConnector
from app.release.project_repo import resolve_declared_monitoring_target
from app.repositories.monitoring_evidence import MonitoringEvidenceRepository
from app.tenancy import TenantContext
from app.tools.broker import BrokerDecision, broker_call_service

_ALLOWED = (BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,)
_TOOL = "monitoring.read_status"


@dataclass
class RefreshResult:
    wrote: bool
    reason: str
    decision: BrokerDecision | None = None
    snapshot_id: uuid.UUID | None = None


async def _audit_failure(
    session: AsyncSession, actor: str, project_id: uuid.UUID, reason: str
) -> None:
    # Safe metadata only — NEVER target_ref / URL / host / path (B8).
    await audit_record(
        session,
        action="monitoring.status_fetch_failed",
        actor=actor,
        target=f"project:{project_id}",
        payload={"project_id": str(project_id), "reason": reason},
    )


async def refresh_monitoring_evidence(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    agent_id: str,  # legacy backward-compatible param: a platform-SERVICE identity (not an agent), routed to broker_call_service
    actor: str,
    connector: MonitoringConnector,
) -> RefreshResult:
    """Broker-gated, binding-bound, SSRF-safe monitoring refresh. Writes a ``connector_verified`` snapshot
    for every safely-attempted outcome; fail-closed (no write) only for unbound/deny/ssrf. The legacy ``agent_id`` parameter is a platform-SERVICE identity (not an agent)."""
    # 1. Resolve the project's OWN declared monitoring binding (fail-closed). Unauthenticated (B9).
    resolved = await resolve_declared_monitoring_target(session, context, project_id)
    if resolved is None:
        await _audit_failure(session, actor, project_id, "monitoring_unbound")
        return RefreshResult(False, "monitoring_unbound")
    status_url, host, path = resolved

    # 2. Broker decision — SAFE params only (no raw URL/host/path).
    decision = await broker_call_service(
        session,
        context,
        project_id=project_id,
        service_id=agent_id,
        tool_name=_TOOL,
        params={"provider": "generic_monitoring_api", "monitoring_present": True},
    )
    if decision not in _ALLOWED:
        await _audit_failure(session, actor, project_id, "broker_denied")
        return RefreshResult(False, "broker_denied", decision=decision)

    # 3. Probe (Fake in tests). An SSRF reject is a refusal to ATTEMPT ⇒ no write.
    try:
        observation = await connector.probe_monitoring(host=host, path=path)
    except DeploySSRFRejected:
        await _audit_failure(session, actor, project_id, "ssrf_reject")
        return RefreshResult(False, "ssrf_reject", decision=decision)

    # 4. Write a connector_verified snapshot for the safely-attempted outcome (valid OR failed read).
    payload = {
        **observation,
        "provider": "generic_monitoring_api",
        "target_ref": status_url,
        "observed_at": datetime.now(timezone.utc),
    }
    row = await MonitoringEvidenceRepository(session, context).record_connector_verified_monitoring(
        project_id=project_id, payload=payload, actor=actor
    )
    return RefreshResult(True, "observed", decision=decision, snapshot_id=row.id)
