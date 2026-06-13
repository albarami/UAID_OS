"""Deterministic build-readiness auditor (Slice 12 base; Slice 16 R3 rules) tests
(§4.3/§4.4/§4.5).

Docker-free: the R0/R1/R2 spine ladder, the **R3 rule** (R2 base + the three declared
§4.3 technical categories, capped at R3), parent-kind validation (orphan/wrong-kind
links never satisfy coverage), the staging facet (`R3 AND environments_and_deployment_targets`
declared) and always-false go-live with recorded reasons, §4.4 assumption bucketing,
and the report keys (`missing_r3_categories`, `r3_category_not_declared:<category>`).
DB-backed (`db`): evaluate_and_record persistence + audit safety, latest/history,
the D-6 stale-source exclusion (a quarantined source document drops R3→R2; same-project
pinning is enforced upstream by the intake-category repo + composite DB FK — see
test_intake_categories.py), RLS deny-by-default + cross-tenant, append-only enforcement,
grants/catalog.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.intake.compiler import SourceInput
from app.intake.readiness import (
    NOT_ASSESSED_CATEGORIES,
    R3_TECHNICAL_CATEGORIES,
    RULESET_VERSION,
    ArtifactView,
    CategoryDeclarationView,
    evaluate_readiness,
)
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.intake import IntakeRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.readiness import ReadinessRepository
from app.tenancy import TenantContext, tenant_scope


def _av(kind, ref, *, parent=None, classification=None):
    return ArtifactView(
        id=uuid.uuid4(),
        kind=kind,
        ref=ref,
        title=f"{ref} title",
        parent_id=parent.id if isinstance(parent, ArtifactView) else parent,
        classification=classification,
    )


def _decl(category, status="declared"):
    return CategoryDeclarationView(category=category, status=status)


def _r2_chain():
    """A minimal R2 base: one valid requirement -> acceptance_criterion chain."""
    req = _av("requirement", "REQ-1")
    return [req, _av("acceptance_criterion", "AC-1", parent=req)]


# --- Docker-free: pure mapping ------------------------------------------------


def test_r0_no_requirements():
    rep = evaluate_readiness("p", [], production_authority_decision="deny")
    assert rep.readiness_level == "R0"


def test_r1_requirements_without_acceptance_chain():
    reqs = [_av("requirement", "REQ-1"), _av("requirement", "REQ-2")]
    rep = evaluate_readiness("p", reqs, production_authority_decision="deny")
    assert rep.readiness_level == "R1"
    # the requirements show up as gaps (no acceptance criterion)
    summaries = " ".join(g["summary"] for g in rep.spine_gaps)
    assert "REQ-1" in summaries and "REQ-2" in summaries


def test_r2_with_one_valid_chain():
    req = _av("requirement", "REQ-1")
    ac = _av("acceptance_criterion", "AC-1", parent=req)
    rep = evaluate_readiness("p", [req, ac], production_authority_decision="deny")
    assert rep.readiness_level == "R2"


def test_full_coverage_without_categories_returns_r2():
    # Spine coverage alone (no declared R3 categories) stays R2; the cap is now R3.
    req = _av("requirement", "REQ-1")
    ac = _av("acceptance_criterion", "AC-1", parent=req)
    oracle = _av("test_oracle", "OR-1", parent=ac)
    rep = evaluate_readiness("p", [req, ac, oracle], production_authority_decision="needs_approval")
    assert rep.readiness_level == "R2"
    assert rep.readiness_cap == "R3"
    assert rep.to_dict()["readiness_cap_reason"]


def test_can_build_to_staging_false_below_r3_with_reason():
    req = _av("requirement", "REQ-1")
    ac = _av("acceptance_criterion", "AC-1", parent=req)
    oracle = _av("test_oracle", "OR-1", parent=ac)
    rep = evaluate_readiness("p", [req, ac, oracle], production_authority_decision="needs_approval")
    assert rep.can_build_to_staging is False
    assert rep.to_dict()["can_build_to_staging_reason"] == "readiness_below_R3"


def test_can_go_live_false_with_reasons_even_if_policy_allows():
    req = _av("requirement", "REQ-1")
    ac = _av("acceptance_criterion", "AC-1", parent=req)
    oracle = _av("test_oracle", "OR-1", parent=ac)
    # even if a (hypothetical) policy decision were ALLOW, go-live stays false
    rep = evaluate_readiness("p", [req, ac, oracle], production_authority_decision="allow")
    assert rep.can_go_live_autonomously is False
    reasons = rep.to_dict()["can_go_live_autonomously_reasons"]
    assert any("R5" in r for r in reasons)
    assert any("gated" in r for r in reasons)
    assert rep.to_dict()["production_authority_decision"] == "allow"


def test_orphan_and_wrong_kind_parents_do_not_satisfy_coverage():
    # AC whose parent is an assumption (wrong kind) must NOT cover the requirement
    req = _av("requirement", "REQ-1")
    asm = _av("assumption", "ASM-1", classification="safe_assumption")
    ac_wrong = _av("acceptance_criterion", "AC-1", parent=asm)  # wrong-kind parent
    ac_orphan = _av("acceptance_criterion", "AC-2", parent=None)  # orphan
    # oracle whose parent is a requirement (wrong kind) is not valid coverage
    oracle_wrong = _av("test_oracle", "OR-1", parent=req)
    rep = evaluate_readiness(
        "p", [req, asm, ac_wrong, ac_orphan, oracle_wrong], production_authority_decision="deny"
    )
    # no VALID requirement -> acceptance chain exists, so still R1
    assert rep.readiness_level == "R1"
    summaries = " ".join(g["summary"] for g in rep.spine_gaps)
    assert "AC-1" in summaries  # wrong-kind parent flagged
    assert "AC-2" in summaries  # orphan flagged
    assert "OR-1" in summaries  # wrong-kind oracle flagged


def test_assumption_bucketing_by_label():
    req = _av("requirement", "REQ-1")
    ac = _av("acceptance_criterion", "AC-1", parent=req)
    safe = _av("assumption", "ASM-SAFE", classification="safe_assumption")
    needs = _av("assumption", "ASM-NEEDS", classification="needs_approval")
    unsafe = _av("assumption", "ASM-UNSAFE", classification="unsafe_assumption_blocked")
    unknown = _av("assumption", "ASM-UNK", classification="unknown_cannot_proceed")
    rep = evaluate_readiness(
        "p", [req, ac, safe, needs, unsafe, unknown], production_authority_decision="deny"
    )
    d = rep.to_dict()
    safe_refs = {a["ref"] for a in d["safe_assumptions"]}
    blocked = {a["ref"]: a["classification"] for a in d["blocked_assumptions"]}
    assert safe_refs == {"ASM-SAFE"}
    # everything not safe is reported as not-auto-safe (fail-closed), label preserved
    assert blocked == {
        "ASM-NEEDS": "needs_approval",
        "ASM-UNSAFE": "unsafe_assumption_blocked",
        "ASM-UNK": "unknown_cannot_proceed",
    }


def test_missing_for_go_live_includes_gaps_and_not_assessed():
    req = _av("requirement", "REQ-1")  # no AC -> a spine gap
    rep = evaluate_readiness("p", [req], production_authority_decision="deny")
    mfg = rep.to_dict()["missing_for_go_live"]
    assert any("REQ-1" in m for m in mfg)  # spine gap present
    # every not-assessed category present
    for cat in NOT_ASSESSED_CATEGORIES:
        assert cat in mfg


def test_report_has_all_required_keys():
    rep = evaluate_readiness("p", [], production_authority_decision="deny")
    d = rep.to_dict()
    for key in (
        "project_id",
        "readiness_level",
        "can_build_to_staging",
        "can_go_live_autonomously",
        "missing_for_go_live",
        "safe_assumptions",
        "blocked_assumptions",
        "readiness_cap",
        "readiness_cap_reason",
        "can_build_to_staging_reason",
        "can_go_live_autonomously_reasons",
        "not_assessed_categories",
        "spine_gaps",
        "missing_r3_categories",
        "production_authority_decision",
        "ruleset_version",
    ):
        assert key in d, key
    assert d["ruleset_version"] == RULESET_VERSION
    assert RULESET_VERSION == "slice16.v1"


# --- Docker-free: Slice 16 R3 rules -------------------------------------------


def test_r3_with_r2_base_and_three_declared_categories():
    decls = tuple(_decl(c) for c in R3_TECHNICAL_CATEGORIES)
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="needs_approval", declarations=decls
    )
    assert rep.readiness_level == "R3"
    assert rep.missing_r3_categories == []


@pytest.mark.parametrize("missing", list(R3_TECHNICAL_CATEGORIES))
def test_each_missing_r3_category_stays_r2(missing):
    decls = tuple(_decl(c) for c in R3_TECHNICAL_CATEGORIES if c != missing)
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="deny", declarations=decls
    )
    assert rep.readiness_level == "R2"
    assert missing in rep.missing_r3_categories
    assert f"r3_category_not_declared:{missing}" in rep.to_dict()["missing_for_go_live"]


def test_not_applicable_does_not_satisfy_r3():
    decls = tuple(_decl(c, "not_applicable") for c in R3_TECHNICAL_CATEGORIES)
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="deny", declarations=decls
    )
    assert rep.readiness_level == "R2"
    assert set(rep.missing_r3_categories) == set(R3_TECHNICAL_CATEGORIES)


def test_below_r2_base_never_reaches_r3_even_if_categories_declared():
    # only requirements, no acceptance chain (R1) — declaring categories cannot lift it
    reqs = [_av("requirement", "REQ-1")]
    decls = tuple(_decl(c) for c in R3_TECHNICAL_CATEGORIES)
    rep = evaluate_readiness("p", reqs, production_authority_decision="deny", declarations=decls)
    assert rep.readiness_level == "R1"


def test_all_declarable_categories_still_caps_at_r3_never_higher():
    from app.intake.categories import DECLARABLE_INTAKE_CATEGORIES

    decls = tuple(_decl(c) for c in DECLARABLE_INTAKE_CATEGORIES)
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="allow", declarations=decls
    )
    assert rep.readiness_level == "R3"  # never R4/R5
    assert rep.can_go_live_autonomously is False


def test_staging_false_at_r3_without_environments():
    decls = tuple(_decl(c) for c in R3_TECHNICAL_CATEGORIES)  # no environments
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="deny", declarations=decls
    )
    assert rep.readiness_level == "R3"
    assert rep.can_build_to_staging is False
    assert (
        rep.to_dict()["can_build_to_staging_reason"]
        == "r3_but_environments_and_deployment_targets_not_declared"
    )


def test_staging_true_at_r3_with_environments():
    decls = tuple(_decl(c) for c in R3_TECHNICAL_CATEGORIES) + (
        _decl("environments_and_deployment_targets"),
    )
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="deny", declarations=decls
    )
    assert rep.readiness_level == "R3"
    assert rep.can_build_to_staging is True
    assert (
        rep.to_dict()["can_build_to_staging_reason"]
        == "r3_with_environments_and_deployment_targets_declared"
    )


def test_r2_semantics_unchanged_without_declarations():
    rep = evaluate_readiness("p", _r2_chain(), production_authority_decision="deny")
    assert rep.readiness_level == "R2"
    assert rep.can_build_to_staging is False
    assert rep.can_go_live_autonomously is False
    assert rep.missing_r3_categories == list(R3_TECHNICAL_CATEGORIES)


def test_not_assessed_categories_golden_and_consistent():
    assert NOT_ASSESSED_CATEGORIES == (
        "project_manifest",
        "product_brief",
        "business_objectives",
        "scope_and_boundaries",
        "users_roles_permissions",
        "non_functional_requirements",
        "domain_pack",
        "integrations_and_external_systems",
        "existing_assets_and_repositories",
        "security_privacy_compliance",
        "secrets_and_credentials_manifest",
        "tool_access_manifest",
        "autonomy_policy",
        "human_approval_policy",
        "cost_and_resource_policy",
        "operations_observability_support",
        "go_live_checklist",
        "risk_register_and_assurance_requirements",
        "prior_decisions_and_architecture_log",
        "production_authority",
    )
    # single-source-of-truth consistency with the Slice-15 universe
    from app.intake.categories import CANONICAL_READINESS_CATEGORY_UNIVERSE

    consumed = {
        "functional_requirements",
        "acceptance_criteria",
        "test_oracles",
        "user_journeys_and_workflows",
        "data_model_and_contracts",
        "architecture_and_technology_constraints",
        "environments_and_deployment_targets",
    }
    assert set(NOT_ASSESSED_CATEGORIES) == set(CANONICAL_READINESS_CATEGORY_UNIVERSE) - consumed


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def rd_ctx(admin_engine):
    """Two tenants; t1 has p1+p2, t2 has px; one accepted document per project for sources."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('RdOrg',:s) RETURNING id",
            s=f"rd-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"rd-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"rd-{proj}-{sfx}",
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


