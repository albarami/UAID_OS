"""``semantic_contradiction_reports`` — tenant-owned, append-only semantic-detection run snapshots (Slice 37).

One immutable row per `detect` run over the project's spine requirement+AC artifacts. `outcome` includes
`skipped_insufficient_input` (the no-call `<2`-artifacts outcome, B1). `contradiction_count` is DB-bound to
the child `semantic_contradictions` rows by report-side **and** child-side DEFERRABLE constraint triggers
(B6/B9, migration `0036`). Append-only (SELECT/INSERT only). Kept SEPARATE from the Slice-13 structural
`intake_findings_reports`. Descriptive only — no readiness/A5/go-live effect.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.intake.semantic_contradictions import MAX_CONTRADICTIONS_PERSISTED, OUTCOMES
from app.models.base import Base

_OUT = ", ".join(repr(v) for v in OUTCOMES)


class SemanticContradictionReport(Base):
    __tablename__ = "semantic_contradiction_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(f"outcome IN ({_OUT})", name="outcome_valid"),
        CheckConstraint(
            f"contradiction_count BETWEEN 0 AND {MAX_CONTRADICTIONS_PERSISTED}",
            name="contradiction_count_bounded",
        ),
        CheckConstraint("analyzed_artifact_count >= 0", name="analyzed_artifact_count_nonneg"),
        UniqueConstraint(
            "id",
            "project_id",
            "tenant_id",
            name="uq_semantic_contradiction_reports_id_project_tenant",
        ),
        Index("ix_semantic_contradiction_reports_latest", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    cost_external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    contradiction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    analyzed_artifact_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    input_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    detected_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
