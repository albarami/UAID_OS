"""hotfix-intent evaluation store (non-closing §26.6)

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-22

Slice 58 — local A2 plans + fail-closed production non-execution + current
Slice 52/54 rollback context. Does not close self-healing. Does not change A5,
readiness, control_loop, Slice-56 db_checks, or Slice-57 incident CHECKs.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.ops.hotfix_db_checks import CHILD_CHECK_CONSTRAINTS, DECISION_SNAPSHOT_SQL
from app.ops.hotfix_ddl import drop_hotfix_guards, install_hotfix_guards, populated_downgrade_sql

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HASH = r"^sha256:[0-9a-f]{64}$"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_era_id_project_tenant",
        "emergency_rollback_authorizations",
        ["id", "project_id", "tenant_id"],
    )
    op.create_table(
        "ops_self_healing_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("action_count", sa.Integer(), nullable=False),
        sa.Column("policy_present", sa.Boolean(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=True),
        sa.Column("autonomy_level_snapshot", sa.Integer(), nullable=True),
        sa.Column("policy_input_digest", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column("decision_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("rollback_verification_run_id", sa.UUID(), nullable=True),
        sa.Column("emergency_control_binding_id", sa.UUID(), nullable=True),
        sa.Column("emergency_rollback_authorization_id", sa.UUID(), nullable=True),
        sa.Column("rollback_coverage_digest", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset_version='slice58.v1'", name="ruleset_version"),
        sa.CheckConstraint("action_count=5", name="action_count"),
        sa.CheckConstraint(
            "(policy_present IS TRUE AND policy_id IS NOT NULL "
            "AND autonomy_level_snapshot BETWEEN 0 AND 5) OR "
            "(policy_present IS FALSE AND policy_id IS NULL "
            "AND autonomy_level_snapshot IS NULL)",
            name="policy_presence",
        ),
        sa.CheckConstraint(f"policy_input_digest ~ '{_HASH}'", name="policy_input_digest"),
        sa.CheckConstraint(f"request_digest ~ '{_HASH}'", name="request_digest"),
        sa.CheckConstraint(
            f"rollback_coverage_digest ~ '{_HASH}'", name="rollback_coverage_digest"
        ),
        sa.CheckConstraint(DECISION_SNAPSHOT_SQL, name="decision_snapshot"),
        sa.CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        sa.CheckConstraint(
            "emergency_rollback_authorization_id IS NULL "
            "OR emergency_control_binding_id IS NOT NULL",
            name="authorization_requires_binding",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["incident_id", "project_id", "tenant_id"],
            ["ops_incidents.id", "ops_incidents.project_id", "ops_incidents.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id", "project_id", "tenant_id"],
            [
                "autonomy_policies.id",
                "autonomy_policies.project_id",
                "autonomy_policies.tenant_id",
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
            ["emergency_control_binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["emergency_rollback_authorization_id", "project_id", "tenant_id"],
            [
                "emergency_rollback_authorizations.id",
                "emergency_rollback_authorizations.project_id",
                "emergency_rollback_authorizations.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_self_healing_runs_id_project_tenant"
        ),
        sa.UniqueConstraint(
            "id",
            "incident_id",
            "project_id",
            "tenant_id",
            name="uq_ops_self_healing_runs_id_incident_project_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "incident_id",
            "idempotency_key",
            name="uq_ops_self_healing_runs_idempotency",
        ),
    )
    op.create_index(
        "ix_ops_self_healing_runs_latest",
        "ops_self_healing_runs",
        ["tenant_id", "incident_id", "created_at"],
    )
    op.create_table(
        "ops_hotfix_plans",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("plan_kind", sa.Text(), nullable=False),
        sa.Column("intended_ref", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("plan_kind IN ('patch_branch','hotfix_pr')", name="plan_kind"),
        sa.CheckConstraint(
            "char_length(intended_ref) BETWEEN 1 AND 200 AND intended_ref = btrim(intended_ref)",
            name="intended_ref",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["run_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_self_healing_runs.id",
                "ops_self_healing_runs.incident_id",
                "ops_self_healing_runs.project_id",
                "ops_self_healing_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "run_id", "plan_kind", name="uq_ops_hotfix_plans_run_kind"
        ),
        sa.UniqueConstraint(
            "id",
            "run_id",
            "project_id",
            "tenant_id",
            "plan_kind",
            name="uq_ops_hotfix_plans_id_run_project_tenant_kind",
        ),
    )
    op.create_table(
        "ops_self_healing_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("matrix_action", sa.Text(), nullable=False),
        sa.Column("policy_decision", sa.Text(), nullable=False),
        sa.Column("execution_posture", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=True),
        sa.Column("plan_kind", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "policy_decision IN ('allow','deny','needs_approval')", name="policy_decision"
        ),
        sa.CheckConstraint(
            "execution_posture IN ("
            "'local_branch_plan_written','local_pr_plan_written',"
            "'recorded_not_executed','staging_not_executed','production_not_executed')",
            name="execution_posture",
        ),
        sa.CheckConstraint(
            "reason_code IN ("
            "'plan_written','plan_denied_by_policy','plan_needs_approval',"
            "'branch_plan_required','no_deploy_actuator','production_not_executed')",
            name="reason_code",
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in CHILD_CHECK_CONSTRAINTS],
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["run_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_self_healing_runs.id",
                "ops_self_healing_runs.incident_id",
                "ops_self_healing_runs.project_id",
                "ops_self_healing_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "run_id", "project_id", "tenant_id", "plan_kind"],
            [
                "ops_hotfix_plans.id",
                "ops_hotfix_plans.run_id",
                "ops_hotfix_plans.project_id",
                "ops_hotfix_plans.tenant_id",
                "ops_hotfix_plans.plan_kind",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_ops_self_healing_results_run_seq"),
        sa.UniqueConstraint("run_id", "action", name="uq_ops_self_healing_results_run_action"),
    )
    install_hotfix_guards()


def downgrade() -> None:
    op.execute(populated_downgrade_sql())
    drop_hotfix_guards()
    op.drop_table("ops_self_healing_results")
    op.drop_table("ops_hotfix_plans")
    op.drop_index("ix_ops_self_healing_runs_latest", table_name="ops_self_healing_runs")
    op.drop_table("ops_self_healing_runs")
    op.drop_constraint(
        "uq_era_id_project_tenant", "emergency_rollback_authorizations", type_="unique"
    )
