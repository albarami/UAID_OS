"""Tenant-scoped deployment-target evidence repository (Slice 30, App. B #2 / §5.2 / §26.3).

``record_deployment_target`` (caller path) stamps ``provenance='caller_supplied_unverified'``;
``record_connector_verified_deployment_target`` (connector path, after a SSRF-safe probe) stamps
``provenance='connector_verified'`` — written for **every safely-attempted outcome** (positive when
serving, verified-negative when unavailable; B-30-9). Both validate fail-closed and persist an immutable
row + an audit entry with **safe metadata only** (ids/provider/environment/booleans/provenance — **never**
``target_ref``/domain/URL/resolved IPs). ``latest_deployment_target_for_ref`` is the repo-scoped lookup
gate #2 uses (latest-wins). Verification-only — never deploys / authorizes production / enables go-live.
Run inside ``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.deployment_target_snapshot import DeploymentTargetSnapshot
from app.release.deploy_evidence import (
    validate_connector_deployment_target,
    validate_new_deployment_target,
)
from app.tenancy import TenantContext, TenantScopedRepository


class DeploymentTargetRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, DeploymentTargetSnapshot)

    async def record_deployment_target(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> DeploymentTargetSnapshot:
        validate_new_deployment_target(payload)
        return await self._record(
            project_id, payload, "caller_supplied_unverified", actor, "deploy.target_observed"
        )

    async def record_connector_verified_deployment_target(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> DeploymentTargetSnapshot:
        """Connector path — reached only after an SSRF-safe probe; ``observed_at`` required."""
        validate_connector_deployment_target(payload)
        return await self._record(
            project_id, payload, "connector_verified", actor, "deploy.target_verified"
        )

    async def _record(
        self, project_id: uuid.UUID, payload: dict, provenance: str, actor: str, action: str
    ) -> DeploymentTargetSnapshot:
        row = DeploymentTargetSnapshot(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider=payload["provider"],
            environment=payload["environment"],
            target_ref=payload["target_ref"],
            reachable=payload["reachable"],
            provisioned=payload["provisioned"],
            target_available=payload["target_available"],
            observed_http_status=payload.get("observed_http_status"),
            observed_at=payload.get("observed_at"),
            provenance=provenance,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, action, actor)
        return row

    async def latest_deployment_target_for_ref(
        self,
        project_id: uuid.UUID,
        provider: str,
        target_ref: str,
        environment: str = "production",
    ) -> DeploymentTargetSnapshot | None:
        """Latest snapshot for the SPECIFIC declared ``(provider, environment, target_ref)`` — **gate #2
        uses this with ``environment='production'``** (B5) so a newer *staging* row for the same host
        cannot contaminate the production gate, and a snapshot for a no-longer-declared target cannot
        satisfy the gate."""
        stmt = (
            select(DeploymentTargetSnapshot)
            .where(
                DeploymentTargetSnapshot.tenant_id == self.context.tenant_id,
                DeploymentTargetSnapshot.project_id == project_id,
                DeploymentTargetSnapshot.provider == provider,
                DeploymentTargetSnapshot.environment == environment,
                DeploymentTargetSnapshot.target_ref == target_ref,
            )
            .order_by(
                DeploymentTargetSnapshot.created_at.desc(),
                DeploymentTargetSnapshot.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def latest_deployment_target(
        self, project_id: uuid.UUID
    ) -> DeploymentTargetSnapshot | None:
        stmt = (
            select(DeploymentTargetSnapshot)
            .where(
                DeploymentTargetSnapshot.tenant_id == self.context.tenant_id,
                DeploymentTargetSnapshot.project_id == project_id,
            )
            .order_by(
                DeploymentTargetSnapshot.created_at.desc(),
                DeploymentTargetSnapshot.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_deployment_target_snapshots(self, project_id: uuid.UUID) -> int:
        return await self._count(project_id)

    async def count_connector_verified_deployment_targets(self, project_id: uuid.UUID) -> int:
        return await self._count(project_id, provenance="connector_verified")

    async def _count(self, project_id: uuid.UUID, provenance: str | None = None) -> int:
        stmt = select(func.count()).where(
            DeploymentTargetSnapshot.tenant_id == self.context.tenant_id,
            DeploymentTargetSnapshot.project_id == project_id,
        )
        if provenance is not None:
            stmt = stmt.where(DeploymentTargetSnapshot.provenance == provenance)
        return int((await self.session.execute(stmt)).scalar_one())

    async def _audit(self, row: DeploymentTargetSnapshot, action: str, actor: str) -> None:
        # Safe metadata only — NEVER target_ref / domain / URL / resolved IPs.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"deployment_target_snapshot:{row.id}",
            payload={
                "deployment_target_snapshot_id": str(row.id),
                "project_id": str(row.project_id),
                "provider": row.provider,
                "environment": row.environment,
                "reachable": row.reachable,
                "provisioned": row.provisioned,
                "target_available": row.target_available,
                "provenance": row.provenance,
            },
        )
