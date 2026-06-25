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
_UNREACHABLE = dict(reachable=False, valid=False, status=None, fk="unreachable", mc=None, ac=None, mon=False, al=False, overall=False)
_HTTP_ERROR = dict(reachable=True, valid=False, status=503, fk="http_error", mc=None, ac=None, mon=False, al=False, overall=False)
_MALFORMED = dict(reachable=True, valid=False, status=200, fk="malformed", mc=None, ac=None, mon=False, al=False, overall=False)


@pytest.mark.db
async def test_guard_accepts_valid_and_each_failure_kind(mon_ctx, rls_engine):
    t1, p1 = mon_ctx["t1"], mon_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1)  # valid active
    await _raw_insert(rls_engine, t1, p1, mc=3, ac=0, mon=True, al=False, overall=False)  # valid inactive
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
        {"reachable": True, "valid": False, "status": 503, "fk": "http_error", "mc": 0, "ac": 0, "mon": False, "al": False, "overall": False},
        # per-failure_kind:
        {"reachable": True, "valid": False, "status": 200, "fk": "unreachable", "mc": None, "ac": None, "mon": False, "al": False, "overall": False},  # unreachable needs status NULL + reachable false
        {"reachable": True, "valid": False, "status": 200, "fk": "http_error", "mc": None, "ac": None, "mon": False, "al": False, "overall": False},  # http_error needs status<>200
        {"reachable": True, "valid": False, "status": 503, "fk": "malformed", "mc": None, "ac": None, "mon": False, "al": False, "overall": False},  # malformed needs status=200
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
