"""test oracle execution subsystem

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.test_oracle_run import AGGREGATE_PASS_RATE_EXPR, RUN_VERDICT_EXPR
from app.models.test_result import RESULT_PASSED_EXPR, TYPE_SHAPE_CHECK

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLES = ("test_oracle_runs", "test_results")


def upgrade() -> None:
    op.create_table(
        "test_oracle_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("oracle_artifact_id", sa.UUID(), nullable=False),
        sa.Column("definition_hash", sa.Text(), nullable=False),
        sa.Column("definition_schema_version", sa.Text(), nullable=False),
        sa.Column("repo_binding_hash", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.Text(), nullable=False),
        sa.Column("oracle_type", sa.Text(), nullable=False),
        sa.Column("runner_key", sa.Text(), nullable=False),
        sa.Column("runner_version", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("observation_provenance", sa.Text(), nullable=False),
        sa.Column("execution_provenance", sa.Text(), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("required_sample_size", sa.Integer(), nullable=False),
        sa.Column("minimum_pass_rate", sa.Numeric(8, 6), nullable=False),
        sa.Column("irr_minimum", sa.Numeric(8, 6), nullable=True),
        sa.Column(
            "human_review_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("reported_result_count", sa.Integer(), nullable=False),
        sa.Column("reported_passed_count", sa.Integer(), nullable=False),
        sa.Column("reported_distinct_case_count", sa.Integer(), nullable=False),
        sa.Column("reported_evaluator_lineage_count", sa.Integer(), nullable=False),
        sa.Column("reported_irr", sa.Numeric(8, 6), nullable=True),
        sa.Column("reported_unresolved_disagreement_count", sa.Integer(), nullable=False),
        sa.Column(
            "aggregate_pass_rate",
            sa.Numeric(),
            sa.Computed(AGGREGATE_PASS_RATE_EXPR, persisted=True),
            nullable=False,
        ),
        sa.Column(
            "verdict",
            sa.Text(),
            sa.Computed(RUN_VERDICT_EXPR, persisted=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "definition_schema_version = 'slice43.oracle.v1'", name="ck_tor_schema_version"
        ),
        sa.CheckConstraint(
            "oracle_type IN ('specified','reference','judgment')", name="ck_tor_oracle_type"
        ),
        sa.CheckConstraint(
            "execution_status IN ('succeeded','failed','refused')",
            name="ck_tor_execution_status",
        ),
        sa.CheckConstraint(
            "observation_provenance IN "
            "('caller_supplied_unverified','connector_verified_ci')",
            name="ck_tor_observation_provenance",
        ),
        sa.CheckConstraint(
            "execution_provenance IN ('system_executed','system_attempted')",
            name="ck_tor_execution_provenance",
        ),
        sa.CheckConstraint(
            "definition_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_tor_definition_hash"
        ),
        sa.CheckConstraint(
            "repo_binding_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_tor_repo_binding_hash"
        ),
        sa.CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="ck_tor_commit_sha"),
        sa.CheckConstraint(
            "required_sample_size BETWEEN 1 AND 1000", name="ck_tor_sample_size"
        ),
        sa.CheckConstraint("minimum_pass_rate BETWEEN 0 AND 1", name="ck_tor_pass_rate"),
        sa.CheckConstraint(
            "reported_result_count >= 0 AND reported_passed_count >= 0 "
            "AND reported_passed_count <= reported_result_count "
            "AND reported_distinct_case_count >= 0 "
            "AND reported_evaluator_lineage_count >= 0 "
            "AND reported_unresolved_disagreement_count >= 0",
            name="ck_tor_counts_sane",
        ),
        sa.CheckConstraint(
            "(execution_status = 'succeeded' AND oracle_type = 'judgment' "
            "AND irr_minimum IS NOT NULL AND reported_irr IS NOT NULL "
            "AND reported_evaluator_lineage_count >= 2) OR "
            "(execution_status IN ('failed','refused') AND oracle_type = 'judgment' "
            "AND irr_minimum IS NOT NULL AND reported_irr IS NULL "
            "AND reported_evaluator_lineage_count = 0 "
            "AND reported_unresolved_disagreement_count = 0) OR "
            "(oracle_type <> 'judgment' AND irr_minimum IS NULL AND reported_irr IS NULL "
            "AND reported_evaluator_lineage_count = 0 "
            "AND reported_unresolved_disagreement_count = 0 AND NOT human_review_required)",
            name="ck_tor_judgment_shape",
        ),
        sa.CheckConstraint(
            "(execution_status = 'succeeded' AND failure_code IS NULL "
            "AND execution_provenance = 'system_executed' AND reported_result_count > 0) OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL "
            "AND execution_provenance = 'system_attempted' AND reported_result_count = 0 "
            "AND reported_passed_count = 0 AND reported_distinct_case_count = 0 "
            "AND reported_evaluator_lineage_count = 0 "
            "AND reported_unresolved_disagreement_count = 0)",
            name="ck_tor_execution_shape",
        ),
        sa.CheckConstraint(
            "octet_length(runner_key) BETWEEN 1 AND 128 AND btrim(runner_key) <> '' "
            "AND octet_length(runner_version) BETWEEN 1 AND 64 "
            "AND btrim(runner_version) <> ''",
            name="ck_tor_runner_bounds",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (octet_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code) <> '')",
            name="ck_tor_failure_code_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oracle_artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            name="oracle_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_tor_tenant", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_oracle_runs"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_tor_id_project_tenant"),
    )
    op.create_index(
        "ix_test_oracle_runs_latest",
        "test_oracle_runs",
        [
            "tenant_id",
            "project_id",
            "oracle_artifact_id",
            "repo_binding_hash",
            "commit_sha",
            "created_at",
        ],
    )

    op.create_table(
        "test_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("test_oracle_run_id", sa.UUID(), nullable=False),
        sa.Column("case_ref", sa.Text(), nullable=False),
        sa.Column("sample_class", sa.Text(), nullable=True),
        sa.Column("result_kind", sa.Text(), nullable=False),
        sa.Column("expected_digest", sa.Text(), nullable=True),
        sa.Column("observed_digest", sa.Text(), nullable=True),
        sa.Column("reference_digest", sa.Text(), nullable=True),
        sa.Column("observed_numeric", sa.Numeric(30, 12), nullable=True),
        sa.Column("reference_numeric", sa.Numeric(30, 12), nullable=True),
        sa.Column("tolerance_numeric", sa.Numeric(12, 9), nullable=True),
        sa.Column("evaluator_instance_id", sa.UUID(), nullable=True),
        sa.Column("evaluator_version_hash", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_external_ref", sa.Text(), nullable=True),
        sa.Column(
            "criterion_scores",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("judgment_label", sa.Boolean(), nullable=True),
        sa.Column(
            "passed",
            sa.Boolean(),
            sa.Computed(RESULT_PASSED_EXPR, persisted=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result_kind IN "
            "('specified_exact','reference_exact','reference_percentage','judgment_vote')",
            name="ck_tr_result_kind",
        ),
        sa.CheckConstraint(
            "sample_class IS NULL OR sample_class IN "
            "('representative','adversarial','calibration','other')",
            name="ck_tr_sample_class",
        ),
        sa.CheckConstraint(
            "octet_length(case_ref) BETWEEN 1 AND 128 AND btrim(case_ref) <> ''",
            name="ck_tr_case_ref_bounds",
        ),
        sa.CheckConstraint(
            "expected_digest IS NULL OR expected_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_tr_expected_digest",
        ),
        sa.CheckConstraint(
            "observed_digest IS NULL OR observed_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_tr_observed_digest",
        ),
        sa.CheckConstraint(
            "reference_digest IS NULL OR reference_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_tr_reference_digest",
        ),
        sa.CheckConstraint(TYPE_SHAPE_CHECK, name="ck_tr_type_shape"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_oracle_run_id", "project_id", "tenant_id"],
            ["test_oracle_runs.id", "test_oracle_runs.project_id", "test_oracle_runs.tenant_id"],
            name="run_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluator_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            name="evaluator_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_tr_tenant", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_results"),
    )
    op.create_index(
        "ix_test_results_run",
        "test_results",
        ["tenant_id", "test_oracle_run_id", "case_ref"],
    )
    op.create_index(
        "uq_test_results_deterministic_case",
        "test_results",
        ["test_oracle_run_id", "case_ref"],
        unique=True,
        postgresql_where=sa.text("evaluator_instance_id IS NULL"),
    )
    op.create_index(
        "uq_test_results_judgment_vote",
        "test_results",
        ["test_oracle_run_id", "case_ref", "evaluator_instance_id"],
        unique=True,
        postgresql_where=sa.text("evaluator_instance_id IS NOT NULL"),
    )

    _create_guards()
    _apply_rls_and_append_only()


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.test_oracle_runs_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE artifact_kind text; parent_kind text;
        BEGIN
            SELECT a.kind, p.kind INTO artifact_kind, parent_kind
            FROM public.intake_artifacts a
            LEFT JOIN public.intake_artifacts p ON p.id = a.parent_id
            WHERE a.id = NEW.oracle_artifact_id;
            IF artifact_kind IS DISTINCT FROM 'test_oracle'
               OR parent_kind IS DISTINCT FROM 'acceptance_criterion' THEN
                RAISE EXCEPTION
                    'test_oracle_runs: oracle requires an acceptance_criterion parent';
            END IF;
            RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER test_oracle_runs_kind_guard BEFORE INSERT ON public.test_oracle_runs "
        "FOR EACH ROW EXECUTE FUNCTION public.test_oracle_runs_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_test_oracle_run(target_run uuid) RETURNS void
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE
            r public.test_oracle_runs;
            actual_count int; actual_passed int; actual_cases int; actual_evaluators int;
            invalid_evaluators int; invalid_scores int;
            blueprint_count int; version_count int; model_count int;
            min_panel int; max_panel int; disagreements int;
            observed numeric; expected numeric; actual_irr numeric;
        BEGIN
            SELECT * INTO r FROM public.test_oracle_runs WHERE id = target_run;
            IF NOT FOUND THEN RETURN; END IF;
            SELECT count(*), count(*) FILTER (WHERE passed), count(DISTINCT case_ref),
                   count(DISTINCT evaluator_instance_id)
                       FILTER (WHERE evaluator_instance_id IS NOT NULL)
            INTO actual_count, actual_passed, actual_cases, actual_evaluators
            FROM public.test_results WHERE test_oracle_run_id = target_run;
            IF actual_count <> r.reported_result_count
               OR actual_passed <> r.reported_passed_count
               OR actual_cases <> r.reported_distinct_case_count
               OR actual_evaluators <> r.reported_evaluator_lineage_count THEN
                RAISE EXCEPTION 'test_oracle_runs: aggregate mismatch';
            END IF;
            IF r.execution_status <> 'succeeded' THEN
                IF actual_count <> 0 THEN
                    RAISE EXCEPTION 'test_oracle_runs: failed/refused run has results';
                END IF;
                RETURN;
            END IF;
            IF actual_cases <> r.required_sample_size THEN
                RAISE EXCEPTION 'test_oracle_runs: aggregate mismatch (sample coverage)';
            END IF;
            IF r.oracle_type <> 'judgment' THEN RETURN; END IF;
            SELECT count(*) INTO invalid_evaluators
            FROM (
                SELECT evaluator_instance_id, evaluator_version_hash
                FROM public.test_results WHERE test_oracle_run_id = target_run
            ) e
            LEFT JOIN public.agent_instances i ON i.id = e.evaluator_instance_id
            LEFT JOIN public.agent_versions v ON v.id = i.version_id
            LEFT JOIN public.agent_blueprints b ON b.id = v.blueprint_id
            LEFT JOIN public.agent_realizations ar ON ar.instance_id = i.id
            WHERE i.status IS DISTINCT FROM 'active'
               OR ar.qualification_status IS DISTINCT FROM 'qualified'
               OR b.archetype IS DISTINCT FROM 'ai_evaluation'
               OR e.evaluator_version_hash IS DISTINCT FROM v.content_hash;
            SELECT count(*) INTO invalid_scores
            FROM public.test_results tr, LATERAL jsonb_each(tr.criterion_scores) score
            WHERE tr.test_oracle_run_id = target_run
              AND jsonb_typeof(score.value) <> 'boolean';
            SELECT count(DISTINCT v.blueprint_id), count(DISTINCT v.content_hash),
                   count(DISTINCT v.model_route)
            INTO blueprint_count, version_count, model_count
            FROM (
                SELECT DISTINCT evaluator_instance_id FROM public.test_results
                WHERE test_oracle_run_id = target_run
            ) e
            JOIN public.agent_instances i ON i.id = e.evaluator_instance_id
            JOIN public.agent_versions v ON v.id = i.version_id;
            IF invalid_evaluators <> 0 OR invalid_scores <> 0 OR actual_evaluators < 2
               OR blueprint_count <> actual_evaluators
               OR version_count <> actual_evaluators
               OR model_count <> actual_evaluators THEN
                RAISE EXCEPTION 'test_oracle_runs: evaluator lineage mismatch';
            END IF;
            SELECT min(n), max(n), count(*) FILTER (WHERE yes_count NOT IN (0,n))
            INTO min_panel, max_panel, disagreements
            FROM (
                SELECT case_ref, count(*) n, count(*) FILTER (WHERE passed) yes_count
                FROM public.test_results WHERE test_oracle_run_id = target_run
                GROUP BY case_ref
            ) q;
            IF min_panel <> actual_evaluators OR max_panel <> actual_evaluators
               OR disagreements <> r.reported_unresolved_disagreement_count THEN
                RAISE EXCEPTION 'test_oracle_runs: aggregate mismatch (judgment panel)';
            END IF;
            WITH per_case AS (
                SELECT count(*)::numeric n,
                       count(*) FILTER (WHERE passed)::numeric yes_count
                FROM public.test_results WHERE test_oracle_run_id = target_run
                GROUP BY case_ref
            )
            SELECT avg(
                (yes_count*(yes_count-1)+(n-yes_count)*(n-yes_count-1))/(n*(n-1))
            ) INTO observed FROM per_case;
            expected := power(actual_passed::numeric/actual_count,2)
                + power(1-actual_passed::numeric/actual_count,2);
            actual_irr := round(
                CASE WHEN expected=1 THEN CASE WHEN observed=1 THEN 1 ELSE 0 END
                     ELSE (observed-expected)/(1-expected) END,
                6
            );
            IF actual_irr IS DISTINCT FROM r.reported_irr THEN
                RAISE EXCEPTION 'test_oracle_runs: aggregate mismatch (Fleiss kappa)';
            END IF;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.test_oracle_run_verify_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN
            PERFORM public.verify_test_oracle_run(NEW.id);
            RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.test_result_verify_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN
            PERFORM public.verify_test_oracle_run(NEW.test_oracle_run_id);
            RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER test_oracle_runs_verify "
        "AFTER INSERT ON public.test_oracle_runs DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION public.test_oracle_run_verify_trigger()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER test_results_verify "
        "AFTER INSERT ON public.test_results DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION public.test_result_verify_trigger()"
    )


def _apply_rls_and_append_only() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
            LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
            BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$
            """
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE "
            f"ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute("DROP TRIGGER IF EXISTS test_results_verify ON public.test_results")
    op.execute("DROP TRIGGER IF EXISTS test_oracle_runs_verify ON public.test_oracle_runs")
    op.execute("DROP FUNCTION IF EXISTS public.test_result_verify_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.test_oracle_run_verify_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_test_oracle_run(uuid)")
    op.execute("DROP TRIGGER IF EXISTS test_oracle_runs_kind_guard ON public.test_oracle_runs")
    op.execute("DROP FUNCTION IF EXISTS public.test_oracle_runs_guard()")
    op.drop_index("uq_test_results_judgment_vote", table_name="test_results")
    op.drop_index("uq_test_results_deterministic_case", table_name="test_results")
    op.drop_index("ix_test_results_run", table_name="test_results")
    op.drop_table("test_results")
    op.drop_index("ix_test_oracle_runs_latest", table_name="test_oracle_runs")
    op.drop_table("test_oracle_runs")
