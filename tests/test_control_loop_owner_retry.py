"""Owner-ruled Slice 55 transaction-retry proofs."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.tenancy import TenantContext


def _dbapi_error(sqlstate: str) -> DBAPIError:
    original = type("OriginalDatabaseError", (Exception,), {"sqlstate": sqlstate})()
    return DBAPIError("owner_retry_probe", {}, original)


async def _seed_two_projects(admin_engine) -> tuple[uuid.UUID, list[uuid.UUID], list[uuid.UUID]]:
    suffix = uuid.uuid4().hex[:10]
    async with admin_engine.begin() as connection:
        organization_id = await connection.scalar(
            text(
                "INSERT INTO organizations (name,slug) "
                "VALUES ('OwnerRetryOrg',:slug) RETURNING id"
            ),
            {"slug": f"owner-retry-org-{suffix}"},
        )
        tenant_id = await connection.scalar(
            text(
                "INSERT INTO tenants (organization_id,name,slug) "
                "VALUES (:organization,'OwnerRetryTenant',:slug) RETURNING id"
            ),
            {
                "organization": organization_id,
                "slug": f"owner-retry-tenant-{suffix}",
            },
        )
        project_ids: list[uuid.UUID] = []
        run_ids: list[uuid.UUID] = []
        for index in range(2):
            project_id = await connection.scalar(
                text(
                    "INSERT INTO projects (tenant_id,name,slug) "
                    "VALUES (:tenant,:name,:slug) RETURNING id"
                ),
                {
                    "tenant": tenant_id,
                    "name": f"OwnerRetryProject{index}",
                    "slug": f"owner-retry-project-{index}-{suffix}",
                },
            )
            run_id = await connection.scalar(
                text(
                    "INSERT INTO project_runs (tenant_id,project_id,status) "
                    "VALUES (:tenant,:project,'created') RETURNING id"
                ),
                {"tenant": tenant_id, "project": project_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO budgets "
                    "(tenant_id,project_id,max_total_cost_usd,max_daily_cost_usd) "
                    "VALUES (:tenant,:project,1,1)"
                ),
                {"tenant": tenant_id, "project": project_id},
            )
            project_ids.append(project_id)
            run_ids.append(run_id)
    return tenant_id, project_ids, run_ids


async def _seed_project(session) -> tuple[TenantContext, uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:10]
    organization_id = await session.scalar(
        text(
            "INSERT INTO organizations (name,slug) "
            "VALUES ('OwnerPropagationOrg',:slug) RETURNING id"
        ),
        {"slug": f"owner-propagation-org-{suffix}"},
    )
    tenant_id = await session.scalar(
        text(
            "INSERT INTO tenants (organization_id,name,slug) "
            "VALUES (:organization,'OwnerPropagationTenant',:slug) RETURNING id"
        ),
        {
            "organization": organization_id,
            "slug": f"owner-propagation-tenant-{suffix}",
        },
    )
    project_id = await session.scalar(
        text(
            "INSERT INTO projects (tenant_id,name,slug) "
            "VALUES (:tenant,'OwnerPropagationProject',:slug) RETURNING id"
        ),
        {"tenant": tenant_id, "slug": f"owner-propagation-project-{suffix}"},
    )
    run_id = await session.scalar(
        text(
            "INSERT INTO project_runs (tenant_id,project_id,status) "
            "VALUES (:tenant,:project,'created') RETURNING id"
        ),
        {"tenant": tenant_id, "project": project_id},
    )
    await session.execute(
        text("SELECT set_config('app.current_tenant',:tenant,true)"),
        {"tenant": str(tenant_id)},
    )
    return TenantContext(tenant_id), project_id, run_id


@pytest.mark.db
@pytest.mark.serializable
async def test_start_does_not_reclassify_40001(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.runtime import control_loop

    context, project_id, run_id = await _seed_project(db_session)
    infrastructure_calls: list[object] = []

    class FailingGraph:
        async def ainvoke(self, state, config):
            raise _dbapi_error("40001")

    async def record_failure(executor) -> None:
        infrastructure_calls.append(executor)

    monkeypatch.setattr(control_loop, "_build_control_loop_graph", lambda *_: FailingGraph())
    monkeypatch.setattr(control_loop, "_record_infrastructure_failure", record_failure)

    with pytest.raises(DBAPIError) as raised:
        await control_loop.start_control_loop(
            db_session,
            context,
            project_id=project_id,
            project_run_id=run_id,
            idempotency_key="owner-40001-propagates",
        )
    assert control_loop.is_retryable_transaction_error(raised.value)
    assert infrastructure_calls == []


@pytest.mark.db
async def test_owned_start_retries_deadlock_through_fifth_attempt(
    admin_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.runtime import control_loop

    tenant_id, project_ids, run_ids = await _seed_two_projects(admin_engine)
    monkeypatch.setattr("app.tenancy.get_engine", lambda: admin_engine)
    attempts = 0

    async def fail_four_times(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 5:
            raise _dbapi_error("40P01")
        return {"outcome_code": "eventual_success"}

    monkeypatch.setattr(control_loop, "start_control_loop", fail_four_times)
    result = await control_loop.start_control_loop_owned(
        TenantContext(tenant_id),
        project_id=project_ids[0],
        project_run_id=run_ids[0],
        idempotency_key="owner-deadlock-retry",
    )
    assert result == {"outcome_code": "eventual_success"}
    assert attempts == 5


@pytest.mark.db
async def test_two_owned_starts_retry_real_serialization_conflict(
    admin_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.runtime import control_loop

    tenant_id, project_ids, run_ids = await _seed_two_projects(admin_engine)
    monkeypatch.setattr("app.tenancy.get_engine", lambda: admin_engine)
    barrier = asyncio.Barrier(2)
    attempts = {project_id: 0 for project_id in project_ids}

    async def write_skew(
        session,
        context,
        *,
        project_id,
        project_run_id,
        idempotency_key,
        as_of=None,
    ):
        attempts[project_id] += 1
        await session.scalar(
            text("SELECT sum(max_daily_cost_usd) FROM budgets WHERE tenant_id=:tenant"),
            {"tenant": tenant_id},
        )
        if attempts[project_id] == 1:
            await barrier.wait()
        await session.execute(
            text(
                "UPDATE budgets SET max_daily_cost_usd=max_daily_cost_usd+1 "
                "WHERE project_id=:project"
            ),
            {"project": project_id},
        )
        return {"project_id": str(project_id)}

    monkeypatch.setattr(control_loop, "start_control_loop", write_skew)
    context = TenantContext(tenant_id)
    results = await asyncio.gather(
        *(
            control_loop.start_control_loop_owned(
                context,
                project_id=project_id,
                project_run_id=run_id,
                idempotency_key=f"owner-concurrent-{index}",
            )
            for index, (project_id, run_id) in enumerate(zip(project_ids, run_ids, strict=True))
        )
    )
    assert {result["project_id"] for result in results} == {
        str(project_id) for project_id in project_ids
    }
    assert sum(attempts.values()) > 2


def test_resume_has_an_owned_retry_entry_point() -> None:
    from app.runtime import control_loop

    assert isinstance(getattr(control_loop, "resume_control_loop_owned", None), Callable)


@pytest.mark.db
@pytest.mark.serializable
async def test_approved_blocked_resume_creates_fresh_cycle_events_and_evaluation(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.repositories.approvals import ApprovalRepository
    from app.runtime import control_loop
    from tests.test_control_loop import _seed_decision_ready

    seeded = await _seed_decision_ready(db_session)
    project_id = seeded["project"]
    run_id = seeded["project_run"]
    context = seeded["requester_context"]
    await db_session.execute(
        text(
            "INSERT INTO budgets "
            "(tenant_id,project_id,max_total_cost_usd,max_daily_cost_usd) "
            "VALUES (:tenant,:project,100,100)"
        ),
        {"tenant": seeded["tenant"], "project": project_id},
    )

    async def negative_a5(self, *, as_of=None):
        return ProductionAutonomyReport(
            project_id=str(project_id),
            gates=[
                GateResult(
                    number,
                    f"gate_{number}",
                    "insufficient_evidence" if number == 1 else "passed",
                    "owner_resume_probe",
                    {},
                )
                for number in range(1, 14)
            ],
        )

    monkeypatch.setattr(control_loop.ControlLoopCapabilities, "evaluate_a5", negative_a5)
    first = await control_loop.start_control_loop(
        db_session,
        context,
        project_id=project_id,
        project_run_id=run_id,
        idempotency_key="owner-blocked-initial",
    )
    assert first["outcome_code"] == "blocked_evidence_or_authority"
    first_cycle_id = uuid.UUID(str(first["control_loop_run_id"]))
    approval_subject = f"production_preapproval:{seeded['preapproval'].request_id}"
    assert (
        await ApprovalRepository(db_session, context).is_blocked(
            project_id,
            "deploy_production",
            subject_ref=approval_subject,
        )
        is False
    )

    prior_event_rows = (
        await db_session.execute(
            text(
                "SELECT id,ordinal,stage_code,outcome_code FROM control_loop_events "
                "WHERE control_loop_run_id=:cycle ORDER BY ordinal"
            ),
            {"cycle": first_cycle_id},
        )
    ).all()
    prior_evaluation_ids = (
        await db_session.execute(
            text(
                "SELECT id FROM go_live_evaluations "
                "WHERE control_loop_run_id=:cycle ORDER BY created_at,id"
            ),
            {"cycle": first_cycle_id},
        )
    ).scalars().all()
    prior_step_count = await db_session.scalar(
        text("SELECT count(*) FROM run_steps WHERE run_id=:run"),
        {"run": run_id},
    )

    resumed = await control_loop.resume_control_loop(
        db_session,
        context,
        project_id=project_id,
        project_run_id=run_id,
        control_loop_run_id=first_cycle_id,
    )
    resumed_cycle_id = uuid.UUID(str(resumed["control_loop_run_id"]))
    assert resumed_cycle_id != first_cycle_id
    assert resumed["outcome_code"] == "blocked_evidence_or_authority"
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM go_live_evaluations "
                "WHERE control_loop_run_id=:cycle"
            ),
            {"cycle": resumed_cycle_id},
        )
        == 1
    )
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM control_loop_events "
                "WHERE control_loop_run_id=:cycle"
            ),
            {"cycle": resumed_cycle_id},
        )
        > 0
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM run_steps WHERE run_id=:run"),
            {"run": run_id},
        )
        > prior_step_count
    )
    assert (
        await db_session.execute(
            text(
                "SELECT id,ordinal,stage_code,outcome_code FROM control_loop_events "
                "WHERE control_loop_run_id=:cycle ORDER BY ordinal"
            ),
            {"cycle": first_cycle_id},
        )
    ).all() == prior_event_rows
    assert (
        await db_session.execute(
            text(
                "SELECT id FROM go_live_evaluations "
                "WHERE control_loop_run_id=:cycle ORDER BY created_at,id"
            ),
            {"cycle": first_cycle_id},
        )
    ).scalars().all() == prior_evaluation_ids


async def test_staging_stage_does_not_claim_observation_without_gate_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.release.production_autonomy import GateResult, ProductionAutonomyReport
    from app.runtime import control_loop

    recorded_events: list[dict[str, object]] = []

    async def clear_guard(self, stage_code):
        return None

    async def evaluate_a5(*, as_of=None):
        return ProductionAutonomyReport(
            project_id="owner-staging-probe",
            gates=[
                GateResult(
                    number,
                    f"gate_{number}",
                    "no_evidence_source" if number == 10 else "passed",
                    "owner_staging_probe",
                    {},
                )
                for number in range(1, 14)
            ],
        )

    async def append_event(**fields):
        recorded_events.append(fields)

    monkeypatch.setattr(control_loop._ControlLoopExecutor, "_guard", clear_guard)
    executor = control_loop._ControlLoopExecutor(
        object(),  # type: ignore[arg-type]
        SimpleNamespace(tenant_id=uuid.uuid4()),  # type: ignore[arg-type]
        project_id=uuid.uuid4(),
        project_run_id=uuid.uuid4(),
        control_loop_run_id=uuid.uuid4(),
        as_of=control_loop.datetime.now(control_loop.timezone.utc),
    )
    untyped_executor = cast(Any, executor)
    untyped_executor.capabilities = SimpleNamespace(evaluate_a5=evaluate_a5)
    untyped_executor.decisions = SimpleNamespace(append_event=append_event)

    await executor.execute("observe_staging_evidence", {"completed_stages": ()})
    assert recorded_events[0]["outcome_code"] == "staging_evidence_not_observed"


@pytest.mark.db
@pytest.mark.serializable
async def test_zero_persisted_staging_evidence_records_not_observed(db_session) -> None:
    from app.runtime.control_loop import start_control_loop

    context, project_id, run_id = await _seed_project(db_session)
    await db_session.execute(
        text(
            "INSERT INTO budgets "
            "(tenant_id,project_id,max_total_cost_usd,max_daily_cost_usd) "
            "VALUES (:tenant,:project,1,1)"
        ),
        {"tenant": context.tenant_id, "project": project_id},
    )

    await start_control_loop(
        db_session,
        context,
        project_id=project_id,
        project_run_id=run_id,
        idempotency_key="owner-zero-staging-evidence",
    )
    outcome = await db_session.scalar(
        text(
            "SELECT outcome_code FROM control_loop_events "
            "WHERE project_id=:project AND stage_code='observe_staging_evidence' "
            "ORDER BY ordinal DESC LIMIT 1"
        ),
        {"project": project_id},
    )
    assert outcome == "staging_evidence_not_observed"


