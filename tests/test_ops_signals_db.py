"""Slice 56 §25.1 ops-signal assessment — DB, RLS, trigger, and CHECK proofs."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.ops.collect import collect_ops_signals
from app.ops.signals import HISTORY_LIMIT_MAX, OpsSignalError, OpsSignalIdempotencyConflict
from app.release.production_autonomy import evaluate_production_autonomy
from app.tenancy import TenantContext, tenant_scope
from tests.ops_signals_support import OPS_DIGEST, OPS_MISSING, new_parent


def _by_class(rows):
    return {row.signal_class: row for row in rows}


@pytest.mark.db
async def test_collect_persists_eleven_children_and_is_idempotent(ops_ctx, admin_engine):
    from app.repositories.cost import BudgetRepository, CostEventRepository
    from app.repositories.ops_signals import OpsSignalRepository

    t1, p1 = ops_ctx["t1"], ops_ctx["p1"]
    ctx = TenantContext(t1)
    key = f"ops-default-{ops_ctx['suffix']}"
    first = await collect_ops_signals(ctx, p1, actor="ops-test", idempotency_key=key)
    assert len(first.signals) == 11
    assert (first.observed_count, first.caller_supplied_count, first.not_observed_count) == (
        2,
        0,
        9,
    )
    retry = await collect_ops_signals(ctx, p1, actor="ops-test", idempotency_key=key)
    assert retry.id == first.id
    assert retry.request_digest == first.request_digest
    changed = [
        {
            "signal_class": "error_rates",
            "metric_ratio": "0.01",
            "threshold_ratio": "0.02",
            "window_start": datetime.now(timezone.utc) - timedelta(minutes=5),
            "window_end": datetime.now(timezone.utc),
        }
    ]
    with pytest.raises(OpsSignalIdempotencyConflict):
        await collect_ops_signals(ctx, p1, actor="ops-test", samples=changed, idempotency_key=key)
    async with tenant_scope(ctx) as session:
        events = CostEventRepository(session, ctx)
        await events.record(
            project_id=p1,
            component="model_inference",
            amount_usd="3.00",
            actor="ops-test",
            occurred_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        await BudgetRepository(session, ctx).upsert(
            project_id=p1, max_total_cost_usd="100", max_daily_cost_usd="50", actor="ops-test"
        )
    spent = await collect_ops_signals(
        ctx, p1, actor="ops-test", idempotency_key=f"ops-spent-{ops_ctx['suffix']}"
    )
    cost = _by_class(spent.signals)["cost_anomalies"]
    assert cost.reason_code == "cost_within_budget"
    assert cost.metric_money == Decimal("3.000000") or cost.metric_money == Decimal("3")
    async with tenant_scope(ctx) as session:
        repo = OpsSignalRepository(session, ctx)
        latest = await repo.latest(p1)
        history = await repo.history(p1)
        assert latest is not None and latest.id == spent.id
        assert len(history) >= 2
        assert history[0].id == spent.id
        with pytest.raises(OpsSignalError):
            await repo.history(p1, limit=0)
        with pytest.raises(OpsSignalError):
            await repo.history(p1, limit=HISTORY_LIMIT_MAX + 1)
    other = TenantContext(ops_ctx["t2"])
    async with tenant_scope(other) as session:
        assert await OpsSignalRepository(session, other).latest(p1) is None
    before = evaluate_production_autonomy(p1, readiness_level="R2")
    await collect_ops_signals(
        ctx, p1, actor="ops-test", idempotency_key=f"ops-a5-{ops_ctx['suffix']}"
    )
    after = evaluate_production_autonomy(p1, readiness_level="R2")
    assert (
        before.to_dict()["can_go_live_autonomously"]
        is after.to_dict()["can_go_live_autonomously"]
        is False
    )
    async with admin_engine.connect() as conn:
        payload = json.dumps(
            (
                await conn.execute(
                    text(
                        "SELECT actor, action, target, payload FROM audit_logs "
                        "WHERE tenant_id=:t AND action='ops_signals.recorded'"
                    ),
                    {"t": t1},
                )
            )
            .mappings()
            .all(),
            default=str,
        )
    assert "http://" not in payload and "https://" not in payload
    assert "finding" not in payload.lower()


@pytest.mark.db
async def test_job_failures_count_run_steps_not_project_status(ops_ctx, admin_engine):
    t1, p1, run = ops_ctx["t1"], ops_ctx["p1"], ops_ctx["run"]
    ctx = TenantContext(t1)
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO run_steps (tenant_id, project_id, run_id, event_type, created_at) "
                "VALUES (:t,:p,:r,'run_failed', now() - interval '1 minute')"
            ),
            {"t": t1, "p": p1, "r": run},
        )
        await conn.execute(
            text(
                "INSERT INTO run_steps (tenant_id, project_id, run_id, event_type, created_at) "
                "VALUES (:t,:p,:r,'run_failed', now() + interval '1 hour')"
            ),
            {"t": t1, "p": p1, "r": run},
        )
    snapshot = await collect_ops_signals(
        ctx, p1, actor="ops-test", idempotency_key=f"ops-jobs-{ops_ctx['suffix']}"
    )
    jobs = _by_class(snapshot.signals)["job_failures"]
    assert jobs.metric_int == 1
    assert jobs.threshold_state == "not_evaluable"


@pytest.mark.db
async def test_catalog_triggers_window_guard_and_count_match(ops_ctx, admin_engine, db_session):
    t1, p1 = ops_ctx["t1"], ops_ctx["p1"]
    ctx = TenantContext(t1)
    await collect_ops_signals(
        ctx, p1, actor="ops-test", idempotency_key=f"ops-cat-{ops_ctx['suffix']}"
    )
    async with admin_engine.connect() as conn:
        for table in ("ops_observation_runs", "ops_signal_results"):
            row = (
                await conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": table},
                )
            ).one()
            assert row == (True, True)
            grants = {
                item[0]
                for item in (
                    await conn.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:t AND grantee='uaid_app'"
                        ),
                        {"t": table},
                    )
                ).all()
            }
            assert grants == {"SELECT", "INSERT"}
        assert (
            await conn.execute(
                text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
            )
        ).scalar_one() == "808036faf2660d6810aeca4342e6f1ac"
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text("UPDATE ops_observation_runs SET observed_count=0"))
    run_id, as_of = (
        await db_session.execute(
            text(
                "SELECT id, as_of FROM ops_observation_runs WHERE project_id=:p "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"p": p1},
        )
    ).one()
    with pytest.raises(DBAPIError, match="cumulative window_end"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_signal_results ("
                    "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                    "truth_tier, source_kind, source_table, source_digest, window_kind, "
                    "window_end, reason_code, threshold_provenance, threshold_kind, "
                    "metric_kind, metric_int, threshold_state) VALUES ("
                    ":t,:p,:r,4,'job_failures','observed','system_derived_ledger',"
                    "'uaid_runtime','run_steps',:d,'cumulative_project', :late,"
                    "'uaid_runtime_failed_run_count','none','none','count',0,'not_evaluable')"
                ),
                {
                    "t": t1,
                    "p": p1,
                    "r": run_id,
                    "d": OPS_DIGEST,
                    "late": as_of + timedelta(hours=1),
                },
            )
    assert (
        await db_session.execute(
            text(
                "SELECT 1 FROM ops_signal_results WHERE run_id=:r AND seq=4 AND window_end=:as_of"
            ),
            {"r": run_id, "as_of": as_of},
        )
    ).scalar() == 1
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_observation_runs ("
                    "tenant_id, project_id, ruleset_version, idempotency_key, request_digest, "
                    "input_digest, as_of, signal_count, observed_count, caller_supplied_count, "
                    "not_observed_count, breached_count) VALUES ("
                    ":t,:p,'slice56.v1',:k,:d,:d, now(), 11, 2, 0, 9, 0)"
                ),
                {"t": t1, "p": p1, "k": f"zero-child-{ops_ctx['suffix']}", "d": OPS_DIGEST},
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_signal_results ("
                    "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                    "truth_tier, source_kind, source_table, window_kind, reason_code, "
                    "threshold_provenance, threshold_kind, metric_kind, threshold_state) VALUES ("
                    ":t,:p,:r,12,'uptime','not_observed','none','none','none','none',"
                    "'no_uptime_source','none','none','none','not_evaluable')"
                ),
                {"t": t1, "p": p1, "r": run_id},
            )
    with pytest.raises(DBAPIError, match="child counts"):
        async with db_session.begin_nested():
            parent_id, parent_as_of = await new_parent(
                db_session, t1, p1, f"ten-child-{ops_ctx['suffix']}"
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
                {"t": t1, "p": p1, "r": parent_id, "d": OPS_DIGEST, "as_of": parent_as_of},
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
                        "r": parent_id,
                        "seq": seq,
                        "name": name,
                        "reason": reason,
                    },
                )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.db
async def test_concurrent_collect_retries_without_unique_violation(ops_ctx):
    ctx = TenantContext(ops_ctx["t1"])
    key = f"ops-race-{ops_ctx['suffix']}"
    results = await asyncio.gather(
        collect_ops_signals(ctx, ops_ctx["p1"], actor="ops-a", idempotency_key=key),
        collect_ops_signals(ctx, ops_ctx["p1"], actor="ops-b", idempotency_key=key),
    )
    assert {item.id for item in results} == {results[0].id}
    assert all(item.request_digest == results[0].request_digest for item in results)
