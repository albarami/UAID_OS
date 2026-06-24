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

from datetime import datetime, timezone

import pytest

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
