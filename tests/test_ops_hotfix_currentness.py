"""Real DB proofs for Slice-58 currentness: gate-10 run identity, latch, old auth."""

from __future__ import annotations

import inspect

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.identity import AuthenticatedActor
from app.ops.incident_service import open_incident
from app.repositories.emergency_controls import EmergencyStopActive
from app.repositories.ops_hotfix import OpsHotfixRepository
from app.tenancy import TenantContext
from tests.ops_hotfix_support import incident_payload, set_policy, unique_key
from tests.ops_incidents_support import insert_incident


@pytest_asyncio.fixture
async def emergency_ctx(db_session):
    from tests.test_emergency_controls import emergency_ctx as factory

    return await inspect.unwrap(factory)(db_session)


@pytest_asyncio.fixture
async def rollback_ctx(db_session):
    from tests.test_rollback_verifications import rollback_ctx as factory

    return await inspect.unwrap(factory)(db_session)


@pytest.mark.db
async def test_active_latch_refuses_evaluate_and_direct_insert(emergency_ctx, db_session):
    from app.release.emergency_control_service import EmergencyControlService

    ctx = emergency_ctx
    await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="hotfix-bind"
    )
    await EmergencyControlService(db_session, ctx["a"]).activate(
        project_id=ctx["project"], idempotency_key="hotfix-activate"
    )
    incident_id = await insert_incident(
        db_session, ctx["tenant"], ctx["project"], unique_key("inc-latch")
    )
    repo = OpsHotfixRepository(db_session, ctx["a"])
    with pytest.raises(EmergencyStopActive):
        await repo.evaluate(
            ctx["project"],
            incident_id,
            actor="hotfix-test",
            idempotency_key=unique_key("hf-latch"),
        )
    digest = "sha256:" + "ab" * 32
    decisions = (
        '{"create_branches":"deny","deploy_production":"deny",'
        '"deploy_staging":"deny","open_pull_requests":"deny"}'
    )
    with pytest.raises(DBAPIError, match="emergency stop is active"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_self_healing_runs ("
                    "tenant_id, project_id, incident_id, ruleset_version, action_count, "
                    "policy_present, policy_input_digest, request_digest, decision_snapshot, "
                    "idempotency_key, rollback_coverage_digest) VALUES ("
                    ":t,:p,:i,'slice58.v1',5,false,:d,:d,CAST(:js AS jsonb),:k,:d)"
                ),
                {
                    "t": ctx["tenant"],
                    "p": ctx["project"],
                    "i": incident_id,
                    "d": digest,
                    "js": decisions,
                    "k": unique_key("sql-latch"),
                },
            )
    assert await repo.latest(ctx["project"], incident_id) is None


@pytest.mark.db
async def test_failed_latest_rollback_run_does_not_set_fk(rollback_ctx):
    from tests.test_rollback_verifications import _bound_payload, _observe_bound_drill

    ctx = rollback_ctx
    passed = await _observe_bound_drill(ctx, _bound_payload())
    negative = _bound_payload()
    negative["workflow_conclusion"] = "failure"
    negative["phases"][2].update(phase_status="failed", result_code="unhealthy", health_ok=False)
    for phase in negative["phases"][3:]:
        phase.update(
            phase_status="not_run",
            result_code="not_run_after_failure",
            health_ok=None,
            operation_ok=None,
            observed_version_digest=None,
        )
    failed = await _observe_bound_drill(ctx, negative)
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert passed.gate_eligible is True
    assert failed.gate_eligible is False
    await ctx["session"].execute(text("SET CONSTRAINTS ALL DEFERRED"))
    incident_id = await insert_incident(
        ctx["session"], ctx["tenant"], ctx["project"], unique_key("inc-stale")
    )
    snap = await OpsHotfixRepository(ctx["session"], ctx["context"]).evaluate(
        ctx["project"],
        incident_id,
        actor="hotfix-test",
        idempotency_key=unique_key("hf-stale"),
    )
    assert snap is not None
    assert snap.rollback_verification_run_id is None
    assert failed.id != passed.id


