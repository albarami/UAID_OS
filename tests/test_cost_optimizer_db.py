"""Slice 62 tenant-path optimizer DB probes."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.cost_optimizer import CostOptimizerError
from app.ecosystem.learning_publish import publish_cross_project_aggregates
from app.intake.readiness import RULESET_VERSION
from app.release.production_autonomy import A5_RULESET_VERSION
from app.repositories.cost_forecasts import CostForecastRepository
from app.repositories.cost_optimizer import CostOptimizerRepository
from app.repositories.production_autonomy import ProductionAutonomyRepository
from app.repositories.readiness import ReadinessRepository
from app.tenancy import TenantContext
from tests.learning_support import (
    CALLER_FLAGS,
    learning_world,
    policy_payload,
    record_cost,
    scoped,
    seed_budgets_on_pairs,
    seed_two_tenant_three_project,
    upsert_budget,
)

async def _publish(engine):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            return await publish_cross_project_aggregates(session)


async def _recommend(engine, tenant_id, project_id, **kwargs):
    ctx = TenantContext(tenant_id)
    async with scoped(engine, ctx) as session:
        return await CostOptimizerRepository(session, ctx).recommend(
            project_id=project_id,
            actor="tester",
            **kwargs,
        )


@pytest.mark.db
async def test_p_opt_learn_db_and_cite_and_p12() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await seed_budgets_on_pairs(admin, seeded["pairs"])
        for tenant_id, project_id in seeded["pairs"]:
            await record_cost(
                admin, tenant_id, project_id, component="model_inference", amount="1"
            )
            await record_cost(admin, tenant_id, project_id, component="rework", amount="2")
        report = await _publish(admin)
        run = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        assert run.recommended_tier == "mid_quality"
        assert run.overlay_applied == "rework_intensity_bump"
        assert run.citation_count == 2
        assert run.aggregate_run_id == report.run_id
        async with scoped(rls, TenantContext(seeded["t1"])) as session:
            keys = {
                row[0]
                for row in (
                    await session.execute(
                        text(
                            "SELECT v.bucket_key FROM cost_optimizer_citations c "
                            "JOIN cross_project_published_buckets v ON v.id = c.bucket_id "
                            "WHERE c.run_id = :r"
                        ),
                        {"r": run.id},
                    )
                ).all()
            }
            assert keys == {"cost:rework", "cost:model_inference"}
            assert run.tenant_id == seeded["t1"]

        other = await _recommend(
            rls,
            seeded["t2"],
            seeded["p3"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        assert other.aggregate_run_id == report.run_id
        assert other.tenant_id == seeded["t2"]
        assert other.tenant_id != run.tenant_id

        for tenant_id, project_id in seeded["pairs"]:
            await record_cost(
                admin, tenant_id, project_id, component="model_inference", amount="10"
            )
        await _publish(admin)
        low = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        assert low.overlay_applied == "none"
        assert low.recommended_tier != "hold"


@pytest.mark.db
async def test_p13_flags_and_p13b_source() -> None:
    assert "max_total_model_cost_usd" not in Path("app/repositories/cost_optimizer.py").read_text()
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await upsert_budget(admin, seeded["t1"], seeded["p1"])
        with pytest.raises(CostOptimizerError, match="no_routing_flags"):
            await _recommend(
                rls,
                seeded["t1"],
                seeded["p1"],
                task_class="code_review",
                risk_level="low",
                ambiguity_high=False,
            )
        caller = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        assert caller.flags_source == "caller_supplied"
        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            policy = await CostForecastRepository(session, ctx).record_policy_version(
                project_id=seeded["p1"],
                payload=policy_payload(cheap_first=False, frontier=True, cached=True),
                source_label="s62",
                evidence_ref=None,
                actor="seed",
            )
        recorded = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
        )
        assert recorded.flags_source == "recorded_cost_policy"
        assert recorded.policy_version_id == policy.id
        assert recorded.cheap_first_for_low_risk is False
        assert recorded.frontier_for_high_risk is True


@pytest.mark.db
async def test_p14_own_stop_not_global() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await upsert_budget(admin, seeded["t1"], seeded["p1"], total="1", daily="1")
        await record_cost(admin, seeded["t1"], seeded["p1"], component="model_inference", amount="1")
        await upsert_budget(admin, seeded["t2"], seeded["p3"], total="100", daily="100")
        held = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        assert held.recommended_tier == "hold"
        assert held.overlay_applied == "budget_hold"
        open_run = await _recommend(
            rls,
            seeded["t2"],
            seeded["p3"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        assert open_run.recommended_tier != "hold"
        assert open_run.overlay_applied != "budget_hold"


@pytest.mark.db
async def test_p15_p16_real_a5_readiness_bit_stable() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await upsert_budget(admin, seeded["t1"], seeded["p1"])
        ctx = TenantContext(seeded["t1"])
        async with scoped(admin, ctx) as session:
            before_a5 = (
                await ProductionAutonomyRepository(session, ctx).evaluate(seeded["p1"])
            ).to_dict()
            before_ready = (
                await ReadinessRepository(session, ctx).evaluate(seeded["p1"])
            ).to_dict()
        await record_cost(admin, seeded["t1"], seeded["p1"], component="model_inference", amount="1")
        await _publish(admin)
        after_run = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        async with scoped(admin, ctx) as session:
            after_a5 = (
                await ProductionAutonomyRepository(session, ctx).evaluate(seeded["p1"])
            ).to_dict()
            after_ready = (
                await ReadinessRepository(session, ctx).evaluate(seeded["p1"])
            ).to_dict()
        assert before_a5["a5_satisfied"] == after_a5["a5_satisfied"]
        assert before_a5["can_go_live_autonomously"] is after_a5["can_go_live_autonomously"] is False
        assert before_a5["ruleset_version"] == after_a5["ruleset_version"] == A5_RULESET_VERSION
        assert [g["status"] for g in before_a5["gates"]] == [g["status"] for g in after_a5["gates"]]
        assert before_ready["readiness_level"] == after_ready["readiness_level"]
        assert before_ready["ruleset_version"] == after_ready["ruleset_version"] == RULESET_VERSION
        assert after_run.recommended_tier is not None


@pytest.mark.db
async def test_p18_rls_cross_tenant() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await upsert_budget(admin, seeded["t1"], seeded["p1"])
        await upsert_budget(admin, seeded["t2"], seeded["p3"])
        run_a = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            routing_flags=CALLER_FLAGS,
        )
        async with scoped(rls, TenantContext(seeded["t2"])) as session:
            seen = (
                await session.execute(
                    text("SELECT count(*) FROM cost_optimizer_runs WHERE id=:i"),
                    {"i": run_a.id},
                )
            ).scalar_one()
            assert seen == 0


@pytest.mark.db
async def test_p_cite_uaid_app_tool_deny() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await seed_budgets_on_pairs(admin, seeded["pairs"])
        for tenant_id, project_id in seeded["pairs"]:
            async with scoped(admin, TenantContext(tenant_id)) as session:
                await session.execute(
                    text(
                        "INSERT INTO tool_calls "
                        "(tenant_id,project_id,agent_id,tool_name,decision) VALUES "
                        "(:t,:p,'a','pm.read_issues','denied_policy'),"
                        "(:t,:p,'a','pm.read_issues','allowed_unverified_identity')"
                    ),
                    {"t": tenant_id, "p": project_id},
                )
        report = await _publish(admin)
        rec = await _recommend(
            rls,
            seeded["t1"],
            seeded["p1"],
            task_class="code_review",
            risk_level="low",
            ambiguity_high=False,
            tool_name="pm.read_issues",
            routing_flags=CALLER_FLAGS,
        )
        assert rec.overlay_applied == "tool_deny_hold"
        assert rec.citation_count == 1
        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            bucket_id = (
                await session.execute(
                    text(
                        "SELECT id FROM cross_project_published_buckets "
                        "WHERE run_id=:r AND bucket_key='pm.read_issues'"
                    ),
                    {"r": report.run_id},
                )
            ).scalar_one()
            from tests.learning_support import insert_optimizer_sql, set_constraints_immediate

            parent = await insert_optimizer_sql(
                session,
                tenant_id=seeded["t1"],
                project_id=seeded["p1"],
                overlay="tool_deny_hold",
                recommended="hold",
                citation_count=1,
                tool_name="pm.read_issues",
                aggregate_run_id=report.run_id,
                published_bucket_count=report.published_bucket_count,
                clamped="cost_efficient",
                base="mid_quality",
            )
            await session.execute(
                text(
                    "INSERT INTO cost_optimizer_citations "
                    "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                ),
                {"t": seeded["t1"], "p": seeded["p1"], "r": parent, "b": bucket_id},
            )
            await set_constraints_immediate(
                session,
                "cost_optimizer_runs_citations_guard",
                "cost_optimizer_citations_row_guard",
            )
