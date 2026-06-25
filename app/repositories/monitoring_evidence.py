"""Tenant-scoped monitoring/alerts evidence repository (Slice 31, App. B #11 / §26.3 / §26.6).

``record_monitoring`` (caller path) stamps ``provenance='caller_supplied_unverified'``;
``record_connector_verified_monitoring`` (connector path, after a SSRF-safe bounded read) stamps
``provenance='connector_verified'`` — written for **every safely-attempted outcome** (valid OR an honest
failed read; B-30-9). Both validate fail-closed and persist an immutable row + an audit entry with **safe
metadata only** (ids/provider/read-state booleans/counts/failure_kind/provenance — **never** ``target_ref``
/ URL / host / path). ``latest_monitoring_for_ref`` is the repo-scoped lookup gate #11 uses (latest-wins,
bound to the currently declared ``status_url``; B2). Verification-only — never enables go-live. Run inside
``tenant_scope``; ``actor`` is an untrusted caller label.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.monitoring_status_snapshot import MonitoringStatusSnapshot
from app.release.monitoring_evidence import (
    validate_connector_monitoring,
    validate_new_monitoring,
)
from app.tenancy import TenantContext, TenantScopedRepository


class MonitoringEvidenceRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, MonitoringStatusSnapshot)

    async def record_monitoring(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> MonitoringStatusSnapshot:
        validate_new_monitoring(payload)
        return await self._record(
            project_id, payload, "caller_supplied_unverified", actor, "monitoring.status_observed"
        )

    async def record_connector_verified_monitoring(
        self, *, project_id: uuid.UUID, payload: dict, actor: str
    ) -> MonitoringStatusSnapshot:
        """Connector path — reached only after a SSRF-safe bounded read; ``observed_at`` required."""
        validate_connector_monitoring(payload)
        return await self._record(
            project_id, payload, "connector_verified", actor, "monitoring.status_verified"
        )

    async def _record(
        self, project_id: uuid.UUID, payload: dict, provenance: str, actor: str, action: str
    ) -> MonitoringStatusSnapshot:
        row = MonitoringStatusSnapshot(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider=payload["provider"],
            target_ref=payload["target_ref"],
            provider_reachable=payload["provider_reachable"],
            response_valid=payload["response_valid"],
            observed_http_status=payload.get("observed_http_status"),
            failure_kind=payload.get("failure_kind"),
            active_monitor_count=payload.get("active_monitor_count"),
            active_alert_rule_count=payload.get("active_alert_rule_count"),
            monitoring_active=payload["monitoring_active"],
            alerts_active=payload["alerts_active"],
            overall_active=payload["overall_active"],
            observed_at=payload.get("observed_at"),
            provenance=provenance,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, action, actor)
        return row

    async def latest_monitoring_for_ref(
        self, project_id: uuid.UUID, provider: str, target_ref: str
    ) -> MonitoringStatusSnapshot | None:
        """Latest snapshot for the SPECIFIC declared ``(provider, target_ref)`` — **gate #11 uses this**
        (B2) so a snapshot for a no-longer-declared ``status_url`` (host or path change) cannot satisfy
        the gate."""
        stmt = (
            select(MonitoringStatusSnapshot)
            .where(
                MonitoringStatusSnapshot.tenant_id == self.context.tenant_id,
                MonitoringStatusSnapshot.project_id == project_id,
                MonitoringStatusSnapshot.provider == provider,
                MonitoringStatusSnapshot.target_ref == target_ref,
            )
            .order_by(
                MonitoringStatusSnapshot.created_at.desc(),
                MonitoringStatusSnapshot.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def latest_monitoring(self, project_id: uuid.UUID) -> MonitoringStatusSnapshot | None:
        stmt = (
            select(MonitoringStatusSnapshot)
            .where(
                MonitoringStatusSnapshot.tenant_id == self.context.tenant_id,
                MonitoringStatusSnapshot.project_id == project_id,
            )
            .order_by(
                MonitoringStatusSnapshot.created_at.desc(),
                MonitoringStatusSnapshot.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_connector_verified_monitoring(self, project_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            MonitoringStatusSnapshot.tenant_id == self.context.tenant_id,
            MonitoringStatusSnapshot.project_id == project_id,
            MonitoringStatusSnapshot.provenance == "connector_verified",
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def _audit(self, row: MonitoringStatusSnapshot, action: str, actor: str) -> None:
        # Safe metadata only — NEVER target_ref / URL / host / path (B8).
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"monitoring_status_snapshot:{row.id}",
            payload={
                "monitoring_status_snapshot_id": str(row.id),
                "project_id": str(row.project_id),
                "provider": row.provider,
                "provider_reachable": row.provider_reachable,
                "response_valid": row.response_valid,
                "failure_kind": row.failure_kind,
                "monitoring_active": row.monitoring_active,
                "alerts_active": row.alerts_active,
                "overall_active": row.overall_active,
                "active_monitor_count": row.active_monitor_count,
                "active_alert_rule_count": row.active_alert_rule_count,
                "provenance": row.provenance,
            },
        )
