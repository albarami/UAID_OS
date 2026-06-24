"""Deployment-target verification validation (Slice 30, App. B #2 / §5.2 / §26.3) — pure, no I/O.

A ``deployment_target_snapshots`` row is an immutable, observational record of whether a project's
declared production deploy **target is available** (App. B #2, ``spec:2986``). Fail-closed and
**non-authorizing** — this never deploys, never authorizes production deploy (A4/A5, ``spec:485``),
never enables go-live:

- ``provider ∈ {generic_https}``; ``environment ∈ {production, staging}``; two-tier ``provenance``
  (caller path ``caller_supplied_unverified``; connector path ``connector_verified``).
- ``target_ref`` must be a strict FQDN (no IP literal, no scheme/port/credential, alpha TLD).
- **Invariant** ``target_available = (provisioned AND reachable)`` — enforced here AND by the DB guard.
- ``map_https_probe`` turns a probe outcome into the observation (B-30-8/9): a *serving* status ⇒
  positive; a *non-serving* status ⇒ reachable-but-not-provisioned negative; *transport/TLS/timeout*
  (``None``) ⇒ unreachable negative. Every safely-attempted outcome is a real observation.
- **SSRF guard** (B-30-4): ``validate_target_host`` (host shape + IP-literal/localhost/.local/.internal
  rejection) and ``assert_safe_resolved_ips`` (no loopback/private/link-local/multicast/reserved/
  cloud-metadata) raise ``DeploySSRFRejected`` — the connector must pass both before any socket.
"""

from __future__ import annotations

import ipaddress
import re

PROVIDERS = ("generic_https",)
ENVIRONMENTS = ("production", "staging")
PROVENANCES = ("caller_supplied_unverified", "connector_verified")
WRITABLE_PROVENANCES = ("caller_supplied_unverified",)
CONNECTOR_WRITABLE = ("connector_verified",)

# Strict FQDN: 1+ labels (each 1..63 alnum/hyphen, alnum ends) + an alphabetic TLD (2..63). Rejects IP
# literals (numeric TLD), single-label hosts (localhost), schemes/ports/credentials ('://', ':', '@').
FQDN_RE = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
_UNSAFE_HOST_SUFFIXES = (".local", ".internal", ".localhost")
_UNSAFE_HOST_EXACT = ("localhost",)

REQUIRED_CREATE_FIELDS = (
    "provider",
    "environment",
    "target_ref",
    "reachable",
    "provisioned",
    "target_available",
)
_BOOL_FIELDS = ("reachable", "provisioned", "target_available")


class InvalidDeploymentSnapshot(ValueError):
    """Raised when a deployment-target snapshot payload is invalid (fail-closed)."""


class DeploySSRFRejected(Exception):
    """Raised when a target host/IP fails the SSRF safety rules — the connector must NOT probe it."""


def is_provisioned(status) -> bool:
    """B-30-8: a target is 'provisioned/serving' iff the HTTP status is 200..399 or in {401, 403}
    (a responding auth-gated production endpoint counts as available)."""
    return (
        isinstance(status, int)
        and not isinstance(status, bool)
        and ((200 <= status <= 399) or status in (401, 403))
    )


def map_https_probe(observed_http_status) -> dict:
    """Deterministic probe-outcome mapping (B-30-8/9). ``None`` = transport/TLS/timeout (after an
    SSRF-safe resolution) ⇒ unreachable negative; otherwise the received status drives the observation.
    The invariant ``target_available = (provisioned AND reachable)`` holds for every row."""
    if observed_http_status is None:
        return {
            "reachable": False,
            "provisioned": False,
            "target_available": False,
            "observed_http_status": None,
        }
    provisioned = is_provisioned(observed_http_status)
    return {
        "reachable": True,
        "provisioned": provisioned,
        "target_available": True and provisioned,  # reachable is True here
        "observed_http_status": observed_http_status,
    }


