"""Tenant-scoped approval-notification repository (Slice 33, §18.2).

``record`` validates fail-closed and persists an immutable ``approval_notifications`` row + an audit entry
with **safe metadata only** (ids / risk_tier / routing_mode / channel / status) — there is **no recipient
/ free-text / secret material** anywhere. Run inside ``tenant_scope``; ``actor`` is an untrusted caller
label. Store/infra-only — never flips an A5 gate / readiness level.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.channels.routing import validate_notification
from app.audit import record as audit_record
from app.models.approval_notification import ApprovalNotification
from app.tenancy import TenantContext, TenantScopedRepository


class ApprovalNotificationRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ApprovalNotification)

    async def record(self, *, payload: dict, actor: str) -> ApprovalNotification:
        validate_notification(payload)
        row = ApprovalNotification(
            tenant_id=self.context.tenant_id,
            project_id=payload["project_id"],
            approval_id=payload["approval_id"],
            risk_tier=payload["risk_tier"],
            routing_mode=payload["routing_mode"],
            channel=payload["channel"],
            status=payload["status"],
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, actor)
        return row

    async def latest_for_approval(self, approval_id: uuid.UUID) -> ApprovalNotification | None:
        stmt = (
            select(ApprovalNotification)
            .where(
                ApprovalNotification.tenant_id == self.context.tenant_id,
                ApprovalNotification.approval_id == approval_id,
            )
            .order_by(
                ApprovalNotification.created_at.desc(),
                ApprovalNotification.id.desc(),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_project(self, project_id: uuid.UUID) -> list[ApprovalNotification]:
        stmt = (
            select(ApprovalNotification)
            .where(
                ApprovalNotification.tenant_id == self.context.tenant_id,
                ApprovalNotification.project_id == project_id,
            )
            .order_by(
                ApprovalNotification.created_at.desc(),
                ApprovalNotification.id.desc(),
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _audit(self, row: ApprovalNotification, actor: str) -> None:
        # Safe metadata only — ids/routing facts; never a recipient or any free-text/secret.
        await audit_record(
            self.session,
            action="approval.notification_recorded",
            actor=actor,
            target=f"approval_notification:{row.id}",
            payload={
                "approval_notification_id": str(row.id),
                "project_id": str(row.project_id),
                "approval_id": str(row.approval_id),
                "risk_tier": row.risk_tier,
                "routing_mode": row.routing_mode,
                "channel": row.channel,
                "status": row.status,
            },
        )
