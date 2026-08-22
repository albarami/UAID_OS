"""Slice 58 Alembic 0057 reversibility proofs (empty roundtrip + populated refusal)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from tests.conftest import TEST_ADMIN_URL


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
    import asyncpg

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


async def _constraint_exists(database: str, name: str) -> bool:
    conn = await _admin_connect(database)
    try:
        found = await conn.fetchval("SELECT 1 FROM pg_constraint WHERE conname=$1", name)
        return found is not None
    finally:
        await conn.close()


async def _seed_run(database: str) -> None:
    conn = await _admin_connect(database)
    try:
        async with conn.transaction():
            org = await conn.fetchval(
                "INSERT INTO organizations (name, slug) VALUES ('HfMig', $1) RETURNING id",
                f"hf-mig-{uuid.uuid4().hex[:8]}",
            )
            tenant = await conn.fetchval(
                "INSERT INTO tenants (organization_id, name, slug) "
                "VALUES ($1,'t1',$2) RETURNING id",
                org,
                f"hf-mig-t-{uuid.uuid4().hex[:8]}",
            )
            project = await conn.fetchval(
                "INSERT INTO projects (tenant_id, name, slug) VALUES ($1,'P',$2) RETURNING id",
                tenant,
                f"hf-mig-p-{uuid.uuid4().hex[:8]}",
            )
            digest = "sha256:" + "ab" * 32
            incident = await conn.fetchval(
                "INSERT INTO ops_incidents ("
                "tenant_id, project_id, ruleset_version, category, severity, status, "
                "summary, source_provenance, idempotency_key, request_digest) VALUES ("
                "$1,$2,'slice57.v1','error','low','open','seed',"
                "'caller_supplied_unverified','migrate-seed',$3) RETURNING id",
                tenant,
                project,
                digest,
            )
            decisions = (
                '{"create_branches":"deny","deploy_production":"deny",'
                '"deploy_staging":"deny","open_pull_requests":"deny"}'
            )
            run_id = await conn.fetchval(
                "INSERT INTO ops_self_healing_runs ("
                "tenant_id, project_id, incident_id, ruleset_version, action_count, "
                "policy_present, policy_input_digest, request_digest, decision_snapshot, "
                "idempotency_key, rollback_coverage_digest) VALUES ("
                "$1,$2,$3,'slice58.v1',5,false,$4,$4,$5::jsonb,'migrate-seed',$4) RETURNING id",
                tenant,
                project,
                incident,
                digest,
                decisions,
            )
            rows = (
                (3, "create_patch_branch", "create_branches"),
                (4, "open_hotfix_pr", "open_pull_requests"),
                (5, "deploy_staging_hotfix", "deploy_staging"),
                (6, "deploy_production_hotfix", "deploy_production"),
                (7, "rollback_production", "deploy_production"),
            )
            for seq, action, matrix in rows:
                await conn.execute(
                    "INSERT INTO ops_self_healing_results ("
                    "tenant_id, project_id, incident_id, run_id, seq, action, matrix_action, "
                    "policy_decision, execution_posture, reason_code) VALUES ("
                    "$1,$2,$3,$4,$5,$6,$7,'deny','recorded_not_executed','plan_denied_by_policy')",
                    tenant,
                    project,
                    incident,
                    run_id,
                    seq,
                    action,
                    matrix,
                )
    finally:
        await conn.close()


def _fresh_db() -> tuple[str, str]:
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_hf58_{uuid.uuid4().hex[:8]}"
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    return dbname, alembic_url


@pytest.mark.db
def test_alembic_0057_empty_roundtrip_and_populated_refusal(_schema) -> None:
    dbname, alembic_url = _fresh_db()
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0057")
            assert asyncio.run(_regclass(dbname, "ops_self_healing_runs")) == (
                "ops_self_healing_runs"
            )
            assert asyncio.run(_constraint_exists(dbname, "uq_era_id_project_tenant"))
            command.downgrade(cfg, "0056")
            assert asyncio.run(_regclass(dbname, "ops_self_healing_runs")) is None
            assert not asyncio.run(_constraint_exists(dbname, "uq_era_id_project_tenant"))
            command.upgrade(cfg, "0057")
            asyncio.run(_seed_run(dbname))
            with pytest.raises(DBAPIError, match="cannot downgrade Slice 58"):
                command.downgrade(cfg, "0056")
    finally:
        asyncio.run(_drop_database(dbname))
