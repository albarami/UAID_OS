"""Slice 4 — approval engine (§18) tests.

Docker-free: the pure state machine, non-response policy, and gate (the
non-bypassable `requires_explicit_approval` rule). DB-backed (`db`): tenant-owned
`approvals`/`approval_events` RLS, repository lifecycle, audit-on-transition,
tri-state explicit handling, and catalog/privilege proofs.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.approvals.states import (
    InvalidApprovalRequest,
    InvalidApprovalTransition,
    RiskTier,
    Status,
    auto_transition,
    compute_deadline,
    is_blocked,
    validate_transition,
)
from app.policy.matrix import is_mandatory_action
from app.repositories.approvals import ApprovalRepository
from app.tenancy import TenantContext, tenant_scope

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
_PAST_DEADLINE = _NOW + timedelta(hours=25)


# --- is_mandatory_action (canonical §2.6 source from the Slice 3 matrix) ------


def test_is_mandatory_action():
    assert is_mandatory_action("deploy_production") is True
    assert is_mandatory_action("delete_resources") is True
    assert is_mandatory_action("run_tests") is False
    assert is_mandatory_action("not_a_real_action") is False


# --- transitions --------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        Status.APPROVED,
        Status.REJECTED,
        Status.CANCELLED,
        Status.EXPIRED,
        Status.PROCEEDED_BY_POLICY,
    ],
)
def test_pending_can_transition_to_any_terminal(target):
    validate_transition(Status.PENDING, target)  # no raise


@pytest.mark.parametrize(
    "terminal",
    [
        Status.APPROVED,
        Status.REJECTED,
        Status.CANCELLED,
        Status.EXPIRED,
        Status.PROCEEDED_BY_POLICY,
    ],
)
def test_terminal_states_are_immutable(terminal):
    with pytest.raises(InvalidApprovalTransition):
        validate_transition(terminal, Status.APPROVED)


# --- non-response policy (deadline + auto transition) -------------------------


def test_deadline_only_for_low_medium_non_explicit():
    assert compute_deadline(_NOW, RiskTier.LOW, requires_explicit=False) == _NOW + timedelta(
        hours=24
    )
    assert compute_deadline(_NOW, RiskTier.MEDIUM, requires_explicit=False) == _NOW + timedelta(
        hours=24
    )
    assert compute_deadline(_NOW, RiskTier.HIGH, requires_explicit=False) is None
    assert compute_deadline(_NOW, RiskTier.PRODUCTION, requires_explicit=False) is None
    assert compute_deadline(_NOW, RiskTier.LOW, requires_explicit=True) is None


def test_auto_transition_low_non_explicit_proceeds_after_deadline():
    assert auto_transition(RiskTier.LOW, False, _NOW, _PAST_DEADLINE) is Status.PROCEEDED_BY_POLICY
    assert auto_transition(RiskTier.LOW, False, _NOW, _NOW) is None  # before deadline


def test_auto_transition_medium_non_explicit_expires_after_deadline():
    assert auto_transition(RiskTier.MEDIUM, False, _NOW, _PAST_DEADLINE) is Status.EXPIRED


def test_auto_transition_never_for_explicit_or_high_production():
    assert auto_transition(RiskTier.LOW, True, _NOW, _PAST_DEADLINE) is None  # explicit
    assert auto_transition(RiskTier.HIGH, False, _NOW, _PAST_DEADLINE) is None
    assert auto_transition(RiskTier.PRODUCTION, False, _NOW, _PAST_DEADLINE) is None


# --- gate (resolves Blocker 1/2): explicit can only be unblocked by APPROVED --


def test_gate_no_approval_is_blocked():
    assert is_blocked(None, requires_explicit=False) is True
    assert is_blocked(None, requires_explicit=True) is True


def test_gate_approved_unblocks_always():
    assert is_blocked(Status.APPROVED, requires_explicit=False) is False
    assert is_blocked(Status.APPROVED, requires_explicit=True) is False


def test_gate_proceeded_by_policy_unblocks_only_non_explicit():
    assert is_blocked(Status.PROCEEDED_BY_POLICY, requires_explicit=False) is False
    assert (
        is_blocked(Status.PROCEEDED_BY_POLICY, requires_explicit=True) is True
    )  # explicit stays blocked


@pytest.mark.parametrize(
    "status", [Status.PENDING, Status.EXPIRED, Status.REJECTED, Status.CANCELLED]
)
def test_gate_other_states_blocked(status):
    assert is_blocked(status, requires_explicit=False) is True
    assert is_blocked(status, requires_explicit=True) is True


# --- DB-backed: lifecycle, gate, RLS, audit, catalog -------------------------

_DAY = timedelta(hours=25)


@pytest_asyncio.fixture
async def approval_ctx(admin_engine):
    """Idempotent org/tenant + a UNIQUE project per test."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org_id = (
            await c.execute(
                text(
                    "INSERT INTO organizations (name, slug) VALUES ('ApvOrg','apv-org') "
                    "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id"
                )
            )
        ).scalar_one()
        tenant_id = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'ApvT','apv-t') "
                    "ON CONFLICT (organization_id, slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id"
                ),
                {"o": org_id},
            )
        ).scalar_one()
        project_id = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'ApvP',:s) RETURNING id"
                ),
                {"t": tenant_id, "s": f"apv-proj-{sfx}"},
            )
        ).scalar_one()
    return tenant_id, project_id


