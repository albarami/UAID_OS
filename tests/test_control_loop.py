from __future__ import annotations

import ast
import inspect
import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.release.go_live_decision import (
    AUTHORITY_TRUTH_TIER,
    CONTROL_LOOP_CONTRACT_VERSION,
    DECISION_STATUS,
    GO_LIVE_CHAIN_CONTRACT_VERSION,
    GO_LIVE_DECISION_CONTRACT_VERSION,
    GO_LIVE_EVALUATION_CONTRACT_VERSION,
    SCOPE_LIMITATION_CODES,
    DecisionInputs,
    GateSnapshot,
    canonical_binding_digest,
    canonical_gate_digest,
    decision_eligible,
    derive_decision,
    reject_caller_truth_fields,
    validate_exact_gate_set,
)
from app.runtime.control_loop import (
    ALLOWLISTED_INVOCATIONS,
    CONTROL_LOOP_NODES,
    GuardOutcome,
    run_guarded_stage,
)


def _gates(*, failed_gate: int | None = None) -> tuple[GateSnapshot, ...]:
    return tuple(
        GateSnapshot(
            gate_number=number,
            gate_name=f"gate_{number}",
            status="failed" if number == failed_gate else "passed",
            reason="test_reason",
            safe_context_digest="sha256:" + f"{number:064x}",
        )
        for number in range(1, 14)
    )


def _inputs(**overrides: object) -> DecisionInputs:
    values: dict[str, object] = {
        "gates": _gates(),
        "preapproval_gate_eligible": True,
        "policy_decision": "needs_approval",
        "emergency_latch_active": False,
        "binding_ids": {
            "release_candidate_id": str(uuid.UUID(int=1)),
            "evidence_pack_id": str(uuid.UUID(int=2)),
            "release_verdict_id": str(uuid.UUID(int=3)),
            "preapproval_request_id": str(uuid.UUID(int=4)),
            "preapproval_attestation_id": str(uuid.UUID(int=5)),
            "autonomy_policy_id": str(uuid.UUID(int=6)),
            "emergency_control_binding_id": str(uuid.UUID(int=7)),
        },
    }
    values.update(overrides)
    return DecisionInputs(**values)  # type: ignore[arg-type]


def test_contracts_and_truth_vocabulary_are_fixed() -> None:
    assert CONTROL_LOOP_CONTRACT_VERSION == "slice55.control_loop.v1"
    assert GO_LIVE_EVALUATION_CONTRACT_VERSION == "slice55.go_live_evaluation.v1"
    assert GO_LIVE_DECISION_CONTRACT_VERSION == "slice55.go_live_decision.v1"
    assert GO_LIVE_CHAIN_CONTRACT_VERSION == "slice55.go_live_decision_chain.v1"
    assert DECISION_STATUS == "decided_not_executed"
    assert AUTHORITY_TRUTH_TIER == (
        "request_authenticated_key_custody_under_recorded_policy_not_human_signature"
    )
    assert "production_not_executed" in SCOPE_LIMITATION_CODES
    assert "key_custody_not_human_signature" in SCOPE_LIMITATION_CODES


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, True),
        ({"gates": _gates(failed_gate=1)}, False),
        ({"preapproval_gate_eligible": False}, False),
        ({"policy_decision": "deny"}, False),
        ({"policy_decision": "allow"}, False),
        ({"emergency_latch_active": True}, False),
    ],
)
def test_decision_eligible_is_exact_four_condition_predicate(
    overrides: dict[str, object], expected: bool
) -> None:
    assert decision_eligible(_inputs(**overrides)) is expected


@pytest.mark.parametrize("failed_gate", range(1, 14))
def test_each_single_gate_failure_refuses(failed_gate: int) -> None:
    assert decision_eligible(_inputs(gates=_gates(failed_gate=failed_gate))) is False


@pytest.mark.parametrize(
    "gates",
    [
        _gates()[:-1],
        _gates() + (_gates()[0],),
        tuple(reversed(_gates())),
        (_gates()[0],) + tuple(
            GateSnapshot(i, f"gate_{i}", "passed", "reason", "sha256:" + "0" * 64)
            for i in range(3, 15)
        ),
    ],
)
def test_exact_gate_set_is_required(gates: tuple[GateSnapshot, ...]) -> None:
    with pytest.raises(ValueError, match="exact_gate_set_required"):
        validate_exact_gate_set(gates)


def test_positive_outcome_is_non_executing_and_hard_false() -> None:
    outcome = derive_decision(_inputs())
    assert outcome.eligible is True
    assert outcome.status == "decided_not_executed"
    assert outcome.production_action_executed is False
    assert outcome.can_go_live_autonomously is False
    assert outcome.authority_truth_tier == AUTHORITY_TRUTH_TIER


def test_negative_outcome_has_no_decision_status() -> None:
    outcome = derive_decision(_inputs(preapproval_gate_eligible=False))
    assert outcome.eligible is False
    assert outcome.status is None
    assert outcome.production_action_executed is False
    assert outcome.can_go_live_autonomously is False


def test_digests_are_canonical_and_materially_sensitive() -> None:
    gates = _gates()
    assert canonical_gate_digest(gates) == canonical_gate_digest(tuple(gates))
    assert canonical_gate_digest(gates) != canonical_gate_digest(_gates(failed_gate=13))

    first = _inputs(binding_ids={"b": "2", "a": "1"})
    reordered = _inputs(binding_ids={"a": "1", "b": "2"})
    changed = _inputs(binding_ids={"a": "1", "b": "3"})
    assert canonical_binding_digest(first) == canonical_binding_digest(reordered)
    assert canonical_binding_digest(first) != canonical_binding_digest(changed)


