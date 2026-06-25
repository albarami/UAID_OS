"""Approval-notification orchestration (Slice 33, §18.2) — the human-surface wiring.

``ApprovalNotificationService.notify_for_approval`` routes an approval **by tier only** (``route`` — no
``human_approval_policy`` read), delivers via the injected channel (Fake/dashboard), and records an
immutable ``approval_notifications`` row. ``request_and_notify_approval`` is the **one authoritative
orchestration surface** (B4): it calls ``ApprovalRepository.request`` (untouched) then
``notify_for_approval`` — so requesting an approval emits **both** an ``approval_events`` row (from
``request``) and an ``approval_notifications`` row. **No secret material; no A5/readiness flip; verified
identity reused from Slice 27** (on the approval resolution, not here). Run inside ``tenant_scope``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.channels.adapter import ApprovalChannel
from app.approvals.channels.routing import route
from app.models.approval import Approval
from app.models.approval_notification import ApprovalNotification
from app.repositories.approval_notifications import ApprovalNotificationRepository
from app.repositories.approvals import ApprovalRepository
from app.tenancy import TenantContext


class ApprovalNotificationService:
    def __init__(self, session: AsyncSession, context: TenantContext):
        self.session = session
        self.context = context
        self._repo = ApprovalNotificationRepository(session, context)

    async def notify_for_approval(
        self, approval: Approval, *, actor: str, channel: ApprovalChannel
    ) -> ApprovalNotification:
        """Route (tier-only) → deliver → record. No policy/secret read."""
        routing_mode = route(approval.risk_tier)
        notification = {
            "approval_id": approval.id,
            "project_id": approval.project_id,
            "risk_tier": approval.risk_tier,
            "routing_mode": routing_mode,
            "channel": channel.name,
        }
        notification["status"] = await channel.deliver(dict(notification))
        return await self._repo.record(payload=notification, actor=actor)


async def request_and_notify_approval(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    action: str,
    risk_tier: str,
    requested_by: str,
    actor: str,
    channel: ApprovalChannel,
    requires_explicit_approval: bool | None = None,
    subject_ref: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> tuple[Approval, ApprovalNotification]:
    """The authoritative request+notify path (B4): ``ApprovalRepository.request`` (unchanged) **then**
    ``ApprovalNotificationService.notify_for_approval`` — writes **both** an ``approval_events`` and an
    ``approval_notifications`` row."""
    approval = await ApprovalRepository(session, context).request(
        project_id=project_id,
        action=action,
        risk_tier=risk_tier,
        requested_by=requested_by,
        requires_explicit_approval=requires_explicit_approval,
        subject_ref=subject_ref,
        payload=payload,
    )
    notification = await ApprovalNotificationService(session, context).notify_for_approval(
        approval, actor=actor, channel=channel
    )
    return approval, notification
