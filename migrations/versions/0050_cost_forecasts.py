"""cost forecast policy versions, exact inputs, and gate evidence

Revision ID: 0050
Revises: 0049
Create Date: 2026-07-13

Slice 51. Additive-only: five tenant-owned RLS ENABLE+FORCE append-only tables and
two composite identity targets. Existing cost/runtime/readiness/findings semantics are unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_HASH = r"^sha256:[0-9a-f]{64}$"
_POLICY_HASH = "sha256:067a1078f436686629e777384c70734eb0c7197554c8b637ea1784587ef2e7d5"
_INPUT_HASH = "sha256:421c35ca34b48aebdaa404404a60ab4b18b9de81608ee754798f6719613aca6d"
_FORECAST_HASH = "sha256:b853aecc7bfd79c5e061a22651285b0c3f1eaa56412c5cb9bddca314f040d705"


def _append_only(table: str) -> None:
    op.execute(
        f"""
        CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$
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


def _tenant_table(table: str) -> None:
    _append_only(table)
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def _create_policy_versions() -> None:
    op.create_table(
        "cost_forecast_policy_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("policy_contract_version", sa.Text(), nullable=False),
        sa.Column("policy_contract_hash", sa.Text(), nullable=False),
        sa.Column("policy_digest", sa.Text(), nullable=False),
        sa.Column("max_total_model_cost_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("max_daily_model_cost_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("max_cloud_spend_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("max_ci_minutes_per_day", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "require_approval_above_forecast_percentage", sa.Numeric(9, 4), nullable=False
        ),
        sa.Column("cheap_first_for_low_risk", sa.Boolean(), nullable=False),
        sa.Column("frontier_for_high_risk", sa.Boolean(), nullable=False),
        sa.Column("use_cached_context_when_possible", sa.Boolean(), nullable=False),
        sa.Column("stop_conditions", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("stop_condition_count", sa.Integer(), nullable=False),
        sa.Column("source_provenance", sa.Text(), nullable=False),
        sa.Column("source_label", sa.Text(), nullable=True),
        sa.Column("evidence_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "policy_contract_version='slice51.cost_policy.v1' "
            "AND source_provenance='caller_supplied_unverified_structured_cost_policy'",
            name="ck_cost_forecast_policy_versions_contract_provenance",
        ),
        sa.CheckConstraint(
            f"policy_contract_hash='{_POLICY_HASH}' AND policy_digest ~ '{_HASH}'",
            name="ck_cost_forecast_policy_versions_hashes",
        ),
        sa.CheckConstraint(
            "max_total_model_cost_usd>0 AND max_daily_model_cost_usd>0 "
            "AND max_cloud_spend_usd>0 AND max_ci_minutes_per_day>0 "
            "AND require_approval_above_forecast_percentage BETWEEN 0 AND 100",
            name="ck_cost_forecast_policy_versions_numeric_bounds",
        ),
        sa.CheckConstraint(
            "stop_condition_count=4 AND cardinality(stop_conditions)=4 AND "
            "stop_conditions=ARRAY['budget_exceeded','repeated_failure_without_new_strategy',"
            "'tool_loop_detected','model_provider_outage_extended']::text[]",
            name="ck_cost_forecast_policy_versions_stop_conditions",
        ),
        sa.CheckConstraint(
            "source_label IS NULL OR (char_length(source_label) BETWEEN 1 AND 255 "
            "AND btrim(source_label)<>'')",
            name="ck_cost_forecast_policy_versions_source_label",
        ),
        sa.CheckConstraint(
            "evidence_ref IS NULL OR (char_length(evidence_ref) BETWEEN 1 AND 500 "
            "AND btrim(evidence_ref)<>'')",
            name="ck_cost_forecast_policy_versions_evidence_ref",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_cfpv_id_project_tenant"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "policy_digest", name="uq_cfpv_project_digest"
        ),
    )


def _create_runs() -> None:
    op.create_table(
        "cost_forecast_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=True),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=True),
        sa.Column("policy_version_id", sa.UUID(), nullable=True),
        sa.Column("budget_id", sa.UUID(), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_utc_date", sa.Date(), nullable=False),
        sa.Column("policy_contract_version", sa.Text(), nullable=False),
        sa.Column("input_contract_version", sa.Text(), nullable=False),
        sa.Column("forecast_contract_version", sa.Text(), nullable=False),
        sa.Column("policy_contract_hash", sa.Text(), nullable=False),
        sa.Column("input_contract_hash", sa.Text(), nullable=False),
        sa.Column("forecast_contract_hash", sa.Text(), nullable=False),
        sa.Column("core_content_hash", sa.Text(), nullable=True),
        sa.Column("budget_total_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("budget_daily_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("budget_digest", sa.Text(), nullable=True),
        sa.Column("ledger_digest", sa.Text(), nullable=True),
        sa.Column("assumption_digest", sa.Text(), nullable=True),
        sa.Column("price_digest", sa.Text(), nullable=True),
        sa.Column("result_digest", sa.Text(), nullable=True),
        sa.Column("input_digest", sa.Text(), nullable=False),
        sa.Column("stop_reason", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("execution_provenance", sa.Text(), nullable=False),
        sa.Column("event_ref_count", sa.Integer(), nullable=False),
        sa.Column("input_line_count", sa.Integer(), nullable=False),
        sa.Column("model_line_count", sa.Integer(), nullable=False),
        sa.Column("dimension_count", sa.Integer(), nullable=False),
        sa.Column("all_dimensions_within", sa.Boolean(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("evidence_consistent", sa.Boolean(), nullable=False),
        sa.Column("gate_eligible", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "policy_contract_version='slice51.cost_policy.v1' "
            "AND input_contract_version='slice51.cost_forecast_input.v1' "
            "AND forecast_contract_version='slice51.cost_forecast.v1' "
            "AND execution_provenance='system_derived_cost_forecast'",
            name="ck_cost_forecast_runs_contracts_provenance",
        ),
        sa.CheckConstraint(
            f"policy_contract_hash='{_POLICY_HASH}' AND input_contract_hash='{_INPUT_HASH}' "
            f"AND forecast_contract_hash='{_FORECAST_HASH}' "
            f"AND (budget_digest IS NULL OR budget_digest ~ '{_HASH}') "
            f"AND (ledger_digest IS NULL OR ledger_digest ~ '{_HASH}') "
            f"AND (assumption_digest IS NULL OR assumption_digest ~ '{_HASH}') "
            f"AND (price_digest IS NULL OR price_digest ~ '{_HASH}') "
            f"AND (result_digest IS NULL OR result_digest ~ '{_HASH}') "
            f"AND input_digest ~ '{_HASH}' "
            f"AND (core_content_hash IS NULL OR core_content_hash ~ '{_HASH}')",
            name="ck_cost_forecast_runs_hashes",
        ),
        sa.CheckConstraint("outcome IN ('succeeded','failed','refused')", name="ck_cost_forecast_runs_outcome"),
        sa.CheckConstraint(
            "stop_reason IN ('ok','no_budget','budget_exceeded','daily_budget_exceeded')",
            name="ck_cost_forecast_runs_stop_reason",
        ),
        sa.CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''",
            name="ck_cost_forecast_runs_reason_code",
        ),
        sa.CheckConstraint(
            "(budget_total_usd IS NULL OR budget_total_usd>0) "
            "AND (budget_daily_usd IS NULL OR budget_daily_usd>0) "
            "AND event_ref_count BETWEEN 0 AND 50000 "
            "AND input_line_count BETWEEN 0 AND 1000 AND model_line_count BETWEEN 0 AND 128 "
            "AND dimension_count BETWEEN 0 AND 6",
            name="ck_cost_forecast_runs_bounds",
        ),
        sa.CheckConstraint(
            "(outcome='succeeded' AND release_candidate_id IS NOT NULL "
            "AND evidence_pack_id IS NOT NULL AND policy_version_id IS NOT NULL "
            "AND budget_id IS NOT NULL AND core_content_hash IS NOT NULL "
            "AND budget_total_usd IS NOT NULL AND budget_daily_usd IS NOT NULL "
            "AND budget_digest IS NOT NULL AND ledger_digest IS NOT NULL "
            "AND assumption_digest IS NOT NULL AND price_digest IS NOT NULL "
            "AND result_digest IS NOT NULL AND event_ref_count>0 AND input_line_count>=9 "
            "AND dimension_count=6) OR "
            "(outcome IN ('failed','refused') AND event_ref_count=0 "
            "AND input_line_count=0 AND model_line_count=0 AND dimension_count=0 "
            "AND NOT all_dimensions_within AND NOT approval_required "
            "AND NOT evidence_consistent AND NOT gate_eligible)",
            name="ck_cost_forecast_runs_result_shape",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "cost_forecast_policy_versions.id",
                "cost_forecast_policy_versions.project_id",
                "cost_forecast_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["budget_id", "project_id", "tenant_id"],
            ["budgets.id", "budgets.project_id", "budgets.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_cfr_id_project_tenant"),
    )


def _create_event_refs() -> None:
    op.create_table(
        "cost_forecast_ledger_event_refs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("cost_event_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("component", sa.Text(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("material_digest", sa.Text(), nullable=False),
        sa.Column("source_provenance", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 50000 AND amount_usd>=0", name="ck_cost_forecast_ledger_event_refs_bounds"),
        sa.CheckConstraint("component IN ('model_inference','tool_execution','cloud_runtime','ci_cd','storage_retrieval','monitoring','human_review','rework')", name="ck_cost_forecast_ledger_event_refs_component"),
        sa.CheckConstraint(f"material_digest ~ '{_HASH}' AND source_provenance='db_bound_incurred_cost_events'", name="ck_cost_forecast_ledger_event_refs_provenance_digest"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id", "project_id", "tenant_id"], ["cost_forecast_runs.id", "cost_forecast_runs.project_id", "cost_forecast_runs.tenant_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cost_event_id", "project_id", "tenant_id"], ["cost_events.id", "cost_events.project_id", "cost_events.tenant_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_cfler_run_ordinal"),
        sa.UniqueConstraint("run_id", "cost_event_id", name="uq_cfler_run_event"),
    )


def _create_input_lines() -> None:
    op.create_table(
        "cost_forecast_input_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("line_kind", sa.Text(), nullable=False),
        sa.Column("component", sa.Text(), nullable=True),
        sa.Column("remaining_total_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("remaining_today_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("model_route_hash", sa.Text(), nullable=True),
        sa.Column("remaining_input_tokens", sa.Integer(), nullable=True),
        sa.Column("remaining_output_tokens", sa.Integer(), nullable=True),
        sa.Column("remaining_today_input_tokens", sa.Integer(), nullable=True),
        sa.Column("remaining_today_output_tokens", sa.Integer(), nullable=True),
        sa.Column("input_rate_usd_per_1k", sa.Numeric(18, 6), nullable=True),
        sa.Column("output_rate_usd_per_1k", sa.Numeric(18, 6), nullable=True),
        sa.Column("ci_minutes", sa.Integer(), nullable=True),
        sa.Column("derived_total_usd", sa.Numeric(18, 6), sa.Computed("CASE WHEN line_kind='model_price' THEN (remaining_input_tokens*input_rate_usd_per_1k + remaining_output_tokens*output_rate_usd_per_1k)/1000.0 WHEN line_kind='component_remaining' THEN remaining_total_usd ELSE NULL END"), nullable=True),
        sa.Column("derived_today_usd", sa.Numeric(18, 6), sa.Computed("CASE WHEN line_kind='model_price' THEN (remaining_today_input_tokens*input_rate_usd_per_1k + remaining_today_output_tokens*output_rate_usd_per_1k)/1000.0 WHEN line_kind='component_remaining' THEN remaining_today_usd ELSE NULL END"), nullable=True),
        sa.Column("source_provenance", sa.Text(), nullable=False),
        sa.Column("line_digest", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 1000", name="ck_cost_forecast_input_lines_ordinal"),
        sa.CheckConstraint("line_kind IN ('component_remaining','model_price','ci_minutes_today')", name="ck_cost_forecast_input_lines_kind"),
        sa.CheckConstraint("component IS NULL OR component IN ('model_inference','tool_execution','cloud_runtime','ci_cd','storage_retrieval','monitoring','human_review','rework')", name="ck_cost_forecast_input_lines_component"),
        sa.CheckConstraint(f"(model_route_hash IS NULL OR model_route_hash ~ '{_HASH}') AND line_digest ~ '{_HASH}'", name="ck_cost_forecast_input_lines_route_hash"),
        sa.CheckConstraint("COALESCE(remaining_total_usd,0)>=0 AND COALESCE(remaining_today_usd,0)>=0 AND COALESCE(remaining_input_tokens,0)>=0 AND COALESCE(remaining_output_tokens,0)>=0 AND COALESCE(remaining_today_input_tokens,0)>=0 AND COALESCE(remaining_today_output_tokens,0)>=0 AND COALESCE(input_rate_usd_per_1k,0)>=0 AND COALESCE(output_rate_usd_per_1k,0)>=0 AND COALESCE(ci_minutes,0)>=0", name="ck_cost_forecast_input_lines_nonnegative"),
        sa.CheckConstraint("COALESCE(remaining_today_input_tokens,0)<=COALESCE(remaining_input_tokens,0) AND COALESCE(remaining_today_output_tokens,0)<=COALESCE(remaining_output_tokens,0)", name="ck_cost_forecast_input_lines_today_tokens"),
        sa.CheckConstraint("(line_kind='component_remaining' AND component IS NOT NULL AND remaining_total_usd IS NOT NULL AND remaining_today_usd IS NOT NULL AND remaining_today_usd<=remaining_total_usd AND model_route_hash IS NULL AND remaining_input_tokens IS NULL AND remaining_output_tokens IS NULL AND remaining_today_input_tokens IS NULL AND remaining_today_output_tokens IS NULL AND input_rate_usd_per_1k IS NULL AND output_rate_usd_per_1k IS NULL AND ci_minutes IS NULL AND source_provenance='reported_cost_forecast_assumption') OR (line_kind='model_price' AND component IS NULL AND remaining_total_usd IS NULL AND remaining_today_usd IS NULL AND model_route_hash IS NOT NULL AND remaining_input_tokens IS NOT NULL AND remaining_output_tokens IS NOT NULL AND remaining_today_input_tokens IS NOT NULL AND remaining_today_output_tokens IS NOT NULL AND input_rate_usd_per_1k IS NOT NULL AND output_rate_usd_per_1k IS NOT NULL AND ci_minutes IS NULL AND source_provenance='operator_configured_price_card_snapshot') OR (line_kind='ci_minutes_today' AND component IS NULL AND remaining_total_usd IS NULL AND remaining_today_usd IS NULL AND model_route_hash IS NULL AND remaining_input_tokens IS NULL AND remaining_output_tokens IS NULL AND remaining_today_input_tokens IS NULL AND remaining_today_output_tokens IS NULL AND input_rate_usd_per_1k IS NULL AND output_rate_usd_per_1k IS NULL AND ci_minutes IS NOT NULL AND source_provenance='reported_cost_forecast_assumption')", name="ck_cost_forecast_input_lines_shape"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id", "project_id", "tenant_id"], ["cost_forecast_runs.id", "cost_forecast_runs.project_id", "cost_forecast_runs.tenant_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_cfil_run_ordinal"),
        sa.UniqueConstraint("run_id", "line_kind", "component", name="uq_cfil_run_kind_component"),
        sa.UniqueConstraint("run_id", "model_route_hash", name="uq_cfil_run_model_route"),
    )


def _create_dimensions() -> None:
    op.create_table(
        "cost_forecast_dimension_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("dimension_code", sa.Text(), nullable=False),
        sa.Column("forecast_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("policy_limit", sa.Numeric(18, 6), nullable=False),
        sa.Column("approval_threshold", sa.Numeric(9, 4), nullable=False),
        sa.Column("dimension_digest", sa.Text(), nullable=False),
        sa.Column("utilization_percent", sa.Numeric(9, 4), sa.Computed("round((forecast_value/policy_limit)*100,4)"), nullable=False),
        sa.Column("within_limit", sa.Boolean(), sa.Computed("forecast_value<policy_limit"), nullable=False),
        sa.Column("approval_triggered", sa.Boolean(), sa.Computed("round((forecast_value/policy_limit)*100,4)>approval_threshold"), nullable=False),
        sa.Column("result_code", sa.Text(), sa.Computed("CASE WHEN forecast_value>=policy_limit THEN 'limit_reached_or_exceeded' WHEN round((forecast_value/policy_limit)*100,4)>approval_threshold THEN 'approval_required' ELSE 'within_limit' END"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 6", name="ck_cost_forecast_dimension_results_ordinal"),
        sa.CheckConstraint("dimension_code IN ('all_cost_total_usd','all_cost_daily_usd','model_cost_total_usd','model_cost_daily_usd','cloud_spend_total_usd','ci_minutes_daily')", name="ck_cost_forecast_dimension_results_dimension"),
        sa.CheckConstraint(f"forecast_value>=0 AND policy_limit>0 AND approval_threshold BETWEEN 0 AND 100 AND dimension_digest ~ '{_HASH}'", name="ck_cost_forecast_dimension_results_bounds"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id", "project_id", "tenant_id"], ["cost_forecast_runs.id", "cost_forecast_runs.project_id", "cost_forecast_runs.tenant_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_cfdr_run_ordinal"),
        sa.UniqueConstraint("run_id", "dimension_code", name="uq_cfdr_run_dimension"),
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.slice51_hash(VARIADIC parts text[]) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $fn$
          SELECT 'sha256:' || encode(sha256(convert_to(array_to_string(parts, chr(31)), 'UTF8')), 'hex')
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.cost_forecast_policy_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE expected text;
        BEGIN
          expected := public.slice51_hash(
            NEW.policy_contract_version, NEW.max_total_model_cost_usd::text,
            NEW.max_daily_model_cost_usd::text, NEW.max_cloud_spend_usd::text,
            NEW.max_ci_minutes_per_day::text,
            NEW.require_approval_above_forecast_percentage::text,
            NEW.cheap_first_for_low_risk::text, NEW.frontier_for_high_risk::text,
            NEW.use_cached_context_when_possible::text,
            array_to_string(NEW.stop_conditions, ','), NEW.source_provenance);
          IF NEW.policy_digest<>expected THEN RAISE EXCEPTION 'cost policy digest mismatch'; END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute("CREATE TRIGGER cost_forecast_policy_guard BEFORE INSERT ON cost_forecast_policy_versions FOR EACH ROW EXECUTE FUNCTION public.cost_forecast_policy_guard()")
    op.execute(
        """
        CREATE FUNCTION public.cost_forecast_event_ref_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE e record; expected text;
        BEGIN
          SELECT * INTO e FROM public.cost_events WHERE id=NEW.cost_event_id;
          IF e.id IS NULL OR e.tenant_id<>NEW.tenant_id OR e.project_id<>NEW.project_id
             OR e.component<>NEW.component OR e.amount_usd<>NEW.amount_usd
             OR e.occurred_at<>NEW.occurred_at THEN
            RAISE EXCEPTION 'cost forecast event reference mismatch';
          END IF;
          expected := public.slice51_hash(e.id::text,e.tenant_id::text,e.project_id::text,
            e.component,e.amount_usd::text,
            to_char(e.occurred_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));
          IF NEW.material_digest<>expected THEN RAISE EXCEPTION 'cost event digest mismatch'; END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute("CREATE TRIGGER cost_forecast_event_ref_guard BEFORE INSERT ON cost_forecast_ledger_event_refs FOR EACH ROW EXECUTE FUNCTION public.cost_forecast_event_ref_guard()")
    op.execute(
        """
        CREATE FUNCTION public.cost_forecast_input_line_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE expected text;
        BEGIN
          expected := public.slice51_hash(NEW.line_kind,COALESCE(NEW.component,''),
            COALESCE(NEW.remaining_total_usd::text,''),COALESCE(NEW.remaining_today_usd::text,''),
            COALESCE(NEW.model_route_hash,''),COALESCE(NEW.remaining_input_tokens::text,''),
            COALESCE(NEW.remaining_output_tokens::text,''),
            COALESCE(NEW.remaining_today_input_tokens::text,''),
            COALESCE(NEW.remaining_today_output_tokens::text,''),
            COALESCE(NEW.input_rate_usd_per_1k::text,''),
            COALESCE(NEW.output_rate_usd_per_1k::text,''),COALESCE(NEW.ci_minutes::text,''),
            NEW.source_provenance);
          IF NEW.line_digest<>expected THEN RAISE EXCEPTION 'cost forecast input line digest mismatch'; END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute("CREATE TRIGGER cost_forecast_input_line_guard BEFORE INSERT ON cost_forecast_input_lines FOR EACH ROW EXECUTE FUNCTION public.cost_forecast_input_line_guard()")
    op.execute(
        """
        CREATE FUNCTION public.cost_forecast_dimension_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE expected text;
        BEGIN
          expected := public.slice51_hash(NEW.dimension_code,NEW.forecast_value::text,
            NEW.policy_limit::text,NEW.approval_threshold::text);
          IF NEW.dimension_digest<>expected THEN RAISE EXCEPTION 'cost forecast dimension digest mismatch'; END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute("CREATE TRIGGER cost_forecast_dimension_guard BEFORE INSERT ON cost_forecast_dimension_results FOR EACH ROW EXECUTE FUNCTION public.cost_forecast_dimension_guard()")
    op.execute(
        f"""
        CREATE FUNCTION public.cost_forecast_run_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE c record; p record; pol record; b record; expected_budget text;
        BEGIN
          IF NEW.policy_contract_hash<>'{_POLICY_HASH}' OR NEW.input_contract_hash<>'{_INPUT_HASH}'
             OR NEW.forecast_contract_hash<>'{_FORECAST_HASH}' THEN
            RAISE EXCEPTION 'cost forecast contract hash mismatch';
          END IF;
          IF NEW.outcome='succeeded' THEN
            SELECT * INTO c FROM public.release_candidates WHERE id=NEW.release_candidate_id;
            SELECT * INTO p FROM public.evidence_packs WHERE id=NEW.evidence_pack_id;
            SELECT * INTO pol FROM public.cost_forecast_policy_versions WHERE id=NEW.policy_version_id;
            SELECT * INTO b FROM public.budgets WHERE id=NEW.budget_id;
            IF c.id IS NULL OR c.status<>'frozen' OR c.project_id<>NEW.project_id OR c.tenant_id<>NEW.tenant_id
               OR p.id IS NULL OR p.assembly_status<>'complete' OR p.release_candidate_id<>c.id
               OR p.project_id<>NEW.project_id OR p.tenant_id<>NEW.tenant_id
               OR p.core_content_hash<>NEW.core_content_hash OR pol.id IS NULL
               OR pol.project_id<>NEW.project_id OR pol.tenant_id<>NEW.tenant_id
               OR b.id IS NULL OR b.project_id<>NEW.project_id OR b.tenant_id<>NEW.tenant_id
               OR b.max_daily_cost_usd IS NULL OR b.max_total_cost_usd<>NEW.budget_total_usd
               OR b.max_daily_cost_usd<>NEW.budget_daily_usd THEN
              RAISE EXCEPTION 'cost forecast exact scope/policy/budget binding mismatch';
            END IF;
            expected_budget := public.slice51_hash(b.id::text,b.max_total_cost_usd::text,b.max_daily_cost_usd::text);
            IF NEW.budget_digest<>expected_budget THEN RAISE EXCEPTION 'cost forecast budget digest mismatch'; END IF;
          END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute("CREATE TRIGGER cost_forecast_run_guard BEFORE INSERT ON cost_forecast_runs FOR EACH ROW EXECUTE FUNCTION public.cost_forecast_run_guard()")

    op.execute(
        """
        CREATE FUNCTION public.verify_cost_forecast_run(run_uuid uuid) RETURNS boolean
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE r record; pol record; event_count bigint; source_event_count bigint;
        DECLARE input_count bigint; model_count bigint;
        DECLARE dim_count bigint; component_count bigint; ci_count bigint;
        DECLARE ledger_hash text; assumption_hash text; price_hash text; result_hash text; expected_input text;
        DECLARE ledger_total numeric; ledger_daily numeric; model_total numeric; model_daily numeric;
        DECLARE remaining_total numeric; remaining_daily numeric; cloud_total numeric; ci_value numeric;
        DECLARE expected_stop text; expected_reason text; all_within boolean; approval boolean;
        BEGIN
          SELECT * INTO r FROM public.cost_forecast_runs WHERE id=run_uuid;
          IF r.id IS NULL THEN RETURN true; END IF;
          SELECT count(*) INTO event_count FROM public.cost_forecast_ledger_event_refs WHERE run_id=r.id;
          SELECT count(*),count(*) FILTER (WHERE line_kind='model_price'),
                 count(DISTINCT component) FILTER (WHERE line_kind='component_remaining'),
                 count(*) FILTER (WHERE line_kind='ci_minutes_today')
            INTO input_count,model_count,component_count,ci_count
            FROM public.cost_forecast_input_lines WHERE run_id=r.id;
          SELECT count(*) INTO dim_count FROM public.cost_forecast_dimension_results WHERE run_id=r.id;
          IF r.outcome<>'succeeded' THEN
            IF event_count<>0 OR input_count<>0 OR dim_count<>0 THEN
              RAISE EXCEPTION 'failed/refused cost forecast has result children';
            END IF;
            RETURN true;
          END IF;
          IF r.forecast_utc_date<>(r.as_of AT TIME ZONE 'UTC')::date THEN
            RAISE EXCEPTION 'cost forecast UTC date does not match as_of';
          END IF;
          IF event_count<>r.event_ref_count OR input_count<>r.input_line_count
             OR model_count<>r.model_line_count OR dim_count<>r.dimension_count
             OR component_count<>8 OR ci_count<>1 OR dim_count<>6 THEN
            RAISE EXCEPTION 'cost forecast child set is incomplete';
          END IF;
          SELECT count(*) INTO source_event_count FROM public.cost_events
            WHERE tenant_id=r.tenant_id AND project_id=r.project_id;
          IF source_event_count<>event_count THEN
            RAISE EXCEPTION 'cost forecast source event inventory mismatch';
          END IF;
          IF EXISTS (
            SELECT 1 FROM public.cost_events e
            WHERE e.tenant_id=r.tenant_id AND e.project_id=r.project_id
              AND e.occurred_at>r.as_of
          ) THEN
            RAISE EXCEPTION 'future-dated incurred source event in forecast';
          END IF;
          IF EXISTS (SELECT 1 FROM public.cost_forecast_input_lines WHERE run_id=r.id
             AND line_kind='component_remaining' AND component='model_inference'
             AND (remaining_total_usd<>0 OR remaining_today_usd<>0)) THEN
            RAISE EXCEPTION 'model forecast dollars were not token-derived';
          END IF;
          IF EXISTS (SELECT 1 FROM public.cost_forecast_input_lines WHERE run_id=r.id
             AND line_kind='model_price'
             AND (remaining_input_tokens+remaining_output_tokens
                  +remaining_today_input_tokens+remaining_today_output_tokens)>0
             AND input_rate_usd_per_1k=0 AND output_rate_usd_per_1k=0) THEN
            RAISE EXCEPTION 'nonzero planned model tokens require a nonzero price';
          END IF;
          IF EXISTS (SELECT 1 FROM public.cost_forecast_ledger_event_refs WHERE run_id=r.id AND occurred_at>r.as_of) THEN
            RAISE EXCEPTION 'future-dated incurred event in forecast';
          END IF;
          SELECT public.slice51_hash(VARIADIC array_agg(material_digest ORDER BY ordinal))
            INTO ledger_hash FROM public.cost_forecast_ledger_event_refs WHERE run_id=r.id;
          SELECT public.slice51_hash(VARIADIC array_agg(line_digest ORDER BY ordinal) FILTER (WHERE line_kind='component_remaining' OR line_kind='ci_minutes_today')),
                 public.slice51_hash(VARIADIC array_agg(line_digest ORDER BY ordinal) FILTER (WHERE line_kind='model_price'))
            INTO assumption_hash,price_hash FROM public.cost_forecast_input_lines WHERE run_id=r.id;
          IF model_count=0 THEN price_hash:=public.slice51_hash(''); END IF;
          SELECT public.slice51_hash(VARIADIC array_agg(dimension_digest ORDER BY ordinal))
            INTO result_hash FROM public.cost_forecast_dimension_results WHERE run_id=r.id;
          IF r.ledger_digest<>ledger_hash OR r.assumption_digest<>assumption_hash
             OR r.price_digest<>price_hash OR r.result_digest<>result_hash THEN
            RAISE EXCEPTION 'cost forecast child-set digest mismatch';
          END IF;
          SELECT COALESCE(sum(amount_usd),0),
                 COALESCE(sum(amount_usd) FILTER (WHERE (occurred_at AT TIME ZONE 'UTC')::date=r.forecast_utc_date),0),
                 COALESCE(sum(amount_usd) FILTER (WHERE component='model_inference'),0),
                 COALESCE(sum(amount_usd) FILTER (WHERE component='model_inference' AND (occurred_at AT TIME ZONE 'UTC')::date=r.forecast_utc_date),0),
                 COALESCE(sum(amount_usd) FILTER (WHERE component='cloud_runtime'),0)
            INTO ledger_total,ledger_daily,model_total,model_daily,cloud_total
            FROM public.cost_forecast_ledger_event_refs WHERE run_id=r.id;
          SELECT COALESCE(sum(derived_total_usd) FILTER (WHERE line_kind='component_remaining'),0),
                 COALESCE(sum(derived_today_usd) FILTER (WHERE line_kind='component_remaining'),0),
                 COALESCE(sum(derived_total_usd) FILTER (WHERE line_kind='model_price'),0),
                 COALESCE(sum(derived_today_usd) FILTER (WHERE line_kind='model_price'),0),
                 max(ci_minutes) FILTER (WHERE line_kind='ci_minutes_today')
            INTO remaining_total,remaining_daily,model_total,model_daily,ci_value
            FROM public.cost_forecast_input_lines WHERE run_id=r.id;
          SELECT * INTO pol FROM public.cost_forecast_policy_versions WHERE id=r.policy_version_id;
          IF EXISTS (
            SELECT 1 FROM public.cost_forecast_dimension_results d WHERE d.run_id=r.id AND
            ((d.dimension_code='all_cost_total_usd' AND (d.forecast_value<>ledger_total+remaining_total+model_total OR d.policy_limit<>r.budget_total_usd)) OR
             (d.dimension_code='all_cost_daily_usd' AND (d.forecast_value<>ledger_daily+remaining_daily+model_daily OR d.policy_limit<>r.budget_daily_usd)) OR
             (d.dimension_code='model_cost_total_usd' AND (d.forecast_value<>(SELECT COALESCE(sum(amount_usd),0) FROM public.cost_forecast_ledger_event_refs WHERE run_id=r.id AND component='model_inference')+model_total OR d.policy_limit<>pol.max_total_model_cost_usd)) OR
             (d.dimension_code='model_cost_daily_usd' AND (d.forecast_value<>(SELECT COALESCE(sum(amount_usd),0) FROM public.cost_forecast_ledger_event_refs WHERE run_id=r.id AND component='model_inference' AND (occurred_at AT TIME ZONE 'UTC')::date=r.forecast_utc_date)+model_daily OR d.policy_limit<>pol.max_daily_model_cost_usd)) OR
             (d.dimension_code='cloud_spend_total_usd' AND (d.forecast_value<>cloud_total+(SELECT remaining_total_usd FROM public.cost_forecast_input_lines WHERE run_id=r.id AND line_kind='component_remaining' AND component='cloud_runtime') OR d.policy_limit<>pol.max_cloud_spend_usd)) OR
             (d.dimension_code='ci_minutes_daily' AND (d.forecast_value<>ci_value OR d.policy_limit<>pol.max_ci_minutes_per_day)) OR
             d.approval_threshold<>pol.require_approval_above_forecast_percentage)
          ) THEN RAISE EXCEPTION 'cost forecast dimension value or limit mismatch'; END IF;
          SELECT bool_and(within_limit),bool_or(approval_triggered) INTO all_within,approval
            FROM public.cost_forecast_dimension_results WHERE run_id=r.id;
          SELECT CASE WHEN COALESCE(sum(amount_usd),0)>=r.budget_total_usd THEN 'budget_exceeded'
                 WHEN COALESCE(sum(amount_usd) FILTER (WHERE (occurred_at AT TIME ZONE 'UTC')::date=r.forecast_utc_date),0)>=r.budget_daily_usd THEN 'daily_budget_exceeded'
                 ELSE 'ok' END INTO expected_stop
            FROM public.cost_forecast_ledger_event_refs WHERE run_id=r.id;
          expected_reason:=CASE WHEN expected_stop<>'ok' THEN 'cost_stop_active'
            WHEN NOT all_within THEN 'limit_reached_or_exceeded'
            WHEN approval THEN 'approval_required' ELSE 'within_recorded_policy' END;
          IF r.stop_reason<>expected_stop OR r.reason_code<>expected_reason
             OR r.all_dimensions_within IS DISTINCT FROM all_within
             OR r.approval_required IS DISTINCT FROM approval OR NOT r.evidence_consistent
             OR r.gate_eligible IS DISTINCT FROM (expected_reason='within_recorded_policy') THEN
            RAISE EXCEPTION 'cost forecast generated summary or gate eligibility mismatch';
          END IF;
          expected_input:=public.slice51_hash(r.core_content_hash,pol.policy_digest,r.budget_digest,
            r.ledger_digest,r.assumption_digest,r.price_digest,r.result_digest,
            r.forecast_utc_date::text,r.stop_reason,r.input_contract_version,r.forecast_contract_version);
          IF r.input_digest<>expected_input THEN RAISE EXCEPTION 'cost forecast input digest mismatch'; END IF;
          RETURN true;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_cost_forecast_run_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE n jsonb:=to_jsonb(NEW); o jsonb:=to_jsonb(OLD); run_uuid uuid;
        BEGIN
          run_uuid:=CASE WHEN TG_TABLE_NAME='cost_forecast_runs'
            THEN COALESCE((n->>'id')::uuid,(o->>'id')::uuid)
            ELSE COALESCE((n->>'run_id')::uuid,(o->>'run_id')::uuid) END;
          PERFORM public.verify_cost_forecast_run(run_uuid); RETURN NULL;
        END $fn$
        """
    )
    for table in (
        "cost_forecast_runs",
        "cost_forecast_ledger_event_refs",
        "cost_forecast_input_lines",
        "cost_forecast_dimension_results",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_verify AFTER INSERT OR UPDATE OR DELETE ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.verify_cost_forecast_run_trigger()"
        )


def upgrade() -> None:
    op.create_unique_constraint("uq_cost_events_id_project_tenant", "cost_events", ["id", "project_id", "tenant_id"])
    op.create_unique_constraint("uq_budgets_id_project_tenant", "budgets", ["id", "project_id", "tenant_id"])
    _create_policy_versions()
    _create_runs()
    _create_event_refs()
    _create_input_lines()
    _create_dimensions()
    for table in (
        "cost_forecast_policy_versions",
        "cost_forecast_runs",
        "cost_forecast_ledger_event_refs",
        "cost_forecast_input_lines",
        "cost_forecast_dimension_results",
    ):
        _tenant_table(table)
    _create_guards()


def downgrade() -> None:
    for table in (
        "cost_forecast_dimension_results",
        "cost_forecast_input_lines",
        "cost_forecast_ledger_event_refs",
        "cost_forecast_runs",
        "cost_forecast_policy_versions",
    ):
        count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM public.{table}")).scalar_one()
        if count:
            raise RuntimeError("0050 downgrade refused: Slice-51 rows exist")
    for table in (
        "cost_forecast_runs",
        "cost_forecast_ledger_event_refs",
        "cost_forecast_input_lines",
        "cost_forecast_dimension_results",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_verify ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS public.verify_cost_forecast_run_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_cost_forecast_run(uuid)")
    for table, trigger, function in (
        ("cost_forecast_dimension_results", "cost_forecast_dimension_guard", "cost_forecast_dimension_guard"),
        ("cost_forecast_input_lines", "cost_forecast_input_line_guard", "cost_forecast_input_line_guard"),
        ("cost_forecast_ledger_event_refs", "cost_forecast_event_ref_guard", "cost_forecast_event_ref_guard"),
        ("cost_forecast_runs", "cost_forecast_run_guard", "cost_forecast_run_guard"),
        ("cost_forecast_policy_versions", "cost_forecast_policy_guard", "cost_forecast_policy_guard"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{function}()")
    for table in (
        "cost_forecast_dimension_results",
        "cost_forecast_input_lines",
        "cost_forecast_ledger_event_refs",
        "cost_forecast_runs",
        "cost_forecast_policy_versions",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.slice51_hash(VARIADIC text[])")
    op.drop_constraint("uq_budgets_id_project_tenant", "budgets", type_="unique")
    op.drop_constraint("uq_cost_events_id_project_tenant", "cost_events", type_="unique")
