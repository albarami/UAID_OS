"""readiness_reports

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-04

Slice 12 — build-readiness auditor (§4.5). Tenant-owned, append-only
``readiness_reports`` (immutable snapshots): ENABLE+FORCE RLS + ``tenant_isolation``;
SELECT/INSERT only for ``uaid_app``; UPDATE/DELETE/TRUNCATE blocked by triggers.
``readiness_level`` CHECK allows R0..R5 for forward compatibility (Slice-12 code emits
only R0/R1/R2). No change to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "readiness_reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("readiness_level", sa.Text(), nullable=False),
        sa.Column("can_build_to_staging", sa.Boolean(), nullable=False),
        sa.Column("can_go_live_autonomously", sa.Boolean(), nullable=False),
        sa.Column("report", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("evaluated_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.CheckConstraint(
            "readiness_level IN ('R0','R1','R2','R3','R4','R5')",
            name=op.f("ck_readiness_reports_readiness_level_valid"),
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
            name=op.f("fk_readiness_reports_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_readiness_reports")),
    )
    op.create_index(
        "ix_readiness_reports_tenant_project_created",
        "readiness_reports",
        ["tenant_id", "project_id", "created_at"],
        unique=False,
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE --------------------------------
    op.execute(
        """
        CREATE FUNCTION public.readiness_reports_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'readiness_reports is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER readiness_reports_no_update_delete
            BEFORE UPDATE OR DELETE ON public.readiness_reports
            FOR EACH ROW EXECUTE FUNCTION public.readiness_reports_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER readiness_reports_no_truncate
            BEFORE TRUNCATE ON public.readiness_reports
            FOR EACH STATEMENT EXECUTE FUNCTION public.readiness_reports_block_mutation()
        """
    )

    # --- RLS (mirrors 0014) -------------------------------------------------------
    op.execute("ALTER TABLE readiness_reports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE readiness_reports FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON readiness_reports "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )

    # --- privileges: append-only for the runtime role -----------------------------
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON readiness_reports FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON readiness_reports TO uaid_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT ON readiness_reports FROM uaid_app")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON readiness_reports")
    op.execute("ALTER TABLE readiness_reports NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE readiness_reports DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TRIGGER IF EXISTS readiness_reports_no_truncate ON public.readiness_reports")
    op.execute(
        "DROP TRIGGER IF EXISTS readiness_reports_no_update_delete ON public.readiness_reports"
    )
    op.execute("DROP FUNCTION IF EXISTS public.readiness_reports_block_mutation()")
    op.drop_index("ix_readiness_reports_tenant_project_created", table_name="readiness_reports")
    op.drop_table("readiness_reports")
