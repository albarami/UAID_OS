"""Slice 56 Alembic 0055 reversibility proofs (empty roundtrip + populated refusal)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from tests.conftest import TEST_ADMIN_URL

_DIGEST = "sha256:" + "ab" * 32
_MISSING = (
    (1, "uptime", "no_uptime_source"),
    (2, "error_rates", "no_error_rate_source"),
    (3, "latency", "no_latency_source"),
    (5, "security_alerts", "no_post_launch_security_alert_source"),
    (6, "user_journey_failures", "no_journey_failure_source"),
    (7, "data_quality_issues", "no_data_quality_source"),
    (9, "model_output_drift", "no_model_drift_source"),
    (10, "support_tickets", "no_support_ticket_source"),
    (11, "incident_reports", "no_incident_store"),
)


@contextmanager
def _alembic_url(url: str) -> Iterator[Config]:
    prior = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield Config("alembic.ini")
    finally:
        if prior is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = prior


async def _admin_connect(database: str = "postgres"):
    url = make_url(TEST_ADMIN_URL)
    return await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=database,
    )


async def _create_database(name: str) -> None:
    conn = await _admin_connect()
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(name: str) -> None:
    conn = await _admin_connect()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


async def _regclass(database: str, table: str) -> str | None:
    conn = await _admin_connect(database)
    try:
        return await conn.fetchval("SELECT to_regclass($1)::text", f"public.{table}")
    finally:
        await conn.close()


async def _seed_complete_run(database: str) -> None:
    conn = await _admin_connect(database)
    try:
        async with conn.transaction():
            org = await conn.fetchval(
                "INSERT INTO organizations (name, slug) VALUES ('OpsMig', $1) RETURNING id",
                f"ops-mig-{uuid.uuid4().hex[:8]}",
            )
            tenant = await conn.fetchval(
                "INSERT INTO tenants (organization_id, name, slug) "
                "VALUES ($1,'t1',$2) RETURNING id",
                org,
                f"ops-mig-t-{uuid.uuid4().hex[:8]}",
            )
            project = await conn.fetchval(
                "INSERT INTO projects (tenant_id, name, slug) VALUES ($1,'P',$2) RETURNING id",
                tenant,
                f"ops-mig-p-{uuid.uuid4().hex[:8]}",
            )
            run_id, as_of = await conn.fetchrow(
                "INSERT INTO ops_observation_runs ("
                "tenant_id, project_id, ruleset_version, idempotency_key, request_digest, "
                "input_digest, as_of, signal_count, observed_count, caller_supplied_count, "
                "not_observed_count, breached_count) VALUES ("
                "$1,$2,'slice56.v1','migrate-seed',$3,$3, now(), 11, 2, 0, 9, 0) "
                "RETURNING id, as_of",
                tenant,
                project,
                _DIGEST,
            )
            await conn.execute(
                "INSERT INTO ops_signal_results ("
                "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                "truth_tier, source_kind, source_table, source_digest, window_kind, "
                "window_end, reason_code, threshold_provenance, threshold_kind, "
                "metric_kind, metric_int, threshold_state) VALUES ("
                "$1,$2,$3,4,'job_failures','observed','system_derived_ledger',"
                "'uaid_runtime','run_steps',$4,'cumulative_project',$5,"
                "'uaid_runtime_failed_run_count','none','none','count',0,'not_evaluable')",
                tenant,
                project,
                run_id,
                _DIGEST,
                as_of,
            )
            await conn.execute(
                "INSERT INTO ops_signal_results ("
                "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                "truth_tier, source_kind, source_table, source_digest, window_kind, "
                "window_end, reason_code, threshold_provenance, threshold_kind, "
                "metric_kind, metric_money, metric_money_daily, threshold_state) VALUES ("
                "$1,$2,$3,8,'cost_anomalies','observed','system_derived_ledger',"
                "'cost_ledger','cost_events_and_budgets',$4,'cumulative_project',$5,"
                "'cost_no_budget','none','none','money',0,0,'not_evaluable')",
                tenant,
                project,
                run_id,
                _DIGEST,
                as_of,
            )
            for seq, name, reason in _MISSING:
                await conn.execute(
                    "INSERT INTO ops_signal_results ("
                    "tenant_id, project_id, run_id, seq, signal_class, observation_status, "
                    "truth_tier, source_kind, source_table, window_kind, reason_code, "
                    "threshold_provenance, threshold_kind, metric_kind, threshold_state) "
                    "VALUES ($1,$2,$3,$4,$5,'not_observed','none','none','none','none',"
                    "$6,'none','none','none','not_evaluable')",
                    tenant,
                    project,
                    run_id,
                    seq,
                    name,
                    reason,
                )
    finally:
        await conn.close()


@pytest.mark.db
def test_alembic_0055_empty_roundtrip_and_populated_refusal(_schema) -> None:
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_ops56_{uuid.uuid4().hex[:8]}"
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0055")
            assert asyncio.run(_regclass(dbname, "ops_observation_runs")) is not None
            command.downgrade(cfg, "0054")
            assert asyncio.run(_regclass(dbname, "ops_observation_runs")) is None
            assert asyncio.run(_regclass(dbname, "ops_signal_results")) is None
            command.upgrade(cfg, "0055")
            assert asyncio.run(_regclass(dbname, "ops_observation_runs")) == (
                "ops_observation_runs"
            )
            asyncio.run(_seed_complete_run(dbname))
            with pytest.raises(Exception, match="cannot downgrade Slice 56"):
                command.downgrade(cfg, "0054")
    finally:
        asyncio.run(_drop_database(dbname))
