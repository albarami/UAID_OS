"""Tenant scoping plumbing (INV-4).

No tenant-owned data may be read or written without an explicit
:class:`TenantContext`. The repository base requires one and filters every read
by ``tenant_id``; writes are stamped with the context tenant and any attempt to
write a row belonging to another tenant raises :class:`CrossTenantError`.

This is the application-layer guard. DB-level enforcement (Postgres RLS) is
Slice 1b — both layers are intended to hold simultaneously.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class CrossTenantError(Exception):
    """Raised when an operation would cross the tenant boundary."""


@dataclass(frozen=True)
class TenantContext:
    """An explicit tenant scope. Required to touch tenant-owned data."""

    tenant_id: uuid.UUID


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
