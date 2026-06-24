"""Deployment-target verification connector (Slice 30) — generic_https, fake-in-tests.

Mirrors the ``app/release/scm_connector`` pattern: a ``DeployTargetConnector`` protocol + a
``FakeDeployTargetConnector`` (**all tests/CI — no network/DNS**) + a shipped
``GenericHttpsDeployTargetConnector`` (**never exercised in CI**).

**SSRF (B-30-4):** ``probe_target`` ALWAYS runs ``validate_target_host`` (host shape), resolves DNS, and
runs ``assert_safe_resolved_ips`` (no loopback/private/link-local/multicast/reserved/cloud-metadata)
**before any socket**; an SSRF violation OR a DNS-resolution failure raises ``DeploySSRFRejected`` (the
caller writes NO snapshot).

**Connect-time IP pinning (B1, anti-rebind):** the HTTP request connects to the **validated resolved IP**
(``https://{ip}/``), preserving the original host for the ``Host`` header and TLS SNI/cert verification
(``extensions={"sni_hostname": host}``). The hostname is never re-resolved at connect time, so a DNS
rebind cannot swap to an unvalidated/internal IP.

**Status-only (B2):** the live probe streams the response and reads ONLY ``status_code`` — the body is
never read/stored/audited.

**B-30-9 / honesty:** a safely-attempted probe ALWAYS returns an observation (never raises on transport
failure) — serving status ⇒ positive; non-serving status ⇒ reachable-but-not-provisioned negative;
transport/TLS/timeout ⇒ unreachable negative. The live HTTP call exists only in
``GenericHttpsDeployTargetConnector`` and is not run in CI.
"""

from __future__ import annotations

from typing import Protocol

from app.release.deploy_evidence import (
    DeploySSRFRejected,
    assert_safe_resolved_ips,
    map_https_probe,
    validate_target_host,
)


class DeployTargetConnector(Protocol):
    async def probe_target(self, *, host: str) -> dict:
        """Return the mapped observation for a SAFELY-ATTEMPTED probe. Raise ``DeploySSRFRejected`` when
        the host/IP is unsafe to probe or cannot be resolved (no observation)."""
        ...


def _default_resolve(host: str) -> list[str]:
    import socket

    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


def _build_pinned_get(host: str, ip: str) -> tuple[str, dict, dict]:
    """Build the (url, headers, extensions) for a connect-time-pinned GET (B1): connect to the validated
    ``ip`` while preserving ``host`` for the Host header and TLS SNI/cert verification."""
    url = f"https://{ip}/"
    headers = {"Host": host, "User-Agent": "uaid-deploy-verify/1.0", "Accept": "*/*"}
    extensions = {"sni_hostname": host}
    return url, headers, extensions


async def _default_http_probe(host: str, ips: list[str]) -> int | None:
    """Live probe (NEVER run in CI): connect to the first validated IP, GET ``/`` (5.0s, redirects off,
    no creds), and read ONLY the status code (B2 — body never consumed). Transport/TLS/timeout ⇒ ``None``
    (unreachable negative, B-30-9)."""
    import httpx

    url, headers, extensions = _build_pinned_get(host, ips[0])
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            async with client.stream("GET", url, headers=headers, extensions=extensions) as resp:
                return resp.status_code  # status only — the response body is never read
    except httpx.HTTPError:
        return None


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
    """Shipped generic-HTTPS adapter — **NEVER exercised in tests** (no network in CI). SSRF-validates the
    host + resolved IPs before any socket, then performs a connect-time-pinned, status-only GET (B1/B2).
    A safely-attempted probe always returns an observation; transport/TLS/timeout ⇒ unreachable negative.
    ``resolve_host`` + ``http_probe`` are injectable for SSRF/pinning/no-body tests."""

    def __init__(self, *, resolve_host=None, http_probe=None):
        self._resolve = resolve_host or _default_resolve
        self._http_probe = http_probe or _default_http_probe

    async def probe_target(self, *, host: str) -> dict:
        # SSRF gates BEFORE any socket (raise DeploySSRFRejected ⇒ caller writes no snapshot).
        validate_target_host(host)
        try:
            ips = self._resolve(host)
        except OSError as exc:  # DNS resolution failure ⇒ fail-closed (cannot attest a safe target)
            raise DeploySSRFRejected(f"target host did not resolve: {host}") from exc
        assert_safe_resolved_ips(ips)  # raises on any non-public IP
        # B1: connect ONLY to the validated IP set (http_probe receives the pinned IPs, not the host).
        status = await self._http_probe(host, list(ips))
        return map_https_probe(status)
