"""secret_reference_checks (secrets-reference verifier)

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-25

Slice 32 — secrets-reference verifier (R5 App. A l.2968 / §26.3 / spec:1094). Adds the tenant-owned,
**immutable append-only** ``secret_reference_checks`` (RLS; SELECT/INSERT only — no UPDATE/DELETE/TRUNCATE;
manager/reference-name bounded-shape CHECKs; outcome/provenance enums; the honesty invariant
``resolved = (outcome = 'resolved')``; and the B1 rule ``manager = 'env' OR (outcome =
'unsupported_manager' AND resolved = false)`` so a non-``env`` manager is recorded honestly). Records
**only** ``(manager, reference_name, outcome, resolved)`` — **NO value column exists** (structural zero-
secret-value guarantee). All validation is expressible as column CHECKs (no guard trigger). **Additive — no
change to existing tables.** Mirrors the append-only snapshot pattern of ``0029``/``0030``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLE = "secret_reference_checks"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("manager", sa.Text(), nullable=False),
        sa.Column("reference_name", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("ck_src_provenance_valid"),
        ),
        sa.CheckConstraint("manager ~ '^[a-z0-9_.:-]{1,64}$'", name=op.f("ck_src_manager_shape")),
        # Shape via char-class + separate length bound: Postgres regex {m,n} caps n at 255
        # (RE_DUP_MAX), so a {1,256} bound is invalid — the length CHECK carries the 256 bound.
        sa.CheckConstraint(
            "reference_name ~ '^[A-Za-z0-9_./:-]+$'", name=op.f("ck_src_reference_name_shape")
        ),
        sa.CheckConstraint(
            "char_length(reference_name) BETWEEN 1 AND 256", name=op.f("ck_src_reference_name_len")
        ),
        sa.CheckConstraint(
            "outcome IN ('resolved','not_found','unsupported_manager','probe_error')",
            name=op.f("ck_src_outcome_valid"),
        ),
        sa.CheckConstraint(
            "resolved = (outcome = 'resolved')", name=op.f("ck_src_resolved_invariant")
        ),
        sa.CheckConstraint(
            "manager = 'env' OR (outcome = 'unsupported_manager' AND resolved = false)",
            name=op.f("ck_src_unsupported_manager_rule"),
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
            name=op.f("fk_secret_reference_checks_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_secret_reference_checks")),
    )
    op.create_index(
        "ix_src_tenant_project_ref_created",
        _TABLE,
        ["tenant_id", "project_id", "manager", "reference_name", "created_at"],
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE (mirror 0029/0030) -------------
    op.execute(
        """
        CREATE FUNCTION public.secret_reference_checks_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'secret_reference_checks is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER secret_reference_checks_no_update_delete
            BEFORE UPDATE OR DELETE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION public.secret_reference_checks_block_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER secret_reference_checks_no_truncate
            BEFORE TRUNCATE ON public.{_TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION public.secret_reference_checks_block_mutation()
        """
    )

    # --- RLS + grants (mirror 0029/0030) ------------------------------------------
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
    op.execute(f"DROP TRIGGER IF EXISTS secret_reference_checks_no_truncate ON public.{_TABLE}")
    op.execute(
        f"DROP TRIGGER IF EXISTS secret_reference_checks_no_update_delete ON public.{_TABLE}"
    )
    op.execute("DROP FUNCTION IF EXISTS public.secret_reference_checks_block_mutation()")
    op.drop_index("ix_src_tenant_project_ref_created", table_name=_TABLE)
    op.drop_table(_TABLE)
