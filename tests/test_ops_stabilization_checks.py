"""Slice 59 CHECK contract fragments and service retry proofs. Docker-free."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.ops.stabilization import StabilizationIdempotencyRace
from app.ops.stabilization_db_checks import (
    CRITERION_CHECK_CONSTRAINTS,
    CRITERION_STATUS_SQL,
    IMPROVEMENT_CHECK_CONSTRAINTS,
    PASSED_ONLY_SEQ5_SQL,
    WINDOW_COUNTER_SQL,
)
from app.ops.stabilization_service import assess_stabilization
from app.tenancy import TenantContext


def test_passed_only_seq5_and_seq3_seq4_have_no_passed():
    names = {name for name, _sql in CRITERION_CHECK_CONSTRAINTS}
    assert "passed_only_seq5" in names
    assert PASSED_ONLY_SEQ5_SQL == "(status<>'passed' OR seq=5)"
    seq3 = CRITERION_STATUS_SQL[
        CRITERION_STATUS_SQL.find("seq=3") : CRITERION_STATUS_SQL.find("seq=4")
    ]
    seq4 = CRITERION_STATUS_SQL[
        CRITERION_STATUS_SQL.find("seq=4") : CRITERION_STATUS_SQL.find("seq=5")
    ]
    assert "'passed'" not in seq3
    assert "'passed'" not in seq4
    assert "not_observed" in seq3
    assert "not_evaluable" in seq3
    assert "rollback_currency_app_derived_not_db_provable" in seq4
    assert "handover_recorded_complete" in CRITERION_STATUS_SQL
    assert WINDOW_COUNTER_SQL.endswith("= 8")
    improvement_names = {name for name, _sql in IMPROVEMENT_CHECK_CONSTRAINTS}
    assert "seq_class_pair" in improvement_names
    assert "status_by_seq" in improvement_names
    from app.ops.stabilization_ddl import CRITERION_GUARD_SQL

    assert "seq 3 cannot be passed" in CRITERION_GUARD_SQL
    assert "seq 4 cannot be passed" in CRITERION_GUARD_SQL
    assert "NEW.status IS NOT DISTINCT FROM 'passed'" in CRITERION_GUARD_SQL


def _dbapi_error(sqlstate: str) -> DBAPIError:
    original = type("OriginalDatabaseError", (Exception,), {"sqlstate": sqlstate})()
    return DBAPIError("stab_retry_probe", {}, original)


async def test_assess_retries_then_succeeds(monkeypatch):
    from app.ops import stabilization_service as service

    winner = MagicMock(name="snapshot")
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise service._IdempotencyWinnerNotVisible()
        return winner

    monkeypatch.setattr(service, "_assess_once", fake_once)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    assert (
        await assess_stabilization(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            actor="stab-test",
            idempotency_key="retry-key",
        )
        is winner
    )
    assert calls["n"] == 2


async def test_assess_exhausts_five_race_retries(monkeypatch):
    from app.ops import stabilization_service as service

    async def fake_once(*_args, **_kwargs):
        raise service._IdempotencyWinnerNotVisible()

    monkeypatch.setattr(service, "_assess_once", fake_once)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    with pytest.raises(StabilizationIdempotencyRace):
        await assess_stabilization(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            actor="stab-test",
            idempotency_key="retry-key",
        )


async def test_retry_retries_serialization_failure(monkeypatch):
    from app.ops import stabilization_service as service

    winner = MagicMock(name="snapshot")
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _dbapi_error("40001")
        return winner

    monkeypatch.setattr(service, "_assess_once", fake_once)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    assert (
        await assess_stabilization(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            actor="stab-test",
            idempotency_key="retry-key",
        )
        is winner
    )
    assert calls["n"] == 2
