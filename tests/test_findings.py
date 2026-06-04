"""Slice 13 — deterministic gap & structural contradiction detector (§4.4/§14.4/§16.5) tests.

Docker-free: each gap/contradiction kind, clean chain, deterministic ordering, refs-only
(no titles), no readiness keys. DB-backed (`db`): evaluate_and_record persistence + audit
safety (counts/metadata only), content/provenance safety, latest/history determinism,
RLS deny-by-default + cross-tenant, append-only, FK pinning, grants/catalog.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.intake.compiler import SourceInput
from app.intake.findings import (
    RULESET_VERSION,
    StructuralArtifactView,
    detect_findings,
)
from app.repositories.findings import FindingsRepository
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext, tenant_scope


def _v(kind, ref, *, parent=None, classification=None):
    return StructuralArtifactView(
        id=uuid.uuid4(),
        kind=kind,
        ref=ref,
        parent_id=parent.id if isinstance(parent, StructuralArtifactView) else parent,
        classification=classification,
    )


def _kinds(findings):
    return [f["kind"] for f in findings]


# --- Docker-free: gaps --------------------------------------------------------


def test_g_no_requirements():
    rep = detect_findings("p", [])
    assert "G_NO_REQUIREMENTS" in _kinds(rep.gaps)
    assert rep.contradictions == []


def test_g_requirement_without_acceptance():
    rep = detect_findings("p", [_v("requirement", "REQ-1")])
    gap = [g for g in rep.gaps if g["kind"] == "G_REQUIREMENT_WITHOUT_ACCEPTANCE"]
    assert gap and gap[0]["ref"] == "REQ-1"


def test_g_acceptance_without_oracle():
    req = _v("requirement", "REQ-1")
    ac = _v("acceptance_criterion", "AC-1", parent=req)
    rep = detect_findings("p", [req, ac])
    gap = [g for g in rep.gaps if g["kind"] == "G_ACCEPTANCE_WITHOUT_ORACLE"]
    assert gap and gap[0]["ref"] == "AC-1"


def test_g_unresolved_assumption_each_label_safe_excluded():
    req = _v("requirement", "REQ-1")
    ac = _v("acceptance_criterion", "AC-1", parent=req)
    oracle = _v("test_oracle", "OR-1", parent=ac)
    safe = _v("assumption", "ASM-SAFE", classification="safe_assumption")
    needs = _v("assumption", "ASM-N", classification="needs_approval")
    unsafe = _v("assumption", "ASM-U", classification="unsafe_assumption_blocked")
    unknown = _v("assumption", "ASM-K", classification="unknown_cannot_proceed")
    rep = detect_findings("p", [req, ac, oracle, safe, needs, unsafe, unknown])
    unresolved = {
        g["ref"]: g["classification"]
        for g in rep.gaps
        if g["kind"] == "G_UNRESOLVED_ASSUMPTION"
    }
    assert unresolved == {
        "ASM-N": "needs_approval",
        "ASM-U": "unsafe_assumption_blocked",
        "ASM-K": "unknown_cannot_proceed",
    }
    assert "ASM-SAFE" not in unresolved


def test_clean_full_chain_has_no_gaps_or_contradictions():
    req = _v("requirement", "REQ-1")
    ac = _v("acceptance_criterion", "AC-1", parent=req)
    oracle = _v("test_oracle", "OR-1", parent=ac)
    safe = _v("assumption", "ASM-1", classification="safe_assumption")
    rep = detect_findings("p", [req, ac, oracle, safe])
    assert rep.gaps == []
    assert rep.contradictions == []


# --- Docker-free: structural contradictions -----------------------------------


def test_c_requirement_has_parent():
    other = _v("requirement", "REQ-0")
    req = _v("requirement", "REQ-1", parent=other)
    rep = detect_findings("p", [other, req])
    c = [x for x in rep.contradictions if x["kind"] == "C_REQUIREMENT_HAS_PARENT"]
    assert c and "REQ-1" in c[0]["refs"]


def test_c_wrong_kind_parent_acceptance_and_oracle():
    req = _v("requirement", "REQ-1")
    asm = _v("assumption", "ASM-1", classification="safe_assumption")
    ac_wrong = _v("acceptance_criterion", "AC-1", parent=asm)  # parent not a requirement
    oracle_wrong = _v("test_oracle", "OR-1", parent=req)  # parent not an acceptance_criterion
    rep = detect_findings("p", [req, asm, ac_wrong, oracle_wrong])
    wrong = {tuple(x["refs"]) for x in rep.contradictions if x["kind"] == "C_WRONG_KIND_PARENT"}
    assert ("AC-1",) in wrong
    assert ("OR-1",) in wrong


def test_c_orphan_acceptance_and_oracle():
    ac = _v("acceptance_criterion", "AC-1", parent=None)
    oracle = _v("test_oracle", "OR-1", parent=None)
    rep = detect_findings("p", [ac, oracle])
    kinds = _kinds(rep.contradictions)
    assert "C_ORPHAN_ACCEPTANCE" in kinds
    assert "C_ORPHAN_ORACLE" in kinds


@pytest.mark.parametrize(
    "kind", ["requirement", "acceptance_criterion", "test_oracle", "assumption"]
)
def test_c_self_parent_is_generic_across_all_kinds(kind):
    aid = uuid.uuid4()
    selfp = StructuralArtifactView(
        id=aid,
        kind=kind,
        ref=f"{kind}-SELF",
        parent_id=aid,  # parent_id == id
        classification="safe_assumption" if kind == "assumption" else None,
    )
    rep = detect_findings("p", [selfp])
    assert "C_SELF_PARENT" in _kinds(rep.contradictions)
    # a requirement self-parent must NOT be shadowed by the less-specific finding
    if kind == "requirement":
        assert "C_REQUIREMENT_HAS_PARENT" not in _kinds(rep.contradictions)


# --- Docker-free: ordering / safety / shape -----------------------------------


def test_findings_deterministically_sorted():
    # build several requirements out of order; gaps must come back sorted by (kind, ref)
    arts = [_v("requirement", f"REQ-{n}") for n in (3, 1, 2)]
    rep = detect_findings("p", arts)
    refs = [g["ref"] for g in rep.gaps if g["kind"] == "G_REQUIREMENT_WITHOUT_ACCEPTANCE"]
    assert refs == sorted(refs)
    # re-running on the same input yields identical output (deterministic)
    assert detect_findings("p", arts).to_dict() == rep.to_dict()


def test_report_keys_and_no_readiness_keys():
    rep = detect_findings("p", [])
    d = rep.to_dict()
    for key in (
        "project_id",
        "gaps",
        "contradictions",
        "gap_count",
        "contradiction_count",
        "ruleset_version",
    ):
        assert key in d, key
    assert d["ruleset_version"] == RULESET_VERSION
    # Slice 13 makes NO readiness claims
    for forbidden in ("readiness_level", "can_build_to_staging", "can_go_live_autonomously"):
        assert forbidden not in d


def test_structural_view_has_no_content_fields():
    # The detector input type must not carry tenant content (enforced by shape).
    v = _v("requirement", "REQ-1")
    assert not hasattr(v, "title")
    assert not hasattr(v, "body")
    assert not hasattr(v, "data")


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def fd_ctx(admin_engine):
    """Two tenants; t1 has p1+p2, t2 has px; one accepted document per project."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('FdOrg',:s) RETURNING id",
            s=f"fd-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"fd-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"fd-{proj}-{sfx}",
            )
            content = f"doc-{proj}-{sfx}"
            out[f"doc_{proj}"] = await _scalar(
                c,
                "INSERT INTO documents (tenant_id, project_id, filename, content_type, source, "
                "content, content_hash, size_bytes, status) "
                "VALUES (:t,:p,'f.txt','text/plain','manual',:c,:h,:sz,'accepted') RETURNING id",
                t=out[tn],
                p=out[proj],
                c=content,
                h="sha256:" + __import__("hashlib").sha256(content.encode()).hexdigest(),
                sz=len(content),
            )
    return out


