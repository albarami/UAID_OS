"""Public Slice-59 stabilization-window wrappers.

Owns ``tenant_scope``. Callers cannot pass a session or ``as_of``.
Nothing here closes §25.4, writes git, brokers, or deploys.
"""

from __future__ import annotations

import asyncio
import random
import uuid

from sqlalchemy.exc import DBAPIError

from app.ops.stabilization import (
    HISTORY_LIMIT_DEFAULT,
    ClosureAttemptRecord,
    StabilizationIdempotencyRace,
    StabilizationSnapshot,
    assessor_identity,
    request_digest,
    validate_actor_label,
    validate_history_limit,
    validate_idempotency_key,
)
from app.repositories.ops_stabilization import OpsStabilizationRepository, assert_digest_match
from app.tenancy import TenantContext, tenant_scope

MAX_IDEMPOTENCY_RACE_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 0.005
RETRY_BACKOFF_JITTER_SECONDS = 0.003
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})
_ASSESS_ISOLATION = "REPEATABLE READ"
_READ_ISOLATION = "READ COMMITTED"


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


async def _retry(operation):
    last_race: BaseException | None = None
    for attempt in range(MAX_IDEMPOTENCY_RACE_RETRIES):
        try:
            return await operation()
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
    raise StabilizationIdempotencyRace(
        "idempotency winner stayed invisible after bounded REPEATABLE READ retries"
    ) from last_race


async def _assess_once(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    idempotency_key: str,
    extends_window_id: uuid.UUID | None,
    digest: str,
) -> StabilizationSnapshot:
    async with tenant_scope(context, isolation_level=_ASSESS_ISOLATION) as session:
        repo = OpsStabilizationRepository(session, context)
        recorded = await repo.assess(
            project_id,
            actor=actor,
            idempotency_key=idempotency_key,
            extends_window_id=extends_window_id,
        )
        if recorded is not None:
            return recorded
        winner = await repo.get_by_idempotency(project_id, idempotency_key)
        if winner is None:
            raise _IdempotencyWinnerNotVisible()
        assert_digest_match(winner, digest)
        return await repo.snapshot_of(winner)


async def assess_stabilization(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    idempotency_key: str,
    extends_window_id: uuid.UUID | None = None,
) -> StabilizationSnapshot:
    """Record one stabilization-window assessment. Does not close the window."""
    actor_label = validate_actor_label(actor)
    key = validate_idempotency_key(idempotency_key)
    identity = assessor_identity(context.actor, actor_label)
    digest = request_digest(
        project_id=project_id,
        extends_window_id=extends_window_id,
        assessor_subject=identity.subject,
        assessor_actor_type=identity.actor_type,
        assessor_provenance=identity.provenance,
    )
    return await _retry(
        lambda: _assess_once(
            context,
            project_id,
            actor=actor_label,
            idempotency_key=key,
            extends_window_id=extends_window_id,
            digest=digest,
        )
    )


async def attempt_closure(
    context: TenantContext, project_id: uuid.UUID, *, actor: str
) -> ClosureAttemptRecord:
    """Persist a closure refusal under READ COMMITTED with a project row lock."""
    actor_label = validate_actor_label(actor)
    async with tenant_scope(context, isolation_level=_READ_ISOLATION) as session:
        return await OpsStabilizationRepository(session, context).attempt_closure(
            project_id, actor=actor_label
        )


async def latest_stabilization(
    context: TenantContext, project_id: uuid.UUID
) -> StabilizationSnapshot | None:
    """Return the latest assessment for the project, or ``None``."""
    async with tenant_scope(context, isolation_level=_READ_ISOLATION) as session:
        return await OpsStabilizationRepository(session, context).latest(project_id)


async def history_stabilization(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    limit: int = HISTORY_LIMIT_DEFAULT,
) -> list[StabilizationSnapshot]:
    """Return newest-first assessment history for the project."""
    bounded = validate_history_limit(limit)
    async with tenant_scope(context, isolation_level=_READ_ISOLATION) as session:
        return await OpsStabilizationRepository(session, context).history(project_id, limit=bounded)
