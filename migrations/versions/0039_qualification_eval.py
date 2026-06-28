"""agent qualification eval

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-28

Slice 40 — the unqualified→qualified transition under a deterministic, DB-non-fakeable eval gate.
  * archetype_evals — GLOBAL controlled library (SELECT-only for uaid_app; immutable append-only); seeded 11.
  * qualification_runs — tenant, RLS, SELECT/INSERT only; aggregate_score/verdict GENERATED; counts/coverage
    deferred-trigger-verified against the FK child cases (B3 — a fake `passed` is rejected).
  * qualification_case_results — tenant, RLS, SELECT/INSERT only; the FK children.
  * agent_realizations — ADD updated_at + qualified_via_run_id (composite FK→qualification_runs); the 0038
    block trigger is CREATE OR REPLACE'd to allow ONLY the one-way unqualified→qualified UPDATE with a
    passing-run backstop; column-level GRANT UPDATE(qualification_status, updated_at, qualified_via_run_id).
Deterministic only — no LLM, no agent run. No A5/readiness change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.qualification_run import AGGREGATE_EXPR, VERDICT_EXPR

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TENANT = ("qualification_runs", "qualification_case_results")
# Must match registry.ARCHETYPES (a test asserts no drift). 'ai_evaluation' is the runtime value (B2).
_ARCHETYPES = (
    "builder",
    "reviewer",
    "security_reviewer",
    "data_engineer",
    "domain_reasoner",
    "prompt_engineer",
    "knowledge_graph_rag",
    "ai_evaluation",
    "integration_connector",
    "deployment_sre",
    "evidence_auditor",
)
_ALL_CATEGORIES = ["positive", "negative", "edge", "adversarial", "incomplete"]


def _seed_rows():
    # §9.5.1 thresholds: most 0.850; reviewer 0.900; evidence_auditor 0.950. zero-critical for all.
    spec = {
        "builder": (
            0.850,
            "Implement features, fix bugs, preserve behavior, avoid shortcuts.",
            "Reference implementations, accepted PRs, deterministic tests, seeded defect corpora.",
            "Correctness, maintainability, test coverage, no-fake-done.",
            "quarterly + after major model/framework/tool change",
        ),
        "reviewer": (
            0.900,
            "Detect defects, missing criteria, weak tests, fake integrations, unsupported claims.",
            "Planted-defect corpus and expert-labeled review reports.",
            "Critical-defect recall, specificity, evidence use, no rubber-stamping.",
            "monthly + after reviewer-miss incident",
        ),
        "security_reviewer": (
            0.850,
            "Detect authz flaws, prompt injection, secrets exposure, unsafe tools, supply-chain risk.",
            "Security fixtures, known vulnerability patterns, red-team cases.",
            "Severity classification, exploit clarity, remediation quality.",
            "monthly + when threat library changes",
        ),
        "data_engineer": (
            0.850,
            "Validate schemas, pipelines, lineage, data quality, retention, migrations.",
            "Data contracts, synthetic/approved datasets, lineage fixtures.",
            "Data integrity, reproducibility, loss prevention, lineage accuracy.",
            "quarterly + after data-stack change",
        ),
        "domain_reasoner": (
            0.850,
            "Apply domain rules, terminology, authorities, prohibited assumptions.",
            "Domain pack fixtures, authority-source mappings, expert cases.",
            "Source fidelity, boundary discipline, safe blocker behavior.",
            "per domain-pack release",
        ),
        "prompt_engineer": (
            0.850,
            "Create constrained agent/reviewer prompts and anti-shortcut instructions.",
            "Prompt evals, injection tests, ambiguity tests, policy-bypass cases.",
            "Clarity, tool discipline, failure-mode coverage, injection resistance.",
            "monthly + after prompt-template change",
        ),
        "knowledge_graph_rag": (
            0.850,
            "Build entity/relation structures, retrieval tests, provenance-backed responses.",
            "Graph fixtures, retrieval gold sets, provenance benchmarks.",
            "Entity/relation precision, retrieval relevance, citation grounding.",
            "per corpus/domain refresh",
        ),
        "ai_evaluation": (
            0.850,
            "Design rubrics, sampling, judge lineages, IRR checks, adversarial sets.",
            "Audited evaluation plans and calibration fixtures.",
            "Oracle validity, sampling adequacy, bias controls, disagreement handling.",
            "quarterly + after model-family change",
        ),
        "integration_connector": (
            0.850,
            "Build connector contracts, auth, rate limits, error handling, audit logging.",
            "Sandbox APIs, mocked failure modes, connector contract tests.",
            "Contract compliance, least privilege, error handling, observability.",
            "per connector/API version change",
        ),
        "deployment_sre": (
            0.850,
            "Build CI/CD, infra, rollback, monitoring, backup/restore, failure drills.",
            "Reference deployments, failure-injection scenarios, runbooks.",
            "Idempotency, rollback, observability, recovery, cost discipline.",
            "monthly + after runtime/cloud change",
        ),
        "evidence_auditor": (
            0.950,
            "Assemble and validate evidence packs.",
            "Complete/incomplete evidence fixtures and schema tests.",
            "Traceability, export validity, missing-evidence detection, tamper evidence.",
            "monthly + after evidence-schema change",
        ),
    }
    rows = []
    for arch in _ARCHETYPES:
        thr, tasks, gold, rubric, refresh = spec[arch]
        rows.append(
            {
                "archetype": arch,
                "eval_version": "v1",
                "representative_task_set": [tasks],
                "gold_answer_source": [gold],
                "scoring_rubric": [rubric],
                "min_aggregate_score": thr,
                "require_zero_critical": True,
                "min_cases": 5,
                "required_categories": list(_ALL_CATEGORIES),
                "refresh_policy": refresh,
            }
        )
    return rows


def upgrade() -> None:
    # --- archetype_evals (GLOBAL, SELECT-only, append-only) ----------------------
    op.create_table(
        "archetype_evals",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("archetype", sa.Text(), nullable=False),
        sa.Column("eval_version", sa.Text(), nullable=False),
        sa.Column("representative_task_set", postgresql.JSONB(), nullable=False),
        sa.Column("gold_answer_source", postgresql.JSONB(), nullable=False),
        sa.Column("scoring_rubric", postgresql.JSONB(), nullable=False),
        sa.Column("min_aggregate_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("require_zero_critical", sa.Boolean(), nullable=False),
        sa.Column("min_cases", sa.Integer(), nullable=False),
        sa.Column("required_categories", postgresql.JSONB(), nullable=False),
        sa.Column("refresh_policy", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "archetype IN (" + ", ".join(repr(a) for a in _ARCHETYPES) + ")",
            name=op.f("ck_archetype_evals_archetype_valid"),
        ),
        sa.CheckConstraint(
            "min_aggregate_score >= 0 AND min_aggregate_score <= 1",
            name=op.f("ck_archetype_evals_min_aggregate_score_range"),
        ),
        sa.CheckConstraint("min_cases >= 1", name=op.f("ck_archetype_evals_min_cases_positive")),
        sa.CheckConstraint(
            "jsonb_typeof(representative_task_set) = 'array' AND jsonb_typeof(gold_answer_source) = 'array' "
            "AND jsonb_typeof(scoring_rubric) = 'array' AND jsonb_typeof(required_categories) = 'array'",
            name=op.f("ck_archetype_evals_json_arrays"),
        ),
        sa.CheckConstraint(
            "jsonb_array_length(required_categories) >= 1 AND required_categories <@ "
            '\'["positive", "negative", "edge", "adversarial", "incomplete"]\'::jsonb',
            name=op.f("ck_archetype_evals_required_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archetype_evals")),
        sa.UniqueConstraint(
            "archetype", "eval_version", name="uq_archetype_evals_archetype_version"
        ),
    )
    seed_tbl = sa.table(
        "archetype_evals",
        sa.column("archetype", sa.Text),
        sa.column("eval_version", sa.Text),
        sa.column("representative_task_set", postgresql.JSONB),
        sa.column("gold_answer_source", postgresql.JSONB),
        sa.column("scoring_rubric", postgresql.JSONB),
        sa.column("min_aggregate_score", sa.Numeric),
        sa.column("require_zero_critical", sa.Boolean),
        sa.column("min_cases", sa.Integer),
        sa.column("required_categories", postgresql.JSONB),
        sa.column("refresh_policy", sa.Text),
    )
    op.bulk_insert(seed_tbl, _seed_rows())

    # --- qualification_runs (tenant; GENERATED aggregate/verdict) ----------------
    op.create_table(
        "qualification_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("realization_id", sa.UUID(), nullable=False),
        sa.Column("archetype_eval_id", sa.UUID(), nullable=False),
        sa.Column("archetype", sa.Text(), nullable=False),
        sa.Column("eval_version", sa.Text(), nullable=False),
        sa.Column("min_aggregate_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("require_zero_critical", sa.Boolean(), nullable=False),
        sa.Column("min_cases", sa.Integer(), nullable=False),
        sa.Column("required_categories", postgresql.JSONB(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("critical_failure_count", sa.Integer(), nullable=False),
        sa.Column("coverage_complete", sa.Boolean(), nullable=False),
        sa.Column(
            "aggregate_score",
            sa.Numeric(),
            sa.Computed(AGGREGATE_EXPR, persisted=True),
            nullable=False,
        ),
        sa.Column("verdict", sa.Text(), sa.Computed(VERDICT_EXPR, persisted=True), nullable=False),
        sa.Column(
            "provenance",
            sa.Text(),
            server_default=sa.text("'caller_supplied_unverified'"),
            nullable=False,
        ),
        sa.Column("evaluated_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "passed_cases >= 0 AND total_cases >= 0 AND critical_failure_count >= 0 AND passed_cases <= total_cases",
            name=op.f("ck_qualification_runs_counts_sane"),
        ),
        sa.CheckConstraint(
            "provenance = 'caller_supplied_unverified'",
            name=op.f("ck_qualification_runs_provenance_unverified"),
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
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_qualification_runs_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["archetype_eval_id"],
            ["archetype_evals.id"],
            name="archetype_eval",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_runs")),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_qualification_runs_id_project_tenant"
        ),
    )
    op.create_index(
        "ix_qualification_runs_realization", "qualification_runs", ["tenant_id", "realization_id"]
    )

    # --- qualification_case_results (tenant; the FK children) --------------------
    op.create_table(
        "qualification_case_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("case_ref", sa.Text(), nullable=False),
        sa.Column("case_category", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "case_category IN ('positive','negative','edge','adversarial','incomplete')",
            name=op.f("ck_qualification_case_results_case_category_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "qualification_runs.id",
                "qualification_runs.project_id",
                "qualification_runs.tenant_id",
            ],
            name="run_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_qcr_tenant"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_case_results")),
    )
    op.create_index(
        "ix_qualification_case_results_run", "qualification_case_results", ["tenant_id", "run_id"]
    )

    # --- B3: deferred children-verify (counts + coverage must match the FK cases) -
    op.execute(
        """
        CREATE FUNCTION public.verify_qualification_run_counts(p_run uuid) RETURNS void
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE
            r record;
            a_total int; a_passed int; a_critical int; a_coverage boolean;
        BEGIN
            SELECT total_cases, passed_cases, critical_failure_count, coverage_complete, required_categories
              INTO r FROM public.qualification_runs WHERE id = p_run;
            IF NOT FOUND THEN RETURN; END IF;
            SELECT count(*), count(*) FILTER (WHERE passed),
                   count(*) FILTER (WHERE is_critical AND NOT passed)
              INTO a_total, a_passed, a_critical
              FROM public.qualification_case_results WHERE run_id = p_run;
            SELECT NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(r.required_categories) AS req
                WHERE req NOT IN (SELECT case_category FROM public.qualification_case_results WHERE run_id = p_run)
            ) INTO a_coverage;
            IF r.total_cases <> a_total OR r.passed_cases <> a_passed
               OR r.critical_failure_count <> a_critical OR r.coverage_complete <> a_coverage THEN
                RAISE EXCEPTION 'qualification_run counts/coverage do not match the recorded child cases';
            END IF;
        END
        $fn$
        """
    )
    for tbl, col in (("qualification_runs", "id"), ("qualification_case_results", "run_id")):
        op.execute(
            f"""
            CREATE FUNCTION public.{tbl}_verify_trg() RETURNS trigger
            LANGUAGE plpgsql AS $fn$
            BEGIN
                PERFORM public.verify_qualification_run_counts(NEW.{col});
                RETURN NULL;
            END
            $fn$
            """
        )
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {tbl}_verify AFTER INSERT ON public.{tbl} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.{tbl}_verify_trg()"
        )

    # --- B1: snapshot + archetype integrity (BEFORE INSERT) ----------------------
    # The GENERATED verdict reads the snapshot columns, so they MUST equal the referenced controlled
    # archetype_evals row, and the eval's archetype MUST equal the realization's actual blueprint
    # archetype — otherwise direct SQL could weaken the threshold/categories and fake a pass.
    op.execute(
        """
        CREATE FUNCTION public.qualification_runs_snapshot_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE ae record; real_archetype text;
        BEGIN
            SELECT archetype, eval_version, min_aggregate_score, require_zero_critical, min_cases,
                   required_categories
              INTO ae FROM public.archetype_evals WHERE id = NEW.archetype_eval_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'qualification_runs: unknown archetype_eval_id';
            END IF;
            IF NEW.archetype <> ae.archetype OR NEW.eval_version <> ae.eval_version
               OR NEW.min_aggregate_score <> ae.min_aggregate_score
               OR NEW.require_zero_critical <> ae.require_zero_critical
               OR NEW.min_cases <> ae.min_cases
               OR NEW.required_categories <> ae.required_categories THEN
                RAISE EXCEPTION 'qualification_runs: snapshot columns must equal the referenced archetype_evals row';
            END IF;
            SELECT b.archetype INTO real_archetype
              FROM public.agent_realizations r
              JOIN public.agent_instances i ON i.id = r.instance_id
              JOIN public.agent_versions v ON v.id = i.version_id
              JOIN public.agent_blueprints b ON b.id = v.blueprint_id
             WHERE r.id = NEW.realization_id;
            IF real_archetype IS NULL OR real_archetype <> NEW.archetype THEN
                RAISE EXCEPTION 'qualification_runs: archetype must match the realization blueprint archetype';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER qualification_runs_snapshot_guard BEFORE INSERT ON public.qualification_runs "
        "FOR EACH ROW EXECUTE FUNCTION public.qualification_runs_snapshot_guard()"
    )

    # --- append-only block triggers + RLS + grants (tenant tables) ---------------
    for table in _TENANT:
        _append_only_block(table)
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")

    # archetype_evals: GLOBAL, immutable append-only, SELECT-only (trust-zone) ----
    _append_only_block("archetype_evals")
    op.execute("REVOKE ALL ON archetype_evals FROM PUBLIC")
    op.execute("GRANT SELECT ON archetype_evals TO uaid_app")

    # --- agent_realizations: add columns + transition relax + grant --------------
    op.add_column(
        "agent_realizations", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("agent_realizations", sa.Column("qualified_via_run_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "qualified_run_project_tenant",
        "agent_realizations",
        "qualification_runs",
        ["qualified_via_run_id", "project_id", "tenant_id"],
        ["id", "project_id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.agent_realizations_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF OLD.qualification_status = 'unqualified' AND NEW.qualification_status = 'qualified'
                   AND NEW.id = OLD.id AND NEW.tenant_id = OLD.tenant_id AND NEW.project_id = OLD.project_id
                   AND NEW.instance_id = OLD.instance_id AND NEW.realized_by = OLD.realized_by
                   AND NEW.created_at = OLD.created_at THEN
                    IF NEW.qualified_via_run_id IS NULL THEN
                        RAISE EXCEPTION 'agent_realizations: qualification requires qualified_via_run_id';
                    END IF;
                    PERFORM 1 FROM public.qualification_runs q
                      WHERE q.id = NEW.qualified_via_run_id AND q.realization_id = NEW.id
                        AND q.tenant_id = NEW.tenant_id AND q.verdict = 'passed';
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'agent_realizations: qualified_via_run_id must reference a PASSING run for this realization';
                    END IF;
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'agent_realizations: only a one-way unqualified->qualified transition is allowed';
            END IF;
            RAISE EXCEPTION 'agent_realizations is append-only (no DELETE/TRUNCATE)';
        END
        $fn$
        """
    )
    op.execute(
        "GRANT UPDATE (qualification_status, updated_at, qualified_via_run_id) ON agent_realizations TO uaid_app"
    )


def _append_only_block(table: str) -> None:
    op.execute(
        f"""
        CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION '{table} is append-only (no UPDATE/DELETE/TRUNCATE)';
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


def downgrade() -> None:
    # restore the 0038 strict agent_realizations block + drop the grant/columns/fk
    op.execute(
        "REVOKE UPDATE (qualification_status, updated_at, qualified_via_run_id) ON agent_realizations FROM uaid_app"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.agent_realizations_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        BEGIN
            RAISE EXCEPTION 'agent_realizations is append-only (no UPDATE/DELETE/TRUNCATE in Slice 39)';
        END
        $fn$
        """
    )
    op.drop_constraint("qualified_run_project_tenant", "agent_realizations", type_="foreignkey")
    op.drop_column("agent_realizations", "qualified_via_run_id")
    op.drop_column("agent_realizations", "updated_at")
    for table in ("archetype_evals",) + _TENANT:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
    for table in _TENANT:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_verify ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_verify_trg()")
    op.execute(
        "DROP TRIGGER IF EXISTS qualification_runs_snapshot_guard ON public.qualification_runs"
    )
    op.execute("DROP FUNCTION IF EXISTS public.qualification_runs_snapshot_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_qualification_run_counts(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.archetype_evals_block_dml()")
    op.execute("DROP FUNCTION IF EXISTS public.qualification_case_results_block_dml()")
    op.execute("DROP FUNCTION IF EXISTS public.qualification_runs_block_dml()")
    op.drop_index("ix_qualification_case_results_run", table_name="qualification_case_results")
    op.drop_table("qualification_case_results")
    op.drop_index("ix_qualification_runs_realization", table_name="qualification_runs")
    op.drop_table("qualification_runs")
    op.drop_table("archetype_evals")