@pytest.mark.parametrize(
    "field",
    [
        "passed",
        "eligible",
        "current",
        "approved",
        "policy_permits",
        "latch_active",
        "decision_status",
        "executed",
        "can_go_live",
        "prev_hash",
        "entry_hash",
        "chain_seq",
    ],
)
def test_caller_truth_fields_fail_closed_recursively(field: str) -> None:
    with pytest.raises(ValueError, match="caller_truth_field_forbidden"):
        reject_caller_truth_fields({"safe": [{"nested": {field: True}}]})


def test_runtime_invocation_allowlist_is_exact_and_has_no_external_action() -> None:
    assert ALLOWLISTED_INVOCATIONS == (
        "ProductionAutonomyRepository.evaluate",
        "EvidencePackRepository.audit_pack",
        "ProductionPreapprovalRepository.coverage_for_project",
        "AutonomyPolicyRepository.decision_for",
        "EmergencyControlRepository.status",
        "app.repositories.cost.evaluate",
    )
    assert CONTROL_LOOP_NODES == (
        "read_project_state",
        "inspect_existing_work_evidence",
        "observe_existing_review_and_verification_evidence",
        "assemble_or_reaudit_evidence_pack",
        "check_cost_and_authority_limits",
        "observe_staging_evidence",
        "evaluate_a5_gate",
        "finalize_go_live_decision",
    )
    assert all("deploy_production" not in node for node in CONTROL_LOOP_NODES)


def test_control_loop_has_no_http_surface_or_production_action_call() -> None:
    from app.main import app

    module = ast.parse(Path("app/runtime/control_loop.py").read_text())
    call_names = {
        node.func.id
        for node in ast.walk(module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "deploy_production" not in call_names
    assert all("control-loop" not in path for path in app.openapi()["paths"])


def test_synthetic_all_thirteen_passes_remains_hard_false() -> None:
    from app.release.production_autonomy import (
        A5_RULESET_VERSION,
        NO_GO_LIVE_REASONS,
        GateResult,
        ProductionAutonomyReport,
    )

    report = ProductionAutonomyReport(
        project_id=str(uuid.uuid4()),
        gates=[
            GateResult(number, f"gate_{number}", "passed", "test_passed", {})
            for number in range(1, 14)
        ],
    )
    assert report.a5_satisfied is True
    assert report.to_dict()["can_go_live_autonomously"] is False
    assert report.to_dict()["can_go_live_reasons"] == ["a5_gates_not_all_satisfied"]
    assert NO_GO_LIVE_REASONS == ("a5_gates_not_all_satisfied",)
    assert A5_RULESET_VERSION == "slice54.v1"


def test_a5_repository_accepts_one_injected_evaluation_instant() -> None:
    from app.repositories.production_autonomy import ProductionAutonomyRepository

    signature = inspect.signature(ProductionAutonomyRepository.evaluate)
    assert "as_of" in signature.parameters
    assert signature.parameters["as_of"].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.asyncio
async def test_guard_order_is_emergency_then_cost_then_stage() -> None:
    calls: list[str] = []

    async def emergency() -> bool:
        calls.append("emergency")
        return False

    async def cost() -> bool:
        calls.append("cost")
        return False

    async def stage() -> str:
        calls.append("stage")
        return "observed"

    result = await run_guarded_stage(
        emergency_active=emergency,
        cost_stop=cost,
        stage=stage,
    )
    assert result == GuardOutcome("completed", "observed")
    assert calls == ["emergency", "cost", "stage"]


@pytest.mark.asyncio
async def test_active_emergency_prevents_cost_and_stage() -> None:
    calls: list[str] = []

    async def emergency() -> bool:
        calls.append("emergency")
        return True

    async def forbidden() -> bool:
        calls.append("forbidden")
        return False

    result = await run_guarded_stage(
        emergency_active=emergency,
        cost_stop=forbidden,
        stage=forbidden,
    )
    assert result == GuardOutcome("paused_emergency_stop", None)
    assert calls == ["emergency"]


@pytest.mark.asyncio
async def test_cost_stop_prevents_stage() -> None:
    calls: list[str] = []

    async def emergency() -> bool:
        calls.append("emergency")
        return False

    async def cost() -> bool:
        calls.append("cost")
        return True

    async def stage() -> str:
        calls.append("stage")
        return "forbidden"

    result = await run_guarded_stage(
        emergency_active=emergency,
        cost_stop=cost,
        stage=stage,
    )
    assert result == GuardOutcome("paused_cost_stop", None)
    assert calls == ["emergency", "cost"]


def test_storage_models_cover_the_five_ruled_append_only_tables() -> None:
    from app.models.go_live_decision import (
        ControlLoopEvent,
        ControlLoopRun,
        GoLiveDecision,
        GoLiveEvaluation,
        GoLiveEvaluationGateResult,
    )

    assert {
        model.__tablename__
        for model in (
            ControlLoopRun,
            ControlLoopEvent,
            GoLiveEvaluation,
            GoLiveEvaluationGateResult,
            GoLiveDecision,
        )
    } == {
        "control_loop_runs",
        "control_loop_events",
        "go_live_evaluations",
        "go_live_evaluation_gate_results",
        "go_live_decisions",
    }


@pytest.mark.db
async def test_slice55_catalog_is_rls_append_only_and_decision_insert_is_narrow(
    db_session,
) -> None:
    tables = (
        "control_loop_runs",
        "control_loop_events",
        "go_live_evaluations",
        "go_live_evaluation_gate_results",
        "go_live_decisions",
    )
    rows = (
        await db_session.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity "
                "FROM pg_class WHERE relname = ANY(:tables) ORDER BY relname"
            ),
            {"tables": list(tables)},
        )
    ).all()
    assert {row[0] for row in rows} == set(tables)
    assert all(row[1] and row[2] for row in rows)

    functions = set(
        (
            await db_session.execute(
                text(
                    "SELECT proname FROM pg_proc WHERE proname IN "
                    "('slice55_finalize_decision','slice55_verify_decision_chain',"
                    "'slice55_validate_evaluation')"
                )
            )
        ).scalars()
    )
    assert functions == {
        "slice55_finalize_decision",
        "slice55_verify_decision_chain",
        "slice55_validate_evaluation",
    }
    grant_rows = (
        await db_session.execute(
            text(
                "SELECT table_name,privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee='uaid_app' AND table_name=ANY(:tables)"
            ),
            {"tables": list(tables)},
        )
    ).all()
    grants = {
        table: {privilege for grant_table, privilege in grant_rows if grant_table == table}
        for table in tables
    }
    assert grants["go_live_decisions"] == {"SELECT"}
    assert all(
        grants[table] == {"SELECT", "INSERT"}
        for table in tables
        if table != "go_live_decisions"
    )
    guard_md5 = await db_session.scalar(
        text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
    )
    assert guard_md5 == "808036faf2660d6810aeca4342e6f1ac"
    function_privileges = {
        signature: await db_session.scalar(
            text("SELECT has_function_privilege('uaid_app',:signature,'EXECUTE')"),
            {"signature": f"public.{signature}"},
        )
        for signature in (
            "slice55_finalize_decision(uuid)",
            "slice55_verify_decision_chain(uuid)",
            "slice55_validate_evaluation(uuid)",
            "slice55_policy_permits(uuid)",
        )
    }
    assert function_privileges == {
        "slice55_finalize_decision(uuid)": True,
        "slice55_verify_decision_chain(uuid)": False,
        "slice55_validate_evaluation(uuid)": False,
        "slice55_policy_permits(uuid)": False,
    }


