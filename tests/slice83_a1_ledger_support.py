"""Slice 83 commit-8 helpers: SQL-function mutation, unique isolation, seeds."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock

from langgraph.checkpoint.base import Checkpoint, WRITES_IDX_MAP
from langchain_core.runnables import RunnableConfig
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.run_checkpoint_write import RunCheckpointWrite
from app.release.production_autonomy import GateResult, ProductionAutonomyReport
from app.runtime.checkpointer import UAIDCheckpointer
from app.tenancy import TenantContext
from tests.slice83_a1_support import seed_emergency_project
from tests.slice83_support import bind_tenant, seed_org_tenant_project
from tests.test_runtime import _ckpt, _config

SKIP_SERIALIZABLE = AsyncMock(return_value=None)

_DROP: dict[str, str] = {
    "uq_ese_previous": ("ALTER TABLE public.emergency_stop_events DROP CONSTRAINT uq_ese_previous"),
    "uq_ese_idempotency": (
        "ALTER TABLE public.emergency_stop_events DROP CONSTRAINT uq_ese_idempotency"
    ),
    "uq_gld_previous": "ALTER TABLE public.go_live_decisions DROP CONSTRAINT uq_gld_previous",
    "uq_gld_entry_hash": ("ALTER TABLE public.go_live_decisions DROP CONSTRAINT uq_gld_entry_hash"),
    "uq_gld_evaluation": ("ALTER TABLE public.go_live_decisions DROP CONSTRAINT uq_gld_evaluation"),
    "uq_gld_project_root": "DROP INDEX public.uq_gld_project_root",
    "uq_admin_policy_changes_action": (
        "ALTER TABLE public.admin_policy_changes DROP CONSTRAINT uq_admin_policy_changes_action"
    ),
}
_RESTORE: dict[str, str] = {
    "uq_ese_previous": (
        "ALTER TABLE public.emergency_stop_events "
        "ADD CONSTRAINT uq_ese_previous UNIQUE (previous_event_id)"
    ),
    "uq_ese_idempotency": (
        "ALTER TABLE public.emergency_stop_events ADD CONSTRAINT uq_ese_idempotency "
        "UNIQUE (tenant_id, project_id, idempotency_key_hash)"
    ),
    "uq_gld_previous": (
        "ALTER TABLE public.go_live_decisions "
        "ADD CONSTRAINT uq_gld_previous UNIQUE (previous_decision_id)"
    ),
    "uq_gld_entry_hash": (
        "ALTER TABLE public.go_live_decisions ADD CONSTRAINT uq_gld_entry_hash UNIQUE (entry_hash)"
    ),
    "uq_gld_evaluation": (
        "ALTER TABLE public.go_live_decisions "
        "ADD CONSTRAINT uq_gld_evaluation UNIQUE (evaluation_id)"
    ),
    "uq_gld_project_root": (
        "CREATE UNIQUE INDEX uq_gld_project_root ON public.go_live_decisions "
        "(tenant_id, project_id) WHERE previous_decision_id IS NULL"
    ),
    "uq_admin_policy_changes_action": (
        "ALTER TABLE public.admin_policy_changes "
        "ADD CONSTRAINT uq_admin_policy_changes_action UNIQUE (admin_action_id)"
    ),
}

_FN_REGPROC = {
    "audit_append": "public.audit_append(text, text, text, jsonb)",
    "slice55_finalize_decision": "public.slice55_finalize_decision(uuid)",
}


def _as_replace(definition: str) -> str:
    if definition.startswith("CREATE OR REPLACE FUNCTION"):
        return definition
    return definition.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


@asynccontextmanager
async def without_uniques(admin_engine: AsyncEngine, names: Sequence[str]) -> AsyncIterator[None]:
    """Drop named unique indexes for one mutation, then restore them."""
    async with admin_engine.begin() as conn:
        for name in names:
            await conn.execute(text(_DROP[name]))
    try:
        yield
    finally:
        async with admin_engine.begin() as conn:
            for name in names:
                await conn.execute(text(_RESTORE[name]))


async def _function_def(admin_engine: AsyncEngine, name: str) -> str:
    async with admin_engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT pg_get_functiondef(to_regprocedure(:sig))"),
                {"sig": _FN_REGPROC[name]},
            )
        ).scalar_one()


@asynccontextmanager
async def without_advisory_lock(admin_engine: AsyncEngine) -> AsyncIterator[None]:
    """Reinstall ``audit_append`` without lock 421; restore owner and grants."""
    original = await _function_def(admin_engine, "audit_append")
    racy = _as_replace(original).replace("PERFORM pg_advisory_xact_lock(421);", "")
    assert "pg_advisory_xact_lock" not in racy
    async with admin_engine.begin() as conn:
        await conn.execute(text(racy))
        await conn.execute(
            text(
                "ALTER FUNCTION public.audit_append(text, text, text, jsonb) OWNER TO audit_writer"
            )
        )
        await conn.execute(
            text(
                "GRANT EXECUTE ON FUNCTION public.audit_append(text, text, text, jsonb) TO uaid_app"
            )
        )
    try:
        yield
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(text(_as_replace(original)))
            await conn.execute(
                text(
                    "ALTER FUNCTION public.audit_append(text, text, text, jsonb) OWNER TO audit_writer"
                )
            )
            await conn.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION public.audit_append(text, text, text, jsonb) TO uaid_app"
                )
            )


@asynccontextmanager
async def without_finalize_row_locks(admin_engine: AsyncEngine) -> AsyncIterator[None]:
    """Reinstall ``slice55_finalize_decision`` without ``FOR UPDATE``."""
    original = await _function_def(admin_engine, "slice55_finalize_decision")
    racy = _as_replace(original).replace(" FOR UPDATE", "")
    assert "FOR UPDATE" not in racy
    async with admin_engine.begin() as conn:
        await conn.execute(text(racy))
        await conn.execute(
            text("GRANT EXECUTE ON FUNCTION public.slice55_finalize_decision(uuid) TO uaid_app")
        )
    try:
        yield
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(text(_as_replace(original)))
            await conn.execute(
                text("GRANT EXECUTE ON FUNCTION public.slice55_finalize_decision(uuid) TO uaid_app")
            )


async def reset_audit_chain(admin_engine: AsyncEngine) -> None:
    """Empty the global audit log so ``audit_verify()`` is load-bearing."""
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_update_delete")
        )
        await conn.execute(text("DELETE FROM audit_logs"))
        await conn.execute(
            text("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_no_update_delete")
        )
        await conn.execute(text("ALTER SEQUENCE audit_logs_seq RESTART WITH 1"))


async def keep_one_policy_change(admin_engine: AsyncEngine, action_id: Any) -> None:
    """Drop duplicate same-action ledger rows before restoring the unique."""
    async with admin_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE admin_policy_changes DISABLE TRIGGER ALL"))
        await conn.execute(
            text(
                "DELETE FROM admin_policy_changes WHERE admin_action_id=:a AND id NOT IN "
                "(SELECT id FROM admin_policy_changes WHERE admin_action_id=:a ORDER BY created_at, id LIMIT 1)"
            ),
            {"a": action_id},
        )
        await conn.execute(text("ALTER TABLE admin_policy_changes ENABLE TRIGGER ALL"))


async def purge_gld_project(admin_engine: AsyncEngine, project_id: Any) -> None:
    """Remove a mutation's extra decision rows so unique restores can succeed."""
    async with admin_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE go_live_decisions DISABLE TRIGGER ALL"))
        await conn.execute(
            text("DELETE FROM go_live_decisions WHERE project_id=:p"), {"p": project_id}
        )
        await conn.execute(text("ALTER TABLE go_live_decisions ENABLE TRIGGER ALL"))


