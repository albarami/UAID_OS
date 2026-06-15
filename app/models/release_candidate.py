"""``release_candidates`` — tenant-owned release-candidate / release-binding namespace (Slice 25,
spec §24.1 / Appendix B #7).

Tenant-owned + RLS; **no DELETE**. A DB guard (migration ``0024``) enforces the lifecycle: created
``draft``; one-way ``draft`` → ``frozen``|``canceled`` and ``frozen`` → ``superseded``|``canceled``;
``frozen_at`` set iff entering ``frozen``; identity immutable; a same-status update changes nothing.
This row is the **future** referent for Slice-22 ``risk_acceptance_records.release_id`` — **not yet
FK'd or validated**. It never asserts issue completeness or enables go-live.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReleaseCandidate(Base):
    __tablename__ = "release_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "project_id", "release_ref", name="uq_release_candidates_ref"
        ),
        # event FK target (mirrors the Slice 23/24 event-table pattern).
        UniqueConstraint("id", "tenant_id", name="uq_release_candidates_id_tenant"),
        # binding FK target.
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_release_candidates_id_proj_tenant"
        ),
        Index("ix_release_candidates_tenant_project_status", "tenant_id", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_ref: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
