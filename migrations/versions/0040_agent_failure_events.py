"""agent failure events (§9.6 replacement policy store)

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-02

Slice 41 — §9.6 agent replacement / failure policy. Purely additive: ONE new table.
  * agent_failure_events (tenant, RLS ENABLE+FORCE, SELECT/INSERT only — append-only block
    triggers): REPORTED (caller-supplied, unverified) §9.6 failure-pattern classifications
    per agent instance. Declarative backstops: the 8-pattern + 4-severity enums, the B1
    provenance CHECK locked to 'caller_supplied_unverified', B3 char_length bounds on every
    user text field, and the composite FK (instance_id, project_id, tenant_id) →
    agent_instances (reuses the Slice-39 uq_agent_instances_id_project_tenant target).
No existing table/column/trigger/grant changes. The replacement decision is compute-on-read
(OD-3) — no decisions table. Nothing here executes or authorizes anything (OD-1).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLE = "agent_failure_events"

_FAILURE_PATTERNS = (
    "missing_skill",
    "weak_instructions",
    "wrong_tools",
    "poor_model_performance",
    "context_overload",
    "repeated_reviewer_rejection",
    "safety_authority_violation",
    "persistent_inability",
)
_SEVERITIES = ("low", "medium", "high", "critical")


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("failure_pattern", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "source_provenance",
            sa.Text(),
            server_default=sa.text("'caller_supplied_unverified'"),
            nullable=False,
        ),
        sa.Column("evidence_ref", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("reported_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            _in("failure_pattern", _FAILURE_PATTERNS),
            name=op.f("ck_agent_failure_events_failure_pattern_valid"),
        ),
        sa.CheckConstraint(
            _in("severity", _SEVERITIES), name=op.f("ck_agent_failure_events_severity_valid")
        ),
        # B1 — the provenance tier is LOCKED to the unverified tier this slice.
        sa.CheckConstraint(
            "source_provenance IN ('caller_supplied_unverified')",
            name=op.f("ck_agent_failure_events_source_provenance_valid"),
        ),
        # B3 — every user text field bounded (NULL passes on the optional fields).
        sa.CheckConstraint(
            "char_length(source) BETWEEN 1 AND 100",
            name=op.f("ck_agent_failure_events_source_len"),
        ),
        sa.CheckConstraint(
            "char_length(evidence_ref) BETWEEN 1 AND 200",
            name=op.f("ck_agent_failure_events_evidence_ref_len"),
        ),
        sa.CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 2000",
            name=op.f("ck_agent_failure_events_summary_len"),
        ),
        sa.CheckConstraint(
            "char_length(detail) BETWEEN 1 AND 8000",
            name=op.f("ck_agent_failure_events_detail_len"),
        ),
        sa.CheckConstraint(
            "char_length(reported_by) BETWEEN 1 AND 200",
            name=op.f("ck_agent_failure_events_reported_by_len"),
        ),
        sa.ForeignKeyConstraint(
            ["instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            name="instance_project_tenant",
            ondelete="RESTRICT",
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
            name=op.f("fk_agent_failure_events_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_failure_events")),
    )
    op.create_index(
        "ix_agent_failure_events_instance", _TABLE, ["tenant_id", "instance_id", "created_at"]
    )

    # --- append-only block triggers + RLS + grants (the 0038/0039 pattern) --------
    op.execute(
        f"""
        CREATE FUNCTION public.{_TABLE}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION '{_TABLE} is append-only (no UPDATE/DELETE/TRUNCATE in Slice 41)';
        END
        $fn$
        """
    )
    op.execute(
        f"CREATE TRIGGER {_TABLE}_no_update_delete BEFORE UPDATE OR DELETE ON public.{_TABLE} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{_TABLE}_block_dml()"
    )
    op.execute(
        f"CREATE TRIGGER {_TABLE}_no_truncate BEFORE TRUNCATE ON public.{_TABLE} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{_TABLE}_block_dml()"
    )
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {_TABLE} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON {_TABLE} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON {_TABLE} TO uaid_app")


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(f"DROP TRIGGER IF EXISTS {_TABLE}_no_truncate ON public.{_TABLE}")
    op.execute(f"DROP TRIGGER IF EXISTS {_TABLE}_no_update_delete ON public.{_TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS public.{_TABLE}_block_dml()")
    op.drop_index("ix_agent_failure_events_instance", table_name=_TABLE)
    op.drop_table(_TABLE)
