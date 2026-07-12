"""Immutable tenant-owned Slice-44 security-scan observation runs."""

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


class SecurityScanRun(Base):
    __tablename__ = "security_scan_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint("provider = 'github'", name="provider"),
        CheckConstraint(
            "artifact_schema_version = 'slice44.security_scan.v1'", name="schema_version"
        ),
        CheckConstraint(
            "execution_status IN ('succeeded','failed','refused')", name="execution_status"
        ),
        CheckConstraint(
            "artifact_provenance IN "
            "('caller_supplied_unverified','connector_verified_ci_security')",
            name="artifact_provenance",
        ),
        CheckConstraint(
            "execution_observation IN ('connector_observed_ci','connector_attempted')",
            name="execution_observation",
        ),
        CheckConstraint("repo_binding_hash ~ '^sha256:[0-9a-f]{64}$'", name="repo_hash"),
        CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="commit_sha"),
        CheckConstraint(
            "scanner_manifest_hash = "
            "'sha256:76fc89f3fb671c61c08b5ddeccda651fc2afce35d5f5d7970e20b027070638fb'",
            name="manifest_hash",
        ),
        CheckConstraint(
            "artifact_digest IS NULL OR artifact_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="artifact_digest",
        ),
        CheckConstraint(
            "reported_category_count BETWEEN 0 AND 5 "
            "AND reported_finding_count BETWEEN 0 AND 1000",
            name="counts",
        ),
        CheckConstraint("coverage_verdict IN ('covered','failed')", name="coverage_verdict"),
        CheckConstraint(
            "(execution_status = 'succeeded' AND failure_code IS NULL "
            "AND artifact_digest IS NOT NULL "
            "AND artifact_provenance = 'connector_verified_ci_security' "
            "AND execution_observation = 'connector_observed_ci') OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL "
            "AND artifact_digest IS NULL AND reported_category_count = 0 "
            "AND reported_finding_count = 0 AND NOT coverage_complete "
            "AND coverage_verdict = 'failed' "
            "AND execution_observation = 'connector_attempted')",
            name="execution_shape",
        ),
        CheckConstraint(
            "failure_code IS NULL OR (octet_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code) <> '')",
            name="failure_code",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_ssr_id_project_tenant"),
        Index(
            "ix_security_scan_runs_latest",
            "tenant_id",
            "project_id",
            "repo_binding_hash",
            "scanner_manifest_hash",
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
    artifact_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    scanner_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    execution_observation: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_category_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    coverage_verdict: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
