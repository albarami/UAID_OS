"""Slice 62 global-table guard refusals and mutation probes (admin)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.learning import BUCKET_KEYS_BY_CLASS
from app.ecosystem.learning_publish import publish_cross_project_aggregates
from tests.learning_support import (
    learning_world,
    record_cost,
    seed_two_tenant_three_project,
    set_constraints_immediate,
    set_trigger,
    trigger_enabled,
)

_COUNTS = "cross_project_aggregate_buckets_counts_match"
_CARD_RUN = "cross_project_aggregate_runs_cardinality"
_CARD_BUCK = "cross_project_aggregate_buckets_cardinality"
_PUB = "cross_project_aggregate_runs_published_count"


async def _publish(engine):
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            return await publish_cross_project_aggregates(session)


async def _parent(session: AsyncSession, *, published: int = 0):
    return (
        await session.execute(
            text(
                "INSERT INTO cross_project_aggregate_runs "
                "(bucket_count, published_bucket_count) VALUES (62, :p) RETURNING id"
            ),
            {"p": published},
        )
    ).scalar_one()


def _unit(signal: str, key: str) -> str:
    if signal != "anonymized_cost_and_latency_benchmarks":
        return "count"
    return "usd" if key.startswith("cost:") else "milliseconds"


async def _insert_universe(
    session: AsyncSession,
    run_id,
    *,
    skip: str | None = None,
    live_cost: tuple[int, int, int, int] | None = None,
) -> int:
    inserted = 0
    for signal, keys in BUCKET_KEYS_BY_CLASS.items():
        for key in keys:
            if skip is not None and f"{signal}:{key}" == skip:
                continue
            n_events = n_projects = n_tenants = 0
            metric = None
            unit = _unit(signal, key)
            if live_cost is not None and key == "cost:model_inference":
                n_events, n_projects, n_tenants, metric_int = live_cost
                metric = metric_int
            await session.execute(
                text(
                    "INSERT INTO cross_project_aggregate_buckets ("
                    "run_id,signal_class,bucket_key,n_events,n_projects,n_tenants,"
                    "metric_sum,metric_unit) VALUES ("
                    ":r,:s,:k,:e,:p,:tn,:m,:u)"
                ),
                {
                    "r": run_id,
                    "s": signal,
                    "k": key,
                    "e": n_events,
                    "p": n_projects,
                    "tn": n_tenants,
                    "m": metric,
                    "u": unit,
                },
            )
            inserted += 1
    return inserted


@pytest.mark.db
async def test_p_forge_counts_and_mutation() -> None:
    async with learning_world() as world:
        async with AsyncSession(world["admin"], expire_on_commit=False) as session:
            await session.begin()
            run_id = await _parent(session)
            with pytest.raises((IntegrityError, DBAPIError), match="counts do not match"):
                await session.execute(
                    text(
                        "INSERT INTO cross_project_aggregate_buckets ("
                        "run_id,signal_class,bucket_key,n_events,n_projects,n_tenants,"
                        "metric_sum,metric_unit) VALUES ("
                        ":r,'anonymized_cost_and_latency_benchmarks',"
                        "'cost:model_inference',3,3,2,3,'usd')"
                    ),
                    {"r": run_id},
                )
                await set_constraints_immediate(session, _COUNTS)
            await session.rollback()

            await session.begin()
            assert await trigger_enabled(session, _COUNTS) == "O"
            await set_trigger(session, "cross_project_aggregate_buckets", _COUNTS, enabled=False)
            run_id = await _parent(session, published=1)
            n = await _insert_universe(session, run_id, live_cost=(3, 3, 2, 3))
            assert n == 62
            await set_constraints_immediate(session, _CARD_RUN, _CARD_BUCK, _PUB)
            await session.commit()
            await session.begin()
            await set_trigger(session, "cross_project_aggregate_buckets", _COUNTS, enabled=True)
            assert await trigger_enabled(session, _COUNTS) == "O"
            await session.commit()


@pytest.mark.db
async def test_p_publisher_literal() -> None:
    async with learning_world() as world:
        async with AsyncSession(world["admin"], expire_on_commit=False) as session:
            await session.begin()
            with pytest.raises((IntegrityError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cross_project_aggregate_runs "
                        "(bucket_count, published_bucket_count, publisher) "
                        "VALUES (62, 0, 'other')"
                    )
                )
            await session.rollback()
            await session.begin()
            run_id = (
                await session.execute(
                    text(
                        "INSERT INTO cross_project_aggregate_runs "
                        "(bucket_count, published_bucket_count, publisher) "
                        "VALUES (62, 0, 'slice62.learning_publish') RETURNING id"
                    )
                )
            ).scalar_one()
            assert run_id is not None
            await session.rollback()


@pytest.mark.db
async def test_p19_universe_and_count() -> None:
    async with learning_world() as world:
        async with AsyncSession(world["admin"], expire_on_commit=False) as session:
            await session.begin()
            with pytest.raises((IntegrityError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cross_project_aggregate_runs "
                        "(bucket_count, published_bucket_count) VALUES (61, 0)"
                    )
                )
            await session.rollback()

            await session.begin()
            run_id = await _parent(session)
            n = await _insert_universe(
                session, run_id, skip="security_safe_statistics:shortcut"
            )
            assert n == 61
            with pytest.raises((IntegrityError, DBAPIError), match="cardinality"):
                await set_constraints_immediate(session, _CARD_RUN, _CARD_BUCK)
            await session.rollback()

            await session.begin()
            assert await trigger_enabled(session, _CARD_RUN) == "O"
            await set_trigger(session, "cross_project_aggregate_runs", _CARD_RUN, enabled=False)
            await set_trigger(
                session, "cross_project_aggregate_buckets", _CARD_BUCK, enabled=False
            )
            run_id = await _parent(session)
            await _insert_universe(session, run_id, skip="security_safe_statistics:shortcut")
            await set_constraints_immediate(session, _CARD_RUN, _CARD_BUCK, _PUB, _COUNTS)
            await session.rollback()
            await session.begin()
            await set_trigger(session, "cross_project_aggregate_runs", _CARD_RUN, enabled=True)
            await set_trigger(
                session, "cross_project_aggregate_buckets", _CARD_BUCK, enabled=True
            )
            assert await trigger_enabled(session, _CARD_RUN) == "O"
            assert await trigger_enabled(session, _CARD_BUCK) == "O"
            await session.rollback()

            await session.begin()
            await set_trigger(session, "cross_project_aggregate_runs", _CARD_RUN, enabled=False)
            await set_trigger(
                session, "cross_project_aggregate_buckets", _CARD_BUCK, enabled=False
            )
            run_id = await _parent(session)
            await _insert_universe(session, run_id)
            with pytest.raises((IntegrityError, DBAPIError)):
                await session.execute(
                    text(
                        "INSERT INTO cross_project_aggregate_buckets ("
                        "run_id,signal_class,bucket_key,n_events,n_projects,n_tenants,"
                        "metric_sum,metric_unit) VALUES ("
                        ":r,'security_safe_statistics','not_a_type',0,0,0,NULL,'count')"
                    ),
                    {"r": run_id},
                )
            await session.rollback()


@pytest.mark.db
async def test_p_pubcount_mutation() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        async with AsyncSession(admin) as session:
            async with session.begin():
                seeded = await seed_two_tenant_three_project(session)
        for tenant_id, project_id in seeded["pairs"]:
            await record_cost(
                admin, tenant_id, project_id, component="model_inference", amount="1"
            )
        await _publish(admin)
        live = (3, 3, 2, 3)
        async with AsyncSession(admin, expire_on_commit=False) as session:
            await session.begin()
            run_id = await _parent(session, published=0)
            await _insert_universe(session, run_id, live_cost=live)
            with pytest.raises((IntegrityError, DBAPIError), match="published_bucket_count"):
                await set_constraints_immediate(session, _PUB)
            await session.rollback()

            await session.begin()
            assert await trigger_enabled(session, _PUB) == "O"
            await set_trigger(session, "cross_project_aggregate_runs", _PUB, enabled=False)
            run_id = await _parent(session, published=0)
            await _insert_universe(session, run_id, live_cost=live)
            await set_constraints_immediate(session, _PUB, _CARD_RUN, _CARD_BUCK, _COUNTS)
            await session.rollback()
            await session.begin()
            await set_trigger(session, "cross_project_aggregate_runs", _PUB, enabled=True)
            assert await trigger_enabled(session, _PUB) == "O"
            await session.rollback()


@pytest.mark.db
async def test_p17_append_only_global() -> None:
    async with learning_world() as world:
        admin = world["admin"]
        await _publish(admin)
        async with AsyncSession(admin, expire_on_commit=False) as session:
            await session.begin()
            for table in (
                "cross_project_aggregate_runs",
                "cross_project_aggregate_buckets",
            ):
                with pytest.raises((IntegrityError, DBAPIError), match="append-only"):
                    await session.execute(text(f"UPDATE {table} SET id = id"))
                await session.rollback()
                await session.begin()
                with pytest.raises((IntegrityError, DBAPIError), match="append-only"):
                    await session.execute(text(f"DELETE FROM {table}"))
                await session.rollback()
                await session.begin()
                with pytest.raises((IntegrityError, DBAPIError), match="append-only"):
                    await session.execute(text(f"TRUNCATE {table} CASCADE"))
                await session.rollback()
                await session.begin()
            await session.rollback()
