"""Audit-log service (Slice 2, §16.6).

Thin wrappers over the database append/verify functions. This module never opens
its own connection and never uses admin credentials: callers pass the session.

- ``record`` runs as the runtime ``uaid_app`` role via the ``audit_append``
  SECURITY DEFINER function. It takes NO tenant_id — the database derives the
  tenant from the transaction-local ``app.current_tenant`` GUC and fails closed
  if it is unset. Therefore ``record`` MUST be called inside ``tenant_scope``.
  It returns only the minimal surface ``{id, entry_hash, created_at}``.
- ``verify_chain`` runs the full-chain integrity check; it requires an
  admin/owner session (the ``audit_verify`` function is not granted to
  ``uaid_app``) and is intended for tests/operations, not the runtime path.
"""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_APPEND_SQL = text(
    "SELECT id, entry_hash, created_at "
    "FROM audit_append(:actor, :action, :target, CAST(:payload AS jsonb))"
)
_VERIFY_SQL = text("SELECT ok, first_bad_seq FROM audit_verify()")


async def record(
    session: AsyncSession,
    *,
    action: str,
    actor: str,
    target: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Append a tenant audit event (tenant derived from the GUC, not a parameter).

    Must run inside ``tenant_scope`` so ``app.current_tenant`` is set; otherwise
    the database raises (fail closed). Returns ``{id, entry_hash, created_at}``.
    """
    result = await session.execute(
        _APPEND_SQL,
        {
            "actor": actor,
            "action": action,
            "target": target,
            "payload": json.dumps(dict(payload) if payload else {}),
        },
    )
    return result.mappings().one()


async def verify_chain(admin_session: AsyncSession) -> Mapping[str, Any]:
    """Full-chain integrity check. Requires an admin/owner session (not uaid_app)."""
    result = await admin_session.execute(_VERIFY_SQL)
    return result.mappings().one()
