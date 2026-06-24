"""Deployment-target verification connector (Slice 30) — generic_https, fake-in-tests.

Mirrors the ``app/release/scm_connector`` pattern: a ``DeployTargetConnector`` protocol + a
``FakeDeployTargetConnector`` (**all tests/CI — no network/DNS**) + a shipped
``GenericHttpsDeployTargetConnector`` (**never exercised in CI**).

**SSRF (B-30-4):** ``probe_target`` ALWAYS runs ``validate_target_host`` (host shape) then resolves DNS
and runs ``assert_safe_resolved_ips`` (no loopback/private/link-local/multicast/reserved/cloud-metadata)
**before any socket**; an SSRF violation raises ``DeploySSRFRejected`` (the caller writes NO snapshot).

**B-30-9 / honesty:** a safely-attempted probe ALWAYS returns an observation (never raises on transport
failure) — a serving status ⇒ positive; a non-serving status ⇒ reachable-but-not-provisioned negative;
transport/TLS/timeout ⇒ unreachable negative. The live HTTP call exists only in
``GenericHttpsDeployTargetConnector`` and is not run in CI.

**Caveat (documented, not hidden):** the shipped adapter resolves + validates the IP set, then issues the
GET to the hostname; strict connect-time pinning of the validated IP (full anti-rebind via a custom
transport) is a hardening left for the operator/implementation review — this adapter never runs in CI, and
the *tested* SSRF guarantee is that ``validate_target_host`` + ``assert_safe_resolved_ips`` execute before
any request.
"""

from __future__ import annotations

from typing import Protocol

from app.release.deploy_evidence import (
    assert_safe_resolved_ips,
    map_https_probe,
    validate_target_host,
)


class DeployTargetConnector(Protocol):
    async def probe_target(self, *, host: str) -> dict:
        """Return the mapped observation (``reachable``/``provisioned``/``target_available``/
        ``observed_http_status``) for a SAFELY-ATTEMPTED probe. Raise ``DeploySSRFRejected`` when the
        host/IP is unsafe to probe (no observation)."""
        ...


def _default_resolve(host: str) -> list[str]:
    import socket

    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


class FakeDeployTargetConnector:
    """Test/CI connector — no network/DNS. Returns a canned observation or raises."""

    def __init__(self, result: dict | None = None, *, error: Exception | None = None):
        self._result = result
        self._error = error

    async def probe_target(self, *, host: str) -> dict:
        if self._error is not None:
            raise self._error
        return self._result


class GenericHttpsDeployTargetConnector:
    """Shipped generic-HTTPS adapter — **NEVER exercised in tests** (no network in CI). SSRF-validates
    the host + resolved IPs before any socket, then ``GET https://{host}/`` (path ``/``, timeout 5.0s,
    redirects disabled, no Authorization/cookies/body). A safely-attempted probe always returns an
    observation; transport/TLS/timeout ⇒ unreachable negative (never raises). ``resolve_host`` is
    injectable for SSRF tests."""

    def __init__(self, *, resolve_host=None):
        self._resolve = resolve_host or _default_resolve

    async def probe_target(self, *, host: str) -> dict:
        # SSRF gates BEFORE any socket (raise DeploySSRFRejected ⇒ caller writes no snapshot).
        validate_target_host(host)
        assert_safe_resolved_ips(self._resolve(host))

        import httpx  # lazy so the pure parts import without the dependency

        headers = {"User-Agent": "uaid-deploy-verify/1.0", "Accept": "*/*"}
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
                resp = await client.get(f"https://{host}/", headers=headers)
        except httpx.HTTPError:
            # Transport/TLS/timeout after an SSRF-safe resolution = unreachable NEGATIVE (B-30-9).
            return map_https_probe(None)
        return map_https_probe(resp.status_code)