@pytest.mark.db
async def test_slice55_rls_denies_default_cross_tenant_and_direct_decision_insert(
    admin_engine, rls_engine
) -> None:
    suffix = uuid.uuid4().hex[:10]
    async with admin_engine.begin() as conn:
        organization = await conn.scalar(
            text(
                "INSERT INTO organizations (name,slug) VALUES ('LoopRLSOrg',:slug) "
                "RETURNING id"
            ),
            {"slug": f"loop-rls-org-{suffix}"},
        )
        tenants: list[uuid.UUID] = []
        for index in range(2):
            tenants.append(
                await conn.scalar(
                    text(
                        "INSERT INTO tenants (organization_id,name,slug) "
                        "VALUES (:org,:name,:slug) RETURNING id"
                    ),
                    {
                        "org": organization,
                        "name": f"LoopRLSTenant{index}",
                        "slug": f"loop-rls-tenant-{index}-{suffix}",
                    },
                )
            )
        project = await conn.scalar(
            text(
                "INSERT INTO projects (tenant_id,name,slug) "
                "VALUES (:tenant,'LoopRLSProject',:slug) RETURNING id"
            ),
            {"tenant": tenants[0], "slug": f"loop-rls-project-{suffix}"},
        )
        project_run = await conn.scalar(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": tenants[0], "project": project},
        )
        loop_id = await conn.scalar(
            text(
                "INSERT INTO control_loop_runs "
                "(tenant_id,project_id,project_run_id,idempotency_digest,"
                "control_loop_contract_version,control_loop_contract_hash) "
                "VALUES (:tenant,:project,:run,:digest,'slice55.control_loop.v1',:digest) "
                "RETURNING id"
            ),
            {
                "tenant": tenants[0],
                "project": project,
                "run": project_run,
                "digest": "sha256:" + "a" * 64,
            },
        )

    async with rls_engine.connect() as conn:
        async with conn.begin():
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM control_loop_runs WHERE id=:id"),
                    {"id": loop_id},
                )
                == 0
            )
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant',:tenant,false)"),
            {"tenant": str(tenants[1])},
        )
        assert (
            await conn.scalar(
                text("SELECT count(*) FROM control_loop_runs WHERE id=:id"),
                {"id": loop_id},
            )
            == 0
        )
        await conn.rollback()
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant',:tenant,false)"),
            {"tenant": str(tenants[0])},
        )
        assert (
            await conn.scalar(
                text("SELECT count(*) FROM control_loop_runs WHERE id=:id"),
                {"id": loop_id},
            )
            == 1
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("INSERT INTO go_live_decisions DEFAULT VALUES"))
        await conn.rollback()