_SECRET_TITLE = "SECRET-REQUIREMENT-PROSE-should-not-leak"


async def _seed_req_without_ac(ctx, project_id, doc_id):
    """One requirement (with a sensitive title) and no acceptance criterion -> a gap."""
    async with tenant_scope(ctx) as session:
        repo = IntakeRepository(session, ctx)
        await repo.add_artifact(
            project_id=project_id,
            kind="requirement",
            ref="REQ-1",
            title=_SECRET_TITLE,
            sources=[SourceInput(origin=f"document:{doc_id}", document_id=doc_id)],
            actor="c",
        )


# --- DB-backed: persistence + safety ------------------------------------------


@pytest.mark.db
async def test_evaluate_and_record_persists_and_is_content_safe(fd_ctx, admin_engine):
    t1, p1, d1 = fd_ctx["t1"], fd_ctx["p1"], fd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_req_without_ac(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        repo = FindingsRepository(session, ctx)
        report, row = await repo.evaluate_and_record(project_id=p1, actor="auditor")
        rid = row.id
        assert row.gap_count >= 1
        assert row.contradiction_count == 0
        # the persisted report carries refs but never the requirement title
        assert _SECRET_TITLE not in str(row.report)
        assert any(g["ref"] == "REQ-1" for g in report.gaps)
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "AND action='intake.findings_evaluated' ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"intake_findings_report:{rid}", "t": t1},
            )
        ).one()
    assert actor == "auditor"
    blob = str(payload)
    # audit = counts/metadata only: no refs, no titles, no report body
    assert _SECRET_TITLE not in blob
    assert "REQ-1" not in blob
    assert "gaps" not in payload and "contradictions" not in payload and "report" not in payload
    assert payload["gap_count"] >= 1


