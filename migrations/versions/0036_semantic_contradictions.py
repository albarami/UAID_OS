"""semantic_contradictions

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-27

Slice 37 — semantic contradiction detector (descriptive-only). Two tenant-owned, append-only tables:
  * semantic_contradiction_reports — one run snapshot (outcome incl. skipped_insufficient_input);
    shape-by-outcome guard + a report-side DEFERRABLE count-match trigger (contradiction_count = child
    rows at commit, B6).
  * semantic_contradictions — one pairwise contradiction (conflict_type ∈ §6.4 8, bounded description,
    artifact_a_id/artifact_b_id composite-FK to intake_artifacts [DB-proven existence, B4] + CHECK a<>b);
    a BEFORE-INSERT kind guard (both artifacts requirement/acceptance_criterion, B7) + a child-side
    DEFERRABLE count-match trigger so a late child insert can't drift the report count (B9).
Both ENABLE+FORCE RLS + tenant_isolation; SELECT/INSERT only (no UPDATE/DELETE/TRUNCATE). Purely additive
(artifact FKs reuse the existing intake_artifacts UNIQUE); Slice-13 untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_OUTCOMES = (
    "succeeded",
    "skipped_insufficient_input",
    "refused_injection",
    "blocked_by_budget",
    "failed",
)
_CONFLICT_TYPES = (
    "minor_wording",
    "scope",
    "business_rule",
    "technical",
    "legal_regulatory",
    "security",
    "budget_timeline",
    "authority",
)
_MAX_DESCRIPTION_CHARS = 2000
_MAX_CONTRADICTIONS = 200


def upgrade() -> None:
    op.create_table(
        "semantic_contradiction_reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("cost_external_ref", sa.Text(), nullable=True),
        sa.Column("contradiction_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "analyzed_artifact_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("input_truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("detected_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"outcome IN ({', '.join(repr(s) for s in _OUTCOMES)})",
            name=op.f("ck_semantic_contradiction_reports_outcome_valid"),
        ),
        sa.CheckConstraint(
            f"contradiction_count BETWEEN 0 AND {_MAX_CONTRADICTIONS}",
            name=op.f("ck_semantic_contradiction_reports_contradiction_count_bounded"),
        ),
        sa.CheckConstraint(
            "analyzed_artifact_count >= 0",
            name=op.f("ck_semantic_contradiction_reports_analyzed_artifact_count_nonneg"),
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
            name=op.f("fk_semantic_contradiction_reports_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_semantic_contradiction_reports")),
        sa.UniqueConstraint(
            "id",
            "project_id",
            "tenant_id",
            name="uq_semantic_contradiction_reports_id_project_tenant",
        ),
    )
    op.create_index(
        "ix_semantic_contradiction_reports_latest",
        "semantic_contradiction_reports",
        ["tenant_id", "project_id", "created_at"],
    )

    op.create_table(
        "semantic_contradictions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("report_id", sa.UUID(), nullable=False),
        sa.Column("conflict_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("artifact_a_id", sa.UUID(), nullable=False),
        sa.Column("artifact_b_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"conflict_type IN ({', '.join(repr(s) for s in _CONFLICT_TYPES)})",
            name=op.f("ck_semantic_contradictions_conflict_type_valid"),
        ),
        sa.CheckConstraint(
            f"char_length(description) BETWEEN 1 AND {_MAX_DESCRIPTION_CHARS}",
            name=op.f("ck_semantic_contradictions_description_bounded"),
        ),
        sa.CheckConstraint(
            "artifact_a_id <> artifact_b_id",
            name=op.f("ck_semantic_contradictions_artifacts_distinct"),
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "project_id", "tenant_id"],
            [
                "semantic_contradiction_reports.id",
                "semantic_contradiction_reports.project_id",
                "semantic_contradiction_reports.tenant_id",
            ],
            name="report_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_a_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            name="artifact_a_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_b_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            name="artifact_b_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_semantic_contradictions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_semantic_contradictions")),
    )
    op.create_index(
        "ix_semantic_contradictions_report", "semantic_contradictions", ["tenant_id", "report_id"]
    )

    # --- reports: shape-by-outcome guard (BEFORE INSERT) --------------------------
    op.execute(
        """
        CREATE FUNCTION public.semantic_contradiction_reports_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NEW.outcome = 'succeeded' THEN
                IF NEW.input_tokens IS NULL OR NEW.output_tokens IS NULL
                   OR NEW.cost_external_ref IS NULL THEN
                    RAISE EXCEPTION 'succeeded report requires tokens and cost';
                END IF;
            ELSIF NEW.outcome IN ('skipped_insufficient_input', 'refused_injection',
                                  'blocked_by_budget') THEN
                IF NEW.input_tokens IS NOT NULL OR NEW.output_tokens IS NOT NULL
                   OR NEW.cost_external_ref IS NOT NULL OR NEW.contradiction_count <> 0 THEN
                    RAISE EXCEPTION 'no-call outcome % must have null tokens/cost and zero '
                        'contradiction_count', NEW.outcome;
                END IF;
            ELSIF NEW.outcome = 'failed' THEN
                IF NEW.contradiction_count <> 0 THEN
                    RAISE EXCEPTION 'failed report must have zero contradiction_count';
                END IF;
                IF NOT (
                    (NEW.cost_external_ref IS NOT NULL AND NEW.input_tokens IS NOT NULL
                     AND NEW.output_tokens IS NOT NULL)
                    OR (NEW.cost_external_ref IS NULL AND NEW.input_tokens IS NULL
                        AND NEW.output_tokens IS NULL)
                ) THEN
                    RAISE EXCEPTION 'failed report cost_external_ref and tokens must be both set '
                        'or both null';
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER semantic_contradiction_reports_guard
            BEFORE INSERT ON public.semantic_contradiction_reports
            FOR EACH ROW EXECUTE FUNCTION public.semantic_contradiction_reports_guard()
        """
    )

    # --- count integrity: report-side (B6) + child-side (B9) deferred triggers ----
    # report-side (NEW is a report row): its stored count must equal its child rows at commit.
    op.execute(
        """
        CREATE FUNCTION public.semantic_contradiction_reports_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NEW.contradiction_count IS DISTINCT FROM (
                SELECT count(*) FROM public.semantic_contradictions WHERE report_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'report % contradiction_count does not match its child rows', NEW.id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER semantic_contradiction_reports_count_match
            AFTER INSERT ON public.semantic_contradiction_reports
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.semantic_contradiction_reports_count_match()
        """
    )
    # child-side (NEW is a contradiction row): the parent report's stored count must equal its child
    # rows at commit — so a LATE child insert into an already-committed report is rejected (B9).
    op.execute(
        """
        CREATE FUNCTION public.semantic_contradictions_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE stored int;
        BEGIN
            SELECT contradiction_count INTO stored
                FROM public.semantic_contradiction_reports WHERE id = NEW.report_id;
            IF stored IS DISTINCT FROM (
                SELECT count(*) FROM public.semantic_contradictions WHERE report_id = NEW.report_id
            ) THEN
                RAISE EXCEPTION 'report % contradiction_count does not match its child rows',
                    NEW.report_id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER semantic_contradictions_count_match
            AFTER INSERT ON public.semantic_contradictions
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.semantic_contradictions_count_match()
        """
    )

    # --- contradictions: artifact-kind guard (B7, BEFORE INSERT) ------------------
    op.execute(
        """
        CREATE FUNCTION public.semantic_contradictions_kind_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE ka text; kb text;
        BEGIN
            SELECT kind INTO ka FROM public.intake_artifacts WHERE id = NEW.artifact_a_id;
            SELECT kind INTO kb FROM public.intake_artifacts WHERE id = NEW.artifact_b_id;
            IF ka IS DISTINCT FROM 'requirement' AND ka IS DISTINCT FROM 'acceptance_criterion' THEN
                RAISE EXCEPTION 'semantic contradiction artifact_a kind % not in '
                    '(requirement, acceptance_criterion)', ka;
            END IF;
            IF kb IS DISTINCT FROM 'requirement' AND kb IS DISTINCT FROM 'acceptance_criterion' THEN
                RAISE EXCEPTION 'semantic contradiction artifact_b kind % not in '
                    '(requirement, acceptance_criterion)', kb;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER semantic_contradictions_kind_guard
            BEFORE INSERT ON public.semantic_contradictions
            FOR EACH ROW EXECUTE FUNCTION public.semantic_contradictions_kind_guard()
        """
    )

    # --- append-only block triggers ----------------------------------------------
    for table in ("semantic_contradiction_reports", "semantic_contradictions"):
        op.execute(
            f"""
            CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
            LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
            BEGIN
                RAISE EXCEPTION '{table} is append-only (no UPDATE/DELETE/TRUNCATE)';
            END
            $fn$
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_update_delete
                BEFORE UPDATE OR DELETE ON public.{table}
                FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_truncate
                BEFORE TRUNCATE ON public.{table}
                FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()
            """
        )

    # --- RLS + grants ------------------------------------------------------------
    for table in ("semantic_contradiction_reports", "semantic_contradictions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    for table in ("semantic_contradiction_reports", "semantic_contradictions"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT ON {table} FROM uaid_app")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS semantic_contradictions_count_match ON public.semantic_contradictions"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS semantic_contradiction_reports_count_match "
        "ON public.semantic_contradiction_reports"
    )
    op.execute("DROP FUNCTION IF EXISTS public.semantic_contradictions_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.semantic_contradiction_reports_count_match()")
    op.execute(
        "DROP TRIGGER IF EXISTS semantic_contradictions_kind_guard ON public.semantic_contradictions"
    )
    op.execute("DROP FUNCTION IF EXISTS public.semantic_contradictions_kind_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS semantic_contradiction_reports_guard "
        "ON public.semantic_contradiction_reports"
    )
    op.execute("DROP FUNCTION IF EXISTS public.semantic_contradiction_reports_guard()")
    op.drop_index("ix_semantic_contradictions_report", table_name="semantic_contradictions")
    op.drop_table("semantic_contradictions")
    op.drop_index(
        "ix_semantic_contradiction_reports_latest", table_name="semantic_contradiction_reports"
    )
    op.drop_table("semantic_contradiction_reports")
