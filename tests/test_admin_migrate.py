"""Slice 63 Alembic 0062 reversibility (empty roundtrip + populated refusal)."""

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


async def _grants(database: str) -> set[str]:
    conn = await _admin_connect(database)
    try:
        rows = await conn.fetch(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name='autonomy_policies' AND grantee='uaid_app'"
        )
        return {r["privilege_type"] for r in rows}
    finally:
        await conn.close()


async def _seed_world(database: str) -> tuple[object, object, object]:
    conn = await _admin_connect(database)
    try:
        org = await conn.fetchval(
            "INSERT INTO organizations (name, slug) VALUES ('Mig', $1) RETURNING id",
            f"mig-{uuid.uuid4().hex[:8]}",
        )
        tenant = await conn.fetchval(
            "INSERT INTO tenants (organization_id, name, slug) VALUES ($1,'t',$2) RETURNING id",
            org,
            f"mig-t-{uuid.uuid4().hex[:8]}",
        )
        project = await conn.fetchval(
            "INSERT INTO projects (tenant_id, name, slug) VALUES ($1,'P',$2) RETURNING id",
            tenant,
            f"mig-p-{uuid.uuid4().hex[:8]}",
        )
        return org, tenant, project
    finally:
        await conn.close()


def _fresh_db() -> tuple[str, str]:
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_s63_{uuid.uuid4().hex[:8]}"
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    return dbname, alembic_url


@pytest.mark.db
def test_alembic_0062_empty_roundtrip_and_populated_refusal(_schema) -> None:
    dbname, alembic_url = _fresh_db()
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0062")
            assert asyncio.run(_regclass(dbname, "admin_role_grants")) == "admin_role_grants"
            assert asyncio.run(_grants(dbname)) == {"SELECT"}
            command.downgrade(cfg, "0061")
            assert asyncio.run(_regclass(dbname, "admin_role_grants")) is None
            assert asyncio.run(_grants(dbname)) == {"SELECT", "INSERT", "UPDATE"}
            command.upgrade(cfg, "0062")
            org, tenant, project = asyncio.run(_seed_world(dbname))
            asyncio.run(_seed_grant_only(dbname, tenant))
            with pytest.raises(DBAPIError, match="admin_role_grants"):
                command.downgrade(cfg, "0061")
            asyncio.run(_clear_admin_tables(dbname))
            asyncio.run(_seed_event_only(dbname, org, tenant))
            with pytest.raises(DBAPIError, match="tenant_admin_events"):
                command.downgrade(cfg, "0061")
            asyncio.run(_clear_admin_tables(dbname))
            asyncio.run(_seed_action_only(dbname, tenant, project))
            with pytest.raises(DBAPIError, match="admin_actions"):
                command.downgrade(cfg, "0061")
            asyncio.run(_clear_admin_tables(dbname))
            asyncio.run(_seed_change(dbname, tenant, project))
            with pytest.raises(DBAPIError, match="admin_policy_changes"):
                command.downgrade(cfg, "0061")
            asyncio.run(_ordered_drop_commits(dbname))
    finally:
        asyncio.run(_drop_database(dbname))


async def _seed_grant_only(database: str, tenant) -> None:
    conn = await _admin_connect(database)
    try:
        await conn.execute(
            "INSERT INTO admin_role_grants ("
            "tenant_id, principal_subject, admin_role, status, "
            "granted_by, granted_by_provenance) "
            "VALUES ($1, 'alice', 'tenant_admin', 'active', 'op', "
            "'operator_admin_session_unverified')",
            tenant,
        )
    finally:
        await conn.close()


async def _seed_event_only(database: str, org, tenant) -> None:
    conn = await _admin_connect(database)
    try:
        await conn.execute(
            "INSERT INTO tenant_admin_events ("
            "tenant_id, organization_id, event_kind, performed_by, "
            "performed_by_provenance) "
            "VALUES ($1, $2, 'tenant_reinstated', 'op', "
            "'operator_admin_session_unverified')",
            tenant,
            org,
        )
    finally:
        await conn.close()


