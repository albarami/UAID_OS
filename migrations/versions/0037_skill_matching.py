"""skill matching engine

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-27

Slice 38 — Skill graph + Skill Matching Engine (§8). Five additive tables (Postgres-relational; no graph DB):
  GLOBAL (admin-curated, NOT RLS; uaid_app SELECT-only, admin-written via this migration / admin session — B8;
  immutable append-only):
    * skills                     — the §8.2 skill vocabulary (seeded with the 27 categories).
    * agent_skill_capabilities   — per-blueprint capability (append-only latest-wins).
    * agent_provided_skills      — FK-normalized provided skills (skill_id -> skills; unknown keys cannot persist, B3).
  TENANT-OWNED (RLS ENABLE+FORCE; uaid_app SELECT/INSERT; tenant-audited; append-only):
    * squad_manifests            — the §8.4 squad snapshot per build.
    * skill_matches              — the persisted §8.3 per-component score breakdown (B2).
Reuses agent_blueprints (Slice 6); no existing table changed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_GLOBAL = ("skills", "agent_skill_capabilities", "agent_provided_skills")
_TENANT = ("squad_manifests", "skill_matches")
_SKILL_CATEGORIES = (
    "product_strategy",
    "business_analysis",
    "ux_design",
    "frontend_engineering",
    "backend_engineering",
    "mobile_engineering",
    "data_engineering",
    "ai_engineering",
    "prompt_engineering",
    "model_evaluation",
    "knowledge_graph_engineering",
    "workflow_automation",
    "api_integration",
    "devops",
    "security",
    "privacy",
    "domain_analysis",
    "compliance_mapping",
    "financial_modeling",
    "geospatial_systems",
    "formula_verification",
    "document_generation",
    "qa_automation",
    "accessibility",
    "performance_engineering",
    "release_management",
    "incident_response",
)


def upgrade() -> None:
    cat_in = ", ".join(repr(c) for c in _SKILL_CATEGORIES)

    # --- skills (global vocab) ---------------------------------------------------
    op.create_table(
        "skills",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(r"key ~ '^[a-z][a-z0-9_]{1,63}$'", name=op.f("ck_skills_key_shape")),
        sa.CheckConstraint(f"category IN ({cat_in})", name=op.f("ck_skills_category_valid")),
        sa.CheckConstraint(
            "char_length(description) <= 1024", name=op.f("ck_skills_description_bounded")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("key", name="uq_skills_key"),
    )

    # --- agent_skill_capabilities (per blueprint) --------------------------------
    op.create_table(
        "agent_skill_capabilities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("blueprint_id", sa.UUID(), nullable=False),
        sa.Column("cost_latency_class", sa.Text(), nullable=False),
        sa.Column("provided_tools", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("domains", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cost_latency_class IN ('low','medium','high')", name=op.f("ck_asc_cost_class")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(provided_tools) = 'array' AND jsonb_array_length(provided_tools) <= 64",
            name=op.f("ck_asc_tools_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(domains) = 'array' AND jsonb_array_length(domains) <= 32",
            name=op.f("ck_asc_domains_array"),
        ),
        sa.ForeignKeyConstraint(
            ["blueprint_id"],
            ["agent_blueprints.id"],
            name=op.f("fk_asc_blueprint"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_skill_capabilities")),
    )
    op.create_index("ix_asc_blueprint", "agent_skill_capabilities", ["blueprint_id", "created_at"])

    # --- agent_provided_skills (FK-normalized — B3) ------------------------------
    op.create_table(
        "agent_provided_skills",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("capability_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("can_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["capability_id"],
            ["agent_skill_capabilities.id"],
            name=op.f("fk_aps_capability"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_aps_skill"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_provided_skills")),
        sa.UniqueConstraint("capability_id", "skill_id", name="uq_aps_capability_skill"),
    )

    # --- squad_manifests (tenant) ------------------------------------------------
    op.create_table(
        "squad_manifests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("work_unit_count", sa.Integer(), nullable=False),
        sa.Column("missing_skill_count", sa.Integer(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("built_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "work_unit_count BETWEEN 0 AND 128", name=op.f("ck_sqm_work_unit_count")
        ),
        sa.CheckConstraint("missing_skill_count >= 0", name=op.f("ck_sqm_missing_skill_count")),
        sa.CheckConstraint(
            "octet_length(manifest::text) <= 262144", name=op.f("ck_sqm_manifest_bounded")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sqm_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_squad_manifests")),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_squad_manifests_id_project_tenant"
        ),
    )
    op.create_index("ix_sqm_latest", "squad_manifests", ["tenant_id", "project_id", "created_at"])

    # --- skill_matches (tenant; persisted §8.3 breakdown — B2) -------------------
    comp = (
        "capability_match",
        "domain_fit",
        "tool_access_fit",
        "eval_performance",
        "reviewer_availability",
        "cost_latency_fit",
        "risk_penalty",
    )
    op.create_table(
        "skill_matches",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("manifest_id", sa.UUID(), nullable=False),
        sa.Column("work_unit_ref", sa.Text(), nullable=False),
        sa.Column("blueprint_id", sa.UUID(), nullable=False),
        *[sa.Column(c, sa.Numeric(7, 6), nullable=False) for c in comp],
        sa.Column("total_score", sa.Numeric(9, 6), nullable=False),
        sa.Column("eval_source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            r"work_unit_ref ~ '^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$'", name=op.f("ck_sm_work_unit_ref")
        ),
        *[sa.CheckConstraint(f"{c} BETWEEN 0 AND 1", name=op.f(f"ck_sm_{c}_unit")) for c in comp],
        sa.ForeignKeyConstraint(
            ["manifest_id", "project_id", "tenant_id"],
            ["squad_manifests.id", "squad_manifests.project_id", "squad_manifests.tenant_id"],
            name="manifest_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["blueprint_id"],
            ["agent_blueprints.id"],
            name=op.f("fk_sm_blueprint"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sm_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_matches")),
    )
    op.create_index("ix_sm_manifest", "skill_matches", ["tenant_id", "manifest_id"])

    # --- seed the §8.2 vocabulary (admin path) -----------------------------------
    op.execute(
        "INSERT INTO skills (key, category) VALUES "
        + ", ".join(f"({c!r}, {c!r})" for c in _SKILL_CATEGORIES)
    )

    # --- append-only / immutable block triggers (all 5 tables) -------------------
    for table in _GLOBAL + _TENANT:
        op.execute(
            f"""
            CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
            LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
            BEGIN
                RAISE EXCEPTION '{table} is append-only / immutable (no UPDATE/DELETE/TRUNCATE)';
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

    # --- grants: global = uaid_app SELECT-only (B8); tenant = SELECT/INSERT ------
    for table in _GLOBAL:
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT ON {table} TO uaid_app")
    for table in _TENANT:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    for table in _TENANT:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in _GLOBAL + _TENANT:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.drop_index("ix_sm_manifest", table_name="skill_matches")
    op.drop_table("skill_matches")
    op.drop_index("ix_sqm_latest", table_name="squad_manifests")
    op.drop_table("squad_manifests")
    op.drop_table("agent_provided_skills")
    op.drop_index("ix_asc_blueprint", table_name="agent_skill_capabilities")
    op.drop_table("agent_skill_capabilities")
    op.drop_table("skills")
