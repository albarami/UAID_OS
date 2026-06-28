"""PM / issue-tracker sync orchestration (Slice 34) — broker-gated, fail-closed, store-only.

``sync_pm_issues``: resolve the project's OWN declared Jira project (`resolve_declared_pm_project`, B4) →
require a declared reference-only ``JIRA_CONNECTOR_TOKEN`` credential (`has_declared_jira_credential`; missing
⇒ audited ``credential_unbound``, no broker call / no write) → broker decision with **safe params** (`{provider:'jira', project_present:true}` — never the project key /
instance key / credential) → fetch observed issues via the injected connector (Fake in tests; live adapter
deferred) → derive the §12.3 ``board_column`` (`map_board_column`, ``unmapped`` fail-closed) → write an
immutable ``connector_verified`` ``pm_issue_mappings`` row per item (idempotent latest-wins). **Creates no
``release_issues``** (store/infra-only — never flips an A5 gate). A malformed observation is **skipped**
(fail-closed per item, never aborts the sync). No declared project ⇒ audited ``pm_unbound``, no write;
broker-deny ⇒ audited, no write. **No title/credential** is ever stored/logged. Admin/internal — no HTTP
endpoint. ``actor`` is an untrusted caller label.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.release.pm_connector import IssueTrackerConnector
from app.release.pm_issues import InvalidPMMapping, map_board_column
from app.release.project_repo import (
    has_declared_jira_credential,
    resolve_declared_pm_project,
)
from app.repositories.pm_issues import PMIssueMappingRepository
from app.tenancy import TenantContext
from app.tools.broker import BrokerDecision, broker_call_service

_ALLOWED = (BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,)
_TOOL = "pm.read_issues"


@dataclass
class PMSyncResult:
    wrote: int
    observed: int
    skipped: int
    reason: str  # "observed" | "pm_unbound" | "credential_unbound" | "broker_denied"


async def _audit_failure(
    session: AsyncSession, actor: str, project_id: uuid.UUID, reason: str
) -> None:
    # Safe metadata only — never the project key / instance key / credential.
    await audit_record(
        session,
        action="pm.sync_failed",
        actor=actor,
        target=f"project:{project_id}",
        payload={"project_id": str(project_id), "reason": reason},
    )


async def sync_pm_issues(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    agent_id: str,  # legacy backward-compatible param: a platform-SERVICE identity (not an agent), routed to broker_call_service
    actor: str,
    connector: IssueTrackerConnector,
) -> PMSyncResult:
    """Broker-gated, declared-project-bound PM sync. Writes one ``connector_verified`` mapping per
    safely-observed issue (idempotent latest-wins); fail-closed (no write) for unbound / broker-deny. The legacy ``agent_id`` parameter is a platform-SERVICE identity (not an agent)."""
    resolved = await resolve_declared_pm_project(session, context, project_id)
    if resolved is None:
        await _audit_failure(session, actor, project_id, "pm_unbound")
        return PMSyncResult(wrote=0, observed=0, skipped=0, reason="pm_unbound")
    instance_key, project_key = resolved

    # B4: the project must declare a usable JIRA_CONNECTOR_TOKEN reference (reference-only; the value is
    # operator-env). Fail-closed BEFORE the broker call / any fetch — no broker attempt, no write.
    if not await has_declared_jira_credential(session, context, project_id):
        await _audit_failure(session, actor, project_id, "credential_unbound")
        return PMSyncResult(wrote=0, observed=0, skipped=0, reason="credential_unbound")

    decision = await broker_call_service(
        session,
        context,
        project_id=project_id,
        service_id=agent_id,
        tool_name=_TOOL,
        params={"provider": "jira", "project_present": True},
    )
    if decision not in _ALLOWED:
        await _audit_failure(session, actor, project_id, "broker_denied")
        return PMSyncResult(wrote=0, observed=0, skipped=0, reason="broker_denied")

    observations = await connector.fetch_issues(instance_key=instance_key, project_key=project_key)
    repo = PMIssueMappingRepository(session, context)
    wrote = 0
    skipped = 0
    for obs in observations:
        payload = {
            "external_system": "jira",
            "instance_key": instance_key,
            "external_ref": obs.get("external_ref"),
            "external_status": obs.get("external_status"),
            "board_column": map_board_column(obs.get("external_status")),
            "title_present": obs.get("title_present"),
            "observed_at": datetime.now(timezone.utc),
        }
        try:
            await repo.record_connector_verified_mapping(
                project_id=project_id, payload=payload, actor=actor
            )
        except InvalidPMMapping:
            skipped += 1  # malformed observation — skip, never abort the sync
            continue
        wrote += 1
    return PMSyncResult(wrote=wrote, observed=len(observations), skipped=skipped, reason="observed")
