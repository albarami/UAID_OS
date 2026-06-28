"""``qualification_runs`` + ``qualification_case_results`` — tenant-owned qualification evidence (Slice 40).

A run scores **recorded** dry-test cases against the realization's archetype threshold. **B3 honesty
backstop:** ``total_cases``/``passed_cases``/``critical_failure_count``/``coverage_complete`` are
caller-provided but **deferred-trigger-verified against the FK child cases** (migration ``0039``), and
``aggregate_score``/``verdict`` are **GENERATED** (the ORM cannot write them) — so a ``passed`` verdict
can never contradict the recorded cases. Both tables are RLS, SELECT/INSERT-only. Eval-result provenance
is ``caller_supplied_unverified`` (no agent executed — a real eval harness is a later slice).
"""

import uuid
from datetime import datetime

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Single source for the GENERATED expressions — the migration reuses these verbatim so the DB verdict
# and the pure `expected_verdict` can never diverge.
AGGREGATE_EXPR = "CASE WHEN total_cases > 0 THEN passed_cases::numeric / total_cases ELSE 0 END"
VERDICT_EXPR = (
    "CASE WHEN total_cases >= min_cases "
    "AND passed_cases::numeric / NULLIF(total_cases, 0) >= min_aggregate_score "
    "AND (NOT require_zero_critical OR critical_failure_count = 0) "
    "AND coverage_complete THEN 'passed' ELSE 'failed' END"
)


class QualificationRun(Base):
    __tablename__ = "qualification_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["realization_id", "project_id", "tenant_id"],
            [
                "agent_realizations.id",
                "agent_realizations.project_id",
                "agent_realizations.tenant_id",
            ],
            ondelete="RESTRICT",
            name="realization_project_tenant",
        ),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "passed_cases >= 0 AND total_cases >= 0 AND critical_failure_count >= 0 "
            "AND passed_cases <= total_cases",
            name="counts_sane",
        ),
        CheckConstraint("provenance = 'caller_supplied_unverified'", name="provenance_unverified"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_qualification_runs_id_project_tenant"
        ),
        Index("ix_qualification_runs_realization", "tenant_id", "realization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    realization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    archetype_eval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("archetype_evals.id", ondelete="RESTRICT"), nullable=False
    )
    # snapshots (from archetype_evals — no later drift)
    archetype: Mapped[str] = mapped_column(Text, nullable=False)
    eval_version: Mapped[str] = mapped_column(Text, nullable=False)
    min_aggregate_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    require_zero_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    min_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    required_categories: Mapped[list] = mapped_column(JSONB, nullable=False)
    # caller-provided, deferred-trigger-verified against the children
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # GENERATED — the ORM never writes these
    aggregate_score: Mapped[float] = mapped_column(
        Numeric, Computed(AGGREGATE_EXPR, persisted=True), nullable=False
    )
    verdict: Mapped[str] = mapped_column(
        Text, Computed(VERDICT_EXPR, persisted=True), nullable=False
    )
    provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    evaluated_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class QualificationCaseResult(Base):
    __tablename__ = "qualification_case_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "qualification_runs.id",
                "qualification_runs.project_id",
                "qualification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "case_category IN ('positive','negative','edge','adversarial','incomplete')",
            name="case_category_valid",
        ),
        Index("ix_qualification_case_results_run", "tenant_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    case_ref: Mapped[str] = mapped_column(Text, nullable=False)
    case_category: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
