"""Public Slice-58 hotfix-intent wrappers.

Owns READ COMMITTED ``tenant_scope``. Callers cannot pass a session.
Nothing here writes git, opens a GitHub PR, deploys, or rolls back production.
"""

from __future__ import annotations

import asyncio
import random
import uuid

from sqlalchemy.exc import DBAPIError

from app.ops.hotfix import (
    HISTORY_LIMIT_DEFAULT,
    HotfixIdempotencyRace,
    HotfixIntentSnapshot,
    request_digest,
    validate_actor_label,
    validate_history_limit,
    validate_idempotency_key,
)
from app.repositories.ops_hotfix import OpsHotfixRepository, assert_digest_match
from app.tenancy import TenantContext, tenant_scope

MAX_IDEMPOTENCY_RACE_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 0.005
RETRY_BACKOFF_JITTER_SECONDS = 0.003
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})
_ISOLATION = "READ COMMITTED"


class _IdempotencyWinnerNotVisible(Exception):
    """READ COMMITTED snapshot cannot yet see the concurrently committed winner."""


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
    raise HotfixIdempotencyRace(
        "idempotency winner stayed invisible after bounded READ COMMITTED retries"
    ) from last_race


async def _evaluate_once(
    context: TenantContext,
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    *,
    actor: str,
    idempotency_key: str,
    digest: str,
) -> HotfixIntentSnapshot:
    async with tenant_scope(context, isolation_level=_ISOLATION) as session:
        repo = OpsHotfixRepository(session, context)
        recorded = await repo.evaluate(
            project_id, incident_id, actor=actor, idempotency_key=idempotency_key
        )
        if recorded is not None:
            return recorded
        winner = await repo.get_by_idempotency(project_id, incident_id, idempotency_key)
        if winner is None:
            raise _IdempotencyWinnerNotVisible()
        assert_digest_match(winner, digest)
        return await repo.snapshot_of(winner)


async def evaluate_hotfix_intent(
    context: TenantContext,
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    *,
    actor: str,
    idempotency_key: str,
) -> HotfixIntentSnapshot:
    """Record one hotfix-intent evaluation for a non-terminal incident."""
    actor_label = validate_actor_label(actor)
    key = validate_idempotency_key(idempotency_key)
    digest = request_digest(incident_id)
    return await _retry(
        lambda: _evaluate_once(
            context,
            project_id,
            incident_id,
            actor=actor_label,
            idempotency_key=key,
            digest=digest,
        )
    )


async def latest_hotfix_intent(
    context: TenantContext, project_id: uuid.UUID, incident_id: uuid.UUID
) -> HotfixIntentSnapshot | None:
    async with tenant_scope(context, isolation_level=_ISOLATION) as session:
        return await OpsHotfixRepository(session, context).latest(project_id, incident_id)


async def history_hotfix_intent(
    context: TenantContext,
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    *,
    limit: int = HISTORY_LIMIT_DEFAULT,
) -> list[HotfixIntentSnapshot]:
    bounded = validate_history_limit(limit)
    async with tenant_scope(context, isolation_level=_ISOLATION) as session:
        return await OpsHotfixRepository(session, context).history(
            project_id, incident_id, limit=bounded
        )
