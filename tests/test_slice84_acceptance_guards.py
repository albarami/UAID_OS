"""Slice 84 / F-021 acceptance-guard probes (critical accept + wrong project/subject)."""

from __future__ import annotations

import re
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.slice84_support import (
    CRITICAL_CANNOT_ACCEPT,
    DB_CRITICAL_CANNOT_ACCEPT,
    FINDING_ACCEPT_SQL,
    ISSUE_ACCEPT_SQL,
    NO_USABLE_RECORD_FINDING,
    NO_USABLE_RECORD_ISSUE,
    assert_acceptance_guard,
    build_valid_finding_graph,
    build_valid_issue_graph,
    disabled_trigger,
    err_text,
    expect_db_error,
    runtime_sql,
    seed_s84_ctx,
    trigger_fire_state,
)


@pytest_asyncio.fixture
async def s84_ctx(admin_engine):
    return await seed_s84_ctx(admin_engine)


async def run_reject_critical_accept(rf_ctx) -> tuple:
    """Direct ``accept()`` on a critical finding with a separately valid RA record."""
    from app.release.findings import InvalidFinding
    from app.tenancy import TenantContext, tenant_scope
    from tests.test_release_findings import (
        _make_ra_record,
        _repo,
        _trusted_security_finding,
    )

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        critical = await _trusted_security_finding(session, ctx, p1, severity="critical")
        other = await _trusted_security_finding(session, ctx, p1, severity="high")
        rec = await _make_ra_record(session, ctx, p1, other.id)
        with pytest.raises(InvalidFinding, match=re.escape(CRITICAL_CANNOT_ACCEPT)):
            await _repo(session, ctx).accept(
                finding_id=critical.id, risk_acceptance_record_id=rec.id, actor="rm"
            )
        row = await _repo(session, ctx).get(critical.id)
        assert row is not None and row.status == "open"
        return critical.id, rec.id, t1


async def run_findings_invalid_record_accepts(rf_ctx, rls_engine) -> None:
    """Expired/revoked/blocking plus separately valid wrong-project/wrong-subject."""
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope
    from tests.test_release_findings import _make_ra_record, _trusted_security_finding

    t1, p1, p1b = rf_ctx["t1"], rf_ctx["p1"], rf_ctx["p1b"]
    ctx = TenantContext(t1)

    async def finding_and_record(*, rec_project, rec_over):
        async with tenant_scope(ctx) as session:
            finding = await _trusted_security_finding(session, ctx, p1)
            rec = await _make_ra_record(session, ctx, rec_project, finding.id, **rec_over)
            return finding.id, rec

    fid, rec = await finding_and_record(rec_project=p1, rec_over={"expiry_date": date(2000, 1, 1)})
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rec.id), fid=str(fid))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_FINDING)

    async with tenant_scope(ctx) as session:
        finding = await _trusted_security_finding(session, ctx, p1)
        rec = await _make_ra_record(session, ctx, p1, finding.id)
        await RiskAcceptanceRepository(session, ctx).revoke(record_id=rec.id, actor="a")
        fid, rid = finding.id, rec.id
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rid), fid=str(fid))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_FINDING)

    fid, rec = await finding_and_record(rec_project=p1, rec_over={"blocking_category": "advisory"})
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rec.id), fid=str(fid))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_FINDING)

    # Wrong-project: foreign-project record refused by the acceptance guard (OD-4).
    async with tenant_scope(ctx) as session:
        fid_a, _ = await build_valid_finding_graph(session, ctx, p1)
    async with tenant_scope(ctx) as session:
        _fid_b, rec_b = await build_valid_finding_graph(session, ctx, p1b)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rec_b), fid=str(fid_a))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_FINDING)
    async with tenant_scope(ctx) as session:
        from tests.test_release_findings import _repo

        row = await _repo(session, ctx).get(fid_a)
        assert row is not None and row.status == "open"

    # Wrong-subject isolates the subject predicate (same project, different record).
    async with tenant_scope(ctx) as session:
        fid_a, _rec_a = await build_valid_finding_graph(session, ctx, p1)
        _fid_b, rec_b = await build_valid_finding_graph(session, ctx, p1)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rec_b), fid=str(fid_a))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_FINDING)
    async with tenant_scope(ctx) as session:
        from tests.test_release_findings import _repo

        row = await _repo(session, ctx).get(fid_a)
        assert row is not None and row.status == "open"


