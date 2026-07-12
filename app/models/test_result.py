"""Immutable per-case Slice-43 test results; outcomes are DB-generated."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

RESULT_PASSED_EXPR = (
    "CASE "
    "WHEN result_kind = 'specified_exact' THEN expected_digest = observed_digest "
    "WHEN result_kind = 'reference_exact' THEN reference_digest = observed_digest "
    "WHEN result_kind = 'reference_percentage' THEN "
    "CASE WHEN reference_numeric = 0 THEN observed_numeric = 0 "
    "ELSE abs(observed_numeric-reference_numeric)/abs(reference_numeric) <= tolerance_numeric END "
    "WHEN result_kind = 'judgment_vote' THEN judgment_label "
    "ELSE false END"
)

TYPE_SHAPE_CHECK = (
    "(result_kind = 'specified_exact' AND expected_digest IS NOT NULL "
    "AND observed_digest IS NOT NULL AND reference_digest IS NULL "
    "AND observed_numeric IS NULL AND reference_numeric IS NULL "
    "AND tolerance_numeric IS NULL AND evaluator_instance_id IS NULL "
    "AND evaluator_version_hash IS NULL "
    "AND llm_provider IS NULL AND llm_model IS NULL "
    "AND input_tokens IS NULL AND output_tokens IS NULL AND cost_external_ref IS NULL "
    "AND sample_class IS NULL "
    "AND judgment_label IS NULL AND criterion_scores = '{}'::jsonb) OR "
    "(result_kind = 'reference_exact' AND reference_digest IS NOT NULL "
    "AND observed_digest IS NOT NULL AND expected_digest IS NULL "
    "AND observed_numeric IS NULL AND reference_numeric IS NULL "
    "AND tolerance_numeric IS NULL AND evaluator_instance_id IS NULL "
    "AND evaluator_version_hash IS NULL "
    "AND llm_provider IS NULL AND llm_model IS NULL "
    "AND input_tokens IS NULL AND output_tokens IS NULL AND cost_external_ref IS NULL "
    "AND sample_class IS NULL "
    "AND judgment_label IS NULL AND criterion_scores = '{}'::jsonb) OR "
    "(result_kind = 'reference_percentage' AND observed_numeric IS NOT NULL "
    "AND reference_numeric IS NOT NULL AND tolerance_numeric BETWEEN 0 AND 1 "
    "AND expected_digest IS NULL AND observed_digest IS NULL AND reference_digest IS NULL "
    "AND evaluator_instance_id IS NULL AND evaluator_version_hash IS NULL "
    "AND llm_provider IS NULL AND llm_model IS NULL "
    "AND input_tokens IS NULL AND output_tokens IS NULL AND cost_external_ref IS NULL "
    "AND sample_class IS NULL "
    "AND judgment_label IS NULL "
    "AND criterion_scores = '{}'::jsonb) OR "
    "(result_kind = 'judgment_vote' AND evaluator_instance_id IS NOT NULL "
    "AND evaluator_version_hash ~ '^sha256:[0-9a-f]{64}$' "
    "AND judgment_label IS NOT NULL AND jsonb_typeof(criterion_scores) = 'object' "
    "AND criterion_scores <> '{}'::jsonb "
    "AND octet_length(criterion_scores::text) <= 8192 "
    "AND sample_class IS NOT NULL "
    "AND octet_length(llm_provider) BETWEEN 1 AND 128 AND btrim(llm_provider) <> '' "
    "AND octet_length(llm_model) BETWEEN 1 AND 256 AND btrim(llm_model) <> '' "
    "AND input_tokens BETWEEN 1 AND 1000000 AND output_tokens BETWEEN 1 AND 1000000 "
    "AND octet_length(cost_external_ref) BETWEEN 1 AND 512 "
    "AND expected_digest IS NULL AND observed_digest IS NULL AND reference_digest IS NULL "
    "AND observed_numeric IS NULL AND reference_numeric IS NULL AND tolerance_numeric IS NULL)"
)


class TestResult(Base):
    __test__ = False
    __tablename__ = "test_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["test_oracle_run_id", "project_id", "tenant_id"],
            ["test_oracle_runs.id", "test_oracle_runs.project_id", "test_oracle_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        ForeignKeyConstraint(
            ["evaluator_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            ondelete="RESTRICT",
            name="evaluator_project_tenant",
        ),
        CheckConstraint(
            "result_kind IN "
            "('specified_exact','reference_exact','reference_percentage','judgment_vote')",
            name="result_kind",
        ),
        CheckConstraint(
            "sample_class IS NULL OR sample_class IN "
            "('representative','adversarial','calibration','other')",
            name="sample_class",
        ),
        CheckConstraint(
            "octet_length(case_ref) BETWEEN 1 AND 128 AND btrim(case_ref) <> ''",
            name="case_ref_bounds",
        ),
        CheckConstraint(
            "expected_digest IS NULL OR expected_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="expected_digest",
        ),
        CheckConstraint(
            "observed_digest IS NULL OR observed_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="observed_digest",
        ),
        CheckConstraint(
            "reference_digest IS NULL OR reference_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="reference_digest",
        ),
        CheckConstraint(TYPE_SHAPE_CHECK, name="type_shape"),
        Index("ix_test_results_run", "tenant_id", "test_oracle_run_id", "case_ref"),
        Index(
            "uq_test_results_deterministic_case",
            "test_oracle_run_id",
            "case_ref",
            unique=True,
            postgresql_where=text("evaluator_instance_id IS NULL"),
        ),
        Index(
            "uq_test_results_judgment_vote",
            "test_oracle_run_id",
            "case_ref",
            "evaluator_instance_id",
            unique=True,
            postgresql_where=text("evaluator_instance_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_oracle_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    case_ref: Mapped[str] = mapped_column(Text, nullable=False)
    sample_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_kind: Mapped[str] = mapped_column(Text, nullable=False)
    expected_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_numeric: Mapped[Decimal | None] = mapped_column(Numeric(30, 12), nullable=True)
    reference_numeric: Mapped[Decimal | None] = mapped_column(Numeric(30, 12), nullable=True)
    tolerance_numeric: Mapped[Decimal | None] = mapped_column(Numeric(12, 9), nullable=True)
    evaluator_instance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    evaluator_version_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    criterion_scores: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    judgment_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    passed: Mapped[bool] = mapped_column(
        Boolean, Computed(RESULT_PASSED_EXPR, persisted=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
