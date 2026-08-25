"""Slice 83 commit-10 helpers: remaining A2 writers, sibling unique isolation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.agents.registry import AgentInstanceRepository, register_blueprint, register_version
from app.ops.incidents import IncidentPayload
from app.release.production_approval import idempotency_digest, subject_digest
from app.tenancy import TenantContext
from app.repositories.emergency_controls import EmergencyControlRepository
from app.repositories.extraction import ExtractionRepository
from app.repositories.go_live_decisions import GoLiveDecisionRepository
from app.repositories.ops_hotfix import OpsHotfixRepository
from app.repositories.ops_incidents import OpsIncidentRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.ops_stabilization import OpsStabilizationRepository
from app.repositories.task_contracts import TaskContractRepository
from tests.admin_support import pg_state, seed_gated_policy
from tests.ops_stabilization_support import window_data
from tests.slice83_a1_ledger_support import _passed_report
from tests.slice83_support import (
    READ_COMMITTED,
    SERIALIZABLE,
    Writer,
    assert_integrity_error_on,
    bind_tenant,
    component_hashes,
    run_two_writers,
    seed_org_tenant_project,
)

_DROP: dict[str, str] = {
    "uq_tc_reviewers_triple": (
        "ALTER TABLE public.task_contract_reviewers DROP CONSTRAINT uq_tc_reviewers_triple"
    ),
    "uq_tc_reviewers_registration": (
        "ALTER TABLE public.task_contract_reviewers "
        "DROP CONSTRAINT uq_tc_reviewers_registration CASCADE"
    ),
    "uq_ppa_idempotency": (
        "ALTER TABLE public.production_preapproval_attestations DROP CONSTRAINT uq_ppa_idempotency"
    ),
    "uq_ppa_request": (
        "ALTER TABLE public.production_preapproval_attestations DROP CONSTRAINT uq_ppa_request"
    ),
    "uq_ppr_generic_approval": (
        "ALTER TABLE public.production_preapproval_requests DROP CONSTRAINT uq_ppr_generic_approval"
    ),
    "uq_ppr_idempotency": (
        "ALTER TABLE public.production_preapproval_requests DROP CONSTRAINT uq_ppr_idempotency"
    ),
}
_RESTORE: dict[str, str | tuple[str, ...]] = {
    "uq_tc_reviewers_triple": (
        "ALTER TABLE public.task_contract_reviewers ADD CONSTRAINT uq_tc_reviewers_triple "
        "UNIQUE (task_contract_id, reviewer_instance_id, layer)"
    ),
    "uq_tc_reviewers_registration": (
        "ALTER TABLE public.task_contract_reviewers ADD CONSTRAINT uq_tc_reviewers_registration "
        "UNIQUE (task_contract_id, reviewer_instance_id, layer, project_id, tenant_id)",
        "ALTER TABLE public.review_reports ADD CONSTRAINT registration "
        "FOREIGN KEY (task_contract_id, reviewer_instance_id, layer, project_id, tenant_id) "
        "REFERENCES public.task_contract_reviewers "
        "(task_contract_id, reviewer_instance_id, layer, project_id, tenant_id) "
        "ON DELETE RESTRICT",
    ),
    "uq_ppa_idempotency": (
        "ALTER TABLE public.production_preapproval_attestations "
        "ADD CONSTRAINT uq_ppa_idempotency "
        "UNIQUE (tenant_id, project_id, resolution_idempotency_key_hash)"
    ),
    "uq_ppa_request": (
        "ALTER TABLE public.production_preapproval_attestations "
        "ADD CONSTRAINT uq_ppa_request UNIQUE (request_id)"
    ),
    "uq_ppr_generic_approval": (
        "ALTER TABLE public.production_preapproval_requests "
        "ADD CONSTRAINT uq_ppr_generic_approval UNIQUE (generic_approval_id)"
    ),
    "uq_ppr_idempotency": (
        "ALTER TABLE public.production_preapproval_requests ADD CONSTRAINT uq_ppr_idempotency "
        "UNIQUE (tenant_id, project_id, request_idempotency_key_hash)"
    ),
}


@asynccontextmanager
async def without_uniques(admin_engine: AsyncEngine, names: Sequence[str]) -> AsyncIterator[None]:
    """Drop named unique indexes for one race, then restore them."""
    async with admin_engine.begin() as conn:
        for name in names:
            await conn.execute(text(_DROP[name]))
    try:
        yield
    finally:
        async with admin_engine.begin() as conn:
            for name in names:
                restore = _RESTORE[name]
                statements = restore if isinstance(restore, tuple) else (restore,)
                for statement in statements:
                    await conn.execute(text(statement))


def assert_a2_serializable(result, constraint: str) -> None:
    """A2 GREEN at SERIALIZABLE: one row; loser is 23505 or a retryable abort."""
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.pending_before_commit is True
    if result.w2_error is None:
        return
    code = pg_state(result.w2_error) if isinstance(result.w2_error, Exception) else None
    if code in ("40001", "40P01"):
        return
    assert_integrity_error_on(result.w2_error, constraint)


def binding_idempotency_writer(world: dict[str, Any], key_hash: str) -> Writer:
    actor_hash = subject_digest("stop-a@example.test")

    async def writer(session: AsyncSession) -> Any:
        return await EmergencyControlRepository(session, world["ctx"]).append_binding(
            project_id=world["project"],
            actor_subject_hash=actor_hash,
            actor_type="human",
            idempotency_key_hash=key_hash,
        )

    return writer


def evaluation_writer(world: dict[str, Any]) -> Writer:
    report = _passed_report(world["project"])

    async def writer(session: AsyncSession) -> Any:
        return await GoLiveDecisionRepository(session, world["ctx"]).record_evaluation(
            control_loop_run_id=world["cycle"],
            report=report,
            preapproval_gate_eligible=False,
            policy_decision="deny",
            emergency_latch_active=False,
            binding_ids={},
        )

    return writer


def promote_writer(ctx: TenantContext, proposal_id: uuid.UUID, ref: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=proposal_id, actor="s83-a2", ref=ref
        )

    return writer


def ticket_writer(ctx: TenantContext, project_id: uuid.UUID, incident_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await OpsIncidentRepository(session, ctx).evaluate_now(
            project_id, incident_id, actor="s83-a2"
        )

    return writer


def hotfix_writer(
    ctx: TenantContext, project_id: uuid.UUID, incident_id: uuid.UUID, key: str
) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await OpsHotfixRepository(session, ctx).evaluate(
            project_id, incident_id, actor="s83-a2", idempotency_key=key
        )

    return writer


def stab_writer(ctx: TenantContext, project_id: uuid.UUID, key: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await OpsStabilizationRepository(session, ctx).assess(
            project_id, actor="s83-a2", idempotency_key=key
        )

    return writer


def link_writer(ctx: TenantContext, contract_id: uuid.UUID, artifact_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await TaskContractRepository(session, ctx).add_artifact_link(
            contract_id=contract_id,
            link_kind="source_requirement",
            artifact_id=artifact_id,
            actor="s83-a2",
        )

    return writer


def reviewer_writer(ctx: TenantContext, contract_id: uuid.UUID, reviewer_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await TaskContractRepository(session, ctx).add_reviewer(
            contract_id=contract_id,
            reviewer_instance_id=reviewer_id,
            layer="role_specific",
            actor="s83-a2",
        )

    return writer


async def seed_open_incident(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Open incident with no ticket, then ALLOW ``create_project_tasks``."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    payload = IncidentPayload(category="availability", severity="low", summary="s83 a2 ticket")
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        opened = await OpsIncidentRepository(session, ctx).open(
            world["project"],
            actor="s83-a2",
            payload=payload,
            idempotency_key=f"open-{world['sfx']}",
        )
        assert opened is not None and opened.ticket_id is None
        await seed_gated_policy(
            session=session,
            ctx=ctx,
            project_id=world["project"],
            autonomy_level=1,
            session_is_admin=True,
        )
        await session.commit()
    world["ctx"] = ctx
    world["incident_id"] = opened.id
    return world


async def seed_hotfix_incident(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Open evaluable incident with no hotfix run."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    payload = IncidentPayload(category="availability", severity="low", summary="s83 a2 hotfix")
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        opened = await OpsIncidentRepository(session, ctx).open(
            world["project"],
            actor="s83-a2",
            payload=payload,
            idempotency_key=f"hf-{world['sfx']}",
        )
        await session.commit()
    assert opened is not None
    world["ctx"] = ctx
    world["incident_id"] = opened.id
    return world


async def seed_stab_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Declared stabilization window, no assessment yet."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=world["project"],
            category="operations_observability_support",
            actor="s83-a2",
            data=window_data(),
            origin="s83",
        )
        await session.commit()
    world["ctx"] = ctx
    return world


async def seed_staffed_contract(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Draft contract, distinct-blueprint reviewer, and a requirement artifact."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    sfx = world["sfx"]
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        builder_bp = await register_blueprint(
            session,
            key=f"s83b-{sfx}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-a2",
        )
        reviewer_bp = await register_blueprint(
            session,
            key=f"s83r-{sfx}",
            role="reviewer",
            mission="probe",
            archetype="reviewer",
            actor="s83-a2",
        )
        builder_ver = await register_version(
            session,
            blueprint_id=builder_bp.id,
            version_label="v1",
            model_route="fake-builder",
            actor="s83-a2",
            **component_hashes("a" * 64),
        )
        reviewer_ver = await register_version(
            session,
            blueprint_id=reviewer_bp.id,
            version_label="v1",
            model_route="fake-reviewer",
            actor="s83-a2",
            **component_hashes("b" * 64),
        )
        instances = AgentInstanceRepository(session, ctx)
        builder = await instances.instantiate(
            project_id=world["project"],
            version_id=builder_ver.id,
            instance_key="builder",
            actor="s83-a2",
        )
        reviewer = await instances.instantiate(
            project_id=world["project"],
            version_id=reviewer_ver.id,
            instance_key="reviewer",
            actor="s83-a2",
        )
        contract = await TaskContractRepository(session, ctx).create(
            builder_instance_id=builder.id,
            task_ref=f"T-{sfx}",
            title="Slice 83 A2 contract",
            description="Independent-insert race for links and reviewers.",
            must_have=["one"],
            must_not_do=["two"],
            required_evidence=["three"],
            definition_of_done=["four"],
            allowed_tools=["ci.run_tests"],
            forbidden_tools=[],
            risk_level="low",
            created_by="s83-a2",
        )
        requirement = (
            await session.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,data) "
                    "VALUES (:t,:p,'requirement','REQ-S83A2','R','{}') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO intake_provenance "
                "(tenant_id,project_id,artifact_id,origin) VALUES (:t,:p,:a,'s83')"
            ),
            {"t": world["tenant"], "p": world["project"], "a": requirement},
        )
        world["ctx"] = ctx
        world["contract_id"] = contract.id
        world["reviewer_id"] = reviewer.id
        world["requirement_id"] = requirement
        await session.commit()
    return world


async def commit_serializable(engine: AsyncEngine, tenant_id: uuid.UUID, writer: Writer) -> Any:
    """Commit one SERIALIZABLE writer so a later ``record_evaluation`` race is pre-seeded."""
    conn = await engine.connect()
    await conn.execution_options(isolation_level=SERIALIZABLE)
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        await bind_tenant(session, tenant_id)
        value = await writer(session)
        await trans.commit()
        return value
    except BaseException:
        await trans.rollback()
        raise
    finally:
        await session.close()
        await conn.close()


async def race_pair(
    *,
    rls_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    tenant_id: uuid.UUID,
    writer: Writer,
    writer_w2: Writer,
    count_sql: str,
    count_params: dict[str, Any],
):
    """Two runtime sessions with distinct writer closures (same collision key)."""
    return await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=tenant_id,
        writer=writer,
        writer_w2=writer_w2,
        count_sql=count_sql,
        count_params=count_params,
    )


async def race_serializable(
    *,
    rls_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    tenant_id: uuid.UUID,
    writer: Writer,
    count_sql: str,
    count_params: dict[str, Any],
):
    """Two runtime sessions at SERIALIZABLE for ``record_evaluation``."""
    return await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=SERIALIZABLE,
        tenant_id=tenant_id,
        writer=writer,
        count_sql=count_sql,
        count_params=count_params,
    )


def emergency_hash(key: str) -> str:
    return idempotency_digest(key)