async def racy_aput_writes(self, config, writes, task_id, task_path=""):
    """``aput_writes`` without ``ON CONFLICT DO UPDATE`` — mutation control."""
    self._check_thread(config)
    cfg = self._configurable(config)
    ns = self._namespace(config)
    checkpoint_id = cfg["checkpoint_id"]
    for idx, (channel, value) in enumerate(writes):
        write_idx = WRITES_IDX_MAP.get(channel, idx)
        type_, blob = self.serde.dumps_typed(value)
        stmt = pg_insert(RunCheckpointWrite).values(
            tenant_id=self.context.tenant_id,
            project_id=self.project_id,
            run_id=self.run_id,
            thread_id=self.thread_id,
            checkpoint_ns=ns,
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            idx=write_idx,
            channel=channel,
            type=type_,
            blob=blob,
            task_path=task_path,
        )
        await self.session.execute(stmt)


async def seed_checkpoint_world(
    rls_engine: AsyncEngine, admin_engine: AsyncEngine
) -> dict[str, Any]:
    """Committed project-run plus one checkpoint the write race can contend."""
    world = await seed_org_tenant_project(admin_engine)
    async with admin_engine.begin() as conn:
        run = (
            await conn.execute(
                text(
                    "INSERT INTO project_runs (tenant_id,project_id,status) "
                    "VALUES (:t,:p,'created') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(rls_engine) as session:
        await bind_tenant(session, world["tenant"])
        cp = UAIDCheckpointer(session, ctx, project_id=world["project"], run_id=run)
        await cp.aput(
            cast(RunnableConfig, _config(run)),
            cast(Checkpoint, _ckpt("cp-1", {"x": 1})),
            {"source": "input", "step": 0},
            {},
        )
        await session.commit()
    world["run"] = run
    world["ctx"] = ctx
    return world


async def seed_armed_stop(rls_engine: AsyncEngine, admin_engine: AsyncEngine) -> dict[str, Any]:
    """Committed bind so concurrent ``activate`` calls contend the armed head."""
    from app.release.emergency_control_service import EmergencyControlService

    world = await seed_emergency_project(admin_engine)
    async with AsyncSession(rls_engine) as session:
        await bind_tenant(session, world["tenant"])
        bound = await EmergencyControlService(session, world["ctx"]).bind(
            project_id=world["project"], idempotency_key="s83-armed"
        )
        world["binding_id"] = bound.binding_id
        await session.commit()
    return world


def _passed_report(project_id: Any) -> ProductionAutonomyReport:
    return ProductionAutonomyReport(
        project_id=str(project_id),
        gates=[
            GateResult(number, f"gate_{number}", "passed", "test_passed", {})
            for number in range(1, 14)
        ],
    )


async def seed_gld_evaluations(admin_engine: AsyncEngine, *, count: int) -> dict[str, Any]:
    """Commit ``count`` gate-eligible evaluations for concurrent finalize."""
    from app.repositories.go_live_decisions import GoLiveDecisionRepository
    from tests.test_control_loop import _seed_decision_ready

    session = AsyncSession(admin_engine, expire_on_commit=False)
    await session.begin()
    try:
        seeded = await _seed_decision_ready(session)
        payload = {
            "tenant": seeded["tenant"],
            "project": seeded["project"],
            "ctx": seeded["requester_context"],
            "project_run": seeded["project_run"],
            "binding_ids": seeded["binding_ids"],
            "expiry": seeded["expiry"],
        }
        await session.commit()
    finally:
        await session.close()

    conn = await admin_engine.connect()
    await conn.execution_options(isolation_level="SERIALIZABLE")
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    evaluations: list[Any] = []
    try:
        await bind_tenant(session, payload["tenant"])
        repo = GoLiveDecisionRepository(session, payload["ctx"])
        report = _passed_report(payload["project"])
        for index in range(count):
            run = payload["project_run"]
            if index:
                run = (
                    await session.execute(
                        text(
                            "INSERT INTO project_runs (tenant_id,project_id,status) "
                            "VALUES (:tenant,:project,'created') RETURNING id"
                        ),
                        {"tenant": payload["tenant"], "project": payload["project"]},
                    )
                ).scalar_one()
            cycle = await repo.start_cycle(
                project_id=payload["project"],
                project_run_id=run,
                idempotency_key=f"s83-gld-{index}-{uuid.uuid4().hex[:10]}",
            )
            evaluation = await repo.record_evaluation(
                control_loop_run_id=cycle.id,
                report=report,
                preapproval_gate_eligible=True,
                policy_decision="needs_approval",
                emergency_latch_active=False,
                binding_ids=payload["binding_ids"],
                preapproval_expires_at=payload["expiry"],
            )
            evaluations.append(evaluation.id)
        await trans.commit()
    finally:
        await session.close()
        await conn.close()
    return {
        "tenant": payload["tenant"],
        "project": payload["project"],
        "ctx": payload["ctx"],
        "evaluations": evaluations,
    }


async def commit_one_finalize(
    rls_engine: AsyncEngine, world: dict[str, Any], evaluation_id: Any
) -> Any:
    """Commit one SERIALIZABLE finalize so a later race contends a real prior."""
    from app.repositories.go_live_decisions import GoLiveDecisionRepository

    conn = await rls_engine.connect()
    await conn.execution_options(isolation_level="SERIALIZABLE")
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        await bind_tenant(session, world["tenant"])
        prior = await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(
            evaluation_id
        )
        prior_id = prior.id
        await trans.commit()
        return prior_id
    finally:
        await session.close()
        await conn.close()