@pytest.mark.db
async def test_old_authorization_row_is_not_cited(rollback_ctx):
    import json

    from app.release.emergency_control_service import EmergencyControlService
    from app.release.production_approval import idempotency_digest, subject_digest
    from tests.test_emergency_controls import _checklist, _policy
    from tests.test_rollback_verifications import _bound_payload, _observe_bound_drill

    ctx = rollback_ctx
    run = await _observe_bound_drill(ctx, _bound_payload())
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await ctx["session"].execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await ctx["session"].execute(
        text(
            "INSERT INTO intake_categories "
            "(tenant_id,project_id,category,status,data,origin) VALUES "
            "(:t,:p,'human_approval_policy','declared',CAST(:policy AS jsonb),'slice54_test'),"
            "(:t,:p,'go_live_checklist','declared',CAST(:checklist AS jsonb),'slice54_test')"
        ),
        {
            "t": ctx["tenant"],
            "p": ctx["project"],
            "policy": json.dumps(_policy()),
            "checklist": json.dumps(_checklist()),
        },
    )
    actor_ctx = TenantContext(
        ctx["tenant"], actor=AuthenticatedActor("stop-a@example.test", "human")
    )
    bound = await EmergencyControlService(ctx["session"], actor_ctx).bind(
        project_id=ctx["project"], idempotency_key="hotfix-auth-bind"
    )
    assert bound.binding_id is not None
    member_id = (
        await ctx["session"].execute(
            text(
                "SELECT id FROM emergency_control_authority_members "
                "WHERE binding_id=:b AND principal_subject_hash=:h"
            ),
            {"b": bound.binding_id, "h": subject_digest("stop-a@example.test")},
        )
    ).scalar_one()
    await ctx["session"].execute(
        text(
            "INSERT INTO emergency_rollback_authorizations ("
            "tenant_id, project_id, binding_id, release_candidate_id, evidence_pack_id, "
            "rollback_verification_run_id, actor_member_id, actor_subject_hash, actor_type, "
            "actor_provenance, release_rollback_binding_digest, authorization_contract_version, "
            "result_code, scope_limitation_code, idempotency_key_hash) VALUES ("
            ":t,:p,:b,:c,:e,:r,:m,:h,'human','request_authenticated',:old,"
            "'slice54.rollback_authority.v1','authorized_not_executed',"
            "'production_rollback_not_executed',:k)"
        ),
        {
            "t": ctx["tenant"],
            "p": ctx["project"],
            "b": bound.binding_id,
            "c": ctx["candidate"],
            "e": ctx["pack"].id,
            "r": run.id,
            "m": member_id,
            "h": subject_digest("stop-a@example.test"),
            "old": "sha256:" + "ff" * 32,
            "k": idempotency_digest(unique_key("old-auth")),
        },
    )
    incident_id = await insert_incident(
        ctx["session"], ctx["tenant"], ctx["project"], unique_key("inc-old-auth")
    )
    snap = await OpsHotfixRepository(ctx["session"], actor_ctx).evaluate(
        ctx["project"],
        incident_id,
        actor="hotfix-test",
        idempotency_key=unique_key("hf-old-auth"),
    )
    assert snap is not None
    assert snap.standing_binding_present is True
    assert snap.emergency_rollback_authorization_id is None


@pytest.mark.db
async def test_forged_snapshot_mismatch_and_seq4_without_branch_plan_fail(inc_ctx, db_session):
    import uuid

    ctx = TenantContext(inc_ctx["t1"])
    project = inc_ctx["p1"]
    tenant = inc_ctx["t1"]
    await set_policy(ctx, project, 2)
    incident = await open_incident(
        ctx,
        project,
        actor="hotfix-test",
        payload=incident_payload(),
        idempotency_key=unique_key("inc-guard"),
    )
    digest = "sha256:" + "ab" * 32

    async def _run(snapshot: str, key: str):
        return (
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
                    "js": snapshot,
                    "k": unique_key(key),
                },
            )
        ).scalar_one()

    deny_snap = (
        '{"create_branches":"deny","deploy_production":"deny",'
        '"deploy_staging":"deny","open_pull_requests":"deny"}'
    )
    with pytest.raises(DBAPIError, match="must match run decision_snapshot"):
        async with db_session.begin_nested():
            deny_run = await _run(deny_snap, "sql-deny")
            await db_session.execute(
                text(
                    "INSERT INTO ops_self_healing_results ("
                    "tenant_id, project_id, incident_id, run_id, seq, action, matrix_action, "
                    "policy_decision, execution_posture, reason_code) VALUES ("
                    ":t,:p,:i,:r,3,'create_patch_branch','create_branches','allow',"
                    "'local_branch_plan_written','plan_written')"
                ),
                {"t": tenant, "p": project, "i": incident.id, "r": deny_run},
            )
    with pytest.raises(DBAPIError, match="requires same-run patch_branch plan"):
        async with db_session.begin_nested():
            pr_run = await _run(
                '{"create_branches":"deny","deploy_production":"deny",'
                '"deploy_staging":"deny","open_pull_requests":"allow"}',
                "sql-pr",
            )
            pr_plan = uuid.uuid4()
            await db_session.execute(
                text(
                    "INSERT INTO ops_hotfix_plans ("
                    "id, tenant_id, project_id, incident_id, run_id, plan_kind, intended_ref) "
                    "VALUES (:id,:t,:p,:i,:r,'hotfix_pr','local:hotfix_pr:deadbeef')"
                ),
                {"id": pr_plan, "t": tenant, "p": project, "i": incident.id, "r": pr_run},
            )
            deny = ("deny", "recorded_not_executed", "plan_denied_by_policy", None, None)
            rows = [
                (3, "create_patch_branch", "create_branches", *deny),
                (
                    4,
                    "open_hotfix_pr",
                    "open_pull_requests",
                    "allow",
                    "local_pr_plan_written",
                    "plan_written",
                    pr_plan,
                    "hotfix_pr",
                ),
                (5, "deploy_staging_hotfix", "deploy_staging", *deny),
                (6, "deploy_production_hotfix", "deploy_production", *deny),
                (7, "rollback_production", "deploy_production", *deny),
            ]
            for seq, action, matrix, decision, posture, reason, plan, kind in rows:
                await db_session.execute(
                    text(
                        "INSERT INTO ops_self_healing_results ("
                        "tenant_id, project_id, incident_id, run_id, seq, action, "
                        "matrix_action, policy_decision, execution_posture, reason_code, "
                        "plan_id, plan_kind) VALUES ("
                        ":t,:p,:i,:r,:seq,:a,:m,:dec,:pos,:rea,:plan,:kind)"
                    ),
                    {
                        "t": tenant,
                        "p": project,
                        "i": incident.id,
                        "r": pr_run,
                        "seq": seq,
                        "a": action,
                        "m": matrix,
                        "dec": decision,
                        "pos": posture,
                        "rea": reason,
                        "plan": plan,
                        "kind": kind,
                    },
                )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
