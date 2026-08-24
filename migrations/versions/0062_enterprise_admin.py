"""enterprise administration

Revision ID: 0062
Revises: 0061
Create Date: 2026-08-24

Slice 63 — org/tenant admin, DB-enforced RBAC, role-gated policy lock.
Additive tables plus one privilege narrowing on autonomy_policies.
Does not alter A5, readiness, go-live, or any frozen module.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.admin.db_checks import (
    ACTION_CHECK_CONSTRAINTS,
    CHANGE_CHECK_CONSTRAINTS,
    EVENT_CHECK_CONSTRAINTS,
    GRANT_CHECK_CONSTRAINTS,
    ORG_STATUS_CHECK,
)
from app.admin.ddl import (
    assert_policy_admin_writer_exists,
    drop_admin_guards,
    install_admin_guards,
    install_resolver_0062,
    populated_downgrade_sql,
    restore_resolver_0026,
)

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_APPEND = "public.audit_append(text, text, text, jsonb)"


def upgrade() -> None:
    assert_policy_admin_writer_exists()
    op.add_column(
        "organizations",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.create_check_constraint(
        op.f(ORG_STATUS_CHECK[0]), "organizations", ORG_STATUS_CHECK[1]
    )
    install_resolver_0062()
    op.execute(f"GRANT EXECUTE ON FUNCTION {_AUDIT_APPEND} TO CURRENT_USER")
    op.create_table(
        "admin_role_grants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("principal_subject", sa.Text(), nullable=False),
        sa.Column("admin_role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("granted_by", sa.Text(), nullable=False),
        sa.Column("granted_by_provenance", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("tenant_id", "principal_subject", "admin_role"),
        sa.UniqueConstraint("id", "tenant_id"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "principal_subject",
            "admin_role",
            name=op.f("uq_admin_role_grants_identity"),
        ),
        *[
            sa.CheckConstraint(sql, name=op.f(name))
            for name, sql in GRANT_CHECK_CONSTRAINTS
        ],
    )
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("action_kind", sa.Text(), nullable=False),
        sa.Column("actor_principal", sa.Text(), nullable=False),
        sa.Column("actor_provenance", sa.Text(), nullable=False),
        sa.Column("required_role", sa.Text(), nullable=False),
        sa.Column("actor_role", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
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
        ),
        sa.UniqueConstraint("id", "project_id", "tenant_id"),
        *[
            sa.CheckConstraint(sql, name=op.f(name))
            for name, sql in ACTION_CHECK_CONSTRAINTS
        ],
    )
    op.create_table(
        "admin_policy_changes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("admin_action_id", sa.UUID(), nullable=False),
        sa.Column("autonomy_policy_id", sa.UUID(), nullable=False),
        sa.Column("previous_autonomy_level", sa.SmallInteger(), nullable=True),
        sa.Column("new_autonomy_level", sa.SmallInteger(), nullable=False),
        sa.Column("override_key_count", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["admin_action_id", "project_id", "tenant_id"],
            ["admin_actions.id", "admin_actions.project_id", "admin_actions.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            [
                "autonomy_policies.id",
                "autonomy_policies.project_id",
                "autonomy_policies.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "admin_action_id", name=op.f("uq_admin_policy_changes_action")
        ),
        *[
            sa.CheckConstraint(sql, name=op.f(name))
            for name, sql in CHANGE_CHECK_CONSTRAINTS
        ],
    )
    op.create_table(
        "tenant_admin_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("event_kind", sa.Text(), nullable=False),
        sa.Column("subject_principal", sa.Text(), nullable=True),
        sa.Column("admin_role", sa.Text(), nullable=True),
        sa.Column("admin_role_grant_id", sa.UUID(), nullable=True),
        sa.Column("performed_by", sa.Text(), nullable=False),
        sa.Column("performed_by_provenance", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["admin_role_grant_id", "tenant_id", "subject_principal", "admin_role"],
            [
                "admin_role_grants.id",
                "admin_role_grants.tenant_id",
                "admin_role_grants.principal_subject",
                "admin_role_grants.admin_role",
            ],
            name=op.f("fk_tae_grant_identity"),
            ondelete="RESTRICT",
        ),
        *[
            sa.CheckConstraint(sql, name=op.f(name))
            for name, sql in EVENT_CHECK_CONSTRAINTS
        ],
    )
    install_admin_guards()


def downgrade() -> None:
    op.execute(populated_downgrade_sql())
    restore_resolver_0026()
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_AUDIT_APPEND} FROM CURRENT_USER")
    drop_admin_guards()
    op.drop_table("admin_policy_changes")
    op.drop_table("tenant_admin_events")
    op.drop_table("admin_actions")
    op.drop_table("admin_role_grants")
    op.drop_constraint(op.f(ORG_STATUS_CHECK[0]), "organizations", type_="check")
    op.drop_column("organizations", "status")
