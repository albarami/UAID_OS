"""Slice 83 commit-9 helpers: A2 GREEN contract, pre-seed mutation, writer factories."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.admin.tenant_admin import grant_admin_role
from app.agents.registry import AgentInstanceRepository, register_blueprint, register_version
from app.agents.skills import SKILL_CATEGORIES
from app.cost import evaluate_stop
from app.ops.assessment import build_assessment
from app.ops.incidents import IncidentPayload
from app.ops.signals import CostObservation, compute_counters, utc_midnight
from app.repositories.catalog_admin import list_asset, record_contract_test, register_connector
from app.repositories.cost import CostEventRepository
from app.repositories.documents import DocumentRepository
from app.repositories.go_live_decisions import GoLiveDecisionRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.ops_incidents import OpsIncidentRepository
from app.repositories.ops_signals import OpsSignalRepository
from app.repositories.projects import ProjectRepository
from app.repositories.release_candidates import ReleaseCandidateRepository
from app.repositories.release_issues import ReleaseIssueRepository
from app.repositories.skills import register_skill
from app.repositories.task_contracts import TaskContractRepository
from app.runtime.checkpointer import UAIDCheckpointer
from app.tenancy import TenantContext
from tests.ecosystem_catalog_support import real_connector_specs, unique
from tests.slice83_support import (
    READ_COMMITTED,
    TwoWriterResult,
    Writer,
    assert_integrity_error_on,
    assert_no_integrity_error,
    bind_tenant,
    component_hashes,
    run_two_writers,
    seed_org_tenant_project,
)
from tests.test_runtime import _ckpt

HASH = "sha256:" + "ab" * 32


def assert_a2_green(result: TwoWriterResult, constraint: str, *, reconciles: bool = False) -> None:
    """A2 GREEN: one row; loser is 23505 or an already-reconciling winner; no deadlock."""
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.pending_before_commit is True
    if reconciles:
        assert_no_integrity_error(result)
        return
    assert_integrity_error_on(result.w2_error, constraint)


async def commit_writer(engine: AsyncEngine, tenant_id: uuid.UUID | None, writer: Writer) -> Any:
    """Commit one writer so a later race is pre-seeded (A2 mutation)."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        if tenant_id is not None:
            await bind_tenant(session, tenant_id)
        value = await writer(session)
        await session.commit()
        return value


async def assert_preseed_breaks_green(
    race: Callable[[], Coroutine[Any, Any, TwoWriterResult]],
    constraint: str,
    *,
    reconciles: bool = False,
) -> None:
    """Pre-seeded race must not satisfy A2 GREEN (absent-read is load-bearing)."""
    try:
        result = await race()
    except IntegrityError:
        return
    held = True
    try:
        assert_a2_green(result, constraint, reconciles=reconciles)
    except AssertionError:
        held = False
    assert held is False, "pre-seeded race still satisfied A2 GREEN"


async def race_runtime(
    *,
    rls_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    tenant_id: uuid.UUID,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
) -> TwoWriterResult:
    """Two runtime sessions, READ COMMITTED, absent-read barrier."""
    return await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=tenant_id,
        writer=writer,
        count_sql=count_sql,
        count_params=count_params,
    )


