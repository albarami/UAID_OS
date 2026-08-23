"""Public Slice-60 export-bundle wrappers.

Owns ``tenant_scope``. Callers cannot pass a session, ``as_of``, or ``expires_at``.
Nothing here signs ``evidence_pack.json``, emits OSCAL, or authorizes go-live.
"""

from __future__ import annotations

import asyncio
import random
import uuid

from sqlalchemy.exc import DBAPIError

from app.audit import record as audit_record
from app.release.export_bundle import (
    AUDIT_ATTEMPT_NON_EVIDENCE,
    BundleVerification,
    ExportBundleError,
    ExportBundleIdempotencyRace,
    ExportBundleSnapshot,
    validate_actor_label,
    validate_idempotency_key,
)
from app.release.export_signing import load_signing_seed
from app.repositories.export_bundle_reads import ExportBundleReadRepository
from app.repositories.export_bundles import ExportBundleRepository, snapshot_of
from app.tenancy import TenantContext, tenant_scope

MAX_IDEMPOTENCY_RACE_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 0.005
RETRY_BACKOFF_JITTER_SECONDS = 0.003
_RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})
_WRITE_ISOLATION = "REPEATABLE READ"
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
    raise ExportBundleIdempotencyRace(
        "idempotency winner stayed invisible after bounded REPEATABLE READ retries"
    ) from last_race


async def _generate_once(
    context: TenantContext,
    pack_id: uuid.UUID,
    *,
    actor: str,
    idempotency_key: str,
) -> ExportBundleSnapshot:
    async with tenant_scope(context, isolation_level=_WRITE_ISOLATION) as session:
        repo = ExportBundleRepository(session, context)
        recorded = await repo.generate(pack_id, actor=actor, idempotency_key=idempotency_key)
        if recorded is not None:
            return recorded
        winner = await repo.get_by_idempotency(pack_id, idempotency_key)
        if winner is None:
            raise _IdempotencyWinnerNotVisible()
        return snapshot_of(winner)


async def generate_export_bundle(
    context: TenantContext,
    pack_id: uuid.UUID,
    *,
    actor: str,
    idempotency_key: str,
) -> ExportBundleSnapshot:
    """Persist one signed offline auditor bundle. Owns REPEATABLE READ ``tenant_scope``."""
    actor_label = validate_actor_label(actor)
    key = validate_idempotency_key(idempotency_key)
    load_signing_seed()
    return await _retry(
        lambda: _generate_once(
            context,
            pack_id,
            actor=actor_label,
            idempotency_key=key,
        )
    )


async def verify_export_bundle(
    context: TenantContext,
    export_record_id: uuid.UUID,
) -> BundleVerification:
    """Recompute integrity and horizon from persisted bytes. Read-only except attempt audit."""
    async with tenant_scope(context, isolation_level=_READ_ISOLATION) as session:
        repo = ExportBundleReadRepository(session, context)
        result = await repo.verify(export_record_id)
        record = await repo.get(export_record_id)
        if record is not None:
            await audit_record(
                session,
                action="evidence_pack.bundle_verification_attempted",
                actor="export-bundle-verify",
                target=str(record.id),
                payload={
                    "project_id": str(record.project_id),
                    "evidence_pack_id": str(record.evidence_pack_id),
                    "result_code": result.integrity_result.value,
                    "horizon_status": result.horizon_status.value,
                    "signing_key_id": record.signing_key_id,
                    "file_count": record.file_count,
                    "manifest_digest": record.manifest_digest,
                    AUDIT_ATTEMPT_NON_EVIDENCE: True,
                },
            )
        return result


__all__ = [
    "generate_export_bundle",
    "verify_export_bundle",
    "ExportBundleError",
    "ExportBundleIdempotencyRace",
]
