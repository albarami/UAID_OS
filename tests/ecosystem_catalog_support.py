"""Shared Slice-61a catalog fixtures, true connector specs, and SQL helpers."""

from __future__ import annotations

import hashlib
import uuid
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.catalog import ConnectorSpecInput
from app.models.ecosystem_catalog import CatalogAsset, CatalogListing, CatalogVettingRecord
from app.repositories.catalog_admin import (
    list_asset,
    record_contract_test,
    record_review,
    register_blueprint_version,
    register_connector,
    register_reference_intake,
)

FROZEN_HASHES: dict[str, str] = {
    "app/tools/broker.py": "20728181a65073d0ec5cacb63385fa2101760ec670e54621991eb24a97a33c57",
    "app/tools/registry.py": "c10023cfcbd074bb8c99e4dc0fa5a2b7de89d685820394b0902cde1ccfcc94e3",
    "app/policy/matrix.py": "c69a09ee8f910bffa839a8b75154dd3f3025fdb44c0c5aa0b9bfdd6e6f31a43f",
    "app/agents/registry.py": "b942a9d6a210cbe9730c0b447d20158137e3c87e2c317515b35d91cb99195964",
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26",
    "app/runtime/control_loop.py": "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180",
    "app/release/scm_connector.py": "b0d0e41086dac11f11f95cc8cb101f2cdf6456f164f1a57497122d6dcbabb648",
    "app/release/deploy_connector.py": (
        "49cd49fa21df0a7b80aa32b61f8964e07cba8b8154b7d3315a75ce74d45fcdcb"
    ),
    "app/release/monitoring_connector.py": (
        "7f507ca61a90f8ea1c6620e7bc06d87ea3921a42c244b1a5946bf9d4da01c09b"
    ),
    "app/release/secrets_connector.py": (
        "1105e3c3cd0a1909ba70444b5203d5ea30b1451b774f279e316526450abe86c0"
    ),
    "app/release/pm_connector.py": "96747244dcb2f857ed44478679e0ebc4b4307989ef4cc66e78c898d2d6bd8e03",
    "app/release/project_repo.py": "01ea9375a6afed9ffacba8eb7de23c99cc2f6b0cef8311ec3ff2a74efa0a84d4",
    "app/repositories/tools.py": "395330aa8581ccfccd52b2ab270fa81b96a33f0d8b4e013405aad378632e1ee0",
}

CATALOG_TABLES: tuple[str, ...] = (
    "catalog_assets",
    "connector_catalog_specs",
    "connector_catalog_tool_scope",
    "catalog_vetting_records",
    "catalog_vetting_check_results",
    "catalog_listings",
    "tenant_catalog_adoptions",
)

CORE_DECISION_GLOBS: tuple[str, ...] = (
    "app/intake/readiness.py",
    "app/release/production_autonomy.py",
    "app/runtime/control_loop.py",
    "app/policy",
    "app/tools",
    "app/agents",
)


class ProbeConnector(Protocol):
    async def probe(self, *, host: str) -> dict: ...


class ProbeFake:
    async def probe(self, *, host: str) -> dict:
        return {}


class ProbeFakeMissing:
    pass


class ProbeFakeMismatch:
    async def probe(self, *, hostname: str) -> dict:
        return {}


class NotAProtocol:
    async def probe(self, *, host: str) -> dict:
        return {}


def sha(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def probe_spec(
    *,
    tools: tuple[str, ...] = ("pm.read_issues",),
    protocol_name: str = "ProbeConnector",
    fake_name: str = "ProbeFake",
    status: str = "absent",
    adapter: str | None = None,
) -> ConnectorSpecInput:
    return ConnectorSpecInput(
        protocol_module="tests.ecosystem_catalog_support",
        protocol_name=protocol_name,
        fake_name=fake_name,
        service_module="tests.ecosystem_catalog_support",
        live_adapter_status=status,
        live_adapter_name=adapter,
        tool_names=tools,
    )


def real_connector_specs() -> dict[str, ConnectorSpecInput]:
    """True specs for the six release services. Thin wrapper over DECLARED_CONNECTORS."""
    from app.ecosystem.catalog_declared import DECLARED_CONNECTORS, DECLARED_CONNECTOR_SHORT_KEYS

    return {
        short: DECLARED_CONNECTORS[asset_key]
        for short, asset_key in DECLARED_CONNECTOR_SHORT_KEYS.items()
    }


async def seed_project(session: AsyncSession) -> dict:
    suffix = uuid.uuid4().hex[:10]
    org = (
        await session.execute(
            text("INSERT INTO organizations (name,slug) VALUES ('CatOrg',:s) RETURNING id"),
            {"s": f"cat-org-{suffix}"},
        )
    ).scalar_one()
    tenant = (
        await session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'t1',:s) RETURNING id"
            ),
            {"o": org, "s": f"cat-t1-{suffix}"},
        )
    ).scalar_one()
    tenant2 = (
        await session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'t2',:s) RETURNING id"
            ),
            {"o": org, "s": f"cat-t2-{suffix}"},
        )
    ).scalar_one()
    project = (
        await session.execute(
            text("INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P1',:s) RETURNING id"),
            {"t": tenant, "s": f"cat-p1-{suffix}"},
        )
    ).scalar_one()
    project2 = (
        await session.execute(
            text("INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P2',:s) RETURNING id"),
            {"t": tenant2, "s": f"cat-p2-{suffix}"},
        )
    ).scalar_one()
    return {
        "org": org,
        "tenant": tenant,
        "tenant2": tenant2,
        "project": project,
        "project2": project2,
    }


