"""Independent-review regressions for the owner-ruled Slice 55 remediation."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.release.go_live_decision import validate_event_transition
from app.tenancy import TenantContext
from tests.test_control_loop_owner_retry import _seed_project, _seed_two_projects


@pytest.mark.db
async def test_owned_start_persists_nonretryable_infrastructure_failure(
    admin_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.repositories.go_live_decisions import GoLiveDecisionRepositoryError
    from app.runtime import control_loop

    tenant_id, project_ids, run_ids = await _seed_two_projects(admin_engine)
    project_id = project_ids[0]
    run_id = run_ids[0]
    sentinel = "OWNER-INFRASTRUCTURE-DETAIL-MUST-NOT-PERSIST"
    monkeypatch.setattr("app.tenancy.get_engine", lambda: admin_engine)

    class FailingGraph:
        async def ainvoke(self, state, config):
            raise RuntimeError(sentinel)

    monkeypatch.setattr(control_loop, "_build_control_loop_graph", lambda *_: FailingGraph())
    with pytest.raises(
        GoLiveDecisionRepositoryError, match="control_loop_infrastructure_failure"
    ):
        await control_loop.start_control_loop_owned(
            TenantContext(tenant_id),
            project_id=project_id,
            project_run_id=run_id,
            idempotency_key="owner-persisted-infrastructure-failure",
        )

    async with admin_engine.connect() as connection:
        run_status = await connection.scalar(
            text("SELECT status FROM project_runs WHERE id=:run"),
            {"run": run_id},
        )
        events = (
            await connection.execute(
                text(
                    "SELECT stage_code,outcome_code FROM control_loop_events "
                    "WHERE project_id=:project ORDER BY ordinal"
                ),
                {"project": project_id},
            )
        ).all()
        audit_rows = (
            await connection.execute(
                text(
                    "SELECT action,payload FROM audit_logs "
                    "WHERE tenant_id=:tenant AND action LIKE 'control_loop.%'"
                ),
                {"tenant": tenant_id},
            )
        ).all()
    assert run_status == "failed"
    assert events == [("control_loop_runtime", "failed_infrastructure")]
    assert sentinel not in json.dumps(audit_rows, default=str)


@pytest.mark.db
@pytest.mark.serializable
async def test_start_checkpoints_under_its_cycle_namespace(db_session) -> None:
    from app.runtime.checkpointer import UAIDCheckpointer
    from app.runtime.control_loop import _config, start_control_loop

    context, project_id, run_id = await _seed_project(db_session)
    result = await start_control_loop(
        db_session,
        context,
        project_id=project_id,
        project_run_id=run_id,
        idempotency_key="owner-cycle-checkpoint-namespace",
    )
    cycle_id = uuid.UUID(str(result["control_loop_run_id"]))
    checkpointer = UAIDCheckpointer(
        db_session,
        context,
        project_id=project_id,
        run_id=run_id,
    )
    namespaces = set(
        (
            await db_session.execute(
                text(
                    "SELECT checkpoint_ns FROM run_checkpoints "
                    "WHERE run_id=:run"
                ),
                {"run": run_id},
            )
        ).scalars()
    )
    assert str(cycle_id) in namespaces
    assert (
        await checkpointer.aget_tuple(
            _config(run_id, control_loop_run_id=cycle_id)
        )
        is not None
    )


@pytest.mark.parametrize(
    ("previous_stage", "previous_outcome"),
    [
        ("read_project_state", "paused_cost_stop"),
        ("finalize_go_live_decision", "blocked_evidence_or_authority"),
        ("finalize_go_live_decision", "decision_recorded"),
    ],
)
def test_python_rejects_runtime_failure_after_guard_or_terminal(
    previous_stage: str, previous_outcome: str
) -> None:
    with pytest.raises(ValueError, match="control_loop_event_transition_invalid"):
        validate_event_transition(
            previous_stage,
            previous_outcome,
            "control_loop_runtime",
            "failed_infrastructure",
        )


@pytest.mark.db
async def test_database_rejects_runtime_failure_after_guard(db_session) -> None:
    from app.repositories.go_live_decisions import GoLiveDecisionRepository

    context, project_id, run_id = await _seed_project(db_session)
    repo = GoLiveDecisionRepository(db_session, context)
    cycle = await repo.start_cycle(
        project_id=project_id,
        project_run_id=run_id,
        idempotency_key="owner-runtime-transition-parity",
    )
    guard = await repo.append_event(
        control_loop_run_id=cycle.id,
        stage_code="read_project_state",
        outcome_code="paused_cost_stop",
    )
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    with pytest.raises(DBAPIError, match="transition is not allowed"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO control_loop_events "
                    "(tenant_id,project_id,control_loop_run_id,ordinal,previous_event_id,"
                    "stage_code,outcome_code) VALUES "
                    "(:tenant,:project,:cycle,2,:previous,'control_loop_runtime',"
                    "'failed_infrastructure')"
                ),
                {
                    "tenant": context.tenant_id,
                    "project": project_id,
                    "cycle": cycle.id,
                    "previous": guard.id,
                },
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