@pytest.mark.db
async def test_request_approve_unblocks_and_records(approval_ctx, admin_engine):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid, action="run_tests", risk_tier="low", requested_by="u:1"
        )
        assert await repo.is_blocked(pid, "run_tests") is True
        await repo.approve(approval_id=a.id, actor="boss")
        assert await repo.is_blocked(pid, "run_tests") is False
    async with admin_engine.connect() as c:
        events = (
            (
                await c.execute(
                    text(
                        "SELECT event_type FROM approval_events WHERE approval_id=:i ORDER BY created_at"
                    ),
                    {"i": a.id},
                )
            )
            .scalars()
            .all()
        )
        assert events == ["requested", "approved"]
        audits = (
            (
                await c.execute(
                    text("SELECT action FROM audit_logs WHERE target=:t ORDER BY seq"),
                    {"t": f"approval:{a.id}"},
                )
            )
            .scalars()
            .all()
        )
        assert audits == ["approval.requested", "approval.approved"]


@pytest.mark.db
async def test_mandatory_action_forces_explicit_even_when_omitted(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid, action="deploy_production", risk_tier="low", requested_by="u"
        )
        assert a.requires_explicit_approval is True


@pytest.mark.db
async def test_mandatory_action_explicit_false_is_rejected(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        with pytest.raises(InvalidApprovalRequest):
            await repo.request(
                project_id=pid,
                action="deploy_production",
                risk_tier="low",
                requested_by="u",
                requires_explicit_approval=False,
            )


@pytest.mark.db
async def test_non_mandatory_tri_state(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        omitted = await repo.request(
            project_id=pid, action="run_tests", risk_tier="low", requested_by="u"
        )
        explicit = await repo.request(
            project_id=pid,
            action="run_tests",
            risk_tier="low",
            requested_by="u",
            requires_explicit_approval=True,
        )
        assert omitted.requires_explicit_approval is False
        assert explicit.requires_explicit_approval is True


@pytest.mark.db
async def test_mandatory_low_past_deadline_still_blocked_unless_approved(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid, action="deploy_production", risk_tier="low", requested_by="u"
        )
        # explicit (mandatory) => expiry is a no-op even past 24h
        await repo.expire_if_overdue(approval_id=a.id, now=a.requested_at + _DAY)
        assert (await repo.get(a.id)).status == "pending"
        assert await repo.is_blocked(pid, "deploy_production") is True
        await repo.approve(approval_id=a.id, actor="boss")
        assert await repo.is_blocked(pid, "deploy_production") is False


@pytest.mark.db
async def test_low_non_explicit_proceeds_after_deadline(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid, action="run_tests", risk_tier="low", requested_by="u"
        )
        await repo.expire_if_overdue(approval_id=a.id, now=a.requested_at + _DAY)
        assert (await repo.get(a.id)).status == "proceeded_by_policy"
        assert await repo.is_blocked(pid, "run_tests") is False


@pytest.mark.db
async def test_medium_non_explicit_expires_and_stays_blocked(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid, action="run_tests", risk_tier="medium", requested_by="u"
        )
        await repo.expire_if_overdue(approval_id=a.id, now=a.requested_at + _DAY)
        assert (await repo.get(a.id)).status == "expired"
        assert await repo.is_blocked(pid, "run_tests") is True


@pytest.mark.db
async def test_high_never_lapses(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid, action="run_tests", risk_tier="high", requested_by="u"
        )
        await repo.expire_if_overdue(approval_id=a.id, now=a.requested_at + _DAY)
        assert (await repo.get(a.id)).status == "pending"
        assert await repo.is_blocked(pid, "run_tests") is True


@pytest.mark.db
async def test_double_resolve_raises(approval_ctx):
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid, action="run_tests", risk_tier="low", requested_by="u"
        )
        await repo.approve(approval_id=a.id, actor="x")
        with pytest.raises(InvalidApprovalTransition):
            await repo.reject(approval_id=a.id, actor="y")


@pytest.mark.db
async def test_rls_deny_by_default_both_tables(rls_engine, admin_engine, approval_ctx):
    tid, pid = approval_ctx
    async with admin_engine.begin() as c:
        approval_id = (
            await c.execute(
                text(
                    "INSERT INTO approvals (tenant_id, project_id, action, risk_tier, "
                    "requires_explicit_approval, requested_by) "
                    "VALUES (:t,:p,'run_tests','low',false,'u') RETURNING id"
                ),
                {"t": tid, "p": pid},
            )
        ).scalar_one()
        await c.execute(
            text(
                "INSERT INTO approval_events (tenant_id, approval_id, event_type, actor) "
                "VALUES (:t,:a,'requested','u')"
            ),
            {"t": tid, "a": approval_id},
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():  # no GUC -> deny by default (both tables)
            assert (await conn.execute(text("SELECT count(*) FROM approvals"))).scalar_one() == 0
            assert (
                await conn.execute(text("SELECT count(*) FROM approval_events"))
            ).scalar_one() == 0


@pytest.mark.db
async def test_approvals_catalog_and_grants(admin_engine):
    async with admin_engine.connect() as c:
        for tbl in ("approvals", "approval_events"):
            rls = (
                await c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": tbl},
                )
            ).one()
            assert rls == (True, True)
        apv = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='approvals' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        ev = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='approval_events' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
    assert apv == {"SELECT", "INSERT", "UPDATE"}  # no DELETE
    assert ev == {"SELECT", "INSERT"}  # append-only: no UPDATE/DELETE


@pytest.mark.db
async def test_explicit_non_mandatory_low_past_deadline_still_blocked_unless_approved(approval_ctx):
    # Closes the "policy NEEDS_APPROVAL + low timeout" bypass case: a non-mandatory
    # action marked explicit must not lapse via low-risk non-response.
    tid, pid = approval_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        repo = ApprovalRepository(session, TenantContext(tid))
        a = await repo.request(
            project_id=pid,
            action="run_tests",
            risk_tier="low",
            requested_by="u",
            requires_explicit_approval=True,
        )
        await repo.expire_if_overdue(approval_id=a.id, now=a.requested_at + _DAY)
        assert (await repo.get(a.id)).status == "pending"
        assert await repo.is_blocked(pid, "run_tests") is True
        await repo.approve(approval_id=a.id, actor="boss")
        assert await repo.is_blocked(pid, "run_tests") is False


@pytest_asyncio.fixture
async def two_approval_tenants(admin_engine):
    """Two tenants, each with a project; tenant B also has a seeded approval."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org_id = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('ApvRLS',:s) RETURNING id"),
                {"s": f"apv-rls-{sfx}"},
            )
        ).scalar_one()
        out = {}
        for label in ("a", "b"):
            t = (
                await c.execute(
                    text(
                        "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id"
                    ),
                    {"o": org_id, "n": label, "s": f"apv-{label}-{sfx}"},
                )
            ).scalar_one()
            p = (
                await c.execute(
                    text(
                        "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id"
                    ),
                    {"t": t, "s": f"apv-{label}-proj-{sfx}"},
                )
            ).scalar_one()
            out[label] = {"tenant": t, "project": p}
        # tenant B gets an approval (so approval_events cross-tenant write has a target).
        b_approval = (
            await c.execute(
                text(
                    "INSERT INTO approvals (tenant_id, project_id, action, risk_tier, "
                    "requires_explicit_approval, requested_by) "
                    "VALUES (:t,:p,'run_tests','low',false,'u') RETURNING id"
                ),
                {"t": out["b"]["tenant"], "p": out["b"]["project"]},
            )
        ).scalar_one()
        out["b"]["approval"] = b_approval
    return out


@pytest.mark.db
async def test_approvals_cross_tenant_write_blocked(rls_engine, two_approval_tenants):
    a, b = two_approval_tenants["a"], two_approval_tenants["b"]

    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(a["tenant"])},
                )
                # GUC=A; write an approval for tenant B (valid composite FK) -> WITH CHECK.
                await conn.execute(
                    text(
                        "INSERT INTO approvals (tenant_id, project_id, action, risk_tier, "
                        "requires_explicit_approval, requested_by) "
                        "VALUES (:t,:p,'run_tests','low',false,'u')"
                    ),
                    {"t": str(b["tenant"]), "p": str(b["project"])},
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


@pytest.mark.db
async def test_approval_events_cross_tenant_write_blocked(rls_engine, two_approval_tenants):
    a, b = two_approval_tenants["a"], two_approval_tenants["b"]

    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(a["tenant"])},
                )
                # GUC=A; write an event for tenant B's approval -> WITH CHECK violation.
                await conn.execute(
                    text(
                        "INSERT INTO approval_events (tenant_id, approval_id, event_type, actor) "
                        "VALUES (:t,:ap,'requested','u')"
                    ),
                    {"t": str(b["tenant"]), "ap": str(b["approval"])},
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()
