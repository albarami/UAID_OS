"""Communication / approval-channel tests (Slice 33, §18.2 / §26.3).

Wires the Slice-4 approval engine to a human surface: a **tier-only** risk router (§18.2 — `{low,medium}`
→ digest, `{high,production}` → realtime; **no `human_approval_policy` read** this slice), a channel adapter
(protocol + Fake + dashboard; externals deferred), and an immutable append-only `approval_notifications`
log. One authoritative `request_and_notify_approval` writes **both** an `approval_events` and an
`approval_notifications` row; `ApprovalRepository` is untouched. **No secret material; no A5/readiness flip
(ruleset is now slice43.v1); verified identity reused from Slice 27.**

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
            c,
            "INSERT INTO organizations (name, slug) VALUES ('AnOrg',:s) RETURNING id",
            s=f"an-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"an-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"an-{proj}-{sfx}",
            )
        # a real approval in (t1, p1) — the composite-FK target.
        out["appr"] = await _scalar(
            c,
            "INSERT INTO approvals (tenant_id, project_id, action, risk_tier, requires_explicit_approval,"
            " requested_by, status) VALUES (:t,:p,'deploy_production','high',true,'req','pending') RETURNING id",
            t=out["t1"],
            p=out["p1"],
        )
    return out


_RAW = (
    "INSERT INTO approval_notifications "
    "(tenant_id, project_id, approval_id, risk_tier, routing_mode, channel, status) "
    "VALUES (:t,:p,:a,:tier,:mode,:ch,:st)"
)


async def _raw_insert(rls_engine, t1, p1, appr, **over):
    params = {
        "t": str(t1),
        "p": str(p1),
        "a": str(appr),
        "tier": "high",
        "mode": "realtime",
        "ch": "dashboard",
        "st": "delivered",
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(_RAW), params)


@pytest.mark.db
async def test_guard_accepts_valid(an_ctx, rls_engine):
    await _raw_insert(rls_engine, an_ctx["t1"], an_ctx["p1"], an_ctx["appr"])
    await _raw_insert(
        rls_engine,
        an_ctx["t1"],
        an_ctx["p1"],
        an_ctx["appr"],
        tier="low",
        mode="digest",
        st="skipped",
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
        await _raw_insert(
            rls_engine, an_ctx["t1"], an_ctx["p2"], an_ctx["appr"]
        )  # appr is in p1, not p2


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(an_ctx, rls_engine):
    await _raw_insert(rls_engine, an_ctx["t1"], an_ctx["p1"], an_ctx["appr"])
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(an_ctx["t1"])}
            )
            nid = (
                await conn.execute(text("SELECT id FROM approval_notifications LIMIT 1"))
            ).scalar_one()
    for verb in (
        "UPDATE approval_notifications SET status='failed' WHERE id=:i",
        "DELETE FROM approval_notifications WHERE id=:i",
        "TRUNCATE approval_notifications",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"),
                        {"t": str(an_ctx["t1"])},
                    )
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


# --- Docker-free: channel adapters --------------------------------------------


async def test_dashboard_channel_delivers():
    from app.approvals.channels.adapter import DashboardChannel

    ch = DashboardChannel()
    assert ch.name == "dashboard"
    assert await ch.deliver({"routing_mode": "realtime"}) == "delivered"


async def test_fake_channel_status_and_error():
    from app.approvals.channels.adapter import FakeChannel

    assert await FakeChannel(status="failed").deliver({}) == "failed"
    with pytest.raises(RuntimeError):
        await FakeChannel(error=RuntimeError("boom")).deliver({})


# --- DB-backed: orchestration (B4/B5) + routing + audit + RLS -----------------


def _an_repo(session, ctx):
    from app.repositories.approval_notifications import ApprovalNotificationRepository

    return ApprovalNotificationRepository(session, ctx)


@pytest.mark.db
@pytest.mark.parametrize("tier,mode", [("high", "realtime"), ("low", "digest")])
async def test_orchestration_writes_both_rows(an_ctx, admin_engine, tier, mode):
    # B4/B5: the authoritative path writes BOTH an approval_events row AND an approval_notifications row,
    # routed by tier; the channel delivery status is recorded.
    from app.approvals.channels.adapter import FakeChannel
    from app.approvals.channels.service import request_and_notify_approval
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(an_ctx["t1"])
    p1 = an_ctx["p1"]
    async with tenant_scope(ctx) as session:
        approval, notif = await request_and_notify_approval(
            session,
            ctx,
            project_id=p1,
            action="some_action",
            risk_tier=tier,
            requested_by="req",
            actor="orch",
            channel=FakeChannel(),
        )
        assert (
            notif.routing_mode == mode
            and notif.channel == "dashboard"
            and notif.status == "delivered"
        )
        assert (await _an_repo(session, ctx).latest_for_approval(approval.id)).id == notif.id
    async with admin_engine.connect() as c:
        n_events = (
            await c.execute(
                text("SELECT count(*) FROM approval_events WHERE approval_id=:a"),
                {"a": str(approval.id)},
            )
        ).scalar_one()
        n_notifs = (
            await c.execute(
                text("SELECT count(*) FROM approval_notifications WHERE approval_id=:a"),
                {"a": str(approval.id)},
            )
        ).scalar_one()
    assert n_events >= 1 and n_notifs == 1  # BOTH rows written


@pytest.mark.db
async def test_audit_safe_metadata(an_ctx, admin_engine):
    from app.approvals.channels.adapter import FakeChannel
    from app.approvals.channels.service import request_and_notify_approval
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(an_ctx["t1"])
    async with tenant_scope(ctx) as session:
        await request_and_notify_approval(
            session,
            ctx,
            project_id=an_ctx["p1"],
            action="some_action",
            risk_tier="high",
            requested_by="req",
            actor="orch",
            channel=FakeChannel(),
        )
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT payload::text FROM audit_logs WHERE action='approval.notification_recorded' "
                    "AND tenant_id=:t"
                ),
                {"t": str(an_ctx["t1"])},
            )
        ).all()
    assert rows and all(
        "realtime" in r[0] and "dashboard" in r[0] for r in rows
    )  # routing facts present


@pytest.mark.db
async def test_rls_cross_tenant(an_ctx):
    from app.approvals.channels.adapter import FakeChannel
    from app.approvals.channels.service import request_and_notify_approval
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = an_ctx["t1"], an_ctx["t2"], an_ctx["p1"]
    async with tenant_scope(TenantContext(t1)) as session:
        _, notif = await request_and_notify_approval(
            session,
            TenantContext(t1),
            project_id=p1,
            action="some_action",
            risk_tier="high",
            requested_by="req",
            actor="orch",
            channel=FakeChannel(),
        )
        approval_id = notif.approval_id
    async with tenant_scope(TenantContext(t2)) as session:
        assert await _an_repo(session, TenantContext(t2)).latest_for_approval(approval_id) is None


# --- DB-backed: no-regression + no-A5-impact (store/infra-only guards) ---------


@pytest.mark.db
async def test_no_regression_is_blocked_unchanged(an_ctx):
    # The notification layer does NOT change approval-engine/broker behavior: a pending mandatory
    # approval is blocked; APPROVED unblocks — identical to a direct ApprovalRepository path.
    from app.approvals.channels.adapter import FakeChannel
    from app.approvals.channels.service import request_and_notify_approval
    from app.repositories.approvals import ApprovalRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(an_ctx["t1"])
    p1 = an_ctx["p1"]
    async with tenant_scope(ctx) as session:
        approval, notif = await request_and_notify_approval(
            session, ctx, project_id=p1, action="deploy_production", risk_tier="high",
            requested_by="req", actor="orch", channel=FakeChannel(),
        )
        assert notif.routing_mode == "realtime"  # the notification was emitted...
        repo = ApprovalRepository(session, ctx)
        assert await repo.is_blocked(project_id=p1, action="deploy_production") is True  # ...still blocked
        await repo.approve(approval_id=approval.id, actor="approver")
        assert await repo.is_blocked(project_id=p1, action="deploy_production") is False  # APPROVED unblocks


@pytest.mark.db
async def test_no_a5_impact_before_equals_after(an_ctx):
    # Store/infra-only: requesting+notifying an approval does not change the A5 report; ruleset slice43.v1.
    from app.approvals.channels.adapter import FakeChannel
    from app.approvals.channels.service import request_and_notify_approval
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(an_ctx["t1"])
    p1 = an_ctx["p1"]
    async with tenant_scope(ctx) as session:
        before = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
        await request_and_notify_approval(
            session, ctx, project_id=p1, action="some_action", risk_tier="high",
            requested_by="req", actor="orch", channel=FakeChannel(),
        )
        after = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
    assert before == after  # no gate flip
    assert after["ruleset_version"] == "slice50.v1"
