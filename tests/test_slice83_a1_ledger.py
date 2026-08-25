"""Slice 83 commit-8: A1 barriers for audit, checkpointer, and admin-policy spend."""

from __future__ import annotations

from typing import cast
from unittest.mock import patch

import pytest
from langchain_core.runnables import RunnableConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.policy_sql import WRITER_BODY, writer_body, writer_create_sql
from app.audit import record, verify_chain
from app.repositories.admin import AdminPolicyChangeRepository
from app.runtime.checkpointer import UAIDCheckpointer
from app.tenancy import TenantContext
from tests.admin_lock_support import seed_committed_first_write
from tests.admin_support import pg_state
from tests.slice83_a1_ledger_support import (
    keep_one_policy_change,
    racy_aput_writes,
    reset_audit_chain,
    seed_checkpoint_world,
    without_advisory_lock,
    without_uniques,
)
from tests.slice83_support import (
    READ_COMMITTED,
    assert_integrity_error_on,
    assert_no_integrity_error,
    run_two_writers,
    seed_org_tenant_project,
)

pytestmark = pytest.mark.db


async def test_a1_audit_append_green(rls_engine, admin_engine):
    """Leaves 1–2 GREEN: concurrent appends chain; ``audit_verify()`` holds."""
    await reset_audit_chain(admin_engine)
    world = await seed_org_tenant_project(admin_engine)
    marker = f"s83-audit-{world['sfx']}"

    async def writer(session: AsyncSession):
        return await record(session, action=marker, actor="s83-a1", target="audit")

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql="SELECT count(*) FROM audit_logs WHERE action=:a",
        count_params={"a": marker},
    )
    assert result.pending_before_commit is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 2
    assert result.w1_error is None and result.w2_error is None
    async with AsyncSession(admin_engine) as session:
        verified = await verify_chain(session)
    assert verified["ok"] is True
    print("A1-AUDIT-GREEN", result.w1_value["id"], result.w2_value["id"], verified["ok"])


async def test_a1_audit_append_mutation(rls_engine, admin_engine):
    """Leaves 1–2 mutation: no lock 421 → chain invalid under contention."""
    await reset_audit_chain(admin_engine)
    world = await seed_org_tenant_project(admin_engine)
    marker = f"s83-audit-mut-{world['sfx']}"

    async def writer(session: AsyncSession):
        return await record(session, action=marker, actor="s83-a1", target="audit")

    async with without_advisory_lock(admin_engine):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer,
            count_sql="SELECT count(*) FROM audit_logs WHERE action=:a",
            count_params={"a": marker},
        )
        async with AsyncSession(admin_engine) as session:
            verified = await verify_chain(session)
    await reset_audit_chain(admin_engine)
    assert result.w1_error is None
    assert verified["ok"] is False
    print("A1-AUDIT-MUT", result.unique_row_count, verified["ok"], verified["first_bad_seq"])


async def test_a1_checkpoint_writes_green(rls_engine, admin_engine):
    """Leaf 21 GREEN: both commit; one row; surviving tuple is wholly one caller."""
    world = await seed_checkpoint_world(rls_engine, admin_engine)
    cfg = cast(
        RunnableConfig,
        {
            "configurable": {
                "thread_id": str(world["run"]),
                "checkpoint_ns": "",
                "checkpoint_id": "cp-1",
            }
        },
    )

    async def writer_a(session: AsyncSession):
        cp = UAIDCheckpointer(
            session, world["ctx"], project_id=world["project"], run_id=world["run"]
        )
        await cp.aput_writes(cfg, [("ch", "alpha")], task_id="task-1", task_path="path-a")
        return ("alpha", "path-a")

    async def writer_b(session: AsyncSession):
        cp = UAIDCheckpointer(
            session, world["ctx"], project_id=world["project"], run_id=world["run"]
        )
        await cp.aput_writes(cfg, [("ch", "beta")], task_id="task-1", task_path="path-b")
        return ("beta", "path-b")

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer_a,
        writer_w2=writer_b,
        count_sql=(
            "SELECT count(*) FROM run_checkpoint_writes WHERE tenant_id=:t "
            "AND thread_id=:th AND checkpoint_id='cp-1' AND task_id='task-1'"
        ),
        count_params={"t": world["tenant"], "th": str(world["run"])},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None and result.w2_error is None
    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT channel, task_path FROM run_checkpoint_writes "
                    "WHERE tenant_id=:t AND thread_id=:th AND checkpoint_id='cp-1' "
                    "AND task_id='task-1'"
                ),
                {"t": world["tenant"], "th": str(world["run"])},
            )
        ).one()
    surviving = (row.channel, row.task_path)
    assert surviving in {("ch", "path-a"), ("ch", "path-b")}
    print("A1-CKPT-GREEN", surviving)