@pytest.mark.db
async def test_control_loop_run_and_event_are_immutable_and_linear(db_session) -> None:
    suffix = uuid.uuid4().hex[:10]
    organization = (
        await db_session.execute(
            text(
                "INSERT INTO organizations (name,slug) VALUES ('LoopOrg',:slug) RETURNING id"
            ),
            {"slug": f"loop-org-{suffix}"},
        )
    ).scalar_one()
    tenant = (
        await db_session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) "
                "VALUES (:org,'LoopTenant',:slug) RETURNING id"
            ),
            {"org": organization, "slug": f"loop-tenant-{suffix}"},
        )
    ).scalar_one()
    project = (
        await db_session.execute(
            text(
                "INSERT INTO projects (tenant_id,name,slug) "
                "VALUES (:tenant,'LoopProject',:slug) RETURNING id"
            ),
            {"tenant": tenant, "slug": f"loop-project-{suffix}"},
        )
    ).scalar_one()
    run = (
        await db_session.execute(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": tenant, "project": project},
        )
    ).scalar_one()
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:tenant,true)"),
        {"tenant": str(tenant)},
    )
    digest = "sha256:" + "1" * 64
    loop = (
        await db_session.execute(
            text(
                "INSERT INTO control_loop_runs "
                "(tenant_id,project_id,project_run_id,idempotency_digest,"
                "control_loop_contract_version,control_loop_contract_hash) "
                "VALUES (:tenant,:project,:run,:digest,'slice55.control_loop.v1',:digest) "
                "RETURNING id"
            ),
            {"tenant": tenant, "project": project, "run": run, "digest": digest},
        )
    ).scalar_one()
    root = (
        await db_session.execute(
            text(
                "INSERT INTO control_loop_events "
                "(tenant_id,project_id,control_loop_run_id,ordinal,previous_event_id,"
                "stage_code,outcome_code) "
                "VALUES (:tenant,:project,:loop,1,NULL,'read_project_state','completed') "
                "RETURNING id"
            ),
            {"tenant": tenant, "project": project, "loop": loop},
        )
    ).scalar_one()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE control_loop_runs SET idempotency_digest=:digest WHERE id=:id"),
                {"digest": "sha256:" + "2" * 64, "id": loop},
            )

    with pytest.raises(DBAPIError, match="linear"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO control_loop_events "
                    "(tenant_id,project_id,control_loop_run_id,ordinal,previous_event_id,"
                    "stage_code,outcome_code) VALUES "
                    "(:tenant,:project,:loop,3,:root,'evaluate_a5_gate','completed')"
                ),
                {"tenant": tenant, "project": project, "loop": loop, "root": root},
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest_asyncio.fixture
async def loop_ctx(db_session):
    from app.tenancy import TenantContext

    suffix = uuid.uuid4().hex[:10]
    organization = (
        await db_session.execute(
            text(
                "INSERT INTO organizations (name,slug) VALUES ('LoopRepoOrg',:slug) RETURNING id"
            ),
            {"slug": f"loop-repo-org-{suffix}"},
        )
    ).scalar_one()
    tenant = (
        await db_session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) "
                "VALUES (:org,'LoopRepoTenant',:slug) RETURNING id"
            ),
            {"org": organization, "slug": f"loop-repo-tenant-{suffix}"},
        )
    ).scalar_one()
    project = (
        await db_session.execute(
            text(
                "INSERT INTO projects (tenant_id,name,slug) "
                "VALUES (:tenant,'LoopRepoProject',:slug) RETURNING id"
            ),
            {"tenant": tenant, "slug": f"loop-repo-project-{suffix}"},
        )
    ).scalar_one()
    run = (
        await db_session.execute(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": tenant, "project": project},
        )
    ).scalar_one()
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:tenant,true)"),
        {"tenant": str(tenant)},
    )
    return {
        "tenant": tenant,
        "project": project,
        "run": run,
        "context": TenantContext(tenant),
    }


@pytest.mark.db
async def test_repository_persists_exact_negative_evaluation_without_a_decision(
    loop_ctx, db_session
) -> None:
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.repositories.go_live_decisions import (
        GoLiveDecisionRepository,
        GoLiveDecisionRepositoryError,
    )

    repo = GoLiveDecisionRepository(db_session, loop_ctx["context"])
    cycle = await repo.start_cycle(
        project_id=loop_ctx["project"],
        project_run_id=loop_ctx["run"],
        idempotency_key="negative-cycle",
    )
    first = await repo.append_event(
        control_loop_run_id=cycle.id,
        stage_code="read_project_state",
        outcome_code="completed",
    )
    second = await repo.append_event(
        control_loop_run_id=cycle.id,
        stage_code="evaluate_a5_gate",
        outcome_code="blocked_evidence_or_authority",
    )
    assert first.ordinal == 1 and second.ordinal == 2
    assert second.previous_event_id == first.id

    report = ProductionAutonomyReport(
        project_id=str(loop_ctx["project"]),
        gates=[
            GateResult(number, f"gate_{number}", "passed", "test_passed", {})
            for number in range(1, 14)
        ],
    )
    evaluation = await repo.record_evaluation(
        control_loop_run_id=cycle.id,
        report=report,
        preapproval_gate_eligible=False,
        policy_decision="deny",
        emergency_latch_active=False,
        binding_ids={},
    )
    assert evaluation.passed_gate_count == 13
    assert evaluation.all_gates_passed is True
    with pytest.raises(GoLiveDecisionRepositoryError, match="predicate_not_satisfied"):
        await repo.finalize_decision(evaluation.id)
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM go_live_decisions WHERE project_id=:project"),
            {"project": loop_ctx["project"]},
        )
    ).scalar_one() == 0


