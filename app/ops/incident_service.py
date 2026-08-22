"""Public Slice-57 incident wrappers.

Owns REPEATABLE READ ``tenant_scope``. Callers cannot pass a session.
Nothing here writes Jira, diagnoses logs, or executes a hotfix.
"""

from __future__ import annotations

import asyncio
import random
import uuid

from sqlalchemy.exc import DBAPIError

from app.ops.incidents import (
    HISTORY_LIMIT_DEFAULT,
    ActionPrescriptionSet,
    HandoverPayload,
    HandoverRecord,
    IncidentIdempotencyConflict,
    IncidentIdempotencyRace,
    IncidentPayload,
    IncidentSnapshot,
    validate_actor_label,
    validate_idempotency_key,
    validate_new_incident,
    request_digest,
)
from app.repositories.ops_incidents import OpsIncidentRepository
from app.tenancy import TenantContext, tenant_scope

MAX_IDEMPOTENCY_RACE_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 0.005
RETRY_BACKOFF_JITTER_SECONDS = 0.003
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})
_EVAL_ACTOR = "slice57.action_eval"


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
    raise IncidentIdempotencyRace(
        "idempotency winner stayed invisible after bounded REPEATABLE READ retries"
    ) from last_race


async def _open_once(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    payload: IncidentPayload,
    idempotency_key: str,
    digest: str,
) -> IncidentSnapshot:
    async with tenant_scope(context, isolation_level="REPEATABLE READ") as session:
        repo = OpsIncidentRepository(session, context)
        recorded = await repo.open(
            project_id, actor=actor, payload=payload, idempotency_key=idempotency_key
        )
        if recorded is not None:
            return recorded
        winner = await repo.get_by_idempotency(project_id, idempotency_key)
        if winner is None:
            raise _IdempotencyWinnerNotVisible()
        if winner.request_digest != digest:
            raise IncidentIdempotencyConflict(
                "idempotency key reused with a different request digest"
            )
        return await repo.snapshot_of(winner)


async def open_incident(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    payload: IncidentPayload,
    idempotency_key: str,
) -> IncidentSnapshot:
    """Record one incident and its seven-row §25.2 prescription set."""
    actor_label = validate_actor_label(actor)
    parsed = validate_new_incident(payload)
    key = validate_idempotency_key(idempotency_key)
    digest = request_digest(parsed)
    return await _retry(
        lambda: _open_once(
            context,
            project_id,
            actor=actor_label,
            payload=parsed,
            idempotency_key=key,
            digest=digest,
        )
    )


async def transition_incident(
    context: TenantContext,
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    *,
    actor: str,
    to_status: str,
) -> IncidentSnapshot:
    """Apply one legal one-way status transition."""
    actor_label = validate_actor_label(actor)

    async def _once() -> IncidentSnapshot:
        async with tenant_scope(context, isolation_level="REPEATABLE READ") as session:
            return await OpsIncidentRepository(session, context).transition(
                project_id, incident_id, actor=actor_label, to_status=to_status
            )

    return await _retry(_once)


async def record_log_diagnosis_unavailable(
    context: TenantContext,
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
    *,
    actor: str,
) -> IncidentSnapshot:
    """Record that log diagnosis has no source. Does not diagnose or close §25.2."""
    actor_label = validate_actor_label(actor)

    async def _once() -> IncidentSnapshot:
        async with tenant_scope(context, isolation_level="REPEATABLE READ") as session:
            return await OpsIncidentRepository(session, context).record_log_diagnosis_unavailable(
                project_id, incident_id, actor=actor_label
            )

    return await _retry(_once)


async def evaluate_post_launch_actions(
    context: TenantContext,
    project_id: uuid.UUID,
    incident_id: uuid.UUID,
) -> ActionPrescriptionSet:
    """Recompute the seven prescriptions against the current policy."""

    async def _once() -> ActionPrescriptionSet:
        async with tenant_scope(context, isolation_level="REPEATABLE READ") as session:
            return await OpsIncidentRepository(session, context).evaluate_now(
                project_id, incident_id, actor=_EVAL_ACTOR
            )

    return await _retry(_once)


async def record_support_handover(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    actor: str,
    payload: HandoverPayload,
) -> HandoverRecord:
    """Append a support-handover presence record. Not Slice 59 closure."""
    actor_label = validate_actor_label(actor)

    async def _once() -> HandoverRecord:
        async with tenant_scope(context, isolation_level="REPEATABLE READ") as session:
            return await OpsIncidentRepository(session, context).record_handover(
                project_id, actor=actor_label, payload=payload
            )

    return await _retry(_once)


async def latest_incident(context: TenantContext, project_id: uuid.UUID) -> IncidentSnapshot | None:
    async with tenant_scope(context) as session:
        return await OpsIncidentRepository(session, context).latest(project_id)


async def list_open(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    limit: int = HISTORY_LIMIT_DEFAULT,
) -> list[IncidentSnapshot]:
    async with tenant_scope(context) as session:
        return await OpsIncidentRepository(session, context).list_open(project_id, limit=limit)


async def history(
    context: TenantContext,
    project_id: uuid.UUID,
    *,
    limit: int = HISTORY_LIMIT_DEFAULT,
) -> list[IncidentSnapshot]:
    async with tenant_scope(context) as session:
        return await OpsIncidentRepository(session, context).history(project_id, limit=limit)


async def latest_handover(context: TenantContext, project_id: uuid.UUID) -> HandoverRecord | None:
    async with tenant_scope(context) as session:
        return await OpsIncidentRepository(session, context).latest_handover(project_id)
