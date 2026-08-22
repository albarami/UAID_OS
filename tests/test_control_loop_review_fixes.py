"""Reviewer-required Slice 55 honesty, isolation, and transition proofs."""

from __future__ import annotations

import ast
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.release.go_live_decision import CONTROL_LOOP_STAGE_SEQUENCE
from app.runtime.control_loop import (
    CHECKPOINT_FORBIDDEN_KEYS,
    CHECKPOINT_SAFE_KEYS,
    CONTROL_LOOP_NODES,
    UNAVAILABLE_OBSERVATION_STAGES,
    ControlLoopState,
    _ControlLoopExecutor,
)


def _execute_source() -> str:
    return Path("app/runtime/control_loop.py").read_text().split("async def execute")[1]


def test_execute_never_records_fake_completed_or_raw_a5_context() -> None:
    body = _execute_source().split("def _build_control_loop_graph")[0]
    assert 'outcome = "completed"' not in body
    assert "a5_report" not in body
    assert "to_dict()" not in body
    assert "latest_frozen_release_ref" not in body
    assert "await self._guard(stage_code)" in body
    assert body.index("await self._guard(stage_code)") < body.index(
        "UNAVAILABLE_OBSERVATION_STAGES"
    )


def test_unavailable_observation_nodes_are_the_first_three_non_invoking_stages() -> None:
    assert CONTROL_LOOP_NODES == CONTROL_LOOP_STAGE_SEQUENCE
    assert UNAVAILABLE_OBSERVATION_STAGES == frozenset(CONTROL_LOOP_STAGE_SEQUENCE[:3])


def test_every_production_node_is_present_in_the_execute_dispatch() -> None:
    tree = ast.parse(Path("app/runtime/control_loop.py").read_text())
    execute = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_ControlLoopExecutor"
    )
    method = next(
        node
        for node in execute.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute"
    )
    compared = {
        constant.value
        for node in ast.walk(method)
        if isinstance(node, ast.Compare)
        for constant in node.comparators
        if isinstance(constant, ast.Constant) and isinstance(constant.value, str)
    }
    assert set(CONTROL_LOOP_STAGE_SEQUENCE[3:]) <= compared


def test_checkpoint_state_is_exactly_the_approved_safe_shape() -> None:
    assert set(ControlLoopState.__annotations__) == CHECKPOINT_SAFE_KEYS
    assert CHECKPOINT_FORBIDDEN_KEYS.isdisjoint(CHECKPOINT_SAFE_KEYS)


@pytest.mark.parametrize("stage_code", CONTROL_LOOP_NODES)
async def test_every_production_node_invokes_guard_before_stage_work(
    stage_code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def _guard(self, observed: str) -> dict[str, object]:
        seen.append(observed)
        return {"outcome_code": "paused_cost_stop"}

    monkeypatch.setattr(_ControlLoopExecutor, "_guard", _guard)
    executor = _ControlLoopExecutor(
        object(),  # type: ignore[arg-type]
        SimpleNamespace(tenant_id=uuid.uuid4()),  # type: ignore[arg-type]
        project_id=uuid.uuid4(),
        project_run_id=uuid.uuid4(),
        control_loop_run_id=uuid.uuid4(),
        as_of=datetime.now(timezone.utc),
    )
    result = await executor.execute(stage_code, {"completed_stages": ()})
    assert seen == [stage_code]
    assert result == {"outcome_code": "paused_cost_stop"}


async def test_serializable_work_retries_the_complete_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.repositories.go_live_decisions import run_serializable_tenant_work
    from app.tenancy import TenantContext

    sessions: list[object] = []
    attempts = {"n": 0}

    @asynccontextmanager
    async def fake_scope(context, *, isolation_level=None):
        assert isolation_level == "SERIALIZABLE"
        session = SimpleNamespace()

        async def scalar(_stmt):
            return "serializable"

        session.scalar = scalar
        sessions.append(session)
        yield session

    monkeypatch.setattr("app.repositories.go_live_decisions.tenant_scope", fake_scope)

    async def work(session):
        attempts["n"] += 1
        assert session is sessions[-1]
        if attempts["n"] == 1:
            orig = type("Orig", (Exception,), {"sqlstate": "40001"})()
            raise DBAPIError("SELECT 1", {}, orig)
        return {"evaluation_id": str(uuid.uuid4()), "attempt": attempts["n"]}

    result = await run_serializable_tenant_work(TenantContext(uuid.uuid4()), work)
    assert result["attempt"] == 2
    assert attempts["n"] == 2
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]


