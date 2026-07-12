"""Immutable blind reviewer-call evidence for Slice 45."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class ShortcutDetectorReviewerResult(Base):
    __tablename__ = "shortcut_detector_reviewer_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["shortcut_detector_category_result_id", "project_id", "tenant_id", "category"],
            [
                "shortcut_detector_category_results.id",
                "shortcut_detector_category_results.project_id",
                "shortcut_detector_category_results.tenant_id",
                "shortcut_detector_category_results.category",
            ],
            ondelete="RESTRICT",
            name="category_project_tenant",
        ),
        ForeignKeyConstraint(
            ["reviewer_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            ondelete="RESTRICT",
            name="reviewer_project_tenant",
        ),
        CheckConstraint("reviewer_version_hash ~ '^sha256:[0-9a-f]{64}$'", name="version_hash"),
        CheckConstraint("model_route_hash ~ '^sha256:[0-9a-f]{64}$'", name="model_route_hash"),
        CheckConstraint("response_digest ~ '^sha256:[0-9a-f]{64}$'", name="response_digest"),
        CheckConstraint("execution_status IN ('succeeded','failed','refused')", name="status"),
        CheckConstraint("decision IN ('clean','findings','failed','refused')", name="decision"),
        UniqueConstraint(
            "shortcut_detector_category_result_id",
            "reviewer_instance_id",
            name="uq_sdrr_category_reviewer",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shortcut_detector_category_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_blueprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_blueprints.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_version_hash: Mapped[str] = mapped_column(Text, nullable=False)
    model_route_hash: Mapped[str] = mapped_column(Text, nullable=False)
    blind_call: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    finding_fingerprints: Mapped[list] = mapped_column(JSONB, nullable=False)
    reported_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    response_digest: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
