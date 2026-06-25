"""Tenant-scoped PM-issue-mapping repository (Slice 34, §12.3 / §26.3).

``record_connector_verified_mapping`` validates fail-closed and persists an immutable ``pm_issue_mappings``
row + an audit entry with **safe metadata only** (system/instance/ref/status/board_column/title_present/
provenance) — **never** a title/description/credential (there is no such column). ``latest_for_ref`` is the
idempotent latest-wins lookup keyed by ``(tenant, project, external_system, instance_key, external_ref)``
(B7). **Store/infra-only — creates no ``release_issues``; never flips an A5 gate.** Run inside
``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.pm_issue_mapping import PMIssueMapping
from app.release.pm_issues import validate_connector_mapping, validate_new_mapping
from app.tenancy import TenantContext, TenantScopedRepository


class PMIssueMappingRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, PMIssueMapping)

    async def record_mapping(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> PMIssueMapping:
        validate_new_mapping(payload)
        return await self._record(
            project_id, payload, "caller_supplied_unverified", actor, "pm.issue_observed"
        )

    async def record_connector_verified_mapping(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> PMIssueMapping:
        """Connector path — ``observed_at`` required."""
        validate_connector_mapping(payload)
        return await self._record(
            project_id, payload, "connector_verified", actor, "pm.issue_verified"
        )

    async def _record(
        self, project_id: uuid.UUID, payload: dict, provenance: str, actor: str, action: str
    ) -> PMIssueMapping:
        row = PMIssueMapping(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            external_system=payload["external_system"],
            instance_key=payload["instance_key"],
            external_ref=payload["external_ref"],
            external_status=payload["external_status"],
            board_column=payload["board_column"],
            title_present=payload["title_present"],
            observed_at=payload.get("observed_at"),
            provenance=provenance,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, action, actor)
        return row

    async def latest_for_ref(
        self,
        project_id: uuid.UUID,
        external_system: str,
        instance_key: str,
        external_ref: str,
    ) -> PMIssueMapping | None:
        stmt = (
            select(PMIssueMapping)
            .where(
                PMIssueMapping.tenant_id == self.context.tenant_id,
                PMIssueMapping.project_id == project_id,
                PMIssueMapping.external_system == external_system,
                PMIssueMapping.instance_key == instance_key,
                PMIssueMapping.external_ref == external_ref,
            )
            .order_by(PMIssueMapping.created_at.desc(), PMIssueMapping.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_latest_for_project(self, project_id: uuid.UUID) -> list[PMIssueMapping]:
        """Latest mapping per ``(external_system, instance_key, external_ref)`` (DISTINCT ON)."""
        stmt = (
            select(PMIssueMapping)
            .where(
                PMIssueMapping.tenant_id == self.context.tenant_id,
                PMIssueMapping.project_id == project_id,
            )
            .distinct(
                PMIssueMapping.external_system,
                PMIssueMapping.instance_key,
                PMIssueMapping.external_ref,
            )
            .order_by(
                PMIssueMapping.external_system,
                PMIssueMapping.instance_key,
                PMIssueMapping.external_ref,
                PMIssueMapping.created_at.desc(),
                PMIssueMapping.id.desc(),
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _audit(self, row: PMIssueMapping, action: str, actor: str) -> None:
        # Safe metadata only — never a title/description/credential (no such column exists).
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"pm_issue_mapping:{row.id}",
            payload={
                "pm_issue_mapping_id": str(row.id),
                "project_id": str(row.project_id),
                "external_system": row.external_system,
                "instance_key": row.instance_key,
                "external_ref": row.external_ref,
                "external_status": row.external_status,
                "board_column": row.board_column,
                "title_present": row.title_present,
                "provenance": row.provenance,
            },
        )