async def _seed_action_only(database: str, tenant, project) -> None:
    conn = await _admin_connect(database)
    try:
        await conn.execute(
            "INSERT INTO admin_actions ("
            "tenant_id, project_id, action_kind, actor_principal, actor_provenance, "
            "required_role, actor_role, decision, ruleset_version) "
            "VALUES ($1, $2, 'set_autonomy_policy', 'unauthenticated', "
            "'caller_supplied_unverified', 'tenant_admin', NULL, "
            "'refused_unauthenticated_actor', 'slice63.v1')",
            tenant,
            project,
        )
    finally:
        await conn.close()


async def _seed_change(database: str, tenant, project) -> None:
    conn = await _admin_connect(database)
    try:
        await conn.execute(
            "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level) "
            "VALUES ($1, $2, 2)",
            tenant,
            project,
        )
        action = await conn.fetchval(
            "INSERT INTO admin_actions ("
            "tenant_id, project_id, action_kind, actor_principal, actor_provenance, "
            "required_role, actor_role, decision, ruleset_version) "
            "VALUES ($1, $2, 'set_autonomy_policy', 'unauthenticated', "
            "'caller_supplied_unverified', 'tenant_admin', NULL, "
            "'refused_unauthenticated_actor', 'slice63.v1') RETURNING id",
            tenant,
            project,
        )
        # Ledger guard refuses a refused action; disable it to seed the occupied table.
        await conn.execute("ALTER TABLE admin_policy_changes DISABLE TRIGGER admin_policy_changes_guard")
        pol = await conn.fetchval(
            "SELECT id FROM autonomy_policies WHERE project_id=$1", project
        )
        await conn.execute(
            "INSERT INTO admin_policy_changes ("
            "tenant_id, project_id, admin_action_id, autonomy_policy_id, "
            "previous_autonomy_level, new_autonomy_level, override_key_count) "
            "VALUES ($1, $2, $3, $4, 2, 2, 0)",
            tenant,
            project,
            action,
            pol,
        )
        await conn.execute("ALTER TABLE admin_policy_changes ENABLE TRIGGER admin_policy_changes_guard")
    finally:
        await conn.close()


async def _clear_admin_tables(database: str) -> None:
    conn = await _admin_connect(database)
    try:
        await conn.execute("ALTER TABLE admin_policy_changes DISABLE TRIGGER ALL")
        await conn.execute("ALTER TABLE tenant_admin_events DISABLE TRIGGER ALL")
        await conn.execute("ALTER TABLE admin_actions DISABLE TRIGGER ALL")
        await conn.execute("ALTER TABLE admin_role_grants DISABLE TRIGGER ALL")
        await conn.execute("DELETE FROM admin_policy_changes")
        await conn.execute("DELETE FROM tenant_admin_events")
        await conn.execute("DELETE FROM admin_actions")
        await conn.execute("DELETE FROM admin_role_grants")
        await conn.execute("ALTER TABLE admin_policy_changes ENABLE TRIGGER ALL")
        await conn.execute("ALTER TABLE tenant_admin_events ENABLE TRIGGER ALL")
        await conn.execute("ALTER TABLE admin_actions ENABLE TRIGGER ALL")
        await conn.execute("ALTER TABLE admin_role_grants ENABLE TRIGGER ALL")
    finally:
        await conn.close()


async def _ordered_drop_commits(database: str) -> None:
    """Mutation for P-downgrade-populated: ordered DROPs succeed, then ROLLBACK."""
    conn = await _admin_connect(database)
    try:
        async with conn.transaction():
            await conn.execute("DROP TABLE public.admin_policy_changes")
            await conn.execute("DROP TABLE public.tenant_admin_events")
            await conn.execute("DROP TABLE public.admin_actions")
            await conn.execute("DROP TABLE public.admin_role_grants")
            raise _Rollback()
    except _Rollback:
        pass
    finally:
        await conn.close()
    assert await _regclass(database, "admin_role_grants") == "admin_role_grants"


class _Rollback(Exception):
    """Sentinel to abort the mutation transaction."""
