"""``intake_findings_reports`` — tenant-owned, append-only findings snapshots (Slice 13).

One immutable row per gap/contradiction evaluation (history preserved; each run inserts
a new snapshot). Append-only: SELECT/INSERT only for the runtime role; UPDATE/DELETE/
TRUNCATE blocked by triggers (migration ``0016``). The §-level findings live in the
``report`` JSONB (refs only — never titles/body/data). ``created_at`` uses
``clock_timestamp()`` so two snapshots in one transaction order deterministically.
``evaluated_by`` is an untrusted caller label.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntakeFindingsReport(Base):
    __tablename__ = "intake_findings_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint("gap_count >= 0", name="gap_count_non_negative"),
        CheckConstraint("contradiction_count >= 0", name="contradiction_count_non_negative"),
        Index(
            "ix_intake_findings_reports_tenant_project_created",
            "tenant_id",
            "project_id",
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
    gap_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contradiction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