@pytest.mark.db
async def test_cycle_start_is_idempotent_but_material_conflicts_fail_closed(
    loop_ctx, db_session
) -> None:
    from app.repositories.go_live_decisions import (
        GoLiveDecisionRepository,
        GoLiveDecisionRepositoryError,
    )

    repo = GoLiveDecisionRepository(db_session, loop_ctx["context"])
    first = await repo.start_cycle(
        project_id=loop_ctx["project"],
        project_run_id=loop_ctx["run"],
        idempotency_key="same-cycle",
    )
    retry = await repo.start_cycle(
        project_id=loop_ctx["project"],
        project_run_id=loop_ctx["run"],
        idempotency_key="same-cycle",
    )
    assert retry.id == first.id

    other_run = (
        await db_session.execute(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": loop_ctx["tenant"], "project": loop_ctx["project"]},
        )
    ).scalar_one()
    with pytest.raises(GoLiveDecisionRepositoryError, match="idempotency_conflict"):
        await repo.start_cycle(
            project_id=loop_ctx["project"],
            project_run_id=other_run,
            idempotency_key="same-cycle",
        )


@pytest.mark.db
async def test_real_checkpointed_loop_honors_cost_stop_before_first_stage(
    loop_ctx, db_session
) -> None:
    from app.runtime.control_loop import start_control_loop

    result = await start_control_loop(
        db_session,
        loop_ctx["context"],
        project_id=loop_ctx["project"],
        project_run_id=loop_ctx["run"],
        idempotency_key="cost-stop-cycle",
    )
    assert result["outcome_code"] == "paused_cost_stop"
    assert result["last_completed_stage"] is None
    assert (
        await db_session.execute(
            text("SELECT status FROM project_runs WHERE id=:run"),
            {"run": loop_ctx["run"]},
        )
    ).scalar_one() == "paused"
    assert (
        await db_session.execute(
            text(
                "SELECT event_type FROM run_steps WHERE run_id=:run "
                "ORDER BY seq DESC LIMIT 1"
            ),
            {"run": loop_ctx["run"]},
        )
    ).scalar_one() == "cost_paused"
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM go_live_evaluations WHERE project_id=:project"),
            {"project": loop_ctx["project"]},
        )
    ).scalar_one() == 0


@pytest.mark.db
async def test_infrastructure_exception_fails_safely_without_leaking_text(
    loop_ctx, db_session, monkeypatch
) -> None:
    from app.repositories.go_live_decisions import GoLiveDecisionRepositoryError
    from app.runtime.control_loop import ControlLoopCapabilities, start_control_loop

    sentinel = "SLICE55-INFRASTRUCTURE-SECRET"
    await db_session.execute(
        text(
            "INSERT INTO budgets "
            "(tenant_id,project_id,max_total_cost_usd,max_daily_cost_usd) "
            "VALUES (:tenant,:project,100,100)"
        ),
        {"tenant": loop_ctx["tenant"], "project": loop_ctx["project"]},
    )

    async def fail_coverage(self, *, as_of=None):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(ControlLoopCapabilities, "read_preapproval_coverage", fail_coverage)
    with pytest.raises(GoLiveDecisionRepositoryError, match="control_loop_infrastructure_failure"):
        await start_control_loop(
            db_session,
            loop_ctx["context"],
            project_id=loop_ctx["project"],
            project_run_id=loop_ctx["run"],
            idempotency_key="infrastructure-failure-cycle",
        )
    assert (
        await db_session.scalar(
            text("SELECT status FROM project_runs WHERE id=:run"),
            {"run": loop_ctx["run"]},
        )
        == "failed"
    )
    audit_text = json.dumps(
        (
            await db_session.execute(
                text(
                    "SELECT actor,action,target,payload FROM audit_logs "
                    "WHERE tenant_id=:tenant AND (action LIKE 'control_loop.%' OR action='run.run_failed')"
                ),
                {"tenant": loop_ctx["tenant"]},
            )
        )
        .mappings()
        .all(),
        default=str,
    )
    assert sentinel not in audit_text


@pytest_asyncio.fixture
async def decision_ready_ctx(db_session):
    from app.release.emergency_control_service import EmergencyControlService
    from app.release.production_approval_service import ProductionApprovalService
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.emergency_controls import EmergencyControlRepository
    from app.repositories.go_live_decisions import GoLiveDecisionRepository
    from app.repositories.production_preapprovals import ProductionPreapprovalRepository
    from tests.test_production_preapprovals import production_preapproval_ctx

    seeded = await production_preapproval_ctx.__wrapped__(db_session)
    requested = await ProductionApprovalService(
        db_session, seeded["requester_context"]
    ).request(project_id=seeded["project"], idempotency_key="slice55-request")
    approved = await ProductionApprovalService(
        db_session, seeded["approver_context"]
    ).approve(
        project_id=seeded["project"],
        request_id=requested.request_id,
        idempotency_key="slice55-approve",
    )
    await EmergencyControlService(db_session, seeded["approver_context"]).bind(
        project_id=seeded["project"], idempotency_key="slice55-emergency-bind"
    )
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    project_run = (
        await db_session.execute(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": seeded["tenant"], "project": seeded["project"]},
        )
    ).scalar_one()
    preapproval = await ProductionPreapprovalRepository(
        db_session, seeded["requester_context"]
    ).coverage_for_project(seeded["project"])
    emergency = await EmergencyControlRepository(
        db_session, seeded["requester_context"]
    ).status(seeded["project"])
    policy = await AutonomyPolicyRepository(
        db_session, seeded["requester_context"]
    ).decision_for(seeded["project"], "deploy_production")
    repo = GoLiveDecisionRepository(db_session, seeded["requester_context"])
    binding_ids, expiry = await repo.load_binding_snapshot(
        project_id=seeded["project"],
        request_id=preapproval.request_id,
        attestation_id=preapproval.attestation_id,
        emergency_binding_id=emergency.binding_id,
        emergency_event_id=emergency.event_id,
    )
    return {
        **seeded,
        "project_run": project_run,
        "approved": approved,
        "preapproval": preapproval,
        "emergency": emergency,
        "policy": policy,
        "binding_ids": binding_ids,
        "expiry": expiry,
    }


