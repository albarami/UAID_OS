"""Slice 83 A3 GREEN contract: two minted parents, two distinct child rows."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.slice83_support import (
    READ_COMMITTED,
    TwoWriterResult,
    Writer,
    reported_constraint,
    run_two_writers,
    two_admin_writers,
    unique_row_count,
)

ParentOf = Callable[[Any], Any]

FORECAST_CHILD_CONSTRAINTS: dict[str, tuple[str, ...]] = {
    "cost_forecast_dimension_results": (
        "uq_cfdr_run_dimension",
        "uq_cfdr_run_ordinal",
    ),
    "cost_forecast_input_lines": (
        "uq_cfil_run_kind_component",
        "uq_cfil_run_model_route",
        "uq_cfil_run_ordinal",
    ),
    "cost_forecast_ledger_event_refs": (
        "uq_cfler_run_event",
        "uq_cfler_run_ordinal",
    ),
}


def assert_a3_green(
    result: TwoWriterResult, *, parent_of: ParentOf, require_count: bool = True
) -> tuple[Any, Any]:
    """A3 GREEN: both commits succeed and minted parent identifiers differ."""
    assert result.w1_error is None
    assert result.w2_error is None
    first = parent_of(result.w1_value)
    second = parent_of(result.w2_value)
    assert first is not None and second is not None and first != second
    if require_count:
        assert result.unique_row_count >= 2
    return first, second


async def assert_a3_scoped_parents(
    admin_engine: AsyncEngine,
    *,
    table: str,
    parent_column: str,
    first: Any,
    second: Any,
) -> None:
    """Exactly two distinct race-created parents have child rows."""
    n = await unique_row_count(
        admin_engine,
        f"SELECT count(DISTINCT {parent_column}) FROM {table} WHERE {parent_column} IN (:a, :b)",
        {"a": first, "b": second},
    )
    assert n == 2


async def assert_a3_mutation(
    race: Callable[[], Coroutine[Any, Any, TwoWriterResult]],
    *,
    parent_of: ParentOf,
    constraint: str | tuple[str, ...],
) -> None:
    """Collapsing onto one parent must fire the leaf unique, not a neighbouring key."""
    allowed = (constraint,) if isinstance(constraint, str) else constraint
    try:
        result = await race()
    except IntegrityError as exc:
        assert reported_constraint(exc) in allowed, reported_constraint(exc)
        return
    observed = [
        reported_constraint(exc)
        for exc in (result.w1_error, result.w2_error)
        if isinstance(exc, Exception)
    ]
    observed = [name for name in observed if name]
    assert any(name in allowed for name in observed), observed


def row_id(value: Any) -> Any:
    """Parent identifier from an ORM row or snapshot with ``id``."""
    return None if value is None else value.id


def minted_id(value: Any) -> Any:
    """Parent identifier when the writer returns the minted UUID itself."""
    return value


def report_run_id(value: Any) -> Any:
    """Parent identifier from ``PublishReport.run_id``."""
    return None if value is None else value.run_id


@contextmanager
def force_row_id(model: type, value: uuid.UUID):
    """Force the next ORM inserts of ``model`` to use one parent primary key."""

    def _set(_mapper, _connection, target) -> None:
        target.id = value

    event.listen(model, "before_insert", _set)
    try:
        yield
    finally:
        event.remove(model, "before_insert", _set)


@asynccontextmanager
async def force_sql_pk_default(
    admin_engine: AsyncEngine, table: str, value: uuid.UUID
) -> AsyncIterator[None]:
    """Force raw ``INSERT`` parents that use a column default onto one UUID."""
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT '{value}'::uuid"))
    try:
        yield
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT gen_random_uuid()")
            )


async def race_runtime(
    *,
    rls_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    tenant_id: uuid.UUID,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
    writer_w2: Writer | None = None,
    isolation_level: str = READ_COMMITTED,
    retryable_loser_sqlstates: tuple[str, ...] = (),
) -> TwoWriterResult:
    """Two runtime sessions; default isolation is READ COMMITTED."""
    return await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=isolation_level,
        tenant_id=tenant_id,
        writer=writer,
        writer_w2=writer_w2,
        count_sql=count_sql,
        count_params=count_params,
        retryable_loser_sqlstates=retryable_loser_sqlstates,
    )


async def race_admin(
    *,
    admin_engine: AsyncEngine,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
    writer_w2: Writer | None = None,
) -> TwoWriterResult:
    """Two admin sessions at READ COMMITTED (global catalog / publisher)."""
    return await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        writer=writer,
        writer_w2=writer_w2,
        count_sql=count_sql,
        count_params=count_params,
    )
