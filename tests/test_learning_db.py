"""Slice 62 publisher DB probes on an isolated empty database."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.learning import EXPECTED_BUCKET_COUNT
from app.ecosystem.learning_publish import publish_cross_project_aggregates
from app.repositories.learning import LearningRepository
from app.tenancy import TenantContext
from tests.learning_support import (
    learning_world,
    record_cost,
    scoped,
    seed_one_tenant_three_project,
    seed_two_tenant_three_project,
)


async def _publish(engine):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            return await publish_cross_project_aggregates(session)


async def _snapshot(engine):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        return await LearningRepository(session).latest_snapshot()


async def _scalar(engine, sql: str, **params):
    async with AsyncSession(engine) as session:
        return (await session.execute(text(sql), params)).scalar()


@pytest.mark.db
async def test_p7_p8_empty_publish() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        assert await _snapshot(admin) is None
        assert await _scalar(admin, "SELECT count(*) FROM cross_project_aggregate_runs") == 0
        report = await _publish(admin)
        snap = await _snapshot(admin)
        assert snap is not None
        assert len(snap.buckets) == EXPECTED_BUCKET_COUNT
        assert report.published_bucket_count == 0
        assert snap.run.published_bucket_count == 0
        assert all(bucket.published is False for bucket in snap.buckets)


@pytest.mark.db
async def test_p9_unpub_view_p10_fn_revoke() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        for tenant_id, project_id in seeded["pairs"]:
            await record_cost(
                admin, tenant_id, project_id, component="model_inference", amount="1"
            )
        await _publish(admin)
        snap = await _snapshot(admin)
        assert snap is not None
        cost_inf = next(
            b
            for b in snap.buckets
            if b.bucket_key == "cost:model_inference"
        )
        assert cost_inf.n_projects == 3
        assert cost_inf.n_tenants == 2
        assert cost_inf.published is True
        assert snap.run.published_bucket_count >= 1
        other_cost = [
            b
            for b in snap.buckets
            if b.bucket_key.startswith("cost:") and b.bucket_key != "cost:model_inference"
        ]
        assert all(b.published is False for b in other_cost)

        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            view_n = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM cross_project_published_buckets "
                        "WHERE bucket_key='cost:model_inference'"
                    )
                )
            ).scalar_one()
            assert view_n == 1
        async with scoped(rls, ctx) as session:
            with pytest.raises((ProgrammingError, DBAPIError)):
                await session.execute(text("SELECT count(*) FROM cross_project_aggregate_buckets"))
        async with scoped(rls, ctx) as session:
            with pytest.raises((ProgrammingError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cross_project_aggregate_runs "
                        "(bucket_count, published_bucket_count) VALUES (62, 0)"
                    )
                )
        async with scoped(rls, ctx) as session:
            run_id = (
                await session.execute(text("SELECT id FROM cross_project_aggregate_runs"))
            ).scalar_one()
            with pytest.raises((ProgrammingError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cross_project_aggregate_buckets ("
                        "run_id,signal_class,bucket_key,n_events,n_projects,n_tenants,"
                        "metric_sum,metric_unit) VALUES ("
                        ":r,'anonymized_cost_and_latency_benchmarks',"
                        "'cost:model_inference',0,0,0,NULL,'usd')"
                    ),
                    {"r": run_id},
                )
        async with scoped(rls, ctx) as session:
            with pytest.raises((ProgrammingError, DBAPIError)):
                await session.execute(
                    text(
                        "SELECT * FROM learning_expected_counts("
                        "'aggregate_eval_failure_rates','builder')"
                    )
                )
        async with scoped(rls, ctx) as session:
            other = (
                await session.execute(
                    text("SELECT count(*) FROM cost_events WHERE tenant_id=:t"),
                    {"t": seeded["t2"]},
                )
            ).scalar_one()
            assert other == 0


@pytest.mark.db
async def test_pk1_and_unpub_hidden() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        rls = world["rls"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_one_tenant_three_project(session)
        for tenant_id, project_id in seeded["pairs"]:
            await record_cost(
                admin, tenant_id, project_id, component="model_inference", amount="1"
            )
        await _publish(admin)
        snap = await _snapshot(admin)
        assert snap is not None
        cost_inf = next(b for b in snap.buckets if b.bucket_key == "cost:model_inference")
        assert cost_inf.n_projects == 3
        assert cost_inf.n_tenants == 1
        assert cost_inf.published is False
        ctx = TenantContext(seeded["t1"])
        async with scoped(rls, ctx) as session:
            view_n = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM cross_project_published_buckets "
                        "WHERE bucket_key='cost:model_inference'"
                    )
                )
            ).scalar_one()
            assert view_n == 0
            with pytest.raises((ProgrammingError, DBAPIError)):
                await session.execute(text("SELECT 1 FROM cross_project_aggregate_buckets LIMIT 1"))


@pytest.mark.db
async def test_p_pub_later_appends() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        for tenant_id, project_id in seeded["pairs"]:
            await record_cost(
                admin, tenant_id, project_id, component="model_inference", amount="1"
            )
        first = await _publish(admin)
        async with AsyncSession(admin) as session:
            async with session.begin():
                extra = (
                    await session.execute(
                        text(
                            "INSERT INTO projects (tenant_id,name,slug) "
                            "VALUES (:t,'p4',:s) RETURNING id"
                        ),
                        {"t": seeded["t2"], "s": f"lrn-p4-{seeded['p3']}"},
                    )
                ).scalar_one()
        await record_cost(admin, seeded["t2"], extra, component="model_inference", amount="1")
        second = await _publish(admin)
        assert first.run_id != second.run_id
        snap1 = None
        async with AsyncSession(admin) as session:
            from app.models.cross_project_aggregate import CrossProjectAggregateBucket
            from sqlalchemy import select

            first_row = (
                await session.execute(
                    select(CrossProjectAggregateBucket).where(
                        CrossProjectAggregateBucket.run_id == first.run_id,
                        CrossProjectAggregateBucket.bucket_key == "cost:model_inference",
                    )
                )
            ).scalar_one()
            latest = (
                await session.execute(
                    select(CrossProjectAggregateBucket).where(
                        CrossProjectAggregateBucket.run_id == second.run_id,
                        CrossProjectAggregateBucket.bucket_key == "cost:model_inference",
                    )
                )
            ).scalar_one()
            snap1 = first_row.n_projects
            assert snap1 == 3
            assert latest.n_projects == 4
            assert first_row.published is True
            assert latest.published is True