async def run_issues_invalid_record_accepts(ri_ctx, rls_engine) -> None:
    """Expired/revoked/blocking plus separately valid wrong-project/wrong-subject issues."""
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope
    from tests.test_release_issues import _make_ra_record, _repo, _valid

    t1, p1, p1b = ri_ctx["t1"], ri_ctx["p1"], ri_ctx["p1b"]
    ctx = TenantContext(t1)

    async def issue_and_record(*, rec_project, rec_over):
        async with tenant_scope(ctx) as session:
            issue = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
            rec = await _make_ra_record(session, ctx, rec_project, issue.id, **rec_over)
            return issue.id, rec

    iid, rec = await issue_and_record(rec_project=p1, rec_over={"expiry_date": date(2000, 1, 1)})
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, ISSUE_ACCEPT_SQL, rid=str(rec.id), iid=str(iid))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_ISSUE)

    async with tenant_scope(ctx) as session:
        issue = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        rec = await _make_ra_record(session, ctx, p1, issue.id)
        await RiskAcceptanceRepository(session, ctx).revoke(record_id=rec.id, actor="a")
        iid, rid = issue.id, rec.id
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, ISSUE_ACCEPT_SQL, rid=str(rid), iid=str(iid))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_ISSUE)

    iid, rec = await issue_and_record(rec_project=p1, rec_over={"blocking_category": "advisory"})
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, ISSUE_ACCEPT_SQL, rid=str(rec.id), iid=str(iid))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_ISSUE)

    async with tenant_scope(ctx) as session:
        iid_a, _ = await build_valid_issue_graph(session, ctx, p1)
    async with tenant_scope(ctx) as session:
        _iid_b, rec_b = await build_valid_issue_graph(session, ctx, p1b)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, ISSUE_ACCEPT_SQL, rid=str(rec_b), iid=str(iid_a))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_ISSUE)

    async with tenant_scope(ctx) as session:
        iid_a, _rec_a = await build_valid_issue_graph(session, ctx, p1)
        _iid_b, rec_b = await build_valid_issue_graph(session, ctx, p1)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, ISSUE_ACCEPT_SQL, rid=str(rec_b), iid=str(iid_a))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_ISSUE)


async def _event_count(session, finding_id) -> int:
    return (
        await session.execute(
            text("SELECT count(*) FROM release_finding_events WHERE finding_id=:i"),
            {"i": str(finding_id)},
        )
    ).scalar_one()


@pytest.mark.db
async def test_p_green_3a_direct_accept_writes_nothing_new(s84_ctx, admin_engine):
    """InvalidFinding from accept(); event count unchanged; no accepted event/audit."""
    from app.release.findings import InvalidFinding
    from app.tenancy import TenantContext, tenant_scope
    from tests.test_release_findings import (
        _make_ra_record,
        _repo,
        _trusted_security_finding,
    )

    t1, p1 = s84_ctx["t1"], s84_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        critical = await _trusted_security_finding(session, ctx, p1, severity="critical")
        other = await _trusted_security_finding(session, ctx, p1, severity="high")
        rec = await _make_ra_record(session, ctx, p1, other.id)
        before = await _event_count(session, critical.id)
        with pytest.raises(InvalidFinding, match=re.escape(CRITICAL_CANNOT_ACCEPT)):
            await _repo(session, ctx).accept(
                finding_id=critical.id, risk_acceptance_record_id=rec.id, actor="rm"
            )
        after = await _event_count(session, critical.id)
        assert after == before
        accepted = (
            await session.execute(
                text(
                    "SELECT count(*) FROM release_finding_events "
                    "WHERE finding_id=:i AND event_type='accepted'"
                ),
                {"i": str(critical.id)},
            )
        ).scalar_one()
        assert accepted == 0
    async with admin_engine.connect() as conn:
        audits = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE action='release.finding_accepted' AND target=:tg"
                ),
                {"tg": f"release_finding:{critical.id}"},
            )
        ).scalar_one()
    assert audits == 0
    async with tenant_scope(ctx) as session:
        row = await _repo(session, ctx).get(critical.id)
        assert row is not None and row.status == "open"


@pytest.mark.db
async def test_p_green_3b_db_guard_critical_with_record(s84_ctx, rls_engine):
    """Direct SQL accept of a critical finding with a valid record hits the DB guard."""
    from app.tenancy import TenantContext, tenant_scope
    from tests.test_release_findings import _make_ra_record, _trusted_security_finding

    t1, p1 = s84_ctx["t1"], s84_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        critical = await _trusted_security_finding(session, ctx, p1, severity="critical")
        other = await _trusted_security_finding(session, ctx, p1, severity="high")
        rec = await _make_ra_record(session, ctx, p1, other.id)
        cid, rid = critical.id, rec.id
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rid), fid=str(cid))
    expect_db_error(
        ei.value,
        DB_CRITICAL_CANNOT_ACCEPT,
        "P0001",
        absent=("accepted requires a risk_acceptance_record_id",),
    )


@pytest.mark.db
async def test_p_mut_3_disabling_findings_guard_unmasks_critical(s84_ctx, rls_engine, admin_engine):
    """Disable release_findings_guard; critical SQL must not name that message."""
    from app.tenancy import TenantContext, tenant_scope
    from tests.test_release_findings import _make_ra_record, _trusted_security_finding

    t1, p1 = s84_ctx["t1"], s84_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        critical = await _trusted_security_finding(session, ctx, p1, severity="critical")
        other = await _trusted_security_finding(session, ctx, p1, severity="high")
        rec = await _make_ra_record(session, ctx, p1, other.id)
        cid, rid = critical.id, rec.id
    async with disabled_trigger(admin_engine, "release_findings", "release_findings_guard"):
        async with rls_engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(t1)},
                )
                await conn.execute(text(FINDING_ACCEPT_SQL), {"rid": str(rid), "fid": str(cid)})
                msg = ""
            except Exception as exc:
                msg = err_text(exc)
            finally:
                await trans.rollback()
    assert await trigger_fire_state(admin_engine, "release_findings_guard") == "O"
    assert DB_CRITICAL_CANNOT_ACCEPT not in msg


