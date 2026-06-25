"""Communication / approval-channel tests (Slice 33, §18.2 / §26.3).

Wires the Slice-4 approval engine to a human surface: a **tier-only** risk router (§18.2 — `{low,medium}`
→ digest, `{high,production}` → realtime; **no `human_approval_policy` read** this slice), a channel adapter
(protocol + Fake + dashboard; externals deferred), and an immutable append-only `approval_notifications`
log. One authoritative `request_and_notify_approval` writes **both** an `approval_events` and an
`approval_notifications` row; `ApprovalRepository` is untouched. **No secret material; no A5/readiness flip
(ruleset stays slice31.v1); verified identity reused from Slice 27.**

Docker-free for the pure router + validators; `db` for the store, DB guard, orchestration, no-regression,
and the `before==after` no-gate-flip guard.
"""

import pytest

from app.approvals.channels.routing import (
    ROUTING_MODES,
    STATUSES,
    WRITABLE_CHANNELS,
    InvalidNotification,
    route,
    validate_notification,
)


def _rec(**over) -> dict:
    rec = {
        "approval_id": "11111111-1111-1111-1111-111111111111",
        "project_id": "22222222-2222-2222-2222-222222222222",
        "risk_tier": "high",
        "routing_mode": "realtime",
        "channel": "dashboard",
        "status": "delivered",
    }
    rec.update(over)
    return rec


# --- pure: tier-only routing (D-33-1) -----------------------------------------


def test_constants():
    assert set(ROUTING_MODES) == {"digest", "realtime"}
    assert WRITABLE_CHANNELS == ("dashboard",)
    assert set(STATUSES) == {"delivered", "failed", "skipped"}


@pytest.mark.parametrize(
    "tier,mode",
    [
        ("low", "digest"),
        ("medium", "digest"),
        ("high", "realtime"),
        ("production", "realtime"),
    ],
)
def test_route_tier_only(tier, mode):
    assert route(tier) == mode


def test_route_accepts_risktier_enum():
    from app.approvals.states import RiskTier

    assert route(RiskTier.PRODUCTION) == "realtime"
    assert route(RiskTier.LOW) == "digest"


def test_route_rejects_unknown_tier():
    with pytest.raises(ValueError):
        route("ultra")


# --- pure: notification validators --------------------------------------------


def test_valid_notification_passes():
    validate_notification(_rec())
    validate_notification(_rec(risk_tier="low", routing_mode="digest", status="skipped"))


@pytest.mark.parametrize(
    "over",
    [
        {"approval_id": None},  # missing FK id
        {"project_id": None},
        {"risk_tier": "ultra"},  # bad tier
        {"routing_mode": "batch"},  # bad mode
        {"channel": "slack"},  # reserved but NOT writable this slice
        {"channel": "email"},
        {"status": "queued"},  # bad status
    ],
)
def test_invalid_notification_rejected(over):
    with pytest.raises(InvalidNotification):
        validate_notification(_rec(**over))
