"""document_classifications

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-26

Slice 35 — document classifier + source/authority mapping. One tenant-owned table:
  * document_classifications — one inert row per classification attempt (1:1 with its run).
    SELECT/INSERT/UPDATE (no DELETE/TRUNCATE); content/identity immutable, one-way review
    lifecycle (pending -> approved|rejected) with a reviewed_by distinct from classified_by
    (§2.2). document_id pinned to an ACCEPTED doc. Shape-by-outcome guard (B2 incurred-cost
    duality): succeeded carries proposed fields + cost + tokens + pending review; the two
    no-call outcomes carry nulls + not_applicable; failed carries null proposed/evidence and
    cost+tokens either both-set (parse/evidence failure) or both-null (exception/invalid token).
ENABLE+FORCE RLS + tenant_isolation. No change to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_DOCUMENT_TYPES = (
    "strategy_document",
    "commercial_document",
    "product_document",
    "technical_architecture_document",
    "regulatory_document",
    "data_dictionary",
    "diagram",
    "policy",
    "operational_runbook",
    "design",
    "source_code",
    "spreadsheet",
    "api_doc",
    "contract",
    "existing_jira_github_artifact",
    "unknown",
)
_AUTHORITY_TIERS = ("authoritative", "supporting", "informational", "unknown")
_OUTCOMES = ("succeeded", "refused_injection", "blocked_by_budget", "failed")
_REVIEW_STATUSES = ("pending", "approved", "rejected", "not_applicable")


def upgrade() -> None:
    op.create_table(
        "document_classifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("cost_external_ref", sa.Text(), nullable=True),
        sa.Column("proposed_document_type", sa.Text(), nullable=True),
        sa.Column("proposed_authority_tier", sa.Text(), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column(
            "review_status", sa.Text(), server_default=sa.text("'not_applicable'"), nullable=False
        ),
        sa.Column("classified_by", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"outcome IN ({', '.join(repr(s) for s in _OUTCOMES)})",
            name=op.f("ck_document_classifications_outcome_valid"),
        ),
        sa.CheckConstraint(
            "proposed_document_type IS NULL OR proposed_document_type IN "
            f"({', '.join(repr(s) for s in _DOCUMENT_TYPES)})",
            name=op.f("ck_document_classifications_proposed_document_type_valid"),
        ),
        sa.CheckConstraint(
            "proposed_authority_tier IS NULL OR proposed_authority_tier IN "
            f"({', '.join(repr(s) for s in _AUTHORITY_TIERS)})",
            name=op.f("ck_document_classifications_proposed_authority_tier_valid"),
        ),
        sa.CheckConstraint(
            f"review_status IN ({', '.join(repr(s) for s in _REVIEW_STATUSES)})",
            name=op.f("ck_document_classifications_review_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            name="document_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_document_classifications_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_classifications")),
    )
    op.create_index(
        "ix_document_classifications_latest",
        "document_classifications",
        ["tenant_id", "project_id", "document_id", "created_at"],
    )

    # --- guard: accepted doc + shape-by-outcome + immutability + one-way review ----
    op.execute(
        """
        CREATE FUNCTION public.document_classifications_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE st text;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.reviewed_by IS NOT NULL OR NEW.reviewed_at IS NOT NULL THEN
                    RAISE EXCEPTION 'classification must be created without review metadata';
                END IF;
                SELECT status INTO st FROM public.documents WHERE id = NEW.document_id;
                IF st IS DISTINCT FROM 'accepted' THEN
                    RAISE EXCEPTION 'classification source document % is not accepted (status=%)',
                        NEW.document_id, st;
                END IF;
                IF NEW.outcome = 'succeeded' THEN
                    IF NEW.proposed_document_type IS NULL OR NEW.proposed_authority_tier IS NULL
                       OR NEW.evidence_quote IS NULL OR NEW.cost_external_ref IS NULL
                       OR NEW.input_tokens IS NULL OR NEW.output_tokens IS NULL
                       OR NEW.review_status <> 'pending' THEN
                        RAISE EXCEPTION 'succeeded classification requires non-null proposed '
                            'fields, evidence, cost and tokens with pending review';
                    END IF;
                ELSIF NEW.outcome IN ('refused_injection', 'blocked_by_budget') THEN
                    IF NEW.input_tokens IS NOT NULL OR NEW.output_tokens IS NOT NULL
                       OR NEW.cost_external_ref IS NOT NULL OR NEW.proposed_document_type IS NOT NULL
                       OR NEW.proposed_authority_tier IS NOT NULL OR NEW.evidence_quote IS NOT NULL
                       OR NEW.review_status <> 'not_applicable' THEN
                        RAISE EXCEPTION 'no-call outcome % must have null tokens/cost/proposed/'
                            'evidence and not_applicable review', NEW.outcome;
                    END IF;
                ELSIF NEW.outcome = 'failed' THEN
                    IF NEW.proposed_document_type IS NOT NULL OR NEW.proposed_authority_tier IS NOT NULL
                       OR NEW.evidence_quote IS NOT NULL OR NEW.review_status <> 'not_applicable' THEN
                        RAISE EXCEPTION 'failed classification must have null proposed/evidence '
                            'and not_applicable review';
                    END IF;
                    IF NOT (
                        (NEW.cost_external_ref IS NOT NULL AND NEW.input_tokens IS NOT NULL
                         AND NEW.output_tokens IS NOT NULL)
                        OR (NEW.cost_external_ref IS NULL AND NEW.input_tokens IS NULL
                            AND NEW.output_tokens IS NULL)
                    ) THEN
                        RAISE EXCEPTION 'failed classification cost_external_ref and tokens must '
                            'be both set or both null';
                    END IF;
                END IF;
                RETURN NEW;
            END IF;
            -- UPDATE: content/identity columns are immutable.
            IF NEW.tenant_id              IS DISTINCT FROM OLD.tenant_id
            OR NEW.project_id             IS DISTINCT FROM OLD.project_id
            OR NEW.document_id            IS DISTINCT FROM OLD.document_id
            OR NEW.model                  IS DISTINCT FROM OLD.model
            OR NEW.provider               IS DISTINCT FROM OLD.provider
            OR NEW.prompt_version         IS DISTINCT FROM OLD.prompt_version
            OR NEW.input_tokens           IS DISTINCT FROM OLD.input_tokens
            OR NEW.output_tokens          IS DISTINCT FROM OLD.output_tokens
            OR NEW.outcome                IS DISTINCT FROM OLD.outcome
            OR NEW.cost_external_ref      IS DISTINCT FROM OLD.cost_external_ref
            OR NEW.proposed_document_type IS DISTINCT FROM OLD.proposed_document_type
            OR NEW.proposed_authority_tier IS DISTINCT FROM OLD.proposed_authority_tier
            OR NEW.evidence_quote         IS DISTINCT FROM OLD.evidence_quote
            OR NEW.classified_by          IS DISTINCT FROM OLD.classified_by
            OR NEW.created_at             IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'document_classifications content/identity columns are immutable';
            END IF;
            -- only a succeeded run is reviewable.
            IF NEW.review_status <> OLD.review_status AND OLD.outcome <> 'succeeded' THEN
                RAISE EXCEPTION 'only a succeeded classification can be reviewed';
            END IF;
            -- one-way review: only pending -> approved|rejected.
            IF NEW.review_status <> OLD.review_status
               AND NOT (OLD.review_status = 'pending'
                        AND NEW.review_status IN ('approved', 'rejected')) THEN
                RAISE EXCEPTION 'document_classifications review transition % -> % not allowed',
                    OLD.review_status, NEW.review_status;
            END IF;
            -- once decided, review metadata is frozen.
            IF OLD.review_status IN ('approved', 'rejected') THEN
                IF NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by
                OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at THEN
                    RAISE EXCEPTION
                        'document_classifications review metadata is immutable once decided';
                END IF;
            END IF;
            IF NEW.review_status <> OLD.review_status THEN
                IF NEW.reviewed_by IS NULL
                   OR NEW.reviewed_by = NEW.classified_by
                   OR NEW.reviewed_at IS NULL THEN
                    RAISE EXCEPTION
                        'review requires reviewed_by (distinct from classified_by) and reviewed_at';
                END IF;
            ELSE
                IF OLD.review_status = 'pending'
                   AND (NEW.reviewed_by IS NOT NULL OR NEW.reviewed_at IS NOT NULL) THEN
                    RAISE EXCEPTION
                        'pending classification cannot gain review metadata without a transition';
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_classifications_guard
            BEFORE INSERT OR UPDATE ON public.document_classifications
            FOR EACH ROW EXECUTE FUNCTION public.document_classifications_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.document_classifications_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'document_classifications does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_classifications_no_delete
            BEFORE DELETE ON public.document_classifications
            FOR EACH ROW EXECUTE FUNCTION public.document_classifications_block_dml()
        """
    )
    op.execute(
        """
        CREATE TRIGGER document_classifications_no_truncate
            BEFORE TRUNCATE ON public.document_classifications
            FOR EACH STATEMENT EXECUTE FUNCTION public.document_classifications_block_dml()
        """
    )

    # --- RLS + grants -------------------------------------------------------------
    op.execute("ALTER TABLE document_classifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_classifications FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON document_classifications "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute("REVOKE DELETE, TRUNCATE ON document_classifications FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON document_classifications TO uaid_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON document_classifications")
    op.execute("ALTER TABLE document_classifications NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_classifications DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON document_classifications FROM uaid_app")
    op.execute(
        "DROP TRIGGER IF EXISTS document_classifications_no_truncate ON public.document_classifications"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS document_classifications_no_delete ON public.document_classifications"
    )
    op.execute("DROP FUNCTION IF EXISTS public.document_classifications_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS document_classifications_guard ON public.document_classifications"
    )
    op.execute("DROP FUNCTION IF EXISTS public.document_classifications_guard()")
    op.drop_index("ix_document_classifications_latest", table_name="document_classifications")
    op.drop_table("document_classifications")