async def test_a1_checkpoint_writes_mutation(rls_engine, admin_engine):
    """Leaf 21 mutation: bare insert → raw 23505 on ``uq_run_checkpoint_writes_id``."""
    world = await seed_checkpoint_world(rls_engine, admin_engine)
    cfg = cast(
        RunnableConfig,
        {
            "configurable": {
                "thread_id": str(world["run"]),
                "checkpoint_ns": "",
                "checkpoint_id": "cp-1",
            }
        },
    )

    async def writer_a(session: AsyncSession):
        cp = UAIDCheckpointer(
            session, world["ctx"], project_id=world["project"], run_id=world["run"]
        )
        await cp.aput_writes(cfg, [("ch", "alpha")], task_id="task-1", task_path="path-a")

    async def writer_b(session: AsyncSession):
        cp = UAIDCheckpointer(
            session, world["ctx"], project_id=world["project"], run_id=world["run"]
        )
        await cp.aput_writes(cfg, [("ch", "beta")], task_id="task-1", task_path="path-b")

    with patch.object(UAIDCheckpointer, "aput_writes", racy_aput_writes):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer_a,
            writer_w2=writer_b,
            count_sql=(
                "SELECT count(*) FROM run_checkpoint_writes WHERE tenant_id=:t "
                "AND thread_id=:th AND checkpoint_id='cp-1' AND task_id='task-1'"
            ),
            count_params={"t": world["tenant"], "th": str(world["run"])},
        )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_run_checkpoint_writes_id")
    print("A1-CKPT-MUT", result.unique_row_count)


async def test_a1_admin_policy_change_green(rls_engine, admin_engine):
    """Leaf 20 GREEN: same ``admin_action_id`` spent once; loser is named, not silent."""
    world = await seed_committed_first_write(admin_engine, prefix="S83A1Adm")
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await AdminPolicyChangeRepository(session, ctx).write_autonomy_policy(
            admin_action_id=world["action_w1"],
            project_id=world["project"],
            autonomy_level=3,
            overrides={},
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql="SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a",
        count_params={"a": world["action_w1"]},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.w2_error is not None
    assert isinstance(result.w2_error, Exception)
    state = pg_state(result.w2_error)
    message = str(result.w2_error)
    assert state in {"23505", "P0001"} or "admin_action_already_spent" in message
    print("A1-APC-GREEN", result.unique_row_count, state, "already_spent" in message)


async def test_a1_admin_policy_change_mutation(rls_engine, admin_engine):
    """Leaf 20 mutation: unique dropped → two spends of one action (limitation, not a fix)."""
    world = await seed_committed_first_write(admin_engine, prefix="S83A1AdmM")
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await AdminPolicyChangeRepository(session, ctx).write_autonomy_policy(
            admin_action_id=world["action_w1"],
            project_id=world["project"],
            autonomy_level=3,
            overrides={},
        )

    async with without_uniques(admin_engine, ("uq_admin_policy_changes_action",)):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer,
            count_sql="SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a",
            count_params={"a": world["action_w1"]},
        )
        assert result.unique_row_count == 2
        await keep_one_policy_change(admin_engine, world["action_w1"])
    print("A1-APC-MUT", 2)


async def test_a1_admin_writer_body_is_migration_frozen(admin_engine):
    """Leaf 20 limitation: installed body still matches the migration-frozen writer."""
    async with admin_engine.connect() as conn:
        body = (
            await conn.execute(
                text("SELECT prosrc FROM pg_proc WHERE proname='admin_write_autonomy_policy'")
            )
        ).scalar_one()
    assert body.strip() == WRITER_BODY.strip()
    assert body.strip() == writer_body().strip()
    assert "CREATE OR REPLACE FUNCTION" in writer_create_sql()
    print("A1-APC-FROZEN", True)
