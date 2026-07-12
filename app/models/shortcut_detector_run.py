"""Tenant-owned immutable Slice-45 shortcut detector runs."""

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

from app.models.base import Base


class ShortcutDetectorRun(Base):
    __tablename__ = "shortcut_detector_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint("provider = 'github'", name="provider"),
        CheckConstraint("schema_version = 'slice45.shortcut_review.v1'", name="schema_version"),
        CheckConstraint("repo_binding_hash ~ '^sha256:[0-9a-f]{64}$'", name="repo_hash"),
        CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="commit_sha"),
        CheckConstraint("detector_contract_hash ~ '^sha256:[0-9a-f]{64}$'", name="contract_hash"),
        CheckConstraint(
            "corpus_digest IS NULL OR corpus_digest ~ '^sha256:[0-9a-f]{64}$'", name="corpus_digest"
        ),
        CheckConstraint("execution_status IN ('succeeded','failed','refused')", name="status"),
        CheckConstraint("coverage_verdict IN ('covered','failed')", name="verdict"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_sdr_id_project_tenant"),
        Index(
            "ix_shortcut_detector_runs_latest",
            "tenant_id",
            "project_id",
            "repo_binding_hash",
            "detector_contract_hash",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    repo_binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    detector_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    corpus_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    corpus_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic_execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    review_execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_category_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_reviewer_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_reviewer_result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    coverage_verdict: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
