"""release_findings

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-15

Slice 23 — security/shortcut release findings (§13.4/§916-920/§24.1). Adds tenant-owned
``release_findings`` (RLS; SELECT/INSERT/UPDATE, no DELETE; type/severity/status CHECKs; a guard
trigger enforcing INSERT invariants, the category='other' rule, NULL resolution/acceptance metadata
on insert, per-transition column mutability, one-way lifecycle, critical-cannot-be-accepted, and
accepted-requires-a-usable-risk-acceptance-record) + append-only ``release_finding_events``
(SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked). Additive — no change to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"

_IMMUTABLE = (
    "id", "tenant_id", "project_id", "finding_type", "category", "severity", "summary",
    "detail", "source", "source_provenance", "detected_at", "created_at",
)
_SECURITY = ("authz", "injection", "secrets_exposure", "unsafe_tool", "supply_chain", "other")
_SHORTCUT = (
    "hardcoded_value", "static_response", "fake_integration", "disabled_validation",
    "weakened_tests", "error_swallowing", "placeholder_ui", "todo_in_required_path",
    "local_only_substitute", "acceptance_silently_skipped", "tests_check_implementation",
    "readiness_without_evidence", "other",
)


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "release_findings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("finding_type", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_provenance", sa.Text(),
                  server_default=sa.text("'caller_supplied_unverified'"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("risk_acceptance_record_id", sa.UUID(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint(
            "finding_type IN ('security','shortcut')",
            name=op.f("ck_release_findings_finding_type_valid"),
        ),
        sa.CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name=op.f("ck_release_findings_severity_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('open','resolved','false_positive','accepted','superseded')",
            name=op.f("ck_release_findings_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["risk_acceptance_record_id", "tenant_id"],
            ["risk_acceptance_records.id", "risk_acceptance_records.tenant_id"],
            name="risk_acceptance_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_release_findings_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_findings")),
        sa.UniqueConstraint("id", "tenant_id", name="uq_release_findings_id_tenant"),
    )
    op.create_index(
        "ix_release_findings_tenant_project_type_status",
        "release_findings", ["tenant_id", "project_id", "finding_type", "status"],
    )

    op.create_table(
        "release_finding_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("finding_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_id", "tenant_id"],
            ["release_findings.id", "release_findings.tenant_id"],
            name="finding_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_release_finding_events_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_release_finding_events")),
    )
    op.create_index(
        "ix_release_finding_events_finding",
        "release_finding_events", ["tenant_id", "finding_id", "created_at"],
    )

    immutable_checks = "\n            OR ".join(
        f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _IMMUTABLE
    )
    op.execute(
        f"""
        CREATE FUNCTION public.release_findings_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE ok int;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'open' THEN
                    RAISE EXCEPTION 'release_findings must be created with status=open';
                END IF;
                IF NEW.source_provenance <> 'caller_supplied_unverified' THEN
                    RAISE EXCEPTION 'release_findings source_provenance must be caller_supplied_unverified';
                END IF;
                IF NEW.risk_acceptance_record_id IS NOT NULL
                OR NEW.resolution_note IS NOT NULL
                OR NEW.resolved_at IS NOT NULL
                OR NEW.resolved_by IS NOT NULL THEN
                    RAISE EXCEPTION 'release_findings: resolution/acceptance metadata must be NULL at creation';
                END IF;
                IF (NEW.finding_type = 'security' AND NEW.category NOT IN ({_sql_list(_SECURITY)}))
                OR (NEW.finding_type = 'shortcut' AND NEW.category NOT IN ({_sql_list(_SHORTCUT)})) THEN
                    RAISE EXCEPTION 'release_findings: category % invalid for finding_type %',
                        NEW.category, NEW.finding_type;
                END IF;
                IF NEW.category = 'other'
                AND (NEW.summary IS NULL OR btrim(NEW.summary) = ''
                     OR NEW.detail IS NULL OR btrim(NEW.detail) = '') THEN
                    RAISE EXCEPTION 'release_findings: category=other requires non-empty summary and detail';
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'release_findings: identity/content/source fields are immutable';
                END IF;
                IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
                    -- status unchanged ⇒ no field may change (incl. updated_at): no out-of-band edits.
                    IF NEW.risk_acceptance_record_id IS DISTINCT FROM OLD.risk_acceptance_record_id
                    OR NEW.resolution_note IS DISTINCT FROM OLD.resolution_note
                    OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
                    OR NEW.resolved_by IS DISTINCT FROM OLD.resolved_by
                    OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
                        RAISE EXCEPTION 'release_findings: fields change only via a status transition';
                    END IF;
                ELSE
                    IF OLD.status <> 'open' THEN
                        RAISE EXCEPTION 'release_findings: terminal status % cannot transition', OLD.status;
                    END IF;
                    IF NEW.status NOT IN ('resolved','false_positive','accepted','superseded') THEN
                        RAISE EXCEPTION 'release_findings: invalid target status %', NEW.status;
                    END IF;
                    IF NEW.status = 'accepted' THEN
                        IF OLD.severity = 'critical' THEN
                            RAISE EXCEPTION 'release_findings: critical findings cannot be accepted';
                        END IF;
                        IF NEW.risk_acceptance_record_id IS NULL THEN
                            RAISE EXCEPTION 'release_findings: accepted requires a risk_acceptance_record_id';
                        END IF;
                        IF NEW.resolution_note IS NOT NULL
                        OR NEW.resolved_at IS NOT NULL
                        OR NEW.resolved_by IS NOT NULL THEN
                            RAISE EXCEPTION 'release_findings: accepted must not set resolution metadata';
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
                            RAISE EXCEPTION 'release_findings: no usable risk-acceptance record for this finding';
                        END IF;
                    ELSE
                        IF NEW.risk_acceptance_record_id IS NOT NULL THEN
                            RAISE EXCEPTION 'release_findings: only accepted may set risk_acceptance_record_id';
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
        CREATE TRIGGER release_findings_guard
            BEFORE INSERT OR UPDATE ON public.release_findings
            FOR EACH ROW EXECUTE FUNCTION public.release_findings_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.release_findings_block_delete() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'release_findings does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_findings_no_delete
            BEFORE DELETE ON public.release_findings
            FOR EACH ROW EXECUTE FUNCTION public.release_findings_block_delete()
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_findings_no_truncate
            BEFORE TRUNCATE ON public.release_findings
            FOR EACH STATEMENT EXECUTE FUNCTION public.release_findings_block_delete()
        """
    )

    op.execute(
        """
        CREATE FUNCTION public.release_finding_events_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'release_finding_events is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_finding_events_no_update_delete
            BEFORE UPDATE OR DELETE ON public.release_finding_events
            FOR EACH ROW EXECUTE FUNCTION public.release_finding_events_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_finding_events_no_truncate
            BEFORE TRUNCATE ON public.release_finding_events
            FOR EACH STATEMENT EXECUTE FUNCTION public.release_finding_events_block_mutation()
        """
    )

    for table in ("release_findings", "release_finding_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
    op.execute("REVOKE DELETE, TRUNCATE ON release_findings FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON release_findings TO uaid_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON release_finding_events FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON release_finding_events TO uaid_app")


def downgrade() -> None:
    for table in ("release_finding_events", "release_findings"):
        op.execute(f"REVOKE ALL ON {table} FROM uaid_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP TRIGGER IF EXISTS release_finding_events_no_truncate ON public.release_finding_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS release_finding_events_no_update_delete "
        "ON public.release_finding_events"
    )
    op.execute("DROP FUNCTION IF EXISTS public.release_finding_events_block_mutation()")
    op.execute("DROP TRIGGER IF EXISTS release_findings_no_truncate ON public.release_findings")
    op.execute("DROP TRIGGER IF EXISTS release_findings_no_delete ON public.release_findings")
    op.execute("DROP TRIGGER IF EXISTS release_findings_guard ON public.release_findings")
    op.execute("DROP FUNCTION IF EXISTS public.release_findings_block_delete()")
    op.execute("DROP FUNCTION IF EXISTS public.release_findings_guard()")
    op.drop_index("ix_release_finding_events_finding", table_name="release_finding_events")
    op.drop_table("release_finding_events")
    op.drop_index(
        "ix_release_findings_tenant_project_type_status", table_name="release_findings"
    )
    op.drop_table("release_findings")
