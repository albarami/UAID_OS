"""intake_categories

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-12

Slice 15 — intake category modeling (R3–R5 readiness foundation; inputs only). Adds a
tenant-owned ``intake_categories`` table: one declaration per (tenant, project, category)
for the 20 declarable §4.2 categories. Exactly one source per row (document XOR origin,
CHECK-enforced); document-backed sources are pinned to an ACCEPTED same-project document
(guard trigger). Content/identity keys are immutable on UPDATE; rows are never DELETEd.
ENABLE+FORCE RLS + tenant_isolation; SELECT/INSERT/UPDATE for uaid_app (no DELETE). No
change to existing tables; the readiness auditor is untouched (still R2-capped).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"

# The 20 declarable §4.2 categories (mirrors app.intake.categories.DECLARABLE_INTAKE_CATEGORIES).
_DECLARABLE = (
    "project_manifest", "product_brief", "business_objectives", "scope_and_boundaries",
    "users_roles_permissions", "user_journeys_and_workflows", "non_functional_requirements",
    "domain_pack", "data_model_and_contracts", "integrations_and_external_systems",
    "existing_assets_and_repositories", "architecture_and_technology_constraints",
    "security_privacy_compliance", "environments_and_deployment_targets",
    "secrets_and_credentials_manifest", "tool_access_manifest",
    "operations_observability_support", "go_live_checklist",
    "risk_register_and_assurance_requirements", "prior_decisions_and_architecture_log",
)
_CATEGORIES_SQL = ", ".join(repr(c) for c in _DECLARABLE)
_SOURCE_XOR = (
    "(source_document_id IS NOT NULL AND locator IS NOT NULL AND origin IS NULL) "
    "OR (source_document_id IS NULL AND locator IS NULL AND origin IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "intake_categories",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'declared'"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("data", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.Column("source_document_id", sa.UUID(), nullable=True),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column("origin", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"category IN ({_CATEGORIES_SQL})",
                           name=op.f("ck_intake_categories_category_valid")),
        sa.CheckConstraint("status IN ('declared', 'not_applicable')",
                           name=op.f("ck_intake_categories_status_valid")),
        sa.CheckConstraint("octet_length(summary) <= 4096",
                           name=op.f("ck_intake_categories_summary_bounded")),
        sa.CheckConstraint("origin IS NULL OR octet_length(origin) BETWEEN 1 AND 512",
                           name=op.f("ck_intake_categories_origin_bounded")),
        sa.CheckConstraint(_SOURCE_XOR, name=op.f("ck_intake_categories_source_xor")),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            name="document_project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_intake_categories_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intake_categories")),
        sa.UniqueConstraint("tenant_id", "project_id", "category", name="uq_intake_categories_cat"),
    )
    op.create_index(
        "ix_intake_categories_tenant_project", "intake_categories", ["tenant_id", "project_id"]
    )

    # Guard: accepted-doc on insert/update + immutability of content/identity keys on update.
    op.execute(
        """
        CREATE FUNCTION public.intake_categories_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE st text;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF NEW.id          IS DISTINCT FROM OLD.id
                OR NEW.tenant_id   IS DISTINCT FROM OLD.tenant_id
                OR NEW.project_id  IS DISTINCT FROM OLD.project_id
                OR NEW.category    IS DISTINCT FROM OLD.category
                OR NEW.created_at  IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'intake_categories id/tenant/project/category/created_at are immutable';
                END IF;
            END IF;
            IF NEW.source_document_id IS NOT NULL THEN
                SELECT status INTO st FROM public.documents WHERE id = NEW.source_document_id;
                IF st IS DISTINCT FROM 'accepted' THEN
                    RAISE EXCEPTION 'intake_categories source document % is not accepted (status=%)',
                        NEW.source_document_id, st;
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER intake_categories_guard
            BEFORE INSERT OR UPDATE ON public.intake_categories
            FOR EACH ROW EXECUTE FUNCTION public.intake_categories_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.intake_categories_block_delete() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'intake_categories does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER intake_categories_no_delete
            BEFORE DELETE ON public.intake_categories
            FOR EACH ROW EXECUTE FUNCTION public.intake_categories_block_delete()
        """
    )
    op.execute(
        """
        CREATE TRIGGER intake_categories_no_truncate
            BEFORE TRUNCATE ON public.intake_categories
            FOR EACH STATEMENT EXECUTE FUNCTION public.intake_categories_block_delete()
        """
    )

    # RLS + grants
    op.execute("ALTER TABLE intake_categories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE intake_categories FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON intake_categories "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute("REVOKE DELETE, TRUNCATE ON intake_categories FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON intake_categories TO uaid_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON intake_categories")
    op.execute("ALTER TABLE intake_categories NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE intake_categories DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON intake_categories FROM uaid_app")
    op.execute("DROP TRIGGER IF EXISTS intake_categories_no_truncate ON public.intake_categories")
    op.execute("DROP TRIGGER IF EXISTS intake_categories_no_delete ON public.intake_categories")
    op.execute("DROP FUNCTION IF EXISTS public.intake_categories_block_delete()")
    op.execute("DROP TRIGGER IF EXISTS intake_categories_guard ON public.intake_categories")
    op.execute("DROP FUNCTION IF EXISTS public.intake_categories_guard()")
    op.drop_index("ix_intake_categories_tenant_project", table_name="intake_categories")
    op.drop_table("intake_categories")
