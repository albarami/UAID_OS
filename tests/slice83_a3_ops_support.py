"""Slice 83 commit-12 helpers: ops-domain A3 writers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.agents.registry import register_blueprint, register_version
from app.ecosystem.learning_publish import publish_cross_project_aggregates
from app.identity import AuthenticatedActor
from app.release.emergency_control_service import EmergencyControlService
from app.repositories.acceptance_verification import AcceptanceVerificationRepository
from app.repositories.agent_realizations import AgentRealizationRepository
from app.repositories.cost_optimizer import CostOptimizerRepository
from app.repositories.go_live_decisions import GoLiveDecisionRepository
from app.repositories.skills import register_capability
from app.tenancy import TenantContext
from tests.admin_support import seed_gated_policy
from tests.learning_support import (
    CALLER_FLAGS,
    record_cost,
    seed_budgets_on_pairs,
    seed_two_tenant_three_project,
)
from tests.slice83_a1_ledger_support import _passed_report
from tests.slice83_a1_support import seed_control_loop, seed_emergency_project
from tests.slice83_a2_c_support import seed_hotfix_incident, seed_stab_world
from tests.slice83_a2_support import observation_writer
from tests.slice83_support import Writer, bind_tenant, component_hashes, seed_org_tenant_project
from tests.test_emergency_controls import _checklist, _policy

SKILL_KEY = "backend_engineering"


def policy_version_id(value: Any) -> Any:
    """Parent identifier from an emergency binding's policy version."""
    return None if value is None else value.policy_version_id


def event_id(value: Any) -> Any:
    """Parent identifier from an emergency-control activate result."""
    return None if value is None else value.event_id


