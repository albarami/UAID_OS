"""Slice 83 commit-11 helpers: evidence-domain A3 writers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.cost import COST_COMPONENTS
from app.cost_forecast import ComponentAssumption
from app.ecosystem.learning_publish import publish_cross_project_aggregates
from app.llm.pricing import ModelPrice
from app.models.intake_artifact import IntakeArtifact
from app.release.evidence_pack import (
    INVENTORY_SECTIONS,
    SectionInventory,
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
    project_source_record,
)
from app.repositories.catalog_admin import record_contract_test
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.repositories.cost_forecasts import CostForecastRepository, ReportedModelPlan
from app.repositories.evidence_packs import EvidencePackRepository
from app.tenancy import TenantContext
from tests.ecosystem_catalog_support import register_probe_connector, unique
from tests.slice83_a2_d_support import export_writer as export_keyed_writer
from tests.slice83_support import Writer, bind_tenant, seed_org_tenant_project
from tests.test_cost_forecasts import _policy_payload

_AS_OF = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)


def _zero_inventories() -> tuple[SectionInventory, ...]:
    empty = digest_bytes(canonical_json_bytes([]))
    return tuple(
        SectionInventory(
            section_code=section,
            presence_code="present_zero_rows",
            item_count=0,
            section_digest=empty,
            required=True,
            failure_code=None,
        )
        for section in INVENTORY_SECTIONS
    )


def _assumptions() -> tuple[ComponentAssumption, ...]:
    return tuple(
        ComponentAssumption(
            component=component,
            remaining_total_usd=Decimal("0") if component == "model_inference" else Decimal("1"),
            remaining_today_usd=Decimal("0") if component == "model_inference" else Decimal("1"),
        )
        for component in sorted(COST_COMPONENTS)
    )


async def seed_connector_asset(admin_engine: AsyncEngine) -> Any:
    """One registered connector so ``record_contract_test`` can race."""
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        asset = await register_probe_connector(session)
        await session.commit()
        return asset


def connector_writer(*, asset_key: str | None = None) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await register_probe_connector(session, asset_key=asset_key)

    return writer


def vetting_writer(asset_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await record_contract_test(session, asset_id=asset_id, reviewer="checker")

    return writer


def learning_writer() -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await publish_cross_project_aggregates(session)

    return writer


def forecast_writer(world: dict[str, Any]) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        repo = CostForecastRepository(session, world["ctx"])
        return await repo.generate_forecast(
            project_id=world["project"],
            assumptions=_assumptions(),
            model_plans=(ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),),
            price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
            forecast_ci_minutes_today=10,
            as_of=_AS_OF,
            actor="s83-a3",
        )

    return writer


def export_fresh_writer(ctx: TenantContext, pack_id: uuid.UUID) -> Writer:
    """Each call mints a fresh idempotency key so two export records can coexist."""

    async def writer(session: AsyncSession) -> Any:
        return await export_keyed_writer(ctx, pack_id, unique("epr"))(session)

    return writer


def pack_writer(world: dict[str, Any]) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        packs = EvidencePackRepository(session, world["ctx"])
        checkpoint = world["checkpoint"]
        refs = (world["source_ref"],)
        inventories = _zero_inventories()
        core = assemble_core(
            project_id=world["project"],
            release_candidate_id=world["candidate"],
            release_ref_digest="sha256:" + "a" * 64,
            generated_at=checkpoint.created_at,
            frozen_at=world["frozen_at"],
            artifact_scope_digest="sha256:" + "b" * 64,
            issue_binding_digest=digest_bytes(canonical_json_bytes([])),
            source_refs=refs,
            inventories=inventories,
            traceability=(),
            audit_checkpoint=checkpoint,
            repo_commit_binding=derive_repo_commit_binding([]),
        )
        return await packs._persist_core(
            project_id=world["project"],
            release_candidate_id=world["candidate"],
            core=core,
            source_refs=refs,
            inventories=inventories,
            traceability_edge_count=0,
            actor="s83-a3",
        )

    return writer


async def seed_forecast_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Frozen candidate + pack + budget + ledger + policy so ``generate_forecast`` succeeds."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    frozen_at = _AS_OF - timedelta(days=1)
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        candidate = (
            await session.execute(
                text(
                    "INSERT INTO release_candidates "
                    "(tenant_id,project_id,release_ref,status) "
                    "VALUES (:t,:p,:r,'draft') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "r": f"fc-{world['sfx']}"},
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE release_candidates SET status='frozen',frozen_at=:f WHERE id=:c"),
            {"c": candidate, "f": frozen_at},
        )
        await session.execute(text("SELECT * FROM audit_append('s83','seed',NULL,'{}'::jsonb)"))
        packs = EvidencePackRepository(session, ctx)
        checkpoint = await packs.record_audit_checkpoint()
        inventories = _zero_inventories()
        core = assemble_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            release_ref_digest="sha256:" + "a" * 64,
            generated_at=checkpoint.created_at,
            frozen_at=frozen_at,
            artifact_scope_digest="sha256:" + "b" * 64,
            issue_binding_digest=digest_bytes(canonical_json_bytes([])),
            source_refs=(),
            inventories=inventories,
            traceability=(),
            audit_checkpoint=checkpoint,
            repo_commit_binding=derive_repo_commit_binding([]),
        )
        pack = await packs._persist_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            core=core,
            source_refs=(),
            inventories=inventories,
            traceability_edge_count=0,
            actor="s83-a3",
        )
        await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="500",
            max_daily_cost_usd="200",
            actor="s83-a3",
        )
        costs = CostEventRepository(session, ctx)
        for component in sorted(COST_COMPONENTS):
            await costs.record(
                project_id=world["project"],
                component=component,
                amount_usd="1",
                actor="s83-a3",
                occurred_at=_AS_OF - timedelta(hours=1),
            )
        await CostForecastRepository(session, ctx).record_policy_version(
            project_id=world["project"],
            payload=_policy_payload(),
            source_label="SENTINEL_POLICY_SOURCE",
            evidence_ref="SENTINEL_POLICY_EVIDENCE",
            actor="s83-a3",
        )
        world["ctx"] = ctx
        world["candidate"] = candidate
        world["pack_id"] = pack.id
        world["frozen_at"] = frozen_at
        await session.commit()
    return world


async def seed_pack_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Frozen candidate with an audit chain so ``_persist_core`` can race."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        candidate = (
            await session.execute(
                text(
                    "INSERT INTO release_candidates "
                    "(tenant_id,project_id,release_ref,status) "
                    "VALUES (:t,:p,:r,'draft') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "r": f"pk-{world['sfx']}"},
            )
        ).scalar_one()
        await session.execute(
            text(
                "UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() "
                "WHERE id=:c"
            ),
            {"c": candidate},
        )
        await session.execute(text("SELECT * FROM audit_append('s83','seed',NULL,'{}'::jsonb)"))
        frozen_at = (
            await session.execute(
                text("SELECT frozen_at FROM release_candidates WHERE id=:c"), {"c": candidate}
            )
        ).scalar_one()
        artifact_id = (
            await session.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,data) "
                    "VALUES (:t,:p,'requirement',:r,'R','{}') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "r": f"REQ-{world['sfx']}"},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO intake_provenance "
                "(tenant_id,project_id,artifact_id,origin) VALUES (:t,:p,:a,'s83')"
            ),
            {"t": world["tenant"], "p": world["project"], "a": artifact_id},
        )
        artifact = await session.get(IntakeArtifact, artifact_id)
        packs = EvidencePackRepository(session, ctx)
        checkpoint = await packs.record_audit_checkpoint()
        world["ctx"] = ctx
        world["candidate"] = candidate
        world["frozen_at"] = frozen_at
        world["checkpoint"] = checkpoint
        world["source_ref"] = project_source_record("intake_artifact", artifact)
        await session.commit()
    return world
