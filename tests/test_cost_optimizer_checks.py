"""Slice 62 optimizer CHECK and citation-guard probes (uaid_app where required)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.learning_publish import publish_cross_project_aggregates
from app.repositories.cost_forecasts import CostForecastRepository
from app.tenancy import TenantContext
from tests.learning_support import (
    insert_optimizer_sql,
    learning_world,
    policy_payload,
    record_cost,
    scoped,
    seed_budgets_on_pairs,
    seed_two_tenant_three_project,
    set_constraints_immediate,
    upsert_budget,
)

_PARENT = "cost_optimizer_runs_citations_guard"
_ROW = "cost_optimizer_citations_row_guard"
_FLAGS = "cost_optimizer_runs_policy_flags_match"


async def _publish_real(engine):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            return await publish_cross_project_aggregates(session)


async def _seed_published(admin):
    async with AsyncSession(admin) as session:
        async with session.begin():
            seeded = await seed_two_tenant_three_project(session)
    await seed_budgets_on_pairs(admin, seeded["pairs"])
    for tenant_id, project_id in seeded["pairs"]:
        await record_cost(admin, tenant_id, project_id, component="model_inference", amount="1")
        await record_cost(admin, tenant_id, project_id, component="rework", amount="2")
    report = await _publish_real(admin)
    return seeded, report


async def _toggle(engine, table: str, name: str, *, enabled: bool) -> None:
    verb = "ENABLE" if enabled else "DISABLE"
    async with engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {table} {verb} TRIGGER {name}"))


async def _tgenabled(engine, name: str) -> str:
    async with engine.connect() as conn:
        value = (
            await conn.execute(text("SELECT tgenabled FROM pg_trigger WHERE tgname=:n"), {"n": name})
        ).scalar_one()
    return value.decode() if isinstance(value, bytes) else str(value)


@pytest.mark.db
async def test_p_cite_parent_zero() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        seeded, report = await _seed_published(admin)
        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError), match="citation count"):
                await insert_optimizer_sql(
                    session,
                    tenant_id=seeded["t1"],
                    project_id=seeded["p1"],
                    overlay="rework_intensity_bump",
                    recommended="mid_quality",
                    citation_count=2,
                    clamped="cost_efficient",
                    base="mid_quality",
                    aggregate_run_id=report.run_id,
                    published_bucket_count=report.published_bucket_count,
                )
                await set_constraints_immediate(session, _PARENT)
        await _toggle(admin, "cost_optimizer_runs", _PARENT, enabled=False)
        try:
            async with scoped(rls, ctx) as session:
                parent = await insert_optimizer_sql(
                    session,
                    tenant_id=seeded["t1"],
                    project_id=seeded["p1"],
                    overlay="rework_intensity_bump",
                    recommended="mid_quality",
                    citation_count=2,
                    clamped="cost_efficient",
                    base="mid_quality",
                    aggregate_run_id=report.run_id,
                    published_bucket_count=report.published_bucket_count,
                )
                await set_constraints_immediate(session, _PARENT)
                assert parent is not None
        finally:
            await _toggle(admin, "cost_optimizer_runs", _PARENT, enabled=True)
        assert await _tgenabled(admin, _PARENT) == "O"


@pytest.mark.db
async def test_p_cite_late_child() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        seeded, report = await _seed_published(admin)
        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            parent = await insert_optimizer_sql(
                session,
                tenant_id=seeded["t1"],
                project_id=seeded["p1"],
                overlay="none",
                recommended="cost_efficient",
                citation_count=0,
                aggregate_run_id=report.run_id,
                published_bucket_count=report.published_bucket_count,
                clamped="cost_efficient",
                base="mid_quality",
            )
            await set_constraints_immediate(session, _PARENT)
            bucket_id = (
                await session.execute(
                    text(
                        "SELECT id FROM cross_project_published_buckets "
                        "WHERE run_id=:r AND bucket_key='cost:rework'"
                    ),
                    {"r": report.run_id},
                )
            ).scalar_one()
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded["t1"], "p": seeded["p1"], "r": parent, "b": bucket_id},
                )
                await set_constraints_immediate(session, _ROW)
        await _toggle(admin, "cost_optimizer_citations", _ROW, enabled=False)
        try:
            async with scoped(rls, ctx) as session:
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded["t1"], "p": seeded["p1"], "r": parent, "b": bucket_id},
                )
                await set_constraints_immediate(session, _ROW)
        finally:
            await _toggle(admin, "cost_optimizer_citations", _ROW, enabled=True)
        assert await _tgenabled(admin, _ROW) == "O"


@pytest.mark.db
async def test_p_cite_unpublished_and_stale() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        empty = await _publish_real(admin)
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await upsert_budget(admin, seeded["t1"], seeded["p1"])
        unpublished = None
        async with AsyncSession(admin) as session:
            unpublished = (
                await session.execute(
                    text(
                        "SELECT id FROM cross_project_aggregate_buckets "
                        "WHERE run_id=:r AND bucket_key='cost:model_inference'"
                    ),
                    {"r": empty.run_id},
                )
            ).scalar_one()
        ctx = TenantContext(seeded["t1"])
        await _toggle(admin, "cost_optimizer_runs", _PARENT, enabled=False)
        try:
            async with scoped(rls, ctx) as session:
                parent = await insert_optimizer_sql(
                    session,
                    tenant_id=seeded["t1"],
                    project_id=seeded["p1"],
                    overlay="tool_deny_hold",
                    recommended="hold",
                    citation_count=1,
                    tool_name="pm.read_issues",
                    aggregate_run_id=empty.run_id,
                    published_bucket_count=0,
                    clamped="cost_efficient",
                    base="mid_quality",
                )
                await set_constraints_immediate(session, _PARENT)
        finally:
            await _toggle(admin, "cost_optimizer_runs", _PARENT, enabled=True)
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError), match="not published"):
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded["t1"], "p": seeded["p1"], "r": parent, "b": unpublished},
                )
                await set_constraints_immediate(session, _ROW)
        await _toggle(admin, "cost_optimizer_citations", _ROW, enabled=False)
        try:
            async with scoped(rls, ctx) as session:
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded["t1"], "p": seeded["p1"], "r": parent, "b": unpublished},
                )
                await set_constraints_immediate(session, _ROW)
        finally:
            await _toggle(admin, "cost_optimizer_citations", _ROW, enabled=True)
        assert await _tgenabled(admin, _ROW) == "O"

        seeded2, first = await _seed_published(admin)
        second = await _publish_real(admin)
        stale = None
        async with AsyncSession(admin) as session:
            stale = (
                await session.execute(
                    text(
                        "SELECT id FROM cross_project_aggregate_buckets "
                        "WHERE run_id=:r AND bucket_key='cost:rework' AND published"
                    ),
                    {"r": first.run_id},
                )
            ).scalar_one()
        ctx2 = TenantContext(seeded2["t1"])
        await _toggle(admin, "cost_optimizer_runs", _PARENT, enabled=False)
        try:
            async with scoped(rls, ctx2) as session:
                parent2 = await insert_optimizer_sql(
                    session,
                    tenant_id=seeded2["t1"],
                    project_id=seeded2["p1"],
                    overlay="rework_intensity_bump",
                    recommended="mid_quality",
                    citation_count=2,
                    clamped="cost_efficient",
                    base="mid_quality",
                    aggregate_run_id=second.run_id,
                    published_bucket_count=second.published_bucket_count,
                )
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded2["t1"], "p": seeded2["p1"], "r": parent2, "b": stale},
                )
                current = (
                    await session.execute(
                        text(
                            "SELECT id FROM cross_project_published_buckets "
                            "WHERE run_id=:r AND bucket_key='cost:model_inference'"
                        ),
                        {"r": second.run_id},
                    )
                ).scalar_one()
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded2["t1"], "p": seeded2["p1"], "r": parent2, "b": current},
                )
                with pytest.raises((IntegrityError, DBAPIError), match="not published"):
                    await set_constraints_immediate(session, _PARENT, _ROW)
        finally:
            await _toggle(admin, "cost_optimizer_runs", _PARENT, enabled=True)


@pytest.mark.db
async def test_p_policy_flags_and_judgment_check() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        await upsert_budget(admin, seeded["t1"], seeded["p1"])
        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            policy = await CostForecastRepository(session, ctx).record_policy_version(
                project_id=seeded["p1"],
                payload=policy_payload(cheap_first=True, frontier=True, cached=True),
                source_label="s62",
                evidence_ref=None,
                actor="seed",
            )
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError), match="policy flags"):
                await insert_optimizer_sql(
                    session,
                    tenant_id=seeded["t1"],
                    project_id=seeded["p1"],
                    overlay="none",
                    recommended="cost_efficient",
                    citation_count=0,
                    flags_source="recorded_cost_policy",
                    policy_version_id=policy.id,
                    cheap_first=False,
                    frontier=True,
                    cached=True,
                    clamped="cost_efficient",
                    base="mid_quality",
                )
        await _toggle(admin, "cost_optimizer_runs", _FLAGS, enabled=False)
        try:
            async with scoped(rls, ctx) as session:
                await insert_optimizer_sql(
                    session,
                    tenant_id=seeded["t1"],
                    project_id=seeded["p1"],
                    overlay="none",
                    recommended="cost_efficient",
                    citation_count=0,
                    flags_source="recorded_cost_policy",
                    policy_version_id=policy.id,
                    cheap_first=False,
                    frontier=True,
                    cached=True,
                    clamped="cost_efficient",
                    base="mid_quality",
                )
        finally:
            await _toggle(admin, "cost_optimizer_runs", _FLAGS, enabled=True)
        assert await _tgenabled(admin, _FLAGS) == "O"
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_runs ("
                        "tenant_id,project_id,task_class,risk_level,ambiguity_high,"
                        "cheap_first_for_low_risk,frontier_for_high_risk,"
                        "use_cached_context_when_possible,flags_source,"
                        "base_policy_tier,clamped_policy_tier,recommended_tier,"
                        "overlay_applied,cache_hint,requires_multiple_reviewers,"
                        "requires_model_diversity,published_bucket_count,citation_count"
                        ") VALUES ("
                        ":t,:p,'code_review','low',false,true,false,false,'caller_supplied',"
                        "'mid_quality','cost_efficient','cost_efficient','none',false,"
                        "true,false,0,0)"
                    ),
                    {"t": seeded["t1"], "p": seeded["p1"]},
                )


@pytest.mark.db
async def test_p_overlay_shape_and_append_only() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        seeded, report = await _seed_published(admin)
        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            rework = (
                await session.execute(
                    text(
                        "SELECT id FROM cross_project_published_buckets "
                        "WHERE run_id=:r AND bucket_key='cost:rework'"
                    ),
                    {"r": report.run_id},
                )
            ).scalar_one()
            inference = (
                await session.execute(
                    text(
                        "SELECT id FROM cross_project_published_buckets "
                        "WHERE run_id=:r AND bucket_key='cost:model_inference'"
                    ),
                    {"r": report.run_id},
                )
            ).scalar_one()
            parent = await insert_optimizer_sql(
                session,
                tenant_id=seeded["t1"],
                project_id=seeded["p1"],
                overlay="none",
                recommended="cost_efficient",
                citation_count=0,
                aggregate_run_id=report.run_id,
                published_bucket_count=report.published_bucket_count,
                clamped="cost_efficient",
                base="mid_quality",
            )
            await set_constraints_immediate(session, _PARENT)
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded["t1"], "p": seeded["p1"], "r": parent, "b": rework},
                )
                await set_constraints_immediate(session, _ROW)
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError)):
                bad = await insert_optimizer_sql(
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
                    {"t": seeded["t1"], "p": seeded["p1"], "r": bad, "b": rework},
                )
                await set_constraints_immediate(session, _PARENT, _ROW)
        async with scoped(rls, ctx) as session:
            with pytest.raises((IntegrityError, DBAPIError)):
                bad = await insert_optimizer_sql(
                    session,
                    tenant_id=seeded["t1"],
                    project_id=seeded["p1"],
                    overlay="rework_intensity_bump",
                    recommended="mid_quality",
                    citation_count=2,
                    clamped="cost_efficient",
                    base="mid_quality",
                    aggregate_run_id=report.run_id,
                    published_bucket_count=report.published_bucket_count,
                )
                await session.execute(
                    text(
                        "INSERT INTO cost_optimizer_citations "
                        "(tenant_id,project_id,run_id,bucket_id) VALUES (:t,:p,:r,:b)"
                    ),
                    {"t": seeded["t1"], "p": seeded["p1"], "r": bad, "b": rework},
                )
                await set_constraints_immediate(session, _PARENT, _ROW)
        async with AsyncSession(admin) as session:
            async with session.begin():
                with pytest.raises((IntegrityError, DBAPIError), match="append-only"):
                    await session.execute(text("UPDATE cost_optimizer_runs SET id = id"))
        async with AsyncSession(admin) as session:
            async with session.begin():
                with pytest.raises((IntegrityError, DBAPIError), match="append-only"):
                    await session.execute(text("DELETE FROM cost_optimizer_runs"))
        for table in ("cost_optimizer_citations", "cost_optimizer_runs"):
            async with AsyncSession(admin) as session:
                async with session.begin():
                    with pytest.raises((IntegrityError, DBAPIError), match="append-only"):
                        await session.execute(text(f"TRUNCATE {table} CASCADE"))
        assert inference is not None
