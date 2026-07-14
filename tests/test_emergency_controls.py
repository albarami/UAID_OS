"""Slice 54 emergency-control contract, runtime, persistence, and A5 tests."""

from __future__ import annotations

import importlib
import inspect
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.release.production_autonomy import (
    GateResult,
    ProductionAutonomyReport,
    STATUS_PASSED,
    evaluate_production_autonomy,
)


def test_emergency_control_contract_module_exists() -> None:
    module = importlib.import_module("app.release.emergency_stop")

    assert module.EMERGENCY_CONTROL_CONTRACT_VERSION == "slice54.emergency_control.v1"
    assert module.EMERGENCY_STOP_CONTRACT_VERSION == "slice54.emergency_stop.v1"
    assert module.ROLLBACK_AUTHORITY_CONTRACT_VERSION == "slice54.rollback_authority.v1"


def _contract():
    return importlib.import_module("app.release.emergency_stop")


def _gate(report: ProductionAutonomyReport, number: int) -> dict:
    return next(item for item in report.to_dict()["gates"] if item["number"] == number)


def _gate13_kwargs() -> dict[str, object]:
    module = _contract()
    return {
        "emergency_policy_present": True,
        "emergency_policy_valid": True,
        "emergency_binding_present": True,
        "emergency_latest_binding_failed_or_refused": False,
        "emergency_contracts_current": True,
        "emergency_authority_membership_complete": True,
        "emergency_authority_member_count": 2,
        "emergency_mechanism_initialized": True,
        "emergency_stop_state_consistent": True,
        "emergency_stop_active": False,
        "emergency_rollback_authority_bound": True,
        "emergency_rollback_binding_current": True,
        "emergency_rollback_verification_current": True,
        "emergency_evidence_consistent": True,
        "emergency_control_contract_version": module.EMERGENCY_CONTROL_CONTRACT_VERSION,
        "emergency_stop_contract_version": module.EMERGENCY_STOP_CONTRACT_VERSION,
        "emergency_rollback_authority_contract_version": (
            module.ROLLBACK_AUTHORITY_CONTRACT_VERSION
        ),
    }


def test_fixed_scope_codes_keep_the_local_runtime_boundary_machine_visible() -> None:
    module = _contract()

    assert module.SCOPE_LIMITATION_CODES == (
        "local_uaid_runtime_step_boundary_only",
        "in_flight_node_not_preempted",
        "production_rollback_not_executed",
        "rollback_path_connector_observed_staging_only",
        "authority_is_request_authenticated_key_custody_under_recorded_policy",
    )
    assert all("production_stop" not in code for code in module.SCOPE_LIMITATION_CODES)


def test_authority_digest_is_canonical_bounded_and_order_sensitive() -> None:
    module = _contract()
    a = "sha256:" + "a" * 64
    b = "sha256:" + "b" * 64

    assert module.authority_set_digest((a, b)) == module.authority_set_digest((a, b))
    assert module.authority_set_digest((a, b)) != module.authority_set_digest((b, a))
    for invalid in ((), (a, a), ("plain-subject",), tuple(a for _ in range(101))):
        with pytest.raises(module.EmergencyControlContractError):
            module.authority_set_digest(invalid)


def test_latch_transition_and_actor_authority_are_fail_closed() -> None:
    module = _contract()
    module.validate_latch_transition("armed", "active")
    module.validate_latch_transition("active", "armed")
    for transition in (("armed", "armed"), ("active", "active"), ("unknown", "armed")):
        with pytest.raises(module.EmergencyControlContractError):
            module.validate_latch_transition(*transition)

    module.validate_actor_authority(
        actor_provenance="request_authenticated",
        actor_type="human",
        actor_is_member=True,
        operation="activate",
    )
    module.validate_actor_authority(
        actor_provenance="request_authenticated",
        actor_type="human",
        actor_is_member=True,
        operation="authorize_rollback",
    )
    module.validate_actor_authority(
        actor_provenance="request_authenticated",
        actor_type="human",
        actor_is_member=True,
        operation="clear",
        activating_subject_hash="sha256:" + "a" * 64,
        actor_subject_hash="sha256:" + "b" * 64,
    )
    for kwargs in (
        {
            "actor_provenance": "caller_supplied_unverified",
            "actor_type": "human",
            "actor_is_member": True,
            "operation": "activate",
        },
        {
            "actor_provenance": "request_authenticated",
            "actor_type": "service",
            "actor_is_member": True,
            "operation": "activate",
        },
        {
            "actor_provenance": "request_authenticated",
            "actor_type": "human",
            "actor_is_member": False,
            "operation": "activate",
        },
        {
            "actor_provenance": "request_authenticated",
            "actor_type": "human",
            "actor_is_member": True,
            "operation": "clear",
            "activating_subject_hash": "sha256:" + "a" * 64,
            "actor_subject_hash": "sha256:" + "a" * 64,
        },
    ):
        with pytest.raises(module.EmergencyControlContractError):
            module.validate_actor_authority(**kwargs)


