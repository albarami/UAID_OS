"""Risk-acceptance record store tests (Slice 22, spec §24.1 / §27.10).

Fail-closed and non-authorizing: hard-refusal categories are rejected, signer identity is
caller-supplied-unverified, expiry is required, lifecycle is one-way, and records never enable
go-live. Docker-free for the pure validators; ``db`` for the tenant-owned store (RLS, append-only
events, record immutability guard, audit safe-metadata).
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.risk_acceptance import (
    APPROVAL_AUTHORITY_SOURCE,
    HARD_REFUSAL_CATEGORIES,
    SEVERITIES,
    InvalidRiskAcceptance,
    is_hard_refusal,
    validate_new_record,
    validate_transition,
)

_FUTURE = date(2099, 1, 1)
_PAST = date(2000, 1, 1)

_REQUIRED = (
    "release_id", "issue_id", "severity", "reason_for_acceptance", "business_impact",
    "rollback_or_mitigation_plan", "required_follow_up_ticket", "expiry_date", "owner",
    "approver", "accepted_by", "approval_authority_source",
)


def _valid(**over) -> dict:
    rec = {
        "release_id": "REL-1",
        "issue_id": "ISSUE-1",
        "severity": "medium",
        "reason_for_acceptance": "known non-critical limitation",
        "business_impact": "export unavailable until next release",
        "rollback_or_mitigation_plan": "documented manual export",
        "required_follow_up_ticket": "APP-219",
        "expiry_date": _FUTURE,
        "owner": "product_owner",
        "approver": "release_manager",
        "accepted_by": ["product_owner", "release_manager"],
        "approval_authority_source": APPROVAL_AUTHORITY_SOURCE,
        "affected_requirements": ["REQ-1"],
        "compensating_controls": ["weekly manual export"],
        "evidence_links": ["https://example/ticket/APP-219"],
        "included_in_release_notes": True,
        "blocking_category": None,
    }
    rec.update(over)
    return rec


# --- Docker-free: pure validators ---------------------------------------------


def test_valid_record_accepted():
    validate_new_record(_valid())  # no raise


def test_missing_expiry_rejected():
    rec = _valid()
    del rec["expiry_date"]
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(rec)
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(_valid(expiry_date=None))


def test_invalid_severity_rejected():
    assert "urgent" not in SEVERITIES
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(_valid(severity="urgent"))


@pytest.mark.parametrize("category", HARD_REFUSAL_CATEGORIES)
def test_hard_refusal_category_rejected(category):
    assert is_hard_refusal(category)
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(_valid(blocking_category=category))


def test_lifecycle_transitions():
    # active -> terminal states allowed
    for term in ("expired", "revoked", "superseded"):
        validate_transition("active", term)  # no raise
    # terminal -> anything is invalid; active -> active invalid
    for bad in (
        ("active", "active"),
        ("revoked", "active"),
        ("expired", "revoked"),
        ("superseded", "expired"),
        ("revoked", "superseded"),
    ):
        with pytest.raises(InvalidRiskAcceptance):
            validate_transition(*bad)


@pytest.mark.parametrize("field", _REQUIRED)
def test_required_fields_enforced(field):
    # missing
    rec = _valid()
    del rec[field]
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(rec)
    # empty (string/list)
    empty = [] if field == "accepted_by" else ""
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(_valid(**{field: empty}))


def test_accepted_by_must_be_nonempty_list_and_authority_must_be_approval_matrix():
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(_valid(accepted_by=[]))
    with pytest.raises(InvalidRiskAcceptance):
        validate_new_record(_valid(approval_authority_source="self"))


# --- DB-backed: store + lifecycle + RLS + immutability ------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def ra_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c, "INSERT INTO organizations (name, slug) VALUES ('RaOrg',:s) RETURNING id",
            s=f"ra-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c, "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org, n=label, s=f"ra-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c, "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn], s=f"ra-{proj}-{sfx}",
            )
    return out


def _repo(session, ctx):
    from app.repositories.risk_acceptance import RiskAcceptanceRepository

    return RiskAcceptanceRepository(session, ctx)


@pytest.mark.db
async def test_create_persists_active_and_audits_safely(ra_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    secret = "SENSITIVE-business-impact-should-not-leak"
    async with tenant_scope(ctx) as session:
        rec = await _repo(session, ctx).create(
            project_id=p1, payload=_valid(business_impact=secret), actor="planner"
        )
        rid = rec.id
        assert rec.status == "active"
        assert rec.approver_provenance == "caller_supplied_unverified"
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"risk_acceptance_record:{rid}", "t": t1},
            )
        ).one()
    assert actor == "planner"
    blob = str(payload)
    assert secret not in blob  # no business_impact prose in audit
    assert "reason_for_acceptance" not in payload and "business_impact" not in payload


@pytest.mark.db
async def test_revoke_and_supersede_are_one_way(ra_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        r1 = await repo.create(project_id=p1, payload=_valid(), actor="a")
        revoked = await repo.revoke(record_id=r1.id, actor="rm")
        assert revoked.status == "revoked"
        # terminal -> re-transition refused
        with pytest.raises(Exception):
            await repo.supersede(record_id=r1.id, actor="rm")
        r2 = await repo.create(project_id=p1, payload=_valid(issue_id="ISSUE-2"), actor="a")
        sup = await repo.supersede(record_id=r2.id, actor="rm")
        assert sup.status == "superseded"


@pytest.mark.db
async def test_expire_if_overdue(ra_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        r = await repo.create(project_id=p1, payload=_valid(expiry_date=_PAST), actor="a")
        expired = await repo.expire_if_overdue(record_id=r.id, actor="sys")
        assert expired.status == "expired"
        # not counted
        assert await repo.count_active_nonblocking(p1) == 0


@pytest.mark.db
async def test_hard_refusal_rejected_at_store_time(ra_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        with pytest.raises(InvalidRiskAcceptance):
            await repo.create(
                project_id=p1,
                payload=_valid(blocking_category="critical_security_blocker"),
                actor="a",
            )


@pytest.mark.db
async def test_count_active_nonblocking(ra_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        await repo.create(project_id=p1, payload=_valid(issue_id="A"), actor="a")  # counts
        revoked = await repo.create(project_id=p1, payload=_valid(issue_id="B"), actor="a")
        await repo.revoke(record_id=revoked.id, actor="a")  # not counted
        await repo.create(project_id=p1, payload=_valid(issue_id="C", expiry_date=_PAST), actor="a")
        # past-expiry record is not active-nonblocking even before expire_if_overdue runs
        assert await repo.count_active_nonblocking(p1) == 1


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant(ra_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = ra_ctx["t1"], ra_ctx["t2"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM risk_acceptance_records"))
            ).scalar_one()
            assert n == 0  # deny-by-default (no GUC)
    # tenant t2 sees none of t1's records
    async with tenant_scope(TenantContext(t2)) as session:
        assert await _repo(session, TenantContext(t2)).count_active_nonblocking(p1) == 0
    # tenant t2 cannot CREATE a record for tenant t1's project (composite FK / RLS WITH CHECK)
    with pytest.raises(Exception):
        async with tenant_scope(TenantContext(t2)) as session:
            await _repo(session, TenantContext(t2)).create(
                project_id=p1, payload=_valid(), actor="attacker"
            )


@pytest.mark.db
async def test_append_only_and_immutable_columns(ra_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        rec = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        rid = rec.id
    # mutating an immutable column (severity) is refused by the guard trigger
    for verb_sql in (
        "UPDATE risk_acceptance_records SET severity='high' WHERE id=:i",
        "DELETE FROM risk_acceptance_records WHERE id=:i",
        "DELETE FROM risk_acceptance_events WHERE record_id=:i",
    ):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb_sql), {"i": str(rid)})
        msg = str(ei.value).lower()
        assert (
            "only status and updated_at are mutable" in msg
            or "append-only" in msg
            or "does not allow delete" in msg
            or "denied" in msg
            or "permission" in msg
        )


_RAW_INSERT = (
    "INSERT INTO risk_acceptance_records "
    "(tenant_id, project_id, release_id, issue_id, severity, reason_for_acceptance, "
    " business_impact, rollback_or_mitigation_plan, required_follow_up_ticket, expiry_date, "
    " owner, approver, accepted_by, approval_authority_source, status, blocking_category) "
    "VALUES (:t,:p,'R','I','low','r','b','rb','T-1',:exp,'o','a','[\"o\"]'::jsonb,"
    " 'approval_matrix',:status,:blocking)"
)


@pytest.mark.db
async def test_db_guard_rejects_bad_inserts(ra_ctx, rls_engine):
    # Direct runtime SQL (uaid_app has INSERT) must still be refused by the guard.
    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    for status, blocking in (("revoked", None), ("active", "critical_security_blocker")):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(
                        text(_RAW_INSERT),
                        {"t": str(t1), "p": str(p1), "exp": _FUTURE,
                         "status": status, "blocking": blocking},
                    )
        msg = str(ei.value).lower()
        assert "status=active" in msg or "hard-refusal" in msg


@pytest.mark.db
async def test_db_guard_rejects_bad_status_transitions(ra_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ra_ctx["t1"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        rec = await repo.create(project_id=p1, payload=_valid(), actor="a")
        await repo.revoke(record_id=rec.id, actor="a")
        rid = rec.id
    # confirm the revoke committed (cross-connection) before testing the transition guard
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            st = (
                await conn.execute(
                    text("SELECT status FROM risk_acceptance_records WHERE id=:i"), {"i": str(rid)}
                )
            ).scalar_one()
    assert st == "revoked"
    # terminal (revoked) cannot transition again, via direct SQL
    for target in ("active", "superseded"):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(
                        text("UPDATE risk_acceptance_records SET status=:s WHERE id=:i"),
                        {"s": target, "i": str(rid)},
                    )
        assert "invalid status transition" in str(ei.value).lower()


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        for table, expected in (
            ("risk_acceptance_records", {"SELECT", "INSERT", "UPDATE"}),
            ("risk_acceptance_events", {"SELECT", "INSERT"}),
        ):
            grants = {
                r[0]
                for r in (
                    await c.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:tb AND grantee='uaid_app'"
                        ),
                        {"tb": table},
                    )
                ).all()
            }
            assert grants == expected, table
            rls = (
                await c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": table},
                )
            ).one()
            assert rls == (True, True), table