@pytest.mark.db
async def test_positive_decisions_are_fixed_hard_false_and_form_one_verified_chain(
    decision_ready_ctx, db_session
) -> None:
    from app.audit import verify_chain
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.repositories.go_live_decisions import GoLiveDecisionRepository

    ctx = decision_ready_ctx
    sentinel = "SLICE55-SENTINEL-SECRET-DO-NOT-PERSIST"
    assert ctx["preapproval"].gate_eligible is True
    assert ctx["policy"].value == "needs_approval"
    assert ctx["emergency"].state == "armed"
    report = ProductionAutonomyReport(
        project_id=str(ctx["project"]),
        gates=[
            GateResult(number, f"gate_{number}", "passed", "test_passed", {})
            for number in range(1, 14)
        ],
    )
    repo = GoLiveDecisionRepository(db_session, ctx["requester_context"])
    decisions = []
    for index in range(2):
        run = ctx["project_run"]
        if index:
            run = (
                await db_session.execute(
                    text(
                        "INSERT INTO project_runs (tenant_id,project_id,status) "
                        "VALUES (:tenant,:project,'created') RETURNING id"
                    ),
                    {"tenant": ctx["tenant"], "project": ctx["project"]},
                )
            ).scalar_one()
        cycle = await repo.start_cycle(
            project_id=ctx["project"],
            project_run_id=run,
            idempotency_key=f"positive-cycle-{index}-{sentinel}",
        )
        await repo.append_event(
            control_loop_run_id=cycle.id,
            stage_code="finalize_go_live_decision",
            outcome_code="decision_recorded",
        )
        evaluation = await repo.record_evaluation(
            control_loop_run_id=cycle.id,
            report=report,
            preapproval_gate_eligible=True,
            policy_decision="needs_approval",
            emergency_latch_active=False,
            binding_ids=ctx["binding_ids"],
            preapproval_expires_at=ctx["expiry"],
        )
        decisions.append(await repo.finalize_decision(evaluation.id))
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    assert all(item.status == "decided_not_executed" for item in decisions)
    assert all(item.production_action_executed is False for item in decisions)
    assert all(item.can_go_live_autonomously_snapshot is False for item in decisions)
    assert decisions[1].previous_decision_id == decisions[0].id
    assert decisions[1].prev_entry_hash == decisions[0].entry_hash
    assert (
        await db_session.execute(
            text("SELECT public.slice55_verify_decision_chain(:project)"),
            {"project": ctx["project"]},
        )
    ).scalar_one() is True
    audit_text = json.dumps(
        (
            await db_session.execute(
                text(
                    "SELECT actor,action,target,payload FROM audit_logs "
                    "WHERE tenant_id=:tenant AND action LIKE 'control_loop.%'"
                ),
                {"tenant": ctx["tenant"]},
            )
        )
        .mappings()
        .all(),
        default=str,
    )
    assert sentinel not in audit_text
    for forbidden in (
        "principal_subject",
        "policy_json",
        "repo_ref",
        "commit_sha",
        "raw_context",
        "exception_text",
    ):
        assert forbidden not in audit_text
    assert (await verify_chain(db_session))["ok"] is True
    for table in (
        "control_loop_runs",
        "control_loop_events",
        "go_live_evaluations",
        "go_live_evaluation_gate_results",
        "go_live_decisions",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(f"DELETE FROM {table} WHERE project_id=:project"),  # noqa: S608
                    {"project": ctx["project"]},
                )


