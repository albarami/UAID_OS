"""Tenant-owned append-only Slice 62 cost-optimizer runs and citations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ecosystem.learning_db_checks import OPT_RUN_CHECK_CONSTRAINTS
from app.models.base import Base


class CostOptimizerRun(Base):
    """One tenant-owned tier recommendation."""

    __tablename__ = "cost_optimizer_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "cost_forecast_policy_versions.id",
                "cost_forecast_policy_versions.project_id",
                "cost_forecast_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
            name="policy_project_tenant",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_cor_id_project_tenant"),
        *[CheckConstraint(sql, name=name) for name, sql in OPT_RUN_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_class: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    ambiguity_high: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    cheap_first_for_low_risk: Mapped[bool] = mapped_column(Boolean, nullable=False)
    frontier_for_high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False)
    use_cached_context_when_possible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    flags_source: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    base_policy_tier: Mapped[str] = mapped_column(Text, nullable=False)
    clamped_policy_tier: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_tier: Mapped[str] = mapped_column(Text, nullable=False)
    overlay_applied: Mapped[str] = mapped_column(Text, nullable=False)
    cache_hint: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_multiple_reviewers: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_model_diversity: Mapped[bool] = mapped_column(Boolean, nullable=False)
    published_bucket_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    citation_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    aggregate_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cross_project_aggregate_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    ruleset_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'slice62.v1'")
    )
    execution_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'system_derived_cost_recommendation'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CostOptimizerCitation(Base):
    """One used published bucket. FK is identity-only."""

    __tablename__ = "cost_optimizer_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "cost_optimizer_runs.id",
                "cost_optimizer_runs.project_id",
                "cost_optimizer_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        UniqueConstraint("run_id", "bucket_id", name="uq_coc_run_bucket"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cross_project_aggregate_buckets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
