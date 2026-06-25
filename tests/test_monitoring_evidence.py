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

from datetime import datetime, timezone

import pytest

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
