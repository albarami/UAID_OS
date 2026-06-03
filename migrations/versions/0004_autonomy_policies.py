"""autonomy policies (autonomy level + tighten-only overrides)

Slice 3 (§5, §2.6). Tenant-owned `autonomy_policies` with the same RLS discipline
as `projects`/`project_runs`: ENABLE + FORCE row-level security, deny-by-default
`tenant_isolation` policy keyed on the `app.current_tenant` GUC. The runtime role
`uaid_app` is granted SELECT, INSERT, UPDATE — **NO DELETE** (policy deletion is a
governance-bypass risk; out of scope for this slice). Admin-run only.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-03

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "autonomy_policies",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("autonomy_level", sa.SmallInteger(), nullable=False),
        sa.Column(
            "overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "autonomy_level BETWEEN 0 AND 5",
            name=op.f("ck_autonomy_policies_autonomy_level_valid"),
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
            name=op.f("fk_autonomy_policies_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_autonomy_policies")),
        sa.UniqueConstraint(
            "tenant_id", "project_id", name=op.f("uq_autonomy_policies_tenant_id_project_id")
        ),
    )
    op.create_index(
        op.f("ix_autonomy_policies_tenant_id"), "autonomy_policies", ["tenant_id"], unique=False
    )

    # Row-level security (deny-by-default; mirrors 0002).
    op.execute("ALTER TABLE autonomy_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE autonomy_policies FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON autonomy_policies "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    # Minimal grants: NO DELETE (policy deletion = governance-bypass risk).
    op.execute("GRANT SELECT, INSERT, UPDATE ON autonomy_policies TO uaid_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE ON autonomy_policies FROM uaid_app")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON autonomy_policies")
    op.execute("ALTER TABLE autonomy_policies NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE autonomy_policies DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f("ix_autonomy_policies_tenant_id"), table_name="autonomy_policies")
    op.drop_table("autonomy_policies")
