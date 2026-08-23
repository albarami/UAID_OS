"""Idempotent admin-path population of the declared catalog (Slice 61b).

Writes only through CatalogAdmin. One caller transaction: a refused checker
result raises and the caller rolls back. Does not close the Slice 61 exit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.catalog import ConnectorSpecInput
from app.ecosystem.catalog_declared import (
    ACTOR_BLUEPRINT_REVIEWER,
    ACTOR_CONTRACT_CHECKER,
    ACTOR_INTAKE_ATTESTOR,
    ACTOR_POPULATE,
    DECLARED_CONNECTORS,
    DECLARED_INTAKE,
    DECLARED_VERSION_LABEL,
    intake_file_path,
    reference_intake_digest,
)
from app.models.agent_blueprint import AgentBlueprint
from app.models.agent_version import AgentVersion
from app.models.ecosystem_catalog import CatalogAsset, ConnectorCatalogSpec
from app.repositories.catalog_admin import (
    list_asset,
    record_contract_test,
    record_review,
    register_blueprint_version,
    register_connector,
    register_reference_intake,
)
from app.repositories.catalog_reads import get_by_key, latest_listing, scope_names


class CatalogPopulateError(Exception):
    """Declared catalog populate refused. The caller must roll back."""


@dataclass(frozen=True)
class PopulateReport:
    """Counts-only report. Listings are the evidence; no audit event is written."""

    connector_listed: tuple[str, ...]
    connector_skipped: tuple[str, ...]
    blueprint_listed: int
    blueprint_skipped: int
    intake_listed: bool
    intake_skipped: bool


def _mismatch(asset_key: str) -> CatalogPopulateError:
    return CatalogPopulateError(f"declared_identity_mismatch:{asset_key}")


def _spec_matches(stored: ConnectorSpecInput, declared: ConnectorSpecInput) -> bool:
    return (
        stored.protocol_module == declared.protocol_module
        and stored.protocol_name == declared.protocol_name
        and stored.fake_name == declared.fake_name
        and stored.service_module == declared.service_module
        and stored.live_adapter_status == declared.live_adapter_status
        and stored.live_adapter_name == declared.live_adapter_name
        and frozenset(stored.tool_names) == frozenset(declared.tool_names)
        and len(stored.tool_names) == len(declared.tool_names)
    )


async def _stored_connector_spec(
    session: AsyncSession, asset_id: uuid.UUID, asset_key: str
) -> ConnectorSpecInput:
    spec = (
        await session.execute(
            select(ConnectorCatalogSpec).where(ConnectorCatalogSpec.asset_id == asset_id)
        )
    ).scalar_one_or_none()
    if spec is None:
        raise _mismatch(asset_key)
    names = tuple(await scope_names(session, spec.asset_id))
    if not names:
        raise _mismatch(asset_key)
    return ConnectorSpecInput(
        protocol_module=spec.protocol_module,
        protocol_name=spec.protocol_name,
        fake_name=spec.fake_name,
        service_module=spec.service_module,
        live_adapter_status=spec.live_adapter_status,
        live_adapter_name=spec.live_adapter_name,
        tool_names=names,
    )


async def _is_listed(session: AsyncSession, asset_id: uuid.UUID) -> bool:
    listing = await latest_listing(session, asset_id)
    return listing is not None and listing.listing_state == "listed"


async def _list_connector(session: AsyncSession, asset: CatalogAsset, asset_key: str) -> None:
    record = await record_contract_test(session, asset_id=asset.id, reviewer=ACTOR_CONTRACT_CHECKER)
    if record.outcome != "passed":
        raise CatalogPopulateError(f"connector_contract_test_failed:{asset_key}")
    await list_asset(
        session,
        asset_id=asset.id,
        vetting_record_id=record.id,
        listed_by=ACTOR_POPULATE,
    )


async def _populate_connectors(session: AsyncSession) -> tuple[list[str], list[str]]:
    listed: list[str] = []
    skipped: list[str] = []
    for asset_key in sorted(DECLARED_CONNECTORS):
        declared = DECLARED_CONNECTORS[asset_key]
        existing = await get_by_key(session, "connector", asset_key, DECLARED_VERSION_LABEL)
        if existing is not None:
            stored = await _stored_connector_spec(session, existing.id, asset_key)
            if not _spec_matches(stored, declared):
                raise _mismatch(asset_key)
            if await _is_listed(session, existing.id):
                skipped.append(asset_key)
                continue
            await _list_connector(session, existing, asset_key)
            listed.append(asset_key)
            continue
        asset = await register_connector(
            session,
            asset_key=asset_key,
            version_label=DECLARED_VERSION_LABEL,
            registered_by=ACTOR_POPULATE,
            protocol_module=declared.protocol_module,
            protocol_name=declared.protocol_name,
            fake_name=declared.fake_name,
            service_module=declared.service_module,
            live_adapter_status=declared.live_adapter_status,
            live_adapter_name=declared.live_adapter_name,
            tool_names=list(declared.tool_names),
        )
        await _list_connector(session, asset, asset_key)
        listed.append(asset_key)
    return listed, skipped


async def _list_review(
    session: AsyncSession,
    asset: CatalogAsset,
    *,
    vetting_kind: str,
    reviewer: str,
) -> None:
    record = await record_review(
        session,
        asset_id=asset.id,
        vetting_kind=vetting_kind,
        provenance="reviewer_asserted_admin_recorded",
        outcome="passed",
        reviewer=reviewer,
    )
    await list_asset(
        session,
        asset_id=asset.id,
        vetting_record_id=record.id,
        listed_by=ACTOR_POPULATE,
    )


async def _query_blueprint_versions(
    session: AsyncSession,
) -> list[tuple[uuid.UUID, str, str]]:
    rows = (
        await session.execute(
            select(AgentVersion.id, AgentVersion.version_label, AgentBlueprint.key)
            .join(AgentBlueprint, AgentBlueprint.id == AgentVersion.blueprint_id)
            .order_by(AgentBlueprint.key, AgentVersion.version_label, AgentVersion.id)
        )
    ).all()
    return [(row.id, row.version_label, row.key) for row in rows]


async def _populate_blueprints(session: AsyncSession) -> tuple[int, int]:
    rows = await _query_blueprint_versions(session)
    seen: set[tuple[str, str]] = set()
    listed = 0
    skipped = 0
    for version_id, version_label, blueprint_key in rows:
        pair = (blueprint_key, version_label)
        if pair in seen:
            raise CatalogPopulateError(f"duplicate_blueprint_version_label:{blueprint_key}")
        seen.add(pair)
        existing = await get_by_key(session, "agent_blueprint", blueprint_key, version_label)
        if existing is not None:
            if existing.agent_version_id != version_id:
                raise _mismatch(blueprint_key)
            if await _is_listed(session, existing.id):
                skipped += 1
                continue
            await _list_review(
                session,
                existing,
                vetting_kind="blueprint_security_review",
                reviewer=ACTOR_BLUEPRINT_REVIEWER,
            )
            listed += 1
            continue
        asset = await register_blueprint_version(
            session,
            asset_key=blueprint_key,
            version_label=version_label,
            registered_by=ACTOR_POPULATE,
            agent_version_id=version_id,
        )
        await _list_review(
            session,
            asset,
            vetting_kind="blueprint_security_review",
            reviewer=ACTOR_BLUEPRINT_REVIEWER,
        )
        listed += 1
    return listed, skipped


def _intake_matches(asset: CatalogAsset, digest: str) -> bool:
    return (
        asset.domain_label == DECLARED_INTAKE.domain_label
        and asset.source_ref == DECLARED_INTAKE.source_ref
        and asset.content_sha256 == digest
    )


async def _populate_intake(session: AsyncSession) -> tuple[bool, bool]:
    path = intake_file_path()
    if not path.is_file():
        raise CatalogPopulateError("declared_intake_file_missing")
    digest = reference_intake_digest(path)
    existing = await get_by_key(
        session, "reference_intake", DECLARED_INTAKE.asset_key, DECLARED_INTAKE.version_label
    )
    if existing is not None:
        if not _intake_matches(existing, digest):
            raise _mismatch(DECLARED_INTAKE.asset_key)
        if await _is_listed(session, existing.id):
            return False, True
        await _list_review(
            session,
            existing,
            vetting_kind="reference_intake_constraint_attestation",
            reviewer=ACTOR_INTAKE_ATTESTOR,
        )
        return True, False
    asset = await register_reference_intake(
        session,
        asset_key=DECLARED_INTAKE.asset_key,
        version_label=DECLARED_INTAKE.version_label,
        registered_by=ACTOR_POPULATE,
        domain_label=DECLARED_INTAKE.domain_label,
        content_sha256=digest,
        source_ref=DECLARED_INTAKE.source_ref,
    )
    await _list_review(
        session,
        asset,
        vetting_kind="reference_intake_constraint_attestation",
        reviewer=ACTOR_INTAKE_ATTESTOR,
    )
    return True, False


async def populate_declared_catalog(session: AsyncSession) -> PopulateReport:
    """Register, vet, and list declared connectors, query blueprints, and the intake.

    Admin session only. Does not commit. A failed connector checker raises
    ``CatalogPopulateError`` so the caller can roll back; nothing stays listed.
    """
    connector_listed, connector_skipped = await _populate_connectors(session)
    blueprint_listed, blueprint_skipped = await _populate_blueprints(session)
    intake_listed, intake_skipped = await _populate_intake(session)
    return PopulateReport(
        connector_listed=tuple(connector_listed),
        connector_skipped=tuple(connector_skipped),
        blueprint_listed=blueprint_listed,
        blueprint_skipped=blueprint_skipped,
        intake_listed=intake_listed,
        intake_skipped=intake_skipped,
    )
