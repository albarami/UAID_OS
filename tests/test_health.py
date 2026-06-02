"""Health endpoint tests — Docker-free.

Liveness takes no dependencies. Readiness's DB ping is injected via a FastAPI
dependency so these route-level tests can force success or failure WITHOUT a
real database. The genuine "fails when the DB is down" proof is the integration
evidence (real Postgres stopped), not this override.
"""

import pytest
from fastapi.testclient import TestClient

from app.health import get_db_ping
from app.main import app

client = TestClient(app)


def test_live_returns_200_without_dependencies():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_ready_returns_200_when_db_ping_succeeds():
    async def ok_ping() -> None:
        return None

    app.dependency_overrides[get_db_ping] = lambda: ok_ping
    try:
        r = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db_ping, None)

    assert r.status_code == 200
    assert r.json() == {"status": "ready", "components": {"db": "ok"}}


def test_ready_returns_503_when_db_ping_fails():
    # ROUTE-LEVEL test: forces the ping to raise. Proves the route returns 503
    # on a failed ping — NOT proof the system fails on a real DB outage.
    async def failing_ping() -> None:
        raise ConnectionError("simulated db down")

    app.dependency_overrides[get_db_ping] = lambda: failing_ping
    try:
        r = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db_ping, None)

    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["components"]["db"] == "down"
    assert "error" in body["components"]


def test_old_fake_health_endpoint_is_gone():
    r = client.get("/health")
    assert r.status_code == 404


@pytest.mark.db
def test_ready_returns_200_against_real_database(postgres_ready):
    # DB-backed: NO dependency override — exercises the real `ping()` round-trip
    # against the configured database. This is the automated counterpart to the
    # manual stopped-Postgres 503 checkpoint evidence.
    with TestClient(app) as real_client:
        r = real_client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["components"]["db"] == "ok"