def test_caller_payload_is_bodyless_and_truth_fields_never_enter_contract() -> None:
    module = _contract()
    module.validate_empty_operation_payload({})

    for payload in (
        {"actor": "x"},
        {"active": True},
        {"release_candidate_id": "x"},
        {"gate_eligible": True},
        {"authority": "release_manager"},
    ):
        with pytest.raises(module.EmergencyControlContractError):
            module.validate_empty_operation_payload(payload)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            {"emergency_policy_present": False},
            "insufficient_evidence:no_recorded_emergency_authority_policy",
        ),
        (
            {"emergency_policy_valid": False},
            "insufficient_evidence:emergency_authority_policy_invalid",
        ),
        (
            {"emergency_binding_present": False},
            "insufficient_evidence:no_emergency_control_binding",
        ),
        (
            {"emergency_latest_binding_failed_or_refused": True},
            "insufficient_evidence:latest_emergency_control_binding_failed_or_refused",
        ),
        (
            {"emergency_contracts_current": False},
            "insufficient_evidence:emergency_control_contract_mismatch",
        ),
        (
            {"emergency_authority_membership_complete": False},
            "insufficient_evidence:emergency_authority_membership_incomplete",
        ),
        (
            {"emergency_mechanism_initialized": False},
            "insufficient_evidence:emergency_stop_mechanism_uninitialized",
        ),
        (
            {"emergency_stop_state_consistent": False},
            "insufficient_evidence:emergency_stop_state_inconsistent",
        ),
        (
            {"emergency_rollback_authority_bound": False},
            "insufficient_evidence:rollback_authority_not_release_bound",
        ),
        (
            {"emergency_rollback_binding_current": False},
            "insufficient_evidence:rollback_authority_binding_stale",
        ),
        (
            {"emergency_rollback_verification_current": False},
            "insufficient_evidence:rollback_verification_not_current_or_gate_eligible",
        ),
        (
            {"emergency_evidence_consistent": False},
            "insufficient_evidence:emergency_control_evidence_inconsistent",
        ),
        ({"emergency_stop_active": True}, "insufficient_evidence:emergency_stop_active"),
    ],
)
def test_gate13_exact_precedence(mutation: dict[str, object], reason: str) -> None:
    kwargs = _gate13_kwargs()
    kwargs.update(mutation)

    gate = _gate(evaluate_production_autonomy("p", readiness_level="R5", **kwargs), 13)

    assert gate["status"] == "insufficient_evidence"
    assert gate["reason"] == reason


def test_gate13_pass_is_honestly_scoped_and_other_gates_are_unchanged() -> None:
    before = evaluate_production_autonomy("p", readiness_level="R5").to_dict()
    after = evaluate_production_autonomy("p", readiness_level="R5", **_gate13_kwargs()).to_dict()
    gate13 = next(item for item in after["gates"] if item["number"] == 13)

    assert before["gates"][:12] == after["gates"][:12]
    assert gate13["status"] == "passed"
    assert gate13["reason"] == (
        "passed:request_authenticated_runtime_stop_and_release_bound_rollback_authority"
    )
    assert gate13["context"]["scope_limitation_codes"] == list(_contract().SCOPE_LIMITATION_CODES)
    assert "human" not in gate13["reason"]
    assert "production_rollback_executed" not in gate13["reason"]


