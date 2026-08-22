"""Slice 56 class/source/metric/threshold CHECK and caller-window proofs."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.ops_signals_support import OPS_DIGEST, OPS_MISSING, new_parent


@pytest.mark.db
async def test_matrix_checks_and_caller_window_guard(ops_ctx, db_session):
    t1, p1 = ops_ctx["t1"], ops_ctx["p1"]
    probes = [
        (
            "job_failures_shape",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, threshold_money, "
            "metric_kind, metric_money, threshold_state) VALUES ("
            ":t,:p,:r,4,'job_failures','observed','system_derived_ledger',"
            "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
            "'cost_within_budget','recorded_budget','cost_stop',100,"
            "'money',1,'ok')",
        ),
        (
            "not_observed_shape",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, window_kind, reason_code, "
            "threshold_provenance, threshold_kind, metric_kind, metric_int, "
            "threshold_state) VALUES ("
            ":t,:p,:r,1,'uptime','not_observed','none','none','none','none',"
            "'no_uptime_source','none','none','count',1,'not_evaluable')",
        ),
        (
            "metric_ratio",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, "
            "window_start, window_end, reason_code, threshold_provenance, threshold_kind, "
            "threshold_ratio, metric_kind, metric_ratio, threshold_state) VALUES ("
            ":t,:p,:r,2,'error_rates','caller_supplied_unverified',"
            "'caller_supplied_unverified','caller_supplied','caller_sample',:d,"
            "'caller_declared',:start,:as_of,'caller_threshold_ok',"
            "'caller_supplied_unverified','caller_ratio',1,'ratio',2,'ok')",
        ),
        (
            "cost_daily_metric",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, metric_kind, metric_money, "
            "threshold_state) VALUES ("
            ":t,:p,:r,8,'cost_anomalies','observed','system_derived_ledger',"
            "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
            "'cost_no_budget','none','none','money',0,'not_evaluable')",
        ),
        (
            "cost_daily_metric",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, metric_kind, metric_int, "
            "metric_money_daily, threshold_state) VALUES ("
            ":t,:p,:r,4,'job_failures','observed','system_derived_ledger',"
            "'uaid_runtime','run_steps',:d,'cumulative_project',:as_of,"
            "'uaid_runtime_failed_run_count','none','none','count',0,1,'not_evaluable')",
        ),
        (
            "sampleable_not_ledger|caller_ratio_shape",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, metric_kind, metric_int, "
            "threshold_state) VALUES ("
            ":t,:p,:r,2,'error_rates','observed','system_derived_ledger',"
            "'uaid_runtime','run_steps',:d,'cumulative_project',:as_of,"
            "'uaid_runtime_failed_run_count','none','none','count',0,'not_evaluable')",
        ),
        (
            "metric_money_daily_nonneg",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, metric_kind, metric_money, "
            "metric_money_daily, threshold_state) VALUES ("
            ":t,:p,:r,8,'cost_anomalies','observed','system_derived_ledger',"
            "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
            "'cost_no_budget','none','none','money',0,-1,'not_evaluable')",
        ),
        (
            "metric_money_nonneg",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, metric_kind, metric_money, "
            "metric_money_daily, threshold_state) VALUES ("
            ":t,:p,:r,8,'cost_anomalies','observed','system_derived_ledger',"
            "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
            "'cost_no_budget','none','none','money','NaN'::numeric,0,'not_evaluable')",
        ),
        (
            "metric_money_daily_nonneg",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, metric_kind, metric_money, "
            "metric_money_daily, threshold_state) VALUES ("
            ":t,:p,:r,8,'cost_anomalies','observed','system_derived_ledger',"
            "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
            "'cost_no_budget','none','none','money',0,'NaN'::numeric,'not_evaluable')",
        ),
        (
            "threshold_money_nonneg|cost_anomalies_shape",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, threshold_money, "
            "metric_kind, metric_money, metric_money_daily, threshold_state) VALUES ("
            ":t,:p,:r,8,'cost_anomalies','observed','system_derived_ledger',"
            "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
            "'cost_budget_exceeded','recorded_budget','cost_stop','NaN'::numeric,"
            "'money',10,0,'breached')",
        ),
        (
            "threshold_money_daily_nonneg|cost_anomalies_shape",
            "INSERT INTO ops_signal_results ("
            "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
            "truth_tier, source_kind, source_table, source_digest, window_kind, window_end, "
            "reason_code, threshold_provenance, threshold_kind, threshold_money, "
            "threshold_money_daily, metric_kind, metric_money, metric_money_daily, "
            "threshold_state) VALUES ("
            ":t,:p,:r,8,'cost_anomalies','observed','system_derived_ledger',"
            "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
            "'cost_daily_budget_exceeded','recorded_budget','cost_stop',100,"
            "'NaN'::numeric,'money',1,1,'breached')",
        ),
    ]
    for index, (fragment, sql) in enumerate(probes):
        with pytest.raises(DBAPIError, match=fragment):
            async with db_session.begin_nested():
                parent_id, as_of = await new_parent(
                    db_session, t1, p1, f"matrix-{index}-{ops_ctx['suffix']}"
                )
                await db_session.execute(
                    text(sql),
                    {
                        "t": t1,
                        "p": p1,
                        "r": parent_id,
                        "d": OPS_DIGEST,
                        "as_of": as_of,
                        "start": as_of - timedelta(hours=1),
                    },
                )
    with pytest.raises(DBAPIError, match="caller window"):
        async with db_session.begin_nested():
            parent_id, as_of = await new_parent(
                db_session, t1, p1, f"caller-window-{ops_ctx['suffix']}"
            )
            await db_session.execute(
                text(
                    "INSERT INTO ops_signal_results ("
                    "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                    "truth_tier, source_kind, source_table, source_digest, window_kind, "
                    "window_start, window_end, reason_code, threshold_provenance, "
                    "threshold_kind, threshold_ratio, metric_kind, metric_ratio, "
                    "threshold_state) VALUES ("
                    ":t,:p,:r,2,'error_rates','caller_supplied_unverified',"
                    "'caller_supplied_unverified','caller_supplied','caller_sample',:d,"
                    "'caller_declared',:start,:late,'caller_threshold_ok',"
                    "'caller_supplied_unverified','caller_ratio',0.2,'ratio',0.1,'ok')"
                ),
                {
                    "t": t1,
                    "p": p1,
                    "r": parent_id,
                    "d": OPS_DIGEST,
                    "start": as_of - timedelta(hours=1),
                    "late": as_of + timedelta(hours=1),
                },
            )
    with pytest.raises(DBAPIError, match="child counts"):
        async with db_session.begin_nested():
            bad_id, bad_as_of = await new_parent(
                db_session, t1, p1, f"counts-{ops_ctx['suffix']}", observed=3, missing=8
            )
            await db_session.execute(
                text(
                    "INSERT INTO ops_signal_results ("
                    "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                    "truth_tier, source_kind, source_table, source_digest, window_kind, "
                    "window_end, reason_code, threshold_provenance, threshold_kind, "
                    "metric_kind, metric_int, threshold_state) VALUES ("
                    ":t,:p,:r,4,'job_failures','observed','system_derived_ledger',"
                    "'uaid_runtime','run_steps',:d,'cumulative_project', :as_of,"
                    "'uaid_runtime_failed_run_count','none','none','count',0,'not_evaluable')"
                ),
                {"t": t1, "p": p1, "r": bad_id, "d": OPS_DIGEST, "as_of": bad_as_of},
            )
            await db_session.execute(
                text(
                    "INSERT INTO ops_signal_results ("
                    "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                    "truth_tier, source_kind, source_table, source_digest, window_kind, "
                    "window_end, reason_code, threshold_provenance, threshold_kind, "
                    "metric_kind, metric_money, metric_money_daily, threshold_state) VALUES ("
                    ":t,:p,:r,8,'cost_anomalies','observed','system_derived_ledger',"
                    "'cost_ledger','cost_events_and_budgets',:d,'cumulative_project',:as_of,"
                    "'cost_no_budget','none','none','money',0,0,'not_evaluable')"
                ),
                {"t": t1, "p": p1, "r": bad_id, "d": OPS_DIGEST, "as_of": bad_as_of},
            )
            for seq, name, reason in OPS_MISSING:
                await db_session.execute(
                    text(
                        "INSERT INTO ops_signal_results ("
                        "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                        "truth_tier, source_kind, source_table, window_kind, reason_code, "
                        "threshold_provenance, threshold_kind, metric_kind, threshold_state) "
                        "VALUES (:t,:p,:r,:seq,:name,'not_observed','none','none','none','none',"
                        ":reason,'none','none','none','not_evaluable')"
                    ),
                    {
                        "t": t1,
                        "p": p1,
                        "r": bad_id,
                        "seq": seq,
                        "name": name,
                        "reason": reason,
                    },
                )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