@pytest.mark.db
async def test_cost_paused_loop_resumes_from_checkpoint_and_blocks_without_evidence(
    loop_ctx, db_session
) -> None:
    from app.runtime.control_loop import resume_control_loop, start_control_loop

    first = await start_control_loop(
        db_session,
        loop_ctx["context"],
        project_id=loop_ctx["project"],
        project_run_id=loop_ctx["run"],
        idempotency_key="resume-cycle",
    )
    assert first["outcome_code"] == "paused_cost_stop"
    replay = await start_control_loop(
        db_session,
        loop_ctx["context"],
        project_id=loop_ctx["project"],
        project_run_id=loop_ctx["run"],
        idempotency_key="resume-cycle",
    )
    assert replay["outcome_code"] == "paused_cost_stop"
    assert replay["control_loop_run_id"] == first["control_loop_run_id"]
    await db_session.execute(
        text(
            "INSERT INTO budgets "
            "(tenant_id,project_id,max_total_cost_usd,max_daily_cost_usd) "
            "VALUES (:tenant,:project,100,100)"
        ),
        {"tenant": loop_ctx["tenant"], "project": loop_ctx["project"]},
    )
    cycle_id = (
        await db_session.execute(
            text(
                "SELECT id FROM control_loop_runs WHERE project_id=:project "
                "ORDER BY created_at DESC,id DESC LIMIT 1"
            ),
            {"project": loop_ctx["project"]},
        )
    ).scalar_one()
    resumed = await resume_control_loop(
        db_session,
        loop_ctx["context"],
        project_id=loop_ctx["project"],
        project_run_id=loop_ctx["run"],
        control_loop_run_id=cycle_id,
    )
    assert resumed["outcome_code"] == "blocked_evidence_or_authority"
    assert resumed["last_completed_stage"] == "finalize_go_live_decision"
    assert (
        await db_session.execute(
            text("SELECT status FROM project_runs WHERE id=:run"),
            {"run": loop_ctx["run"]},
        )
    ).scalar_one() == "blocked"
    assert (
        await db_session.execute(
            text(
                "SELECT count(*) FROM run_steps "
                "WHERE run_id=:run AND event_type='cost_paused'"
            ),
            {"run": loop_ctx["run"]},
        )
    ).scalar_one() == 1
    assert (
        await db_session.execute(
            text("SELECT count(*) FROM go_live_decisions WHERE project_id=:project"),
            {"project": loop_ctx["project"]},
        )
    ).scalar_one() == 0


@pytest.mark.db
async def test_newer_negative_cycle_prevents_fallback_to_older_decision(
    decision_ready_ctx, db_session
) -> None:
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.repositories.go_live_decisions import GoLiveDecisionRepository

    ctx = decision_ready_ctx
    repo = GoLiveDecisionRepository(db_session, ctx["requester_context"])
    passed_report = ProductionAutonomyReport(
        project_id=str(ctx["project"]),
        gates=[
            GateResult(number, f"gate_{number}", "passed", "test_passed", {})
            for number in range(1, 14)
        ],
    )
    first_cycle = await repo.start_cycle(
        project_id=ctx["project"],
        project_run_id=ctx["project_run"],
        idempotency_key="old-positive",
    )
    first_evaluation = await repo.record_evaluation(
        control_loop_run_id=first_cycle.id,
        report=passed_report,
        preapproval_gate_eligible=True,
        policy_decision="needs_approval",
        emergency_latch_active=False,
        binding_ids=ctx["binding_ids"],
        preapproval_expires_at=ctx["expiry"],
    )
    historical = await repo.finalize_decision(first_evaluation.id)

    new_run = (
        await db_session.execute(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": ctx["tenant"], "project": ctx["project"]},
        )
    ).scalar_one()
    negative_cycle = await repo.start_cycle(
        project_id=ctx["project"],
        project_run_id=new_run,
        idempotency_key="new-negative",
    )
    await repo.record_evaluation(
        control_loop_run_id=negative_cycle.id,
        report=passed_report,
        preapproval_gate_eligible=False,
        policy_decision="deny",
        emergency_latch_active=False,
        binding_ids={},
    )
    assert (await repo.latest_decision(ctx["project"])).id == historical.id
    assert await repo.current_decision(ctx["project"]) is None


@pytest.mark.db
async def test_policy_change_between_evaluation_and_finalize_refuses(
    decision_ready_ctx, db_session
) -> None:
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.repositories.go_live_decisions import (
        GoLiveDecisionRepository,
        GoLiveDecisionRepositoryError,
    )

    ctx = decision_ready_ctx
    repo = GoLiveDecisionRepository(db_session, ctx["requester_context"])
    cycle = await repo.start_cycle(
        project_id=ctx["project"],
        project_run_id=ctx["project_run"],
        idempotency_key="policy-race",
    )
    evaluation = await repo.record_evaluation(
        control_loop_run_id=cycle.id,
        report=ProductionAutonomyReport(
            project_id=str(ctx["project"]),
            gates=[
                GateResult(number, f"gate_{number}", "passed", "test_passed", {})
                for number in range(1, 14)
            ],
        ),
        preapproval_gate_eligible=True,
        policy_decision="needs_approval",
        emergency_latch_active=False,
        binding_ids=ctx["binding_ids"],
        preapproval_expires_at=ctx["expiry"],
    )
    await db_session.execute(
        text(
            "UPDATE autonomy_policies SET autonomy_level=3,updated_at=clock_timestamp() "
            "WHERE id=:policy"
        ),
        {"policy": uuid.UUID(ctx["binding_ids"]["autonomy_policy_id"])},
    )
    with pytest.raises(GoLiveDecisionRepositoryError, match="decision_finalization_refused"):
        await repo.finalize_decision(evaluation.id)
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM go_live_decisions WHERE evaluation_id=:evaluation"),
            {"evaluation": evaluation.id},
        )
        == 0
    )


