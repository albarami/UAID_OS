"""agent realization + broker decision schema

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-27

Slice 39 — agent realization + broker↔instance wiring. Additive:
  * agent_instances gains UNIQUE(id, project_id, tenant_id) — the composite-FK target (B6; verified absent).
  * agent_realizations (tenant, RLS, SELECT/INSERT only) — one per instance; INSERT guard locks
    qualification_status='unqualified' (B4; the 'qualified' transition is Slice 40).
  * agent_realization_reviewers (tenant, RLS, SELECT/INSERT only) — FK-backed reviewer linkage; a
    BEFORE-INSERT guard rejects a reviewer equal to the realized agent's ACTUAL blueprint (resolved via
    instance→version, B3 — no denormalized blueprint).
  * tool_calls.ck_tool_calls_decision_valid recreated to add denied_unknown_agent + denied_unqualified_agent (B2).
No Slice-6 column/data/trigger change (only the additive agent_instances UNIQUE).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TENANT = ("agent_realizations", "agent_realization_reviewers")
_DECISIONS_7 = (
    "allowed_unverified_identity",
    "needs_approval",
    "needs_authenticated_approval",
    "denied_unknown_tool",
    "denied_invalid_params",
    "denied_not_allowlisted",
    "denied_policy",
)
_DECISIONS_9 = _DECISIONS_7 + ("denied_unknown_agent", "denied_unqualified_agent")


def _decision_check(values):
    return "decision IN (" + ", ".join(repr(v) for v in values) + ")"


def upgrade() -> None:
    # --- B6: composite-FK target on the Slice-6 instance table (additive) ---------
    op.create_unique_constraint(
        "uq_agent_instances_id_project_tenant", "agent_instances", ["id", "project_id", "tenant_id"]
    )

    # --- agent_realizations ------------------------------------------------------
    op.create_table(
        "agent_realizations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("qualification_status", sa.Text(), nullable=False),
        sa.Column("realized_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "qualification_status IN ('unqualified', 'qualified')",
            name=op.f("ck_agent_realizations_qualification_status_valid"),
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
            name=op.f("fk_agent_realizations_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_realizations")),
        sa.UniqueConstraint("instance_id", name="uq_agent_realizations_instance"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_agent_realizations_id_project_tenant"
        ),
    )
    op.create_index(
        "ix_agent_realizations_instance", "agent_realizations", ["tenant_id", "instance_id"]
    )

    # --- agent_realization_reviewers ---------------------------------------------
    op.create_table(
        "agent_realization_reviewers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("realization_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_blueprint_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["realization_id", "project_id", "tenant_id"],
            [
                "agent_realizations.id",
                "agent_realizations.project_id",
                "agent_realizations.tenant_id",
            ],
            name="realization_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_blueprint_id"],
            ["agent_blueprints.id"],
            name="reviewer_blueprint",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_arr_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_realization_reviewers")),
        sa.UniqueConstraint(
            "realization_id", "reviewer_blueprint_id", name="uq_agent_realization_reviewers_pair"
        ),
    )
    op.create_index(
        "ix_agent_realization_reviewers_realization",
        "agent_realization_reviewers",
        ["tenant_id", "realization_id"],
    )

    # --- B2: extend the tool_calls decision CHECK (7 -> 9) ------------------------
    # NB: pass the bare token; the naming convention expands it to ck_tool_calls_decision_valid.
    op.drop_constraint("decision_valid", "tool_calls", type_="check")
    op.create_check_constraint("decision_valid", "tool_calls", _decision_check(_DECISIONS_9))

    # --- B4 guard: agent_realizations INSERT locks 'unqualified' ------------------
    op.execute(
        """
        CREATE FUNCTION public.agent_realizations_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF NEW.qualification_status <> 'unqualified' THEN
                RAISE EXCEPTION 'agent_realizations: qualification_status must be unqualified on INSERT '
                    '(the qualified transition is Slice 40)';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER agent_realizations_guard BEFORE INSERT ON public.agent_realizations "
        "FOR EACH ROW EXECUTE FUNCTION public.agent_realizations_guard()"
    )

    # --- B3 guard: reviewer must NOT be the realized agent's ACTUAL blueprint -----
    op.execute(
        """
        CREATE FUNCTION public.agent_realization_reviewers_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE realized_bp uuid;
        BEGIN
            SELECT v.blueprint_id INTO realized_bp
            FROM public.agent_realizations r
            JOIN public.agent_instances i ON i.id = r.instance_id
            JOIN public.agent_versions v ON v.id = i.version_id
            WHERE r.id = NEW.realization_id;
            IF NEW.reviewer_blueprint_id = realized_bp THEN
                RAISE EXCEPTION 'agent_realization_reviewers: reviewer cannot be the realized agent '
                    'blueprint (self-review, section 2.2)';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER agent_realization_reviewers_guard BEFORE INSERT ON public.agent_realization_reviewers "
        "FOR EACH ROW EXECUTE FUNCTION public.agent_realization_reviewers_guard()"
    )

    # --- append-only block triggers + RLS + grants (both tenant tables) ----------
    for table in _TENANT:
        op.execute(
            f"""
            CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
            LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
            BEGIN
                RAISE EXCEPTION '{table} is append-only (no UPDATE/DELETE/TRUNCATE in Slice 39)';
            END
            $fn$
            """
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    op.drop_constraint("decision_valid", "tool_calls", type_="check")
    op.create_check_constraint("decision_valid", "tool_calls", _decision_check(_DECISIONS_7))
    for table in _TENANT:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS agent_realization_reviewers_guard ON public.agent_realization_reviewers"
    )
    op.execute("DROP FUNCTION IF EXISTS public.agent_realization_reviewers_guard()")
    op.execute("DROP TRIGGER IF EXISTS agent_realizations_guard ON public.agent_realizations")
    op.execute("DROP FUNCTION IF EXISTS public.agent_realizations_guard()")
    op.drop_index(
        "ix_agent_realization_reviewers_realization", table_name="agent_realization_reviewers"
    )
    op.drop_table("agent_realization_reviewers")
    op.drop_index("ix_agent_realizations_instance", table_name="agent_realizations")
    op.drop_table("agent_realizations")
    op.drop_constraint("uq_agent_instances_id_project_tenant", "agent_instances", type_="unique")
