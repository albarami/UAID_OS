"""cost learning aggregates and optimizer

Revision ID: 0061
Revises: 0060
Create Date: 2026-08-23

Slice 62 — tenant-safe cross-project aggregates + decision-only cost optimizer.
Purely additive. Does not alter A5, readiness, go-live, or any frozen module.
Publish is not DDL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.ecosystem.learning_db_checks import (
    BUCKET_CHECK_CONSTRAINTS,
    OPT_RUN_CHECK_CONSTRAINTS,
    RUN_CHECK_CONSTRAINTS,
)
from app.ecosystem.learning_ddl import (
    drop_learning_guards,
    install_learning_guards,
    populated_downgrade_sql,
)

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cross_project_aggregate_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "ruleset_version",
            sa.Text(),
            server_default=sa.text("'slice62.v1'"),
            nullable=False,
        ),
        sa.Column(
            "contract_version",
            sa.Text(),
            server_default=sa.text("'slice62.aggregates.v1'"),
            nullable=False,
        ),
        sa.Column("bucket_count", sa.SmallInteger(), nullable=False),
        sa.Column("published_bucket_count", sa.SmallInteger(), nullable=False),
        sa.Column(
            "publisher",
            sa.Text(),
            server_default=sa.text("'slice62.learning_publish'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        *[sa.CheckConstraint(sql, name=name) for name, sql in RUN_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "cross_project_aggregate_buckets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("signal_class", sa.Text(), nullable=False),
        sa.Column("bucket_key", sa.Text(), nullable=False),
        sa.Column("n_events", sa.Integer(), nullable=False),
        sa.Column("n_projects", sa.Integer(), nullable=False),
        sa.Column("n_tenants", sa.Integer(), nullable=False),
        sa.Column("metric_sum", sa.Numeric(18, 6), nullable=True),
        sa.Column("metric_unit", sa.Text(), nullable=False),
        sa.Column(
            "published",
            sa.Boolean(),
            sa.Computed("n_projects >= 3 AND n_tenants >= 2", persisted=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["cross_project_aggregate_runs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("run_id", "signal_class", "bucket_key", name="uq_cpab_run_class_key"),
        *[sa.CheckConstraint(sql, name=name) for name, sql in BUCKET_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "cost_optimizer_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_class", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("ambiguity_high", sa.Boolean(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("cheap_first_for_low_risk", sa.Boolean(), nullable=False),
        sa.Column("frontier_for_high_risk", sa.Boolean(), nullable=False),
        sa.Column("use_cached_context_when_possible", sa.Boolean(), nullable=False),
        sa.Column("flags_source", sa.Text(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=True),
        sa.Column("base_policy_tier", sa.Text(), nullable=False),
        sa.Column("clamped_policy_tier", sa.Text(), nullable=False),
        sa.Column("recommended_tier", sa.Text(), nullable=False),
        sa.Column("overlay_applied", sa.Text(), nullable=False),
        sa.Column("cache_hint", sa.Boolean(), nullable=False),
        sa.Column("requires_multiple_reviewers", sa.Boolean(), nullable=False),
        sa.Column("requires_model_diversity", sa.Boolean(), nullable=False),
        sa.Column("published_bucket_count", sa.SmallInteger(), nullable=False),
        sa.Column("citation_count", sa.SmallInteger(), nullable=False),
        sa.Column("aggregate_run_id", sa.UUID(), nullable=True),
        sa.Column(
            "ruleset_version",
            sa.Text(),
            server_default=sa.text("'slice62.v1'"),
            nullable=False,
        ),
        sa.Column(
            "execution_provenance",
            sa.Text(),
            server_default=sa.text("'system_derived_cost_recommendation'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "cost_forecast_policy_versions.id",
                "cost_forecast_policy_versions.project_id",
                "cost_forecast_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
            name="policy_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["aggregate_run_id"],
            ["cross_project_aggregate_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_cor_id_project_tenant"),
        *[sa.CheckConstraint(sql, name=name) for name, sql in OPT_RUN_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "cost_optimizer_citations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("bucket_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "cost_optimizer_runs.id",
                "cost_optimizer_runs.project_id",
                "cost_optimizer_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["bucket_id"],
            ["cross_project_aggregate_buckets.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("run_id", "bucket_id", name="uq_coc_run_bucket"),
    )
    install_learning_guards()


def downgrade() -> None:
    op.execute(populated_downgrade_sql())
    drop_learning_guards()
    op.drop_table("cost_optimizer_citations")
    op.drop_table("cost_optimizer_runs")
    op.drop_table("cross_project_aggregate_buckets")
    op.drop_table("cross_project_aggregate_runs")
