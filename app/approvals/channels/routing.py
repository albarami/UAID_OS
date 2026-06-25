"""Approval-channel routing (Slice 33, §18.2) — pure, no I/O, no policy read.

A **tier-only** router (D-33-1): `{low, medium} → digest`, `{high, production} → realtime`. This slice reads
**no** `human_approval_policy` (B6) — no `realtime_for`, no `daily_digest_time`, no `approval_channel`; the
channel is fixed to ``dashboard``. ``digest`` is a routing **label** only (D-33-7 — no scheduler/assembly).
Also validates a notification record (enums + FK-id presence) fail-closed. **No secret material** anywhere.
"""

from __future__ import annotations

from app.approvals.states import RiskTier

ROUTING_MODES = ("digest", "realtime")
# Only ``dashboard`` is writable this slice; the rest are reserved enum values (deferred adapters).
WRITABLE_CHANNELS = ("dashboard",)
CHANNELS = ("dashboard", "slack", "teams", "email", "ticketing_system")
STATUSES = ("delivered", "failed", "skipped")

_REALTIME_TIERS = frozenset({RiskTier.HIGH, RiskTier.PRODUCTION})

REQUIRED_FIELDS = ("approval_id", "project_id", "risk_tier", "routing_mode", "channel", "status")


class InvalidNotification(ValueError):
    """Raised when a notification record is invalid (fail-closed)."""


def route(risk_tier) -> str:
    """Tier-only routing (§18.2): ``realtime`` iff the tier is ``high``/``production`` else ``digest``.
    ``RiskTier`` rejects unknown tiers (fail-closed)."""
    return "realtime" if RiskTier(risk_tier) in _REALTIME_TIERS else "digest"


def validate_notification(record: dict) -> None:
    for field in REQUIRED_FIELDS:
        if record.get(field) is None:
            raise InvalidNotification(f"missing required field: {field}")
    try:
        RiskTier(record["risk_tier"])  # validates the tier
    except ValueError as exc:
        raise InvalidNotification(f"invalid risk_tier: {record['risk_tier']!r}") from exc
    if record["routing_mode"] not in ROUTING_MODES:
        raise InvalidNotification(f"invalid routing_mode: {record['routing_mode']!r}")
    if record["channel"] not in WRITABLE_CHANNELS:
        raise InvalidNotification(
            f"channel {record['channel']!r} is not writable this slice (dashboard only)"
        )
    if record["status"] not in STATUSES:
        raise InvalidNotification(f"invalid status: {record['status']!r}")
