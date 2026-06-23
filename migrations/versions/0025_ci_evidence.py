"""ci_evidence (branch_protection_snapshots)

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-23

Slice 26 — source-control / CI evidence-provenance foundation (Appendix B #3 / §26.3). Adds the
tenant-owned, **immutable append-only** ``branch_protection_snapshots`` (RLS; SELECT/INSERT only —
no UPDATE/DELETE; provider/provenance/count CHECKs; a ``repo_ref`` owner/repo-slug CHECK + a
GitHub-token-prefix denylist CHECK; a ``required_status_checks`` JSON-array CHECK; a BEFORE INSERT
guard enforcing provenance=caller_supplied_unverified [the ``connector_verified`` tier is
schema-reserved but unwritable this slice], the ``repo_ref`` shape + token denylist, the JSON-array
shape + per-element bounded-string rule, and ``required_status_check_count`` =
jsonb_array_length(required_status_checks); plus UPDATE/DELETE/TRUNCATE block triggers). Additive —
no change to existing tables. Mirrors the append-only snapshot pattern of ``0015_readiness_reports``
and the guard pattern of ``0022_release_findings``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_SLUG_RE = "^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$"
_TOKENISH_RE = "/(gh[opusr]_|github_pat_)"


def upgrade() -> None:
    op.create_table(
        "branch_protection_snapshots",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("repo_ref", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("protection_enabled", sa.Boolean(), nullable=False),
        sa.Column("required_pull_request_reviews", sa.Boolean(), nullable=False),
        sa.Column(
            "required_status_checks",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("required_status_check_count", sa.Integer(), nullable=False),
        sa.Column("enforce_admins", sa.Boolean(), nullable=False),
        sa.Column(
            "provenance",
            sa.Text(),
            server_default=sa.text("'caller_supplied_unverified'"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name=op.f("ck_bps_provenance_valid"),
        ),
        sa.CheckConstraint("provider IN ('github')", name=op.f("ck_bps_provider_valid")),
        sa.CheckConstraint(
            "required_status_check_count >= 0", name=op.f("ck_bps_check_count_nonneg")
        ),
        sa.CheckConstraint(f"repo_ref ~ '{_SLUG_RE}'", name=op.f("ck_bps_repo_ref_slug")),
        sa.CheckConstraint(
            f"repo_ref !~* '{_TOKENISH_RE}'", name=op.f("ck_bps_repo_ref_not_tokenish")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(required_status_checks) = 'array'", name=op.f("ck_bps_checks_array")
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
            name=op.f("fk_branch_protection_snapshots_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_branch_protection_snapshots")),
    )
    op.create_index(
        "ix_branch_protection_snapshots_tenant_project_created",
        "branch_protection_snapshots",
        ["tenant_id", "project_id", "created_at"],
    )

    # --- BEFORE INSERT guard (authoritative DB backstop; uaid_app holds INSERT) ----
    op.execute(
        f"""
        CREATE FUNCTION public.branch_protection_snapshots_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NEW.provenance <> 'caller_supplied_unverified' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: provenance must be caller_supplied_unverified (connector_verified is unwritable this slice)';
            END IF;
            IF NEW.repo_ref !~ '{_SLUG_RE}' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: repo_ref must be an owner/repo slug';
            END IF;
            IF NEW.repo_ref ~* '{_TOKENISH_RE}' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: repo_ref must not contain a token prefix';
            END IF;
            IF jsonb_typeof(NEW.required_status_checks) <> 'array' THEN
                RAISE EXCEPTION 'branch_protection_snapshots: required_status_checks must be a JSON array';
            END IF;
            IF EXISTS (
                SELECT 1 FROM jsonb_array_elements(NEW.required_status_checks) AS elem(val)
                WHERE jsonb_typeof(val) <> 'string'
                   OR char_length(val #>> '{{}}') < 1
                   OR char_length(val #>> '{{}}') > 200
            ) THEN
                RAISE EXCEPTION 'branch_protection_snapshots: required_status_checks elements must be 1..200-char strings';
            END IF;
            IF NEW.required_status_check_count <> jsonb_array_length(NEW.required_status_checks) THEN
                RAISE EXCEPTION 'branch_protection_snapshots: required_status_check_count must equal jsonb_array_length(required_status_checks)';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER branch_protection_snapshots_guard
            BEFORE INSERT ON public.branch_protection_snapshots
            FOR EACH ROW EXECUTE FUNCTION public.branch_protection_snapshots_guard()
        """
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE (mirror 0015) -------------------
    op.execute(
        """
        CREATE FUNCTION public.branch_protection_snapshots_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'branch_protection_snapshots is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER branch_protection_snapshots_no_update_delete
            BEFORE UPDATE OR DELETE ON public.branch_protection_snapshots
            FOR EACH ROW EXECUTE FUNCTION public.branch_protection_snapshots_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER branch_protection_snapshots_no_truncate
            BEFORE TRUNCATE ON public.branch_protection_snapshots
            FOR EACH STATEMENT EXECUTE FUNCTION public.branch_protection_snapshots_block_mutation()
        """
    )

    # --- RLS + grants (mirror 0015) -----------------------------------------------
    op.execute("ALTER TABLE branch_protection_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branch_protection_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON branch_protection_snapshots "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON branch_protection_snapshots FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON branch_protection_snapshots TO uaid_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON branch_protection_snapshots FROM uaid_app")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON branch_protection_snapshots")
    op.execute("ALTER TABLE branch_protection_snapshots NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branch_protection_snapshots DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP TRIGGER IF EXISTS branch_protection_snapshots_no_truncate "
        "ON public.branch_protection_snapshots"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS branch_protection_snapshots_no_update_delete "
        "ON public.branch_protection_snapshots"
    )
    op.execute("DROP FUNCTION IF EXISTS public.branch_protection_snapshots_block_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS branch_protection_snapshots_guard "
        "ON public.branch_protection_snapshots"
    )
    op.execute("DROP FUNCTION IF EXISTS public.branch_protection_snapshots_guard()")
    op.drop_index(
        "ix_branch_protection_snapshots_tenant_project_created",
        table_name="branch_protection_snapshots",
    )
    op.drop_table("branch_protection_snapshots")