async def _seed_full_chain(ctx, project_id, doc_id):
    """Seed REQ -> AC -> ORACLE + one safe assumption via the spine repository."""
    async with tenant_scope(ctx) as session:
        repo = IntakeRepository(session, ctx)
        src = [SourceInput(origin=f"document:{doc_id}", document_id=doc_id)]
        req = await repo.add_artifact(
            project_id=project_id, kind="requirement", ref="REQ-1", title="r", sources=src, actor="c"
        )
        ac = await repo.add_artifact(
            project_id=project_id, kind="acceptance_criterion", ref="AC-1", title="a",
            parent_id=req.id, sources=src, actor="c",
        )
        await repo.add_artifact(
            project_id=project_id, kind="test_oracle", ref="OR-1", title="o",
            parent_id=ac.id, sources=src, actor="c",
        )
        await repo.add_artifact(
            project_id=project_id, kind="assumption", ref="ASM-1", title="assume",
            classification="safe_assumption", sources=src, actor="c",
        )


async def _declare_r3_categories(ctx, project_id, doc_id, *, categories):
    """Declare the given intake categories (doc-backed) via the Slice-15 repository."""
    async with tenant_scope(ctx) as session:
        repo = IntakeCategoryRepository(session, ctx)
        for cat in categories:
            await repo.declare(
                project_id=project_id, category=cat, source_document_id=doc_id,
                locator="§ ref", actor="planner",
            )


