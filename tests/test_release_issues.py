"""Open-issue / blocker store tests (Slice 24, spec §24.1 / §24.2 / Appendix B #7).

Deterministic, tenant-owned release-blocker issues. Fail-closed and non-authorizing:
- ``issue_category`` ∈ the 10-value §24.1/Appendix-B gate-axis set; ``other`` requires summary+detail.
- ``severity='critical'`` implies ``blocking=true`` (critical rows cannot masquerade as non-blocking)
  — refused at the pure validator AND the DB-guard INSERT.
- One-way lifecycle ``open`` → ``resolved`` | ``accepted`` | ``superseded`` (no ``false_positive``).
- ``accepted`` ALWAYS requires a usable ``risk_acceptance_records`` link (active + non-expired +
  non-blocking + same tenant/project + ``issue_id == issue.id``); hard blockers (critical OR a
  hard-refusal ``blocking_category``) can never be accepted.
Docker-free for the pure validators; ``db`` for the store (RLS, append-only events, per-transition
DB guard, audit safe-metadata). Gate #7 never passes.
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.issues import (
    ISSUE_CATEGORIES,
    SEVERITIES,
    STATUSES,
    InvalidIssue,
    is_critical,
    is_hard_blocker,
    validate_new_issue,
    validate_transition,
)
from app.release.risk_acceptance import HARD_REFUSAL_CATEGORIES

_REQUIRED = ("issue_category", "severity", "blocking", "summary", "source")


def _valid(**over) -> dict:
    rec = {
        "issue_category": "security",
        "severity": "high",
        "blocking": True,
        "summary": "unresolved authz gap blocks release",
        "detail": "export endpoint lacks an authz check; tracked as a release blocker",
        "source": "manual",
    }
    rec.update(over)
    return rec


# --- Docker-free: pure validators ---------------------------------------------


def test_valid_issue_per_category():
    for cat in ISSUE_CATEGORIES:
        rec = _valid(issue_category=cat)
        if cat == "other":
            rec.update(summary="s", detail="d")  # other needs both
        validate_new_issue(rec)


@pytest.mark.parametrize("field", _REQUIRED)
def test_required_fields_enforced(field):
    rec = _valid()
    del rec[field]
    with pytest.raises(InvalidIssue):
        validate_new_issue(rec)
    # empty value rejected too (blocking handled separately — it is a bool)
    if field != "blocking":
        with pytest.raises(InvalidIssue):
            validate_new_issue(_valid(**{field: ""}))


def test_bad_issue_category_rejected():
    assert "blocker" not in ISSUE_CATEGORIES  # 'blocker' is the boolean axis, not a category
    with pytest.raises(InvalidIssue):
        validate_new_issue(_valid(issue_category="perf"))


def test_bad_severity_rejected():
    with pytest.raises(InvalidIssue):
        validate_new_issue(_valid(severity="blocker"))


def test_other_requires_summary_and_detail():
    validate_new_issue(_valid(issue_category="other"))  # has summary + detail ⇒ ok
    with pytest.raises(InvalidIssue):
        validate_new_issue(_valid(issue_category="other", detail=""))
    with pytest.raises(InvalidIssue):
        validate_new_issue(_valid(issue_category="other", summary=""))


def test_critical_implies_blocking():
    # critical rows cannot be created non-blocking (fail-closed)
    validate_new_issue(_valid(severity="critical", blocking=True))
    with pytest.raises(InvalidIssue):
        validate_new_issue(_valid(severity="critical", blocking=False))


def test_hard_refusal_category_implies_blocking():
    # a hard-refusal blocking_category cannot masquerade as non-blocking (would dodge the gate count)
    for cat in HARD_REFUSAL_CATEGORIES:
        validate_new_issue(_valid(severity="high", blocking_category=cat, blocking=True))  # ok
        with pytest.raises(InvalidIssue):
            validate_new_issue(_valid(severity="high", blocking_category=cat, blocking=False))
    # a benign (non-hard-refusal) category may be non-blocking
    validate_new_issue(_valid(severity="high", blocking_category="advisory", blocking=False))


def test_blocking_must_be_bool():
    with pytest.raises(InvalidIssue):
        validate_new_issue(_valid(blocking="yes"))


def test_lifecycle_transitions():
    for term in ("resolved", "accepted", "superseded"):
        validate_transition("open", term)
    for bad in (
        ("open", "open"),
        ("open", "false_positive"),  # not a Slice-24 status
        ("resolved", "accepted"),
        ("accepted", "resolved"),
        ("superseded", "open"),
    ):
        with pytest.raises(InvalidIssue):
            validate_transition(*bad)


def test_is_critical_and_hard_blocker():
    assert is_critical("critical") and not is_critical("high")
    # critical ⇒ hard blocker regardless of category
    assert is_hard_blocker("critical", None)
    # any hard-refusal category ⇒ hard blocker regardless of severity
    for cat in HARD_REFUSAL_CATEGORIES:
        assert is_hard_blocker("low", cat)
    # benign, non-critical ⇒ not a hard blocker
    assert not is_hard_blocker("high", None)
    assert not is_hard_blocker("high", "advisory")


def test_statuses_constant():
    assert STATUSES == ("open", "resolved", "accepted", "superseded")
    assert "false_positive" not in STATUSES
    assert "blocker" not in SEVERITIES


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def ri_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('RiOrg',:s) RETURNING id",
            s=f"ri-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"ri-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p1b", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"ri-{proj}-{sfx}",
            )
    return out


def _repo(session, ctx):
    from app.repositories.release_issues import ReleaseIssueRepository

    return ReleaseIssueRepository(session, ctx)


async def _make_ra_record(session, ctx, project_id, ref_id, **over):
    """Create a risk-acceptance record whose issue_id references the issue (``ref_id``)."""
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.risk_acceptance import RiskAcceptanceRepository

    candidates = ReleaseCandidateRepository(session, ctx)
    release_ref = f"REL-{uuid.uuid4().hex[:12]}"
    candidate = await candidates.create(
        project_id=project_id, payload={"release_ref": release_ref}, actor="planner"
    )
    await candidates.bind_issue(
        candidate_id=candidate.id, release_issue_id=ref_id, actor="planner"
    )
    await candidates.freeze(candidate_id=candidate.id, actor="planner")
    payload = {
        "release_id": release_ref,
        "issue_id": str(ref_id),
        "subject_type": "release_issue",
        "severity": "high",
        "reason_for_acceptance": "accepted risk",
        "business_impact": "minor",
        "rollback_or_mitigation_plan": "documented",
        "required_follow_up_ticket": "T-1",
        "expiry_date": date(2099, 1, 1),
        "owner": "po",
        "approver": "rm",
        "accepted_by": ["po", "rm"],
        "approval_authority_source": "approval_matrix",
    }
    payload.update(over)
    return await RiskAcceptanceRepository(session, ctx).create(
        project_id=project_id, payload=payload, actor="planner"
    )


# --- DB-backed: repository ----------------------------------------------------


@pytest.mark.db
async def test_create_open_and_audit_safe(ri_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    secret = "SENSITIVE-detail-should-not-leak"
    async with tenant_scope(ctx) as session:
        i = await _repo(session, ctx).create(
            project_id=p1, payload=_valid(detail=secret), actor="rev"
        )
        iid = i.id
        assert i.status == "open" and i.source_provenance == "caller_supplied_unverified"
        assert i.blocking is True
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"release_issue:{iid}", "t": t1},
            )
        ).one()
    assert actor == "rev"
    blob = str(payload)
    assert secret not in blob
    assert "summary" not in payload and "detail" not in payload
    assert "resolution_note" not in payload and "blocking_category" not in payload


@pytest.mark.db
async def test_resolve_and_supersede(ri_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        i = await repo.create(project_id=p1, payload=_valid(), actor="a")
        out = await repo.resolve(
            issue_id=i.id, resolution_note="fixed", resolved_by="dev", actor="dev"
        )
        assert out.status == "resolved" and out.resolved_by == "dev"
        i2 = await repo.create(project_id=p1, payload=_valid(), actor="a")
        sup = await repo.supersede(
            issue_id=i2.id, resolution_note="replaced", resolved_by="dev", actor="dev"
        )
        assert sup.status == "superseded"


@pytest.mark.db
async def test_accept_noncritical_with_valid_record(ri_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        i = await repo.create(project_id=p1, payload=_valid(severity="high"), actor="a")
        rec = await _make_ra_record(session, ctx, p1, i.id)
        accepted = await repo.accept(issue_id=i.id, risk_acceptance_record_id=rec.id, actor="rm")
        assert accepted.status == "accepted" and accepted.risk_acceptance_record_id == rec.id


@pytest.mark.db
async def test_reject_critical_accept(ri_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        i = await repo.create(project_id=p1, payload=_valid(severity="critical"), actor="a")
        rec = await _make_ra_record(session, ctx, p1, i.id, severity="high")
        with pytest.raises(Exception):
            await repo.accept(issue_id=i.id, risk_acceptance_record_id=rec.id, actor="rm")


@pytest.mark.db
async def test_reject_hard_refusal_category_accept(ri_ctx):
    # A non-critical issue carrying a hard-refusal blocking_category can never be accepted.
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        i = await repo.create(
            project_id=p1,
            payload=_valid(severity="high", blocking_category="critical_security_blocker"),
            actor="a",
        )
        rec = await _make_ra_record(session, ctx, p1, i.id)
        with pytest.raises(Exception):
            await repo.accept(issue_id=i.id, risk_acceptance_record_id=rec.id, actor="rm")


@pytest.mark.db
async def test_reject_accept_with_expired_record(ri_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        i = await repo.create(project_id=p1, payload=_valid(severity="high"), actor="a")
        rec = await _make_ra_record(session, ctx, p1, i.id, expiry_date=date(2000, 1, 1))
        with pytest.raises(Exception):
            await repo.accept(issue_id=i.id, risk_acceptance_record_id=rec.id, actor="rm")


@pytest.mark.db
async def test_counts_open_blocking_and_unaccepted(ri_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        # open blocking (high), open non-blocking, then one resolved and one accepted blocking
        await repo.create(project_id=p1, payload=_valid(severity="high", blocking=True), actor="a")
        await repo.create(project_id=p1, payload=_valid(severity="low", blocking=False), actor="a")
        r = await repo.create(project_id=p1, payload=_valid(severity="high"), actor="a")
        await repo.resolve(issue_id=r.id, resolution_note="x", resolved_by="d", actor="d")
        acc = await repo.create(project_id=p1, payload=_valid(severity="high"), actor="a")
        rec = await _make_ra_record(session, ctx, p1, acc.id)
        await repo.accept(issue_id=acc.id, risk_acceptance_record_id=rec.id, actor="rm")
        assert await repo.count_open(p1) == 2  # the high-blocking + low-nonblocking
        assert await repo.count_open_blocking(p1) == 1
        # open ⟹ not accepted, so this equals count_open_blocking (documented equivalence)
        assert await repo.count_open_unaccepted_blocking(p1) == 1


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant(ri_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = ri_ctx["t1"], ri_ctx["t2"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (await conn.execute(text("SELECT count(*) FROM release_issues"))).scalar_one()
            assert n == 0
    async with tenant_scope(TenantContext(t2)) as session:
        assert await _repo(session, TenantContext(t2)).count_open(p1) == 0


# --- DB-backed: guard (direct SQL refusals) -----------------------------------

_RAW_INSERT = (
    "INSERT INTO release_issues "
    "(tenant_id, project_id, issue_category, severity, blocking, blocking_category, summary, detail, "
    " source, status, resolution_note, risk_acceptance_record_id) "
    "VALUES (:t,:p,:cat,:sev,:blocking,:bcat,:summary,:detail,'manual',:status,:rnote,:raid)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    params = {
        "t": str(t1),
        "p": str(p1),
        "cat": "security",
        "sev": "high",
        "blocking": True,
        "bcat": None,
        "summary": "s",
        "detail": "d",
        "status": "open",
        "rnote": None,
        "raid": None,
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(_RAW_INSERT), params)


@pytest.mark.db
async def test_guard_rejects_bad_status_insert(ri_ctx, rls_engine):
    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, status="resolved")


@pytest.mark.db
async def test_guard_rejects_other_without_detail(ri_ctx, rls_engine):
    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, cat="other", detail="")


@pytest.mark.db
async def test_guard_rejects_resolution_metadata_on_insert(ri_ctx, rls_engine):
    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, rnote="prefilled")


@pytest.mark.db
async def test_guard_rejects_critical_nonblocking_insert(ri_ctx, rls_engine):
    # critical ⇒ blocking enforced at the DB layer too
    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, sev="critical", blocking=False)


@pytest.mark.db
async def test_guard_rejects_hard_refusal_category_nonblocking_insert(ri_ctx, rls_engine):
    # a hard-refusal blocking_category ⇒ blocking enforced at the DB layer (cannot dodge the count)
    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    for cat in HARD_REFUSAL_CATEGORIES:
        with pytest.raises(Exception):
            await _raw_insert(rls_engine, t1, p1, sev="high", blocking=False, bcat=cat)


async def _direct_sql(rls_engine, t1, sql, **params):
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(sql), params)


_ACCEPT_SQL = (
    "UPDATE release_issues SET status='accepted', risk_acceptance_record_id=:rid WHERE id=:iid"
)


@pytest.mark.db
async def test_guard_rejects_updated_at_only_update(ri_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        i = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        iid = i.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "UPDATE release_issues SET updated_at=clock_timestamp() WHERE id=:i",
            i=str(iid),
        )


@pytest.mark.db
async def test_guard_rejects_terminal_retransition(ri_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        i = await repo.create(project_id=p1, payload=_valid(), actor="a")
        await repo.resolve(issue_id=i.id, resolution_note="x", resolved_by="d", actor="d")
        iid = i.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine, t1, "UPDATE release_issues SET status='superseded' WHERE id=:i", i=str(iid)
        )


@pytest.mark.db
async def test_guard_rejects_critical_accept_via_direct_sql(ri_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        i = await _repo(session, ctx).create(
            project_id=p1, payload=_valid(severity="critical"), actor="a"
        )
        iid = i.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine, t1, "UPDATE release_issues SET status='accepted' WHERE id=:i", i=str(iid)
        )


@pytest.mark.db
async def test_guard_rejects_hard_refusal_accept_via_direct_sql(ri_ctx, rls_engine):
    # The DB guard (not just the repo) refuses accepting a non-critical hard-refusal-category issue,
    # even with an otherwise-usable risk-acceptance record.
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        i = await _repo(session, ctx).create(
            project_id=p1,
            payload=_valid(severity="high", blocking_category="critical_security_blocker"),
            actor="a",
        )
        rec = await _make_ra_record(session, ctx, p1, i.id)
        iid, rid = i.id, rec.id
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rid), iid=str(iid))


@pytest.mark.db
async def test_guard_rejects_accept_without_record(ri_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        i = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        iid = i.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine, t1, "UPDATE release_issues SET status='accepted' WHERE id=:i", i=str(iid)
        )


@pytest.mark.db
async def test_guard_rejects_accept_with_invalid_records(ri_ctx, rls_engine):
    # The DB guard itself (not just the repo) enforces the usable-record predicate.
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p1b = ri_ctx["t1"], ri_ctx["p1"], ri_ctx["p1b"]
    ctx = TenantContext(t1)

    async def _issue_and_record(*, rec_project, rec_over):
        async with tenant_scope(ctx) as session:
            i = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
            rec = await _make_ra_record(session, ctx, rec_project, i.id, **rec_over)
            return i.id, rec

    # expired record
    iid, rec = await _issue_and_record(rec_project=p1, rec_over={"expiry_date": date(2000, 1, 1)})
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rec.id), iid=str(iid))

    # non-active (revoked) record
    async with tenant_scope(ctx) as session:
        i = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        rec = await _make_ra_record(session, ctx, p1, i.id)
        await RiskAcceptanceRepository(session, ctx).revoke(record_id=rec.id, actor="a")
        iid, rid = i.id, rec.id
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rid), iid=str(iid))

    # blocking_category set on the record (blocks acceptance)
    iid, rec = await _issue_and_record(rec_project=p1, rec_over={"blocking_category": "advisory"})
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rec.id), iid=str(iid))

    # same-tenant wrong project (record under p1b, issue under p1)
    with pytest.raises(Exception):
        await _issue_and_record(rec_project=p1b, rec_over={})

    # issue_id != issue.id
    with pytest.raises(Exception):
        await _issue_and_record(
            rec_project=p1, rec_over={"issue_id": str(uuid.uuid4())}
        )


@pytest.mark.db
async def test_guard_rejects_cross_tenant_record_via_direct_sql(ri_ctx, rls_engine):
    # A t1 issue cannot reference a t2 record by id (composite FK (rec_id, tenant_id) has no row).
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1, px = ri_ctx["t1"], ri_ctx["t2"], ri_ctx["p1"], ri_ctx["px"]
    async with tenant_scope(TenantContext(t1)) as session:
        i = await _repo(session, TenantContext(t1)).create(
            project_id=p1, payload=_valid(), actor="a"
        )
        iid = i.id
    async with tenant_scope(TenantContext(t2)) as session:
        other = await _repo(session, TenantContext(t2)).create(
            project_id=px, payload=_valid(), actor="a"
        )
        rec = await _make_ra_record(session, TenantContext(t2), px, other.id)
        rid = rec.id
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rid), iid=str(iid))


@pytest.mark.db
async def test_append_only_and_no_delete(ri_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = ri_ctx["t1"], ri_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        i = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        iid = i.id
    for verb in (
        "UPDATE release_issues SET severity='low' WHERE id=:i",
        "DELETE FROM release_issues WHERE id=:i",
        "DELETE FROM release_issue_events WHERE issue_id=:i",
        "UPDATE release_issue_events SET actor='x' WHERE issue_id=:i",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb), {"i": str(iid)})


@pytest.mark.db
async def test_truncate_refused_both_tables(ri_ctx, rls_engine):
    # Runtime SQL (uaid_app) cannot TRUNCATE either table (REVOKE + BEFORE TRUNCATE trigger).
    t1 = ri_ctx["t1"]
    for stmt in ("TRUNCATE release_issues", "TRUNCATE release_issue_events"):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(stmt))


@pytest.mark.db
async def test_cross_tenant_accept_refused(ri_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1, px = ri_ctx["t1"], ri_ctx["t2"], ri_ctx["p1"], ri_ctx["px"]
    ctx1 = TenantContext(t1)
    async with tenant_scope(ctx1) as session:
        i = await _repo(session, ctx1).create(project_id=p1, payload=_valid(), actor="a")
        iid = i.id
    async with tenant_scope(TenantContext(t2)) as session:
        other = await _repo(session, TenantContext(t2)).create(
            project_id=px, payload=_valid(), actor="a"
        )
        rec = await _make_ra_record(session, TenantContext(t2), px, other.id)
        rid = rec.id
    with pytest.raises(Exception):
        async with tenant_scope(ctx1) as session:
            await _repo(session, ctx1).accept(
                issue_id=iid, risk_acceptance_record_id=rid, actor="rm"
            )


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        for table, expected in (
            ("release_issues", {"SELECT", "INSERT", "UPDATE"}),
            ("release_issue_events", {"SELECT", "INSERT"}),
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
