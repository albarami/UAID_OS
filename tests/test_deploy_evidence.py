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


# --- DB-backed: repository + resolver -----------------------------------------


def _dt_repo(session, ctx):
    from app.repositories.deployments import DeploymentTargetRepository

    return DeploymentTargetRepository(session, ctx)


def _conn_payload(**over) -> dict:
    rec = {
        "provider": "generic_https",
        "environment": "production",
        "target_ref": "app.example.com",
        "reachable": True,
        "provisioned": True,
        "target_available": True,
        "observed_http_status": 200,
        "observed_at": _NOW,
    }
    rec.update(over)
    return rec


async def _declare_env(session, ctx, project_id, domain="app.example.com", production=...):
    from app.repositories.intake_categories import IntakeCategoryRepository

    if production is ...:
        production = {"domain": domain}
    data = {"environments": {"production": production}} if production is not None else {}
    await IntakeCategoryRepository(session, ctx).declare(
        project_id=project_id,
        category="environments_and_deployment_targets",
        actor="a",
        data=data,
        origin="test",
    )


@pytest.mark.db
async def test_record_connector_caller_latest_counts(dt_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _dt_repo(session, ctx)
        row = await repo.record_connector_verified_deployment_target(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )
        assert row.provenance == "connector_verified" and row.target_available is True
        await repo.record_deployment_target(
            project_id=p1,
            payload={
                "provider": "generic_https",
                "environment": "production",
                "target_ref": "app.example.com",
                "reachable": True,
                "provisioned": True,
                "target_available": True,
            },
            actor="caller",
        )
        assert await repo.count_deployment_target_snapshots(p1) == 2
        assert await repo.count_connector_verified_deployment_targets(p1) == 1


@pytest.mark.db
async def test_negative_refresh_supersedes_positive_at_repo(dt_ctx):
    # B-30-9 at the repo layer: a later verified-negative snapshot is the latest for the same target.
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _dt_repo(session, ctx)
        await repo.record_connector_verified_deployment_target(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )  # positive/available
        neg = await repo.record_connector_verified_deployment_target(
            project_id=p1,
            payload=_conn_payload(
                reachable=False, provisioned=False, target_available=False, observed_http_status=None
            ),
            actor="conn",
        )  # transport-fail negative
        latest = await repo.latest_deployment_target_for_ref(p1, "generic_https", "app.example.com")
        assert latest.id == neg.id and latest.target_available is False


@pytest.mark.db
async def test_resolver_returns_declared_host(dt_ctx):
    from app.release.project_repo import resolve_declared_production_target
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _declare_env(session, ctx, p1, domain="app.example.com")
        assert await resolve_declared_production_target(session, ctx, p1) == "app.example.com"


@pytest.mark.db
async def test_resolver_fail_closed_undeclared(dt_ctx):
    from app.release.project_repo import resolve_declared_production_target
    from app.tenancy import TenantContext, tenant_scope

    t1, p2 = dt_ctx["t1"], dt_ctx["p2"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        assert await resolve_declared_production_target(session, ctx, p2) is None  # never declared


@pytest.mark.db
@pytest.mark.parametrize(
    "kwargs",
    [
        {"domain": ""},  # blank domain
        {"domain": "app.local"},  # SSRF-unsafe (.local)
        {"domain": "10.0.0.5"},  # IP literal
        {"production": {}},  # missing domain
        {"production": None},  # missing production block (data has no environments)
        {"production": {"domain": 123}},  # non-string domain
    ],
)
async def test_resolver_fail_closed_bad_data(dt_ctx, kwargs):
    from app.release.project_repo import resolve_declared_production_target
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _declare_env(session, ctx, p1, **kwargs)
        assert await resolve_declared_production_target(session, ctx, p1) is None


@pytest.mark.db
async def test_rls_cross_tenant(dt_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = dt_ctx["t1"], dt_ctx["t2"], dt_ctx["p1"]
    async with tenant_scope(TenantContext(t1)) as session:
        await _dt_repo(session, TenantContext(t1)).record_connector_verified_deployment_target(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM deployment_target_snapshots"))
            ).scalar_one()
            assert n == 0  # deny-by-default: no GUC set
    async with tenant_scope(TenantContext(t2)) as session:
        assert (
            await _dt_repo(session, TenantContext(t2)).latest_deployment_target_for_ref(
                p1, "generic_https", "app.example.com"
            )
            is None
        )


@pytest.mark.db
async def test_audit_is_safe_metadata_only(dt_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    secret_host = "secret-prod.example.com"
    async with tenant_scope(ctx) as session:
        row = await _dt_repo(session, ctx).record_connector_verified_deployment_target(
            project_id=p1, payload=_conn_payload(target_ref=secret_host), actor="conn"
        )
        sid = row.id
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"deployment_target_snapshot:{sid}", "t": t1},
            )
        ).scalar_one()
    assert secret_host not in str(payload)  # target_ref/domain never audited
    assert "target_ref" not in payload


# --- Docker-free: connector (Fake + GenericHttps SSRF wiring, no network) ------


async def test_fake_deploy_connector_returns_and_raises():
    from app.release.deploy_connector import FakeDeployTargetConnector

    obs = {"reachable": True, "provisioned": True, "target_available": True, "observed_http_status": 200}
    ok = FakeDeployTargetConnector(result=obs)
    assert (await ok.probe_target(host="app.example.com")) == obs
    boom = FakeDeployTargetConnector(error=DeploySSRFRejected("nope"))
    with pytest.raises(DeploySSRFRejected):
        await boom.probe_target(host="app.example.com")


async def test_generic_connector_rejects_unsafe_host_before_dns():
    # validate_target_host runs before any DNS/socket -> unsafe host fails closed, no network.
    from app.release.deploy_connector import GenericHttpsDeployTargetConnector

    conn = GenericHttpsDeployTargetConnector(resolve_host=lambda h: ["8.8.8.8"])
    for bad in ("localhost", "app.local", "10.0.0.5", "http://app.example.com"):
        with pytest.raises(DeploySSRFRejected):
            await conn.probe_target(host=bad)


async def test_generic_connector_rejects_dns_to_private_before_request():
    # DNS-resolve-then-pin: a host that resolves to a private IP fails closed before the HTTP request.
    from app.release.deploy_connector import GenericHttpsDeployTargetConnector

    conn = GenericHttpsDeployTargetConnector(resolve_host=lambda h: ["10.0.0.1"])
    with pytest.raises(DeploySSRFRejected):
        await conn.probe_target(host="app.example.com")
    conn2 = GenericHttpsDeployTargetConnector(resolve_host=lambda h: ["169.254.169.254"])
    with pytest.raises(DeploySSRFRejected):
        await conn2.probe_target(host="metadata.example.com")


# --- DB-backed: broker-gated service (B-30-5/9) -------------------------------


def _observation(**over) -> dict:
    rec = {"reachable": True, "provisioned": True, "target_available": True, "observed_http_status": 200}
    rec.update(over)
    return rec


async def _allow_setup(session, ctx, project_id, agent_id="conn", domain="app.example.com"):
    from app.policy.levels import AutonomyLevel
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.tools import ToolAllowlistRepository

    await _declare_env(session, ctx, project_id, domain=domain)
    await AutonomyPolicyRepository(session, ctx).upsert(
        project_id=project_id, autonomy_level=int(AutonomyLevel.A5), actor="a"
    )
    await ToolAllowlistRepository(session, ctx).grant(
        agent_id=agent_id, tool_name="deployment.read_target_status", actor="admin"
    )


@pytest.mark.db
async def test_refresh_broker_allow_writes_positive_safe_params(dt_ctx, admin_engine):
    from app.release.deploy_connector import FakeDeployTargetConnector
    from app.release.deploy_evidence_service import refresh_deployment_target_evidence
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _allow_setup(session, ctx, p1)
        result = await refresh_deployment_target_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeDeployTargetConnector(result=_observation()),
        )
        assert result.wrote is True
        row = await _dt_repo(session, ctx).latest_deployment_target_for_ref(
            p1, "generic_https", "app.example.com"
        )
        assert row.provenance == "connector_verified" and row.target_available is True
    # broker recorded SAFE params only — never the raw domain/target_ref.
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT params FROM tool_calls WHERE tenant_id=:t "
                    "AND tool_name='deployment.read_target_status'"
                ),
                {"t": str(t1)},
            )
        ).all()
    assert rows
    for (params,) in rows:
        assert "app.example.com" not in str(params)
        assert "target_ref" not in (params or {}) and "domain" not in (params or {})
        assert params.get("target_present") is True


