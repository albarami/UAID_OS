"""``risk_acceptance_events`` — append-only lifecycle trail for risk-acceptance records (Slice 22).

One row per lifecycle action (``created``/``revoked``/``superseded``/``expired``). Tenant-owned +
RLS; **append-only** (SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked by triggers, migration
``0021``). Pinned to its record's tenant via a composite FK. ``actor`` is an UNTRUSTED caller label.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
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


class RiskAcceptanceEvent(Base):
    __tablename__ = "risk_acceptance_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["record_id", "tenant_id"],
            ["risk_acceptance_records.id", "risk_acceptance_records.tenant_id"],
            ondelete="RESTRICT",
            name="record_tenant",
        ),
        Index("ix_risk_acceptance_events_record", "tenant_id", "record_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
