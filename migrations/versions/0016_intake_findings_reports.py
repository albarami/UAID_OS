"""intake_findings_reports

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-04

Slice 13 — gap & structural contradiction detector. Tenant-owned, append-only
``intake_findings_reports`` (immutable snapshots): ENABLE+FORCE RLS + ``tenant_isolation``;
SELECT/INSERT only for ``uaid_app``; UPDATE/DELETE/TRUNCATE blocked by triggers;
non-negative count CHECKs; ``created_at`` defaults to ``clock_timestamp()``. No change to
existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "intake_findings_reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("report", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("evaluated_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.CheckConstraint(
            "gap_count >= 0", name=op.f("ck_intake_findings_reports_gap_count_non_negative")
        ),
        sa.CheckConstraint(
            "contradiction_count >= 0",
            name=op.f("ck_intake_findings_reports_contradiction_count_non_negative"),
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
            name=op.f("fk_intake_findings_reports_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intake_findings_reports")),
    )
    op.create_index(
        "ix_intake_findings_reports_tenant_project_created",
        "intake_findings_reports",
        ["tenant_id", "project_id", "created_at"],
        unique=False,
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE --------------------------------
    op.execute(
        """
        CREATE FUNCTION public.intake_findings_reports_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'intake_findings_reports is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER intake_findings_reports_no_update_delete
            BEFORE UPDATE OR DELETE ON public.intake_findings_reports
            FOR EACH ROW EXECUTE FUNCTION public.intake_findings_reports_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER intake_findings_reports_no_truncate
            BEFORE TRUNCATE ON public.intake_findings_reports
            FOR EACH STATEMENT EXECUTE FUNCTION public.intake_findings_reports_block_mutation()
        """
    )

    # --- RLS (mirrors 0015) -------------------------------------------------------
    op.execute("ALTER TABLE intake_findings_reports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE intake_findings_reports FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON intake_findings_reports "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )

    # --- privileges: append-only for the runtime role -----------------------------
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON intake_findings_reports FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON intake_findings_reports TO uaid_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT ON intake_findings_reports FROM uaid_app")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON intake_findings_reports")
    op.execute("ALTER TABLE intake_findings_reports NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE intake_findings_reports DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP TRIGGER IF EXISTS intake_findings_reports_no_truncate "
        "ON public.intake_findings_reports"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS intake_findings_reports_no_update_delete "
        "ON public.intake_findings_reports"
    )
    op.execute("DROP FUNCTION IF EXISTS public.intake_findings_reports_block_mutation()")
    op.drop_index(
        "ix_intake_findings_reports_tenant_project_created",
        table_name="intake_findings_reports",
    )
    op.drop_table("intake_findings_reports")
