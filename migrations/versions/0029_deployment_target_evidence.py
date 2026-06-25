"""deployment_target_evidence (deployment_target_snapshots)

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-24

Slice 30 — production deployment-target verification (App. B #2 / §5.2 / §26.3). Adds the tenant-owned,
**immutable append-only** ``deployment_target_snapshots`` (RLS; SELECT/INSERT only — no
UPDATE/DELETE/TRUNCATE; provider/environment/provenance enums; a strict FQDN ``target_ref`` CHECK +
length CHECK; an ``observed_http_status`` 100..599-or-NULL CHECK; and the **invariant CHECK**
``target_available = (provisioned AND reachable)`` [B-30-6]; plus UPDATE/DELETE/TRUNCATE block triggers).
All validation is expressible as column CHECKs, so there is no BEFORE INSERT guard trigger (unlike
``0028``). **Additive — no change to existing tables.** Mirrors the append-only snapshot pattern of
``0025``/``0028``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_FQDN_RE = r"^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?[.])+[A-Za-z]{2,63}$"
_TABLE = "deployment_target_snapshots"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("target_ref", sa.Text(), nullable=False),
        sa.Column("reachable", sa.Boolean(), nullable=False),
        sa.Column("provisioned", sa.Boolean(), nullable=False),
        sa.Column("target_available", sa.Boolean(), nullable=False),
        sa.Column("observed_http_status", sa.SmallInteger(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provenance",
            sa.Text(),
            server_default=sa.text("'caller_supplied_unverified'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name=op.f("ck_dts_provenance_valid"),
        ),
        sa.CheckConstraint("provider IN ('generic_https')", name=op.f("ck_dts_provider_valid")),
        sa.CheckConstraint(
            "environment IN ('production','staging')", name=op.f("ck_dts_environment_valid")
        ),
        sa.CheckConstraint(f"target_ref ~ '{_FQDN_RE}'", name=op.f("ck_dts_target_ref_fqdn")),
        sa.CheckConstraint(
            "char_length(target_ref) BETWEEN 1 AND 253", name=op.f("ck_dts_target_ref_len")
        ),
        sa.CheckConstraint(
            "target_ref !~* '(gh[opusr]_|github_pat_)'",
            name=op.f("ck_dts_target_ref_not_tokenish"),
        ),
        sa.CheckConstraint(
            "observed_http_status IS NULL OR (observed_http_status BETWEEN 100 AND 599)",
            name=op.f("ck_dts_http_status_range"),
        ),
        sa.CheckConstraint(
            "target_available = (provisioned AND reachable)",
            name=op.f("ck_dts_available_invariant"),
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
            name=op.f("fk_deployment_target_snapshots_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deployment_target_snapshots")),
    )
    op.create_index(
        "ix_dts_tenant_project_target_created",
        _TABLE,
        ["tenant_id", "project_id", "provider", "target_ref", "created_at"],
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE (mirror 0025/0028) --------------
    op.execute(
        """
        CREATE FUNCTION public.deployment_target_snapshots_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'deployment_target_snapshots is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER deployment_target_snapshots_no_update_delete
            BEFORE UPDATE OR DELETE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION public.deployment_target_snapshots_block_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER deployment_target_snapshots_no_truncate
            BEFORE TRUNCATE ON public.{_TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION public.deployment_target_snapshots_block_mutation()
        """
    )

    # --- RLS + grants (mirror 0025/0028) ------------------------------------------
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
    op.execute(f"DROP TRIGGER IF EXISTS deployment_target_snapshots_no_truncate ON public.{_TABLE}")
    op.execute(
        f"DROP TRIGGER IF EXISTS deployment_target_snapshots_no_update_delete ON public.{_TABLE}"
    )
    op.execute("DROP FUNCTION IF EXISTS public.deployment_target_snapshots_block_mutation()")
    op.drop_index("ix_dts_tenant_project_target_created", table_name=_TABLE)
    op.drop_table(_TABLE)