@pytest.mark.db
async def test_emergency_activation_between_evaluation_and_finalize_refuses(
    decision_ready_ctx, db_session
) -> None:
    from app.release.emergency_control_service import EmergencyControlService
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.repositories.go_live_decisions import (
        GoLiveDecisionRepository,
        GoLiveDecisionRepositoryError,
    )

    ctx = decision_ready_ctx
    repo = GoLiveDecisionRepository(db_session, ctx["requester_context"])
    cycle = await repo.start_cycle(
        project_id=ctx["project"],
        project_run_id=ctx["project_run"],
        idempotency_key="emergency-race",
    )
    evaluation = await repo.record_evaluation(
        control_loop_run_id=cycle.id,
        report=ProductionAutonomyReport(
            project_id=str(ctx["project"]),
            gates=[
                GateResult(number, f"gate_{number}", "passed", "test_passed", {})
                for number in range(1, 14)
            ],
        ),
        preapproval_gate_eligible=True,
        policy_decision="needs_approval",
        emergency_latch_active=False,
        binding_ids=ctx["binding_ids"],
        preapproval_expires_at=ctx["expiry"],
    )
    await EmergencyControlService(db_session, ctx["approver_context"]).activate(
        project_id=ctx["project"], idempotency_key="slice55-race-activate"
    )
    with pytest.raises(GoLiveDecisionRepositoryError, match="decision_finalization_refused"):
        await repo.finalize_decision(evaluation.id)
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM go_live_decisions WHERE evaluation_id=:evaluation"),
            {"evaluation": evaluation.id},
        )
        == 0
    )


@pytest.mark.db
async def test_preapproval_revocation_between_evaluation_and_finalize_refuses(
    decision_ready_ctx, db_session
) -> None:
    from app.release.production_approval_service import ProductionApprovalService
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.repositories.go_live_decisions import (
        GoLiveDecisionRepository,
        GoLiveDecisionRepositoryError,
    )

    ctx = decision_ready_ctx
    repo = GoLiveDecisionRepository(db_session, ctx["requester_context"])
    cycle = await repo.start_cycle(
        project_id=ctx["project"],
        project_run_id=ctx["project_run"],
        idempotency_key="preapproval-race",
    )
    evaluation = await repo.record_evaluation(
        control_loop_run_id=cycle.id,
        report=ProductionAutonomyReport(
            project_id=str(ctx["project"]),
            gates=[
                GateResult(number, f"gate_{number}", "passed", "test_passed", {})
                for number in range(1, 14)
            ],
        ),
        preapproval_gate_eligible=True,
        policy_decision="needs_approval",
        emergency_latch_active=False,
        binding_ids=ctx["binding_ids"],
        preapproval_expires_at=ctx["expiry"],
    )
    await ProductionApprovalService(db_session, ctx["approver_context"]).revoke(
        project_id=ctx["project"],
        attestation_id=ctx["approved"].attestation_id,
        idempotency_key="slice55-race-revoke",
    )
    with pytest.raises(GoLiveDecisionRepositoryError, match="decision_finalization_refused"):
        await repo.finalize_decision(evaluation.id)
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM go_live_decisions WHERE evaluation_id=:evaluation"),
            {"evaluation": evaluation.id},
        )
        == 0
    )


@pytest.mark.db
async def test_direct_sql_incomplete_evaluation_and_hard_false_forgery_are_rejected(
    loop_ctx, db_session
) -> None:
    digest = "sha256:" + "a" * 64
    loop = (
        await db_session.execute(
            text(
                "INSERT INTO control_loop_runs "
                "(tenant_id,project_id,project_run_id,idempotency_digest,"
                "control_loop_contract_version,control_loop_contract_hash) "
                "VALUES (:tenant,:project,:run,:digest,'slice55.control_loop.v1',:digest) "
                "RETURNING id"
            ),
            {
                "tenant": loop_ctx["tenant"],
                "project": loop_ctx["project"],
                "run": loop_ctx["run"],
                "digest": digest,
            },
        )
    ).scalar_one()
    with pytest.raises(DBAPIError, match="exact gate set incomplete"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO go_live_evaluations "
                    "(tenant_id,project_id,control_loop_run_id,evaluated_at,ruleset_version,"
                    "evaluation_contract_version,evaluation_contract_hash,gate_result_digest,"
                    "passed_gate_count,all_gates_passed,preapproval_gate_eligible,policy_decision,"
                    "emergency_latch_active,decision_binding_digest) VALUES "
                    "(:tenant,:project,:loop,clock_timestamp(),'slice54.v1',"
                    "'slice55.go_live_evaluation.v1',:digest,:digest,13,true,true,"
                    "'needs_approval',false,:digest)"
                ),
                {
                    "tenant": loop_ctx["tenant"],
                    "project": loop_ctx["project"],
                    "loop": loop,
                    "digest": digest,
                },
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    with pytest.raises(DBAPIError, match="hard_false"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO go_live_decisions "
                    "(tenant_id,project_id,control_loop_run_id,evaluation_id,"
                    "preapproval_request_id,preapproval_attestation_id,autonomy_policy_id,"
                    "autonomy_policy_digest,"
                    "emergency_control_binding_id,emergency_stop_event_id,release_candidate_id,"
                    "evidence_pack_id,release_verdict_id,evaluation_digest,decision_binding_digest,"
                    "status,authority_truth_tier,production_action_executed,"
                    "can_go_live_autonomously_snapshot,scope_limitation_digest,entry_hash) VALUES "
                    "(:tenant,:project,:id,:id,:id,:id,:id,:digest,:id,:id,:id,:id,:id,:digest,:digest,"
                    "'decided_not_executed',"
                    "'request_authenticated_key_custody_under_recorded_policy_not_human_signature',"
                    "true,true,:digest,:digest)"
                ),
                {
                    "tenant": loop_ctx["tenant"],
                    "project": loop_ctx["project"],
                    "id": uuid.uuid4(),
                    "digest": digest,
                },
            )
