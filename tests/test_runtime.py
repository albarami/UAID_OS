"""Slice 8a — durable runtime substrate (§23.2) tests.

Docker-free: transition table, serde round-trip, no-un-mediated-IO structural check.
DB-backed (`db`): checkpointer conformance, crash→resume proof, state machine,
RLS + cross-tenant, FK pinning, run_steps immutability, catalog/grants/triggers.
"""

import inspect
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

import app.runtime.engine as engine_mod
from app.repositories.runs import InvalidRunTransition, RunRepository, is_valid_transition
from app.runtime.checkpointer import UAIDCheckpointer
from app.runtime.engine import resume_demo_run, start_demo_run
from app.tenancy import TenantContext, tenant_scope


def _ckpt(cid: str, values: dict) -> dict:
    return {
        "v": 4,
        "id": cid,
        "ts": "2026-01-01T00:00:00+00:00",
        "channel_values": values,
        "channel_versions": {},
        "versions_seen": {},
    }


def _config(run_id, checkpoint_id=None) -> dict:
    cfg = {"thread_id": str(run_id), "checkpoint_ns": ""}
    if checkpoint_id:
        cfg["checkpoint_id"] = checkpoint_id
    return {"configurable": cfg}


# --- Docker-free --------------------------------------------------------------


def test_transition_table():
    assert is_valid_transition("created", "running")
    assert is_valid_transition("running", "completed")
    assert is_valid_transition("running", "failed")
    assert not is_valid_transition("completed", "running")
    assert not is_valid_transition("created", "completed")


def test_serde_roundtrip():
    cp = UAIDCheckpointer(
        None, TenantContext(uuid.uuid4()), project_id=uuid.uuid4(), run_id=uuid.uuid4()
    )
    checkpoint = _ckpt("c1", {"x": 1, "nested": {"y": [1, 2, 3]}})
    type_, blob = cp.serde.dumps_typed(checkpoint)
    restored = cp.serde.loads_typed((type_, blob))
    assert restored["channel_values"] == {"x": 1, "nested": {"y": [1, 2, 3]}}
    assert restored["id"] == "c1"


