"""extraction

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-04

Slice 14a — LLM-assisted extractor. Two tenant-owned tables:
  * extraction_runs — immutable final-outcome rows (append-only: SELECT/INSERT only;
    UPDATE/DELETE/TRUNCATE blocked); document_id pinned to an ACCEPTED doc.
  * extraction_proposals — inert AI proposals; SELECT/INSERT/UPDATE (no DELETE);
    content-immutable + one-way pending->approved|rejected lifecycle, and a review
    requires a reviewed_by distinct from extracted_by (§2.2). source_document_id pinned
    to an ACCEPTED doc.
Both ENABLE+FORCE RLS + tenant_isolation. No change to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_KINDS = ("requirement", "acceptance_criterion", "test_oracle", "assumption")
_CLS = ("safe_assumption", "needs_approval", "unsafe_assumption_blocked", "unknown_cannot_proceed")
_RUN_STATUSES = ("succeeded", "failed", "blocked_by_budget", "refused_injection")
_PROP_STATUSES = ("pending", "approved", "rejected")
_CLS_CHECK = (
    f"(proposed_kind = 'assumption' AND proposed_classification IS NOT NULL "
    f"AND proposed_classification IN ({', '.join(repr(c) for c in _CLS)})) "
    "OR (proposed_kind <> 'assumption' AND proposed_classification IS NULL)"
)


def upgrade() -> None:
    # --- extraction_runs ----------------------------------------------------------
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("cost_external_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _RUN_STATUSES)})",
            name=op.f("ck_extraction_runs_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            name="document_project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_extraction_runs_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_runs")),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_extraction_runs_id_project_tenant"
        ),
    )
    op.create_index(
        "ix_extraction_runs_tenant_project", "extraction_runs", ["tenant_id", "project_id"]
    )

    # --- extraction_proposals -----------------------------------------------------
    op.create_table(
        "extraction_proposals",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("extraction_run_id", sa.UUID(), nullable=False),
        sa.Column("proposed_kind", sa.Text(), nullable=False),
        sa.Column("proposed_text", sa.Text(), nullable=False),
        sa.Column("proposed_classification", sa.Text(), nullable=True),
        sa.Column("source_document_id", sa.UUID(), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("extracted_by", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"proposed_kind IN ({', '.join(repr(k) for k in _KINDS)})",
            name=op.f("ck_extraction_proposals_proposed_kind_valid"),
        ),
        sa.CheckConstraint(_CLS_CHECK, name=op.f("ck_extraction_proposals_proposed_classification_valid")),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _PROP_STATUSES)})",
            name=op.f("ck_extraction_proposals_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id", "project_id", "tenant_id"],
            ["extraction_runs.id", "extraction_runs.project_id", "extraction_runs.tenant_id"],
            name="run_project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            name="document_project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_extraction_proposals_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_proposals")),
    )
    op.create_index(
        "ix_extraction_proposals_tenant_run", "extraction_proposals",
        ["tenant_id", "extraction_run_id"],
    )

    # --- extraction_runs: accepted-source-doc + append-only -----------------------
    op.execute(
        """
        CREATE FUNCTION public.extraction_runs_require_accepted_doc() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE st text;
        BEGIN
            SELECT status INTO st FROM public.documents WHERE id = NEW.document_id;
            IF st IS DISTINCT FROM 'accepted' THEN
                RAISE EXCEPTION 'extraction source document % is not accepted (status=%)',
                    NEW.document_id, st;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_runs_accepted_doc
            BEFORE INSERT ON public.extraction_runs
            FOR EACH ROW EXECUTE FUNCTION public.extraction_runs_require_accepted_doc()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.extraction_runs_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'extraction_runs is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_runs_no_update_delete
            BEFORE UPDATE OR DELETE ON public.extraction_runs
            FOR EACH ROW EXECUTE FUNCTION public.extraction_runs_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_runs_no_truncate
            BEFORE TRUNCATE ON public.extraction_runs
            FOR EACH STATEMENT EXECUTE FUNCTION public.extraction_runs_block_mutation()
        """
    )

    # --- extraction_proposals: guard (accepted doc + immutability + lifecycle) ----
    op.execute(
        """
        CREATE FUNCTION public.extraction_proposals_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE st text;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'pending' THEN
                    RAISE EXCEPTION 'extraction_proposals must be created pending';
                END IF;
                -- a pending row must be created without any review metadata.
                IF NEW.reviewed_by IS NOT NULL OR NEW.reviewed_at IS NOT NULL THEN
                    RAISE EXCEPTION 'pending extraction_proposals must have no review metadata';
                END IF;
                SELECT status INTO st FROM public.documents WHERE id = NEW.source_document_id;
                IF st IS DISTINCT FROM 'accepted' THEN
                    RAISE EXCEPTION 'proposal source document % is not accepted (status=%)',
                        NEW.source_document_id, st;
                END IF;
                RETURN NEW;
            END IF;
            -- UPDATE: content/identity columns are immutable.
            IF NEW.tenant_id              IS DISTINCT FROM OLD.tenant_id
            OR NEW.project_id             IS DISTINCT FROM OLD.project_id
            OR NEW.extraction_run_id      IS DISTINCT FROM OLD.extraction_run_id
            OR NEW.proposed_kind          IS DISTINCT FROM OLD.proposed_kind
            OR NEW.proposed_text          IS DISTINCT FROM OLD.proposed_text
            OR NEW.proposed_classification IS DISTINCT FROM OLD.proposed_classification
            OR NEW.source_document_id     IS DISTINCT FROM OLD.source_document_id
            OR NEW.evidence_quote         IS DISTINCT FROM OLD.evidence_quote
            OR NEW.extracted_by           IS DISTINCT FROM OLD.extracted_by
            OR NEW.created_at             IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'extraction_proposals content/identity columns are immutable';
            END IF;
            -- one-way lifecycle: only pending -> approved|rejected (also forbids
            -- leaving a terminal state, e.g. approved -> pending).
            IF NEW.status <> OLD.status
               AND NOT (OLD.status = 'pending' AND NEW.status IN ('approved', 'rejected')) THEN
                RAISE EXCEPTION 'extraction_proposals.status transition % -> % not allowed',
                    OLD.status, NEW.status;
            END IF;
            -- once decided, status + review metadata are frozen.
            IF OLD.status IN ('approved', 'rejected') THEN
                IF NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by
                OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at THEN
                    RAISE EXCEPTION
                        'extraction_proposals review metadata is immutable once decided';
                END IF;
            END IF;
            IF NEW.status <> OLD.status THEN
                -- pending -> decided: requires a complete, distinct-reviewer review (§2.2).
                IF NEW.reviewed_by IS NULL
                   OR NEW.reviewed_by = NEW.extracted_by
                   OR NEW.reviewed_at IS NULL THEN
                    RAISE EXCEPTION
                        'review requires reviewed_by (distinct from extracted_by) and reviewed_at';
                END IF;
            ELSE
                -- status unchanged & still pending: review metadata cannot be added.
                IF OLD.status = 'pending'
                   AND (NEW.reviewed_by IS NOT NULL OR NEW.reviewed_at IS NOT NULL) THEN
                    RAISE EXCEPTION
                        'pending extraction_proposals cannot gain review metadata '
                        'without a status transition';
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_proposals_guard
            BEFORE INSERT OR UPDATE ON public.extraction_proposals
            FOR EACH ROW EXECUTE FUNCTION public.extraction_proposals_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.extraction_proposals_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'extraction_proposals does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_proposals_no_delete
            BEFORE DELETE ON public.extraction_proposals
            FOR EACH ROW EXECUTE FUNCTION public.extraction_proposals_block_dml()
        """
    )
    op.execute(
        """
        CREATE TRIGGER extraction_proposals_no_truncate
            BEFORE TRUNCATE ON public.extraction_proposals
            FOR EACH STATEMENT EXECUTE FUNCTION public.extraction_proposals_block_dml()
        """
    )

    # --- RLS + grants -------------------------------------------------------------
    for table in ("extraction_runs", "extraction_proposals"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON extraction_runs FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON extraction_runs TO uaid_app")
    op.execute("REVOKE DELETE, TRUNCATE ON extraction_proposals FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON extraction_proposals TO uaid_app")


def downgrade() -> None:
    for table in ("extraction_runs", "extraction_proposals"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON extraction_proposals FROM uaid_app")
    op.execute("REVOKE SELECT, INSERT ON extraction_runs FROM uaid_app")
    # proposals triggers/functions
    op.execute("DROP TRIGGER IF EXISTS extraction_proposals_no_truncate ON public.extraction_proposals")
    op.execute("DROP TRIGGER IF EXISTS extraction_proposals_no_delete ON public.extraction_proposals")
    op.execute("DROP FUNCTION IF EXISTS public.extraction_proposals_block_dml()")
    op.execute("DROP TRIGGER IF EXISTS extraction_proposals_guard ON public.extraction_proposals")
    op.execute("DROP FUNCTION IF EXISTS public.extraction_proposals_guard()")
    # runs triggers/functions
    op.execute("DROP TRIGGER IF EXISTS extraction_runs_no_truncate ON public.extraction_runs")
    op.execute("DROP TRIGGER IF EXISTS extraction_runs_no_update_delete ON public.extraction_runs")
    op.execute("DROP FUNCTION IF EXISTS public.extraction_runs_block_mutation()")
    op.execute("DROP TRIGGER IF EXISTS extraction_runs_accepted_doc ON public.extraction_runs")
    op.execute("DROP FUNCTION IF EXISTS public.extraction_runs_require_accepted_doc()")
    # tables: proposals first (FK → runs)
    op.drop_index("ix_extraction_proposals_tenant_run", table_name="extraction_proposals")
    op.drop_table("extraction_proposals")
    op.drop_index("ix_extraction_runs_tenant_project", table_name="extraction_runs")
    op.drop_table("extraction_runs")
