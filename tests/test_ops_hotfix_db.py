"""Slice 58 hotfix-intent DB proofs: policy-first results, latch, RLS, context FKs."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.ops.hotfix import MATRIX_ACTIONS
from app.ops.hotfix_service import (
    evaluate_hotfix_intent,
    history_hotfix_intent,
    latest_hotfix_intent,
)
from app.ops.incident_service import open_incident
from app.ops.incidents import IncidentPayload
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.emergency_controls import assert_project_not_stopped
from app.repositories.ops_hotfix import OpsHotfixRepository
from app.tenancy import TenantContext, tenant_scope
from tests.ops_hotfix_support import HOTFIX_TABLES, incident_payload, set_policy, unique_key


def _by_seq(actions):
    return {child.seq: child for child in actions}


@pytest.mark.db
async def test_a2_allow_writes_local_plans_and_null_context_fks(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await set_policy(ctx, project, 2)
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=incident_payload(),
        idempotency_key=unique_key("inc"),
    )
    snap = await evaluate_hotfix_intent(
        ctx,
        project,
        incident.id,
        actor="hotfix-test",
        idempotency_key=unique_key("hf"),
    )
    mapped = _by_seq(snap.actions)
    assert mapped[3].execution_posture == "local_branch_plan_written"
    assert mapped[4].execution_posture == "local_pr_plan_written"
    assert mapped[3].plan_id is not None
    assert mapped[4].plan_id is not None
    assert mapped[5].reason_code == "plan_denied_by_policy"
    assert snap.rollback_verification_run_id is None
    assert snap.emergency_rollback_authorization_id is None
    assert snap.rollback_run_present is False
    latest = await latest_hotfix_intent(ctx, project, incident.id)
    assert latest is not None and latest.id == snap.id
    history = await history_hotfix_intent(ctx, project, incident.id, limit=5)
    assert history[0].id == snap.id


@pytest.mark.db
async def test_a0_and_missing_policy_write_zero_plans(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=IncidentPayload(category="error", severity="low", summary="missing"),
        idempotency_key=unique_key("inc-miss"),
    )
    missing = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-miss")
    )
    assert all(child.plan_id is None for child in missing.actions)
    await set_policy(ctx, project, 0)
    a0 = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-a0")
    )
    assert all(child.reason_code == "plan_denied_by_policy" for child in a0.actions)


@pytest.mark.db
async def test_staging_override_and_a3_allow_residual(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await set_policy(ctx, project, 3, {"deploy_staging": {"requires_approval": True}})
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=incident_payload(),
        idempotency_key=unique_key("inc-st"),
    )
    needs = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-st")
    )
    assert _by_seq(needs.actions)[5].reason_code == "plan_needs_approval"
    await set_policy(ctx, project, 3)
    allowed = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-st2")
    )
    assert _by_seq(allowed.actions)[5].reason_code == "no_deploy_actuator"
    assert allowed.policy_input_digest != needs.policy_input_digest


@pytest.mark.db
async def test_missing_current_release_graph_does_not_cite_authorization(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await set_policy(ctx, project, 2)
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=incident_payload(),
        idempotency_key=unique_key("inc-auth"),
    )
    snap = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-auth")
    )
    assert snap.rollback_verification_run_id is None
    assert snap.emergency_rollback_authorization_id is None
    assert snap.standing_binding_present is False


@pytest.mark.db
async def test_policy_for_share_blocks_concurrent_upsert(inc_ctx, admin_engine):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await set_policy(ctx, project, 2)
    async with tenant_scope(ctx, isolation_level="READ COMMITTED") as session:
        await AutonomyPolicyRepository(session, ctx).snapshot_decisions(project, MATRIX_ACTIONS)
        async with admin_engine.connect() as other:
            await other.execute(text("SET lock_timeout = '200ms'"))
            with pytest.raises(DBAPIError):
                await other.execute(
                    text("UPDATE autonomy_policies SET autonomy_level=0 WHERE project_id=:p"),
                    {"p": project},
                )


@pytest.mark.db
async def test_swapped_kind_insert_and_seq67_plan_fail(inc_ctx, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    tenant = inc_ctx["t1"]
    await set_policy(ctx, project, 2)
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=incident_payload(),
        idempotency_key=unique_key("inc-fk"),
    )
    snap = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-fk")
    )
    assert _by_seq(snap.actions)[3].plan_kind == "patch_branch"
    digest = "sha256:" + "ab" * 32
    decisions = (
        '{"create_branches":"allow","deploy_production":"deny",'
        '"deploy_staging":"deny","open_pull_requests":"allow"}'
    )
    run_id = (
        await db_session.execute(
            text(
                "INSERT INTO ops_self_healing_runs ("
                "tenant_id, project_id, incident_id, ruleset_version, action_count, "
                "policy_present, policy_input_digest, request_digest, decision_snapshot, "
                "idempotency_key, rollback_coverage_digest) VALUES ("
                ":t,:p,:i,'slice58.v1',5,false,:d,:d,CAST(:js AS jsonb),:k,:d) RETURNING id"
            ),
            {
                "t": tenant,
                "p": project,
                "i": incident.id,
                "d": digest,
                "js": decisions,
                "k": unique_key("sql"),
            },
        )
    ).scalar_one()
    pr_plan = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO ops_hotfix_plans ("
            "id, tenant_id, project_id, incident_id, run_id, plan_kind, intended_ref) "
            "VALUES (:id,:t,:p,:i,:r,'hotfix_pr','local:hotfix_pr:deadbeef')"
        ),
        {"id": pr_plan, "t": tenant, "p": project, "i": incident.id, "r": run_id},
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_self_healing_results ("
                    "tenant_id, project_id, incident_id, run_id, seq, action, matrix_action, "
                    "policy_decision, execution_posture, reason_code, plan_id, plan_kind) VALUES ("
                    ":t,:p,:i,:r,3,'create_patch_branch','create_branches','allow',"
                    "'local_branch_plan_written','plan_written',:plan,'patch_branch')"
                ),
                {"t": tenant, "p": project, "i": incident.id, "r": run_id, "plan": pr_plan},
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_self_healing_results ("
                    "tenant_id, project_id, incident_id, run_id, seq, action, matrix_action, "
                    "policy_decision, execution_posture, reason_code, plan_id, plan_kind) VALUES ("
                    ":t,:p,:i,:r,6,'deploy_production_hotfix','deploy_production','allow',"
                    "'production_not_executed','production_not_executed',:plan,NULL)"
                ),
                {"t": tenant, "p": project, "i": incident.id, "r": run_id, "plan": pr_plan},
            )


@pytest.mark.db
async def test_catalog_rls_append_only_and_audit_omits_intended_ref(
    inc_ctx, admin_engine, db_session
):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await set_policy(ctx, project, 2)
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=incident_payload(),
        idempotency_key=unique_key("inc-cat"),
    )
    snap = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-cat")
    )
    async with admin_engine.connect() as conn:
        for table in HOTFIX_TABLES:
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
        plan_id = (
            await conn.execute(
                text("SELECT id FROM ops_hotfix_plans WHERE run_id=:r LIMIT 1"),
                {"r": snap.id},
            )
        ).scalar_one()
        result_id = (
            await conn.execute(
                text("SELECT id FROM ops_self_healing_results WHERE run_id=:r LIMIT 1"),
                {"r": snap.id},
            )
        ).scalar_one()
        unique = (
            await conn.execute(
                text("SELECT 1 FROM pg_constraint WHERE conname='uq_era_id_project_tenant'")
            )
        ).scalar_one()
        assert unique == 1
        payload = (
            await conn.execute(
                text(
                    "SELECT payload::text FROM audit_logs WHERE action='ops_hotfix_intent.recorded' "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            )
        ).scalar_one()
    assert "intended_ref" not in payload
    assert "local:patch_branch" not in payload
    row_ids = {
        "ops_self_healing_runs": snap.id,
        "ops_hotfix_plans": plan_id,
        "ops_self_healing_results": result_id,
    }
    for table, row_id in row_ids.items():
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
            await db_session.execute(text("TRUNCATE ops_hotfix_plans CASCADE"))


@pytest.mark.db
async def test_idempotency_and_terminal_incident_refused(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    await set_policy(ctx, project, 2)
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=incident_payload(),
        idempotency_key=unique_key("inc-id"),
    )
    key = unique_key("hf-id")
    first = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=key
    )
    second = await evaluate_hotfix_intent(
        ctx, project, incident.id, actor="hotfix-test", idempotency_key=key
    )
    assert first.id == second.id
    from app.ops.incident_service import transition_incident
    from app.ops.hotfix import HotfixError

    await transition_incident(
        ctx, project, incident.id, actor="hotfix-test", to_status="investigating"
    )
    await transition_incident(ctx, project, incident.id, actor="hotfix-test", to_status="mitigated")
    await transition_incident(ctx, project, incident.id, actor="hotfix-test", to_status="resolved")
    with pytest.raises(HotfixError, match="not evaluable"):
        await evaluate_hotfix_intent(
            ctx, project, incident.id, actor="hotfix-test", idempotency_key=unique_key("hf-term")
        )


@pytest.mark.db
async def test_latch_project_lock_blocks_concurrent_update(inc_ctx, admin_engine):
    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    async with tenant_scope(ctx, isolation_level="READ COMMITTED") as session:
        await assert_project_not_stopped(session, ctx, project)
        async with admin_engine.connect() as other:
            await other.execute(text("SET lock_timeout = '200ms'"))
            with pytest.raises(DBAPIError):
                await other.execute(
                    text("SELECT id FROM projects WHERE id=:p FOR UPDATE"),
                    {"p": project},
                )


@pytest.mark.db
async def test_wrappers_do_not_accept_session_and_frozen_guard(inc_ctx, db_session):
    from tests.ops_hotfix_support import FINDINGS_GUARD_MD5

    md5 = (
        await db_session.execute(
            text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
        )
    ).scalar_one()
    assert md5 == FINDINGS_GUARD_MD5
    assert "session" not in evaluate_hotfix_intent.__code__.co_varnames
    repo = OpsHotfixRepository
    assert repo.evaluate.__name__ == "evaluate"