def test_demo_nodes_have_no_unmediated_io():
    src = inspect.getsource(engine_mod)
    for forbidden in ("import requests", "import httpx", "import urllib", "import socket"):
        assert forbidden not in src


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(c, sql, **p):
    return (await c.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def rt_ctx(admin_engine):
    """Two tenants; tenant1 has P1 (runs r1/r1b/r1c) + P2 (r2); tenant2 has PX (rx).
    All runs seeded with status 'created'."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('RtOrg',:s) RETURNING id",
            s=f"rt-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"rt-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"rt-{proj}-{sfx}",
            )
        for run, tn, proj in (
            ("r1", "t1", "p1"),
            ("r1b", "t1", "p1"),
            ("r1c", "t1", "p1"),
            ("r2", "t1", "p2"),
            ("rx", "t2", "px"),
        ):
            out[run] = await _scalar(
                c,
                "INSERT INTO project_runs (tenant_id, project_id, status) "
                "VALUES (:t,:p,'created') RETURNING id",
                t=out[tn],
                p=out[proj],
            )
    return out


# --- DB-backed: checkpointer conformance --------------------------------------


@pytest.mark.db
async def test_checkpointer_put_get_list_writes_and_delete(rt_ctx, admin_engine):
    t1, p1, r1 = rt_ctx["t1"], rt_ctx["p1"], rt_ctx["r1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        cp = UAIDCheckpointer(session, ctx, project_id=p1, run_id=r1)
        config = _config(r1)
        out_cfg = await cp.aput(config, _ckpt("cp-1", {"x": 1}), {"source": "input", "step": 0}, {})
        cp_id = out_cfg["configurable"]["checkpoint_id"]
        assert cp_id == "cp-1"
        # get
        tup = await cp.aget_tuple(config)
        assert tup is not None
        assert tup.checkpoint["channel_values"] == {"x": 1}
        # list
        listed = [t async for t in cp.alist(config)]
        assert len(listed) == 1
        # writes (with task_path) — persisted at rest; pending_writes is 3-tuple
        await cp.aput_writes(out_cfg, [("ch", "val")], task_id="task-1", task_path="0/node_a")
        tup2 = await cp.aget_tuple(out_cfg)
        assert ("task-1", "ch", "val") in tup2.pending_writes
        # record a run_step (must survive adelete_thread)
        await RunRepository(session, ctx).record_step(
            run_id=r1, project_id=p1, event_type="run_started"
        )
        # task_path persisted at rest (before delete) — verify via the live session
        tp = (
            await session.execute(
                text("SELECT task_path FROM run_checkpoint_writes WHERE tenant_id=:t LIMIT 1"),
                {"t": t1},
            )
        ).scalar_one()
        assert tp == "0/node_a"
        await cp.adelete_thread(str(r1))
    async with admin_engine.connect() as c:
        ck = (
            await c.execute(
                text("SELECT count(*) FROM run_checkpoints WHERE tenant_id=:t"), {"t": t1}
            )
        ).scalar_one()
        wr = (
            await c.execute(
                text("SELECT count(*) FROM run_checkpoint_writes WHERE tenant_id=:t"), {"t": t1}
            )
        ).scalar_one()
        st = (
            await c.execute(text("SELECT count(*) FROM run_steps WHERE tenant_id=:t"), {"t": t1})
        ).scalar_one()
    assert ck == 0 and wr == 0  # checkpoint working state deleted by adelete_thread
    assert st == 1  # run_steps survived adelete_thread


# --- DB-backed: crash → resume proof ------------------------------------------


@pytest.mark.db
async def test_crash_then_resume_does_not_reexecute(rt_ctx, admin_engine):
    t1, p1, r1b = rt_ctx["t1"], rt_ctx["p1"], rt_ctx["r1b"]
    ctx = TenantContext(t1)
    # phase 1: start → runs node_a, checkpoints, interrupts (node_b not run yet)
    async with tenant_scope(ctx) as session:
        state = await start_demo_run(session, ctx, project_id=p1, run_id=r1b)
    assert state["a"] == 1 and state.get("b", 0) == 0
    # phase 2: fresh session/engine → resume from checkpoint → node_b runs → END
    async with tenant_scope(ctx) as session:
        state2 = await resume_demo_run(session, ctx, project_id=p1, run_id=r1b)
    assert state2["a"] == 1 and state2["b"] == 2
    async with admin_engine.connect() as c:
        a_steps = (
            await c.execute(
                text(
                    "SELECT count(*) FROM run_steps WHERE run_id=:r AND node='node_a' AND event_type='step_completed'"
                ),
                {"r": r1b},
            )
        ).scalar_one()
        b_steps = (
            await c.execute(
                text(
                    "SELECT count(*) FROM run_steps WHERE run_id=:r AND node='node_b' AND event_type='step_completed'"
                ),
                {"r": r1b},
            )
        ).scalar_one()
        status = (
            await c.execute(text("SELECT status FROM project_runs WHERE id=:r"), {"r": r1b})
        ).scalar_one()
    assert a_steps == 1  # node_a executed exactly once (not re-run on resume)
    assert b_steps == 1
    assert status == "completed"


# --- DB-backed: state machine -------------------------------------------------


@pytest.mark.db
async def test_state_machine_transitions_and_rejects_invalid(rt_ctx):
    t1, r1c = rt_ctx["t1"], rt_ctx["r1c"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = RunRepository(session, ctx)
        run = await repo.mark_running(run_id=r1c, actor="a")
        assert run.status == "running"
        await repo.mark_completed(run_id=r1c, actor="a")
        with pytest.raises(InvalidRunTransition):
            await repo.transition(
                run_id=r1c, to_status="running", event_type="run_started", actor="a"
            )


# --- DB-backed: RLS, cross-tenant, FK pinning ---------------------------------

_RUNTIME_TABLES = ("run_checkpoints", "run_checkpoint_writes", "run_steps")


def _insert_sql(table: str, *, tenant, project, run) -> tuple[str, dict]:
    """Raw INSERT for a runtime table (thread_id := run::text to satisfy the CHECK)."""
    params = {"t": str(tenant), "p": str(project), "r": str(run), "th": str(run)}
    if table == "run_steps":
        sql = (
            "INSERT INTO run_steps (tenant_id, project_id, run_id, event_type) "
            "VALUES (:t,:p,:r,'run_started')"
        )
    elif table == "run_checkpoints":
        sql = (
            "INSERT INTO run_checkpoints (tenant_id, project_id, run_id, thread_id, "
            "checkpoint_id, checkpoint) VALUES (:t,:p,:r,:th,'c1',decode('00','hex'))"
        )
    else:  # run_checkpoint_writes
        sql = (
            "INSERT INTO run_checkpoint_writes (tenant_id, project_id, run_id, thread_id, "
            "checkpoint_id, task_id, idx, channel, blob) "
            "VALUES (:t,:p,:r,:th,'c1','task1',0,'ch',decode('00','hex'))"
        )
    return sql, params


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant_blocked(rt_ctx, rls_engine):
    t1, t2, p1, r1, px, rx = (
        rt_ctx["t1"],
        rt_ctx["t2"],
        rt_ctx["p1"],
        rt_ctx["r1"],
        rt_ctx["px"],
        rt_ctx["rx"],
    )
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        cp = UAIDCheckpointer(session, ctx, project_id=p1, run_id=r1)
        await cp.aput(_config(r1), _ckpt("cp-1", {"x": 1}), {"source": "input", "step": 0}, {})
        await RunRepository(session, ctx).record_step(
            run_id=r1, project_id=p1, event_type="run_started"
        )
    # no GUC => deny-by-default on all three tables
    async with rls_engine.connect() as conn:
        async with conn.begin():
            for tbl in _RUNTIME_TABLES:
                n = (await conn.execute(text(f"SELECT count(*) FROM {tbl}"))).scalar_one()
                assert n == 0, tbl
    # GUC=t1, insert a tenant2 row (valid tenant2 triple rx/px/t2) into EACH table => WITH CHECK
    for tbl in _RUNTIME_TABLES:
        sql, params = _insert_sql(tbl, tenant=t2, project=px, run=rx)
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(sql), params)
        msg = str(ei.value).lower()
        assert "row-level security" in msg or "policy" in msg, f"{tbl}: {ei.value}"


@pytest.mark.db
async def test_fk_pinning_run_must_match_project_and_tenant(rt_ctx, admin_engine):
    # run r2 belongs to project p2; inserting with project_id=p1 => triple FK violation,
    # for ALL three runtime tables.
    t1, p1, r2 = rt_ctx["t1"], rt_ctx["p1"], rt_ctx["r2"]
    for tbl in _RUNTIME_TABLES:
        sql, params = _insert_sql(tbl, tenant=t1, project=p1, run=r2)
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(text(sql), params)
        msg = str(ei.value).lower()
        assert "foreign key" in msg or "violates" in msg, f"{tbl}: {ei.value}"


@pytest.mark.db
async def test_thread_id_must_equal_run_id_db_check(rt_ctx, admin_engine):
    # A malformed same-tenant row whose thread_id != run_id::text is rejected by the CHECK.
    t1, p1, r1 = rt_ctx["t1"], rt_ctx["p1"], rt_ctx["r1"]
    for tbl in ("run_checkpoints", "run_checkpoint_writes"):
        sql, params = _insert_sql(tbl, tenant=t1, project=p1, run=r1)
        params["th"] = "not-the-run-id"  # break the thread_id = run_id::text invariant
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(text(sql), params)
        assert "thread_matches_run" in str(ei.value).lower() or "check" in str(ei.value).lower()


@pytest.mark.db
async def test_same_tenant_two_runs_isolated(rt_ctx, admin_engine):
    # A checkpointer bound to run A must not read/list/delete run B's state (same tenant).
    t1, p1, rA, rB = rt_ctx["t1"], rt_ctx["p1"], rt_ctx["r1"], rt_ctx["r1b"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        cpA = UAIDCheckpointer(session, ctx, project_id=p1, run_id=rA)
        cpB = UAIDCheckpointer(session, ctx, project_id=p1, run_id=rB)
        await cpA.aput(_config(rA), _ckpt("a1", {"a": 1}), {"source": "input", "step": 0}, {})
        await cpB.aput(_config(rB), _ckpt("b1", {"b": 2}), {"source": "input", "step": 0}, {})
        # cpA sees only run A
        tupA = await cpA.aget_tuple(_config(rA))
        assert tupA is not None and tupA.checkpoint["channel_values"] == {"a": 1}
        listedA = [t async for t in cpA.alist(_config(rA))]
        assert len(listedA) == 1
        # cpA refuses to delete run B's thread
        with pytest.raises(ValueError):
            await cpA.adelete_thread(str(rB))
        # cpA deletes only its own; run B survives
        await cpA.adelete_thread(str(rA))
        assert await cpA.aget_tuple(_config(rA)) is None
        tupB = await cpB.aget_tuple(_config(rB))
        assert tupB is not None and tupB.checkpoint["channel_values"] == {"b": 2}


# --- DB-backed: run_steps immutability + catalog ------------------------------


@pytest.mark.db
async def test_run_steps_immutable(rt_ctx, rls_engine, admin_engine):
    t1, p1, r1 = rt_ctx["t1"], rt_ctx["p1"], rt_ctx["r1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        step = await RunRepository(session, ctx).record_step(
            run_id=r1, project_id=p1, event_type="run_started"
        )
        sid = step.id
    # raw uaid_app UPDATE/DELETE rejected (grant or trigger)
    for stmt in ("UPDATE run_steps SET node='x' WHERE id=:i", "DELETE FROM run_steps WHERE id=:i"):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(stmt), {"i": str(sid)})
        msg = str(ei.value).lower()
        assert "permission denied" in msg or "immutable" in msg
    # admin connection: UPDATE/DELETE/TRUNCATE rejected by trigger
    for stmt in (
        "UPDATE run_steps SET node='x' WHERE id=:i",
        "DELETE FROM run_steps WHERE id=:i",
        "TRUNCATE run_steps",
    ):
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(text(stmt), {"i": str(sid)} if ":i" in stmt else {})
        assert "immutable" in str(ei.value).lower()


@pytest.mark.db
async def test_catalog_grants_and_triggers(admin_engine):
    async with admin_engine.connect() as c:
        grants = {}
        for tbl in ("run_checkpoints", "run_checkpoint_writes", "run_steps"):
            grants[tbl] = {
                r[0]
                for r in (
                    await c.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:t AND grantee='uaid_app'"
                        ),
                        {"t": tbl},
                    )
                ).all()
            }
            rls = (
                await c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": tbl},
                )
            ).one()
            assert rls == (True, True), tbl
        assert grants["run_checkpoints"] == {"SELECT", "INSERT", "DELETE"}
        assert grants["run_checkpoint_writes"] == {"SELECT", "INSERT", "UPDATE", "DELETE"}
        assert grants["run_steps"] == {"SELECT", "INSERT"}
        trigs = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                        "AND tgrelid = 'run_steps'::regclass"
                    )
                )
            ).all()
        }
    assert {"run_steps_no_update_delete", "run_steps_no_truncate"} <= trigs