@pytest.mark.db
async def test_p_green_4a_4b_findings_wrong_project_and_subject(s84_ctx, rls_engine):
    """Wrong-project and wrong-subject finding accepts; matching pair succeeds (rolled back)."""
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p1b = s84_ctx["t1"], s84_ctx["p1"], s84_ctx["p1b"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        fid_a, rec_a = await build_valid_finding_graph(session, ctx, p1)
    async with tenant_scope(ctx) as session:
        _fid_b, rec_b = await build_valid_finding_graph(session, ctx, p1b)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rec_b), fid=str(fid_a))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_FINDING)
    async with tenant_scope(ctx) as session:
        fid_c, rec_c = await build_valid_finding_graph(session, ctx, p1)
        fid_d, rec_d = await build_valid_finding_graph(session, ctx, p1)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, FINDING_ACCEPT_SQL, rid=str(rec_d), fid=str(fid_c))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_FINDING)
    async with rls_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(t1)},
            )
            result = await conn.execute(
                text(FINDING_ACCEPT_SQL), {"rid": str(rec_a), "fid": str(fid_a)}
            )
            assert result.rowcount == 1
        finally:
            await trans.rollback()


@pytest.mark.db
async def test_p_green_4c_4d_issues_wrong_project_and_subject(s84_ctx, rls_engine):
    """Wrong-project and wrong-subject issue accepts; matching pair succeeds (rolled back)."""
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p1b = s84_ctx["t1"], s84_ctx["p1"], s84_ctx["p1b"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        iid_a, rec_a = await build_valid_issue_graph(session, ctx, p1)
    async with tenant_scope(ctx) as session:
        _iid_b, rec_b = await build_valid_issue_graph(session, ctx, p1b)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, ISSUE_ACCEPT_SQL, rid=str(rec_b), iid=str(iid_a))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_ISSUE)
    async with tenant_scope(ctx) as session:
        iid_c, rec_c = await build_valid_issue_graph(session, ctx, p1)
        iid_d, rec_d = await build_valid_issue_graph(session, ctx, p1)
    with pytest.raises(Exception) as ei:
        await runtime_sql(rls_engine, t1, ISSUE_ACCEPT_SQL, rid=str(rec_d), iid=str(iid_c))
    assert_acceptance_guard(ei.value, NO_USABLE_RECORD_ISSUE)
    async with rls_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(t1)},
            )
            result = await conn.execute(
                text(ISSUE_ACCEPT_SQL), {"rid": str(rec_a), "iid": str(iid_a)}
            )
            assert result.rowcount == 1
        finally:
            await trans.rollback()


@pytest.mark.db
async def test_p_mut_4a_findings_guard_disabled(s84_ctx, rls_engine, admin_engine):
    """Disable release_findings_guard; wrong-project SQL must not name the usable-record text."""
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p1b = s84_ctx["t1"], s84_ctx["p1"], s84_ctx["p1b"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        fid_a, _ = await build_valid_finding_graph(session, ctx, p1)
    async with tenant_scope(ctx) as session:
        _fid_b, rec_b = await build_valid_finding_graph(session, ctx, p1b)
    async with disabled_trigger(admin_engine, "release_findings", "release_findings_guard"):
        async with rls_engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(t1)},
                )
                await conn.execute(text(FINDING_ACCEPT_SQL), {"rid": str(rec_b), "fid": str(fid_a)})
                observed = "success"
                msg = ""
            except Exception as exc:
                observed = "error"
                msg = err_text(exc)
            finally:
                await trans.rollback()
    assert await trigger_fire_state(admin_engine, "release_findings_guard") == "O"
    assert NO_USABLE_RECORD_FINDING not in msg
    # Quote whatever fired next (slice47 subject-kind guard, or success).
    assert observed in {"success", "error"}


@pytest.mark.db
async def test_p_mut_4b_issues_guard_disabled(s84_ctx, rls_engine, admin_engine):
    """Disable release_issues_guard; wrong-project SQL must not name the usable-record text."""
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p1b = s84_ctx["t1"], s84_ctx["p1"], s84_ctx["p1b"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        iid_a, _ = await build_valid_issue_graph(session, ctx, p1)
    async with tenant_scope(ctx) as session:
        _iid_b, rec_b = await build_valid_issue_graph(session, ctx, p1b)
    async with disabled_trigger(admin_engine, "release_issues", "release_issues_guard"):
        async with rls_engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(t1)},
                )
                await conn.execute(text(ISSUE_ACCEPT_SQL), {"rid": str(rec_b), "iid": str(iid_a)})
                msg = ""
            except Exception as exc:
                msg = err_text(exc)
            finally:
                await trans.rollback()
    assert await trigger_fire_state(admin_engine, "release_issues_guard") == "O"
    assert NO_USABLE_RECORD_ISSUE not in msg
