"""generated_artifacts

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-26

Slice 36 — canonical artifact generator under §7 authorship independence. One tenant-owned table:
  * generated_artifacts — one inert, NON-BINDING §6.3-typed draft row per generation attempt.
    SELECT/INSERT/UPDATE (no DELETE/TRUNCATE); content/identity/generator-lineage immutable; the
    one-way §7.2 authorship lifecycle (system_authored_unapproved -> {human_approved, independent_approved,
    disputed}) is gated by the §7.3 independence evidence (DB guard): approval needs approved_by distinct
    from generated_by; human_owner needs reviewer_authority; independent_agent_lineage needs a
    reviewer_prompt_family distinct from the generator's + reviewer_role + reviewer_authority. The deferred
    bases (domain_authority, reference_oracle) are forbidden by the approval_basis CHECK and the guard.
    source_document_id pinned to an ACCEPTED doc; shape-by-outcome (incl. the incurred-cost failed duality).
ENABLE+FORCE RLS + tenant_isolation. No change to existing tables (no spine write — store/infra-only).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_ARTIFACT_TYPES = (
    "project_manifest",
    "prd",
    "system_architecture_document",
    "data_model",
    "domain_pack",
    "integration_plan",
    "acceptance_criteria",
    "test_oracle_pack",
    "backlog",
    "task_contracts",
    "agent_skill_map",
    "tool_access_plan",
    "risk_register",
    "evidence_requirements",
    "go_live_checklist",
)
_AUTHORSHIP_STATUSES = (
    "user_authored",
    "user_authored_system_normalized",
    "system_authored_human_approved",
    "system_authored_independent_approved",
    "system_authored_unapproved",
    "disputed",
)
_OUTCOMES = ("succeeded", "refused_injection", "blocked_by_budget", "failed")
_APPROVAL_BASES = ("human_owner", "independent_agent_lineage")


def upgrade() -> None:
    op.create_table(
        "generated_artifacts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("source_document_id", sa.UUID(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("cost_external_ref", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "authorship_status",
            sa.Text(),
            server_default=sa.text("'system_authored_unapproved'"),
            nullable=False,
        ),
        sa.Column("generated_by", sa.Text(), nullable=False),
        sa.Column("generator_prompt_family", sa.Text(), nullable=False),
        sa.Column("generator_model_route", sa.Text(), nullable=True),
        sa.Column("approval_basis", sa.Text(), nullable=True),
        sa.Column("reviewer_role", sa.Text(), nullable=True),
        sa.Column("reviewer_prompt_family", sa.Text(), nullable=True),
        sa.Column("reviewer_authority", sa.Text(), nullable=True),
        sa.Column("reviewer_model_route", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"artifact_type IN ({', '.join(repr(s) for s in _ARTIFACT_TYPES)})",
            name=op.f("ck_generated_artifacts_artifact_type_valid"),
        ),
        sa.CheckConstraint(
            f"outcome IN ({', '.join(repr(s) for s in _OUTCOMES)})",
            name=op.f("ck_generated_artifacts_outcome_valid"),
        ),
        sa.CheckConstraint(
            f"authorship_status IN ({', '.join(repr(s) for s in _AUTHORSHIP_STATUSES)})",
            name=op.f("ck_generated_artifacts_authorship_status_valid"),
        ),
        sa.CheckConstraint(
            "approval_basis IS NULL OR approval_basis IN "
            f"({', '.join(repr(s) for s in _APPROVAL_BASES)})",
            name=op.f("ck_generated_artifacts_approval_basis_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            name="document_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_generated_artifacts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_artifacts")),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_generated_artifacts_id_project_tenant"
        ),
    )
    op.create_index(
        "ix_generated_artifacts_latest",
        "generated_artifacts",
        ["tenant_id", "project_id", "source_document_id", "artifact_type", "created_at"],
    )

    # --- guard: accepted doc + shape-by-outcome + immutability + §7.3 authorship --
    op.execute(
        """
        CREATE FUNCTION public.generated_artifacts_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE st text;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.authorship_status <> 'system_authored_unapproved'
                   OR NEW.approval_basis IS NOT NULL OR NEW.approved_by IS NOT NULL
                   OR NEW.approved_at IS NOT NULL OR NEW.reviewer_role IS NOT NULL
                   OR NEW.reviewer_prompt_family IS NOT NULL OR NEW.reviewer_authority IS NOT NULL
                   OR NEW.reviewer_model_route IS NOT NULL THEN
                    RAISE EXCEPTION 'generated artifact must be created system_authored_unapproved '
                        'with null approval evidence';
                END IF;
                SELECT status INTO st FROM public.documents WHERE id = NEW.source_document_id;
                IF st IS DISTINCT FROM 'accepted' THEN
                    RAISE EXCEPTION 'generated artifact source document % is not accepted (status=%)',
                        NEW.source_document_id, st;
                END IF;
                IF NEW.outcome = 'succeeded' THEN
                    IF NEW.title IS NULL OR NEW.body IS NULL OR NEW.cost_external_ref IS NULL
                       OR NEW.input_tokens IS NULL OR NEW.output_tokens IS NULL THEN
                        RAISE EXCEPTION 'succeeded generated artifact requires title, body, cost '
                            'and tokens';
                    END IF;
                ELSIF NEW.outcome IN ('refused_injection', 'blocked_by_budget') THEN
                    IF NEW.input_tokens IS NOT NULL OR NEW.output_tokens IS NOT NULL
                       OR NEW.cost_external_ref IS NOT NULL OR NEW.title IS NOT NULL
                       OR NEW.body IS NOT NULL THEN
                        RAISE EXCEPTION 'no-call outcome % must have null tokens/cost/title/body',
                            NEW.outcome;
                    END IF;
                ELSIF NEW.outcome = 'failed' THEN
                    IF NEW.title IS NOT NULL OR NEW.body IS NOT NULL THEN
                        RAISE EXCEPTION 'failed generated artifact must have null title/body';
                    END IF;
                    IF NOT (
                        (NEW.cost_external_ref IS NOT NULL AND NEW.input_tokens IS NOT NULL
                         AND NEW.output_tokens IS NOT NULL)
                        OR (NEW.cost_external_ref IS NULL AND NEW.input_tokens IS NULL
                            AND NEW.output_tokens IS NULL)
                    ) THEN
                        RAISE EXCEPTION 'failed generated artifact cost_external_ref and tokens must '
                            'be both set or both null';
                    END IF;
                END IF;
                RETURN NEW;
            END IF;
            -- UPDATE: run/content/identity/generator columns are immutable.
            IF NEW.tenant_id               IS DISTINCT FROM OLD.tenant_id
            OR NEW.project_id              IS DISTINCT FROM OLD.project_id
            OR NEW.source_document_id      IS DISTINCT FROM OLD.source_document_id
            OR NEW.artifact_type           IS DISTINCT FROM OLD.artifact_type
            OR NEW.model                   IS DISTINCT FROM OLD.model
            OR NEW.provider                IS DISTINCT FROM OLD.provider
            OR NEW.prompt_version          IS DISTINCT FROM OLD.prompt_version
            OR NEW.input_tokens            IS DISTINCT FROM OLD.input_tokens
            OR NEW.output_tokens           IS DISTINCT FROM OLD.output_tokens
            OR NEW.outcome                 IS DISTINCT FROM OLD.outcome
            OR NEW.cost_external_ref       IS DISTINCT FROM OLD.cost_external_ref
            OR NEW.title                   IS DISTINCT FROM OLD.title
            OR NEW.body                    IS DISTINCT FROM OLD.body
            OR NEW.generated_by            IS DISTINCT FROM OLD.generated_by
            OR NEW.generator_prompt_family IS DISTINCT FROM OLD.generator_prompt_family
            OR NEW.generator_model_route   IS DISTINCT FROM OLD.generator_model_route
            OR NEW.created_at              IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION
                    'generated_artifacts content/identity/generator columns are immutable';
            END IF;
            IF NEW.authorship_status <> OLD.authorship_status THEN
                IF OLD.outcome <> 'succeeded' THEN
                    RAISE EXCEPTION 'only a succeeded generated artifact can be reviewed';
                END IF;
                IF NOT (OLD.authorship_status = 'system_authored_unapproved'
                        AND NEW.authorship_status IN ('system_authored_human_approved',
                            'system_authored_independent_approved', 'disputed')) THEN
                    RAISE EXCEPTION 'generated_artifacts authorship transition % -> % not allowed',
                        OLD.authorship_status, NEW.authorship_status;
                END IF;
                IF NEW.authorship_status IN ('system_authored_human_approved',
                                             'system_authored_independent_approved') THEN
                    IF NEW.approved_by IS NULL OR NEW.approved_at IS NULL THEN
                        RAISE EXCEPTION 'approval requires approved_by and approved_at';
                    END IF;
                    IF NEW.approved_by = NEW.generated_by THEN
                        RAISE EXCEPTION 'approver must be distinct from the generator';
                    END IF;
                    IF NEW.authorship_status = 'system_authored_human_approved' THEN
                        IF NEW.approval_basis IS DISTINCT FROM 'human_owner'
                           OR NEW.reviewer_authority IS NULL THEN
                            RAISE EXCEPTION 'human_owner approval requires approval_basis=human_owner '
                                'and reviewer_authority';
                        END IF;
                    ELSE
                        IF NEW.approval_basis IS DISTINCT FROM 'independent_agent_lineage' THEN
                            RAISE EXCEPTION 'independent approval requires '
                                'approval_basis=independent_agent_lineage';
                        END IF;
                        IF NEW.reviewer_prompt_family IS NULL
                           OR NEW.reviewer_prompt_family = NEW.generator_prompt_family THEN
                            RAISE EXCEPTION 'reviewer_prompt_family must differ from the generator '
                                'prompt family';
                        END IF;
                        IF NEW.reviewer_role IS NULL OR NEW.reviewer_authority IS NULL THEN
                            RAISE EXCEPTION 'independent approval requires reviewer_role and '
                                'reviewer_authority';
                        END IF;
                    END IF;
                ELSIF NEW.authorship_status = 'disputed' THEN
                    IF NEW.approval_basis IS NOT NULL OR NEW.approved_by IS NOT NULL
                    OR NEW.approved_at IS NOT NULL OR NEW.reviewer_role IS NOT NULL
                    OR NEW.reviewer_prompt_family IS NOT NULL OR NEW.reviewer_authority IS NOT NULL
                    OR NEW.reviewer_model_route IS NOT NULL THEN
                        RAISE EXCEPTION 'disputed generated artifact must have null '
                            'approval/reviewer evidence';
                    END IF;
                END IF;
            ELSE
                IF OLD.authorship_status IN ('system_authored_human_approved',
                        'system_authored_independent_approved', 'disputed') THEN
                    IF NEW.approval_basis     IS DISTINCT FROM OLD.approval_basis
                    OR NEW.approved_by        IS DISTINCT FROM OLD.approved_by
                    OR NEW.approved_at        IS DISTINCT FROM OLD.approved_at
                    OR NEW.reviewer_role      IS DISTINCT FROM OLD.reviewer_role
                    OR NEW.reviewer_prompt_family IS DISTINCT FROM OLD.reviewer_prompt_family
                    OR NEW.reviewer_authority IS DISTINCT FROM OLD.reviewer_authority
                    OR NEW.reviewer_model_route IS DISTINCT FROM OLD.reviewer_model_route THEN
                        RAISE EXCEPTION
                            'generated_artifacts approval evidence is immutable once decided';
                    END IF;
                ELSE
                    IF NEW.approval_basis IS NOT NULL OR NEW.approved_by IS NOT NULL
                    OR NEW.approved_at IS NOT NULL OR NEW.reviewer_role IS NOT NULL
                    OR NEW.reviewer_prompt_family IS NOT NULL OR NEW.reviewer_authority IS NOT NULL
                    OR NEW.reviewer_model_route IS NOT NULL THEN
                        RAISE EXCEPTION 'generated_artifacts cannot gain approval evidence without '
                            'an authorship transition';
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
        CREATE TRIGGER generated_artifacts_guard
            BEFORE INSERT OR UPDATE ON public.generated_artifacts
            FOR EACH ROW EXECUTE FUNCTION public.generated_artifacts_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.generated_artifacts_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'generated_artifacts does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER generated_artifacts_no_delete
            BEFORE DELETE ON public.generated_artifacts
            FOR EACH ROW EXECUTE FUNCTION public.generated_artifacts_block_dml()
        """
    )
    op.execute(
        """
        CREATE TRIGGER generated_artifacts_no_truncate
            BEFORE TRUNCATE ON public.generated_artifacts
            FOR EACH STATEMENT EXECUTE FUNCTION public.generated_artifacts_block_dml()
        """
    )

    # --- RLS + grants -------------------------------------------------------------
    op.execute("ALTER TABLE generated_artifacts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE generated_artifacts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON generated_artifacts "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute("REVOKE DELETE, TRUNCATE ON generated_artifacts FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON generated_artifacts TO uaid_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON generated_artifacts")
    op.execute("ALTER TABLE generated_artifacts NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE generated_artifacts DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON generated_artifacts FROM uaid_app")
    op.execute(
        "DROP TRIGGER IF EXISTS generated_artifacts_no_truncate ON public.generated_artifacts"
    )
    op.execute("DROP TRIGGER IF EXISTS generated_artifacts_no_delete ON public.generated_artifacts")
    op.execute("DROP FUNCTION IF EXISTS public.generated_artifacts_block_dml()")
    op.execute("DROP TRIGGER IF EXISTS generated_artifacts_guard ON public.generated_artifacts")
    op.execute("DROP FUNCTION IF EXISTS public.generated_artifacts_guard()")
    op.drop_index("ix_generated_artifacts_latest", table_name="generated_artifacts")
    op.drop_table("generated_artifacts")
