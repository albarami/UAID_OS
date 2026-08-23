"""stabilization-window assessment store (non-closing §25.4 / §26.6)

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-23

Slice 59 — tenant-owned stabilization-window assessment. Seq 5 is the only
pass path. Does not close §25.4 or §26.6. Does not change A5, readiness,
control_loop, or Slice 56–58 CHECK modules.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.ops.stabilization_db_checks import (
    ASSESSOR_SHAPE_SQL,
    CRITERION_CHECK_CONSTRAINTS,
    IMPROVEMENT_CHECK_CONSTRAINTS,
    WINDOW_COUNTER_SQL,
)
from app.ops.stabilization_ddl import (
    drop_stabilization_guards,
    install_stabilization_guards,
    populated_downgrade_sql,
)

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HASH = r"^sha256:[0-9a-f]{64}$"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_mss_id_project_tenant",
        "monitoring_status_snapshots",
        ["id", "project_id", "tenant_id"],
    )
    op.create_unique_constraint(
        "uq_osh_id_project_tenant",
        "ops_support_handovers",
        ["id", "project_id", "tenant_id"],
    )
    op.create_unique_constraint(
        "uq_ifr_id_project_tenant",
        "intake_findings_reports",
        ["id", "project_id", "tenant_id"],
    )
    op.create_table(
        "ops_stabilization_windows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clock_basis", sa.Text(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_digest", sa.Text(), nullable=False),
        sa.Column("monitoring_target_ref", sa.Text(), nullable=True),
        sa.Column("monitoring_max_age_hours", sa.Integer(), nullable=False),
        sa.Column("deployment_max_age_hours", sa.Integer(), nullable=False),
        sa.Column("assessor_subject", sa.Text(), nullable=False),
        sa.Column("assessor_actor_type", sa.Text(), nullable=True),
        sa.Column("assessor_provenance", sa.Text(), nullable=False),
        sa.Column("follow_up_posture", sa.Text(), nullable=False),
        sa.Column("extension_required", sa.Boolean(), nullable=False),
        sa.Column("extends_window_id", sa.UUID(), nullable=True),
        sa.Column("criterion_count", sa.Integer(), nullable=False),
        sa.Column("improvement_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("not_observed_count", sa.Integer(), nullable=False),
        sa.Column("not_evaluable_count", sa.Integer(), nullable=False),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column("input_digest", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset_version='slice59.v1'", name="ruleset_version"),
        sa.CheckConstraint("status='open'", name="status"),
        sa.CheckConstraint(
            "clock_basis='transaction_timestamp_not_production_uptime'", name="clock_basis"
        ),
        sa.CheckConstraint("criterion_count=8", name="criterion_count"),
        sa.CheckConstraint("improvement_count=8", name="improvement_count"),
        sa.CheckConstraint(WINDOW_COUNTER_SQL, name="status_counters"),
        sa.CheckConstraint("extension_required IS TRUE", name="extension_required"),
        sa.CheckConstraint(
            "follow_up_posture IN ('none','required_not_executed')", name="follow_up_posture"
        ),
        sa.CheckConstraint(
            "assessor_provenance IN ('caller_supplied_unverified','request_authenticated')",
            name="assessor_provenance",
        ),
        sa.CheckConstraint(ASSESSOR_SHAPE_SQL, name="assessor_shape"),
        sa.CheckConstraint(
            "char_length(assessor_subject) BETWEEN 1 AND 200 "
            "AND assessor_subject = btrim(assessor_subject)",
            name="assessor_subject",
        ),
        sa.CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        sa.CheckConstraint(f"policy_digest ~ '{_HASH}'", name="policy_digest"),
        sa.CheckConstraint(f"request_digest ~ '{_HASH}'", name="request_digest"),
        sa.CheckConstraint(f"input_digest ~ '{_HASH}'", name="input_digest"),
        sa.CheckConstraint(
            "monitoring_max_age_hours BETWEEN 1 AND 168 "
            "AND deployment_max_age_hours BETWEEN 1 AND 168",
            name="age_hours",
        ),
        sa.CheckConstraint(
            "monitoring_target_ref IS NULL OR ("
            "char_length(monitoring_target_ref) BETWEEN 1 AND 2048 "
            "AND monitoring_target_ref = btrim(monitoring_target_ref))",
            name="monitoring_target_ref",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["category_id", "project_id", "tenant_id"],
            [
                "intake_categories.id",
                "intake_categories.project_id",
                "intake_categories.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["extends_window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_stab_windows_id_project_tenant"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "idempotency_key",
            name="uq_ops_stab_windows_idempotency",
        ),
    )
    op.create_index(
        "ix_ops_stab_windows_latest",
        "ops_stabilization_windows",
        ["tenant_id", "project_id", "created_at"],
    )
    op.create_table(
        "ops_stabilization_criterion_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("window_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("criterion_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("monitoring_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("rollback_verification_run_id", sa.UUID(), nullable=True),
        sa.Column("handover_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('passed','failed','not_observed','not_evaluable')", name="status"
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in CRITERION_CHECK_CONSTRAINTS],
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["monitoring_snapshot_id", "project_id", "tenant_id"],
            [
                "monitoring_status_snapshots.id",
                "monitoring_status_snapshots.project_id",
                "monitoring_status_snapshots.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_verification_run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["handover_id", "project_id", "tenant_id"],
            [
                "ops_support_handovers.id",
                "ops_support_handovers.project_id",
                "ops_support_handovers.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "window_id", "seq", name="uq_ops_stab_criteria_window_seq"
        ),
    )
    op.create_table(
        "ops_improvement_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("window_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("improvement_class", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("findings_report_id", sa.UUID(), nullable=True),
        sa.Column("cost_forecast_run_id", sa.UUID(), nullable=True),
        sa.Column("metric_int", sa.Integer(), nullable=True),
        sa.Column("refresh_posture", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('observed','not_observed')", name="status"),
        sa.CheckConstraint(
            "refresh_posture IS NULL OR refresh_posture='recorded_not_refreshed'",
            name="refresh_posture",
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in IMPROVEMENT_CHECK_CONSTRAINTS],
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["findings_report_id", "project_id", "tenant_id"],
            [
                "intake_findings_reports.id",
                "intake_findings_reports.project_id",
                "intake_findings_reports.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cost_forecast_run_id", "project_id", "tenant_id"],
            [
                "cost_forecast_runs.id",
                "cost_forecast_runs.project_id",
                "cost_forecast_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "window_id", "seq", name="uq_ops_improvement_results_window_seq"
        ),
    )
    op.create_table(
        "ops_stabilization_closure_attempts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("window_id", sa.UUID(), nullable=False),
        sa.Column("result_code", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result_code IN ("
            "'refused_latch_active','refused_unauthenticated',"
            "'refused_same_actor','refused_incomplete_criteria')",
            name="result_code",
        ),
        sa.CheckConstraint(
            "char_length(actor) BETWEEN 1 AND 200 AND actor = btrim(actor)",
            name="actor",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ops_stab_closure_latest",
        "ops_stabilization_closure_attempts",
        ["tenant_id", "project_id", "created_at"],
    )
    install_stabilization_guards()


def downgrade() -> None:
    op.execute(populated_downgrade_sql())
    drop_stabilization_guards()
    op.drop_index("ix_ops_stab_closure_latest", table_name="ops_stabilization_closure_attempts")
    op.drop_table("ops_stabilization_closure_attempts")
    op.drop_table("ops_improvement_results")
    op.drop_table("ops_stabilization_criterion_results")
    op.drop_index("ix_ops_stab_windows_latest", table_name="ops_stabilization_windows")
    op.drop_table("ops_stabilization_windows")
    op.drop_constraint("uq_ifr_id_project_tenant", "intake_findings_reports", type_="unique")
    op.drop_constraint("uq_osh_id_project_tenant", "ops_support_handovers", type_="unique")
    op.drop_constraint("uq_mss_id_project_tenant", "monitoring_status_snapshots", type_="unique")
