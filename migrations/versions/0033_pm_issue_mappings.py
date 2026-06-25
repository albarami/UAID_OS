"""pm_issue_mappings (PM / issue-tracker connector)

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-25

Slice 34 — PM / issue-tracker connector (§12.3 / §26.3). Adds the tenant-owned, **immutable append-only**
``pm_issue_mappings`` (RLS; SELECT/INSERT only — no UPDATE/DELETE/TRUNCATE; ``external_system`` enum;
``instance_key``/``external_ref`` bounded-shape CHECKs + a token denylist; ``external_status`` length CHECK;
``board_column`` ∈ the 16 §12.3 columns ∪ ``unmapped``). Records **only** observed facts — **NO
title/description/credential/release_issue_id column** (structural: no secret/free-text, no ``release_issues``
coupling). Latest-wins keyed by ``(tenant_id, project_id, external_system, instance_key, external_ref)``.
All validation is column CHECKs (no guard trigger). **Additive — no change to existing tables** (incl.
``release_issues``). Mirrors the append-only pattern of ``0031``/``0032``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLE = "pm_issue_mappings"
_BOARD_COLUMNS = (
    "backlog",
    "analysis",
    "requirements_review",
    "ready_for_development",
    "in_progress",
    "developer_self_check",
    "specialist_review",
    "changes_requested",
    "qa_testing",
    "security_review",
    "shortcut_detection",
    "acceptance_verification",
    "evidence_audit",
    "ready_for_release",
    "released",
    "done",
    "unmapped",
)


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("external_system", sa.Text(), nullable=False),
        sa.Column("instance_key", sa.Text(), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=False),
        sa.Column("external_status", sa.Text(), nullable=False),
        sa.Column("board_column", sa.Text(), nullable=False),
        sa.Column("title_present", sa.Boolean(), nullable=False),
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
            name=op.f("ck_pim_provenance_valid"),
        ),
        sa.CheckConstraint(
            "external_system IN ('jira')", name=op.f("ck_pim_external_system_valid")
        ),
        sa.CheckConstraint(
            "instance_key ~ '^[a-z0-9_.:-]{1,64}$'", name=op.f("ck_pim_instance_key_shape")
        ),
        sa.CheckConstraint(
            "external_ref ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'",
            name=op.f("ck_pim_external_ref_shape"),
        ),
        sa.CheckConstraint(
            "external_ref !~* '(gh[opusr]_|github_pat_)'",
            name=op.f("ck_pim_external_ref_not_tokenish"),
        ),
        sa.CheckConstraint(
            "char_length(external_status) BETWEEN 1 AND 256",
            name=op.f("ck_pim_external_status_len"),
        ),
        sa.CheckConstraint(
            "board_column IN (" + ", ".join(repr(c) for c in _BOARD_COLUMNS) + ")",
            name=op.f("ck_pim_board_column_valid"),
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
            name=op.f("fk_pm_issue_mappings_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pm_issue_mappings")),
    )
    op.create_index(
        "ix_pim_tenant_project_system_instance_ref_created",
        _TABLE,
        [
            "tenant_id",
            "project_id",
            "external_system",
            "instance_key",
            "external_ref",
            "created_at",
        ],
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE (mirror 0031/0032) -------------
    op.execute(
        """
        CREATE FUNCTION public.pm_issue_mappings_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'pm_issue_mappings is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER pm_issue_mappings_no_update_delete
            BEFORE UPDATE OR DELETE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION public.pm_issue_mappings_block_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER pm_issue_mappings_no_truncate
            BEFORE TRUNCATE ON public.{_TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION public.pm_issue_mappings_block_mutation()
        """
    )

    # --- RLS + grants (mirror 0031/0032) ------------------------------------------
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
    op.execute(f"DROP TRIGGER IF EXISTS pm_issue_mappings_no_truncate ON public.{_TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS pm_issue_mappings_no_update_delete ON public.{_TABLE}")
    op.execute("DROP FUNCTION IF EXISTS public.pm_issue_mappings_block_mutation()")
    op.drop_index("ix_pim_tenant_project_system_instance_ref_created", table_name=_TABLE)
    op.drop_table(_TABLE)
