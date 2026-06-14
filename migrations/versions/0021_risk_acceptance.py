"""risk_acceptance

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-15

Slice 22 — go-live risk-acceptance records (§24.1/§27.10). Adds two tenant-owned tables:
``risk_acceptance_records`` (RLS; SELECT/INSERT/UPDATE, no DELETE; severity + status CHECKs;
guard trigger so only ``status``/``updated_at`` are mutable after creation; no DELETE/TRUNCATE)
and append-only ``risk_acceptance_events`` (RLS; SELECT/INSERT only; UPDATE/DELETE/TRUNCATE
blocked). Additive — no change to existing tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"

# Columns immutable after creation (everything except status + updated_at).
_IMMUTABLE = (
    "id", "tenant_id", "project_id", "release_id", "issue_id", "severity",
    "affected_requirements", "reason_for_acceptance", "business_impact",
    "compensating_controls", "rollback_or_mitigation_plan", "evidence_links",
    "required_follow_up_ticket", "included_in_release_notes", "expiry_date", "owner",
    "approver", "accepted_by", "approval_authority_source", "blocking_category",
    "approver_provenance", "created_at",
)


def upgrade() -> None:
    op.create_table(
        "risk_acceptance_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_id", sa.Text(), nullable=False),
        sa.Column("issue_id", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("affected_requirements", sa.dialects.postgresql.JSONB(),
                  server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("reason_for_acceptance", sa.Text(), nullable=False),
        sa.Column("business_impact", sa.Text(), nullable=False),
        sa.Column("compensating_controls", sa.dialects.postgresql.JSONB(),
                  server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("rollback_or_mitigation_plan", sa.Text(), nullable=False),
        sa.Column("evidence_links", sa.dialects.postgresql.JSONB(),
                  server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("required_follow_up_ticket", sa.Text(), nullable=False),
        sa.Column("included_in_release_notes", sa.Boolean(),
                  server_default=sa.text("false"), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("approver", sa.Text(), nullable=False),
        sa.Column("accepted_by", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("approval_authority_source", sa.Text(), nullable=False),
        sa.Column("blocking_category", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("approver_provenance", sa.Text(),
                  server_default=sa.text("'caller_supplied_unverified'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint(
            "severity IN ('low','medium','high','critical')",
            name=op.f("ck_risk_acceptance_records_severity_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active','expired','revoked','superseded')",
            name=op.f("ck_risk_acceptance_records_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_risk_acceptance_records_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_acceptance_records")),
        sa.UniqueConstraint("id", "tenant_id", name="uq_risk_acceptance_records_id_tenant"),
    )
    op.create_index(
        "ix_risk_acceptance_records_tenant_project_status",
        "risk_acceptance_records", ["tenant_id", "project_id", "status"],
    )

    op.create_table(
        "risk_acceptance_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id", "tenant_id"],
            ["risk_acceptance_records.id", "risk_acceptance_records.tenant_id"],
            name="record_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_risk_acceptance_events_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_acceptance_events")),
    )
    op.create_index(
        "ix_risk_acceptance_events_record",
        "risk_acceptance_events", ["tenant_id", "record_id", "created_at"],
    )

    # --- records guard: INSERT invariants + one-way status transitions + immutability ---
    # DB is the backstop even against direct runtime SQL (uaid_app has INSERT/UPDATE).
    immutable_checks = "\n            OR ".join(
        f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _IMMUTABLE
    )
    hard_refusals = ", ".join(
        f"'{c}'" for c in (
            "critical_security_blocker", "fake_done_finding",
            "missing_production_rollback", "missing_regulated_or_safety_authority",
        )
    )
    op.execute(
        f"""
        CREATE FUNCTION public.risk_acceptance_records_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'active' THEN
                    RAISE EXCEPTION 'risk_acceptance_records must be created with status=active';
                END IF;
                IF NEW.approver_provenance <> 'caller_supplied_unverified' THEN
                    RAISE EXCEPTION 'risk_acceptance_records approver_provenance must be caller_supplied_unverified';
                END IF;
                IF NEW.approval_authority_source <> 'approval_matrix' THEN
                    RAISE EXCEPTION 'risk_acceptance_records approval_authority_source must be approval_matrix';
                END IF;
                IF NEW.blocking_category IN ({hard_refusals}) THEN
                    RAISE EXCEPTION 'risk_acceptance_records: hard-refusal category cannot be accepted (%)',
                        NEW.blocking_category;
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'risk_acceptance_records: only status and updated_at are mutable';
                END IF;
                IF NEW.status IS DISTINCT FROM OLD.status THEN
                    IF OLD.status <> 'active'
                    OR NEW.status NOT IN ('expired', 'revoked', 'superseded') THEN
                        RAISE EXCEPTION 'risk_acceptance_records invalid status transition: % -> %',
                            OLD.status, NEW.status;
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
        CREATE TRIGGER risk_acceptance_records_guard
            BEFORE INSERT OR UPDATE ON public.risk_acceptance_records
            FOR EACH ROW EXECUTE FUNCTION public.risk_acceptance_records_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.risk_acceptance_records_block_delete() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'risk_acceptance_records does not allow DELETE/TRUNCATE';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER risk_acceptance_records_no_delete
            BEFORE DELETE ON public.risk_acceptance_records
            FOR EACH ROW EXECUTE FUNCTION public.risk_acceptance_records_block_delete()
        """
    )
    op.execute(
        """
        CREATE TRIGGER risk_acceptance_records_no_truncate
            BEFORE TRUNCATE ON public.risk_acceptance_records
            FOR EACH STATEMENT EXECUTE FUNCTION public.risk_acceptance_records_block_delete()
        """
    )

    # --- events append-only: block UPDATE/DELETE/TRUNCATE ------------------------
    op.execute(
        """
        CREATE FUNCTION public.risk_acceptance_events_block_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'risk_acceptance_events is append-only (no UPDATE/DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER risk_acceptance_events_no_update_delete
            BEFORE UPDATE OR DELETE ON public.risk_acceptance_events
            FOR EACH ROW EXECUTE FUNCTION public.risk_acceptance_events_block_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER risk_acceptance_events_no_truncate
            BEFORE TRUNCATE ON public.risk_acceptance_events
            FOR EACH STATEMENT EXECUTE FUNCTION public.risk_acceptance_events_block_mutation()
        """
    )

    # --- RLS + grants ------------------------------------------------------------
    for table in ("risk_acceptance_records", "risk_acceptance_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
    op.execute("REVOKE DELETE, TRUNCATE ON risk_acceptance_records FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT, UPDATE ON risk_acceptance_records TO uaid_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON risk_acceptance_events FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON risk_acceptance_events TO uaid_app")


def downgrade() -> None:
    for table in ("risk_acceptance_events", "risk_acceptance_records"):
        op.execute(f"REVOKE ALL ON {table} FROM uaid_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP TRIGGER IF EXISTS risk_acceptance_events_no_truncate ON public.risk_acceptance_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS risk_acceptance_events_no_update_delete "
        "ON public.risk_acceptance_events"
    )
    op.execute("DROP FUNCTION IF EXISTS public.risk_acceptance_events_block_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS risk_acceptance_records_no_truncate "
        "ON public.risk_acceptance_records"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS risk_acceptance_records_no_delete ON public.risk_acceptance_records"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS risk_acceptance_records_guard ON public.risk_acceptance_records"
    )
    op.execute("DROP FUNCTION IF EXISTS public.risk_acceptance_records_block_delete()")
    op.execute("DROP FUNCTION IF EXISTS public.risk_acceptance_records_guard()")
    op.drop_index("ix_risk_acceptance_events_record", table_name="risk_acceptance_events")
    op.drop_table("risk_acceptance_events")
    op.drop_index(
        "ix_risk_acceptance_records_tenant_project_status", table_name="risk_acceptance_records"
    )
    op.drop_table("risk_acceptance_records")
