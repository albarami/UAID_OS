"""``approval_events`` — tenant-owned, append-only per-approval lifecycle history.

Insert-only (no UPDATE/DELETE grant). The global tamper-evident trail is the
Slice 2 audit log; this table is the operational per-approval transition log.
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

_EVENT_TYPES = ("requested", "approved", "rejected", "cancelled", "expired", "proceeded_by_policy")


class ApprovalEvent(Base):
    __tablename__ = "approval_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["approval_id", "tenant_id"],
            ["approvals.id", "approvals.tenant_id"],
            ondelete="RESTRICT",
            name="approval_tenant",
        ),
        CheckConstraint(
            f"event_type IN ({', '.join(repr(e) for e in _EVENT_TYPES)})", name="event_type_valid"
        ),
        Index(None, "tenant_id"),
        Index(None, "approval_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
