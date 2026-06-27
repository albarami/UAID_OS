"""Secrets-reference verification orchestration (Slice 32) — broker-gated, fail-closed, store-only.

``refresh_secret_reference_evidence``: resolve the project's OWN declared secret references (canonical
persisted shape, B5) → for each, a broker decision with **safe params** (`{manager, reference_present:
true}` — never the reference_name or any value, B3) → verify via the injected connector (env-only;
unsupported managers ⇒ ``unsupported_manager``) → write an immutable ``connector_verified``
``secret_reference_checks`` row recording **only** `(manager, reference_name, outcome, resolved)`.
**NO secret value** is ever stored/logged/audited/returned. No declared references ⇒ audited
``secrets_unbound``, no write; a broker deny skips that reference (no write). **Store-only — never flips an
A5 gate / readiness level; ruleset stays slice31.v1.** Admin/internal — no HTTP endpoint. ``actor`` is an
untrusted caller label.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.release.project_repo import resolve_declared_secret_references
from app.release.secrets_connector import SecretsManagerConnector
from app.repositories.secrets_verification import SecretReferenceCheckRepository
from app.tenancy import TenantContext
from app.tools.broker import BrokerDecision, broker_call_service

_ALLOWED = (BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY,)
_TOOL = "secrets.verify_reference"


@dataclass
class SecretRefRefreshResult:
    wrote: int
    references: int
    reason: str  # "observed" | "secrets_unbound"
    # Per-reference outcomes (manager/outcome/resolved/wrote) — NEVER the reference_name or a value.
    results: list[dict] = field(default_factory=list)


async def _audit_failure(
    session: AsyncSession, actor: str, project_id: uuid.UUID, reason: str
) -> None:
    # Safe metadata only — NEVER reference_name or any value.
    await audit_record(
        session,
        action="secrets.reference_fetch_failed",
        actor=actor,
        target=f"project:{project_id}",
        payload={"project_id": str(project_id), "reason": reason},
    )


async def refresh_secret_reference_evidence(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    agent_id: str,
    actor: str,
    connector: SecretsManagerConnector,
) -> SecretRefRefreshResult:
    """Broker-gated, per-reference secrets verification. Writes one ``connector_verified`` row per
    safely-verified reference; fail-closed (no write) for unbound / broker-deny."""
    refs = await resolve_declared_secret_references(session, context, project_id)
    if not refs:
        await _audit_failure(session, actor, project_id, "secrets_unbound")
        return SecretRefRefreshResult(wrote=0, references=0, reason="secrets_unbound")

    repo = SecretReferenceCheckRepository(session, context)
    results: list[dict] = []
    wrote = 0
    for manager, reference_name in refs:
        # SAFE params only — never the reference_name or a value (B3).
        decision = await broker_call_service(
            session,
            context,
            project_id=project_id,
            service_id=agent_id,
            tool_name=_TOOL,
            params={"manager": manager, "reference_present": True},
        )
        if decision not in _ALLOWED:
            await _audit_failure(session, actor, project_id, "broker_denied")
            results.append(
                {"manager": manager, "outcome": "broker_denied", "resolved": False, "wrote": False}
            )
            continue
        observation = await connector.verify_reference(
            manager=manager, reference_name=reference_name
        )
        payload = {
            "manager": manager,
            "reference_name": reference_name,
            **observation,
            "checked_at": datetime.now(timezone.utc),
        }
        await repo.record_connector_verified_check(
            project_id=project_id, payload=payload, actor=actor
        )
        wrote += 1
        results.append(
            {
                "manager": manager,
                "outcome": observation["outcome"],
                "resolved": observation["resolved"],
                "wrote": True,
            }
        )
    return SecretRefRefreshResult(
        wrote=wrote, references=len(refs), reason="observed", results=results
    )
