"""Slice 83 A3 GREEN contract: two minted parents, two distinct child rows."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.slice83_support import (
    READ_COMMITTED,
    TwoWriterResult,
    Writer,
    run_two_writers,
    two_admin_writers,
)

ParentOf = Callable[[Any], Any]


def assert_a3_green(result: TwoWriterResult, *, parent_of: ParentOf) -> None:
    """A3 GREEN: both commits succeed; minted parent identifiers differ; ≥2 child rows."""
    assert result.w1_error is None
    assert result.w2_error is None
    first = parent_of(result.w1_value)
    second = parent_of(result.w2_value)
    assert first is not None and second is not None and first != second
    assert result.unique_row_count >= 2


async def assert_a3_mutation(
    race: Callable[[], Coroutine[Any, Any, TwoWriterResult]],
    *,
    parent_of: ParentOf,
) -> None:
    """Collapsing onto one minted parent must fail the A3 distinctness assertion."""
    try:
        result = await race()
    except IntegrityError:
        return
    held = True
    try:
        assert_a3_green(result, parent_of=parent_of)
    except AssertionError:
        held = False
    assert held is False, "collapsed-parent race still satisfied A3 GREEN"


def row_id(value: Any) -> Any:
    """Parent identifier from an ORM row or snapshot with ``id``."""
    return None if value is None else value.id


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


async def race_runtime(
    *,
    rls_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    tenant_id: uuid.UUID,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
) -> TwoWriterResult:
    """Two runtime sessions at READ COMMITTED."""
    return await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=tenant_id,
        writer=writer,
        count_sql=count_sql,
        count_params=count_params,
    )


async def race_admin(
    *,
    admin_engine: AsyncEngine,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
) -> TwoWriterResult:
    """Two admin sessions at READ COMMITTED (global catalog / publisher)."""
    return await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        writer=writer,
        count_sql=count_sql,
        count_params=count_params,
    )
