"""Immutable per-category deterministic + independent-review shortcut coverage."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShortcutDetectorCategoryResult(Base):
    __tablename__ = "shortcut_detector_category_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["shortcut_detector_run_id", "project_id", "tenant_id"],
            [
                "shortcut_detector_runs.id",
                "shortcut_detector_runs.project_id",
                "shortcut_detector_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint(
            "detector_evidence_digest ~ '^sha256:[0-9a-f]{64}$'", name="evidence_digest"
        ),
        CheckConstraint(
            "deterministic_status IN ('completed','failed','refused')", name="deterministic_status"
        ),
        CheckConstraint("review_status IN ('completed','failed','refused')", name="review_status"),
        CheckConstraint(
            "coverage_status IN ('completed_clean','completed_with_findings','failed','refused')",
            name="coverage_status",
        ),
        UniqueConstraint("shortcut_detector_run_id", "category", name="uq_sdcr_run_category"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", "category", name="uq_sdcr_attachment_target"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shortcut_detector_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic_status: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_status: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic_fingerprints: Mapped[list] = mapped_column(JSONB, nullable=False)
    reported_reviewer_result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    detector_evidence_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