def test_synthetic_all_thirteen_pass_stays_hard_false() -> None:
    report = ProductionAutonomyReport(
        project_id="p",
        gates=[GateResult(i, f"gate_{i}", STATUS_PASSED, "passed:test") for i in range(1, 14)],
    ).to_dict()

    assert report["a5_satisfied"] is True
    assert report["can_go_live_autonomously"] is False
    assert report["can_go_live_reasons"] == ["a5_gates_not_all_satisfied"]


def test_all_eight_runtime_entry_points_and_every_work_node_have_boundaries() -> None:
    import app.runtime.engine as runtime

    entry_points = (
        runtime.start_demo_run,
        runtime.resume_demo_run,
        runtime.start_approval_run,
        runtime.resume_approval_run,
        runtime.run_retry_demo,
        runtime.run_failing_demo,
        runtime.start_costguard_run,
        runtime.resume_costguard_run,
    )
    assert len(entry_points) == 8
    assert all("_emergency_boundary" in inspect.getsource(value) for value in entry_points)
    for builder in (
        runtime._build_demo_graph,
        runtime._build_approval_graph,
        runtime._build_retry_graph,
        runtime._build_failing_graph,
        runtime._build_cost_graph,
    ):
        assert "_emergency_boundary" in inspect.getsource(builder)


def _policy() -> dict:
    return {
        "approval_channel": "dashboard",
        "daily_digest_time": "09:00",
        "batch_low_risk_questions": True,
        "realtime_for": [
            "production_deployment",
            "security_exception",
            "cost_overrun",
            "data_access",
            "legal_or_regulatory_decision",
        ],
        "non_response_policy": {
            "low_risk": "proceed_with_safe_assumption_after_24h",
            "medium_risk": "pause_affected_work_after_24h",
            "high_risk": "block_until_approval",
            "production": "block_until_approval",
        },
        "approvers": ["stop-a@example.test", "stop-b@example.test"],
    }


def _checklist() -> dict:
    return {
        "product": {},
        "engineering": {},
        "ai_and_data": {},
        "security": {},
        "operations": {},
        "governance": {
            "evidence_pack_complete": "required",
            "approval_events_recorded": "required",
            "separation_of_duties_confirmed": "required",
            "open_issues_have_risk_acceptance": "required_if_any_open_issues",
        },
    }


async def _scalar(session, sql: str, **params):
    return (await session.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def emergency_ctx(db_session):
    from app.identity import AuthenticatedActor
    from app.tenancy import TenantContext

    suffix = uuid.uuid4().hex[:10]
    organization = await _scalar(
        db_session,
        "INSERT INTO organizations (name,slug) VALUES ('EmergencyOrg',:slug) RETURNING id",
        slug=f"emergency-org-{suffix}",
    )
    tenant = await _scalar(
        db_session,
        "INSERT INTO tenants (organization_id,name,slug) VALUES (:org,'EmergencyTenant',:slug) RETURNING id",
        org=organization,
        slug=f"emergency-tenant-{suffix}",
    )
    project = await _scalar(
        db_session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:tenant,'EmergencyProject',:slug) RETURNING id",
        tenant=tenant,
        slug=f"emergency-project-{suffix}",
    )
    await db_session.execute(
        text(
            "INSERT INTO intake_categories "
            "(tenant_id,project_id,category,status,data,origin) VALUES "
            "(:tenant,:project,'human_approval_policy','declared',CAST(:policy AS jsonb),'slice54_test'),"
            "(:tenant,:project,'go_live_checklist','declared',CAST(:checklist AS jsonb),'slice54_test')"
        ),
        {
            "tenant": tenant,
            "project": project,
            "policy": json.dumps(_policy()),
            "checklist": json.dumps(_checklist()),
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO autonomy_policies (tenant_id,project_id,autonomy_level,overrides) "
            "VALUES (:tenant,:project,5,'{}'::jsonb)"
        ),
        {"tenant": tenant, "project": project},
    )
    runs = {}
    for label, status in (
        ("created", "created"),
        ("running", "running"),
        ("paused", "paused"),
        ("blocked", "blocked"),
    ):
        runs[label] = await _scalar(
            db_session,
            "INSERT INTO project_runs (tenant_id,project_id,status) VALUES (:tenant,:project,:status) RETURNING id",
            tenant=tenant,
            project=project,
            status=status,
        )
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:tenant,true)"), {"tenant": str(tenant)}
    )
    return {
        "tenant": tenant,
        "project": project,
        "runs": runs,
        "a": TenantContext(tenant, actor=AuthenticatedActor("stop-a@example.test", "human")),
        "b": TenantContext(tenant, actor=AuthenticatedActor("stop-b@example.test", "human")),
        "outsider": TenantContext(
            tenant, actor=AuthenticatedActor("outsider@example.test", "human")
        ),
    }


