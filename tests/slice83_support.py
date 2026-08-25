"""Slice 83 two-writer harness (Tier A's instrument) and seed helpers."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.exc import IntegrityError

from tests.admin_lock_support import write_wait_snapshot
from tests.admin_support import pg_constraint, pg_state
from app.intake.extraction import promotion_ref

Writer = Callable[[AsyncSession], Coroutine[Any, Any, Any]]
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


def assert_integrity_error_on(exc: BaseException | None, constraint: str | None = None) -> None:
    """Assert a unique-violation IntegrityError, optionally on a named constraint."""
    assert exc is not None
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


def reported_constraint(exc: BaseException | None) -> str | None:
    """Named unique constraint from a 23505, or None if unparseable."""
    if not isinstance(exc, Exception):
        return None
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


def assert_no_integrity_error(result: TwoWriterResult) -> None:
    """Neither writer outcome may carry SQLSTATE 23505."""
    for label, exc in (("w1", result.w1_error), ("w2", result.w2_error)):
        state = pg_state(exc) if isinstance(exc, Exception) else None
        assert state != "23505", f"{label} still unique-violated: {exc!r}"
        if exc is not None:
            assert not isinstance(exc, IntegrityError) or state != "23505"


def assert_green_race(result: TwoWriterResult) -> None:
    """Shared GREEN race contract: contended, one survivor, no 23505."""
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1


@contextmanager
def patched_out_conflict_handling(target: Any, name: str, replacement: Any) -> Iterator[None]:
    """Replace exactly one writer method with its pre-fix body."""
    with patch.object(target, name, replacement):
        yield


async def audit_action_count(
    admin_engine: AsyncEngine, *, tenant_id: uuid.UUID, action: str
) -> int:
    """Count audit rows for one tenant and action."""
    return await unique_row_count(
        admin_engine,
        "SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action=:a",
        {"t": tenant_id, "a": action},
    )


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
    writer_w2: Writer | None = None,
    retryable_loser_sqlstates: tuple[str, ...] = (),
) -> TwoWriterResult:
    """Two connections, absent-read barrier, blocked-at-write, ordered commit.

    W1 runs the writer to completion inside an open transaction (pre-read absent,
    insert uncommitted). W2 then runs ``writer_w2`` or the same writer as a task
    so its insert waits on W1. After W1 commits, W2 is awaited. An aborted W2 is
    rolled back.
    """
    second = writer_w2 if writer_w2 is not None else writer
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
        w2_task = asyncio.create_task(second(s2))
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
    writer_w2: Writer | None = None,
) -> TwoWriterResult:
    """Same harness on the admin engine (global tables; no tenant GUC)."""
    return await run_two_writers(
        engine=admin_engine,
        admin_engine=admin_engine,
        isolation_level=isolation_level,
        tenant_id=None,
        writer=writer,
        writer_w2=writer_w2,
        count_sql=count_sql,
        count_params=count_params,
    )


@dataclass
class TwoCommitResult:
    """Sequential two-commit upsert plus an independent confirming read."""

    first: Any
    second: Any
    session: AsyncSession
    confirmed: Any
    confirm_session: AsyncSession


async def two_committed_transactions(
    *,
    engine: AsyncEngine,
    tenant_id: uuid.UUID,
    first: Writer,
    second: Writer,
    confirm: Writer,
    rebind_second: bool = True,
) -> TwoCommitResult:
    """One expire_on_commit=False session, two committed transactions, GUC rebound.

    Binds ``app.current_tenant`` with ``set_config(..., true)`` inside txn 1, txn 2
    (unless ``rebind_second`` is false), and the independent confirming read.
    Caller must close both sessions.
    """
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    await bind_tenant(session, tenant_id)
    first_result = await first(session)
    await session.commit()
    await session.begin()
    if rebind_second:
        await bind_tenant(session, tenant_id)
    second_result = await second(session)
    await session.commit()
    confirm_session = AsyncSession(engine, expire_on_commit=False)
    await confirm_session.begin()
    await bind_tenant(confirm_session, tenant_id)
    confirmed = await confirm(confirm_session)
    await confirm_session.commit()
    return TwoCommitResult(
        first=first_result,
        second=second_result,
        session=session,
        confirmed=confirmed,
        confirm_session=confirm_session,
    )


def forecast_policy_payload() -> dict:
    """Structured file-21 policy body used by the forecast-policy writers."""
    return {
        "cost_and_resource_policy": {
            "max_total_model_cost_usd": 100,
            "max_daily_model_cost_usd": 50,
            "max_cloud_spend_usd": 100,
            "max_ci_minutes_per_day": 100,
            "require_approval_above_forecast_percentage": 90,
            "model_routing": {
                "cheap_first_for_low_risk": True,
                "frontier_for_high_risk": True,
                "use_cached_context_when_possible": True,
            },
            "stop_conditions": [
                "budget_exceeded",
                "repeated_failure_without_new_strategy",
                "tool_loop_detected",
                "model_provider_outage_extended",
            ],
        }
    }


def component_hashes(prompt: str = "a" * 64) -> dict[str, str]:
    """Six §22.2 hashes for register_version probes."""
    return {
        "prompt_hash": f"sha256:{prompt}",
        "tool_policy_hash": "sha256:" + "1" * 64,
        "context_policy_hash": "sha256:" + "2" * 64,
        "eval_suite_hash": "sha256:" + "3" * 64,
        "critical_dependencies_hash": "sha256:" + "4" * 64,
        "output_schema_hash": "sha256:" + "5" * 64,
    }


async def seed_approved_requirement(admin_engine: AsyncEngine, *, extra: int = 0) -> dict[str, Any]:
    """Commit one accepted document plus one or more approved requirement proposals."""
    world = await seed_org_tenant_project(admin_engine)
    content = "The system shall export an evidence pack."
    digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    async with admin_engine.begin() as conn:
        doc = (
            await conn.execute(
                text(
                    "INSERT INTO documents (tenant_id, project_id, filename, content_type, "
                    "source, content, content_hash, size_bytes, status) "
                    "VALUES (:t,:p,'f.txt','text/plain','manual',:c,:h,:sz,'accepted') "
                    "RETURNING id"
                ),
                {
                    "t": world["tenant"],
                    "p": world["project"],
                    "c": content,
                    "h": digest,
                    "sz": len(content.encode()),
                },
            )
        ).scalar_one()
        run_id = (
            await conn.execute(
                text(
                    "INSERT INTO extraction_runs (id, tenant_id, project_id, document_id, "
                    "model, provider, prompt_version, status) "
                    "VALUES (gen_random_uuid(),:t,:p,:d,'m','fake','v','succeeded') "
                    "RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "d": doc},
            )
        ).scalar_one()
        pids: list[Any] = []
        for index in range(1 + extra):
            text_body = content if index == 0 else f"{content} variant {index}."
            pid = (
                await conn.execute(
                    text(
                        "INSERT INTO extraction_proposals (tenant_id, project_id, "
                        "extraction_run_id, proposed_kind, proposed_text, "
                        "proposed_classification, source_document_id, evidence_quote, "
                        "status, extracted_by) "
                        "VALUES (:t,:p,:r,'requirement',:tx,NULL,:d,:ev,'pending','agent-x') "
                        "RETURNING id"
                    ),
                    {
                        "t": world["tenant"],
                        "p": world["project"],
                        "r": run_id,
                        "tx": text_body,
                        "d": doc,
                        "ev": content,
                    },
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "UPDATE extraction_proposals SET status='approved', "
                    "reviewed_by='human-rev', reviewed_at=now() WHERE id=:i"
                ),
                {"i": pid},
            )
            pids.append(pid)
    world["proposal"] = pids[0]
    world["proposals"] = pids
    world["ref"] = promotion_ref("requirement", pids[0])
    world["document"] = doc
    return world
