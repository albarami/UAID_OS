"""extraction_promotions

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-05

Slice 14b — promotion link from an approved extraction_proposal to the spine artifact it
became. Adds the additive UNIQUE(id, project_id, tenant_id) to extraction_proposals (a
composite-FK target) and a tenant-owned, append-only extraction_promotions table:
UNIQUE(tenant_id, extraction_proposal_id) (promote-once), composite FKs pinning both the
proposal and the artifact to the same tenant/project, ENABLE+FORCE RLS + tenant_isolation,
SELECT/INSERT only + UPDATE/DELETE/TRUNCATE block triggers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    # additive composite-FK target on extraction_proposals
    op.create_unique_constraint(
        "uq_extraction_proposals_id_project_tenant",
        "extraction_proposals",
        ["id", "project_id", "tenant_id"],
    )

    op.create_table(
        "extraction_promotions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("extraction_proposal_id", sa.UUID(), nullable=False),
        sa.Column("artifact_id", sa.UUID(), nullable=False),
        sa.Column("promoted_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_proposal_id", "project_id", "tenant_id"],
            ["extraction_proposals.id", "extraction_proposals.project_id",
             "extraction_proposals.tenant_id"],
            name="proposal_project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            name="artifact_project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_extraction_promotions_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_promotions")),
        sa.UniqueConstraint(
            "tenant_id", "extraction_proposal_id", name="uq_extraction_promotions_proposal"
        ),
    )
    op.create_index(
        "ix_extraction_promotions_tenant_project", "extraction_promotions",
        ["tenant_id", "project_id"],
    )

    # append-only
    op.execute(
        """
        CREATE FUNCTION public.extraction_promotions_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'extraction_promotions is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_promotions_no_update_delete
            BEFORE UPDATE OR DELETE ON public.extraction_promotions
            FOR EACH ROW EXECUTE FUNCTION public.extraction_promotions_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_promotions_no_truncate
            BEFORE TRUNCATE ON public.extraction_promotions
            FOR EACH STATEMENT EXECUTE FUNCTION public.extraction_promotions_block_mutation()
        """
    )

    # RLS + grants
    op.execute("ALTER TABLE extraction_promotions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE extraction_promotions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON extraction_promotions "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON extraction_promotions FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON extraction_promotions TO uaid_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON extraction_promotions")
    op.execute("ALTER TABLE extraction_promotions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE extraction_promotions DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT ON extraction_promotions FROM uaid_app")
    op.execute(
        "DROP TRIGGER IF EXISTS extraction_promotions_no_truncate ON public.extraction_promotions"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS extraction_promotions_no_update_delete "
        "ON public.extraction_promotions"
    )
    op.execute("DROP FUNCTION IF EXISTS public.extraction_promotions_block_mutation()")
    op.drop_index("ix_extraction_promotions_tenant_project", table_name="extraction_promotions")
    op.drop_table("extraction_promotions")
    op.drop_constraint(
        "uq_extraction_proposals_id_project_tenant", "extraction_proposals", type_="unique"
    )
