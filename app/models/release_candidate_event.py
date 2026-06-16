"""``release_candidate_events`` — append-only lifecycle trail for release candidates (Slice 25).

One row per lifecycle action (``created``/``frozen``/``superseded``/``canceled``/``issue_bound``).
Tenant-owned + RLS; **append-only** (SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked by triggers,
migration ``0024``). Pinned to its candidate's tenant via a composite FK. ``actor`` is an UNTRUSTED
caller label.
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


class ReleaseCandidateEvent(Base):
    __tablename__ = "release_candidate_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_candidate_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
            name="release_candidate_tenant",
        ),
        Index(
            "ix_release_candidate_events_candidate",
            "tenant_id",
            "release_candidate_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
