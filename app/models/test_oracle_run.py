"""Immutable tenant-owned Slice-43 test-oracle execution runs (spec §14)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

AGGREGATE_PASS_RATE_EXPR = (
    "CASE WHEN reported_result_count > 0 "
    "THEN reported_passed_count::numeric / reported_result_count ELSE 0 END"
)
RUN_VERDICT_EXPR = (
    "CASE WHEN execution_status = 'succeeded' "
    "AND observation_provenance = 'connector_verified_ci' "
    "AND reported_result_count > 0 "
    "AND reported_distinct_case_count = required_sample_size "
    "AND reported_passed_count::numeric / NULLIF(reported_result_count,0) >= minimum_pass_rate "
    "AND (oracle_type <> 'judgment' OR (reported_evaluator_lineage_count >= 2 "
    "AND reported_irr >= irr_minimum "
    "AND reported_unresolved_disagreement_count = 0 "
    "AND NOT human_review_required)) "
    "THEN 'passed' ELSE 'failed' END"
)


class TestOracleRun(Base):
    __test__ = False
    __tablename__ = "test_oracle_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["oracle_artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            ondelete="RESTRICT",
            name="oracle_project_tenant",
        ),
        CheckConstraint("definition_schema_version = 'slice43.oracle.v1'", name="schema_version"),
        CheckConstraint("oracle_type IN ('specified','reference','judgment')", name="oracle_type"),
        CheckConstraint(
            "execution_status IN ('succeeded','failed','refused')", name="execution_status"
        ),
        CheckConstraint(
            "observation_provenance IN ('caller_supplied_unverified','connector_verified_ci')",
            name="observation_provenance",
        ),
        CheckConstraint(
            "execution_provenance IN ('system_executed','system_attempted')",
            name="execution_provenance",
        ),
        CheckConstraint("definition_hash ~ '^sha256:[0-9a-f]{64}$'", name="definition_hash"),
        CheckConstraint("repo_binding_hash ~ '^sha256:[0-9a-f]{64}$'", name="repo_binding_hash"),
        CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="commit_sha"),
        CheckConstraint("required_sample_size BETWEEN 1 AND 1000", name="sample_size"),
        CheckConstraint("minimum_pass_rate BETWEEN 0 AND 1", name="pass_rate"),
        CheckConstraint(
            "reported_result_count >= 0 AND reported_passed_count >= 0 "
            "AND reported_passed_count <= reported_result_count "
            "AND reported_distinct_case_count >= 0 "
            "AND reported_evaluator_lineage_count >= 0 "
            "AND reported_unresolved_disagreement_count >= 0",
            name="counts_sane",
        ),
        CheckConstraint(
            "(execution_status = 'succeeded' AND oracle_type = 'judgment' "
            "AND irr_minimum IS NOT NULL AND reported_irr IS NOT NULL "
            "AND reported_evaluator_lineage_count >= 2) OR "
            "(execution_status IN ('failed','refused') AND oracle_type = 'judgment' "
            "AND irr_minimum IS NOT NULL AND reported_irr IS NULL "
            "AND reported_evaluator_lineage_count = 0 "
            "AND reported_unresolved_disagreement_count = 0) OR "
            "(oracle_type <> 'judgment' AND irr_minimum IS NULL AND reported_irr IS NULL "
            "AND reported_evaluator_lineage_count = 0 "
            "AND reported_unresolved_disagreement_count = 0 AND NOT human_review_required)",
            name="judgment_shape",
        ),
        CheckConstraint(
            "(execution_status = 'succeeded' AND failure_code IS NULL "
            "AND execution_provenance = 'system_executed' AND reported_result_count > 0) OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL "
            "AND execution_provenance = 'system_attempted' AND reported_result_count = 0 "
            "AND reported_passed_count = 0 AND reported_distinct_case_count = 0 "
            "AND reported_evaluator_lineage_count = 0 "
            "AND reported_unresolved_disagreement_count = 0)",
            name="execution_shape",
        ),
        CheckConstraint(
            "octet_length(runner_key) BETWEEN 1 AND 128 AND btrim(runner_key) <> '' "
            "AND octet_length(runner_version) BETWEEN 1 AND 64 "
            "AND btrim(runner_version) <> ''",
            name="runner_bounds",
        ),
        CheckConstraint(
            "failure_code IS NULL OR (octet_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code) <> '')",
            name="failure_code_bounds",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_tor_id_project_tenant"),
        Index(
            "ix_test_oracle_runs_latest",
            "tenant_id",
            "project_id",
            "oracle_artifact_id",
            "repo_binding_hash",
            "commit_sha",
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
    oracle_artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    definition_hash: Mapped[str] = mapped_column(Text, nullable=False)
    definition_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    repo_binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    oracle_type: Mapped[str] = mapped_column(Text, nullable=False)
    runner_key: Mapped[str] = mapped_column(Text, nullable=False)
    runner_version: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    observation_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_pass_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    irr_minimum: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reported_result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_passed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_distinct_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_evaluator_lineage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_irr: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    reported_unresolved_disagreement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_pass_rate: Mapped[Decimal] = mapped_column(
        Numeric, Computed(AGGREGATE_PASS_RATE_EXPR, persisted=True), nullable=False
    )
    verdict: Mapped[str] = mapped_column(
        Text, Computed(RUN_VERDICT_EXPR, persisted=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
