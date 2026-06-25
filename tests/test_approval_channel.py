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


# --- DB-backed fixtures + guard -----------------------------------------------

import uuid  # noqa: E402

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def an_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c, "INSERT INTO organizations (name, slug) VALUES ('AnOrg',:s) RETURNING id", s=f"an-org-{sfx}"
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org, n=label, s=f"an-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn], s=f"an-{proj}-{sfx}",
            )
        # a real approval in (t1, p1) — the composite-FK target.
        out["appr"] = await _scalar(
            c,
            "INSERT INTO approvals (tenant_id, project_id, action, risk_tier, requires_explicit_approval,"
            " requested_by, status) VALUES (:t,:p,'deploy_production','high',true,'req','pending') RETURNING id",
            t=out["t1"], p=out["p1"],
        )
    return out


_RAW = (
    "INSERT INTO approval_notifications "
    "(tenant_id, project_id, approval_id, risk_tier, routing_mode, channel, status) "
    "VALUES (:t,:p,:a,:tier,:mode,:ch,:st)"
)


async def _raw_insert(rls_engine, t1, p1, appr, **over):
    params = {
        "t": str(t1), "p": str(p1), "a": str(appr), "tier": "high",
        "mode": "realtime", "ch": "dashboard", "st": "delivered",
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)})
            await conn.execute(text(_RAW), params)


@pytest.mark.db
async def test_guard_accepts_valid(an_ctx, rls_engine):
    await _raw_insert(rls_engine, an_ctx["t1"], an_ctx["p1"], an_ctx["appr"])
    await _raw_insert(
        rls_engine, an_ctx["t1"], an_ctx["p1"], an_ctx["appr"],
        tier="low", mode="digest", st="skipped",
    )


@pytest.mark.db
@pytest.mark.parametrize(
    "over",
    [
        {"tier": "ultra"},  # bad risk_tier
        {"mode": "batch"},  # bad routing_mode
        {"ch": "slack"},  # channel not writable
        {"st": "queued"},  # bad status
    ],
)
async def test_guard_rejects_bad(an_ctx, rls_engine, over):
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, an_ctx["t1"], an_ctx["p1"], an_ctx["appr"], **over)


@pytest.mark.db
async def test_composite_fk_rejects_project_mismatch(an_ctx, rls_engine):
    # B3: a notification whose project_id != the approval's project_id violates the composite FK.
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, an_ctx["t1"], an_ctx["p2"], an_ctx["appr"])  # appr is in p1, not p2


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(an_ctx, rls_engine):
    await _raw_insert(rls_engine, an_ctx["t1"], an_ctx["p1"], an_ctx["appr"])
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(an_ctx["t1"])})
            nid = (await conn.execute(text("SELECT id FROM approval_notifications LIMIT 1"))).scalar_one()
    for verb in (
        "UPDATE approval_notifications SET status='failed' WHERE id=:i",
        "DELETE FROM approval_notifications WHERE id=:i",
        "TRUNCATE approval_notifications",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(an_ctx["t1"])})
                    await conn.execute(text(verb), {"i": str(nid)})


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='approval_notifications' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='approval_notifications'"
                )
            )
        ).one()
        assert rls == (True, True)
