"""Monitoring / alerts evidence connector tests (Slice 31, App. B #11 / §26.3 / §26.6).

Immutable, append-only ``monitoring_status_snapshots`` (RLS, latest-wins, two-tier provenance). A
broker-gated, SSRF-safe, **unauthenticated** ``generic_monitoring_api`` connector performs a **bounded**
JSON read of the project's OWN declared status URL and verifies **≥1 active monitor AND ≥1 active alert
rule**. **Honesty (B4/B6):** a failed/malformed read is NOT "0 monitors / 0 alerts" — it sets
``response_valid=False`` + ``failure_kind`` + NULL counts; counts are non-null only on a valid (200 +
JSON + in-cap + strict-shape) read. The binding key is the full ``status_url`` (B2). No credential exists
(B9); host/path live only in ``target_ref`` (B8) / the transient pinned request (B10). Gate #11 only.

Docker-free for the pure validators / URL+body parsing / observation builders / invariants / SSRF reuse;
``db`` for the store, resolver, DB guard, broker-gated connector, gate #11, and no-other-gate-regression.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.deploy_evidence import DeploySSRFRejected
from app.release.monitoring_evidence import (
    FAILURE_KINDS,
    MAX_COUNT,
    PROVENANCES,
    PROVIDERS,
    WRITABLE_PROVENANCES,
    InvalidMonitoringSnapshot,
    MalformedMonitoringBody,
    observation_failure,
    observation_http_error,
    observation_unreachable,
    observation_valid,
    parse_and_validate_status_url,
    parse_monitoring_body,
    validate_connector_monitoring,
    validate_new_monitoring,
)

_NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
_URL = "https://mon.example.com/status"


def _valid(**over) -> dict:
    rec = {
        "provider": "generic_monitoring_api",
        "target_ref": _URL,
        "provider_reachable": True,
        "response_valid": True,
        "observed_http_status": 200,
        "failure_kind": None,
        "active_monitor_count": 3,
        "active_alert_rule_count": 2,
        "monitoring_active": True,
        "alerts_active": True,
        "overall_active": True,
    }
    rec.update(over)
    return rec


def _connector(**over) -> dict:
    rec = _valid(provenance="connector_verified", observed_at=_NOW)
    rec.update(over)
    return rec


# --- Docker-free: constants + status-URL validation (B2/URL-safety) -----------


def test_constants():
    assert PROVIDERS == ("generic_monitoring_api",)
    assert PROVENANCES == ("caller_supplied_unverified", "connector_verified")
    assert WRITABLE_PROVENANCES == ("caller_supplied_unverified",)
    assert set(FAILURE_KINDS) == {
        "unreachable",
        "http_error",
        "content_type",
        "oversize",
        "malformed",
    }
    assert MAX_COUNT == 32767


def test_parse_status_url_valid():
    assert parse_and_validate_status_url("https://mon.example.com/status") == (
        "mon.example.com",
        "/status",
    )
    assert parse_and_validate_status_url("https://mon.example.com")[1] == "/"  # default path


@pytest.mark.parametrize(
    "url",
    [
        "http://mon.example.com/status",  # not https
        "https://user@mon.example.com/status",  # userinfo
        "https://mon.example.com:8443/status",  # non-443 port
        "https://mon.example.com/status?q=1",  # query
        "https://mon.example.com/status#frag",  # fragment
        "https://10.0.0.5/status",  # IP literal host
        "https://localhost/status",  # localhost
        "https://mon.local/status",  # .local
        "https://mon.example.com/a/../b",  # path traversal
        "https://mon.example.com//double",  # double slash
        "https://mon.example.com/" + "x" * 300,  # oversized path
        "https://mon.example.com/ghp_token",  # token denylist
        "not-a-url",
    ],
)
def test_parse_status_url_rejected(url):
    with pytest.raises(InvalidMonitoringSnapshot):
        parse_and_validate_status_url(url)


# --- Docker-free: bounded JSON body parse (B3/B7) -----------------------------


def test_parse_monitoring_body_valid():
    assert parse_monitoring_body({"active_monitor_count": 5, "active_alert_rule_count": 0}) == (
        5,
        0,
    )
    assert parse_monitoring_body(
        {"active_monitor_count": MAX_COUNT, "active_alert_rule_count": 1}
    ) == (MAX_COUNT, 1)


@pytest.mark.parametrize(
    "body",
    [
        {"active_monitor_count": 1},  # missing field
        {"active_monitor_count": 1, "active_alert_rule_count": 1, "extra": 1},  # extra field
        {"active_monitor_count": "1", "active_alert_rule_count": 1},  # wrong type
        {"active_monitor_count": True, "active_alert_rule_count": 1},  # bool not int
        {"active_monitor_count": -1, "active_alert_rule_count": 1},  # negative
        {"active_monitor_count": MAX_COUNT + 1, "active_alert_rule_count": 1},  # > 32767 (B7)
        "not-an-object",
        [1, 2],
    ],
)
def test_parse_monitoring_body_malformed(body):
    with pytest.raises(MalformedMonitoringBody):
        parse_monitoring_body(body)


# --- Docker-free: observation builders honor the read-state honesty model (B4/B6) ---


def test_observation_valid_active_and_inactive():
    f = observation_valid(3, 2)
    assert f["response_valid"] is True and f["provider_reachable"] is True
    assert f["observed_http_status"] == 200 and f["failure_kind"] is None
    assert f["active_monitor_count"] == 3 and f["active_alert_rule_count"] == 2
    assert f["monitoring_active"] and f["alerts_active"] and f["overall_active"]
    # zero alerts -> inactive (but a real, valid read)
    g = observation_valid(3, 0)
    assert g["response_valid"] is True
    assert g["alerts_active"] is False and g["overall_active"] is False
    assert g["active_alert_rule_count"] == 0  # honest zero from a VALID read


def test_observation_unreachable_is_honest_unknown():
    f = observation_unreachable()
    assert f["provider_reachable"] is False and f["response_valid"] is False
    assert f["failure_kind"] == "unreachable" and f["observed_http_status"] is None
    assert f["active_monitor_count"] is None and f["active_alert_rule_count"] is None  # NOT 0
    assert f["overall_active"] is False


def test_observation_http_error_is_honest_unknown():
    f = observation_http_error(503)
    assert f["provider_reachable"] is True and f["response_valid"] is False
    assert f["failure_kind"] == "http_error" and f["observed_http_status"] == 503
    assert f["active_monitor_count"] is None and f["overall_active"] is False


@pytest.mark.parametrize("kind", ["content_type", "oversize", "malformed"])
def test_observation_failure_post_200_is_honest_unknown(kind):
    f = observation_failure(kind)
    assert f["provider_reachable"] is True and f["response_valid"] is False
    assert f["failure_kind"] == kind and f["observed_http_status"] == 200
    assert f["active_monitor_count"] is None and f["overall_active"] is False


# --- Docker-free: snapshot validators enforce the same invariants -------------


def test_valid_caller_and_connector_snapshots():
    validate_new_monitoring(_valid())
    validate_new_monitoring(
        observation_unreachable() | {"provider": "generic_monitoring_api", "target_ref": _URL}
    )
    validate_connector_monitoring(_connector())
    validate_connector_monitoring(_connector(**observation_http_error(500)))


@pytest.mark.parametrize(
    "over",
    [
        {"provider": "datadog"},  # provider CHECK
        {"target_ref": "http://mon.example.com/x"},  # bad URL
        # valid-read invariant: response_valid requires status 200 + non-null counts (B6)
        {"response_valid": True, "observed_http_status": 204},
        {"response_valid": True, "active_monitor_count": None},
        {"response_valid": True, "failure_kind": "malformed"},
        # failed-read invariant: not response_valid -> NULL counts + failure_kind set (B4)
        {
            "response_valid": False,
            "failure_kind": "http_error",
            "observed_http_status": 500,
            "active_monitor_count": 0,
            "active_alert_rule_count": 0,
            "monitoring_active": False,
            "alerts_active": False,
            "overall_active": False,
        },  # counts must be NULL
        # per-failure_kind (B6)
        {
            "response_valid": False,
            "failure_kind": "unreachable",
            "observed_http_status": 200,
            "provider_reachable": True,
            "active_monitor_count": None,
            "active_alert_rule_count": None,
            "monitoring_active": False,
            "alerts_active": False,
            "overall_active": False,
        },  # unreachable -> status NULL
        {
            "response_valid": False,
            "failure_kind": "http_error",
            "observed_http_status": 200,
            "active_monitor_count": None,
            "active_alert_rule_count": None,
            "monitoring_active": False,
            "alerts_active": False,
            "overall_active": False,
        },  # http_error -> status<>200
        # overall_active invariant
        {"overall_active": False},  # but monitoring+alerts True
    ],
)
def test_invalid_snapshot_rejected(over):
    with pytest.raises(InvalidMonitoringSnapshot):
        validate_new_monitoring(_valid(**over))


def test_caller_path_rejects_connector_verified():
    with pytest.raises(InvalidMonitoringSnapshot):
        validate_new_monitoring(_valid(provenance="connector_verified"))


def test_connector_path_requires_verified_and_observed_at():
    with pytest.raises(InvalidMonitoringSnapshot):
        validate_connector_monitoring(_valid(provenance="caller_supplied_unverified"))
    with pytest.raises(InvalidMonitoringSnapshot):
        validate_connector_monitoring(_valid(provenance="connector_verified"))  # no observed_at


# --- Docker-free: SSRF reuse (host-shape + IP-range from Slice 30) -------------


def test_ssrf_reuse_rejects_unsafe_host_in_url():
    # the URL validator reuses validate_target_host -> SSRF-unsafe hosts are rejected as invalid URLs
    for bad in ("https://127.0.0.1/x", "https://app.internal/x", "https://[::1]/x"):
        with pytest.raises(InvalidMonitoringSnapshot):
            parse_and_validate_status_url(bad)


def test_ssrf_exception_is_reused_from_deploy():
    # the connector reuses the Slice-30 DeploySSRFRejected (shared SSRF primitive) — sanity import.
    assert issubclass(DeploySSRFRejected, Exception)


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def mon_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('MonOrg',:s) RETURNING id",
            s=f"mon-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"mon-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"mon-{proj}-{sfx}",
            )
    return out


# --- DB-backed: guard (direct SQL refusals) -----------------------------------

_RAW_INSERT = (
    "INSERT INTO monitoring_status_snapshots "
    "(tenant_id, project_id, provider, target_ref, provider_reachable, response_valid, "
    " observed_http_status, failure_kind, active_monitor_count, active_alert_rule_count, "
    " monitoring_active, alerts_active, overall_active, provenance) "
    "VALUES (:t,:p,:provider,:target_ref,:reachable,:valid,:status,:fk,:mc,:ac,"
    " :mon,:al,:overall,:prov)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    params = {
        "t": str(t1),
        "p": str(p1),
        "provider": "generic_monitoring_api",
        "target_ref": "https://mon.example.com/status",
        "reachable": True,
        "valid": True,
        "status": 200,
        "fk": None,
        "mc": 3,
        "ac": 2,
        "mon": True,
        "al": True,
        "overall": True,
        "prov": "caller_supplied_unverified",
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(_RAW_INSERT), params)


# failed-read column packs (read-state honesty)
_UNREACHABLE = dict(
    reachable=False,
    valid=False,
    status=None,
    fk="unreachable",
    mc=None,
    ac=None,
    mon=False,
    al=False,
    overall=False,
)
_HTTP_ERROR = dict(
    reachable=True,
    valid=False,
    status=503,
    fk="http_error",
    mc=None,
    ac=None,
    mon=False,
    al=False,
    overall=False,
)
_MALFORMED = dict(
    reachable=True,
    valid=False,
    status=200,
    fk="malformed",
    mc=None,
    ac=None,
    mon=False,
    al=False,
    overall=False,
)


@pytest.mark.db
async def test_guard_accepts_valid_and_each_failure_kind(mon_ctx, rls_engine):
    t1, p1 = mon_ctx["t1"], mon_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1)  # valid active
    await _raw_insert(
        rls_engine, t1, p1, mc=3, ac=0, mon=True, al=False, overall=False
    )  # valid inactive
    await _raw_insert(rls_engine, t1, p1, **_UNREACHABLE)
    await _raw_insert(rls_engine, t1, p1, **_HTTP_ERROR)
    await _raw_insert(rls_engine, t1, p1, **_MALFORMED)
    await _raw_insert(rls_engine, t1, p1, prov="connector_verified")  # both tiers writable


@pytest.mark.db
@pytest.mark.parametrize(
    "over",
    [
        {"provider": "datadog"},  # provider CHECK
        {"target_ref": "http://mon.example.com/x"},  # not https
        {"target_ref": "https://u@mon.example.com/x"},  # userinfo char
        {"target_ref": "https://mon.example.com/ghp_token"},  # token denylist
        {"status": 600},  # http status range
        {"fk": "boom"},  # failure_kind CHECK
        {"mc": 40000},  # count > 32767 (smallint/CHECK)
        # read-state honesty (B6) — valid read requires status=200 + counts:
        {"valid": True, "status": 204},
        {"valid": True, "mc": None},
        {"valid": True, "fk": "malformed", "status": 200},  # valid must have null failure_kind
        # failed read must have NULL counts:
        {
            "reachable": True,
            "valid": False,
            "status": 503,
            "fk": "http_error",
            "mc": 0,
            "ac": 0,
            "mon": False,
            "al": False,
            "overall": False,
        },
        # per-failure_kind:
        {
            "reachable": True,
            "valid": False,
            "status": 200,
            "fk": "unreachable",
            "mc": None,
            "ac": None,
            "mon": False,
            "al": False,
            "overall": False,
        },  # unreachable needs status NULL + reachable false
        {
            "reachable": True,
            "valid": False,
            "status": 200,
            "fk": "http_error",
            "mc": None,
            "ac": None,
            "mon": False,
            "al": False,
            "overall": False,
        },  # http_error needs status<>200
        {
            "reachable": True,
            "valid": False,
            "status": 503,
            "fk": "malformed",
            "mc": None,
            "ac": None,
            "mon": False,
            "al": False,
            "overall": False,
        },  # malformed needs status=200
        # overall_active invariant:
        {"overall": False},  # but mon+al True
    ],
)
async def test_guard_rejects_bad_inserts(mon_ctx, rls_engine, over):
    t1, p1 = mon_ctx["t1"], mon_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, **over)


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(mon_ctx, rls_engine):
    t1, p1 = mon_ctx["t1"], mon_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            sid = (
                await conn.execute(text("SELECT id FROM monitoring_status_snapshots LIMIT 1"))
            ).scalar_one()
    for verb in (
        "UPDATE monitoring_status_snapshots SET response_valid=false WHERE id=:i",
        "DELETE FROM monitoring_status_snapshots WHERE id=:i",
        "TRUNCATE monitoring_status_snapshots",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb), {"i": str(sid)})


@pytest.mark.db
async def test_fk_cross_project_tenant_rejected(mon_ctx, rls_engine):
    t1, px = mon_ctx["t1"], mon_ctx["px"]
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
                        "WHERE table_name='monitoring_status_snapshots' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='monitoring_status_snapshots'"
                )
            )
        ).one()
        assert rls == (True, True)


# --- DB-backed: repository + resolver -----------------------------------------


def _mon_repo(session, ctx):
    from app.repositories.monitoring_evidence import MonitoringEvidenceRepository

    return MonitoringEvidenceRepository(session, ctx)


def _conn_payload(obs=None, target_ref=_URL, **over):
    obs = obs if obs is not None else observation_valid(3, 2)
    payload = {
        "provider": "generic_monitoring_api",
        "target_ref": target_ref,
        **obs,
        "observed_at": _NOW,
    }
    payload.update(over)
    return payload


async def _declare_monitoring(
    session, ctx, project_id, status_url=_URL, provider="generic_monitoring_api"
):
    from app.repositories.intake_categories import IntakeCategoryRepository

    monitoring = {}
    if provider is not None:
        monitoring["provider"] = provider
    if status_url is not None:
        monitoring["status_url"] = status_url
    await IntakeCategoryRepository(session, ctx).declare(
        project_id=project_id,
        category="operations_observability_support",
        actor="a",
        data={"monitoring": monitoring},
        origin="test",
    )


@pytest.mark.db
async def test_record_connector_caller_latest_count(mon_ctx):
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    async with tenant_scope(ctx) as session:
        repo = _mon_repo(session, ctx)
        row = await repo.record_connector_verified_monitoring(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )
        assert row.provenance == "connector_verified" and row.overall_active is True
        await repo.record_monitoring(
            project_id=p1,
            payload={
                "provider": "generic_monitoring_api",
                "target_ref": _URL,
                **observation_valid(2, 1),
            },
            actor="caller",
        )
        assert await repo.count_connector_verified_monitoring(p1) == 1
        latest = await repo.latest_monitoring(p1)
        assert latest is not None


@pytest.mark.db
async def test_negative_refresh_supersedes_positive_at_repo(mon_ctx):
    # B-30-9 at the repo layer: a later verified failed-read is the latest for the same target_ref.
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    async with tenant_scope(ctx) as session:
        repo = _mon_repo(session, ctx)
        await repo.record_connector_verified_monitoring(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )  # valid + active
        neg = await repo.record_connector_verified_monitoring(
            project_id=p1, payload=_conn_payload(obs=observation_unreachable()), actor="conn"
        )  # honest failed read
        latest = await repo.latest_monitoring_for_ref(p1, "generic_monitoring_api", _URL)
        assert latest.id == neg.id
        assert (
            latest.overall_active is False and latest.active_monitor_count is None
        )  # honest unknown


@pytest.mark.db
async def test_latest_for_ref_binding_change_invalidates(mon_ctx):
    # B2: a snapshot for one status_url does NOT satisfy a lookup for a different declared status_url.
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    old = "https://mon.example.com/old"
    new = "https://mon.example.com/new"
    async with tenant_scope(ctx) as session:
        repo = _mon_repo(session, ctx)
        await repo.record_connector_verified_monitoring(
            project_id=p1, payload=_conn_payload(target_ref=old), actor="conn"
        )
        assert await repo.latest_monitoring_for_ref(p1, "generic_monitoring_api", old) is not None
        assert await repo.latest_monitoring_for_ref(p1, "generic_monitoring_api", new) is None


@pytest.mark.db
async def test_resolver_returns_declared_target(mon_ctx):
    from app.release.project_repo import resolve_declared_monitoring_target
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    async with tenant_scope(ctx) as session:
        await _declare_monitoring(session, ctx, p1, status_url="https://mon.example.com/status")
        assert await resolve_declared_monitoring_target(session, ctx, p1) == (
            "https://mon.example.com/status",
            "mon.example.com",
            "/status",
        )


@pytest.mark.db
async def test_resolver_fail_closed_undeclared(mon_ctx):
    from app.release.project_repo import resolve_declared_monitoring_target
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    async with tenant_scope(ctx) as session:
        assert await resolve_declared_monitoring_target(session, ctx, mon_ctx["p2"]) is None


@pytest.mark.db
@pytest.mark.parametrize(
    "kwargs",
    [
        {"status_url": None},  # missing status_url
        {"status_url": "http://mon.example.com/x"},  # not https
        {"status_url": "https://10.0.0.1/x"},  # SSRF host
        {"provider": "datadog"},  # wrong provider
        {"provider": None},  # missing provider
    ],
)
async def test_resolver_fail_closed_bad_data(mon_ctx, kwargs):
    from app.release.project_repo import resolve_declared_monitoring_target
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    async with tenant_scope(ctx) as session:
        await _declare_monitoring(session, ctx, p1, **kwargs)
        assert await resolve_declared_monitoring_target(session, ctx, p1) is None


@pytest.mark.db
async def test_audit_safe_metadata_no_url(mon_ctx, admin_engine):
    # B8: the audit payload must NEVER carry target_ref / URL / host / path.
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    secret_url = "https://super-secret-monitor.example.com/private-status"
    async with tenant_scope(ctx) as session:
        await _mon_repo(session, ctx).record_connector_verified_monitoring(
            project_id=p1, payload=_conn_payload(target_ref=secret_url), actor="conn"
        )
    # audit_logs is not directly readable by uaid_app (SECURITY DEFINER writer) — read as admin.
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT payload::text FROM audit_logs WHERE action='monitoring.status_verified'"
                )
            )
        ).all()
    assert rows and all("secret-monitor" not in r[0] and "private-status" not in r[0] for r in rows)


@pytest.mark.db
async def test_rls_cross_tenant(mon_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = mon_ctx["t1"], mon_ctx["t2"], mon_ctx["p1"]
    async with tenant_scope(TenantContext(t1)) as session:
        await _mon_repo(session, TenantContext(t1)).record_connector_verified_monitoring(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM monitoring_status_snapshots"))
            ).scalar_one()
            assert n == 0  # deny-by-default: no GUC set
    async with tenant_scope(TenantContext(t2)) as session:
        assert (
            await _mon_repo(session, TenantContext(t2)).latest_monitoring_for_ref(
                p1, "generic_monitoring_api", _URL
            )
            is None
        )


# --- Docker-free: connector (monkeypatched transport — no network) ------------


def _install_mock_client(
    monkeypatch,
    seen,
    *,
    status=200,
    content_type="application/json",
    chunks=(b'{"active_monitor_count": 3, "active_alert_rule_count": 2}',),
    body_forbidden=False,
    raise_exc=None,
):
    import httpx

    class _Resp:
        status_code = status
        headers = {"content-type": content_type}

        async def aiter_bytes(self, chunk_size=None):
            if body_forbidden:
                raise AssertionError("body must not be read")
            for c in chunks:
                # record bytes the connector actually pulled from the stream (boundedness assertion).
                seen["consumed"] = seen.get("consumed", 0) + len(c)
                yield c

    class _Stream:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *a):
            return False

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, **k):
            seen.update(method=method, url=url, headers=k.get("headers"), ext=k.get("extensions"))
            if raise_exc is not None:
                raise raise_exc
            return _Stream()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


def test_build_pinned_get_path_ipv6_no_auth():
    from app.release.monitoring_connector import _build_pinned_get

    url, headers, ext = _build_pinned_get("mon.example.com", "8.8.8.8", "/status")
    assert url == "https://8.8.8.8/status"  # IPv4, path preserved
    assert headers["Host"] == "mon.example.com" and ext["sni_hostname"] == "mon.example.com"
    assert "Authorization" not in headers and "Cookie" not in headers  # B9
    # IPv6 bracketed (no InvalidURL crash)
    assert _build_pinned_get("mon.example.com", "2606:4700:4700::1111", "/s")[0] == (
        "https://[2606:4700:4700::1111]/s"
    )


async def test_probe_valid_active(monkeypatch):
    from app.release.monitoring_connector import _default_http_probe

    seen = {}
    _install_mock_client(monkeypatch, seen)
    obs = await _default_http_probe("mon.example.com", "/status", ["8.8.8.8"])
    assert obs["response_valid"] and obs["overall_active"] and obs["active_monitor_count"] == 3
    # B10 pinned shape + B9 no-auth
    assert (
        seen["url"] == "https://8.8.8.8/status" and seen["ext"]["sni_hostname"] == "mon.example.com"
    )
    assert "Authorization" not in seen["headers"]


async def test_probe_valid_inactive_zero_alerts(monkeypatch):
    from app.release.monitoring_connector import _default_http_probe

    _install_mock_client(
        monkeypatch, {}, chunks=(b'{"active_monitor_count": 5, "active_alert_rule_count": 0}',)
    )
    obs = await _default_http_probe("mon.example.com", "/s", ["8.8.8.8"])
    assert (
        obs["response_valid"] and obs["alerts_active"] is False and obs["overall_active"] is False
    )
    assert obs["active_alert_rule_count"] == 0  # honest zero from a VALID read


async def test_probe_non_200_is_http_error_no_body(monkeypatch):
    from app.release.monitoring_connector import _default_http_probe

    _install_mock_client(monkeypatch, {}, status=503, body_forbidden=True)
    obs = await _default_http_probe("mon.example.com", "/s", ["8.8.8.8"])
    assert obs["failure_kind"] == "http_error" and obs["observed_http_status"] == 503
    assert obs["active_monitor_count"] is None  # honest unknown (body never read on non-200)


async def test_probe_non_json_is_content_type(monkeypatch):
    from app.release.monitoring_connector import _default_http_probe

    _install_mock_client(monkeypatch, {}, content_type="text/html")
    obs = await _default_http_probe("mon.example.com", "/s", ["8.8.8.8"])
    assert obs["failure_kind"] == "content_type" and obs["active_monitor_count"] is None


async def test_probe_oversize_one_chunk_not_retained(monkeypatch):
    # B11: a single over-cap chunk is rejected BEFORE it is accumulated (pre-check) — oversize, NULL counts.
    from app.release.monitoring_connector import _default_http_probe
    from app.release.monitoring_evidence import MAX_BODY_BYTES

    big = b"x" * (MAX_BODY_BYTES + 10)
    _install_mock_client(monkeypatch, {}, chunks=(big,))
    obs = await _default_http_probe("mon.example.com", "/s", ["8.8.8.8"])
    assert obs["failure_kind"] == "oversize" and obs["response_valid"] is False
    assert obs["active_monitor_count"] is None and obs["active_alert_rule_count"] is None


async def test_probe_oversize_multi_chunk_stops_bounded(monkeypatch):
    # B11: many small chunks totaling >> cap ⇒ oversize, and the connector stops early — it never
    # retains more than MAX_BODY_BYTES (proven by bounded consumption: it does NOT drain the full stream).
    from app.release.monitoring_connector import _READ_CHUNK_BYTES, _default_http_probe
    from app.release.monitoring_evidence import MAX_BODY_BYTES

    chunk = b"x" * _READ_CHUNK_BYTES
    n_chunks = (MAX_BODY_BYTES // _READ_CHUNK_BYTES) * 4 + 16  # ~4x the cap available
    seen = {}
    _install_mock_client(monkeypatch, seen, chunks=tuple(chunk for _ in range(n_chunks)))
    obs = await _default_http_probe("mon.example.com", "/s", ["8.8.8.8"])
    assert obs["failure_kind"] == "oversize" and obs["active_monitor_count"] is None
    # consumed ≤ cap + one chunk ⇒ the connector stopped at the boundary, never accumulating the stream.
    assert seen["consumed"] <= MAX_BODY_BYTES + _READ_CHUNK_BYTES


async def test_probe_bad_shape_is_malformed(monkeypatch):
    from app.release.monitoring_connector import _default_http_probe

    _install_mock_client(monkeypatch, {}, chunks=(b'{"unexpected": 1}',))
    obs = await _default_http_probe("mon.example.com", "/s", ["8.8.8.8"])
    assert obs["failure_kind"] == "malformed" and obs["active_monitor_count"] is None


async def test_probe_transport_error_is_unreachable(monkeypatch):
    import httpx

    from app.release.monitoring_connector import _default_http_probe

    _install_mock_client(monkeypatch, {}, raise_exc=httpx.ConnectError("boom"))
    obs = await _default_http_probe("mon.example.com", "/s", ["8.8.8.8"])
    assert obs["failure_kind"] == "unreachable" and obs["provider_reachable"] is False


async def test_connector_rejects_private_resolved_ip():
    from app.release.monitoring_connector import GenericMonitoringApiConnector

    conn = GenericMonitoringApiConnector(resolve_host=lambda h: ["10.0.0.5"])
    with pytest.raises(DeploySSRFRejected):
        await conn.probe_monitoring(host="mon.example.com", path="/s")


async def test_connector_dns_failure_is_fail_closed():
    from app.release.monitoring_connector import GenericMonitoringApiConnector

    def _boom(host):
        raise OSError("name resolution failed")

    conn = GenericMonitoringApiConnector(resolve_host=_boom)
    with pytest.raises(DeploySSRFRejected):
        await conn.probe_monitoring(host="mon.example.com", path="/s")


async def test_connector_happy_path_pins_validated_ip(monkeypatch):
    from app.release.monitoring_connector import GenericMonitoringApiConnector

    seen = {}
    _install_mock_client(monkeypatch, seen)
    conn = GenericMonitoringApiConnector(resolve_host=lambda h: ["8.8.8.8"])
    obs = await conn.probe_monitoring(host="mon.example.com", path="/status")
    assert obs["overall_active"] is True and seen["url"] == "https://8.8.8.8/status"


# --- DB-backed: broker-gated service ------------------------------------------


async def _mon_allow_setup(session, ctx, project_id, agent_id="conn", status_url=_URL):
    from app.policy.levels import AutonomyLevel
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.tools import ToolAllowlistRepository

    await _declare_monitoring(session, ctx, project_id, status_url=status_url)
    await AutonomyPolicyRepository(session, ctx).upsert(
        project_id=project_id, autonomy_level=int(AutonomyLevel.A5), actor="a"
    )
    await ToolAllowlistRepository(session, ctx).grant(
        agent_id=agent_id, tool_name="monitoring.read_status", actor="admin"
    )


@pytest.mark.db
async def test_refresh_broker_allow_writes_positive_safe_params(mon_ctx, admin_engine):
    from app.release.monitoring_connector import FakeMonitoringConnector
    from app.release.monitoring_evidence_service import refresh_monitoring_evidence
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = mon_ctx["t1"], mon_ctx["p1"]
    ctx = TenantContext(t1)
    secret_url = "https://secret-mon.example.com/private"
    async with tenant_scope(ctx) as session:
        await _mon_allow_setup(session, ctx, p1, status_url=secret_url)
        result = await refresh_monitoring_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeMonitoringConnector(result=observation_valid(3, 2)),
        )
        assert result.wrote is True
        row = await _mon_repo(session, ctx).latest_monitoring_for_ref(
            p1, "generic_monitoring_api", secret_url
        )
        assert row.provenance == "connector_verified" and row.overall_active is True
    # broker recorded SAFE params only — never the raw URL/host/path (B8).
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT params FROM tool_calls WHERE tenant_id=:t "
                    "AND tool_name='monitoring.read_status'"
                ),
                {"t": str(t1)},
            )
        ).all()
    assert rows
    for (params,) in rows:
        assert "secret-mon" not in str(params) and "private" not in str(params)
        assert "status_url" not in (params or {}) and "target_ref" not in (params or {})
        assert params.get("monitoring_present") is True


@pytest.mark.db
async def test_refresh_writes_verified_negative(mon_ctx):
    # B-30-9: a safely-attempted failed read writes a verified-NEGATIVE (honest-unknown) snapshot.
    from app.release.monitoring_connector import FakeMonitoringConnector
    from app.release.monitoring_evidence_service import refresh_monitoring_evidence
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    async with tenant_scope(ctx) as session:
        await _mon_allow_setup(session, ctx, p1)
        result = await refresh_monitoring_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeMonitoringConnector(result=observation_http_error(503)),
        )
        assert result.wrote is True
        row = await _mon_repo(session, ctx).latest_monitoring_for_ref(
            p1, "generic_monitoring_api", _URL
        )
        assert row.provenance == "connector_verified"
        assert row.overall_active is False and row.failure_kind == "http_error"
        assert row.active_monitor_count is None  # honest unknown, not a fake zero


@pytest.mark.db
@pytest.mark.parametrize("scenario", ["monitoring_unbound", "broker_denied", "ssrf_reject"])
async def test_refresh_no_write_paths(mon_ctx, scenario):
    from app.release.monitoring_connector import FakeMonitoringConnector
    from app.release.monitoring_evidence_service import refresh_monitoring_evidence
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    async with tenant_scope(ctx) as session:
        repo = _mon_repo(session, ctx)
        connector = FakeMonitoringConnector(result=observation_valid(3, 2))
        if scenario == "monitoring_unbound":
            pass  # nothing declared
        elif scenario == "broker_denied":
            await _declare_monitoring(session, ctx, p1)  # declared, but agent not allowlisted
        elif scenario == "ssrf_reject":
            await _mon_allow_setup(session, ctx, p1)
            connector = FakeMonitoringConnector(error=DeploySSRFRejected("blocked"))
        result = await refresh_monitoring_evidence(
            session, ctx, project_id=p1, agent_id="conn", actor="conn", connector=connector
        )
        assert result.wrote is False and result.reason == scenario
        assert await repo.count_connector_verified_monitoring(p1) == 0


# --- Gate #11 (the deliverable): ladder + no-other-gate-regression -------------

_VERIFIED_ACTIVE = dict(
    monitoring_bound=True,
    latest_monitoring_provenance="connector_verified",
    latest_monitoring_fresh=True,
    latest_monitoring_response_valid=True,
    latest_monitoring_overall_active=True,
)


def _mon_eval(**over):
    from app.release.production_autonomy import evaluate_production_autonomy

    base = dict(readiness_level="R5")
    base.update(over)
    return evaluate_production_autonomy("p", **base).to_dict()


def _g11(d):
    return next(g for g in d["gates"] if g["number"] == 11)


@pytest.mark.parametrize(
    "inputs,reason",
    [
        ({}, "no_monitoring_declaration"),
        ({"monitoring_bound": True}, "monitoring_declared_but_no_evidence"),
        (
            {
                "monitoring_bound": True,
                "latest_monitoring_provenance": "caller_supplied_unverified",
            },
            "monitoring_observed_unverified",
        ),
        (
            {
                "monitoring_bound": True,
                "latest_monitoring_provenance": "connector_verified",
                "latest_monitoring_fresh": False,
            },
            "monitoring_evidence_stale",
        ),
        (
            {
                "monitoring_bound": True,
                "latest_monitoring_provenance": "connector_verified",
                "latest_monitoring_fresh": True,
                "latest_monitoring_response_valid": False,
                "latest_monitoring_failure_kind": "http_error",
            },
            "monitoring_evidence_unreadable",  # B4: NEVER "inactive" when unreadable
        ),
        (
            {
                "monitoring_bound": True,
                "latest_monitoring_provenance": "connector_verified",
                "latest_monitoring_fresh": True,
                "latest_monitoring_response_valid": True,
                "latest_monitoring_overall_active": False,
            },
            "monitoring_or_alerts_inactive",
        ),
    ],
)
def test_gate11_ladder(inputs, reason):
    g = _g11(_mon_eval(**inputs))
    assert g["status"] == "insufficient_evidence" and g["reason"] == reason


def test_gate11_passes_on_verified_valid_active_fresh():
    assert _g11(_mon_eval(**_VERIFIED_ACTIVE))["status"] == "passed"


def test_gate11_unreadable_is_not_inactive():
    # B4 honesty: an unreadable verified+fresh read must not be reported as alerts-inactive.
    g = _g11(
        _mon_eval(
            monitoring_bound=True,
            latest_monitoring_provenance="connector_verified",
            latest_monitoring_fresh=True,
            latest_monitoring_response_valid=False,
            latest_monitoring_failure_kind="content_type",
        )
    )
    assert g["reason"] == "monitoring_evidence_unreadable"
    assert g["reason"] != "monitoring_or_alerts_inactive"


def test_gate11_only_no_other_gate_regression():
    # The Slice-31 deliverable guard: passing gate #11 changes ONLY gate #11; every other gate is
    # byte-identical, go-live + a5 stay false, ruleset is the current Slice-50 version.
    before = _mon_eval()  # no monitoring evidence
    after = _mon_eval(**_VERIFIED_ACTIVE)  # gate #11 passes
    bg = {g["number"]: g for g in before["gates"]}
    ag = {g["number"]: g for g in after["gates"]}
    for n in range(1, 14):
        if n == 11:
            assert bg[n]["status"] == "insufficient_evidence" and ag[n]["status"] == "passed"
        else:
            assert bg[n] == ag[n], n  # byte-identical — no other gate moved
    assert before["ruleset_version"] == after["ruleset_version"] == "slice50.v1"
    assert after["a5_satisfied"] is False and after["can_go_live_autonomously"] is False


@pytest.mark.db
async def test_gate11_db_passes_then_negative_supersedes(mon_ctx):
    from app.release.monitoring_connector import FakeMonitoringConnector
    from app.release.monitoring_evidence_service import refresh_monitoring_evidence
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(mon_ctx["t1"])
    p1 = mon_ctx["p1"]
    async with tenant_scope(ctx) as session:
        await _mon_allow_setup(session, ctx, p1)
        # 1) verified valid + active + fresh ⇒ gate #11 PASSES (the first DB pass).
        await refresh_monitoring_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeMonitoringConnector(result=observation_valid(3, 2)),
        )
        rep = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
        assert _g11(rep)["status"] == "passed"
        assert rep["a5_satisfied"] is False and rep["can_go_live_autonomously"] is False
        # 2) a later failed read supersedes ⇒ gate #11 STOPS passing, honest unreadable (B-30-9/B4).
        await refresh_monitoring_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeMonitoringConnector(result=observation_http_error(503)),
        )
        rep2 = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
        g = _g11(rep2)
        assert (
            g["status"] == "insufficient_evidence"
            and g["reason"] == "monitoring_evidence_unreadable"
        )
