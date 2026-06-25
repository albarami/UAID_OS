"""Monitoring / alerts evidence validation (Slice 31, App. B #11 / §26.3 / §26.6) — pure, no I/O.

A ``monitoring_status_snapshots`` row is an immutable, observational record of whether a project's
declared monitoring provider reports **≥1 active monitor AND ≥1 active alert rule** (the A5 gate-#11
evidence class, ``spec:2995``). Fail-closed and **non-authorizing**:

- ``provider ∈ {generic_monitoring_api}``; two-tier ``provenance``; **unauthenticated-only** (no credential
  exists — B9). ``target_ref`` is the full declared ``status_url`` (HTTPS, no userinfo/query/fragment,
  port 443, SSRF-safe FQDN host, normalized bounded path) — the binding key (B2).
- **Read-state honesty (B4/B6):** a failed/malformed read is NOT "0 monitors / 0 alerts". ``response_valid``
  is True only on a 200 + JSON + in-cap + strict-shape read; otherwise ``failure_kind`` is set and the
  ``active_*_count`` are **NULL** (unknown). The DB guard mirrors these invariants.
- Counts are bounded ``0..32767`` (B7); the connector maps an out-of-range JSON count to ``malformed``.

Reuses the Slice-30 SSRF primitives (``validate_target_host`` / ``assert_safe_resolved_ips`` /
``DeploySSRFRejected``) — the same generic host-shape + resolved-IP guard, not duplicated.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.release.deploy_evidence import TOKENISH_RE, DeploySSRFRejected, validate_target_host

PROVIDERS = ("generic_monitoring_api",)
PROVENANCES = ("caller_supplied_unverified", "connector_verified")
WRITABLE_PROVENANCES = ("caller_supplied_unverified",)
CONNECTOR_WRITABLE = ("connector_verified",)

FAILURE_KINDS = ("unreachable", "http_error", "content_type", "oversize", "malformed")
_POST_200_FAILURES = ("content_type", "oversize", "malformed")
MAX_COUNT = 32767  # smallint range (B7)
MAX_BODY_BYTES = 64 * 1024  # 64 KiB bounded read (D-31-4)
MAX_URL_LEN = 2048
MAX_PATH_LEN = 256

REQUIRED_CREATE_FIELDS = (
    "provider",
    "target_ref",
    "provider_reachable",
    "response_valid",
    "monitoring_active",
    "alerts_active",
    "overall_active",
)
_BOOL_FIELDS = (
    "provider_reachable",
    "response_valid",
    "monitoring_active",
    "alerts_active",
    "overall_active",
)


class InvalidMonitoringSnapshot(ValueError):
    """Raised when a monitoring snapshot payload (or status_url) is invalid (fail-closed)."""


class MalformedMonitoringBody(Exception):
    """Raised when the bounded JSON body is not the strict counts-only object (⇒ failure_kind=malformed)."""


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def parse_and_validate_status_url(url) -> tuple[str, str]:
    """Validate the declared ``status_url`` (no DNS) and return ``(host, normalized_path)``. HTTPS only;
    no userinfo/query/fragment; port 443 only; SSRF-safe FQDN host (reuses ``validate_target_host``);
    path starts ``/``, no ``..``/``//``/whitespace/control, ≤256; URL ≤2048 + token denylist. Raises
    ``InvalidMonitoringSnapshot``."""
    if not isinstance(url, str) or not (1 <= len(url) <= MAX_URL_LEN):
        raise InvalidMonitoringSnapshot("status_url must be a bounded non-empty string")
    if TOKENISH_RE.search(url):
        raise InvalidMonitoringSnapshot("status_url must not contain a token/secret prefix")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise InvalidMonitoringSnapshot(f"unparseable status_url: {url!r}") from exc
    if parts.scheme != "https":
        raise InvalidMonitoringSnapshot("status_url must use https")
    if parts.username or parts.password:
        raise InvalidMonitoringSnapshot("status_url must not contain userinfo")
    if parts.query or parts.fragment:
        raise InvalidMonitoringSnapshot("status_url must not contain a query or fragment")
    host = parts.hostname
    if not host:
        raise InvalidMonitoringSnapshot("status_url has no host")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidMonitoringSnapshot("status_url has an invalid port") from exc
    if port not in (None, 443):
        raise InvalidMonitoringSnapshot("status_url port must be 443")
    try:
        validate_target_host(host)  # SSRF host-shape (FQDN, no IP literal / localhost / .local)
    except DeploySSRFRejected as exc:
        raise InvalidMonitoringSnapshot(f"unsafe status_url host: {host!r}") from exc
    path = parts.path or "/"
    if (
        not path.startswith("/")
        or ".." in path
        or "//" in path
        or len(path) > MAX_PATH_LEN
        or any(ord(c) < 32 or c.isspace() for c in path)
    ):
        raise InvalidMonitoringSnapshot(f"invalid status_url path: {path!r}")
    return host, path


def parse_monitoring_body(obj) -> tuple[int, int]:
    """Strict counts-only object ``{active_monitor_count:int 0..32767, active_alert_rule_count:int
    0..32767}`` (B3/B7). Missing/extra/wrong-type/negative/out-of-range ⇒ ``MalformedMonitoringBody``."""
    if not isinstance(obj, dict):
        raise MalformedMonitoringBody("body must be a JSON object")
    if set(obj.keys()) != {"active_monitor_count", "active_alert_rule_count"}:
        raise MalformedMonitoringBody("body must contain exactly the two count fields")
    out = []
    for key in ("active_monitor_count", "active_alert_rule_count"):
        v = obj[key]
        if not _is_int(v) or not (0 <= v <= MAX_COUNT):
            raise MalformedMonitoringBody(f"{key} must be an int in 0..{MAX_COUNT}")
        out.append(v)
    return out[0], out[1]


# --- observation builders (honor the read-state honesty model; B4/B6) ---------


def observation_valid(active_monitor_count: int, active_alert_rule_count: int) -> dict:
    mon = active_monitor_count >= 1
    al = active_alert_rule_count >= 1
    return {
        "provider_reachable": True,
        "response_valid": True,
        "observed_http_status": 200,
        "failure_kind": None,
        "active_monitor_count": active_monitor_count,
        "active_alert_rule_count": active_alert_rule_count,
        "monitoring_active": mon,
        "alerts_active": al,
        "overall_active": mon and al,
    }


def _failed(provider_reachable: bool, observed_http_status, failure_kind: str) -> dict:
    return {
        "provider_reachable": provider_reachable,
        "response_valid": False,
        "observed_http_status": observed_http_status,
        "failure_kind": failure_kind,
        "active_monitor_count": None,
        "active_alert_rule_count": None,
        "monitoring_active": False,
        "alerts_active": False,
        "overall_active": False,
    }


def observation_unreachable() -> dict:
    return _failed(False, None, "unreachable")


def observation_http_error(observed_http_status: int) -> dict:
    return _failed(True, observed_http_status, "http_error")


def observation_failure(failure_kind: str) -> dict:
    """A post-200 read failure (``content_type`` / ``oversize`` / ``malformed``)."""
    if failure_kind not in _POST_200_FAILURES:
        raise InvalidMonitoringSnapshot(f"not a post-200 failure_kind: {failure_kind!r}")
    return _failed(True, 200, failure_kind)


# --- snapshot validators ------------------------------------------------------


def _validate_shape(record: dict) -> None:
    for field in REQUIRED_CREATE_FIELDS:
        if field not in record:
            raise InvalidMonitoringSnapshot(f"missing required field: {field}")
    if record["provider"] not in PROVIDERS:
        raise InvalidMonitoringSnapshot(f"invalid provider: {record['provider']!r}")
    parse_and_validate_status_url(record["target_ref"])  # validates the URL (raises on invalid)
    for field in _BOOL_FIELDS:
        if not isinstance(record[field], bool):
            raise InvalidMonitoringSnapshot(f"{field} must be a bool")
    status = record.get("observed_http_status")
    if status is not None and (not _is_int(status) or not (100 <= status <= 599)):
        raise InvalidMonitoringSnapshot("observed_http_status must be null or an int in 100..599")
    failure_kind = record.get("failure_kind")
    if failure_kind is not None and failure_kind not in FAILURE_KINDS:
        raise InvalidMonitoringSnapshot(f"invalid failure_kind: {failure_kind!r}")
    monitor_count = record.get("active_monitor_count")
    alert_count = record.get("active_alert_rule_count")
    for c in (monitor_count, alert_count):
        if c is not None and (not _is_int(c) or not (0 <= c <= MAX_COUNT)):
            raise InvalidMonitoringSnapshot("counts must be null or ints in 0..32767")
    # invariant: overall_active iff monitoring_active AND alerts_active.
    if record["overall_active"] != (record["monitoring_active"] and record["alerts_active"]):
        raise InvalidMonitoringSnapshot(
            "overall_active must equal (monitoring_active AND alerts_active)"
        )
    reachable = record["provider_reachable"]
    if record["response_valid"]:
        # valid-read invariant (B6): 200 + reachable + counts + active-booleans consistent.
        if not (
            reachable
            and status == 200
            and failure_kind is None
            and monitor_count is not None
            and alert_count is not None
            and record["monitoring_active"] == (monitor_count >= 1)
            and record["alerts_active"] == (alert_count >= 1)
        ):
            raise InvalidMonitoringSnapshot("valid-read invariant violated")
    else:
        # failed-read invariant (B4): NULL counts + failure_kind set + actives False.
        if not (
            failure_kind is not None
            and monitor_count is None
            and alert_count is None
            and record["monitoring_active"] is False
            and record["alerts_active"] is False
        ):
            raise InvalidMonitoringSnapshot("failed-read invariant violated")
        # per-failure_kind read-state (B6).
        if failure_kind == "unreachable":
            if not (reachable is False and status is None):
                raise InvalidMonitoringSnapshot("unreachable invariant violated")
        elif failure_kind == "http_error":
            if not (reachable is True and status is not None and status != 200):
                raise InvalidMonitoringSnapshot("http_error invariant violated")
        else:  # content_type / oversize / malformed
            if not (reachable is True and status == 200):
                raise InvalidMonitoringSnapshot(f"{failure_kind} invariant violated")


def validate_new_monitoring(record: dict) -> None:
    """Fail-closed validation of a CALLER (unverified) snapshot."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in WRITABLE_PROVENANCES:
        raise InvalidMonitoringSnapshot(
            f"provenance {prov!r} is not writable on the caller path (only caller_supplied_unverified)"
        )


def validate_connector_monitoring(record: dict) -> None:
    """Fail-closed validation of a CONNECTOR (verified) snapshot — provenance ``connector_verified`` (if
    present) and ``observed_at`` required."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in CONNECTOR_WRITABLE:
        raise InvalidMonitoringSnapshot(
            f"connector provenance must be connector_verified, got {prov!r}"
        )
    if record.get("observed_at") is None:
        raise InvalidMonitoringSnapshot("connector snapshot requires observed_at")
