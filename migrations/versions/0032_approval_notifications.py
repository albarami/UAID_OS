"""approval_notifications (communication / approval channel)

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-25

Slice 33 — communication / approval channel (§18.2 / §26.3). (1) Adds the **additive**
``UNIQUE(id, project_id, tenant_id)`` to the existing ``approvals`` table (the Slice-6/14b composite-FK-
target pattern — constraint only; no column/data change; ``approvals`` logic untouched). (2) Adds the
tenant-owned, **immutable append-only** ``approval_notifications`` (RLS; SELECT/INSERT only — no
UPDATE/DELETE/TRUNCATE; risk_tier/routing_mode/channel/status enum CHECKs; the composite FK
``(approval_id, project_id, tenant_id) → approvals(id, project_id, tenant_id)`` DB-proving project/tenant
consistency). Records **only** routing facts — **no recipient/URL/credential column** (no secret material).
All validation is column CHECKs (no guard trigger). Mirrors the append-only pattern of ``0030``/``0031``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLE = "approval_notifications"
_APPROVALS_UQ = "uq_approvals_id_project_tenant"


def upgrade() -> None:
    # (1) Additive composite-FK target on the existing approvals table.
    op.create_unique_constraint(_APPROVALS_UQ, "approvals", ["id", "project_id", "tenant_id"])

    # (2) The append-only notification log.
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("approval_id", sa.UUID(), nullable=False),
        sa.Column("risk_tier", sa.Text(), nullable=False),
        sa.Column("routing_mode", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "risk_tier IN ('low','medium','high','production')", name=op.f("ck_an_risk_tier_valid")
        ),
        sa.CheckConstraint(
            "routing_mode IN ('digest','realtime')", name=op.f("ck_an_routing_mode_valid")
        ),
        sa.CheckConstraint("channel IN ('dashboard')", name=op.f("ck_an_channel_valid")),
        sa.CheckConstraint(
            "status IN ('delivered','failed','skipped')", name=op.f("ck_an_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["approval_id", "project_id", "tenant_id"],
            ["approvals.id", "approvals.project_id", "approvals.tenant_id"],
            name="approval_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_approval_notifications_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_notifications")),
    )
    op.create_index(
        "ix_an_tenant_project_approval_created",
        _TABLE,
        ["tenant_id", "project_id", "approval_id", "created_at"],
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE (mirror 0030/0031) -------------
    op.execute(
        """
        CREATE FUNCTION public.approval_notifications_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'approval_notifications is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER approval_notifications_no_update_delete
            BEFORE UPDATE OR DELETE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION public.approval_notifications_block_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER approval_notifications_no_truncate
            BEFORE TRUNCATE ON public.{_TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION public.approval_notifications_block_mutation()
        """
    )

    # --- RLS + grants (mirror 0030/0031) ------------------------------------------
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {_TABLE} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {_TABLE} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO uaid_app")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON {_TABLE} FROM uaid_app")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP TRIGGER IF EXISTS approval_notifications_no_truncate ON public.{_TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS approval_notifications_no_update_delete ON public.{_TABLE}")
    op.execute("DROP FUNCTION IF EXISTS public.approval_notifications_block_mutation()")
    op.drop_index("ix_an_tenant_project_approval_created", table_name=_TABLE)
    op.drop_table(_TABLE)
    op.drop_constraint(_APPROVALS_UQ, "approvals", type_="unique")
