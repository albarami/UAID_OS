"""``readiness_reports`` — tenant-owned, append-only readiness snapshots (Slice 12, §4.5).

One immutable row per readiness evaluation (history is preserved; each run inserts a
new snapshot). Append-only: SELECT/INSERT only for the runtime role, with
UPDATE/DELETE/TRUNCATE blocked by triggers (migration ``0015``). ``readiness_level``
permits ``R0..R5`` for forward compatibility; the auditor emits ``R0``/``R1``/``R2``,
``R3`` (Slice 16, R2 base plus the three §4.3 technical categories declared via Slice 15),
and ``R4`` (Slice 18, R3 base plus the two §4.3 "tools" categories declared plus zero spine
gaps). It is **capped at R4** — R5 requires gated-engine completeness + further rules not yet
implemented. The full §4.5 document (plus deterministic extension keys) lives in ``report``;
``evaluated_by`` is an untrusted caller label.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReadinessReportRecord(Base):
    __tablename__ = "readiness_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "readiness_level IN ('R0','R1','R2','R3','R4','R5')", name="readiness_level_valid"
        ),
        Index(
            "ix_readiness_reports_tenant_project_created",
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
    readiness_level: Mapped[str] = mapped_column(Text, nullable=False)
    can_build_to_staging: Mapped[bool] = mapped_column(Boolean, nullable=False)
    can_go_live_autonomously: Mapped[bool] = mapped_column(Boolean, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(Text, nullable=False)
    # clock_timestamp() (not now()) so two snapshots inserted in the same transaction
    # get strictly increasing timestamps — latest()/history() ordering stays correct.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