_R3_TRIO = (
    "user_journeys_and_workflows",
    "data_model_and_contracts",
    "architecture_and_technology_constraints",
)


# --- DB-backed: Slice 16 R3 end-to-end ----------------------------------------


@pytest.mark.db
async def test_db_r3_persists_when_base_and_categories_present(rd_ctx):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    await _declare_r3_categories(ctx, p1, d1, categories=_R3_TRIO)
    async with tenant_scope(ctx) as session:
        report, row = await ReadinessRepository(session, ctx).evaluate_and_record(
            project_id=p1, actor="auditor"
        )
        assert report.readiness_level == "R3"
        assert row.readiness_level == "R3"  # the 0015 CHECK accepts R3
        assert row.can_build_to_staging is False  # no environments declared
        assert report.missing_r3_categories == []


@pytest.mark.db
async def test_db_missing_one_r3_category_persists_r2(rd_ctx):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    await _declare_r3_categories(
        ctx, p1, d1, categories=("user_journeys_and_workflows", "data_model_and_contracts")
    )
    async with tenant_scope(ctx) as session:
        report, row = await ReadinessRepository(session, ctx).evaluate_and_record(
            project_id=p1, actor="auditor"
        )
        assert report.readiness_level == "R2"
        assert row.readiness_level == "R2"
        assert "architecture_and_technology_constraints" in report.missing_r3_categories