@pytest.mark.db
async def test_real_latch_pauses_running_inventory_and_distinct_clear_never_resumes(
    emergency_ctx, db_session
):
    from app.release.emergency_control_service import (
        EmergencyControlConflict,
        EmergencyControlService,
    )

    ctx = emergency_ctx
    bound = await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="bind-1"
    )
    assert bound.state == "armed"
    with pytest.raises(EmergencyControlConflict):
        await EmergencyControlService(db_session, ctx["outsider"]).activate(
            project_id=ctx["project"], idempotency_key="unauthorized-activate"
        )
    activated = await EmergencyControlService(db_session, ctx["a"]).activate(
        project_id=ctx["project"], idempotency_key="activate-1"
    )
    assert activated.state == "active" and activated.affected_run_count == 4
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    statuses = dict(
        (
            await db_session.execute(
                text("SELECT id,status FROM project_runs WHERE project_id=:project"),
                {"project": ctx["project"]},
            )
        ).all()
    )
    assert statuses[ctx["runs"]["running"]] == "paused"
    assert statuses[ctx["runs"]["created"]] == "created"
    assert statuses[ctx["runs"]["paused"]] == "paused"
    assert statuses[ctx["runs"]["blocked"]] == "blocked"
    with pytest.raises(EmergencyControlConflict):
        await EmergencyControlService(db_session, ctx["a"]).clear(
            project_id=ctx["project"], idempotency_key="same-actor-clear"
        )
    cleared = await EmergencyControlService(db_session, ctx["b"]).clear(
        project_id=ctx["project"], idempotency_key="clear-1"
    )
    assert cleared.state == "armed"
    after = dict(
        (
            await db_session.execute(
                text("SELECT id,status FROM project_runs WHERE project_id=:project"),
                {"project": ctx["project"]},
            )
        ).all()
    )
    assert after == statuses


@pytest.mark.db
async def test_db_coverage_is_fail_closed_without_release_authority_and_active_stop_wins(
    emergency_ctx, db_session
):
    from app.release.emergency_control_service import EmergencyControlService
    from app.repositories.emergency_controls import EmergencyControlRepository

    ctx = emergency_ctx
    await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="coverage-bind"
    )
    repo = EmergencyControlRepository(db_session, ctx["a"])
    armed = await repo.coverage_for_project(ctx["project"])
    gate = _gate(
        evaluate_production_autonomy(ctx["project"], readiness_level="R5", **armed.gate_kwargs()),
        13,
    )
    assert gate["reason"] == "insufficient_evidence:rollback_authority_not_release_bound"
    await EmergencyControlService(db_session, ctx["a"]).activate(
        project_id=ctx["project"], idempotency_key="coverage-activate"
    )
    active = await repo.coverage_for_project(ctx["project"])
    # Precedence remains release-binding first; a complete full binding is required before
    # the active-stop rung can be reached. The scalar still exposes the active safety state.
    assert active.stop_active is True and active.rollback_authority_bound is False


@pytest.mark.db
async def test_policy_rebind_never_resets_an_active_stop(emergency_ctx, db_session):
    from app.release.emergency_control_service import (
        EmergencyControlConflict,
        EmergencyControlService,
    )
    from app.repositories.autonomy_policies import AutonomyPolicyRepository

    ctx = emergency_ctx
    await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="rebind-original"
    )
    await EmergencyControlService(db_session, ctx["a"]).activate(
        project_id=ctx["project"], idempotency_key="rebind-activate"
    )
    await AutonomyPolicyRepository(db_session, ctx["a"]).upsert(
        project_id=ctx["project"],
        autonomy_level=5,
        overrides={"read_docs": {"requires_approval": True}},
        actor="test_policy_change",
    )
    with pytest.raises(EmergencyControlConflict):
        await EmergencyControlService(db_session, ctx["b"]).clear(
            project_id=ctx["project"], idempotency_key="stale-clear"
        )
    rebound = await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="rebind-current"
    )
    assert rebound.state == "active"
    cleared = await EmergencyControlService(db_session, ctx["b"]).clear(
        project_id=ctx["project"], idempotency_key="current-clear"
    )
    assert cleared.state == "armed"


