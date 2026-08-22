"""ops incidents, tickets, handover, and §25.2 action evaluations

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-22

Slice 57 — incident workflow ledger. Additive unique targets on
ops_signal_results and pm_issue_mappings. Does not change A5, readiness,
control_loop, or Slice-56 db_checks.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.ops.incident_db_checks import CHILD_CHECK_CONSTRAINTS
from app.ops.incident_ddl import (
    drop_incident_guards,
    install_incident_guards,
    populated_downgrade_sql,
)

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HASH = r"^sha256:[0-9a-f]{64}$"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ops_signal_results_id_project_tenant",
        "ops_signal_results",
        ["id", "project_id", "tenant_id"],
    )
    op.create_unique_constraint(
        "uq_pm_issue_mappings_id_project_tenant",
        "pm_issue_mappings",
        ["id", "project_id", "tenant_id"],
    )
    op.create_table(
        "ops_incidents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("source_provenance", sa.Text(), nullable=False),
        sa.Column("source_signal_id", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset_version='slice57.v1'", name="ruleset_version"),
        sa.CheckConstraint(
            "category IN ('availability','security','error','cost','data_quality','other')",
            name="category",
        ),
        sa.CheckConstraint("severity IN ('low','medium','high','critical')", name="severity"),
        sa.CheckConstraint(
            "status IN ('open','investigating','mitigated','resolved','superseded')",
            name="status",
        ),
        sa.CheckConstraint(
            "source_provenance='caller_supplied_unverified'", name="source_provenance"
        ),
        sa.CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 2000 AND summary = btrim(summary)",
            name="summary",
        ),
        sa.CheckConstraint(
            "detail IS NULL OR (char_length(detail) BETWEEN 1 AND 8000 AND detail = btrim(detail))",
            name="detail",
        ),
        sa.CheckConstraint("(category<>'other') OR (detail IS NOT NULL)", name="other_detail"),
        sa.CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        sa.CheckConstraint(f"request_digest ~ '{_HASH}'", name="request_digest"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_signal_id", "project_id", "tenant_id"],
            [
                "ops_signal_results.id",
                "ops_signal_results.project_id",
                "ops_signal_results.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_incidents_id_project_tenant"
        ),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_ops_incidents_idempotency"
        ),
    )
    op.create_index(
        "ix_ops_incidents_latest", "ops_incidents", ["tenant_id", "project_id", "created_at"]
    )
    op.create_table(
        "ops_incident_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(event_type) BETWEEN 1 AND 64 AND event_type = btrim(event_type)",
            name="event_type",
        ),
        sa.CheckConstraint(
            "char_length(actor) BETWEEN 1 AND 200 AND actor = btrim(actor)", name="actor"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["incident_id", "project_id", "tenant_id"],
            ["ops_incidents.id", "ops_incidents.project_id", "ops_incidents.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ops_incident_tickets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("ticket_kind", sa.Text(), nullable=False),
        sa.Column("delivery", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("pm_issue_mapping_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ticket_kind='bug'", name="ticket_kind"),
        sa.CheckConstraint("delivery='local_record'", name="delivery"),
        sa.CheckConstraint("status='open'", name="status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["incident_id", "project_id", "tenant_id"],
            ["ops_incidents.id", "ops_incidents.project_id", "ops_incidents.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pm_issue_mapping_id", "project_id", "tenant_id"],
            [
                "pm_issue_mappings.id",
                "pm_issue_mappings.project_id",
                "pm_issue_mappings.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "incident_id", name="uq_ops_incident_tickets_incident"),
        sa.UniqueConstraint(
            "id",
            "incident_id",
            "project_id",
            "tenant_id",
            name="uq_ops_incident_tickets_id_incident_project_tenant",
        ),
    )
    op.create_table(
        "ops_support_handovers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("handed_over_by", sa.Text(), nullable=False),
        sa.Column("received_by", sa.Text(), nullable=False),
        sa.Column("recorded_by_provenance", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('recorded_complete','recorded_incomplete')", name="status"),
        sa.CheckConstraint(
            "recorded_by_provenance IN ('caller_supplied_unverified','request_authenticated')",
            name="recorded_by_provenance",
        ),
        sa.CheckConstraint(
            "char_length(handed_over_by) BETWEEN 1 AND 200 "
            "AND handed_over_by = btrim(handed_over_by)",
            name="handed_over_by",
        ),
        sa.CheckConstraint(
            "char_length(received_by) BETWEEN 1 AND 200 AND received_by = btrim(received_by)",
            name="received_by",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ops_support_handovers_latest",
        "ops_support_handovers",
        ["tenant_id", "project_id", "created_at"],
    )
    eval_cols = [
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset_version='slice57.v1'", name="ruleset_version"),
        sa.CheckConstraint("action_count=7", name="action_count"),
        sa.CheckConstraint(f"policy_input_digest ~ '{_HASH}'", name="policy_input_digest"),
        sa.CheckConstraint(
            "(policy_present IS TRUE AND policy_id IS NOT NULL "
            "AND autonomy_level_snapshot BETWEEN 0 AND 5) OR "
            "(policy_present IS FALSE AND policy_id IS NULL "
            "AND autonomy_level_snapshot IS NULL)",
            name="policy_presence",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "incident_id",
            "project_id",
            "tenant_id",
            name="uq_ops_incident_action_evaluations_id_incident_project_tenant",
        ),
    ]
    op.create_table("ops_incident_action_evaluations", *eval_cols)
    op.create_index(
        "ix_ops_incident_action_evaluations_latest",
        "ops_incident_action_evaluations",
        ["tenant_id", "incident_id", "created_at"],
    )
    result_checks = [sa.CheckConstraint(sql, name=name) for name, sql in CHILD_CHECK_CONSTRAINTS]
    op.create_table(
        "ops_incident_action_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("matrix_action", sa.Text(), nullable=False),
        sa.Column("policy_decision", sa.Text(), nullable=False),
        sa.Column("execution_posture", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "policy_decision IN ('allow','deny','needs_approval','not_evaluated')",
            name="policy_decision",
        ),
        sa.CheckConstraint(
            "execution_posture IN ('local_ticket_written','recorded_not_executed')",
            name="execution_posture",
        ),
        sa.CheckConstraint(
            "reason_code IN ('ticket_written','ticket_denied_by_policy',"
            "'no_log_source','deferred_slice58','production_not_executed')",
            name="reason_code",
        ),
        *result_checks,
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_incident_action_evaluations.id",
                "ops_incident_action_evaluations.incident_id",
                "ops_incident_action_evaluations.project_id",
                "ops_incident_action_evaluations.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_incident_tickets.id",
                "ops_incident_tickets.incident_id",
                "ops_incident_tickets.project_id",
                "ops_incident_tickets.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_id", "seq", name="uq_ops_incident_action_results_eval_seq"),
        sa.UniqueConstraint(
            "evaluation_id", "action", name="uq_ops_incident_action_results_eval_action"
        ),
    )
    install_incident_guards()


def downgrade() -> None:
    op.execute(populated_downgrade_sql())
    drop_incident_guards()
    op.drop_table("ops_incident_action_results")
    op.drop_table("ops_incident_action_evaluations")
    op.drop_table("ops_support_handovers")
    op.drop_table("ops_incident_tickets")
    op.drop_table("ops_incident_events")
    op.drop_table("ops_incidents")
    op.drop_constraint(
        "uq_pm_issue_mappings_id_project_tenant", "pm_issue_mappings", type_="unique"
    )
    op.drop_constraint(
        "uq_ops_signal_results_id_project_tenant", "ops_signal_results", type_="unique"
    )