async def seed_version_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Committed project plus one registered agent version."""
    world = await seed_org_tenant_project(admin_engine)
    async with AsyncSession(admin_engine) as session:
        blueprint = await register_blueprint(
            session,
            key=f"s83a2-{uuid.uuid4().hex[:12]}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-a2",
        )
        version = await register_version(
            session,
            blueprint_id=blueprint.id,
            version_label="v1",
            model_route="fake",
            actor="s83-a2",
            **component_hashes(),
        )
        world["version_id"] = version.id
        await session.commit()
    return world


async def seed_run_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Committed project plus one ``project_runs`` row."""
    world = await seed_org_tenant_project(admin_engine)
    async with admin_engine.begin() as conn:
        world["run"] = (
            await conn.execute(
                text(
                    "INSERT INTO project_runs (tenant_id,project_id,status) "
                    "VALUES (:t,:p,'created') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
    return world


async def seed_listed_asset_inputs(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Registered connector + passing contract test; no listing yet."""
    spec = real_connector_specs()["pm"]
    key = unique("pm")
    async with AsyncSession(admin_engine) as session:
        asset = await register_connector(
            session,
            asset_key=key,
            version_label="v1",
            registered_by="s83-a2",
            protocol_module=spec.protocol_module,
            protocol_name=spec.protocol_name,
            fake_name=spec.fake_name,
            service_module=spec.service_module,
            live_adapter_status=spec.live_adapter_status,
            live_adapter_name=spec.live_adapter_name,
            tool_names=list(spec.tool_names),
        )
        vetting = await record_contract_test(session, asset_id=asset.id, reviewer="s83-a2")
        seeded = {"asset_id": asset.id, "vetting_id": vetting.id, "asset_key": key}
        await session.commit()
        return seeded


def projects_writer(ctx: TenantContext, slug: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        row = await ProjectRepository(session, ctx).create(name="s83", slug=slug)
        await session.flush()
        return row

    return writer


def skills_writer(key: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        await register_skill(session, key=key, category=SKILL_CATEGORIES[0], description="s83")
        return key

    return writer


def grant_writer(tenant_id: uuid.UUID, principal: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await grant_admin_role(
            session,
            tenant_id=tenant_id,
            principal_subject=principal,
            admin_role="tenant_viewer",
            performed_by="s83-operator@example.test",
        )

    return writer


def documents_writer(ctx: TenantContext, project_id: uuid.UUID, body: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await DocumentRepository(session, ctx).ingest(
            project_id=project_id,
            filename="s83.txt",
            content_type="text/plain",
            source="manual",
            content=body,
            actor="s83-a2",
        )

    return writer


def cost_writer(ctx: TenantContext, project_id: uuid.UUID, external_ref: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await CostEventRepository(session, ctx).record(
            project_id=project_id,
            component="model_inference",
            amount_usd="1",
            source_system="s83",
            external_ref=external_ref,
            actor="s83-a2",
        )

    return writer


def category_writer(ctx: TenantContext, project_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await IntakeCategoryRepository(session, ctx).declare(
            project_id=project_id,
            category="human_approval_policy",
            actor="s83-a2",
            origin="planner",
        )

    return writer


def candidate_writer(ctx: TenantContext, project_id: uuid.UUID, ref: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await ReleaseCandidateRepository(session, ctx).create(
            project_id=project_id, payload={"release_ref": ref}, actor="s83-a2"
        )

    return writer


def instance_writer(
    ctx: TenantContext, project_id: uuid.UUID, version_id: uuid.UUID, key: str
) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await AgentInstanceRepository(session, ctx).instantiate(
            project_id=project_id, version_id=version_id, instance_key=key, actor="s83-a2"
        )

    return writer


def contract_writer(ctx: TenantContext, builder_id: uuid.UUID, task_ref: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await TaskContractRepository(session, ctx).create(
            builder_instance_id=builder_id,
            task_ref=task_ref,
            title="Slice 83 A2 contract",
            description="Independent-insert race for task_ref.",
            must_have=["one"],
            must_not_do=["two"],
            required_evidence=["three"],
            definition_of_done=["four"],
            allowed_tools=["ci.run_tests"],
            forbidden_tools=[],
            risk_level="low",
            created_by="s83-a2",
        )

    return writer


def cycle_writer(ctx: TenantContext, project_id: uuid.UUID, run_id: uuid.UUID, key: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await GoLiveDecisionRepository(session, ctx).start_cycle(
            project_id=project_id, project_run_id=run_id, idempotency_key=key
        )

    return writer


def incident_writer(ctx: TenantContext, project_id: uuid.UUID, key: str) -> Writer:
    payload = IncidentPayload(category="availability", severity="low", summary="s83 a2 incident")

    async def writer(session: AsyncSession) -> Any:
        return await OpsIncidentRepository(session, ctx).open(
            project_id, actor="s83-a2", payload=payload, idempotency_key=key
        )

    return writer


def observation_writer(ctx: TenantContext, project_id: uuid.UUID, key: str) -> Writer:
    as_of = datetime.now(UTC)
    spent = Decimal("0")
    cost = CostObservation(
        total_spent=spent,
        daily_spent=spent,
        utc_midnight=utc_midnight(as_of),
        budget=None,
        decision=evaluate_stop(total_spent=spent, daily_spent=spent, budget=None),
    )
    rows = build_assessment(project_id=project_id, as_of=as_of, failed_run_ids=(), cost=cost)
    counters = compute_counters(rows)

    async def writer(session: AsyncSession) -> Any:
        return await OpsSignalRepository(session, ctx).record_run(
            project_id=project_id,
            idempotency_key=key,
            request_digest=HASH,
            input_digest=HASH,
            as_of=as_of,
            observed_count=counters.observed_count,
            caller_supplied_count=counters.caller_supplied_count,
            not_observed_count=counters.not_observed_count,
            breached_count=counters.breached_count,
            rows=rows,
            actor="s83-a2",
        )

    return writer


def connector_writer(asset_key: str) -> Writer:
    spec = real_connector_specs()["pm"]

    async def writer(session: AsyncSession) -> Any:
        return await register_connector(
            session,
            asset_key=asset_key,
            version_label="v1",
            registered_by="s83-a2",
            protocol_module=spec.protocol_module,
            protocol_name=spec.protocol_name,
            fake_name=spec.fake_name,
            service_module=spec.service_module,
            live_adapter_status=spec.live_adapter_status,
            live_adapter_name=spec.live_adapter_name,
            tool_names=list(spec.tool_names),
        )

    return writer


def listing_writer(asset_id: uuid.UUID, vetting_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await list_asset(
            session,
            asset_id=asset_id,
            vetting_record_id=vetting_id,
            listed_by="s83-a2",
        )

    return writer


def checkpoint_writer(world: dict[str, Any]) -> Writer:
    cfg = cast(
        RunnableConfig,
        {
            "configurable": {
                "thread_id": str(world["run"]),
                "checkpoint_ns": "",
                "checkpoint_id": "a2-cp",
            }
        },
    )

    async def writer(session: AsyncSession) -> Any:
        cp = UAIDCheckpointer(
            session, world["ctx"], project_id=world["project"], run_id=world["run"]
        )
        return await cp.aput(
            cfg,
            cast(Any, _ckpt("a2-cp", {"x": 1})),
            {"source": "input", "step": 0},
            {},
        )

    return writer


async def seed_binding_world(rls_engine: AsyncEngine, admin_engine: AsyncEngine) -> dict[str, Any]:
    """Draft candidate plus one open issue for the binding unique."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(rls_engine) as session:
        await bind_tenant(session, world["tenant"])
        candidate = await ReleaseCandidateRepository(session, ctx).create(
            project_id=world["project"],
            payload={"release_ref": f"rc-{uuid.uuid4().hex[:10]}"},
            actor="s83-a2",
        )
        issue = await ReleaseIssueRepository(session, ctx).create(
            project_id=world["project"],
            payload={
                "issue_category": "cost",
                "severity": "low",
                "blocking": False,
                "summary": "s83 a2 issue",
                "source": "s83",
            },
            actor="s83-a2",
        )
        world["candidate_id"] = candidate.id
        world["issue_id"] = issue.id
        world["ctx"] = ctx
        await session.commit()
    return world


def binding_writer(world: dict[str, Any]) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await ReleaseCandidateRepository(session, world["ctx"]).bind_issue(
            candidate_id=world["candidate_id"],
            release_issue_id=world["issue_id"],
            actor="s83-a2",
        )

    return writer
