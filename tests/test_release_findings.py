"""Release findings store tests (Slice 23, spec §13.4 / §916-920 / §24.1 / Appendix B #5/#6).

Security + shortcut/fake-done findings. Fail-closed and non-authorizing: critical findings are hard
blockers (never accepted), non-critical findings may be accepted only via a usable
risk_acceptance_record (active + non-expired + non-blocking + same tenant/project + issue_id ==
finding.id). Docker-free for the pure validators; ``db`` for the store (RLS, append-only events,
per-transition DB guard, audit safe-metadata).
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.release.findings import (
    SECURITY_CATEGORIES,
    SEVERITIES,
    SHORTCUT_CATEGORIES,
    InvalidFinding,
    is_critical,
    validate_new_finding,
    validate_transition,
)

_REQUIRED = ("finding_type", "category", "severity", "summary", "source")


def _valid(**over) -> dict:
    rec = {
        "finding_type": "security",
        "category": "authz",
        "severity": "high",
        "summary": "missing authorization check on export endpoint",
        "detail": "GET /export returns all tenants' rows without an authz check",
        "source": "security_reviewer",
    }
    rec.update(over)
    return rec


# --- Docker-free: pure validators ---------------------------------------------


def test_valid_security_and_shortcut_findings():
    validate_new_finding(_valid())  # security/authz
    validate_new_finding(_valid(finding_type="shortcut", category="fake_integration"))


@pytest.mark.parametrize("field", _REQUIRED)
def test_required_fields_enforced(field):
    rec = _valid()
    del rec[field]
    with pytest.raises(InvalidFinding):
        validate_new_finding(rec)
    with pytest.raises(InvalidFinding):
        validate_new_finding(_valid(**{field: ""}))


def test_bad_finding_type_rejected():
    with pytest.raises(InvalidFinding):
        validate_new_finding(_valid(finding_type="perf"))


def test_category_must_match_type():
    # a shortcut category under finding_type=security is rejected (and vice versa)
    with pytest.raises(InvalidFinding):
        validate_new_finding(_valid(finding_type="security", category="fake_integration"))
    with pytest.raises(InvalidFinding):
        validate_new_finding(_valid(finding_type="shortcut", category="authz"))


def test_other_requires_summary_and_detail():
    # category='other' is not a silent escape hatch
    validate_new_finding(_valid(category="other"))  # has summary + detail ⇒ ok
    with pytest.raises(InvalidFinding):
        validate_new_finding(_valid(category="other", detail=""))
    with pytest.raises(InvalidFinding):
        validate_new_finding(_valid(category="other", summary=""))


def test_bad_severity_rejected():
    assert "blocker" not in SEVERITIES
    with pytest.raises(InvalidFinding):
        validate_new_finding(_valid(severity="blocker"))


def test_lifecycle_transitions():
    for term in ("resolved", "false_positive", "accepted", "superseded"):
        validate_transition("open", term)
    for bad in (
        ("open", "open"),
        ("resolved", "accepted"),
        ("accepted", "resolved"),
        ("superseded", "open"),
        ("false_positive", "resolved"),
    ):
        with pytest.raises(InvalidFinding):
            validate_transition(*bad)


def test_is_critical():
    assert is_critical("critical") and not is_critical("high")


def test_category_constants_disjoint_basis():
    # sanity: the two category sets share only 'other'
    assert set(SECURITY_CATEGORIES) & set(SHORTCUT_CATEGORIES) == {"other"}


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def rf_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c, "INSERT INTO organizations (name, slug) VALUES ('RfOrg',:s) RETURNING id",
            s=f"rf-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c, "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org, n=label, s=f"rf-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p1b", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c, "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn], s=f"rf-{proj}-{sfx}",
            )
    return out


def _repo(session, ctx):
    from app.repositories.release_findings import ReleaseFindingRepository

    return ReleaseFindingRepository(session, ctx)


async def _make_ra_record(session, ctx, project_id, finding_id, **over):
    """Create a risk-acceptance record whose issue_id references the finding."""
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.repositories.risk_acceptance import RiskAcceptanceRepository

    issue = await ReleaseIssueRepository(session, ctx).get_by_source_finding(finding_id)
    if issue is None:
        raise AssertionError("Slice-47 finding acceptance fixture requires a trusted bridge")
    candidates = ReleaseCandidateRepository(session, ctx)
    release_ref = f"REL-{uuid.uuid4().hex[:12]}"
    candidate = await candidates.create(
        project_id=project_id, payload={"release_ref": release_ref}, actor="planner"
    )
    await candidates.bind_issue(
        candidate_id=candidate.id, release_issue_id=issue.id, actor="planner"
    )
    await candidates.freeze(candidate_id=candidate.id, actor="planner")
    payload = {
        "release_id": release_ref,
        "issue_id": str(finding_id),
        "subject_type": "release_finding",
        "severity": "high",
        "reason_for_acceptance": "accepted risk", "business_impact": "minor",
        "rollback_or_mitigation_plan": "documented", "required_follow_up_ticket": "T-1",
        "expiry_date": date(2099, 1, 1), "owner": "po", "approver": "rm",
        "accepted_by": ["po", "rm"], "approval_authority_source": "approval_matrix",
    }
    payload.update(over)
    return await RiskAcceptanceRepository(session, ctx).create(
        project_id=project_id, payload=payload, actor="planner"
    )


async def _trusted_security_finding(session, ctx, project_id, *, severity="high"):
    from app.models.release_finding import ReleaseFinding
    from app.release.project_repo import resolve_declared_repo
    from app.release.scm_connector import FakeSCMConnector
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.repositories.security_scans import SecurityScanRepository
    from app.verify.security_scan import SCANNER_ALLOWLIST, SCHEMA_VERSION

    if await resolve_declared_repo(session, ctx, project_id) is None:
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=project_id,
            category="existing_assets_and_repositories",
            actor="fixture",
            data={"primary_repository": f"owner/repo-{project_id}", "protected_branch": "main"},
            origin="db-test",
        )
    manifest = []
    categories = []
    fingerprint = "sha256:" + uuid.uuid4().hex * 2
    for scanner_key, contract in SCANNER_ALLOWLIST.items():
        supported = sorted(contract["supported_categories"])
        manifest.append(
            {
                "scanner_key": scanner_key,
                "scanner_version": contract["scanner_version"],
                "rule_pack_hash": contract["rule_pack_hash"],
                "supported_categories": supported,
            }
        )
        for category in supported:
            findings = []
            coverage_status = "completed_clean"
            if category == "authz":
                coverage_status = "completed_with_findings"
                findings = [
                    {
                        "fingerprint": fingerprint,
                        "severity": severity,
                        "summary": "trusted fixture finding",
                        "detail": "fixture detail",
                        "evidence_ref": "scan://fixture/authz",
                    }
                ]
            categories.append(
                {
                    "category": category,
                    "scanner_key": scanner_key,
                    "scanner_version": contract["scanner_version"],
                    "rule_pack_hash": contract["rule_pack_hash"],
                    "coverage_status": coverage_status,
                    "findings": findings,
                }
            )
    commit_sha = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    await SecurityScanRepository(session, ctx).execute_ci(
        project_id=project_id,
        commit_sha=commit_sha,
        connector=FakeSCMConnector(
            security_scan_artifact={
                "schema_version": SCHEMA_VERSION,
                "commit_sha": commit_sha,
                "scanner_manifest": manifest,
                "categories": categories,
            }
        ),
        actor="fixture",
    )
    return (
        await session.execute(
            select(ReleaseFinding)
            .where(
                ReleaseFinding.tenant_id == ctx.tenant_id,
                ReleaseFinding.project_id == project_id,
                ReleaseFinding.scan_finding_fingerprint == fingerprint,
            )
            .limit(1)
        )
    ).scalar_one()


# --- DB-backed: repository ----------------------------------------------------


@pytest.mark.db
async def test_create_open_and_audit_safe(rf_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    secret = "SENSITIVE-detail-should-not-leak"
    async with tenant_scope(ctx) as session:
        f = await _repo(session, ctx).create(
            project_id=p1, payload=_valid(detail=secret), actor="rev"
        )
        fid = f.id
        assert f.status == "open" and f.source_provenance == "caller_supplied_unverified"
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"release_finding:{fid}", "t": t1},
            )
        ).one()
    assert actor == "rev"
    blob = str(payload)
    assert secret not in blob
    assert "summary" not in payload and "detail" not in payload and "resolution_note" not in payload


@pytest.mark.db
async def test_resolve_false_positive_supersede(rf_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        f = await repo.create(project_id=p1, payload=_valid(), actor="a")
        out = await repo.resolve(
            finding_id=f.id, resolution_note="fixed", resolved_by="dev", actor="dev"
        )
        assert out.status == "resolved" and out.resolved_by == "dev"
        f2 = await repo.create(project_id=p1, payload=_valid(), actor="a")
        fp = await repo.mark_false_positive(
            finding_id=f2.id, resolution_note="not real", resolved_by="dev", actor="dev"
        )
        assert fp.status == "false_positive"
        f3 = await repo.create(project_id=p1, payload=_valid(), actor="a")
        sup = await repo.supersede(
            finding_id=f3.id, resolution_note="replaced", resolved_by="dev", actor="dev"
        )
        assert sup.status == "superseded"


@pytest.mark.db
async def test_accept_noncritical_with_valid_record(rf_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        f = await _trusted_security_finding(session, ctx, p1, severity="high")
        rec = await _make_ra_record(session, ctx, p1, f.id)
        accepted = await repo.accept(finding_id=f.id, risk_acceptance_record_id=rec.id, actor="rm")
        assert accepted.status == "accepted" and accepted.risk_acceptance_record_id == rec.id


@pytest.mark.db
async def test_reject_critical_accept(rf_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        f = await _trusted_security_finding(session, ctx, p1, severity="critical")
        with pytest.raises(Exception):
            await _make_ra_record(session, ctx, p1, f.id, severity="high")


@pytest.mark.db
async def test_reject_accept_with_unusable_record(rf_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        f = await _trusted_security_finding(session, ctx, p1, severity="high")
        # expired record ⇒ not usable
        rec = await _make_ra_record(session, ctx, p1, f.id, expiry_date=date(2000, 1, 1))
        with pytest.raises(Exception):
            await repo.accept(finding_id=f.id, risk_acceptance_record_id=rec.id, actor="rm")


@pytest.mark.db
async def test_count_open_and_unaccepted_critical(rf_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        await repo.create(project_id=p1, payload=_valid(severity="high"), actor="a")  # open security
        await repo.create(project_id=p1, payload=_valid(severity="critical"), actor="a")  # open crit security
        await repo.create(
            project_id=p1, payload=_valid(finding_type="shortcut", category="fake_integration"), actor="a"
        )
        assert await repo.count_open(p1, "security") == 2
        assert await repo.count_open_unaccepted_critical(p1, "security") == 1
        assert await repo.count_open(p1, "shortcut") == 1
        assert await repo.count_open_unaccepted_critical(p1, "shortcut") == 0


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant(rf_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = rf_ctx["t1"], rf_ctx["t2"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (await conn.execute(text("SELECT count(*) FROM release_findings"))).scalar_one()
            assert n == 0
    async with tenant_scope(TenantContext(t2)) as session:
        assert await _repo(session, TenantContext(t2)).count_open(p1, "security") == 0


# --- DB-backed: guard (direct SQL refusals) -----------------------------------

_RAW_INSERT = (
    "INSERT INTO release_findings "
    "(tenant_id, project_id, finding_type, category, severity, summary, detail, source, status, "
    " resolution_note, risk_acceptance_record_id) "
    "VALUES (:t,:p,:ftype,:category,'high',:summary,:detail,'manual',:status,:rnote,:raid)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    from sqlalchemy import text as _t

    params = {
        "t": str(t1), "p": str(p1), "ftype": "security", "category": "authz",
        "summary": "s", "detail": "d", "status": "open", "rnote": None, "raid": None,
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                _t("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(_t(_RAW_INSERT), params)


@pytest.mark.db
async def test_guard_rejects_bad_status_insert(rf_ctx, rls_engine):
    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, status="resolved")


@pytest.mark.db
async def test_guard_rejects_other_without_detail(rf_ctx, rls_engine):
    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, category="other", detail="")


@pytest.mark.db
async def test_guard_rejects_resolution_metadata_on_insert(rf_ctx, rls_engine):
    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, rnote="prefilled")


@pytest.mark.db
async def test_guard_rejects_critical_accept_and_terminal_retransition(rf_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        crit = await repo.create(project_id=p1, payload=_valid(severity="critical"), actor="a")
        resolved = await repo.create(project_id=p1, payload=_valid(), actor="a")
        await repo.resolve(finding_id=resolved.id, resolution_note="x", resolved_by="d", actor="d")
        crit_id, res_id = crit.id, resolved.id
    # critical → accepted via direct SQL refused
    with pytest.raises(Exception):
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text("UPDATE release_findings SET status='accepted' WHERE id=:i"),
                    {"i": str(crit_id)},
                )
    # terminal (resolved) → accepted via direct SQL refused
    with pytest.raises(Exception):
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text("UPDATE release_findings SET status='accepted' WHERE id=:i"),
                    {"i": str(res_id)},
                )


@pytest.mark.db
async def test_guard_rejects_accept_without_valid_record(rf_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        f = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        fid = f.id
    # direct SQL accept with a NULL record id is refused by the guard
    with pytest.raises(Exception):
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text("UPDATE release_findings SET status='accepted' WHERE id=:i"),
                    {"i": str(fid)},
                )


async def _direct_sql(rls_engine, t1, sql, **params):
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(sql), params)


_ACCEPT_SQL = (
    "UPDATE release_findings SET status='accepted', risk_acceptance_record_id=:rid WHERE id=:fid"
)


@pytest.mark.db
async def test_guard_rejects_updated_at_only_update(rf_ctx, rls_engine):
    # status unchanged ⇒ no field may change, incl. updated_at (no out-of-band edits).
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        f = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        fid = f.id
    with pytest.raises(Exception):
        await _direct_sql(
            rls_engine, t1,
            "UPDATE release_findings SET updated_at=clock_timestamp() WHERE id=:i", i=str(fid),
        )


@pytest.mark.db
async def test_guard_rejects_accept_with_invalid_records(rf_ctx, rls_engine):
    # The DB guard itself (not just the repo) enforces the usable-record predicate. Each case below
    # creates a finding + a defective risk-acceptance record, then attempts a direct-SQL accept.
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p1b = rf_ctx["t1"], rf_ctx["p1"], rf_ctx["p1b"]
    ctx = TenantContext(t1)

    async def _finding_and_record(*, rec_project, rec_over):
        async with tenant_scope(ctx) as session:
            f = await _trusted_security_finding(session, ctx, p1)
            rec = await _make_ra_record(session, ctx, rec_project, f.id, **rec_over)
            return f.id, rec

    # expired record
    fid, rec = await _finding_and_record(rec_project=p1, rec_over={"expiry_date": date(2000, 1, 1)})
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rec.id), fid=str(fid))

    # non-active (revoked) record
    async with tenant_scope(ctx) as session:
        f = await _trusted_security_finding(session, ctx, p1)
        rec = await _make_ra_record(session, ctx, p1, f.id)
        await RiskAcceptanceRepository(session, ctx).revoke(record_id=rec.id, actor="a")
        fid, rid = f.id, rec.id
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rid), fid=str(fid))

    # blocking_category set (non-hard-refusal, allowed on the record but blocks acceptance)
    fid, rec = await _finding_and_record(rec_project=p1, rec_over={"blocking_category": "advisory"})
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rec.id), fid=str(fid))

    # same-tenant wrong project (record under p1b, finding under p1)
    with pytest.raises(Exception):
        await _finding_and_record(rec_project=p1b, rec_over={})

    # issue_id != finding.id
    with pytest.raises(Exception):
        await _finding_and_record(
            rec_project=p1, rec_over={"issue_id": str(uuid.uuid4())}
        )


@pytest.mark.db
async def test_guard_rejects_cross_tenant_record_via_direct_sql(rf_ctx, rls_engine):
    # A t1 finding cannot reference a t2 record by id (composite FK (rec_id, tenant_id) has no row).
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1, px = rf_ctx["t1"], rf_ctx["t2"], rf_ctx["p1"], rf_ctx["px"]
    async with tenant_scope(TenantContext(t1)) as session:
        f = await _trusted_security_finding(session, TenantContext(t1), p1)
        fid = f.id
    async with tenant_scope(TenantContext(t2)) as session:
        other = await _trusted_security_finding(session, TenantContext(t2), px)
        rec = await _make_ra_record(session, TenantContext(t2), px, other.id)
        rid = rec.id
    with pytest.raises(Exception):
        await _direct_sql(rls_engine, t1, _ACCEPT_SQL, rid=str(rid), fid=str(fid))


@pytest.mark.db
async def test_append_only_and_no_delete(rf_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = rf_ctx["t1"], rf_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        f = await _repo(session, ctx).create(project_id=p1, payload=_valid(), actor="a")
        fid = f.id
    for verb in (
        "UPDATE release_findings SET severity='low' WHERE id=:i",
        "DELETE FROM release_findings WHERE id=:i",
        "DELETE FROM release_finding_events WHERE finding_id=:i",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb), {"i": str(fid)})


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        for table, expected in (
            ("release_findings", {"SELECT", "INSERT", "UPDATE"}),
            ("release_finding_events", {"SELECT", "INSERT"}),
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
                    text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"),
                    {"t": table},
                )
            ).one()
            assert rls == (True, True), table


@pytest.mark.db
async def test_cross_tenant_accept_refused(rf_ctx):
    # A finding in t1 cannot be accepted with a risk-acceptance record created under t2.
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1, px = rf_ctx["t1"], rf_ctx["t2"], rf_ctx["p1"], rf_ctx["px"]
    ctx1 = TenantContext(t1)
    async with tenant_scope(ctx1) as session:
        f = await _trusted_security_finding(session, ctx1, p1)
        fid = f.id
    # A valid t2 record cannot satisfy a t1 finding.
    async with tenant_scope(TenantContext(t2)) as session:
        other = await _trusted_security_finding(session, TenantContext(t2), px)
        rec = await _make_ra_record(session, TenantContext(t2), px, other.id)
        rid = rec.id
    with pytest.raises(Exception):
        async with tenant_scope(ctx1) as session:
            await _repo(session, ctx1).accept(
                finding_id=fid, risk_acceptance_record_id=rid, actor="rm"
            )
