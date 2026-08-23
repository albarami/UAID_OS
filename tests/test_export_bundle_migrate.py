"""Slice 60 Alembic 0059 reversibility proofs (empty roundtrip + populated refusal)."""

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


async def _seed_stub_row(database: str) -> None:
    conn = await _admin_connect(database)
    digest = "sha256:" + "ab" * 32
    try:
        await conn.execute("ALTER TABLE public.evidence_pack_export_records DISABLE TRIGGER ALL")
        await conn.execute(
            """
            INSERT INTO public.evidence_pack_export_records (
                tenant_id, project_id, evidence_pack_id, release_candidate_id,
                release_verdict_id, audit_checkpoint_id, idempotency_key,
                bundle_contract_version, manifest_digest, redaction_policy_version,
                redaction_policy_digest, core_content_hash, immutable_log_reference,
                signing_key_id, auditor_access_mode, as_of, expires_at, file_count,
                total_byte_count
            ) VALUES (
                gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),
                gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),
                'migrate-seed', 'slice60.export_bundle.v1', $1,
                'slice60.redaction_policy.v1', $1, $1, $2, 'k1', 'offline_bundle',
                now(), now() + INTERVAL '720 hours', 4, 1
            )
            """,
            digest,
            "cd" * 32,
        )
    finally:
        await conn.close()


def _fresh_db() -> tuple[str, str]:
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_s60_{uuid.uuid4().hex[:8]}"
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    return dbname, alembic_url


@pytest.mark.db
def test_alembic_0059_empty_roundtrip_and_populated_refusal(_schema) -> None:
    dbname, alembic_url = _fresh_db()
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0059")
            assert asyncio.run(_regclass(dbname, "evidence_pack_export_records")) == (
                "evidence_pack_export_records"
            )
            assert asyncio.run(_regclass(dbname, "evidence_pack_export_files")) == (
                "evidence_pack_export_files"
            )
            assert asyncio.run(_regclass(dbname, "evidence_pack_manifest_signatures")) == (
                "evidence_pack_manifest_signatures"
            )
            assert asyncio.run(_constraint_exists(dbname, "uq_ep_id_project_tenant"))
            command.downgrade(cfg, "0058")
            assert asyncio.run(_regclass(dbname, "evidence_pack_export_records")) is None
            assert asyncio.run(_constraint_exists(dbname, "uq_ep_id_project_tenant"))
            command.upgrade(cfg, "0059")
            asyncio.run(_seed_stub_row(dbname))
            with pytest.raises(DBAPIError, match="cannot downgrade Slice 60"):
                command.downgrade(cfg, "0058")
    finally:
        asyncio.run(_drop_database(dbname))