@pytest.mark.db
async def test_refresh_writes_verified_negative(dt_ctx):
    # B-30-9: a safely-attempted UNAVAILABLE probe writes a verified-NEGATIVE snapshot.
    from app.release.deploy_connector import FakeDeployTargetConnector
    from app.release.deploy_evidence_service import refresh_deployment_target_evidence
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _allow_setup(session, ctx, p1)
        result = await refresh_deployment_target_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeDeployTargetConnector(
                result=_observation(
                    reachable=False, provisioned=False, target_available=False, observed_http_status=None
                )
            ),
        )
        assert result.wrote is True
        row = await _dt_repo(session, ctx).latest_deployment_target_for_ref(
            p1, "generic_https", "app.example.com"
        )
        assert row.provenance == "connector_verified" and row.target_available is False


@pytest.mark.db
@pytest.mark.parametrize("scenario", ["target_unbound", "broker_denied", "ssrf_reject"])
async def test_refresh_no_write_paths(dt_ctx, scenario):
    from app.release.deploy_connector import FakeDeployTargetConnector
    from app.release.deploy_evidence_service import refresh_deployment_target_evidence
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = dt_ctx["t1"], dt_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _dt_repo(session, ctx)
        connector = FakeDeployTargetConnector(result=_observation())
        if scenario == "target_unbound":
            pass  # no environments declared
        elif scenario == "broker_denied":
            await _declare_env(session, ctx, p1)  # declared, but agent not allowlisted
        elif scenario == "ssrf_reject":
            await _allow_setup(session, ctx, p1)
            connector = FakeDeployTargetConnector(error=DeploySSRFRejected("blocked"))
        result = await refresh_deployment_target_evidence(
            session, ctx, project_id=p1, agent_id="conn", actor="conn", connector=connector
        )
        assert result.wrote is False
        assert await repo.count_connector_verified_deployment_targets(p1) == 0
