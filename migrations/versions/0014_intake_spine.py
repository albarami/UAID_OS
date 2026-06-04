"""intake_spine

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-04

Slice 11 — Sanad provenance store + canonical intake spine (§3.4/§4.2/§4.4).

Adds the tenant-owned, append-only ``intake_artifacts`` (unified kind table) and
``intake_provenance`` (Sanad source store). DB-level guarantees:
  * no artifact may commit with zero provenance — a DEFERRABLE constraint trigger;
  * a document-backed source is pinned to an accepted document of the SAME
    tenant+project — a composite FK (needs the new documents unique) + a BEFORE
    INSERT trigger rejecting non-accepted documents;
  * both tables are append-only (SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked);
  * tenant isolation via ENABLE+FORCE RLS + the standard ``tenant_isolation`` policy.

The only change to the Slice-9 ``documents`` table is the additive unique
``(id, project_id, tenant_id)`` used as the document composite-FK target.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"

_KINDS = ("requirement", "acceptance_criterion", "test_oracle", "assumption")
_CLASSIFICATIONS = (
    "safe_assumption",
    "needs_approval",
    "unsafe_assumption_blocked",
    "unknown_cannot_proceed",
)
_KINDS_SQL = ", ".join(repr(k) for k in _KINDS)
_CLASSIFICATIONS_SQL = ", ".join(repr(c) for c in _CLASSIFICATIONS)
_CLASSIFICATION_CHECK = (
    f"(kind = 'assumption' AND classification IS NOT NULL "
    f"AND classification IN ({_CLASSIFICATIONS_SQL})) "
    "OR (kind <> 'assumption' AND classification IS NULL)"
)


def upgrade() -> None:
    # --- additive documents unique (FK target for document-backed provenance) -----
    op.create_unique_constraint(
        "uq_documents_id_project_tenant", "documents", ["id", "project_id", "tenant_id"]
    )

    # --- intake_artifacts ---------------------------------------------------------
    op.create_table(
        "intake_artifacts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "data", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("classification", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(f"kind IN ({_KINDS_SQL})", name=op.f("ck_intake_artifacts_kind_valid")),
        sa.CheckConstraint(
            "octet_length(ref) BETWEEN 1 AND 128", name=op.f("ck_intake_artifacts_ref_bounded")
        ),
        sa.CheckConstraint(
            "octet_length(title) BETWEEN 1 AND 4096",
            name=op.f("ck_intake_artifacts_title_bounded"),
        ),
        sa.CheckConstraint(
            _CLASSIFICATION_CHECK, name=op.f("ck_intake_artifacts_classification_valid")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            name="parent_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_intake_artifacts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intake_artifacts")),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "kind", "ref", name="uq_intake_artifacts_ref"
        ),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_intake_artifacts_id_project_tenant"
        ),
    )
    op.create_index(
        "ix_intake_artifacts_tenant_project",
        "intake_artifacts",
        ["tenant_id", "project_id"],
        unique=False,
    )

    # --- intake_provenance --------------------------------------------------------
    op.create_table(
        "intake_provenance",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("artifact_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "octet_length(origin) BETWEEN 1 AND 512",
            name=op.f("ck_intake_provenance_origin_bounded"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            name="artifact_project_tenant",
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
            name=op.f("fk_intake_provenance_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intake_provenance")),
    )
    op.create_index(
        "ix_intake_provenance_tenant_artifact",
        "intake_provenance",
        ["tenant_id", "artifact_id"],
        unique=False,
    )

    # --- DB invariant 1: every artifact needs >=1 provenance source (Sanad) -------
    # Deferrable so the artifact may be inserted before its sources within one txn;
    # the check runs at COMMIT (or when SET CONSTRAINTS ... IMMEDIATE is issued).
    op.execute(
        """
        CREATE FUNCTION public.intake_artifact_require_source() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM public.intake_provenance WHERE artifact_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'intake artifact % has no provenance source', NEW.id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER intake_artifacts_requires_source
            AFTER INSERT ON public.intake_artifacts
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.intake_artifact_require_source()
        """
    )

    # --- DB invariant 2: document-backed sources must reference an accepted doc ----
    op.execute(
        """
        CREATE FUNCTION public.intake_provenance_require_accepted_doc() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE st text;
        BEGIN
            IF NEW.document_id IS NOT NULL THEN
                SELECT status INTO st FROM public.documents WHERE id = NEW.document_id;
                IF st IS DISTINCT FROM 'accepted' THEN
                    RAISE EXCEPTION
                        'provenance document % is not accepted (status=%)', NEW.document_id, st;
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER intake_provenance_accepted_doc
            BEFORE INSERT ON public.intake_provenance
            FOR EACH ROW EXECUTE FUNCTION public.intake_provenance_require_accepted_doc()
        """
    )

    # --- DB invariant 3: append-only (block UPDATE/DELETE/TRUNCATE) ----------------
    for table in ("intake_artifacts", "intake_provenance"):
        op.execute(
            f"""
            CREATE FUNCTION public.{table}_block_mutation() RETURNS trigger
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
                FOR EACH ROW EXECUTE FUNCTION public.{table}_block_mutation()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_truncate
                BEFORE TRUNCATE ON public.{table}
                FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_mutation()
            """
        )

    # --- RLS (mirrors 0002/0004/.../0011) -----------------------------------------
    for table in ("intake_artifacts", "intake_provenance"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )

    # --- privileges: append-only for the runtime role -----------------------------
    for table in ("intake_artifacts", "intake_provenance"):
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    for table in ("intake_artifacts", "intake_provenance"):
        op.execute(f"REVOKE SELECT, INSERT ON {table} FROM uaid_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    # triggers + functions
    op.execute(
        "DROP TRIGGER IF EXISTS intake_provenance_accepted_doc ON public.intake_provenance"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.intake_provenance_require_accepted_doc()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS intake_artifacts_requires_source ON public.intake_artifacts"
    )
    op.execute("DROP FUNCTION IF EXISTS public.intake_artifact_require_source()")
    for table in ("intake_artifacts", "intake_provenance"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_mutation()")
    # tables: provenance first (its FK references intake_artifacts + documents unique)
    op.drop_index("ix_intake_provenance_tenant_artifact", table_name="intake_provenance")
    op.drop_table("intake_provenance")
    op.drop_index("ix_intake_artifacts_tenant_project", table_name="intake_artifacts")
    op.drop_table("intake_artifacts")
    # finally the documents unique (no FK references it now)
    op.drop_constraint("uq_documents_id_project_tenant", "documents", type_="unique")
