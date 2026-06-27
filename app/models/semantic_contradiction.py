"""``semantic_contradictions`` — tenant-owned, append-only pairwise semantic contradictions (Slice 37).

One immutable row per detected PAIRWISE contradiction: a §6.4 `conflict_type`, a bounded `description`, and
the two conflicting spine artifacts as **composite-FK-proven** `artifact_a_id`/`artifact_b_id` (DB proves
both exist in the same project/tenant — B4) with `CHECK a<>b` (distinctness). A BEFORE-INSERT kind guard
proves both artifacts are `requirement`/`acceptance_criterion` (B7); child-side + report-side DEFERRABLE
triggers keep the report's `contradiction_count` matching the child rows (B6/B9). Append-only (SELECT/INSERT).
Descriptive only — no resolution is ever chosen (§6.4).
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

from app.intake.semantic_contradictions import CONFLICT_TYPES, MAX_DESCRIPTION_CHARS
from app.models.base import Base

_CT = ", ".join(repr(v) for v in CONFLICT_TYPES)


class SemanticContradiction(Base):
    __tablename__ = "semantic_contradictions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["report_id", "project_id", "tenant_id"],
            [
                "semantic_contradiction_reports.id",
                "semantic_contradiction_reports.project_id",
                "semantic_contradiction_reports.tenant_id",
            ],
            ondelete="RESTRICT",
            name="report_project_tenant",
        ),
        ForeignKeyConstraint(
            ["artifact_a_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            ondelete="RESTRICT",
            name="artifact_a_project_tenant",
        ),
        ForeignKeyConstraint(
            ["artifact_b_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            ondelete="RESTRICT",
            name="artifact_b_project_tenant",
        ),
        CheckConstraint(f"conflict_type IN ({_CT})", name="conflict_type_valid"),
        CheckConstraint(
            f"char_length(description) BETWEEN 1 AND {MAX_DESCRIPTION_CHARS}",
            name="description_bounded",
        ),
        CheckConstraint("artifact_a_id <> artifact_b_id", name="artifacts_distinct"),
        Index("ix_semantic_contradictions_report", "tenant_id", "report_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conflict_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    artifact_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