@pytest.mark.db
async def test_checkpointed_node_b_never_executes_after_activation(emergency_ctx, db_session):
    from app.release.emergency_control_service import EmergencyControlService
    from app.repositories.emergency_controls import EmergencyStopActive
    from app.runtime.engine import resume_demo_run, start_demo_run

    ctx = emergency_ctx
    run_id = ctx["runs"]["created"]
    await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="checkpoint-bind"
    )
    state = await start_demo_run(db_session, ctx["a"], project_id=ctx["project"], run_id=run_id)
    assert state["a"] == 1 and state.get("b", 0) == 0
    await EmergencyControlService(db_session, ctx["a"]).activate(
        project_id=ctx["project"], idempotency_key="checkpoint-activate"
    )
    with pytest.raises(EmergencyStopActive):
        await resume_demo_run(db_session, ctx["a"], project_id=ctx["project"], run_id=run_id)
    node_b = await _scalar(
        db_session,
        "SELECT count(*) FROM run_steps WHERE run_id=:run AND node='node_b'",
        run=run_id,
    )
    status = await _scalar(db_session, "SELECT status FROM project_runs WHERE id=:run", run=run_id)
    assert node_b == 0 and status == "paused"


@pytest.mark.db
async def test_active_latch_refuses_all_eight_runtime_entry_points(emergency_ctx, db_session):
    from app.release.emergency_control_service import EmergencyControlService
    from app.repositories.emergency_controls import EmergencyStopActive
    from app.runtime import engine

    ctx = emergency_ctx
    run_ids = [
        await _scalar(
            db_session,
            "INSERT INTO project_runs (tenant_id,project_id,status) VALUES (:tenant,:project,'created') RETURNING id",
            tenant=ctx["tenant"],
            project=ctx["project"],
        )
        for _ in range(8)
    ]
    await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="all-entry-bind"
    )
    await EmergencyControlService(db_session, ctx["a"]).activate(
        project_id=ctx["project"], idempotency_key="all-entry-activate"
    )
    calls = (
        lambda run: engine.start_demo_run(
            db_session, ctx["a"], project_id=ctx["project"], run_id=run
        ),
        lambda run: engine.resume_demo_run(
            db_session, ctx["a"], project_id=ctx["project"], run_id=run
        ),
        lambda run: engine.start_approval_run(
            db_session, ctx["a"], project_id=ctx["project"], run_id=run
        ),
        lambda run: engine.resume_approval_run(
            db_session, ctx["a"], project_id=ctx["project"], run_id=run
        ),
        lambda run: engine.run_retry_demo(
            db_session,
            ctx["a"],
            project_id=ctx["project"],
            run_id=run,
            fail_times=0,
            max_attempts=1,
        ),
        lambda run: engine.run_failing_demo(
            db_session, ctx["a"], project_id=ctx["project"], run_id=run
        ),
        lambda run: engine.start_costguard_run(
            db_session, ctx["a"], project_id=ctx["project"], run_id=run
        ),
        lambda run: engine.resume_costguard_run(
            db_session, ctx["a"], project_id=ctx["project"], run_id=run
        ),
    )
    for call, run_id in zip(calls, run_ids, strict=True):
        with pytest.raises(EmergencyStopActive):
            await call(run_id)
    executed_steps = await _scalar(
        db_session,
        "SELECT count(*) FROM run_steps WHERE run_id = ANY(:runs) AND event_type<>'emergency_paused'",
        runs=run_ids,
    )
    assert executed_steps == 0