@pytest.mark.db
async def test_db_not_applicable_category_does_not_satisfy_r3(rd_ctx):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    # two declared, one not_applicable
    async with tenant_scope(ctx) as session:
        repo = IntakeCategoryRepository(session, ctx)
        await repo.declare(
            project_id=p1, category="user_journeys_and_workflows",
            source_document_id=d1, locator="x", actor="a",
        )
        await repo.declare(
            project_id=p1, category="data_model_and_contracts",
            source_document_id=d1, locator="x", actor="a",
        )
        await repo.declare(
            project_id=p1, category="architecture_and_technology_constraints",
            status="not_applicable", origin="declared_n/a", actor="a",
        )
    async with tenant_scope(ctx) as session:
        report = await ReadinessRepository(session, ctx).evaluate(project_id=p1)
        assert report.readiness_level == "R2"
        assert "architecture_and_technology_constraints" in report.missing_r3_categories


@pytest.mark.db
async def test_db_stale_doc_backed_declaration_excluded_after_quarantine(rd_ctx, admin_engine):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    await _declare_r3_categories(ctx, p1, d1, categories=_R3_TRIO)
    async with tenant_scope(ctx) as session:
        assert (await ReadinessRepository(session, ctx).evaluate(project_id=p1)).readiness_level == "R3"
    # quarantine the source document (admin path)
    async with admin_engine.begin() as c:
        await c.execute(
            text("UPDATE documents SET status='quarantined' WHERE id=:i"), {"i": str(d1)}
        )
    # D-6: the doc-backed declarations no longer count ⇒ drops back to R2
    async with tenant_scope(ctx) as session:
        report = await ReadinessRepository(session, ctx).evaluate(project_id=p1)
        assert report.readiness_level == "R2"
        assert set(report.missing_r3_categories) == set(_R3_TRIO)


# --- DB-backed: persistence + audit safety ------------------------------------