@pytest.mark.db
async def test_invalid_stage_outcome_and_skipped_transition_are_rejected(db_session) -> None:
    suffix = uuid.uuid4().hex[:10]
    organization = (
        await db_session.execute(
            text(
                "INSERT INTO organizations (name,slug) VALUES ('TransOrg',:slug) RETURNING id"
            ),
            {"slug": f"trans-org-{suffix}"},
        )
    ).scalar_one()
    tenant = (
        await db_session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) "
                "VALUES (:org,'TransTenant',:slug) RETURNING id"
            ),
            {"org": organization, "slug": f"trans-tenant-{suffix}"},
        )
    ).scalar_one()
    project = (
        await db_session.execute(
            text(
                "INSERT INTO projects (tenant_id,name,slug) "
                "VALUES (:tenant,'TransProject',:slug) RETURNING id"
            ),
            {"tenant": tenant, "slug": f"trans-project-{suffix}"},
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
    digest = "sha256:" + "b" * 64
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
    with pytest.raises(DBAPIError, match="stage_outcome"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO control_loop_events "
                    "(tenant_id,project_id,control_loop_run_id,ordinal,previous_event_id,"
                    "stage_code,outcome_code) VALUES "
                    "(:tenant,:project,:loop,1,NULL,'read_project_state','completed')"
                ),
                {"tenant": tenant, "project": project, "loop": loop},
            )
    root = (
        await db_session.execute(
            text(
                "INSERT INTO control_loop_events "
                "(tenant_id,project_id,control_loop_run_id,ordinal,previous_event_id,"
                "stage_code,outcome_code) VALUES "
                "(:tenant,:project,:loop,1,NULL,'read_project_state',"
                "'capability_unavailable_not_executed') RETURNING id"
            ),
            {"tenant": tenant, "project": project, "loop": loop},
        )
    ).scalar_one()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    with pytest.raises(DBAPIError, match="transition is not allowed"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO control_loop_events "
                    "(tenant_id,project_id,control_loop_run_id,ordinal,previous_event_id,"
                    "stage_code,outcome_code) VALUES "
                    "(:tenant,:project,:loop,2,:root,'evaluate_a5_gate',"
                    "'a5_evaluation_completed')"
                ),
                {"tenant": tenant, "project": project, "loop": loop, "root": root},
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.db
async def test_failed_gate_status_is_rejected_by_three_status_vocabulary(db_session) -> None:
    suffix = uuid.uuid4().hex[:10]
    organization = (
        await db_session.execute(
            text(
                "INSERT INTO organizations (name,slug) VALUES ('GateOrg',:slug) RETURNING id"
            ),
            {"slug": f"gate-org-{suffix}"},
        )
    ).scalar_one()
    tenant = (
        await db_session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) "
                "VALUES (:org,'GateTenant',:slug) RETURNING id"
            ),
            {"org": organization, "slug": f"gate-tenant-{suffix}"},
        )
    ).scalar_one()
    project = (
        await db_session.execute(
            text(
                "INSERT INTO projects (tenant_id,name,slug) "
                "VALUES (:tenant,'GateProject',:slug) RETURNING id"
            ),
            {"tenant": tenant, "slug": f"gate-project-{suffix}"},
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
    digest = "sha256:" + "c" * 64
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
    evaluation = (
        await db_session.execute(
            text(
                "INSERT INTO go_live_evaluations "
                "(tenant_id,project_id,control_loop_run_id,evaluated_at,ruleset_version,"
                "evaluation_contract_version,evaluation_contract_hash,gate_result_digest,"
                "passed_gate_count,all_gates_passed,preapproval_gate_eligible,policy_decision,"
                "emergency_latch_active,decision_binding_digest) VALUES "
                "(:tenant,:project,:loop,clock_timestamp(),'slice54.v1',"
                "'slice55.go_live_evaluation.v1',:digest,:digest,0,false,false,'deny',false,"
                ":digest) RETURNING id"
            ),
            {"tenant": tenant, "project": project, "loop": loop, "digest": digest},
        )
    ).scalar_one()
    with pytest.raises(DBAPIError, match="status"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO go_live_evaluation_gate_results "
                    "(tenant_id,project_id,evaluation_id,gate_number,gate_name_code,status,"
                    "reason_code,safe_context_digest,ordinal) VALUES "
                    "(:tenant,:project,:evaluation,1,'gate_1','failed','reason',:digest,1)"
                ),
                {
                    "tenant": tenant,
                    "project": project,
                    "evaluation": evaluation,
                    "digest": digest,
                },
            )


@pytest.mark.db
async def test_two_connections_cannot_fork_the_event_root(admin_engine) -> None:
    suffix = uuid.uuid4().hex[:10]
    async with admin_engine.begin() as conn:
        organization = await conn.scalar(
            text(
                "INSERT INTO organizations (name,slug) VALUES ('RaceOrg',:slug) RETURNING id"
            ),
            {"slug": f"race-org-{suffix}"},
        )
        tenant = await conn.scalar(
            text(
                "INSERT INTO tenants (organization_id,name,slug) "
                "VALUES (:org,'RaceTenant',:slug) RETURNING id"
            ),
            {"org": organization, "slug": f"race-tenant-{suffix}"},
        )
        project = await conn.scalar(
            text(
                "INSERT INTO projects (tenant_id,name,slug) "
                "VALUES (:tenant,'RaceProject',:slug) RETURNING id"
            ),
            {"tenant": tenant, "slug": f"race-project-{suffix}"},
        )
        run = await conn.scalar(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": tenant, "project": project},
        )
        digest = "sha256:" + "d" * 64
        loop = await conn.scalar(
            text(
                "INSERT INTO control_loop_runs "
                "(tenant_id,project_id,project_run_id,idempotency_digest,"
                "control_loop_contract_version,control_loop_contract_hash) "
                "VALUES (:tenant,:project,:run,:digest,'slice55.control_loop.v1',:digest) "
                "RETURNING id"
            ),
            {"tenant": tenant, "project": project, "run": run, "digest": digest},
        )

    insert = text(
        "INSERT INTO control_loop_events "
        "(tenant_id,project_id,control_loop_run_id,ordinal,previous_event_id,"
        "stage_code,outcome_code) VALUES "
        "(:tenant,:project,:loop,1,NULL,'read_project_state',"
        "'capability_unavailable_not_executed')"
    )
    params = {"tenant": tenant, "project": project, "loop": loop}
    barrier = asyncio.Barrier(2)

    async def insert_root():
        async with admin_engine.connect() as conn:
            await conn.execution_options(isolation_level="SERIALIZABLE")
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant',:tenant,true)"),
                    {"tenant": str(tenant)},
                )
                isolation = await conn.scalar(text("SHOW transaction_isolation"))
                assert isolation == "serializable"
                await barrier.wait()
                return await conn.execute(insert, params)

    results = await asyncio.gather(insert_root(), insert_root(), return_exceptions=True)
    assert sum(isinstance(item, Exception) for item in results) == 1
    async with admin_engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM control_loop_events WHERE control_loop_run_id=:loop"),
            {"loop": loop},
        )
    assert count == 1