async def register_probe_connector(
    session: AsyncSession,
    *,
    asset_key: str | None = None,
    version_label: str = "v1",
    registered_by: str = "registrar",
    fake_name: str | None = None,
    tool_names: list[str] | None = None,
) -> CatalogAsset:
    spec = real_connector_specs()["pm"]
    return await register_connector(
        session,
        asset_key=asset_key or unique("pm"),
        version_label=version_label,
        registered_by=registered_by,
        protocol_module=spec.protocol_module,
        protocol_name=spec.protocol_name,
        fake_name=fake_name or spec.fake_name,
        service_module=spec.service_module,
        live_adapter_status=spec.live_adapter_status,
        live_adapter_name=spec.live_adapter_name,
        tool_names=tool_names if tool_names is not None else list(spec.tool_names),
    )


async def register_vet_list_pm(
    session: AsyncSession, *, listed_by: str = "lister"
) -> tuple[CatalogAsset, CatalogVettingRecord, CatalogListing]:
    asset = await register_probe_connector(session)
    vetting = await record_contract_test(session, asset_id=asset.id, reviewer="checker")
    listing = await list_asset(
        session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by=listed_by
    )
    return asset, vetting, listing


async def register_listed_blueprint(
    session: AsyncSession, *, reviewer: str = "reviewer-b"
) -> tuple[CatalogAsset, CatalogVettingRecord, CatalogListing]:
    from app.agents.registry import register_blueprint, register_version

    key = unique("bp")
    blueprint = await register_blueprint(
        session,
        key=key,
        role="builder",
        mission="probe",
        archetype="builder",
        actor="admin",
    )
    version = await register_version(
        session,
        blueprint_id=blueprint.id,
        version_label="v1",
        model_route="fake",
        prompt_hash=sha("p"),
        tool_policy_hash=sha("t"),
        context_policy_hash=sha("c"),
        eval_suite_hash=sha("e"),
        critical_dependencies_hash=sha("d"),
        output_schema_hash=sha("o"),
        actor="admin",
    )
    asset = await register_blueprint_version(
        session,
        asset_key=key,
        version_label="v1",
        registered_by="registrar-a",
        agent_version_id=version.id,
    )
    vetting = await record_review(
        session,
        asset_id=asset.id,
        vetting_kind="blueprint_security_review",
        provenance="reviewer_asserted_admin_recorded",
        outcome="passed",
        reviewer=reviewer,
    )
    listing = await list_asset(
        session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by="lister"
    )
    return asset, vetting, listing


async def register_listed_intake(
    session: AsyncSession,
) -> tuple[CatalogAsset, CatalogVettingRecord, CatalogListing]:
    asset = await register_reference_intake(
        session,
        asset_key=unique("intake"),
        version_label="v1",
        registered_by="registrar",
        domain_label="generic",
        content_sha256=sha("intake"),
        source_ref="docs/example.md",
    )
    vetting = await record_review(
        session,
        asset_id=asset.id,
        vetting_kind="reference_intake_constraint_attestation",
        provenance="reviewer_asserted_admin_recorded",
        outcome="passed",
        reviewer="attestor",
    )
    listing = await list_asset(
        session, asset_id=asset.id, vetting_record_id=vetting.id, listed_by="lister"
    )
    return asset, vetting, listing


def message_holds(exc: BaseException, fragment: str) -> bool:
    return fragment in str(exc)


async def execute_sql(session: AsyncSession, sql: str, **params):
    return await session.execute(text(sql), params)


async def add_probe_blueprint(session: AsyncSession, key: str):
    from app.agents.registry import register_blueprint

    return await register_blueprint(
        session, key=key, role="builder", mission="p", archetype="builder", actor="admin"
    )


async def add_probe_version(session: AsyncSession, blueprint_id, label: str, tag: str):
    from app.agents.registry import register_version

    return await register_version(
        session,
        blueprint_id=blueprint_id,
        version_label=label,
        model_route="fake",
        prompt_hash=sha(tag + "p"),
        tool_policy_hash=sha(tag + "t"),
        context_policy_hash=sha(tag + "c"),
        eval_suite_hash=sha(tag + "e"),
        critical_dependencies_hash=sha(tag + "d"),
        output_schema_hash=sha(tag + "o"),
        actor="admin",
    )


async def stored_connector_spec(session: AsyncSession, key: str) -> ConnectorSpecInput:
    from app.ecosystem.catalog_declared import DECLARED_VERSION_LABEL
    from app.models.ecosystem_catalog import ConnectorCatalogSpec, ConnectorCatalogToolScope
    from app.repositories.catalog_reads import get_by_key

    asset = await get_by_key(session, "connector", key, DECLARED_VERSION_LABEL)
    assert asset is not None
    spec = (
        await session.execute(
            select(ConnectorCatalogSpec).where(ConnectorCatalogSpec.asset_id == asset.id)
        )
    ).scalar_one()
    names = (
        (
            await session.execute(
                select(ConnectorCatalogToolScope.tool_name)
                .where(ConnectorCatalogToolScope.asset_id == asset.id)
                .order_by(ConnectorCatalogToolScope.tool_name)
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
        tool_names=tuple(names),
    )
