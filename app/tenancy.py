"""Tenant scoping plumbing (INV-4).

No tenant-owned data may be read or written without an explicit
:class:`TenantContext`. The repository base requires one and filters every read
by ``tenant_id``; writes are stamped with the context tenant and any attempt to
write a row belonging to another tenant raises :class:`CrossTenantError`.

This is the application-layer guard. DB-level enforcement (Postgres RLS) is
Slice 1b — both layers are intended to hold simultaneously.
"""

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_sessionmaker
from app.identity import AuthenticatedActor


class CrossTenantError(Exception):
    """Raised when an operation would cross the tenant boundary."""


@dataclass(frozen=True)
class TenantContext:
    """An explicit tenant scope. Required to touch tenant-owned data.

    ``actor`` is the request-authenticated principal (Slice 27), or ``None`` for an
    unauthenticated/internal caller. When present, repositories stamp the
    ``request_authenticated`` provenance tier (key-custody-based, NOT a human signature).
    """

    tenant_id: uuid.UUID
    actor: AuthenticatedActor | None = None


@asynccontextmanager
async def tenant_scope(context: TenantContext) -> AsyncIterator[AsyncSession]:
    """Yield a session whose transaction is bound to ``context``'s tenant for RLS.

    The runtime transaction invariant (INV-5 enforcement): the Postgres GUC
    ``app.current_tenant`` is set with ``set_config(..., true)`` (transaction-local)
    on the **same** connection/transaction that then executes the tenant-owned
    queries. RLS policies read this GUC; an unset GUC denies by default. Because
    ``set_config(..., true)`` is transaction-scoped, all work MUST happen inside
    this single ``session.begin()`` block — `TenantScopedRepository` is intended
    to be used within ``tenant_scope``.
    """
    if context is None:
        raise CrossTenantError("a TenantContext is required for tenant-owned data")
    async with get_sessionmaker()() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tenant, true)"),
                {"tenant": str(context.tenant_id)},
            )
            yield session


class TenantScopedRepository:
    """Base repository bound to a single tenant.

    ``model`` must expose a ``tenant_id`` column. Every query issued through this
    repository is filtered to ``context.tenant_id``; there is no unscoped path.
    """

    def __init__(self, session: AsyncSession, context: TenantContext, model: type):
        if context is None:
            raise CrossTenantError("a TenantContext is required for tenant-owned data")
        self.session = session
        self.context = context
        self.model = model

    async def add(self, obj):
        """Stamp ``obj`` with the context tenant; reject foreign-tenant writes."""
        existing = getattr(obj, "tenant_id", None)
        if existing is not None and existing != self.context.tenant_id:
            raise CrossTenantError(
                f"refusing to write {self.model.__name__} for tenant {existing} "
                f"under context tenant {self.context.tenant_id}"
            )
        obj.tenant_id = self.context.tenant_id
        self.session.add(obj)
        return obj

    async def get(self, obj_id: uuid.UUID):
        """Fetch by id, scoped to the context tenant (None if not in tenant)."""
        stmt = select(self.model).where(
            self.model.id == obj_id,
            self.model.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(self) -> Sequence:
        """All rows for the context tenant only."""
        stmt = select(self.model).where(self.model.tenant_id == self.context.tenant_id)
        return (await self.session.execute(stmt)).scalars().all()
