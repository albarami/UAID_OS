"""Read-only catalog lookups (Slice 61a). Admin or SELECT-capable sessions."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ecosystem_catalog import (
    CatalogAsset,
    CatalogListing,
    CatalogVettingRecord,
    ConnectorCatalogToolScope,
)


async def get_by_key(
    session: AsyncSession,
    asset_kind: str,
    asset_key: str,
    version_label: str,
) -> CatalogAsset | None:
    """Return the asset for ``(kind, key, version)`` or None."""
    return (
        await session.execute(
            select(CatalogAsset).where(
                CatalogAsset.asset_kind == asset_kind,
                CatalogAsset.asset_key == asset_key,
                CatalogAsset.version_label == version_label,
            )
        )
    ).scalar_one_or_none()


async def listed_keys(session: AsyncSession, asset_kind: str) -> list[str]:
    """Sorted unique asset keys of ``asset_kind`` whose latest live listing is listed."""
    rows = (
        (
            await session.execute(
                select(CatalogAsset.asset_key)
                .join(CatalogListing, CatalogListing.asset_id == CatalogAsset.id)
                .where(
                    CatalogAsset.asset_kind == asset_kind,
                    CatalogListing.listing_state == "listed",
                )
                .distinct()
                .order_by(CatalogAsset.asset_key)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_asset(session: AsyncSession, asset_id: uuid.UUID) -> CatalogAsset | None:
    """Return one catalog asset or None."""
    return await session.get(CatalogAsset, asset_id)


async def latest_listing(session: AsyncSession, asset_id: uuid.UUID) -> CatalogListing | None:
    """Latest listing row for an asset, if any."""
    return (
        await session.execute(
            select(CatalogListing)
            .where(CatalogListing.asset_id == asset_id)
            .order_by(CatalogListing.created_at.desc(), CatalogListing.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def latest_vetting(session: AsyncSession, asset_id: uuid.UUID) -> CatalogVettingRecord | None:
    """Latest vetting record for an asset, if any."""
    return (
        await session.execute(
            select(CatalogVettingRecord)
            .where(CatalogVettingRecord.asset_id == asset_id)
            .order_by(CatalogVettingRecord.created_at.desc(), CatalogVettingRecord.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def count_assets(session: AsyncSession) -> int:
    """Count registered catalog assets."""
    return int((await session.execute(select(func.count()).select_from(CatalogAsset))).scalar_one())


async def scope_names(session: AsyncSession, asset_id: uuid.UUID) -> list[str]:
    """Declared tool names for a connector, ordered."""
    rows = (
        (
            await session.execute(
                select(ConnectorCatalogToolScope.tool_name)
                .where(ConnectorCatalogToolScope.asset_id == asset_id)
                .order_by(ConnectorCatalogToolScope.tool_name, ConnectorCatalogToolScope.id)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
