"""Tenant-owned catalog adoption records (Slice 61a). Not a grant."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.ecosystem.catalog import (
    ADOPTED_BY_MAX,
    CatalogError,
    audit_safe_adoption_payload,
    require_bounded_text,
)
from app.models.ecosystem_catalog import CatalogAsset, CatalogListing, TenantCatalogAdoption
from app.tenancy import TenantContext, TenantScopedRepository, tenant_scope


class CatalogAdoptionError(CatalogError):
    """Adoption refused."""


class CatalogAdoptionRepository(TenantScopedRepository):
    """Tenant-scoped adoption writes. Creates no allowlist or instance."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, TenantCatalogAdoption)

    async def adopt(
        self,
        project_id: uuid.UUID,
        listing_id: uuid.UUID,
        *,
        adopted_by: str,
    ) -> TenantCatalogAdoption:
        """Record that this tenant/project adopted a listed asset. Idempotent."""
        listing = await self.session.get(CatalogListing, listing_id)
        if listing is None:
            raise CatalogAdoptionError("unknown listing")
        existing = (
            await self.session.execute(
                select(TenantCatalogAdoption).where(
                    TenantCatalogAdoption.tenant_id == self.context.tenant_id,
                    TenantCatalogAdoption.project_id == project_id,
                    TenantCatalogAdoption.listing_id == listing_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        actor = require_bounded_text("adopted_by", adopted_by, ADOPTED_BY_MAX)
        row = TenantCatalogAdoption(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            listing_id=listing.id,
            asset_id=listing.asset_id,
            adopted_by=actor,
        )
        self.session.add(row)
        await self.session.flush()
        asset = await self.session.get(CatalogAsset, listing.asset_id)
        if asset is None:
            raise CatalogAdoptionError("listing asset missing")
        await audit_record(
            self.session,
            action="catalog.adopted",
            actor=actor,
            target=str(row.id),
            payload=dict(
                audit_safe_adoption_payload(
                    listing_id=str(listing.id),
                    asset_kind=asset.asset_kind,
                    asset_key=asset.asset_key,
                    version_label=asset.version_label,
                )
            ),
        )
        return row


async def adopt_listing(
    context: TenantContext,
    project_id: uuid.UUID,
    listing_id: uuid.UUID,
    *,
    adopted_by: str,
) -> TenantCatalogAdoption:
    """Public wrapper: READ COMMITTED tenant_scope, then adopt."""
    async with tenant_scope(context) as session:
        return await CatalogAdoptionRepository(session, context).adopt(
            project_id, listing_id, adopted_by=adopted_by
        )


async def count_adoptions(session: AsyncSession, project_id: uuid.UUID) -> int:
    """Count adoption rows for a project (caller session, GUC-scoped under RLS)."""
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(TenantCatalogAdoption)
                .where(TenantCatalogAdoption.project_id == project_id)
            )
        ).scalar_one()
    )
