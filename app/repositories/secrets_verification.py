"""Tenant-scoped secrets-reference verification repository (Slice 32, R5 App. A / §26.3).

``record_connector_verified_check`` (connector path) stamps ``provenance='connector_verified'``;
``record_check`` (caller path) stamps ``caller_supplied_unverified``. Both validate fail-closed and persist
an immutable row + an audit entry with **safe metadata only** — `manager` + `outcome` + `resolved`,
**NEVER** the `reference_name` (defense-in-depth) and **never** any secret value (there is no value to
record — the model has no value column). ``latest_for_reference`` is the latest-wins lookup; the
``list_latest_for_project`` / ``count_resolved`` helpers are a **future** feed for gate #2 / R5 completeness
(no gate consumes them this slice). Run inside ``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.secret_reference_check import SecretReferenceCheck
from app.release.secrets_verification import (
    validate_connector_secret_check,
    validate_new_secret_check,
)
from app.tenancy import TenantContext, TenantScopedRepository


class SecretReferenceCheckRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, SecretReferenceCheck)

    async def record_check(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> SecretReferenceCheck:
        validate_new_secret_check(payload)
        return await self._record(
            project_id, payload, "caller_supplied_unverified", actor, "secrets.reference_observed"
        )

    async def record_connector_verified_check(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> SecretReferenceCheck:
        """Connector path — ``checked_at`` required."""
        validate_connector_secret_check(payload)
        return await self._record(
            project_id, payload, "connector_verified", actor, "secrets.reference_verified"
        )

    async def _record(
        self, project_id: uuid.UUID, payload: dict, provenance: str, actor: str, action: str
    ) -> SecretReferenceCheck:
        row = SecretReferenceCheck(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            manager=payload["manager"],
            reference_name=payload["reference_name"],
            outcome=payload["outcome"],
            resolved=payload["resolved"],
            checked_at=payload.get("checked_at"),
            provenance=provenance,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, action, actor)
        return row

    async def latest_for_reference(
        self, project_id: uuid.UUID, manager: str, reference_name: str
    ) -> SecretReferenceCheck | None:
        stmt = (
            select(SecretReferenceCheck)
            .where(
                SecretReferenceCheck.tenant_id == self.context.tenant_id,
                SecretReferenceCheck.project_id == project_id,
                SecretReferenceCheck.manager == manager,
                SecretReferenceCheck.reference_name == reference_name,
            )
            .order_by(
                SecretReferenceCheck.created_at.desc(),
                SecretReferenceCheck.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_latest_for_project(self, project_id: uuid.UUID) -> list[SecretReferenceCheck]:
        """Latest check per ``(manager, reference_name)`` (DISTINCT ON, latest-wins)."""
        stmt = (
            select(SecretReferenceCheck)
            .where(
                SecretReferenceCheck.tenant_id == self.context.tenant_id,
                SecretReferenceCheck.project_id == project_id,
            )
            .distinct(SecretReferenceCheck.manager, SecretReferenceCheck.reference_name)
            .order_by(
                SecretReferenceCheck.manager,
                SecretReferenceCheck.reference_name,
                SecretReferenceCheck.created_at.desc(),
                SecretReferenceCheck.id.desc(),
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_resolved(self, project_id: uuid.UUID) -> int:
        """Count of references whose LATEST check resolved (future gate feed; no consumer this slice)."""
        latest = await self.list_latest_for_project(project_id)
        return sum(1 for r in latest if r.resolved)

    async def _audit(self, row: SecretReferenceCheck, action: str, actor: str) -> None:
        # Safe metadata only — NEVER reference_name, and there is no value to record.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"secret_reference_check:{row.id}",
            payload={
                "secret_reference_check_id": str(row.id),
                "project_id": str(row.project_id),
                "manager": row.manager,
                "outcome": row.outcome,
                "resolved": row.resolved,
                "provenance": row.provenance,
            },
        )
