"""Deployment-target verification connector tests (Slice 30, App. B #2 / §5.2 / §26.3).

Immutable, append-only ``deployment_target_snapshots`` (RLS, latest-wins, two-tier provenance). A
broker-gated, SSRF-safe, read-only ``generic_https`` probe (``GET https://{domain}/``, path ``/``,
timeout 5.0s, redirects off, no creds) of the project's OWN declared production target writes a
``connector_verified`` snapshot — **positive when serving, verified-negative for every safely-attempted
unavailable outcome** (so latest-wins gate #2 can't keep an old passing snapshot active). The DB-guard
invariant is ``target_available = (provisioned AND reachable)``. Verification-only — no deploy/mutation,
no production-deploy authorization, no go-live.

Docker-free for the pure validators / probe mapping / SSRF guard / invariant; ``db`` for the store,
resolver, DB guard, broker-gated connector, gate #2, and the no-other-gate-regression check.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.deploy_evidence import (
    ENVIRONMENTS,
    PROVENANCES,
    PROVIDERS,
    WRITABLE_PROVENANCES,
    DeploySSRFRejected,
    InvalidDeploymentSnapshot,
    assert_safe_resolved_ips,
    is_provisioned,
    map_https_probe,
    validate_connector_deployment_target,
    validate_new_deployment_target,
    validate_target_host,
)

_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _valid(**over) -> dict:
    rec = {
        "provider": "generic_https",
        "environment": "production",
        "target_ref": "app.example.com",
        "reachable": True,
        "provisioned": True,
        "target_available": True,
    }
    rec.update(over)
    return rec


def _connector(**over) -> dict:
    rec = _valid(provenance="connector_verified", observed_at=_NOW)
    rec.update(over)
    return rec


# --- Docker-free: constants + shape validators --------------------------------


def test_constants():
    assert PROVIDERS == ("generic_https",)
    assert ENVIRONMENTS == ("production", "staging")
    assert PROVENANCES == ("caller_supplied_unverified", "connector_verified")
    assert WRITABLE_PROVENANCES == ("caller_supplied_unverified",)


def test_valid_caller_and_connector_snapshots():
    validate_new_deployment_target(_valid())
    validate_new_deployment_target(
        _valid(reachable=False, provisioned=False, target_available=False)
    )
    validate_connector_deployment_target(_connector())
    validate_connector_deployment_target(
        _connector(
            reachable=True, provisioned=False, target_available=False, observed_http_status=500
        )
    )


@pytest.mark.parametrize(
    "over",
    [
        {"provider": "kubernetes"},  # provider CHECK
        {"environment": "qa"},  # environment CHECK
        {"target_ref": "192.168.1.1"},  # IP literal not an FQDN
        {"target_ref": "localhost"},  # single label
        {"target_ref": "https://app.example.com"},  # scheme/credential markers
        {"target_ref": "user@app.example.com"},  # '@'
        {"target_ref": "app.example.com:8443"},  # port
        {"target_ref": ""},  # empty
        {"reachable": "yes"},  # not a bool
        {"observed_http_status": 600},  # out of 100..599
        {"observed_http_status": 99},
        {"target_available": True, "provisioned": False},  # invariant: avail != (prov AND reach)
        {"target_available": False, "provisioned": True, "reachable": True},  # invariant
    ],
)
def test_invalid_snapshot_rejected(over):
    with pytest.raises(InvalidDeploymentSnapshot):
        validate_new_deployment_target(_valid(**over))


def test_caller_path_rejects_connector_verified():
    with pytest.raises(InvalidDeploymentSnapshot):
        validate_new_deployment_target(_valid(provenance="connector_verified"))


def test_connector_path_requires_verified_and_observed_at():
    with pytest.raises(InvalidDeploymentSnapshot):
        validate_connector_deployment_target(_valid(provenance="caller_supplied_unverified"))
    with pytest.raises(InvalidDeploymentSnapshot):
        validate_connector_deployment_target(
            _valid(provenance="connector_verified")
        )  # no observed_at


# --- Docker-free: provisioned rule + probe mapping (B-30-8/9) ------------------


@pytest.mark.parametrize(
    "status,expected",
    [
        (199, False),
        (200, True),
        (302, True),
        (399, True),
        (400, False),
        (401, True),
        (403, True),
        (404, False),
        (500, False),
    ],
)
def test_is_provisioned_rule(status, expected):
    assert is_provisioned(status) is expected


def test_map_https_probe_serving_positive():
    m = map_https_probe(200)
    assert m == {
        "reachable": True,
        "provisioned": True,
        "target_available": True,
        "observed_http_status": 200,
    }


@pytest.mark.parametrize("status", [404, 500, 502])
def test_map_https_probe_non_serving_negative(status):
    m = map_https_probe(status)
    assert m["reachable"] is True
    assert m["provisioned"] is False
    assert m["target_available"] is False
    assert m["observed_http_status"] == status


def test_map_https_probe_transport_failure_negative():
    m = map_https_probe(None)  # transport/TLS/timeout after SSRF-safe resolution
    assert m["reachable"] is False
    assert m["provisioned"] is False
    assert m["target_available"] is False
    assert m["observed_http_status"] is None


def test_map_https_probe_invariant_holds_for_all():
    for status in (200, 401, 404, 500, None):
        m = map_https_probe(status)
        assert m["target_available"] == (m["provisioned"] and m["reachable"])


# --- Docker-free: SSRF guard (B-30-4) -----------------------------------------


def test_validate_target_host_accepts_fqdn():
    validate_target_host("app.example.com")
    validate_target_host("api.staging.example.co.uk")


@pytest.mark.parametrize(
    "host",
    [
        "192.168.1.1",  # IPv4 literal
        "10.0.0.5",
        "::1",  # IPv6 literal
        "2001:db8::1",
        "localhost",
        "app.local",  # .local
        "svc.internal",  # .internal
        "host.localhost",
        "http://app.example.com",  # scheme
        "app.example.com:8443",  # port
        "user@app.example.com",  # credential
        "",  # empty
        "single",  # single label
    ],
)
def test_validate_target_host_rejects_unsafe(host):
    with pytest.raises(DeploySSRFRejected):
        validate_target_host(host)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "169.254.1.1",  # link-local
        "0.0.0.0",  # unspecified/reserved
        "224.0.0.1",  # multicast
        "::1",  # loopback v6
        "fe80::1",  # link-local v6
        "fc00::1",  # private v6
    ],
)
def test_assert_safe_resolved_ips_rejects_internal(ip):
    with pytest.raises(DeploySSRFRejected):
        assert_safe_resolved_ips([ip])


def test_assert_safe_resolved_ips_accepts_public():
    assert_safe_resolved_ips(["8.8.8.8"])
    assert_safe_resolved_ips(["8.8.8.8", "1.1.1.1"])
    assert_safe_resolved_ips(["2606:4700:4700::1111"])  # public v6


def test_assert_safe_resolved_ips_rejects_if_any_internal():
    with pytest.raises(DeploySSRFRejected):
        assert_safe_resolved_ips(["8.8.8.8", "10.0.0.1"])  # one internal poisons the set
    with pytest.raises(DeploySSRFRejected):
        assert_safe_resolved_ips([])  # no resolution = cannot attest safe


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def dt_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('DtOrg',:s) RETURNING id",
            s=f"dt-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"dt-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"dt-{proj}-{sfx}",
            )
    return out


# --- DB-backed: guard (direct SQL refusals) -----------------------------------

_RAW_INSERT = (
    "INSERT INTO deployment_target_snapshots "
    "(tenant_id, project_id, provider, environment, target_ref, reachable, provisioned, "
    " target_available, observed_http_status, provenance) "
    "VALUES (:t,:p,:provider,:environment,:target_ref,:reachable,:provisioned,"
    " :target_available,:status,:prov)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    params = {
        "t": str(t1),
        "p": str(p1),
        "provider": "generic_https",
        "environment": "production",
        "target_ref": "app.example.com",
        "reachable": True,
        "provisioned": True,
        "target_available": True,
        "status": 200,
        "prov": "caller_supplied_unverified",
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(_RAW_INSERT), params)


@pytest.mark.db
@pytest.mark.parametrize(
    "over",
    [
        {"provider": "kubernetes"},  # provider CHECK
        {"environment": "qa"},  # environment CHECK
        {"prov": "made_up"},  # provenance CHECK
        {"target_ref": "192.168.1.1"},  # IP literal (not FQDN)
        {"target_ref": "localhost"},  # single label
        {"target_ref": "https://app.example.com"},  # scheme markers
        {"target_ref": "a." + "x" * 260 + ".com"},  # oversized
        {"status": 600},  # http status range
        {"status": 99},
        # invariant: target_available must equal (provisioned AND reachable)
        {"target_available": True, "provisioned": False, "reachable": True, "status": 500},
        {"target_available": False, "provisioned": True, "reachable": True, "status": 200},
    ],
)
async def test_guard_rejects_bad_inserts(dt_ctx, rls_engine, over):
    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, **over)


@pytest.mark.db
async def test_guard_accepts_positive_and_negative_rows(dt_ctx, rls_engine):
    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    # positive (available)
    await _raw_insert(rls_engine, t1, p1, reachable=True, provisioned=True, target_available=True)
    # non-serving negative (reachable, not provisioned)
    await _raw_insert(
        rls_engine, t1, p1, reachable=True, provisioned=False, target_available=False, status=500
    )
    # transport-failure negative (unreachable)
    await _raw_insert(
        rls_engine, t1, p1, reachable=False, provisioned=False, target_available=False, status=None
    )
    # connector-verified provenance is writable too
    await _raw_insert(rls_engine, t1, p1, prov="connector_verified")


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(dt_ctx, rls_engine):
    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            sid = (
                await conn.execute(text("SELECT id FROM deployment_target_snapshots LIMIT 1"))
            ).scalar_one()
    for verb in (
        "UPDATE deployment_target_snapshots SET provisioned=false WHERE id=:i",
        "DELETE FROM deployment_target_snapshots WHERE id=:i",
        "TRUNCATE deployment_target_snapshots",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb), {"i": str(sid)})


@pytest.mark.db
async def test_fk_cross_project_tenant_rejected(dt_ctx, rls_engine):
    t1, px = dt_ctx["t1"], dt_ctx["px"]  # px belongs to t2, not t1
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, px)


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='deployment_target_snapshots' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}  # append-only
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='deployment_target_snapshots'"
                )
            )
        ).one()
        assert rls == (True, True)
