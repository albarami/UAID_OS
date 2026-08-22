"""ops observation runs and per-class signal results

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-22

Slice 56 — post-launch §25.1 signal assessment. Additive. Does not change A5,
readiness, or the control loop.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.ops.db_checks import CHILD_CHECK_CONSTRAINTS

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_HASH = r"^sha256:[0-9a-f]{64}$"
_CLASSES = (
    "uptime",
    "error_rates",
    "latency",
    "job_failures",
    "security_alerts",
    "user_journey_failures",
    "data_quality_issues",
    "cost_anomalies",
    "model_output_drift",
    "support_tickets",
    "incident_reports",
)
_REASONS = (
    "no_uptime_source",
    "no_error_rate_source",
    "no_latency_source",
    "no_post_launch_security_alert_source",
    "no_journey_failure_source",
    "no_data_quality_source",
    "no_model_drift_source",
    "no_support_ticket_source",
    "no_incident_store",
    "no_job_slo_threshold",
    "cost_ledger_recorded",
    "cost_no_budget",
    "cost_budget_exceeded",
    "cost_daily_budget_exceeded",
    "cost_within_budget",
    "uaid_runtime_failed_run_count",
    "caller_sample_accepted",
    "caller_threshold_ok",
    "caller_threshold_breached",
)
_IN = ", ".join(repr(item) for item in _CLASSES)
_REASON_IN = ", ".join(repr(item) for item in _REASONS)
_SEQ_CLASS = " OR ".join(
    f"(seq={index} AND signal_class='{name}')" for index, name in enumerate(_CLASSES, start=1)
)
_TABLES = ("ops_observation_runs", "ops_signal_results")


def _append_only(table: str) -> None:
    op.execute(
        f"""CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$"""
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
    )


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def upgrade() -> None:
    op.create_table(
        "ops_observation_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column("input_digest", sa.Text(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("caller_supplied_count", sa.Integer(), nullable=False),
        sa.Column("not_observed_count", sa.Integer(), nullable=False),
        sa.Column("breached_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ruleset_version='slice56.v1'", name="ruleset_version"),
        sa.CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        sa.CheckConstraint(f"request_digest ~ '{_HASH}'", name="request_digest"),
        sa.CheckConstraint(f"input_digest ~ '{_HASH}'", name="input_digest"),
        sa.CheckConstraint("signal_count = 11", name="signal_count"),
        sa.CheckConstraint(
            "observed_count >= 0 AND caller_supplied_count >= 0 AND not_observed_count >= 0 "
            "AND observed_count + caller_supplied_count + not_observed_count = 11",
            name="status_counts",
        ),
        sa.CheckConstraint("breached_count BETWEEN 0 AND 11", name="breached_count"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_observation_runs_id_project_tenant"
        ),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_ops_observation_runs_idempotency"
        ),
    )
    op.create_index(
        "ix_ops_observation_runs_latest",
        "ops_observation_runs",
        ["tenant_id", "project_id", "created_at"],
    )
    op.create_table(
        "ops_signal_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("signal_class", sa.Text(), nullable=False),
        sa.Column("observation_status", sa.Text(), nullable=False),
        sa.Column("truth_tier", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.UUID(), nullable=True),
        sa.Column("source_digest", sa.Text(), nullable=True),
        sa.Column("window_kind", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("threshold_provenance", sa.Text(), nullable=False),
        sa.Column("threshold_kind", sa.Text(), nullable=False),
        sa.Column("threshold_int", sa.Integer(), nullable=True),
        sa.Column("threshold_ratio", sa.Numeric(8, 6), nullable=True),
        sa.Column("threshold_money", sa.Numeric(18, 6), nullable=True),
        sa.Column("threshold_money_daily", sa.Numeric(18, 6), nullable=True),
        sa.Column("metric_kind", sa.Text(), nullable=False),
        sa.Column("metric_int", sa.Integer(), nullable=True),
        sa.Column("metric_ratio", sa.Numeric(8, 6), nullable=True),
        sa.Column("metric_money", sa.Numeric(18, 6), nullable=True),
        sa.Column("metric_money_daily", sa.Numeric(18, 6), nullable=True),
        sa.Column("threshold_state", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("seq BETWEEN 1 AND 11", name="seq_bounded"),
        sa.CheckConstraint(f"signal_class IN ({_IN})", name="signal_class"),
        sa.CheckConstraint(_SEQ_CLASS, name="seq_class_pair"),
        sa.CheckConstraint(
            "observation_status IN ('observed','caller_supplied_unverified','not_observed')",
            name="observation_status",
        ),
        sa.CheckConstraint(
            "truth_tier IN ('none','system_derived_ledger','caller_supplied_unverified')",
            name="truth_tier",
        ),
        sa.CheckConstraint(
            "source_kind IN ('none','cost_ledger','uaid_runtime','caller_supplied')",
            name="source_kind",
        ),
        sa.CheckConstraint(
            "source_table IN ('none','cost_events_and_budgets','run_steps','caller_sample')",
            name="source_table",
        ),
        sa.CheckConstraint(
            "window_kind IN ('none','cumulative_project','caller_declared')", name="window_kind"
        ),
        sa.CheckConstraint(f"reason_code IN ({_REASON_IN})", name="reason_code"),
        sa.CheckConstraint(
            "threshold_provenance IN ('none','recorded_budget','caller_supplied_unverified')",
            name="threshold_provenance",
        ),
        sa.CheckConstraint(
            "threshold_kind IN ('none','cost_stop','caller_count','caller_ratio','caller_ms')",
            name="threshold_kind",
        ),
        sa.CheckConstraint(
            "metric_kind IN ('none','count','ratio','milliseconds','money')", name="metric_kind"
        ),
        sa.CheckConstraint(
            "threshold_state IN ('not_evaluable','ok','breached')", name="threshold_state"
        ),
        sa.CheckConstraint(
            f"source_digest IS NULL OR source_digest ~ '{_HASH}'", name="source_digest"
        ),
        sa.CheckConstraint(
            "(window_kind='none' AND window_start IS NULL AND window_end IS NULL) OR "
            "(window_kind='cumulative_project' AND window_start IS NULL "
            "AND window_end IS NOT NULL) OR "
            "(window_kind='caller_declared' AND window_start IS NOT NULL "
            "AND window_end IS NOT NULL AND window_start < window_end)",
            name="window_shape",
        ),
        sa.CheckConstraint(
            "(signal_class='cost_anomalies' AND metric_money_daily IS NOT NULL) OR "
            "(signal_class<>'cost_anomalies' AND metric_money_daily IS NULL)",
            name="cost_daily_metric",
        ),
        sa.CheckConstraint(
            "(observation_status<>'not_observed') OR ("
            "truth_tier='none' AND source_kind='none' AND source_table='none' "
            "AND source_ref IS NULL AND source_digest IS NULL AND metric_kind='none' "
            "AND metric_int IS NULL AND metric_ratio IS NULL AND metric_money IS NULL "
            "AND metric_money_daily IS NULL AND threshold_kind='none' "
            "AND threshold_provenance='none' AND threshold_int IS NULL "
            "AND threshold_ratio IS NULL AND threshold_money IS NULL "
            "AND threshold_money_daily IS NULL AND threshold_state='not_evaluable' "
            "AND window_kind='none' AND window_start IS NULL AND window_end IS NULL)",
            name="not_observed_shape",
        ),
        sa.CheckConstraint(
            "(observation_status<>'observed') OR ("
            "truth_tier='system_derived_ledger' AND source_ref IS NULL "
            "AND source_digest IS NOT NULL AND window_kind='cumulative_project')",
            name="observed_shape",
        ),
        sa.CheckConstraint(
            "(observation_status<>'caller_supplied_unverified') OR ("
            "truth_tier='caller_supplied_unverified' AND source_kind='caller_supplied' "
            "AND source_table='caller_sample' AND source_digest IS NOT NULL "
            "AND window_kind='caller_declared' "
            "AND threshold_provenance='caller_supplied_unverified' "
            "AND threshold_state IN ('ok','breached') AND metric_money IS NULL "
            "AND metric_money_daily IS NULL AND threshold_money IS NULL "
            "AND threshold_money_daily IS NULL AND "
            "((threshold_state='ok' AND reason_code='caller_threshold_ok') OR "
            "(threshold_state='breached' AND reason_code='caller_threshold_breached')))",
            name="caller_shape",
        ),
        sa.CheckConstraint(
            "(signal_class NOT IN ('uptime','security_alerts','support_tickets',"
            "'incident_reports')) OR observation_status='not_observed'",
            name="locked_not_observed",
        ),
        sa.CheckConstraint(
            "(signal_class NOT IN ('job_failures','cost_anomalies')) OR "
            "observation_status='observed'",
            name="locked_observed",
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in CHILD_CHECK_CONSTRAINTS],
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "ops_observation_runs.id",
                "ops_observation_runs.project_id",
                "ops_observation_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_ops_signal_results_run_seq"),
        sa.UniqueConstraint("run_id", "signal_class", name="uq_ops_signal_results_run_class"),
    )
    op.create_index("ix_ops_signal_results_run", "ops_signal_results", ["tenant_id", "run_id"])
    op.execute(
        """
        CREATE FUNCTION public.ops_signal_results_window_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE parent_as_of timestamptz;
        BEGIN
            SELECT as_of INTO parent_as_of FROM public.ops_observation_runs WHERE id = NEW.run_id;
            IF parent_as_of IS NULL THEN
                RAISE EXCEPTION 'ops signal result parent run % missing', NEW.run_id;
            END IF;
            IF NEW.window_kind = 'none' THEN
                IF NEW.window_start IS NOT NULL OR NEW.window_end IS NOT NULL THEN
                    RAISE EXCEPTION 'none window must have null bounds';
                END IF;
            ELSIF NEW.window_kind = 'cumulative_project' THEN
                IF NEW.window_start IS NOT NULL OR NEW.window_end IS NULL
                   OR NEW.window_end > parent_as_of THEN
                    RAISE EXCEPTION 'cumulative window_end must be <= parent as_of';
                END IF;
            ELSIF NEW.window_kind = 'caller_declared' THEN
                IF NEW.window_start IS NULL OR NEW.window_end IS NULL
                   OR NOT (NEW.window_start < NEW.window_end)
                   OR NEW.window_end > parent_as_of THEN
                    RAISE EXCEPTION 'caller window must satisfy start < end <= parent as_of';
                END IF;
            ELSE
                RAISE EXCEPTION 'unknown window_kind';
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER ops_signal_results_window_guard
            BEFORE INSERT ON public.ops_signal_results
            FOR EACH ROW EXECUTE FUNCTION public.ops_signal_results_window_guard()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_observation_runs_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE child_count int; observed int; caller int; missing int; breached int;
        BEGIN
            SELECT count(*),
                   count(*) FILTER (WHERE observation_status='observed'),
                   count(*) FILTER (WHERE observation_status='caller_supplied_unverified'),
                   count(*) FILTER (WHERE observation_status='not_observed'),
                   count(*) FILTER (WHERE threshold_state='breached')
              INTO child_count, observed, caller, missing, breached
              FROM public.ops_signal_results WHERE run_id = NEW.id;
            IF NEW.signal_count IS DISTINCT FROM 11
               OR child_count IS DISTINCT FROM 11
               OR NEW.observed_count IS DISTINCT FROM observed
               OR NEW.caller_supplied_count IS DISTINCT FROM caller
               OR NEW.not_observed_count IS DISTINCT FROM missing
               OR NEW.breached_count IS DISTINCT FROM breached THEN
                RAISE EXCEPTION 'ops observation run % child counts do not match', NEW.id;
            END IF;
            IF (SELECT count(DISTINCT seq) FROM public.ops_signal_results
                WHERE run_id = NEW.id AND seq BETWEEN 1 AND 11) IS DISTINCT FROM 11 THEN
                RAISE EXCEPTION 'ops observation run % seq set incomplete', NEW.id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_observation_runs_count_match
            AFTER INSERT ON public.ops_observation_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_observation_runs_count_match()
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.ops_signal_results_count_match() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE stored_signal int; stored_observed int; stored_caller int;
                stored_missing int; stored_breached int; child_count int;
                observed int; caller int; missing int; breached int;
        BEGIN
            SELECT signal_count, observed_count, caller_supplied_count,
                   not_observed_count, breached_count
              INTO stored_signal, stored_observed, stored_caller, stored_missing, stored_breached
              FROM public.ops_observation_runs WHERE id = NEW.run_id;
            SELECT count(*),
                   count(*) FILTER (WHERE observation_status='observed'),
                   count(*) FILTER (WHERE observation_status='caller_supplied_unverified'),
                   count(*) FILTER (WHERE observation_status='not_observed'),
                   count(*) FILTER (WHERE threshold_state='breached')
              INTO child_count, observed, caller, missing, breached
              FROM public.ops_signal_results WHERE run_id = NEW.run_id;
            IF stored_signal IS DISTINCT FROM 11
               OR child_count IS DISTINCT FROM stored_signal
               OR stored_observed IS DISTINCT FROM observed
               OR stored_caller IS DISTINCT FROM caller
               OR stored_missing IS DISTINCT FROM missing
               OR stored_breached IS DISTINCT FROM breached THEN
                RAISE EXCEPTION 'ops observation run % child counts do not match', NEW.run_id;
            END IF;
            RETURN NULL;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER ops_signal_results_count_match
            AFTER INSERT ON public.ops_signal_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION public.ops_signal_results_count_match()
        """
    )
    for table in _TABLES:
        _append_only(table)
        _rls(table)


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.ops_observation_runs)
               OR EXISTS (SELECT 1 FROM public.ops_signal_results) THEN
                RAISE EXCEPTION 'cannot downgrade Slice 56 while ops-signal rows exist';
            END IF;
        END
        $fn$
        """
    )
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT ON public.{table} FROM uaid_app")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute("DROP TRIGGER IF EXISTS ops_signal_results_count_match ON public.ops_signal_results")
    op.execute(
        "DROP TRIGGER IF EXISTS ops_observation_runs_count_match ON public.ops_observation_runs"
    )
    op.execute("DROP FUNCTION IF EXISTS public.ops_signal_results_count_match()")
    op.execute("DROP FUNCTION IF EXISTS public.ops_observation_runs_count_match()")
    op.execute(
        "DROP TRIGGER IF EXISTS ops_signal_results_window_guard ON public.ops_signal_results"
    )
    op.execute("DROP FUNCTION IF EXISTS public.ops_signal_results_window_guard()")
    op.drop_index("ix_ops_signal_results_run", table_name="ops_signal_results")
    op.drop_table("ops_signal_results")
    op.drop_index("ix_ops_observation_runs_latest", table_name="ops_observation_runs")
    op.drop_table("ops_observation_runs")
