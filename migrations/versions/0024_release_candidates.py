"""release_candidates

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-15

Slice 25 — release-candidate / release-binding store (§24.1/§24.2/Appendix B #7). Adds tenant-owned
``release_candidates`` (RLS; SELECT/INSERT/UPDATE, no DELETE; status CHECK; guard trigger enforcing
INSERT invariants, identity immutability, same-status no-op, one-way lifecycle, frozen_at-iff-frozen)
+ append-only, freeze-locked ``release_candidate_issue_bindings`` (SELECT/INSERT only; trigger
rejecting INSERT unless the parent candidate is draft and the issue's project matches) + append-only
``release_candidate_events`` (SELECT/INSERT only). Additive — no change to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"

_IMMUTABLE = ("id", "tenant_id", "project_id", "release_ref", "title", "created_at")


def upgrade() -> None:
    op.create_table(
        "release_candidates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_ref", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('draft','frozen','superseded','canceled')",
            name=op.f("ck_release_candidates_status_valid"),
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
            name=op.f("fk_release_candidates_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_candidates")),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "release_ref", name="uq_release_candidates_ref"
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_release_candidates_id_tenant"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_release_candidates_id_proj_tenant"
        ),
    )
    op.create_index(
        "ix_release_candidates_tenant_project_status",
        "release_candidates",
        ["tenant_id", "project_id", "status"],
    )

    op.create_table(
        "release_candidate_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.tenant_id"],
            name="release_candidate_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_release_candidate_events_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_candidate_events")),
    )
    op.create_index(
        "ix_release_candidate_events_candidate",
        "release_candidate_events",
        ["tenant_id", "release_candidate_id", "created_at"],
    )

    op.create_table(
        "release_candidate_issue_bindings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("release_issue_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            name="release_candidate_proj_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_issue_id", "tenant_id"],
            ["release_issues.id", "release_issues.tenant_id"],
            name="release_issue_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_release_candidate_issue_bindings_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_candidate_issue_bindings")),
        sa.UniqueConstraint(
            "tenant_id",
            "release_candidate_id",
            "release_issue_id",
            name="uq_release_candidate_issue_binding",
        ),
    )
    op.create_index(
        "ix_release_candidate_issue_bindings_candidate",
        "release_candidate_issue_bindings",
        ["tenant_id", "release_candidate_id"],
    )

    immutable_checks = "\n            OR ".join(
        f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _IMMUTABLE
    )
    op.execute(
        f"""
        CREATE FUNCTION public.release_candidates_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'draft' THEN
                    RAISE EXCEPTION 'release_candidates must be created with status=draft';
                END IF;
                IF NEW.frozen_at IS NOT NULL THEN
                    RAISE EXCEPTION 'release_candidates: frozen_at must be NULL at creation';
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'release_candidates: identity fields are immutable';
                END IF;
                IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
                    -- status unchanged ⇒ no field may change (incl. frozen_at/updated_at).
                    IF NEW.frozen_at IS DISTINCT FROM OLD.frozen_at
                    OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
                        RAISE EXCEPTION 'release_candidates: fields change only via a status transition';
                    END IF;
                ELSE
                    IF NOT (
                        (OLD.status = 'draft' AND NEW.status IN ('frozen','canceled'))
                        OR (OLD.status = 'frozen' AND NEW.status IN ('superseded','canceled'))
                    ) THEN
                        RAISE EXCEPTION 'release_candidates: invalid transition % -> %',
                            OLD.status, NEW.status;
                    END IF;
                    IF NEW.status = 'frozen' THEN
                        IF OLD.frozen_at IS NOT NULL OR NEW.frozen_at IS NULL THEN
                            RAISE EXCEPTION 'release_candidates: entering frozen must set frozen_at';
                        END IF;
                    ELSE
                        IF NEW.frozen_at IS DISTINCT FROM OLD.frozen_at THEN
                            RAISE EXCEPTION 'release_candidates: frozen_at is set only when entering frozen';
                        END IF;
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_candidates_guard
            BEFORE INSERT OR UPDATE ON public.release_candidates
            FOR EACH ROW EXECUTE FUNCTION public.release_candidates_guard()
        """
    )

    op.execute(
        """
        CREATE FUNCTION public.release_candidate_bindings_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE parent_status text; issue_project uuid;
        BEGIN
            SELECT status INTO parent_status FROM public.release_candidates
                WHERE id = NEW.release_candidate_id AND tenant_id = NEW.tenant_id;
            IF parent_status IS DISTINCT FROM 'draft' THEN
                RAISE EXCEPTION 'release_candidate_issue_bindings: candidate must be draft to bind (got %)',
                    parent_status;
            END IF;
            SELECT project_id INTO issue_project FROM public.release_issues
                WHERE id = NEW.release_issue_id AND tenant_id = NEW.tenant_id;
            IF issue_project IS DISTINCT FROM NEW.project_id THEN
                RAISE EXCEPTION 'release_candidate_issue_bindings: issue project mismatch';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_candidate_bindings_guard
            BEFORE INSERT ON public.release_candidate_issue_bindings
            FOR EACH ROW EXECUTE FUNCTION public.release_candidate_bindings_guard()
        """
    )

    # block triggers: candidates (no DELETE/TRUNCATE), bindings + events (append-only).
    op.execute(
        """
        CREATE FUNCTION public.release_candidates_block_delete() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'release_candidates does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER release_candidates_no_delete BEFORE DELETE ON public.release_candidates "
        "FOR EACH ROW EXECUTE FUNCTION public.release_candidates_block_delete()"
    )
    op.execute(
        "CREATE TRIGGER release_candidates_no_truncate BEFORE TRUNCATE ON public.release_candidates "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.release_candidates_block_delete()"
    )

    op.execute(
        """
        CREATE FUNCTION public.release_candidate_append_only() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'append-only table: no UPDATE/DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    for tbl in ("release_candidate_events", "release_candidate_issue_bindings"):
        op.execute(
            f"CREATE TRIGGER {tbl}_no_update_delete BEFORE UPDATE OR DELETE ON public.{tbl} "
            f"FOR EACH ROW EXECUTE FUNCTION public.release_candidate_append_only()"
        )
        op.execute(
            f"CREATE TRIGGER {tbl}_no_truncate BEFORE TRUNCATE ON public.{tbl} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION public.release_candidate_append_only()"
        )

    for table in (
        "release_candidates",
        "release_candidate_events",
        "release_candidate_issue_bindings",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
    op.execute("REVOKE DELETE, TRUNCATE ON release_candidates FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON release_candidates TO uaid_app")
    for tbl in ("release_candidate_events", "release_candidate_issue_bindings"):
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {tbl} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {tbl} TO uaid_app")


def downgrade() -> None:
    for table in (
        "release_candidate_issue_bindings",
        "release_candidate_events",
        "release_candidates",
    ):
        op.execute(f"REVOKE ALL ON {table} FROM uaid_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for tbl in ("release_candidate_events", "release_candidate_issue_bindings"):
        op.execute(f"DROP TRIGGER IF EXISTS {tbl}_no_truncate ON public.{tbl}")
        op.execute(f"DROP TRIGGER IF EXISTS {tbl}_no_update_delete ON public.{tbl}")
    op.execute("DROP FUNCTION IF EXISTS public.release_candidate_append_only()")
    op.execute("DROP TRIGGER IF EXISTS release_candidates_no_truncate ON public.release_candidates")
    op.execute("DROP TRIGGER IF EXISTS release_candidates_no_delete ON public.release_candidates")
    op.execute("DROP FUNCTION IF EXISTS public.release_candidates_block_delete()")
    op.execute(
        "DROP TRIGGER IF EXISTS release_candidate_bindings_guard "
        "ON public.release_candidate_issue_bindings"
    )
    op.execute("DROP FUNCTION IF EXISTS public.release_candidate_bindings_guard()")
    op.execute("DROP TRIGGER IF EXISTS release_candidates_guard ON public.release_candidates")
    op.execute("DROP FUNCTION IF EXISTS public.release_candidates_guard()")
    op.drop_index(
        "ix_release_candidate_issue_bindings_candidate",
        table_name="release_candidate_issue_bindings",
    )
    op.drop_table("release_candidate_issue_bindings")
    op.drop_index("ix_release_candidate_events_candidate", table_name="release_candidate_events")
    op.drop_table("release_candidate_events")
    op.drop_index("ix_release_candidates_tenant_project_status", table_name="release_candidates")
    op.drop_table("release_candidates")