@pytest.mark.db
async def test_tenant_scope_serializable_is_visible_to_show(
    admin_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tenancy import TenantContext, tenant_scope

    monkeypatch.setattr("app.tenancy.get_engine", lambda: admin_engine)
    async with tenant_scope(
        TenantContext(uuid.uuid4()), isolation_level="SERIALIZABLE"
    ) as session:
        isolation = await session.scalar(text("SHOW transaction_isolation"))
        assert isolation == "serializable"


@pytest.mark.db
async def test_serializable_retry_discards_first_transaction_writes(
    admin_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.repositories.go_live_decisions import run_serializable_tenant_work
    from app.tenancy import TenantContext

    suffix = uuid.uuid4().hex[:10]
    async with admin_engine.begin() as conn:
        organization = await conn.scalar(
            text(
                "INSERT INTO organizations (name,slug) VALUES ('RetryOrg',:slug) RETURNING id"
            ),
            {"slug": f"retry-org-{suffix}"},
        )
        tenant = await conn.scalar(
            text(
                "INSERT INTO tenants (organization_id,name,slug) "
                "VALUES (:org,'RetryTenant',:slug) RETURNING id"
            ),
            {"org": organization, "slug": f"retry-tenant-{suffix}"},
        )
        project = await conn.scalar(
            text(
                "INSERT INTO projects (tenant_id,name,slug) "
                "VALUES (:tenant,'RetryProject',:slug) RETURNING id"
            ),
            {"tenant": tenant, "slug": f"retry-project-{suffix}"},
        )
        run = await conn.scalar(
            text(
                "INSERT INTO project_runs (tenant_id,project_id,status) "
                "VALUES (:tenant,:project,'created') RETURNING id"
            ),
            {"tenant": tenant, "project": project},
        )

    monkeypatch.setattr("app.tenancy.get_engine", lambda: admin_engine)
    attempts = {"n": 0}

    async def work(session):
        attempts["n"] += 1
        digest = "sha256:" + f"{attempts['n']:064x}"
        await session.execute(
            text(
                "INSERT INTO control_loop_runs "
                "(tenant_id,project_id,project_run_id,idempotency_digest,"
                "control_loop_contract_version,control_loop_contract_hash) "
                "VALUES (:tenant,:project,:run,:digest,'slice55.control_loop.v1',:digest)"
            ),
            {"tenant": tenant, "project": project, "run": run, "digest": digest},
        )
        if attempts["n"] == 1:
            orig = type("Orig", (Exception,), {"sqlstate": "40001"})()
            raise DBAPIError("SELECT 1", {}, orig)
        return attempts["n"]

    result = await run_serializable_tenant_work(TenantContext(tenant), work)
    assert result == 2
    async with admin_engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM control_loop_runs WHERE project_id=:project"),
            {"project": project},
        )
        digests = list(
            (
                await conn.execute(
                    text(
                        "SELECT idempotency_digest FROM control_loop_runs "
                        "WHERE project_id=:project"
                    ),
                    {"project": project},
                )
            ).scalars()
        )
    assert count == 1
    assert digests == ["sha256:" + f"{2:064x}"]
