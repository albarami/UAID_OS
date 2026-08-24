"""Slice 59 stabilization-window DB proofs: assess, catalog, closure, race."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.identity import AuthenticatedActor
from app.ops.incident_service import record_support_handover
from app.ops.incidents import HandoverPayload
from app.ops.stabilization import StabilizationError, StabilizationIdempotencyConflict
from app.ops.stabilization_service import (
    assess_stabilization,
    attempt_closure,
    history_stabilization,
    latest_stabilization,
)
from app.release.monitoring_evidence import observation_unreachable, observation_valid
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.monitoring_evidence import MonitoringEvidenceRepository
from app.tenancy import TenantContext, tenant_scope
from tests.ops_stabilization_support import (
    FINDINGS_GUARD_MD5,
    MONITORING_URL,
    STABLE_HASHES,
    STABILIZATION_TABLES,
    VALID_POLICY,
    bind_and_activate_emergency_stop,
    by_seq,
    create_project,
    declare_window,
    seed_emergency_authority,
    unique_key,
    window_data,
)


@pytest.mark.db
async def test_missing_declaration_writes_nothing(inc_ctx, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    with pytest.raises(StabilizationError, match="no_window_declaration"):
        await assess_stabilization(
            ctx, inc_ctx["p1"], actor="stab-test", idempotency_key=unique_key("missing")
        )
    count = (
        await db_session.execute(
            text("SELECT count(*) FROM ops_stabilization_windows WHERE project_id=:p"),
            {"p": inc_ctx["p1"]},
        )
    ).scalar_one()
    assert count == 0


@pytest.mark.db
async def test_assess_seq5_pass_history_and_incomplete_latest_wins(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await declare_window(ctx, project)
    empty = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("empty")
    )
    mapped = by_seq(empty.criteria)
    assert empty.status == "open"
    assert empty.passed_count == 0
    assert empty.extension_required is True
    assert mapped[5].status == "not_observed"
    assert mapped[3].status == "not_observed"
    complete = await record_support_handover(
        ctx,
        project,
        actor="stab-test",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_complete"
        ),
    )
    passed = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("pass")
    )
    assert passed.passed_count == 1
    assert by_seq(passed.criteria)[5].status == "passed"
    assert by_seq(passed.criteria)[5].handover_id == complete.id
    await record_support_handover(
        ctx,
        project,
        actor="stab-test",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_incomplete"
        ),
    )
    failed = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("fail")
    )
    assert failed.passed_count == 0
    assert by_seq(failed.criteria)[5].status == "failed"
    latest = await latest_stabilization(ctx, project)
    assert latest is not None and latest.id == failed.id
    history = await history_stabilization(ctx, project, limit=5)
    assert history[0].id == failed.id
    assert {item.passed_count for item in history} <= {0, 1}


@pytest.mark.db
async def test_seq3_verified_active_fresh_is_not_evaluable(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await declare_window(ctx, project)
    async with tenant_scope(ctx) as session:
        await MonitoringEvidenceRepository(session, ctx).record_connector_verified_monitoring(
            project_id=project,
            payload={
                "provider": "generic_monitoring_api",
                "target_ref": MONITORING_URL,
                **observation_valid(3, 2),
                "observed_at": datetime.now(timezone.utc),
            },
            actor="conn",
        )
    snap = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("mon")
    )
    seq3 = by_seq(snap.criteria)[3]
    assert seq3.status == "not_evaluable"
    assert seq3.reason == "monitoring_active_app_derived_not_db_provable"
    assert snap.monitoring_target_bound is True


@pytest.mark.db
async def test_catalog_rls_append_only_and_audit_omits_owner_url(inc_ctx, admin_engine, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await declare_window(ctx, project)
    snap = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("cat")
    )
    closure = await attempt_closure(ctx, project, actor="closer")
    async with admin_engine.connect() as conn:
        for table in STABILIZATION_TABLES:
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
        for name in (
            "uq_mss_id_project_tenant",
            "uq_osh_id_project_tenant",
            "uq_ifr_id_project_tenant",
        ):
            assert (
                await conn.execute(
                    text("SELECT 1 FROM pg_constraint WHERE conname=:n"), {"n": name}
                )
            ).scalar_one() == 1
        payload = (
            await conn.execute(
                text(
                    "SELECT payload::text FROM audit_logs "
                    "WHERE action='ops_stabilization.recorded' "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            )
        ).scalar_one()
        md5 = (
            await conn.execute(
                text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
            )
        ).scalar_one()
    assert md5 == FINDINGS_GUARD_MD5
    assert "sre-owner" not in payload
    assert "checkout" not in payload
    assert "https://" not in payload
    assert "summary" not in payload
    child = (
        await db_session.execute(
            text("SELECT id FROM ops_stabilization_criterion_results WHERE window_id=:w LIMIT 1"),
            {"w": snap.id},
        )
    ).scalar_one()
    improvement = (
        await db_session.execute(
            text("SELECT id FROM ops_improvement_results WHERE window_id=:w LIMIT 1"),
            {"w": snap.id},
        )
    ).scalar_one()
    for table, row_id in (
        ("ops_stabilization_windows", snap.id),
        ("ops_stabilization_criterion_results", child),
        ("ops_improvement_results", improvement),
        ("ops_stabilization_closure_attempts", closure.id),
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(f"UPDATE {table} SET created_at = created_at WHERE id=:i"),
                    {"i": row_id},
                )
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(f"DELETE FROM {table} WHERE id=:i"), {"i": row_id})
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(f"TRUNCATE {table} CASCADE"))
    other = TenantContext(inc_ctx["t2"])
    assert await latest_stabilization(other, project) is None
    assert await latest_stabilization(other, inc_ctx["p2"]) is None


@pytest.mark.db
async def test_category_revise_leaves_historical_snapshot(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await declare_window(ctx, project)
    first = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("rev1")
    )
    revised = dict(VALID_POLICY)
    revised["duration_days"] = 30
    async with tenant_scope(ctx) as session:
        await IntakeCategoryRepository(session, ctx).revise(
            project_id=project,
            category="operations_observability_support",
            actor="stab-test",
            data=window_data(policy=revised),
        )
    latest = await latest_stabilization(ctx, project)
    assert latest is not None and latest.id == first.id
    assert latest.policy_digest == first.policy_digest
    second = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("rev2")
    )
    assert second.policy_digest != first.policy_digest


@pytest.mark.db
async def test_four_closure_refusals_leave_status_open(inc_ctx, monkeypatch):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await declare_window(ctx, project)
    await assess_stabilization(ctx, project, actor="stab-test", idempotency_key=unique_key("cl"))
    unauth = await attempt_closure(ctx, project, actor="closer")
    assert unauth.result_code == "refused_unauthenticated"
    alice = TenantContext(inc_ctx["t1"], actor=AuthenticatedActor("alice@example.test", "human"))
    await declare_window(TenantContext(inc_ctx["t1"]), inc_ctx["p1b"], data=window_data())
    await assess_stabilization(
        alice, inc_ctx["p1b"], actor="alice", idempotency_key=unique_key("alice")
    )
    same = await attempt_closure(alice, inc_ctx["p1b"], actor="alice")
    assert same.result_code == "refused_same_actor"
    bob = TenantContext(inc_ctx["t1"], actor=AuthenticatedActor("bob@example.test", "human"))
    incomplete = await attempt_closure(bob, inc_ctx["p1b"], actor="bob")
    assert incomplete.result_code == "refused_incomplete_criteria"

    async def fake_stop(*_args, **_kwargs):
        return type("Stop", (), {"state_after": "active"})()

    monkeypatch.setattr("app.repositories.ops_stabilization.latest_stop_event", fake_stop)
    latch = await attempt_closure(bob, inc_ctx["p1b"], actor="bob")
    assert latch.result_code == "refused_latch_active"
    latest = await latest_stabilization(alice, inc_ctx["p1b"])
    assert latest is not None and latest.status == "open"
    with pytest.raises(StabilizationError, match="no_stabilization_window"):
        await attempt_closure(TenantContext(inc_ctx["t2"]), inc_ctx["p2"], actor="x")


@pytest.mark.db
async def test_idempotency_conflict_and_repeatable_read_race(inc_ctx):
    ctx_a = TenantContext(inc_ctx["t1"], actor=AuthenticatedActor("a@example.test", "human"))
    ctx_b = TenantContext(inc_ctx["t1"], actor=AuthenticatedActor("b@example.test", "human"))
    project = inc_ctx["p1"]
    await declare_window(ctx_a, project)
    key = unique_key("idemp")
    first = await assess_stabilization(ctx_a, project, actor="a", idempotency_key=key)
    again = await assess_stabilization(ctx_a, project, actor="a", idempotency_key=key)
    assert first.id == again.id
    with pytest.raises(StabilizationIdempotencyConflict):
        await assess_stabilization(ctx_b, project, actor="b", idempotency_key=key)
    race_key = unique_key("race")
    results = await asyncio.gather(
        assess_stabilization(ctx_a, project, actor="a", idempotency_key=race_key),
        assess_stabilization(ctx_a, project, actor="a", idempotency_key=race_key),
    )
    assert {item.id for item in results} == {results[0].id}


@pytest.mark.db
async def test_frozen_hashes_and_verified_unreadable_seq3(inc_ctx):
    for path, digest in STABLE_HASHES.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await declare_window(ctx, project)
    async with tenant_scope(ctx) as session:
        await MonitoringEvidenceRepository(session, ctx).record_connector_verified_monitoring(
            project_id=project,
            payload={
                "provider": "generic_monitoring_api",
                "target_ref": MONITORING_URL,
                **observation_unreachable(),
                "observed_at": datetime.now(timezone.utc),
            },
            actor="conn",
        )
    snap = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("unread")
    )
    seq3 = by_seq(snap.criteria)[3]
    assert seq3.status == "not_evaluable"
    assert seq3.reason == "monitoring_evidence_unreadable"
    assert seq3.status != "failed"


@pytest.mark.db
async def test_real_emergency_latch_refuses_closure_and_leaves_window_open(inc_ctx, db_session, admin_engine):
    member = TenantContext(inc_ctx["t1"], actor=AuthenticatedActor("stop-a@example.test", "human"))
    closer = TenantContext(inc_ctx["t1"], actor=AuthenticatedActor("stop-b@example.test", "human"))
    project = await create_project(member, name="StabLatch", slug=unique_key("stab-latch"))
    await declare_window(member, project)
    window = await assess_stabilization(
        member, project, actor="alice", idempotency_key=unique_key("latch-win")
    )
    await seed_emergency_authority(member, project, admin_engine=admin_engine)
    bound, activated = await bind_and_activate_emergency_stop(
        member,
        project,
        bind_key=unique_key("stab-bind"),
        activate_key=unique_key("stab-activate"),
    )
    assert bound.binding_id is not None
    assert activated.state == "active"
    refused = await attempt_closure(closer, project, actor="bob")
    assert refused.result_code == "refused_latch_active"
    persisted = (
        await db_session.execute(
            text("SELECT result_code FROM ops_stabilization_closure_attempts WHERE id=:id"),
            {"id": refused.id},
        )
    ).scalar_one()
    assert persisted == "refused_latch_active"
    latest = await latest_stabilization(member, project)
    assert latest is not None
    assert latest.id == window.id
    assert latest.status == "open"


@pytest.mark.db
async def test_assess_leaves_a5_and_readiness_bit_stable(inc_ctx):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.readiness import ReadinessRepository

    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await declare_window(ctx, project)
    async with tenant_scope(ctx) as session:
        before_a5 = (await ProductionAutonomyRepository(session, ctx).evaluate(project)).to_dict()
        before_ready = (await ReadinessRepository(session, ctx).evaluate(project)).to_dict()
    recorded = await assess_stabilization(
        ctx, project, actor="stab-test", idempotency_key=unique_key("a5-stable")
    )
    assert recorded.status == "open"
    async with tenant_scope(ctx) as session:
        after_a5 = (await ProductionAutonomyRepository(session, ctx).evaluate(project)).to_dict()
        after_ready = (await ReadinessRepository(session, ctx).evaluate(project)).to_dict()
    assert before_a5 == after_a5
    assert before_ready == after_ready
    assert after_a5["ruleset_version"] == "slice54.v1"
    assert after_a5["can_go_live_autonomously"] is False
    assert after_ready["ruleset_version"] == "slice20.v1"
    assert after_ready["can_go_live_autonomously"] is False
