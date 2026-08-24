"""Slice 83 two-writer harness (Tier A's instrument) and seed helpers."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.exc import IntegrityError

from tests.admin_lock_support import write_wait_snapshot
from tests.admin_support import pg_constraint, pg_state

Writer = Callable[[AsyncSession], Awaitable[Any]]
Seeder = Callable[[AsyncSession], Awaitable[dict[str, Any]]]

_POLL_S = 0.05
_WAIT_S = 5.0

READ_COMMITTED = "READ COMMITTED"
SERIALIZABLE = "SERIALIZABLE"


@dataclass(frozen=True)
class TwoWriterResult:
    """Outcomes of one two-session first-write race."""

    w1_value: Any
    w1_error: BaseException | None
    w2_value: Any
    w2_error: BaseException | None
    blocked_at_write: bool
    pending_before_commit: bool
    unique_row_count: int
    wait: dict[str, Any]


async def bind_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Set transaction-local ``app.current_tenant``. Never uses session-level false."""
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


async def backend_pid(session: AsyncSession) -> int:
    return int((await session.execute(text("SELECT pg_backend_pid()"))).scalar_one())


async def unique_row_count(admin_engine: AsyncEngine, sql: str, params: dict[str, Any]) -> int:
    """Count surviving rows for the contended key via the admin observer."""
    async with admin_engine.connect() as conn:
        return int((await conn.execute(text(sql), params)).scalar_one())


def assert_integrity_error_on(exc: BaseException, constraint: str | None = None) -> None:
    """Assert a unique-violation IntegrityError, optionally on a named constraint."""
    assert isinstance(exc, IntegrityError), type(exc).__name__
    assert pg_state(exc) == "23505", pg_state(exc)
    if constraint is not None:
        named = pg_constraint(exc) or _constraint_from_message(exc)
        assert named == constraint, named


def _constraint_from_message(exc: BaseException) -> str | None:
    text_form = str(exc)
    marker = "constraint"
    if "violates unique constraint" in text_form:
        start = text_form.find('"')
        end = text_form.find('"', start + 1)
        if start >= 0 and end > start:
            return text_form[start + 1 : end]
    if marker in text_form.lower():
        return text_form
    return None


def reported_constraint(exc: BaseException) -> str | None:
    """Named unique constraint from a 23505, or None if unparseable."""
    return pg_constraint(exc) or _constraint_from_message(exc)


async def seed_org_tenant_project(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Commit one org/tenant/project visible to both later writer sessions."""
    sfx = uuid.uuid4().hex[:10]
    async with admin_engine.begin() as conn:
        org = (
            await conn.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('S83Org', :s) RETURNING id"),
                {"s": f"s83-org-{sfx}"},
            )
        ).scalar_one()
        tenant = (
            await conn.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o, 's83', :s) RETURNING id"
                ),
                {"o": org, "s": f"s83-t-{sfx}"},
            )
        ).scalar_one()
        project = (
            await conn.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P', :s) RETURNING id"
                ),
                {"t": tenant, "s": f"s83-p-{sfx}"},
            )
        ).scalar_one()
    return {"org": org, "tenant": tenant, "project": project, "sfx": sfx}


async def _session_on(engine: AsyncEngine, isolation_level: str) -> tuple[Any, Any, AsyncSession]:
    conn = await engine.connect()
    await conn.execution_options(isolation_level=isolation_level)
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    return conn, trans, session


async def run_two_writers(
    *,
    engine: AsyncEngine,
    admin_engine: AsyncEngine,
    isolation_level: str,
    tenant_id: uuid.UUID | None,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
    retryable_loser_sqlstates: tuple[str, ...] = (),
) -> TwoWriterResult:
    """Two connections, absent-read barrier, blocked-at-write, ordered commit.

    W1 runs the writer to completion inside an open transaction (pre-read absent,
    insert uncommitted). W2 then runs the same writer as a task so its insert
    waits on W1. After W1 commits, W2 is awaited. An aborted W2 is rolled back.
    """
    w1_conn, trans1, s1 = await _session_on(engine, isolation_level)
    w2_conn, trans2, s2 = await _session_on(engine, isolation_level)
    w1_value: Any = None
    w1_error: BaseException | None = None
    w2_value: Any = None
    w2_error: BaseException | None = None
    wait: dict[str, Any] = {"blocked_at_write": False}
    pending_before_commit = False
    try:
        if tenant_id is not None:
            await bind_tenant(s1, tenant_id)
        w1_pid = await backend_pid(s1)
        try:
            w1_value = await writer(s1)
        except BaseException as exc:
            w1_error = exc
            raise

        if tenant_id is not None:
            await bind_tenant(s2, tenant_id)
        w2_pid = await backend_pid(s2)
        w2_task = asyncio.create_task(writer(s2))
        async with admin_engine.connect() as observer:
            deadline = asyncio.get_running_loop().time() + _WAIT_S
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(_POLL_S)
                wait = await write_wait_snapshot(observer, waiter_pid=w2_pid, holder_pid=w1_pid)
                if wait["blocked_at_write"] or w2_task.done():
                    break
            pending_before_commit = not w2_task.done()
        await trans1.commit()
        try:
            w2_value = await asyncio.wait_for(w2_task, timeout=_WAIT_S)
        except BaseException as exc:
            w2_error = exc
            if not w2_task.done():
                w2_task.cancel()
            try:
                await trans2.rollback()
            except BaseException:
                pass
        else:
            state = pg_state(w2_error) if w2_error else None
            if state in retryable_loser_sqlstates:
                await trans2.rollback()
            else:
                await trans2.commit()
    finally:
        await s1.close()
        await s2.close()
        await w1_conn.close()
        await w2_conn.close()

    count = await unique_row_count(admin_engine, count_sql, count_params)
    return TwoWriterResult(
        w1_value=w1_value,
        w1_error=w1_error,
        w2_value=w2_value,
        w2_error=w2_error,
        blocked_at_write=bool(wait.get("blocked_at_write")),
        pending_before_commit=pending_before_commit,
        unique_row_count=count,
        wait=wait,
    )


async def two_admin_writers(
    *,
    admin_engine: AsyncEngine,
    isolation_level: str,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
) -> TwoWriterResult:
    """Same harness on the admin engine (global tables; no tenant GUC)."""
    return await run_two_writers(
        engine=admin_engine,
        admin_engine=admin_engine,
        isolation_level=isolation_level,
        tenant_id=None,
        writer=writer,
        count_sql=count_sql,
        count_params=count_params,
    )


async def two_committed_transactions(
    *,
    engine: AsyncEngine,
    tenant_id: uuid.UUID,
    first: Writer,
    second: Writer,
) -> tuple[Any, Any, AsyncSession]:
    """One expire_on_commit=False session, two committed transactions, GUC rebound.

    Returns ``(first_result, second_result, session)``. Caller must close the session.
    """
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    await bind_tenant(session, tenant_id)
    first_result = await first(session)
    await session.commit()
    await session.begin()
    await bind_tenant(session, tenant_id)
    second_result = await second(session)
    await session.commit()
    return first_result, second_result, session