@pytest.mark.db
async def test_evaluate_and_record_persists_and_audits_safely(rd_ctx, admin_engine):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        repo = ReadinessRepository(session, ctx)
        report, row = await repo.evaluate_and_record(project_id=p1, actor="auditor")
        rid = row.id
        assert report.readiness_level == "R2"
        assert row.readiness_level == "R2"
        assert row.can_build_to_staging is False
        assert row.can_go_live_autonomously is False
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "AND action='intake.readiness_evaluated' ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"readiness_report:{rid}", "t": t1},
            )
        ).one()
    assert actor == "auditor"
    assert payload["readiness_level"] == "R2"
    # no tenant content / titles / report body in the audit payload
    blob = str(payload).lower()
    assert "title" not in payload
    assert "report" not in payload
    assert "assume" not in blob  # the assumption title must not leak


@pytest.mark.db
async def test_latest_and_history(rd_ctx):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        repo = ReadinessRepository(session, ctx)
        _, first = await repo.evaluate_and_record(project_id=p1, actor="a")
        _, second = await repo.evaluate_and_record(project_id=p1, actor="a")
        assert first.id != second.id
        hist = await repo.history(p1)
        assert len(hist) == 2
        latest = await repo.latest(p1)
        assert latest is not None
        # deterministic: the most recently inserted snapshot is returned
        assert latest.id == second.id
        assert hist[0].id == second.id and hist[1].id == first.id


# --- DB-backed: autonomy-policy wiring (Slice 3) ------------------------------


@pytest.mark.db
async def test_evaluate_wires_deploy_production_policy_decision(rd_ctx):
    """A high autonomy policy yields needs_approval for deploy_production (it is
    mandatory-approval), and go-live still stays false — proving real Slice-3 wiring."""
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        # high autonomy: A5 / level 5
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=p1, autonomy_level=5, actor="admin"
        )
        repo = ReadinessRepository(session, ctx)
        report, row = await repo.evaluate_and_record(project_id=p1, actor="auditor")
        # deploy_production is mandatory-approval -> NEEDS_APPROVAL even at A5, never ALLOW
        assert report.to_dict()["production_authority_decision"] == "needs_approval"
        assert report.can_go_live_autonomously is False
        # the stored snapshot carries the same wired decision
        assert row.report["production_authority_decision"] == "needs_approval"
        assert row.can_go_live_autonomously is False


# --- DB-backed: RLS / cross-tenant / append-only / catalog --------------------


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant(rd_ctx, rls_engine):
    t1, t2, p1, d1 = rd_ctx["t1"], rd_ctx["t2"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        await ReadinessRepository(session, ctx).evaluate_and_record(project_id=p1, actor="a")
    # deny-by-default (no GUC)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (await conn.execute(text("SELECT count(*) FROM readiness_reports"))).scalar_one()
            assert n == 0
    # cross-tenant WITH CHECK insert blocked (GUC=t1, row for t2)
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(
                        "INSERT INTO readiness_reports "
                        "(tenant_id, project_id, readiness_level, can_build_to_staging, "
                        "can_go_live_autonomously, report, evaluated_by) "
                        "VALUES (:t,:p,'R0',false,false,'{}'::jsonb,'x')"
                    ),
                    {"t": str(t2), "p": str(p1)},
                )
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()
    # tenant t2 sees none of t1's reports
    async with tenant_scope(TenantContext(t2)) as session:
        assert await ReadinessRepository(session, TenantContext(t2)).history(p1) == []


@pytest.mark.db
async def test_append_only(rd_ctx, admin_engine, rls_engine):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        await ReadinessRepository(session, ctx).evaluate_and_record(project_id=p1, actor="a")
    for verb_sql in (
        "UPDATE readiness_reports SET readiness_level='R5' WHERE tenant_id=:t",
        "DELETE FROM readiness_reports WHERE tenant_id=:t",
    ):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb_sql), {"t": str(t1)})
        msg = str(ei.value).lower()
        assert "append-only" in msg or "permission denied" in msg or "denied" in msg


@pytest.mark.db
async def test_fk_pinning(rd_ctx, admin_engine):
    # project p1 (tenant1) but tenant_id=t2 => project_tenant FK violation
    t2, p1 = rd_ctx["t2"], rd_ctx["p1"]
    with pytest.raises(Exception) as ei:
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO readiness_reports "
                    "(tenant_id, project_id, readiness_level, can_build_to_staging, "
                    "can_go_live_autonomously, report, evaluated_by) "
                    "VALUES (:t,:p,'R0',false,false,'{}'::jsonb,'x')"
                ),
                {"t": str(t2), "p": str(p1)},
            )
    assert "foreign key" in str(ei.value).lower() or "violates" in str(ei.value).lower()


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='readiness_reports' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='readiness_reports'"
                )
            )
        ).one()
        assert rls == (True, True)
