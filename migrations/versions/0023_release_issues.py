"""release_issues

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-15

Slice 24 — open-issue / blocker store (§24.1/§24.2/Appendix B #7). Adds tenant-owned
``release_issues`` (RLS; SELECT/INSERT/UPDATE, no DELETE; category/severity/status CHECKs; a guard
trigger enforcing INSERT invariants, the issue_category='other' rule, critical⇒blocking, NULL
resolution/acceptance metadata on insert, per-transition column mutability, one-way lifecycle,
hard-blocker-cannot-be-accepted, and accepted-requires-a-usable-risk-acceptance-record) +
append-only ``release_issue_events`` (SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked). Additive —
no change to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"

_IMMUTABLE = (
    "id",
    "tenant_id",
    "project_id",
    "issue_category",
    "severity",
    "blocking",
    "blocking_category",
    "summary",
    "detail",
    "source",
    "source_provenance",
    "created_at",
)
_CATEGORIES = (
    "security",
    "shortcut",
    "test_or_acceptance",
    "cost",
    "deployment",
    "rollback",
    "monitoring",
    "evidence",
    "approval",
    "other",
)
_HARD_REFUSALS = (
    "critical_security_blocker",
    "fake_done_finding",
    "missing_production_rollback",
    "missing_regulated_or_safety_authority",
)


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "release_issues",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("issue_category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("blocking_category", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "source_provenance",
            sa.Text(),
            server_default=sa.text("'caller_supplied_unverified'"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("risk_acceptance_record_id", sa.UUID(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
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
            f"issue_category IN ({_sql_list(_CATEGORIES)})",
            name=op.f("ck_release_issues_issue_category_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name=op.f("ck_release_issues_severity_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('open','resolved','accepted','superseded')",
            name=op.f("ck_release_issues_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["risk_acceptance_record_id", "tenant_id"],
            ["risk_acceptance_records.id", "risk_acceptance_records.tenant_id"],
            name="risk_acceptance_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_release_issues_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_issues")),
        sa.UniqueConstraint("id", "tenant_id", name="uq_release_issues_id_tenant"),
    )
    op.create_index(
        "ix_release_issues_tenant_project_status",
        "release_issues",
        ["tenant_id", "project_id", "status"],
    )

    op.create_table(
        "release_issue_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("issue_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["issue_id", "tenant_id"],
            ["release_issues.id", "release_issues.tenant_id"],
            name="issue_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_release_issue_events_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_issue_events")),
    )
    op.create_index(
        "ix_release_issue_events_issue",
        "release_issue_events",
        ["tenant_id", "issue_id", "created_at"],
    )

    immutable_checks = "\n            OR ".join(
        f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _IMMUTABLE
    )
    op.execute(
        f"""
        CREATE FUNCTION public.release_issues_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE ok int;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'open' THEN
                    RAISE EXCEPTION 'release_issues must be created with status=open';
                END IF;
                IF NEW.source_provenance <> 'caller_supplied_unverified' THEN
                    RAISE EXCEPTION 'release_issues source_provenance must be caller_supplied_unverified';
                END IF;
                IF NEW.risk_acceptance_record_id IS NOT NULL
                OR NEW.resolution_note IS NOT NULL
                OR NEW.resolved_at IS NOT NULL
                OR NEW.resolved_by IS NOT NULL THEN
                    RAISE EXCEPTION 'release_issues: resolution/acceptance metadata must be NULL at creation';
                END IF;
                IF NEW.issue_category = 'other'
                AND (NEW.summary IS NULL OR btrim(NEW.summary) = ''
                     OR NEW.detail IS NULL OR btrim(NEW.detail) = '') THEN
                    RAISE EXCEPTION 'release_issues: issue_category=other requires non-empty summary and detail';
                END IF;
                IF NEW.severity = 'critical' AND NEW.blocking IS NOT TRUE THEN
                    RAISE EXCEPTION 'release_issues: critical issues must be blocking';
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'release_issues: identity/content/source fields are immutable';
                END IF;
                IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
                    -- status unchanged ⇒ no field may change (incl. updated_at): no out-of-band edits.
                    IF NEW.risk_acceptance_record_id IS DISTINCT FROM OLD.risk_acceptance_record_id
                    OR NEW.resolution_note IS DISTINCT FROM OLD.resolution_note
                    OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
                    OR NEW.resolved_by IS DISTINCT FROM OLD.resolved_by
                    OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
                        RAISE EXCEPTION 'release_issues: fields change only via a status transition';
                    END IF;
                ELSE
                    IF OLD.status <> 'open' THEN
                        RAISE EXCEPTION 'release_issues: terminal status % cannot transition', OLD.status;
                    END IF;
                    IF NEW.status NOT IN ('resolved','accepted','superseded') THEN
                        RAISE EXCEPTION 'release_issues: invalid target status %', NEW.status;
                    END IF;
                    IF NEW.status = 'accepted' THEN
                        IF OLD.severity = 'critical'
                        OR OLD.blocking_category IN ({_sql_list(_HARD_REFUSALS)}) THEN
                            RAISE EXCEPTION 'release_issues: critical/hard-blocker issues cannot be accepted';
                        END IF;
                        IF NEW.risk_acceptance_record_id IS NULL THEN
                            RAISE EXCEPTION 'release_issues: accepted requires a risk_acceptance_record_id';
                        END IF;
                        IF NEW.resolution_note IS NOT NULL
                        OR NEW.resolved_at IS NOT NULL
                        OR NEW.resolved_by IS NOT NULL THEN
                            RAISE EXCEPTION 'release_issues: accepted must not set resolution metadata';
                        END IF;
                        SELECT 1 INTO ok FROM public.risk_acceptance_records r
                            WHERE r.id = NEW.risk_acceptance_record_id
                              AND r.tenant_id = NEW.tenant_id
                              AND r.project_id = NEW.project_id
                              AND r.status = 'active'
                              AND r.expiry_date >= CURRENT_DATE
                              AND r.blocking_category IS NULL
                              AND r.issue_id = NEW.id::text;
                        IF ok IS NULL THEN
                            RAISE EXCEPTION 'release_issues: no usable risk-acceptance record for this issue';
                        END IF;
                    ELSE
                        IF NEW.risk_acceptance_record_id IS NOT NULL THEN
                            RAISE EXCEPTION 'release_issues: only accepted may set risk_acceptance_record_id';
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
        CREATE TRIGGER release_issues_guard
            BEFORE INSERT OR UPDATE ON public.release_issues
            FOR EACH ROW EXECUTE FUNCTION public.release_issues_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.release_issues_block_delete() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'release_issues does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_issues_no_delete
            BEFORE DELETE ON public.release_issues
            FOR EACH ROW EXECUTE FUNCTION public.release_issues_block_delete()
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_issues_no_truncate
            BEFORE TRUNCATE ON public.release_issues
            FOR EACH STATEMENT EXECUTE FUNCTION public.release_issues_block_delete()
        """
    )

    op.execute(
        """
        CREATE FUNCTION public.release_issue_events_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'release_issue_events is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_issue_events_no_update_delete
            BEFORE UPDATE OR DELETE ON public.release_issue_events
            FOR EACH ROW EXECUTE FUNCTION public.release_issue_events_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_issue_events_no_truncate
            BEFORE TRUNCATE ON public.release_issue_events
            FOR EACH STATEMENT EXECUTE FUNCTION public.release_issue_events_block_mutation()
        """
    )

    for table in ("release_issues", "release_issue_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
    op.execute("REVOKE DELETE, TRUNCATE ON release_issues FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON release_issues TO uaid_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON release_issue_events FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON release_issue_events TO uaid_app")


def downgrade() -> None:
    for table in ("release_issue_events", "release_issues"):
        op.execute(f"REVOKE ALL ON {table} FROM uaid_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP TRIGGER IF EXISTS release_issue_events_no_truncate ON public.release_issue_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS release_issue_events_no_update_delete "
        "ON public.release_issue_events"
    )
    op.execute("DROP FUNCTION IF EXISTS public.release_issue_events_block_mutation()")
    op.execute("DROP TRIGGER IF EXISTS release_issues_no_truncate ON public.release_issues")
    op.execute("DROP TRIGGER IF EXISTS release_issues_no_delete ON public.release_issues")
    op.execute("DROP TRIGGER IF EXISTS release_issues_guard ON public.release_issues")
    op.execute("DROP FUNCTION IF EXISTS public.release_issues_block_delete()")
    op.execute("DROP FUNCTION IF EXISTS public.release_issues_guard()")
    op.drop_index("ix_release_issue_events_issue", table_name="release_issue_events")
    op.drop_table("release_issue_events")
    op.drop_index("ix_release_issues_tenant_project_status", table_name="release_issues")
    op.drop_table("release_issues")