@pytest.mark.db
async def test_latest_and_history_deterministic(fd_ctx):
    t1, p1, d1 = fd_ctx["t1"], fd_ctx["p1"], fd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_req_without_ac(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        repo = FindingsRepository(session, ctx)
        _, first = await repo.evaluate_and_record(project_id=p1, actor="a")
        _, second = await repo.evaluate_and_record(project_id=p1, actor="a")
        assert first.id != second.id
        hist = await repo.history(p1)
        assert len(hist) == 2
        assert hist[0].id == second.id and hist[1].id == first.id
        latest = await repo.latest(p1)
        assert latest.id == second.id


# --- DB-backed: RLS / cross-tenant / append-only / FK / catalog ---------------


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant(fd_ctx, rls_engine):
    t1, t2, p1, d1 = fd_ctx["t1"], fd_ctx["t2"], fd_ctx["p1"], fd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_req_without_ac(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        await FindingsRepository(session, ctx).evaluate_and_record(project_id=p1, actor="a")
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM intake_findings_reports"))
            ).scalar_one()
            assert n == 0
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(
                        "INSERT INTO intake_findings_reports "
                        "(tenant_id, project_id, gap_count, contradiction_count, report, "
                        "evaluated_by) VALUES (:t,:p,0,0,'{}'::jsonb,'x')"
                    ),
                    {"t": str(t2), "p": str(p1)},
                )
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()
    async with tenant_scope(TenantContext(t2)) as session:
        assert await FindingsRepository(session, TenantContext(t2)).history(p1) == []


@pytest.mark.db
async def test_append_only(fd_ctx, rls_engine):
    t1, p1, d1 = fd_ctx["t1"], fd_ctx["p1"], fd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_req_without_ac(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        await FindingsRepository(session, ctx).evaluate_and_record(project_id=p1, actor="a")
    for sql in (
        "UPDATE intake_findings_reports SET gap_count=99 WHERE tenant_id=:t",
        "DELETE FROM intake_findings_reports WHERE tenant_id=:t",
    ):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(sql), {"t": str(t1)})
        msg = str(ei.value).lower()
        assert "append-only" in msg or "permission denied" in msg or "denied" in msg


@pytest.mark.db
async def test_count_check_and_fk_pinning(fd_ctx, admin_engine):
    t1, t2, p1 = fd_ctx["t1"], fd_ctx["t2"], fd_ctx["p1"]
    # negative gap_count rejected by CHECK
    with pytest.raises(Exception) as ei1:
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO intake_findings_reports "
                    "(tenant_id, project_id, gap_count, contradiction_count, report, evaluated_by) "
                    "VALUES (:t,:p,-1,0,'{}'::jsonb,'x')"
                ),
                {"t": str(t1), "p": str(p1)},
            )
    assert "check" in str(ei1.value).lower() or "violates" in str(ei1.value).lower()
    # wrong tenant for project => FK violation
    with pytest.raises(Exception) as ei2:
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO intake_findings_reports "
                    "(tenant_id, project_id, gap_count, contradiction_count, report, evaluated_by) "
                    "VALUES (:t,:p,0,0,'{}'::jsonb,'x')"
                ),
                {"t": str(t2), "p": str(p1)},
            )
    assert "foreign key" in str(ei2.value).lower() or "violates" in str(ei2.value).lower()


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='intake_findings_reports' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='intake_findings_reports'"
                )
            )
        ).one()
        assert rls == (True, True)
