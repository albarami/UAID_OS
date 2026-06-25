"""``approval_notifications`` — tenant-owned, append-only approval-channel notification log (Slice 33, §18.2).

One immutable row per routed/delivered notification for an approval. Append-only (migration ``0032``).
Records **only** the routing facts ``(approval_id, risk_tier, routing_mode, channel, status)`` — there is
**no recipient/URL/credential column** (structural: **no secret material**). The composite FK
``(approval_id, project_id, tenant_id) → approvals(id, project_id, tenant_id)`` DB-proves that the
notification's project/tenant matches the approval's (B3). ``digest`` is a routing **label** only (no
scheduler this slice). **Store/infra-only — never flips an A5 gate / readiness level.**
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_TIERS = ("low", "medium", "high", "production")


class ApprovalNotification(Base):
    __tablename__ = "approval_notifications"
    __table_args__ = (
        # Composite FK pins the notification to the SAME approval+project+tenant (B3).
        ForeignKeyConstraint(
            ["approval_id", "project_id", "tenant_id"],
            ["approvals.id", "approvals.project_id", "approvals.tenant_id"],
            ondelete="RESTRICT",
            name="approval_project_tenant",
        ),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            f"risk_tier IN ({', '.join(repr(t) for t in _TIERS)})", name="ck_an_risk_tier_valid"
        ),
        CheckConstraint("routing_mode IN ('digest','realtime')", name="ck_an_routing_mode_valid"),
        CheckConstraint("channel IN ('dashboard')", name="ck_an_channel_valid"),
        CheckConstraint("status IN ('delivered','failed','skipped')", name="ck_an_status_valid"),
        Index(
            "ix_an_tenant_project_approval_created",
            "tenant_id",
            "project_id",
            "approval_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    risk_tier: Mapped[str] = mapped_column(Text, nullable=False)
    routing_mode: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
