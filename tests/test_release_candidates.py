"""Release-candidate / release-binding store tests (Slice 25, spec §24.1 / Appendix B #7).

Deterministic, tenant-owned release candidates + freeze-locked issue bindings. Fail-closed and
non-authorizing:
- Lifecycle one-way: ``draft`` → ``frozen`` | ``canceled``; ``frozen`` → ``superseded`` | ``canceled``.
- ``frozen_at`` is set iff entering ``frozen``; identity is immutable; same-status update changes
  nothing (no out-of-band edits).
- Bindings are append-only and may be added **only while the candidate is ``draft``** (freeze locks
  membership); a binding's issue must be the same project; no unbind.
- Binding/declaring issues for a release does NOT assert the issue set is complete — gate #7 still
  never passes.
Docker-free for the pure validators; ``db`` for the store (RLS, append-only events, per-transition
DB guard, audit safe-metadata, A5 count helpers).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.release_candidates import (
    STATUSES,
    TERMINAL_STATUSES,
    InvalidReleaseCandidate,
    validate_new_candidate,
    validate_transition,
)


# --- Docker-free: pure validators ---------------------------------------------


def test_valid_candidate():
    validate_new_candidate({"release_ref": "REL-2026-06-15-001"})
    validate_new_candidate({"release_ref": "REL-1", "title": "June release"})


def test_release_ref_required():
    with pytest.raises(InvalidReleaseCandidate):
        validate_new_candidate({})
    with pytest.raises(InvalidReleaseCandidate):
        validate_new_candidate({"release_ref": ""})
    with pytest.raises(InvalidReleaseCandidate):
        validate_new_candidate({"release_ref": "   "})


def test_title_must_be_str_if_present():
    with pytest.raises(InvalidReleaseCandidate):
        validate_new_candidate({"release_ref": "REL-1", "title": 123})


def test_lifecycle_transitions():
    for ok in (
        ("draft", "frozen"),
        ("draft", "canceled"),
        ("frozen", "superseded"),
        ("frozen", "canceled"),
    ):
        validate_transition(*ok)
    for bad in (
        ("draft", "superseded"),
        ("draft", "draft"),
        ("frozen", "draft"),
        ("frozen", "frozen"),
        ("superseded", "canceled"),
        ("canceled", "frozen"),
        ("superseded", "superseded"),
    ):
        with pytest.raises(InvalidReleaseCandidate):
            validate_transition(*bad)


def test_status_constants():
    assert STATUSES == ("draft", "frozen", "superseded", "canceled")
    assert TERMINAL_STATUSES == ("superseded", "canceled")


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def rc_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('RcOrg',:s) RETURNING id",
            s=f"rc-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"rc-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p1b", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"rc-{proj}-{sfx}",
            )
    return out


def _repo(session, ctx):
    from app.repositories.release_candidates import ReleaseCandidateRepository

    return ReleaseCandidateRepository(session, ctx)


async def _make_issue(session, ctx, project_id, **over):
    from app.repositories.release_issues import ReleaseIssueRepository

    payload = {
        "issue_category": "deployment",
        "severity": "high",
        "blocking": True,
        "summary": "blocker",
        "detail": "d",
        "source": "manual",
    }
    payload.update(over)
    return await ReleaseIssueRepository(session, ctx).create(
        project_id=project_id, payload=payload, actor="a"
    )


# --- DB-backed: repository ----------------------------------------------------


@pytest.mark.db
async def test_create_freeze_and_audit_safe(rc_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    secret_title = "SENSITIVE-title-should-not-leak"
    async with tenant_scope(ctx) as session:
        rc = await _repo(session, ctx).create(
            project_id=p1, payload={"release_ref": "REL-1", "title": secret_title}, actor="rm"
        )
        rcid = rc.id
        assert rc.status == "draft" and rc.frozen_at is None
        frozen = await _repo(session, ctx).freeze(candidate_id=rcid, actor="rm")
        assert frozen.status == "frozen"
        # frozen_at is a DB-computed (clock_timestamp) column — re-fetch async to materialize it
        refetched = await _repo(session, ctx).get(rcid)
        assert refetched.frozen_at is not None
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"release_candidate:{rcid}", "t": t1},
            )
        ).one()
    blob = str(payload)
    assert secret_title not in blob and "title" not in payload
    assert "release_candidate_id" in payload and "status" in payload


@pytest.mark.db
async def test_cancel_from_draft_and_from_frozen(rc_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        d = await repo.create(project_id=p1, payload={"release_ref": "RC-D"}, actor="a")
        cd = await repo.cancel(candidate_id=d.id, actor="a")
        assert cd.status == "canceled"
        f = await repo.create(project_id=p1, payload={"release_ref": "RC-F"}, actor="a")
        await repo.freeze(candidate_id=f.id, actor="a")
        cf = await repo.cancel(candidate_id=f.id, actor="a")
        assert cf.status == "canceled"


@pytest.mark.db
async def test_supersede_from_frozen(rc_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        f = await repo.create(project_id=p1, payload={"release_ref": "RC-S"}, actor="a")
        await repo.freeze(candidate_id=f.id, actor="a")
        s = await repo.supersede(candidate_id=f.id, actor="a")
        assert s.status == "superseded"


@pytest.mark.db
async def test_bind_issue_in_draft_and_counts(rc_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        rc = await repo.create(project_id=p1, payload={"release_ref": "RC-B"}, actor="a")
        i_block = await _make_issue(session, ctx, p1, blocking=True, severity="high")
        i_nonblock = await _make_issue(session, ctx, p1, blocking=False, severity="low")
        await repo.bind_issue(candidate_id=rc.id, release_issue_id=i_block.id, actor="a")
        await repo.bind_issue(candidate_id=rc.id, release_issue_id=i_nonblock.id, actor="a")
        assert await repo.bound_open_issue_count(rc.id) == 2
        assert await repo.bound_open_blocking_issue_count(rc.id) == 1
        assert await repo.bound_open_unaccepted_blocking_issue_count(rc.id) == 1


@pytest.mark.db
async def test_count_frozen_and_latest_frozen_ordering(rc_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        assert await repo.count_frozen(p1) == 0
        first = await repo.create(project_id=p1, payload={"release_ref": "RC-1"}, actor="a")
        await repo.freeze(candidate_id=first.id, actor="a")
        second = await repo.create(project_id=p1, payload={"release_ref": "RC-2"}, actor="a")
        await repo.freeze(candidate_id=second.id, actor="a")
        assert await repo.count_frozen(p1) == 2
        latest = await repo.latest_frozen(p1)
        # ordering frozen_at DESC, created_at DESC, id DESC ⇒ the second-frozen candidate
        assert latest.id == second.id


@pytest.mark.db
async def test_rls_cross_tenant(rc_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = rc_ctx["t1"], rc_ctx["t2"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _repo(session, ctx).create(project_id=p1, payload={"release_ref": "RC-X"}, actor="a")
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (await conn.execute(text("SELECT count(*) FROM release_candidates"))).scalar_one()
            assert n == 0
    async with tenant_scope(TenantContext(t2)) as session:
        assert await _repo(session, TenantContext(t2)).count_frozen(p1) == 0


# --- DB-backed: guard (direct SQL refusals) -----------------------------------


async def _direct_sql(rls_engine, t1, sql, **params):
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(sql), params)


_RC_INSERT = (
    "INSERT INTO release_candidates (tenant_id, project_id, release_ref, status, frozen_at) "
    "VALUES (:t,:p,:ref,:status,:frozen_at)"
)


@pytest.mark.db
async def test_guard_rejects_bad_status_insert(rc_ctx, rls_engine):
    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            _RC_INSERT,
            t=str(t1),
            p=str(p1),
            ref="X",
            status="frozen",
            frozen_at=None,
        )


@pytest.mark.db
async def test_guard_rejects_frozen_at_on_insert(rc_ctx, rls_engine):
    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "INSERT INTO release_candidates (tenant_id, project_id, release_ref, status, frozen_at) "
            "VALUES (:t,:p,'X','draft',clock_timestamp())",
            t=str(t1),
            p=str(p1),
        )


@pytest.mark.db
async def test_guard_rejects_updated_at_only_update(rc_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        rc = await _repo(session, ctx).create(
            project_id=p1, payload={"release_ref": "U"}, actor="a"
        )
        rcid = rc.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "UPDATE release_candidates SET updated_at=clock_timestamp() WHERE id=:i",
            i=str(rcid),
        )


@pytest.mark.db
async def test_guard_rejects_freeze_without_frozen_at(rc_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        rc = await _repo(session, ctx).create(
            project_id=p1, payload={"release_ref": "F0"}, actor="a"
        )
        rcid = rc.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine, t1, "UPDATE release_candidates SET status='frozen' WHERE id=:i", i=str(rcid)
        )


@pytest.mark.db
async def test_guard_rejects_terminal_retransition(rc_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        rc = await repo.create(project_id=p1, payload={"release_ref": "T"}, actor="a")
        await repo.cancel(candidate_id=rc.id, actor="a")
        rcid = rc.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "UPDATE release_candidates SET status='frozen', "
            "frozen_at=clock_timestamp() WHERE id=:i",
            i=str(rcid),
        )


@pytest.mark.db
async def test_guard_rejects_bind_when_not_draft(rc_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        rc = await repo.create(project_id=p1, payload={"release_ref": "FZ"}, actor="a")
        i = await _make_issue(session, ctx, p1)
        await repo.freeze(candidate_id=rc.id, actor="a")
        rcid, iid = rc.id, i.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "INSERT INTO release_candidate_issue_bindings "
            "(tenant_id, project_id, release_candidate_id, release_issue_id) "
            "VALUES (:t,:p,:rc,:iss)",
            t=str(t1),
            p=str(p1),
            rc=str(rcid),
            iss=str(iid),
        )


@pytest.mark.db
async def test_guard_rejects_bind_cross_project(rc_ctx, rls_engine):
    # binding an issue from a different (same-tenant) project is refused by the project-match trigger
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p1b = rc_ctx["t1"], rc_ctx["p1"], rc_ctx["p1b"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        rc = await repo.create(project_id=p1, payload={"release_ref": "XP"}, actor="a")
        i_other = await _make_issue(session, ctx, p1b)  # issue under p1b
        rcid, iid = rc.id, i_other.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "INSERT INTO release_candidate_issue_bindings "
            "(tenant_id, project_id, release_candidate_id, release_issue_id) "
            "VALUES (:t,:p,:rc,:iss)",
            t=str(t1),
            p=str(p1),
            rc=str(rcid),
            iss=str(iid),
        )


@pytest.mark.db
async def test_guard_rejects_duplicate_binding(rc_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        rc = await repo.create(project_id=p1, payload={"release_ref": "DUP"}, actor="a")
        i = await _make_issue(session, ctx, p1)
        await repo.bind_issue(candidate_id=rc.id, release_issue_id=i.id, actor="a")
        rcid, iid = rc.id, i.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "INSERT INTO release_candidate_issue_bindings "
            "(tenant_id, project_id, release_candidate_id, release_issue_id) "
            "VALUES (:t,:p,:rc,:iss)",
            t=str(t1),
            p=str(p1),
            rc=str(rcid),
            iss=str(iid),
        )


@pytest.mark.db
async def test_guard_rejects_cross_tenant_binding(rc_ctx, rls_engine):
    # An issue created under tenant B cannot be bound from tenant A: the composite FK
    # (release_issue_id, tenant_id) → release_issues(id, tenant_id) has no matching row for (B-issue, A).
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1, px = rc_ctx["t1"], rc_ctx["t2"], rc_ctx["p1"], rc_ctx["px"]
    async with tenant_scope(TenantContext(t1)) as session:
        rc = await _repo(session, TenantContext(t1)).create(
            project_id=p1, payload={"release_ref": "XT"}, actor="a"
        )
        rcid = rc.id
    async with tenant_scope(TenantContext(t2)) as session:
        issue_b = await _make_issue(session, TenantContext(t2), px)
        iss_b = issue_b.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine,
            t1,
            "INSERT INTO release_candidate_issue_bindings "
            "(tenant_id, project_id, release_candidate_id, release_issue_id) "
            "VALUES (:t,:p,:rc,:iss)",
            t=str(t1),
            p=str(p1),
            rc=str(rcid),
            iss=str(iss_b),
        )


@pytest.mark.db
async def test_lifecycle_events_recorded(rc_ctx):
    # Repository operations record the expected event_type rows (created/issue_bound/frozen, and the
    # terminal transitions) in the append-only release_candidate_events trail.
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)

    async def _event_types(session, candidate_id):
        rows = (
            await session.execute(
                text(
                    "SELECT event_type FROM release_candidate_events "
                    "WHERE release_candidate_id=:c AND tenant_id=:t ORDER BY created_at, id"
                ),
                {"c": str(candidate_id), "t": str(t1)},
            )
        ).all()
        return [r[0] for r in rows]

    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        # create → bind → frozen → supersede
        rc = await repo.create(project_id=p1, payload={"release_ref": "EV-1"}, actor="a")
        i = await _make_issue(session, ctx, p1)
        await repo.bind_issue(candidate_id=rc.id, release_issue_id=i.id, actor="a")
        await repo.freeze(candidate_id=rc.id, actor="a")
        await repo.supersede(candidate_id=rc.id, actor="a")
        assert await _event_types(session, rc.id) == [
            "created",
            "issue_bound",
            "frozen",
            "superseded",
        ]
        # a separate candidate exercising the cancel terminal
        rc2 = await repo.create(project_id=p1, payload={"release_ref": "EV-2"}, actor="a")
        await repo.cancel(candidate_id=rc2.id, actor="a")
        assert await _event_types(session, rc2.id) == ["created", "canceled"]


@pytest.mark.db
async def test_append_only_no_delete_no_truncate(rc_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rc_ctx["t1"], rc_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        rc = await repo.create(project_id=p1, payload={"release_ref": "AO"}, actor="a")
        i = await _make_issue(session, ctx, p1)
        await repo.bind_issue(candidate_id=rc.id, release_issue_id=i.id, actor="a")
        rcid = rc.id
    # row-level: candidates no DELETE; bindings/events no UPDATE/DELETE
    for verb in (
        "DELETE FROM release_candidates WHERE id=:i",
        "UPDATE release_candidate_issue_bindings SET release_issue_id=gen_random_uuid() "
        "WHERE release_candidate_id=:i",
        "DELETE FROM release_candidate_issue_bindings WHERE release_candidate_id=:i",
        "UPDATE release_candidate_events SET actor='x' WHERE release_candidate_id=:i",
        "DELETE FROM release_candidate_events WHERE release_candidate_id=:i",
    ):
        with pytest.raises(Exception):
            await _direct_sql(rls_engine, t1, verb, i=str(rcid))
    # statement-level TRUNCATE on all three
    for table in (
        "release_candidates",
        "release_candidate_issue_bindings",
        "release_candidate_events",
    ):
        with pytest.raises(Exception):
            await _direct_sql(rls_engine, t1, f"TRUNCATE {table}")


@pytest.mark.db
async def test_catalog_grants_rls_and_constraints(admin_engine):
    async with admin_engine.connect() as c:
        for table, expected in (
            ("release_candidates", {"SELECT", "INSERT", "UPDATE"}),
            ("release_candidate_issue_bindings", {"SELECT", "INSERT"}),
            ("release_candidate_events", {"SELECT", "INSERT"}),
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
        # the three unique constraints on release_candidates exist
        cons = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid='release_candidates'::regclass AND contype='u'"
                    )
                )
            ).all()
        }
        assert {
            "uq_release_candidates_ref",
            "uq_release_candidates_id_tenant",
            "uq_release_candidates_id_proj_tenant",
        } <= cons
