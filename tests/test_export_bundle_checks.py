"""Slice 60 CHECK contract fragments and service retry proofs. Docker-free."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.release.export_bundle import ExportBundleIdempotencyRace
from app.release.export_bundle_db_checks import (
    FILE_COUNT,
    SIGNATURE_B64_SQL,
    RECORD_CHECK_CONSTRAINTS,
)
from app.release.export_bundle_service import generate_export_bundle
from app.tenancy import TenantContext


def test_signature_b64_sql_is_strict_and_does_not_normalize_input():
    assert "signature_b64 ~ '^[A-Za-z0-9+/]{86}==$'" in SIGNATURE_B64_SQL
    assert "octet_length(decode(signature_b64,'base64')) = 64" in SIGNATURE_B64_SQL
    assert "replace(encode(decode(signature_b64,'base64'),'base64'), E'\\n', '') = signature_b64"
    assert "replace(signature_b64" not in SIGNATURE_B64_SQL
    assert "btrim(signature_b64" not in SIGNATURE_B64_SQL


def test_record_checks_pin_expiry_file_count_and_offline_mode():
    named = dict(RECORD_CHECK_CONSTRAINTS)
    assert named["file_count"] == f"file_count={FILE_COUNT}"
    assert named["access_mode"] == "auditor_access_mode='offline_bundle'"
    assert "expires_at > as_of" in named["expiry_after_as_of"]
    ddl = Path("app/release/export_bundle_ddl.py").read_text()
    assert "INTERVAL '720 hours'" in ddl
    assert "public_key" not in ddl
    assert "verified_at" not in ddl
    assert "signature_ok" not in ddl
    model = Path("app/models/evidence_pack_export.py").read_text()
    assert "public_key" not in model
    assert "verified_at" not in model
    assert "signature_ok" not in model
    migration = Path("migrations/versions/0059_export_bundles.py").read_text()
    assert 'revision: str = "0059"' in migration
    assert 'down_revision: str | None = "0058"' in migration
    assert 'name="uq_ep_id_project_tenant"' not in migration


def _dbapi_error(sqlstate: str) -> DBAPIError:
    original = type("OriginalDatabaseError", (Exception,), {"sqlstate": sqlstate})()
    return DBAPIError("bundle_retry_probe", {}, original)


async def test_generate_retries_then_succeeds(monkeypatch):
    from app.release import export_bundle_service as service

    winner = MagicMock(name="snapshot")
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise service._IdempotencyWinnerNotVisible()
        return winner

    monkeypatch.setattr(service, "_generate_once", fake_once)
    monkeypatch.setattr(service, "load_signing_seed", lambda: (b"x" * 32, "k", b"y" * 32))
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    assert (
        await generate_export_bundle(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            actor="slice60-test",
            idempotency_key="retry-key",
        )
        is winner
    )
    assert calls["n"] == 2


async def test_generate_exhausts_five_race_retries(monkeypatch):
    from app.release import export_bundle_service as service

    async def fake_once(*_args, **_kwargs):
        raise service._IdempotencyWinnerNotVisible()

    monkeypatch.setattr(service, "_generate_once", fake_once)
    monkeypatch.setattr(service, "load_signing_seed", lambda: (b"x" * 32, "k", b"y" * 32))
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    with pytest.raises(ExportBundleIdempotencyRace):
        await generate_export_bundle(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            actor="slice60-test",
            idempotency_key="retry-key",
        )


async def test_retry_retries_serialization_failure(monkeypatch):
    from app.release import export_bundle_service as service

    winner = MagicMock(name="snapshot")
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _dbapi_error("40001")
        return winner

    monkeypatch.setattr(service, "_generate_once", fake_once)
    monkeypatch.setattr(service, "load_signing_seed", lambda: (b"x" * 32, "k", b"y" * 32))
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    assert (
        await generate_export_bundle(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            actor="slice60-test",
            idempotency_key="retry-key",
        )
        is winner
    )
    assert calls["n"] == 2
