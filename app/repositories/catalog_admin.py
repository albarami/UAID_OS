"""Admin-path catalog registration, vetting, listing, and delist (Slice 61a).

Runs on an admin session and is not tenant-audited, matching
``register_blueprint`` / ``register_version``. The catalog stays empty of
product assets: this module registers only what a caller asks for.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.catalog import (
    ASSET_KEY_MAX,
    LISTED_BY_MAX,
    LIVE_ADAPTER_STATUSES,
    REGISTERED_BY_MAX,
    REVIEWER_MAX,
    SOURCE_REF_MAX,
    SYMBOL_MAX,
    VERSION_LABEL_MAX,
    CatalogError,
    CatalogValidationError,
    ConnectorSpecInput,
    refuse_checker_provenance_for_review,
    require_bounded_text,
    require_content_sha256,
    require_member,
    required_provenance,
    required_vetting_kind,
    validate_live_adapter,
    validate_tool_names,
)
from app.ecosystem.contract_test import run_connector_contract_test
from app.models.ecosystem_catalog import (
    CatalogAsset,
    CatalogListing,
    CatalogVettingCheckResult,
    CatalogVettingRecord,
    ConnectorCatalogSpec,
    ConnectorCatalogToolScope,
)


class CatalogAdminError(CatalogError):
    """Admin-path catalog operation refused."""


async def _lock_asset(session: AsyncSession, asset_id: uuid.UUID) -> CatalogAsset:
    row = (
        await session.execute(
            select(CatalogAsset).where(CatalogAsset.id == asset_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise CatalogAdminError("unknown catalog asset")
    return row


def _require_known_tools(tool_names: tuple[str, ...]) -> None:
    from app.tools.registry import get_contract

    for name in tool_names:
        if get_contract(name) is None:
            raise CatalogValidationError(f"unknown tool (not in the broker registry): {name!r}")


async def register_connector(
    session: AsyncSession,
    *,
    asset_key: str,
    version_label: str,
    registered_by: str,
    protocol_module: str,
    protocol_name: str,
    fake_name: str,
    service_module: str,
    live_adapter_status: str,
    live_adapter_name: str | None,
    tool_names: list[str] | tuple[str, ...],
) -> CatalogAsset:
    """Write asset + spec + scope in one transaction. Admin path."""
    key = require_bounded_text("asset_key", asset_key, ASSET_KEY_MAX)
    version = require_bounded_text("version_label", version_label, VERSION_LABEL_MAX)
    actor = require_bounded_text("registered_by", registered_by, REGISTERED_BY_MAX)
    proto_mod = require_bounded_text("protocol_module", protocol_module, SYMBOL_MAX)
    proto_name = require_bounded_text("protocol_name", protocol_name, SYMBOL_MAX)
    fake = require_bounded_text("fake_name", fake_name, SYMBOL_MAX)
    service = require_bounded_text("service_module", service_module, SYMBOL_MAX)
    require_member("live_adapter_status", live_adapter_status, LIVE_ADAPTER_STATUSES)
    validate_live_adapter(status=live_adapter_status, name=live_adapter_name)
    adapter = (
        None
        if live_adapter_name is None
        else require_bounded_text("live_adapter_name", live_adapter_name, SYMBOL_MAX)
    )
    names = validate_tool_names(tool_names)
    _require_known_tools(names)
    asset = CatalogAsset(
        asset_kind="connector",
        asset_key=key,
        version_label=version,
        registered_by=actor,
    )
    session.add(asset)
    await session.flush()
    session.add(
        ConnectorCatalogSpec(
            asset_id=asset.id,
            asset_kind="connector",
            protocol_module=proto_mod,
            protocol_name=proto_name,
            fake_name=fake,
            service_module=service,
            live_adapter_status=live_adapter_status,
            live_adapter_name=adapter,
        )
    )
    for name in names:
        session.add(
            ConnectorCatalogToolScope(asset_id=asset.id, asset_kind="connector", tool_name=name)
        )
    await session.flush()
    return asset


async def register_blueprint_version(
    session: AsyncSession,
    *,
    asset_key: str,
    version_label: str,
    registered_by: str,
    agent_version_id: uuid.UUID,
) -> CatalogAsset:
    """Register a catalog row bound to an existing immutable agent_versions row."""
    from app.models.agent_version import AgentVersion

    version_row = await session.get(AgentVersion, agent_version_id)
    if version_row is None:
        raise CatalogValidationError("agent_version_id must reference an existing agent version")
    asset = CatalogAsset(
        asset_kind="agent_blueprint",
        asset_key=require_bounded_text("asset_key", asset_key, ASSET_KEY_MAX),
        version_label=require_bounded_text("version_label", version_label, VERSION_LABEL_MAX),
        registered_by=require_bounded_text("registered_by", registered_by, REGISTERED_BY_MAX),
        agent_version_id=agent_version_id,
    )
    session.add(asset)
    await session.flush()
    return asset


async def register_reference_intake(
    session: AsyncSession,
    *,
    asset_key: str,
    version_label: str,
    registered_by: str,
    domain_label: str,
    content_sha256: str,
    source_ref: str,
) -> CatalogAsset:
    """Register a reference-intake identity. Digest is registrar-supplied metadata."""
    from app.ecosystem.catalog import DOMAIN_LABEL_MAX

    asset = CatalogAsset(
        asset_kind="reference_intake",
        asset_key=require_bounded_text("asset_key", asset_key, ASSET_KEY_MAX),
        version_label=require_bounded_text("version_label", version_label, VERSION_LABEL_MAX),
        registered_by=require_bounded_text("registered_by", registered_by, REGISTERED_BY_MAX),
        domain_label=require_bounded_text("domain_label", domain_label, DOMAIN_LABEL_MAX),
        content_sha256=require_content_sha256(content_sha256),
        source_ref=require_bounded_text("source_ref", source_ref, SOURCE_REF_MAX),
    )
    session.add(asset)
    await session.flush()
    return asset


async def _load_connector_spec(session: AsyncSession, asset_id: uuid.UUID) -> ConnectorSpecInput:
    spec = (
        await session.execute(
            select(ConnectorCatalogSpec).where(ConnectorCatalogSpec.asset_id == asset_id)
        )
    ).scalar_one()
    scopes = (
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
    return ConnectorSpecInput(
        protocol_module=spec.protocol_module,
        protocol_name=spec.protocol_name,
        fake_name=spec.fake_name,
        service_module=spec.service_module,
        live_adapter_status=spec.live_adapter_status,
        live_adapter_name=spec.live_adapter_name,
        tool_names=tuple(scopes),
    )


async def record_contract_test(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    reviewer: str,
) -> CatalogVettingRecord:
    """Lock the asset, load children, run the checker, then insert the record."""
    asset = await _lock_asset(session, asset_id)
    if asset.asset_kind != "connector":
        raise CatalogValidationError("record_contract_test is only for connectors")
    spec = await _load_connector_spec(session, asset_id)
    result = run_connector_contract_test(spec)
    record = CatalogVettingRecord(
        asset_id=asset.id,
        vetting_kind=required_vetting_kind("connector"),
        provenance=required_provenance("connector_contract_test"),
        outcome="passed" if result.passed else "failed",
        reviewer=require_bounded_text("reviewer", reviewer, REVIEWER_MAX),
    )
    session.add(record)
    await session.flush()
    for check in result.results:
        session.add(
            CatalogVettingCheckResult(
                vetting_record_id=record.id, check_name=check.name, passed=check.passed
            )
        )
    await session.flush()
    return record


async def record_review(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    vetting_kind: str,
    provenance: str,
    outcome: str,
    reviewer: str,
) -> CatalogVettingRecord:
    """Record a reviewer-asserted outcome. Refuses checker provenance."""
    refuse_checker_provenance_for_review(provenance)
    asset = await _lock_asset(session, asset_id)
    if asset.asset_kind == "connector":
        raise CatalogValidationError("record_review does not write connector contract tests")
    expected_kind = required_vetting_kind(asset.asset_kind)
    if vetting_kind != expected_kind:
        raise CatalogValidationError("vetting_kind does not match the asset kind")
    if provenance != required_provenance(vetting_kind):
        raise CatalogValidationError("provenance does not match the vetting kind")
    if outcome not in ("passed", "failed"):
        raise CatalogValidationError("outcome must be passed or failed")
    record = CatalogVettingRecord(
        asset_id=asset.id,
        vetting_kind=vetting_kind,
        provenance=provenance,
        outcome=outcome,
        reviewer=require_bounded_text("reviewer", reviewer, REVIEWER_MAX),
    )
    session.add(record)
    await session.flush()
    return record


async def list_asset(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    vetting_record_id: uuid.UUID,
    listed_by: str,
) -> CatalogListing:
    """Insert a listed row citing one exact passing vetting record."""
    listing = CatalogListing(
        asset_id=asset_id,
        vetting_record_id=vetting_record_id,
        listing_state="listed",
        listed_by=require_bounded_text("listed_by", listed_by, LISTED_BY_MAX),
    )
    session.add(listing)
    await session.flush()
    return listing


async def delist_asset(
    session: AsyncSession,
    *,
    listing_id: uuid.UUID,
    reason: str,
) -> CatalogListing:
    """One-way listed → delisted. Mutates only state, delisted_at, and reason."""
    from app.ecosystem.catalog import DELISTED_REASON_MAX

    listing = await session.get(CatalogListing, listing_id)
    if listing is None:
        raise CatalogAdminError("unknown listing")
    listing.listing_state = "delisted"
    listing.delisted_at = datetime.now(timezone.utc)
    listing.delisted_reason = require_bounded_text("delisted_reason", reason, DELISTED_REASON_MAX)
    await session.flush()
    return listing


async def children_complete(session: AsyncSession, asset_id: uuid.UUID) -> bool:
    """Probe the STABLE SQL helper directly."""
    value = (
        await session.execute(
            text("SELECT public.catalog_connector_children_complete(:id)"),
            {"id": asset_id},
        )
    ).scalar_one()
    return bool(value)
