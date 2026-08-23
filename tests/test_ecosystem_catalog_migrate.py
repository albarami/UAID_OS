"""Slice 61a Alembic 0060 reversibility proofs (empty roundtrip + populated refusal)."""

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
from tests.ecosystem_catalog_support import CATALOG_TABLES


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


async def _seed_asset_row(database: str) -> None:
    conn = await _admin_connect(database)
    try:
        await conn.execute("ALTER TABLE public.catalog_assets DISABLE TRIGGER ALL")
        await conn.execute(
            "INSERT INTO public.catalog_assets "
            "(asset_kind,asset_key,version_label,registered_by) "
            "VALUES ('connector','migrate-seed','v1','admin')"
        )
    finally:
        await conn.close()


def _fresh_db() -> tuple[str, str]:
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_s61a_{uuid.uuid4().hex[:8]}"
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    return dbname, alembic_url


@pytest.mark.db
def test_d35_alembic_0060_empty_roundtrip_and_populated_refusal(_schema) -> None:
    dbname, alembic_url = _fresh_db()
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0060")
            for table in CATALOG_TABLES:
                assert asyncio.run(_regclass(dbname, table)) == table
            assert asyncio.run(_regclass(dbname, "evidence_pack_export_records")) == (
                "evidence_pack_export_records"
            )
            command.downgrade(cfg, "0059")
            for table in CATALOG_TABLES:
                assert asyncio.run(_regclass(dbname, table)) is None
            assert asyncio.run(_regclass(dbname, "evidence_pack_export_records")) == (
                "evidence_pack_export_records"
            )
            command.upgrade(cfg, "0060")
            asyncio.run(_seed_asset_row(dbname))
            with pytest.raises(DBAPIError, match="cannot downgrade Slice 61a"):
                command.downgrade(cfg, "0059")
    finally:
        asyncio.run(_drop_database(dbname))