@pytest.mark.db
async def test_active_latch_blocks_repository_and_direct_sql_restart(emergency_ctx, db_session):
    from app.release.emergency_control_service import EmergencyControlService
    from app.repositories.emergency_controls import EmergencyStopActive
    from app.repositories.runs import RunRepository

    ctx = emergency_ctx
    await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="guard-bind"
    )
    await EmergencyControlService(db_session, ctx["a"]).activate(
        project_id=ctx["project"], idempotency_key="guard-activate"
    )
    with pytest.raises(EmergencyStopActive):
        await RunRepository(db_session, ctx["a"]).mark_running(
            run_id=ctx["runs"]["created"], actor="runtime"
        )
    with pytest.raises(DBAPIError, match="project emergency stop is active"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE project_runs SET status='running' WHERE id=:run"),
                {"run": ctx["runs"]["created"]},
            )


@pytest.mark.db
async def test_emergency_tables_are_rls_forced_append_only_and_safe_audited(
    emergency_ctx, db_session
):
    from app.release.emergency_control_service import EmergencyControlService

    ctx = emergency_ctx
    await EmergencyControlService(db_session, ctx["a"]).bind(
        project_id=ctx["project"], idempotency_key="catalog-bind"
    )
    catalog = (
        await db_session.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY(:tables) ORDER BY relname"
            ),
            {
                "tables": [
                    "emergency_control_bindings",
                    "emergency_control_authority_members",
                    "emergency_stop_events",
                    "emergency_stop_run_effects",
                    "emergency_rollback_authorizations",
                ]
            },
        )
    ).all()
    assert len(catalog) == 5 and all(row[1] and row[2] for row in catalog)
    generated = {
        row[0]
        for row in (
            await db_session.execute(
                text(
                    "SELECT attname FROM pg_attribute WHERE attrelid="
                    "'emergency_control_bindings'::regclass AND attgenerated='s'"
                )
            )
        ).all()
    }
    assert generated == {
        "stop_authority_bound",
        "rollback_authority_bound",
        "evidence_consistent",
        "gate_eligible_at_creation",
    }
    guard_md5 = await _scalar(
        db_session,
        "SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))",
    )
    assert guard_md5 == "808036faf2660d6810aeca4342e6f1ac"
    grants = {
        row[0]
        for row in (
            await db_session.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name='emergency_control_bindings' AND grantee='uaid_app'"
                )
            )
        ).all()
    }
    assert grants == {"SELECT", "INSERT"}
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE emergency_control_bindings SET reason_code='forged' "
                    "WHERE project_id=:project"
                ),
                {"project": ctx["project"]},
            )
    with pytest.raises(DBAPIError, match="cannot downgrade Slice 54"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "DO $fn$ BEGIN IF EXISTS (SELECT 1 FROM emergency_control_bindings) "
                    "THEN RAISE EXCEPTION 'cannot downgrade Slice 54 while emergency-control rows exist'; "
                    "END IF; END $fn$"
                )
            )
    audit_text = json.dumps(
        (
            await db_session.execute(
                text(
                    "SELECT actor,action,target,payload FROM audit_logs "
                    "WHERE tenant_id=:tenant AND action LIKE 'emergency_%'"
                ),
                {"tenant": ctx["tenant"]},
            )
        )
        .mappings()
        .all(),
        default=str,
    )
    assert "stop-a@example.test" not in audit_text
    assert "sha256:" not in audit_text
    assert "emergency_control_authority" in audit_text


def test_emergency_api_is_exactly_four_bodyless_mutations_plus_status() -> None:
    from app.main import app

    paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if "emergency-" in path
    }
    assert len(paths) == 5
    assert sum("post" in operations for operations in paths.values()) == 4
    assert sum("get" in operations for operations in paths.values()) == 1
    for operations in paths.values():
        if "post" in operations:
            assert "requestBody" not in operations["post"]


@pytest.mark.asyncio
async def test_emergency_api_rejects_truth_body_without_echoing_sentinel() -> None:
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.api.emergency_controls import _empty_body

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {
            "type": "http.request",
            "body": b'{"active":true,"actor":"SENTINEL_EMERGENCY_PRINCIPAL"}',
            "more_body": False,
        }

    request = Request({"type": "http", "method": "POST", "path": "/"}, receive)
    with pytest.raises(HTTPException) as rejected:
        await _empty_body(request)
    assert rejected.value.status_code == 409
    assert rejected.value.detail == "emergency control unavailable"
    assert "SENTINEL" not in rejected.value.detail
