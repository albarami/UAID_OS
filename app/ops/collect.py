"""Public Slice-56 ops-signal collector.

Owns REPEATABLE READ ``tenant_scope``. Callers cannot pass a session or as_of.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime
from typing import Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ops.assessment import build_assessment
from app.ops.signals import (
    CallerSample,
    CostObservation,
    OpsObservationSnapshot,
    OpsSignalError,
    OpsSignalIdempotencyConflict,
    OpsSignalIdempotencyRace,
    compute_counters,
    input_digest,
    parse_samples,
    request_digest,
    utc_midnight,
    validate_idempotency_key,
)
from app.repositories.ops_signals import OpsSignalRepository, stop_decision_for_snapshot
from app.tenancy import TenantContext, tenant_scope

MAX_IDEMPOTENCY_RACE_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 0.005
RETRY_BACKOFF_JITTER_SECONDS = 0.003
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})


class _IdempotencyWinnerNotVisible(Exception):
    """REPEATABLE READ snapshot cannot yet see the concurrently committed winner."""


def _transaction_sqlstate(exc: BaseException) -> str | None:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(current, attribute, None)
            if isinstance(value, str):
                return value
        for attribute in ("orig", "__cause__", "__context__"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
    return None


def _retry_delay_seconds(attempt: int) -> float:
    exponential = RETRY_BACKOFF_BASE_SECONDS * (2**attempt)
    return exponential + random.uniform(0.0, RETRY_BACKOFF_JITTER_SECONDS)


async def collect_ops_signals(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    samples: Sequence[Mapping[str, object] | CallerSample] | None = None,
    idempotency_key: str,
) -> OpsObservationSnapshot:
    """Assess all eleven §25.1 classes for one project.

    Opens REPEATABLE READ itself. Repository/DB errors abort; they do not become
    ``not_observed``. A REPEATABLE READ winner-not-visible collision retries the
    complete operation in a fresh transaction at most five times.
    """
    parsed = parse_samples(samples)
    key = validate_idempotency_key(idempotency_key)
    last_race: BaseException | None = None
    for attempt in range(MAX_IDEMPOTENCY_RACE_RETRIES):
        try:
            return await _collect_once(
                context, project_id, actor=actor, samples=parsed, idempotency_key=key
            )
        except (_IdempotencyWinnerNotVisible, DBAPIError) as exc:
            if (
                isinstance(exc, DBAPIError)
                and _transaction_sqlstate(exc) not in _RETRYABLE_SQLSTATES
            ):
                raise
            last_race = exc
            if attempt + 1 >= MAX_IDEMPOTENCY_RACE_RETRIES:
                break
            await asyncio.sleep(_retry_delay_seconds(attempt))
    raise OpsSignalIdempotencyRace(
        "idempotency winner stayed invisible after bounded REPEATABLE READ retries"
    ) from last_race


async def _collect_once(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    samples: tuple[CallerSample, ...],
    idempotency_key: str,
) -> OpsObservationSnapshot:
    async with tenant_scope(context, isolation_level="REPEATABLE READ") as session:
        as_of_raw = await session.scalar(select(func.transaction_timestamp()))
        if as_of_raw is None or as_of_raw.tzinfo is None:
            raise OpsSignalError("transaction_timestamp must return a timezone-aware datetime")
        as_of = as_of_raw.astimezone(UTC)
        return await _collect_ops_signals_in_txn(
            session,
            context,
            project_id,
            actor=actor,
            as_of=as_of,
            samples=samples,
            idempotency_key=idempotency_key,
        )


async def _collect_ops_signals_in_txn(
    session: AsyncSession,
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    as_of: datetime,
    samples: tuple[CallerSample, ...],
    idempotency_key: str,
) -> OpsObservationSnapshot:
    repo = OpsSignalRepository(session, context)
    digest = request_digest(project_id, samples)
    existing = await repo.get_by_idempotency(project_id, idempotency_key)
    if existing is not None:
        if existing.request_digest != digest:
            raise OpsSignalIdempotencyConflict(
                "idempotency key reused with a different request digest"
            )
        return await repo.snapshot(existing)

    failed_run_ids = await repo.failed_run_ids_as_of(project_id, as_of)
    total_spent, daily_spent = await repo.cost_spend_as_of(project_id, as_of)
    budget = await repo.budget_ceilings(project_id)
    decision = stop_decision_for_snapshot(
        total_spent=total_spent, daily_spent=daily_spent, budget=budget
    )
    cost = CostObservation(
        total_spent=total_spent,
        daily_spent=daily_spent,
        utc_midnight=utc_midnight(as_of),
        budget=budget,
        decision=decision,
    )
    rows = build_assessment(
        project_id=project_id,
        as_of=as_of,
        failed_run_ids=failed_run_ids,
        cost=cost,
        samples=samples,
    )
    counters = compute_counters(rows)
    snapshot_digest = input_digest(project_id, as_of, rows)
    recorded = await repo.record_run(
        project_id=project_id,
        idempotency_key=idempotency_key,
        request_digest=digest,
        input_digest=snapshot_digest,
        as_of=as_of,
        observed_count=counters.observed_count,
        caller_supplied_count=counters.caller_supplied_count,
        not_observed_count=counters.not_observed_count,
        breached_count=counters.breached_count,
        rows=rows,
        actor=actor,
    )
    if recorded is not None:
        return recorded
    winner = await repo.get_by_idempotency(project_id, idempotency_key)
    if winner is None:
        raise _IdempotencyWinnerNotVisible()
    if winner.request_digest != digest:
        raise OpsSignalIdempotencyConflict("idempotency key reused with a different request digest")
    return await repo.snapshot(winner)