def _valid_fqdn(host) -> bool:
    return isinstance(host, str) and 1 <= len(host) <= 253 and FQDN_RE.fullmatch(host) is not None


def validate_target_host(host) -> None:
    """SSRF host-shape gate (no DNS). Reject non-FQDN, IP literals, and localhost/.local/.internal/
    .localhost hosts. Raises ``DeploySSRFRejected``."""
    if not isinstance(host, str) or not host:
        raise DeploySSRFRejected("target host must be a non-empty string")
    lowered = host.lower()
    if lowered in _UNSAFE_HOST_EXACT or lowered.endswith(_UNSAFE_HOST_SUFFIXES):
        raise DeploySSRFRejected(f"unsafe host: {host!r}")
    # Reject any IP literal (v4/v6) — targets must be FQDNs that we resolve + pin.
    try:
        ipaddress.ip_address(host)
        raise DeploySSRFRejected(f"target must be an FQDN, not an IP literal: {host!r}")
    except ValueError:
        pass
    if not _valid_fqdn(host):
        raise DeploySSRFRejected(f"target must be a valid FQDN: {host!r}")


def assert_safe_resolved_ips(ips) -> None:
    """SSRF resolved-IP gate. Every resolved IP must be a global/public address — reject loopback,
    private, link-local, multicast, reserved, unspecified, and cloud-metadata. An empty set cannot be
    attested safe. Raises ``DeploySSRFRejected``."""
    if not ips:
        raise DeploySSRFRejected("no resolved IPs — cannot attest the target is safe")
    for raw in ips:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise DeploySSRFRejected(f"unparseable resolved IP: {raw!r}") from exc
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or not ip.is_global
        ):
            raise DeploySSRFRejected(f"resolved IP is not a public address: {raw!r}")


def _validate_shape(record: dict) -> None:
    for field in REQUIRED_CREATE_FIELDS:
        if field not in record:
            raise InvalidDeploymentSnapshot(f"missing required field: {field}")
    if record["provider"] not in PROVIDERS:
        raise InvalidDeploymentSnapshot(f"invalid provider: {record['provider']!r}")
    if record["environment"] not in ENVIRONMENTS:
        raise InvalidDeploymentSnapshot(f"invalid environment: {record['environment']!r}")
    if not _valid_fqdn(record["target_ref"]):
        raise InvalidDeploymentSnapshot(
            f"target_ref must be a valid FQDN: {record['target_ref']!r}"
        )
    for field in _BOOL_FIELDS:
        if not isinstance(record[field], bool):
            raise InvalidDeploymentSnapshot(f"{field} must be a bool")
    # Invariant (B-30-6): target_available iff provisioned AND reachable.
    if record["target_available"] != (record["provisioned"] and record["reachable"]):
        raise InvalidDeploymentSnapshot("target_available must equal (provisioned AND reachable)")
    status = record.get("observed_http_status")
    if status is not None and (
        not isinstance(status, int) or isinstance(status, bool) or not (100 <= status <= 599)
    ):
        raise InvalidDeploymentSnapshot("observed_http_status must be null or an int in 100..599")


def validate_new_deployment_target(record: dict) -> None:
    """Fail-closed validation of a CALLER (unverified) snapshot."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in WRITABLE_PROVENANCES:
        raise InvalidDeploymentSnapshot(
            f"provenance {prov!r} is not writable on the caller path (only caller_supplied_unverified)"
        )


def validate_connector_deployment_target(record: dict) -> None:
    """Fail-closed validation of a CONNECTOR (verified) snapshot — provenance must be
    ``connector_verified`` (if present) and ``observed_at`` is required."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in CONNECTOR_WRITABLE:
        raise InvalidDeploymentSnapshot(
            f"connector provenance must be connector_verified, got {prov!r}"
        )
    if record.get("observed_at") is None:
        raise InvalidDeploymentSnapshot("connector snapshot requires observed_at")
