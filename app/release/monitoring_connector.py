"""Monitoring-status verification connector (Slice 31) — generic_monitoring_api, fake-in-tests.

Mirrors ``app/release/deploy_connector``: a ``MonitoringConnector`` protocol + a
``FakeMonitoringConnector`` (**all tests/CI — no network/DNS**) + a shipped
``GenericMonitoringApiConnector`` (**never exercised in CI**).

**SSRF (reused from Slice 30):** ``probe_monitoring`` ALWAYS runs ``validate_target_host`` (host shape),
resolves DNS, and runs ``assert_safe_resolved_ips`` **before any socket**; an SSRF violation OR a
DNS-resolution failure raises ``DeploySSRFRejected`` (the caller writes NO snapshot).

**Connect-time IP pinning (B10, anti-rebind):** the request connects to the **validated resolved IP**
(``https://{ip}{path}`` — IPv6 literals bracketed) while preserving the original host for the ``Host``
header and TLS SNI/cert verification. The hostname is never re-resolved at connect time.

**Unauthenticated (B9):** the request carries **no ``Authorization`` header / cookie / credential** — there
is no operator token in this slice, so nothing can be mis-targeted at a project-declared host.

**Bounded read + honesty (D-31-4 / B4):** on a 200 the connector reads a **bounded** (≤64 KiB) JSON body
and parses ONLY the two counts; everything else is an honest failed read — 200-but-not-JSON ⇒
``content_type``, over-cap ⇒ ``oversize``, bad-shape ⇒ ``malformed``, non-200 ⇒ ``http_error``,
transport/TLS/timeout ⇒ ``unreachable``. No monitor/alert names or payload are retained. The live HTTP
call exists only in ``GenericMonitoringApiConnector`` and is not run in CI.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Protocol

from app.release.deploy_evidence import (
    DeploySSRFRejected,
    assert_safe_resolved_ips,
    validate_target_host,
)
from app.release.monitoring_evidence import (
    MAX_BODY_BYTES,
    MalformedMonitoringBody,
    observation_failure,
    observation_http_error,
    observation_unreachable,
    observation_valid,
    parse_monitoring_body,
)

# Explicit per-read transport chunk size (B11): bounds how much a single ``aiter_bytes`` step can hand
# back, so the bounded read can never jump by an unbounded transport chunk.
_READ_CHUNK_BYTES = 8192


class MonitoringConnector(Protocol):
    async def probe_monitoring(self, *, host: str, path: str) -> dict:
        """Return the mapped observation for a SAFELY-ATTEMPTED read. Raise ``DeploySSRFRejected`` when
        the host/IP is unsafe to probe or cannot be resolved (no observation)."""
        ...


def _default_resolve(host: str) -> list[str]:
    import socket

    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


def _build_pinned_get(host: str, ip: str, path: str) -> tuple[str, dict, dict]:
    """Build the (url, headers, extensions) for a connect-time-pinned GET (B10): connect to the validated
    ``ip`` (at the declared ``path``) while preserving ``host`` for the Host header and TLS SNI/cert
    verification. **IPv6 literals are bracketed** (``https://[::1]/p``) so the colons are not parsed as a
    port. **No ``Authorization``/credential header (B9).**"""
    try:
        host_part = f"[{ip}]" if ipaddress.ip_address(ip).version == 6 else ip
    except ValueError:
        host_part = ip
    url = f"https://{host_part}{path}"
    headers = {
        "Host": host,
        "User-Agent": "uaid-monitoring-verify/1.0",
        "Accept": "application/json",
    }
    extensions = {"sni_hostname": host}
    return url, headers, extensions


async def _default_http_probe(host: str, path: str, ips: list[str]) -> dict:
    """Live probe (NEVER run in CI): connect to the first validated IP, GET ``path`` (5.0s, redirects off,
    **no creds**), and map the outcome to an observation (D-31-4 / B4). Reads a **bounded** body only on a
    200 + JSON response; transport/TLS/timeout ⇒ unreachable negative."""
    import httpx

    url, headers, extensions = _build_pinned_get(host, ips[0], path)
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            async with client.stream("GET", url, headers=headers, extensions=extensions) as resp:
                if resp.status_code != 200:
                    return observation_http_error(resp.status_code)  # no body read on non-200
                ctype = resp.headers.get("content-type", "")
                if "application/json" not in ctype.lower():
                    return observation_failure("content_type")
                body = bytearray()
                async for chunk in resp.aiter_bytes(chunk_size=_READ_CHUNK_BYTES):
                    # B11: bound BEFORE retaining — an over-cap chunk is never accumulated, so the
                    # retained body can never exceed MAX_BODY_BYTES (the explicit chunk_size also keeps
                    # each transport read small, so a hostile stream can't hand back an unbounded chunk).
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        return observation_failure("oversize")
                    body.extend(chunk)
                try:
                    monitor_count, alert_count = parse_monitoring_body(json.loads(bytes(body)))
                except (ValueError, MalformedMonitoringBody):
                    return observation_failure("malformed")
                return observation_valid(monitor_count, alert_count)
    except httpx.HTTPError:
        return observation_unreachable()


class FakeMonitoringConnector:
    """Test/CI connector — no network/DNS. Returns a canned observation or raises."""

    def __init__(self, result: dict | None = None, *, error: Exception | None = None):
        self._result = result
        self._error = error

    async def probe_monitoring(self, *, host: str, path: str) -> dict:
        if self._error is not None:
            raise self._error
        return self._result


class GenericMonitoringApiConnector:
    """Shipped generic monitoring-API adapter — **NEVER exercised in tests** (no network in CI).
    SSRF-validates the host + resolved IPs before any socket, then performs a connect-time-pinned,
    **unauthenticated**, bounded JSON read (B9/B10/D-31-4). A safely-attempted read always returns an
    observation; transport/TLS/timeout ⇒ unreachable negative. ``resolve_host`` + ``http_probe`` are
    injectable for SSRF/pinning/no-credential tests."""

    def __init__(self, *, resolve_host=None, http_probe=None):
        self._resolve = resolve_host or _default_resolve
        self._http_probe = http_probe or _default_http_probe

    async def probe_monitoring(self, *, host: str, path: str) -> dict:
        # SSRF gates BEFORE any socket (raise DeploySSRFRejected ⇒ caller writes no snapshot).
        validate_target_host(host)
        try:
            ips = self._resolve(host)
        except OSError as exc:  # DNS resolution failure ⇒ fail-closed (cannot attest a safe target)
            raise DeploySSRFRejected(f"monitoring host did not resolve: {host}") from exc
        assert_safe_resolved_ips(ips)  # raises on any non-public IP
        # B10: connect ONLY to the validated IP set (http_probe receives the pinned IPs, not the host).
        return await self._http_probe(host, path, list(ips))