def acceptance_writer(ctx: TenantContext, project_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await AcceptanceVerificationRepository(session, ctx).verify_project(
            project_id, actor="s83-a3"
        )

    return writer


def capability_writer(blueprint_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await register_capability(
            session, blueprint_id=blueprint_id, provided_skills=[SKILL_KEY]
        )

    return writer


def realize_writer(world: dict[str, Any], instance_key: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await AgentRealizationRepository(session, world["ctx"]).realize(
            project_id=world["project"],
            version_id=world["version_id"],
            instance_key=instance_key,
            tool_allowlist=["ci.run_tests"],
            reviewer_blueprint_ids=[world["reviewer_bp"]],
            realized_by="s83-a3",
        )

    return writer


def optimizer_writer(ctx: TenantContext, project_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await CostOptimizerRepository(session, ctx).recommend(
            project_id=project_id,
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            actor="s83-a3",
            routing_flags=CALLER_FLAGS,
        )

    return writer


def activate_writer(world: dict[str, Any], project_id: uuid.UUID, key: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await EmergencyControlService(session, world["ctx"]).activate(
            project_id=project_id, idempotency_key=key
        )

    return writer


def evaluation_for(world: dict[str, Any], cycle_id: uuid.UUID) -> Writer:
    report = _passed_report(world["project"])

    async def writer(session: AsyncSession) -> Any:
        return await GoLiveDecisionRepository(session, world["ctx"]).record_evaluation(
            control_loop_run_id=cycle_id,
            report=report,
            preapproval_gate_eligible=False,
            policy_decision="deny",
            emergency_latch_active=False,
            binding_ids={},
        )

    return writer


def signals_writer(ctx: TenantContext, project_id: uuid.UUID, key: str) -> Writer:
    return observation_writer(ctx, project_id, key)


async def seed_ac_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """One requirement plus one acceptance criterion so verify_project has scope."""
    world = await seed_org_tenant_project(admin_engine)
    async with admin_engine.begin() as conn:
        requirement = (
            await conn.execute(
                text(
                    "INSERT INTO intake_artifacts (tenant_id,project_id,kind,ref,title,data) "
                    "VALUES (:t,:p,'requirement','REQ-A3','Requirement','{}') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO intake_provenance (tenant_id,project_id,artifact_id,origin) "
                "VALUES (:t,:p,:a,'s83')"
            ),
            {"t": world["tenant"], "p": world["project"], "a": requirement},
        )
        ac = (
            await conn.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,data,parent_id) "
                    "VALUES (:t,:p,'acceptance_criterion','AC-A3','AC','{}',:r) RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "r": requirement},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO intake_provenance (tenant_id,project_id,artifact_id,origin) "
                "VALUES (:t,:p,:a,'s83')"
            ),
            {"t": world["tenant"], "p": world["project"], "a": ac},
        )
    world["ctx"] = TenantContext(world["tenant"])
    return world


async def seed_two_blueprints(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Two global blueprints so capability inserts mint distinct parents."""
    sfx = uuid.uuid4().hex[:12]
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        first = await register_blueprint(
            session,
            key=f"s83a3a-{sfx}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-a3",
        )
        second = await register_blueprint(
            session,
            key=f"s83a3b-{sfx}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-a3",
        )
        bp1, bp2 = first.id, second.id
        await session.commit()
    return {"bp1": bp1, "bp2": bp2}


async def seed_realize_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Registered builder version plus a distinct reviewer blueprint."""
    world = await seed_org_tenant_project(admin_engine)
    sfx = world["sfx"]
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        builder = await register_blueprint(
            session,
            key=f"s83a3b-{sfx}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-a3",
        )
        reviewer = await register_blueprint(
            session,
            key=f"s83a3r-{sfx}",
            role="reviewer",
            mission="probe",
            archetype="reviewer",
            actor="s83-a3",
        )
        version = await register_version(
            session,
            blueprint_id=builder.id,
            version_label="v1",
            model_route="fake-a3",
            actor="s83-a3",
            **component_hashes(),
        )
        version_id, reviewer_bp = version.id, reviewer.id
        await session.commit()
    world["version_id"] = version_id
    world["reviewer_bp"] = reviewer_bp
    world["ctx"] = TenantContext(world["tenant"])
    return world


async def seed_optimizer_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Published k-threshold aggregates so recommend() writes citations."""
    async with AsyncSession(admin_engine) as session:
        async with session.begin():
            seeded = await seed_two_tenant_three_project(session)
    await seed_budgets_on_pairs(admin_engine, seeded["pairs"])
    for tenant_id, project_id in seeded["pairs"]:
        await record_cost(
            admin_engine, tenant_id, project_id, component="model_inference", amount="1"
        )
        await record_cost(admin_engine, tenant_id, project_id, component="rework", amount="2")
    async with AsyncSession(admin_engine) as session:
        async with session.begin():
            await publish_cross_project_aggregates(session)
    return {
        "tenant": seeded["t1"],
        "project": seeded["p1"],
        "ctx": TenantContext(seeded["t1"]),
    }


async def seed_two_armed(rls_engine: AsyncEngine, admin_engine: AsyncEngine) -> dict[str, Any]:
    """Two armed projects in one tenant, each with an eligible run."""
    world = await seed_emergency_project(admin_engine)
    sfx = world["sfx"]
    async with admin_engine.begin() as conn:
        second = (
            await conn.execute(
                text("INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P2',:s) RETURNING id"),
                {"t": world["tenant"], "s": f"s83-a3-p2-{sfx}"},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO intake_categories "
                "(tenant_id,project_id,category,status,data,origin) VALUES "
                "(:t,:p,'human_approval_policy','declared',CAST(:policy AS jsonb),'s83'),"
                "(:t,:p,'go_live_checklist','declared',CAST(:checklist AS jsonb),'s83')"
            ),
            {
                "t": world["tenant"],
                "p": second,
                "policy": json.dumps(_policy()),
                "checklist": json.dumps(_checklist()),
            },
        )
        await conn.execute(
            text(
                "INSERT INTO autonomy_policies "
                "(tenant_id,project_id,autonomy_level,overrides) "
                "VALUES (:t,:p,5,'{}'::jsonb)"
            ),
            {"t": world["tenant"], "p": second},
        )
        for project_id in (world["project"], second):
            await conn.execute(
                text(
                    "INSERT INTO project_runs (tenant_id,project_id,status) "
                    "VALUES (:t,:p,'created')"
                ),
                {"t": world["tenant"], "p": project_id},
            )
    world["project2"] = second
    world["ctx"] = TenantContext(
        world["tenant"], actor=AuthenticatedActor("stop-a@example.test", "human")
    )
    async with AsyncSession(rls_engine) as session:
        await bind_tenant(session, world["tenant"])
        service = EmergencyControlService(session, world["ctx"])
        await service.bind(project_id=world["project"], idempotency_key="s83-a3-bind-a")
        await service.bind(project_id=second, idempotency_key="s83-a3-bind-b")
        await session.commit()
    return world


async def seed_two_cycles(rls_engine: AsyncEngine, admin_engine: AsyncEngine) -> dict[str, Any]:
    """Two control-loop cycles so two evaluations can both commit."""
    world = await seed_control_loop(rls_engine, admin_engine)
    async with AsyncSession(rls_engine) as session:
        await bind_tenant(session, world["tenant"])
        second = await GoLiveDecisionRepository(session, world["ctx"]).start_cycle(
            project_id=world["project"],
            project_run_id=world["run"],
            idempotency_key=f"s83-loop-b-{world['sfx']}",
        )
        world["cycle2"] = second.id
        await session.commit()
    return world


async def seed_hotfix_a2(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Evaluable incident plus A2 so evaluate() writes local plans."""
    world = await seed_hotfix_incident(admin_engine)
    async with AsyncSession(admin_engine) as session:
        await bind_tenant(session, world["tenant"])
        await seed_gated_policy(
            session=session,
            ctx=world["ctx"],
            project_id=world["project"],
            autonomy_level=2,
            session_is_admin=True,
        )
        await session.commit()
    return world


async def seed_incident_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Open incident with no ticket so evaluate_now does not hit the ticket unique."""
    return await seed_hotfix_incident(admin_engine)


async def seed_stab(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Declared window, no assessment yet."""
    return await seed_stab_world(admin_engine)
