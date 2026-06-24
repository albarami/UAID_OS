"""pull_request_evidence (pull_request_evidence_snapshots)

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-24

Slice 29 — pull-request evidence connector (§12.3-12.4; App. B #7/#8 provenance feed). Adds the
tenant-owned, **immutable append-only** ``pull_request_evidence_snapshots`` (RLS; SELECT/INSERT only —
no UPDATE/DELETE/TRUNCATE; provider/provenance/pr_number/pr_state/approval_count/repo_ref(slug+token)/
merge_commit_sha CHECKs; a BEFORE INSERT guard enforcing JSON shapes [presence_flags/traceability_refs
objects; approver/reviewer/requested arrays], the **derived invariant** ``approval_count =
jsonb_array_length(approver_principals)`` [B-29-8, mirroring ``0025``'s count rule], and the **nullable
observed** ``check_status_summary`` shape [object of non-negative integer counts keyed by allowed states
+ optional combined_state]; plus UPDATE/DELETE/TRUNCATE block triggers). **Additive — no change to
existing tables; no ``production_autonomy`` / ruleset change (store-only).** Mirrors the append-only
snapshot pattern of ``0025_ci_evidence``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_SLUG_RE = "^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$"
_TOKENISH_RE = "/(gh[opusr]_|github_pat_)"
_TABLE = "pull_request_evidence_snapshots"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("repo_ref", sa.Text(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("pr_state", sa.Text(), nullable=False),
        sa.Column("merged", sa.Boolean(), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merge_commit_sha", sa.Text(), nullable=True),
        sa.Column("base_branch", sa.Text(), nullable=True),
        sa.Column("base_sha", sa.Text(), nullable=True),
        sa.Column("head_branch", sa.Text(), nullable=True),
        sa.Column("head_sha", sa.Text(), nullable=True),
        sa.Column(
            "merged_to_declared_protected_branch_observed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("check_status_summary", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "presence_flags",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("author_principal", sa.Text(), nullable=True),
        sa.Column(
            "approver_principals",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_principals",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "requested_reviewer_principals",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "requested_reviewers_observed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("merger_principal", sa.Text(), nullable=True),
        sa.Column("approval_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "self_approval_observed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "self_merge_observed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "review_separation_observed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "traceability_refs",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
            name=op.f("ck_pres_provenance_valid"),
        ),
        sa.CheckConstraint("provider IN ('github')", name=op.f("ck_pres_provider_valid")),
        sa.CheckConstraint("pr_number > 0", name=op.f("ck_pres_pr_number_pos")),
        sa.CheckConstraint(
            "pr_state IN ('open','closed','merged')", name=op.f("ck_pres_pr_state_valid")
        ),
        sa.CheckConstraint("approval_count >= 0", name=op.f("ck_pres_approval_count_nonneg")),
        sa.CheckConstraint(f"repo_ref ~ '{_SLUG_RE}'", name=op.f("ck_pres_repo_ref_slug")),
        sa.CheckConstraint(
            f"repo_ref !~* '{_TOKENISH_RE}'", name=op.f("ck_pres_repo_ref_not_tokenish")
        ),
        sa.CheckConstraint(
            "merge_commit_sha IS NULL OR merge_commit_sha ~ '^[0-9a-f]{7,64}$'",
            name=op.f("ck_pres_merge_commit_sha"),
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
            name=op.f("fk_pull_request_evidence_snapshots_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pull_request_evidence_snapshots")),
    )
    op.create_index(
        "ix_pres_tenant_project_pr_created",
        _TABLE,
        ["tenant_id", "project_id", "provider", "repo_ref", "pr_number", "created_at"],
    )

    # --- BEFORE INSERT guard (authoritative DB backstop; uaid_app holds INSERT) ----
    op.execute(
        """
        CREATE FUNCTION public.pull_request_evidence_snapshots_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            -- JSON container shapes (B-29-3/4 defense-in-depth).
            IF jsonb_typeof(NEW.presence_flags) <> 'object' THEN
                RAISE EXCEPTION 'pull_request_evidence_snapshots: presence_flags must be a JSON object';
            END IF;
            IF jsonb_typeof(NEW.traceability_refs) <> 'object' THEN
                RAISE EXCEPTION 'pull_request_evidence_snapshots: traceability_refs must be a JSON object';
            END IF;
            IF jsonb_typeof(NEW.approver_principals) <> 'array'
               OR jsonb_typeof(NEW.reviewer_principals) <> 'array'
               OR jsonb_typeof(NEW.requested_reviewer_principals) <> 'array' THEN
                RAISE EXCEPTION 'pull_request_evidence_snapshots: principal lists must be JSON arrays';
            END IF;
            -- Derived-count invariant (B-29-8, mirrors 0025's count rule).
            IF NEW.approval_count <> jsonb_array_length(NEW.approver_principals) THEN
                RAISE EXCEPTION 'pull_request_evidence_snapshots: approval_count must equal jsonb_array_length(approver_principals)';
            END IF;
            -- Observed check-status summary (B-29-1/8): NULL or an object of non-negative TRUE-integer
            -- counts keyed by allowed states, plus optional combined_state. Counts must serialize to
            -- pure integer digits (``^[0-9]+$``) so a float like 1.0 is rejected — making the DB guard
            -- an authoritative backstop that matches the Python validator (which rejects floats).
            IF NEW.check_status_summary IS NOT NULL THEN
                IF jsonb_typeof(NEW.check_status_summary) <> 'object' THEN
                    RAISE EXCEPTION 'pull_request_evidence_snapshots: check_status_summary must be null or an object';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM jsonb_each(NEW.check_status_summary) AS kv(k, v)
                    WHERE NOT (
                        (kv.k = 'combined_state' AND (
                            jsonb_typeof(kv.v) = 'null'
                            OR (jsonb_typeof(kv.v) = 'string'
                                AND (kv.v #>> '{}') IN ('success','failure','pending'))
                        ))
                        OR (kv.k IN ('success','failure','pending','neutral','error','unknown')
                            AND jsonb_typeof(kv.v) = 'number'
                            AND (kv.v::text) ~ '^[0-9]+$')
                    )
                ) THEN
                    RAISE EXCEPTION 'pull_request_evidence_snapshots: check_status_summary has an invalid key or value';
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER pull_request_evidence_snapshots_guard
            BEFORE INSERT ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION public.pull_request_evidence_snapshots_guard()
        """
    )

    # --- append-only: block UPDATE/DELETE/TRUNCATE (mirror 0025) -------------------
    op.execute(
        """
        CREATE FUNCTION public.pull_request_evidence_snapshots_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'pull_request_evidence_snapshots is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER pull_request_evidence_snapshots_no_update_delete
            BEFORE UPDATE OR DELETE ON public.{_TABLE}
            FOR EACH ROW EXECUTE FUNCTION public.pull_request_evidence_snapshots_block_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER pull_request_evidence_snapshots_no_truncate
            BEFORE TRUNCATE ON public.{_TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION public.pull_request_evidence_snapshots_block_mutation()
        """
    )

    # --- RLS + grants (mirror 0025) -----------------------------------------------
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
    op.execute(
        f"DROP TRIGGER IF EXISTS pull_request_evidence_snapshots_no_truncate ON public.{_TABLE}"
    )
    op.execute(
        f"DROP TRIGGER IF EXISTS pull_request_evidence_snapshots_no_update_delete ON public.{_TABLE}"
    )
    op.execute("DROP FUNCTION IF EXISTS public.pull_request_evidence_snapshots_block_mutation()")
    op.execute(f"DROP TRIGGER IF EXISTS pull_request_evidence_snapshots_guard ON public.{_TABLE}")
    op.execute("DROP FUNCTION IF EXISTS public.pull_request_evidence_snapshots_guard()")
    op.drop_index("ix_pres_tenant_project_pr_created", table_name=_TABLE)
    op.drop_table(_TABLE)
