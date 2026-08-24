"""Slice 63 two-writer first-policy-write probe (§5.2.a.2 / §5.0 rule 9)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.admin.policy_sql import WRITER_BODY, writer_body, writer_create_sql
from tests.admin_lock_support import (
    action as _action,
    as_app as _as_app,
    grant as _grant,
    guc as _guc,
    restore_writer as _restore_writer,
    seed_committed_first_write,
    write_wait_snapshot,
)
from tests.admin_support import call_writer, pg_state, seed_admin_world

_POLL_S = 0.05
_WAIT_S = 5.0
_WRITER_SQL = "SELECT * FROM public.admin_write_autonomy_policy(:a, :p, :l, CAST(:o AS jsonb))"


async def _installed_body(admin_engine) -> str:
    async with admin_engine.connect() as conn:
        return (
            await conn.execute(
                text("SELECT prosrc FROM pg_proc WHERE proname='admin_write_autonomy_policy'")
            )
        ).scalar_one()


async def _install_writer(admin_engine, **kwargs: bool) -> None:
    async with admin_engine.begin() as conn:
        await conn.execute(text(writer_create_sql(**kwargs)))
        body = (
            await conn.execute(
                text("SELECT prosrc FROM pg_proc WHERE proname='admin_write_autonomy_policy'")
            )
        ).scalar_one()
    assert body.strip() == writer_body(**kwargs).strip()


async def _run_two_writers(rls_engine, admin_engine, world: dict[str, Any]) -> dict[str, Any]:
    tenant = world["tenant"]
    project = world["project"]
    async with (
        rls_engine.connect() as w1,
        rls_engine.connect() as w2,
        admin_engine.connect() as observer,
    ):
        trans1 = await w1.begin()
        await w1.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        w1_pid = (await w1.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        w1_row = (
            await w1.execute(
                text(_WRITER_SQL),
                {"a": world["action_w1"], "p": project, "l": 3, "o": "{}"},
            )
        ).one()

        trans2 = await w2.begin()
        await w2.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(tenant)},
        )
        w2_pid = (await w2.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        w2_task = asyncio.create_task(
            w2.execute(
                text(_WRITER_SQL),
                {"a": world["action_w2"], "p": project, "l": 2, "o": "{}"},
            )
        )
        wait: dict[str, Any] | None = None
        deadline = asyncio.get_running_loop().time() + _WAIT_S
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(_POLL_S)
            wait = await write_wait_snapshot(
                observer, waiter_pid=int(w2_pid), holder_pid=int(w1_pid)
            )
            if wait["blocked_at_write"]:
                break
            if w2_task.done():
                break
        pending_before_commit = not w2_task.done()
        assert wait is not None
        try:
            await trans1.commit()
            w2_result = await asyncio.wait_for(w2_task, timeout=_WAIT_S)
            w2_row = w2_result.one()
            await trans2.commit()
        except BaseException:
            if not w2_task.done():
                w2_task.cancel()
            raise
    async with admin_engine.connect() as conn:
        ledgers = (
            await conn.execute(
                text(
                    "SELECT admin_action_id, previous_autonomy_level, new_autonomy_level, "
                    "autonomy_policy_id FROM admin_policy_changes "
                    "WHERE tenant_id=:t AND project_id=:p"
                ),
                {"t": tenant, "p": project},
            )
        ).all()
        stored = (
            await conn.execute(
                text(
                    "SELECT id, autonomy_level FROM autonomy_policies "
                    "WHERE tenant_id=:t AND project_id=:p"
                ),
                {"t": tenant, "p": project},
            )
        ).all()
    return {
        "w1_row": w1_row,
        "w2_row": w2_row,
        "wait": wait,
        "pending_before_commit": pending_before_commit,
        "ledgers": ledgers,
        "stored": stored,
    }


def _by_action(ledgers, action_id):
    matches = [row for row in ledgers if row[0] == action_id]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.db
async def test_p_writer_concurrent_first_write(rls_engine, admin_engine):
    """Both spends succeed; one NULL previous; waiter cites level 3; stored level 2."""
    assert (await _installed_body(admin_engine)).strip() == WRITER_BODY.strip()
    world = await seed_committed_first_write(admin_engine, prefix="RaceGreen")
    out = await _run_two_writers(rls_engine, admin_engine, world)
    assert out["pending_before_commit"] is True
    assert out["wait"]["blocked_at_write"] is True, out["wait"]
    assert out["w1_row"][0] is not None and out["w1_row"][1] is not None
    assert out["w2_row"][0] is not None and out["w2_row"][1] is not None
    assert out["w1_row"][0] == out["w2_row"][0]
    assert len(out["stored"]) == 1
    assert out["stored"][0][0] == out["w1_row"][0]
    assert out["stored"][0][1] == 2
    assert len(out["ledgers"]) == 2
    first = _by_action(out["ledgers"], world["action_w1"])
    second = _by_action(out["ledgers"], world["action_w2"])
    assert first[1] is None and first[2] == 3
    assert second[1] == 3 and second[2] == 2
    null_prev = [row for row in out["ledgers"] if row[1] is None]
    assert len(null_prev) == 1


@pytest.mark.db
async def test_p_writer_concurrent_first_write_mutation(rls_engine, admin_engine):
    """Reinstalling the v4 body must reproduce [(NULL,3),(NULL,2)]; restore stays green."""
    await _install_writer(admin_engine, racy_first_write=True)
    try:
        world = await seed_committed_first_write(admin_engine, prefix="RaceRacy")
        out = await _run_two_writers(rls_engine, admin_engine, world)
        assert out["pending_before_commit"] is True
        assert out["wait"]["blocked_at_write"] is True, out["wait"]
        assert out["stored"][0][1] == 2
        first = _by_action(out["ledgers"], world["action_w1"])
        second = _by_action(out["ledgers"], world["action_w2"])
        assert first[1] is None and first[2] == 3
        assert second[1] is None and second[2] == 2
        assert [row[1] for row in out["ledgers"]].count(None) == 2
    finally:
        await _install_writer(admin_engine)
    assert (await _installed_body(admin_engine)).strip() == WRITER_BODY.strip()
    restored = await seed_committed_first_write(admin_engine, prefix="RaceRestored")
    green = await _run_two_writers(rls_engine, admin_engine, restored)
    assert green["wait"]["blocked_at_write"] is True, green["wait"]
    first = _by_action(green["ledgers"], restored["action_w1"])
    second = _by_action(green["ledgers"], restored["action_w2"])
    assert first[1] is None and first[2] == 3
    assert second[1] == 3 and second[2] == 2
    assert green["stored"][0][1] == 2


@pytest.mark.db
async def test_p_writer_concurrent_first_write_tighten_no_orphan(db_session):
    """Tighten against an absent row refuses before any INSERT."""
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    act = await _action(db_session, w["t1"], w["p1"], kind="tighten_autonomy_overrides")
    before = (
        await db_session.execute(
            text("SELECT count(*) FROM autonomy_policies WHERE project_id=:p"),
            {"p": w["p1"]},
        )
    ).scalar_one()
    with pytest.raises(DBAPIError, match="no_existing_policy") as ei:
        await _as_app(
            db_session,
            lambda: call_writer(
                db_session,
                action_id=act,
                project_id=w["p1"],
                level=2,
                overrides='{"run_tests":{"allow":false}}',
            ),
        )
    assert pg_state(ei.value) == "P0001"
    after = (
        await db_session.execute(
            text("SELECT count(*) FROM autonomy_policies WHERE project_id=:p"),
            {"p": w["p1"]},
        )
    ).scalar_one()
    changes = (
        await db_session.execute(
            text("SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a"),
            {"a": act},
        )
    ).scalar_one()
    assert before == 0 and after == 0 and changes == 0
    await _restore_writer(db_session)
