"""Slice 57 Alembic 0056 reversibility proofs (empty roundtrip + populated refusal)."""

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
from sqlalchemy.exc import DBAPIError

from tests.conftest import TEST_ADMIN_URL
from tests.ops_incidents_support import INC_DIGEST


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


async def _constraint_exists(database: str, name: str) -> bool:
    conn = await _admin_connect(database)
    try:
        found = await conn.fetchval(
            "SELECT 1 FROM pg_constraint WHERE conname=$1",
            name,
        )
        return found is not None
    finally:
        await conn.close()


async def _seed_project(database: str) -> tuple[object, object]:
    conn = await _admin_connect(database)
    try:
        async with conn.transaction():
            org = await conn.fetchval(
                "INSERT INTO organizations (name, slug) VALUES ('IncMig', $1) RETURNING id",
                f"inc-mig-{uuid.uuid4().hex[:8]}",
            )
            tenant = await conn.fetchval(
                "INSERT INTO tenants (organization_id, name, slug) "
                "VALUES ($1,'t1',$2) RETURNING id",
                org,
                f"inc-mig-t-{uuid.uuid4().hex[:8]}",
            )
            project = await conn.fetchval(
                "INSERT INTO projects (tenant_id, name, slug) VALUES ($1,'P',$2) RETURNING id",
                tenant,
                f"inc-mig-p-{uuid.uuid4().hex[:8]}",
            )
            return tenant, project
    finally:
        await conn.close()


async def _seed_incident(database: str) -> None:
    tenant, project = await _seed_project(database)
    conn = await _admin_connect(database)
    try:
        await conn.execute(
            "INSERT INTO ops_incidents ("
            "tenant_id, project_id, ruleset_version, category, severity, status, "
            "summary, source_provenance, idempotency_key, request_digest) VALUES ("
            "$1,$2,'slice57.v1','error','low','open','seed',"
            "'caller_supplied_unverified','migrate-seed',$3)",
            tenant,
            project,
            INC_DIGEST,
        )
    finally:
        await conn.close()


async def _seed_handover_only(database: str) -> None:
    tenant, project = await _seed_project(database)
    conn = await _admin_connect(database)
    try:
        await conn.execute(
            "INSERT INTO ops_support_handovers ("
            "tenant_id, project_id, status, handed_over_by, received_by, "
            "recorded_by_provenance) VALUES ("
            "$1,$2,'recorded_complete','alice','ops-queue',"
            "'caller_supplied_unverified')",
            tenant,
            project,
        )
    finally:
        await conn.close()


def _fresh_db() -> tuple[str, str]:
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_inc57_{uuid.uuid4().hex[:8]}"
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    return dbname, alembic_url


@pytest.mark.db
def test_alembic_0056_empty_roundtrip_and_populated_refusal(_schema) -> None:
    dbname, alembic_url = _fresh_db()
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0056")
            assert asyncio.run(_regclass(dbname, "ops_incidents")) == "ops_incidents"
            assert asyncio.run(
                _constraint_exists(dbname, "uq_ops_signal_results_id_project_tenant")
            )
            command.downgrade(cfg, "0055")
            assert asyncio.run(_regclass(dbname, "ops_incidents")) is None
            assert not asyncio.run(
                _constraint_exists(dbname, "uq_ops_signal_results_id_project_tenant")
            )
            command.upgrade(cfg, "0056")
            assert asyncio.run(_regclass(dbname, "ops_incident_tickets")) == (
                "ops_incident_tickets"
            )
            asyncio.run(_seed_incident(dbname))
            with pytest.raises(DBAPIError, match="cannot downgrade Slice 57"):
                command.downgrade(cfg, "0055")
    finally:
        asyncio.run(_drop_database(dbname))


@pytest.mark.db
def test_alembic_0056_handover_only_populated_refusal(_schema) -> None:
    dbname, alembic_url = _fresh_db()
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0056")
            asyncio.run(_seed_handover_only(dbname))
            with pytest.raises(DBAPIError, match="cannot downgrade Slice 57"):
                command.downgrade(cfg, "0055")
    finally:
        asyncio.run(_drop_database(dbname))
