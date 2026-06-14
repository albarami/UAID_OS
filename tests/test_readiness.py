"""Deterministic build-readiness auditor (Slice 12 base; Slice 16 R3; Slice 18 R4; Slice 20 R5)
tests (§4.3/§4.4/§4.5).

Docker-free: the R0/R1/R2 spine ladder, the **R3 rule** (R2 base + the three declared §4.3 technical
categories), the **R4 rule** (R3 base + the two declared §4.3 "tools" categories + zero spine gaps),
the **R5 rule** (R4 base + ALL declarable categories declared + the autonomy & cost engine gates),
**capped at R5**, parent-kind validation (orphan/wrong-kind links never satisfy coverage), the
monotonic staging facet (`R3/R4/R5 AND environments_and_deployment_targets` declared) and
always-false go-live (even at R5 — A5/Appendix-B not evaluated) with recorded reasons, §4.4
assumption bucketing, and the report keys (`missing_r3_categories`, `missing_r4_categories`,
`missing_r4_test_coverage`, `missing_r5_categories`, `missing_r5_gates`, the
`r{3,4,5}_category_not_declared:<category>` / `r5_gate_incomplete:<gate>` entries).
DB-backed (`db`): evaluate_and_record persistence + audit safety, latest/history, the D-6
stale-source exclusion (quarantined source drops R3→R2 and R4→R3), the R5 engine gates read from
real `autonomy_policies` / `budgets` rows (present+valid autonomy, positive budget; invalid overrides
fail), RLS deny-by-default + cross-tenant, append-only enforcement, grants/catalog.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.intake.categories import DECLARABLE_INTAKE_CATEGORIES
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
from app.repositories.cost import BudgetRepository
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
    # Spine coverage alone (no declared categories) stays R2; the cap is now R5.
    req = _av("requirement", "REQ-1")
    ac = _av("acceptance_criterion", "AC-1", parent=req)
    oracle = _av("test_oracle", "OR-1", parent=ac)
    rep = evaluate_readiness("p", [req, ac, oracle], production_authority_decision="needs_approval")
    assert rep.readiness_level == "R2"
    assert rep.readiness_cap == "R5"
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
    # Slice 20: go-live now blocked by A5/Appendix-B not being evaluated, and production_authority
    # being presence-only — NOT by "capped below R5" (R5 is now reachable).
    joined = " ".join(reasons).lower()
    assert "a5" in joined and "appendix" in joined
    assert "authorization" in joined  # production_authority is presence-only, not authorization
    assert not any("capped_below_r5" in r.lower() for r in reasons)
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
        "missing_r4_categories",
        "missing_r4_test_coverage",
        "missing_r5_categories",
        "missing_r5_gates",
        "production_authority_decision",
        "ruleset_version",
    ):
        assert key in d, key
    assert d["ruleset_version"] == RULESET_VERSION
    assert RULESET_VERSION == "slice20.v1"


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


def test_all_declarable_categories_full_chain_but_no_engine_gates_stays_r4():
    from app.intake.categories import DECLARABLE_INTAKE_CATEGORIES

    # full spine chain + every declarable category, but the R5 engine gates default False ⇒ R4
    # (declarations alone do not reach R5 — the autonomy + cost gates are required).
    decls = tuple(_decl(c) for c in DECLARABLE_INTAKE_CATEGORIES)
    rep = evaluate_readiness(
        "p", _full_chain(), production_authority_decision="allow", declarations=decls
    )
    assert rep.readiness_level == "R4"
    assert rep.can_go_live_autonomously is False


def test_all_declarable_categories_but_spine_gap_stays_r3():
    from app.intake.categories import DECLARABLE_INTAKE_CATEGORIES

    # every category declared, but the spine has a gap (AC without oracle) ⇒ R4 blocked.
    decls = tuple(_decl(c) for c in DECLARABLE_INTAKE_CATEGORIES)
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="allow", declarations=decls
    )
    assert rep.readiness_level == "R3"
    assert rep.to_dict()["missing_r4_test_coverage"]  # the spine gap blocks R4


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
    # Slice 20: the R5 rule consumes every remaining category (declarable + the two engine gates),
    # so the not-assessed list is now empty — the whole §4.2 universe is assessed at R5.
    assert NOT_ASSESSED_CATEGORIES == ()
    # single-source-of-truth consistency with the Slice-15 universe: consumed == universe.
    from app.intake.categories import CANONICAL_READINESS_CATEGORY_UNIVERSE

    assert set(NOT_ASSESSED_CATEGORIES) == set(CANONICAL_READINESS_CATEGORY_UNIVERSE) - set(
        CANONICAL_READINESS_CATEGORY_UNIVERSE
    )
    assert NOT_ASSESSED_CATEGORIES == ()  # explicit: nothing left unassessed at R5


# --- Docker-free: Slice 18 R4 rules -------------------------------------------

# Canonical §4.2 file order (12 before 18) — string literals so a missing constant
# can't turn these into collection errors; they fail on the assertion instead.
_R4_TOOLS = ("integrations_and_external_systems", "tool_access_manifest")


def _full_chain():
    """A complete requirement -> acceptance_criterion -> test_oracle chain (no spine gaps)."""
    req = _av("requirement", "REQ-1")
    ac = _av("acceptance_criterion", "AC-1", parent=req)
    oracle = _av("test_oracle", "OR-1", parent=ac)
    return [req, ac, oracle]


def _r4_decls(*, extra=()):
    """R3 trio + the two R4 tool categories (+ any extras), all declared."""
    cats = tuple(R3_TECHNICAL_CATEGORIES) + _R4_TOOLS + tuple(extra)
    return tuple(_decl(c) for c in cats)


def test_r4_when_r3_plus_tools_and_full_coverage():
    rep = evaluate_readiness(
        "p", _full_chain(), production_authority_decision="needs_approval", declarations=_r4_decls()
    )
    assert rep.readiness_level == "R4"
    d = rep.to_dict()
    assert d["missing_r4_categories"] == []
    assert d["missing_r4_test_coverage"] == []


def test_r4_blocked_by_missing_tool_category():
    # R3 trio + only integrations declared (tool_access_manifest missing) + full coverage.
    decls = tuple(_decl(c) for c in R3_TECHNICAL_CATEGORIES) + (
        _decl("integrations_and_external_systems"),
    )
    rep = evaluate_readiness(
        "p", _full_chain(), production_authority_decision="deny", declarations=decls
    )
    assert rep.readiness_level == "R3"
    assert rep.to_dict()["missing_r4_categories"] == ["tool_access_manifest"]


def test_r4_blocked_by_spine_gap():
    # R3 trio + both tools declared, but the AC has no oracle ⇒ spine gap blocks R4.
    rep = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="deny", declarations=_r4_decls()
    )
    assert rep.readiness_level == "R3"
    assert rep.to_dict()["missing_r4_categories"] == []  # tools fine; only coverage blocks
    cov = rep.to_dict()["missing_r4_test_coverage"]
    assert cov  # non-empty
    # structured spine_gaps dicts preserving kind/ref/summary
    g = cov[0]
    assert set(g) >= {"kind", "ref", "summary"}
    assert g["kind"] == "acceptance_criterion_without_test_oracle" and g["ref"] == "AC-1"


def test_r4_staging_monotonic():
    # (a) regression: R3 + env stays staging-true.
    r3_env = tuple(_decl(c) for c in R3_TECHNICAL_CATEGORIES) + (
        _decl("environments_and_deployment_targets"),
    )
    rep_r3 = evaluate_readiness(
        "p", _r2_chain(), production_authority_decision="deny", declarations=r3_env
    )
    assert rep_r3.readiness_level == "R3" and rep_r3.can_build_to_staging is True
    # (b) R4 + env ⇒ staging-true.
    rep_r4 = evaluate_readiness(
        "p", _full_chain(), production_authority_decision="deny",
        declarations=_r4_decls(extra=("environments_and_deployment_targets",)),
    )
    assert rep_r4.readiness_level == "R4" and rep_r4.can_build_to_staging is True
    # (c) R4 without env ⇒ staging-false with the R4-specific reason.
    rep_r4_no_env = evaluate_readiness(
        "p", _full_chain(), production_authority_decision="deny", declarations=_r4_decls()
    )
    assert rep_r4_no_env.readiness_level == "R4" and rep_r4_no_env.can_build_to_staging is False
    assert (
        rep_r4_no_env.to_dict()["can_build_to_staging_reason"]
        == "r4_but_environments_and_deployment_targets_not_declared"
    )


def test_r4_go_live_always_false():
    rep = evaluate_readiness(
        "p", _full_chain(), production_authority_decision="allow", declarations=_r4_decls()
    )
    assert rep.readiness_level == "R4"
    assert rep.can_go_live_autonomously is False


def test_readiness_cap_is_r5():
    rep = evaluate_readiness(
        "p", _full_chain(), production_authority_decision="deny", declarations=_r4_decls()
    )
    assert rep.readiness_cap == "R5"
    d = rep.to_dict()
    assert d["ruleset_version"] == "slice20.v1"
    assert "R5" in d["readiness_cap_reason"]


def test_not_assessed_excludes_r4_tool_categories():
    for cat in _R4_TOOLS:
        assert cat not in NOT_ASSESSED_CATEGORIES


# --- Docker-free: Slice 20 R5 rules -------------------------------------------


def _r5_decls(*, omit=()):
    """Declare every declarable §4.2 category (R5 requires the full declarable set)."""
    return tuple(_decl(c) for c in DECLARABLE_INTAKE_CATEGORIES if c not in omit)


def _eval_r5(
    *,
    declarations=None,
    autonomy_policy_present=True,
    cost_policy_ok=True,
    production_authority_decision="needs_approval",
):
    """Evaluate with the R5-reaching defaults (full declarable set + both engine gates true)."""
    return evaluate_readiness(
        "p",
        _full_chain(),
        production_authority_decision=production_authority_decision,
        declarations=_r5_decls() if declarations is None else declarations,
        autonomy_policy_present=autonomy_policy_present,
        cost_policy_ok=cost_policy_ok,
    )


def test_r5_when_all_gates_present():
    rep = _eval_r5()
    assert rep.readiness_level == "R5"
    d = rep.to_dict()
    assert d["missing_r5_categories"] == []
    assert d["missing_r5_gates"] == []


@pytest.mark.parametrize("omit", DECLARABLE_INTAKE_CATEGORIES)
def test_r5_missing_each_declarable_category_blocks_r5(omit):
    # Omitting ANY declarable category must prevent R5 (and report it missing). The resulting
    # level varies — omitting an R3/R4 prerequisite drops below R4 — so we assert "not R5",
    # not a fixed level. This covers the full declarable set, not a sample.
    rep = _eval_r5(declarations=_r5_decls(omit=(omit,)))
    assert rep.readiness_level != "R5"
    assert omit in rep.to_dict()["missing_r5_categories"]


def test_r5_missing_human_approval_policy_declaration_no_r5():
    rep = _eval_r5(declarations=_r5_decls(omit=("human_approval_policy",)))
    assert rep.readiness_level == "R4"
    assert "human_approval_policy" in rep.to_dict()["missing_r5_categories"]


def test_r5_missing_production_authority_declaration_no_r5():
    rep = _eval_r5(declarations=_r5_decls(omit=("production_authority",)))
    assert rep.readiness_level == "R4"
    assert "production_authority" in rep.to_dict()["missing_r5_categories"]


def test_r5_autonomy_gate_absent_no_r5():
    rep = _eval_r5(autonomy_policy_present=False)
    assert rep.readiness_level == "R4"
    assert "autonomy_policy_absent_or_invalid" in rep.to_dict()["missing_r5_gates"]


def test_r5_cost_gate_absent_no_r5():
    rep = _eval_r5(cost_policy_ok=False)
    assert rep.readiness_level == "R4"
    assert "cost_budget_absent_or_zero" in rep.to_dict()["missing_r5_gates"]


def test_r5_reached_go_live_still_false():
    rep = _eval_r5(production_authority_decision="allow")
    assert rep.readiness_level == "R5"
    assert rep.can_go_live_autonomously is False
    joined = " ".join(rep.to_dict()["can_go_live_autonomously_reasons"]).lower()
    assert "a5" in joined and "appendix" in joined  # blocked by A5/Appendix-B, not "capped below R5"


def test_r5_gates_default_fail_closed():
    # The pure engine's gate inputs default to False ⇒ callers that don't pass them can't reach R5.
    rep = evaluate_readiness(
        "p",
        _full_chain(),
        production_authority_decision="needs_approval",
        declarations=_r5_decls(),
    )
    assert rep.readiness_level == "R4"
    assert set(rep.to_dict()["missing_r5_gates"]) == {
        "autonomy_policy_absent_or_invalid",
        "cost_budget_absent_or_zero",
    }


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


# --- DB-backed: Slice 18 R4 end-to-end + D-6 for R4 inputs ---------------------


@pytest.mark.db
async def test_db_r4_persists_and_d6_excludes_stale_tool_declaration(rd_ctx, admin_engine):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    # R3 trio backed by d1 (stays accepted); R4 tools backed by a second doc (doc_b)
    # so quarantining doc_b isolates the R4-tool D-6 exclusion (R3 trio is unaffected).
    async with admin_engine.begin() as c:
        content = f"docB-{rd_ctx['sfx']}"
        doc_b = await _scalar(
            c,
            "INSERT INTO documents (tenant_id, project_id, filename, content_type, source, "
            "content, content_hash, size_bytes, status) "
            "VALUES (:t,:p,'b.txt','text/plain','manual',:c,:h,:sz,'accepted') RETURNING id",
            t=t1, p=p1, c=content,
            h="sha256:" + __import__("hashlib").sha256(content.encode()).hexdigest(),
            sz=len(content),
        )
    await _declare_r3_categories(ctx, p1, d1, categories=_R3_TRIO)
    await _declare_r3_categories(ctx, p1, doc_b, categories=_R4_TOOLS)
    async with tenant_scope(ctx) as session:
        rep = await ReadinessRepository(session, ctx).evaluate(project_id=p1)
        assert rep.readiness_level == "R4"
    # quarantine doc_b ⇒ R4 tool declarations drop (D-6, generic) ⇒ back to R3
    async with admin_engine.begin() as c:
        await c.execute(
            text("UPDATE documents SET status='quarantined' WHERE id=:i"), {"i": str(doc_b)}
        )
    async with tenant_scope(ctx) as session:
        rep = await ReadinessRepository(session, ctx).evaluate(project_id=p1)
        assert rep.readiness_level == "R3"
        assert set(rep.to_dict()["missing_r4_categories"]) == set(_R4_TOOLS)


# --- DB-backed: Slice 20 R5 end-to-end (repo reads autonomy_policies + budgets) -----


async def _declare_all_r5_categories(ctx, project_id, doc_id):
    """Declare every declarable §4.2 category (doc-backed) — the full R5 category set."""
    from app.intake.categories import DECLARABLE_INTAKE_CATEGORIES

    await _declare_r3_categories(
        ctx, project_id, doc_id, categories=DECLARABLE_INTAKE_CATEGORIES
    )


async def _set_engine_gates(ctx, project_id, *, autonomy=True, budget=True):
    async with tenant_scope(ctx) as session:
        if autonomy:
            await AutonomyPolicyRepository(session, ctx).upsert(
                project_id=project_id, autonomy_level=2, actor="admin"
            )
        if budget:
            await BudgetRepository(session, ctx).upsert(
                project_id=project_id, max_total_cost_usd="100", actor="admin"
            )


@pytest.mark.db
async def test_db_r5_persists_when_all_categories_and_engine_gates_present(rd_ctx):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    await _declare_all_r5_categories(ctx, p1, d1)
    await _set_engine_gates(ctx, p1, autonomy=True, budget=True)
    async with tenant_scope(ctx) as session:
        report, row = await ReadinessRepository(session, ctx).evaluate_and_record(
            project_id=p1, actor="auditor"
        )
        assert report.readiness_level == "R5"
        assert row.readiness_level == "R5"  # 0015 CHECK allows R5
        assert report.can_go_live_autonomously is False
        d = report.to_dict()
        assert d["missing_r5_categories"] == [] and d["missing_r5_gates"] == []


@pytest.mark.db
async def test_db_r5_missing_autonomy_row_no_r5(rd_ctx):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    await _declare_all_r5_categories(ctx, p1, d1)
    await _set_engine_gates(ctx, p1, autonomy=False, budget=True)  # no autonomy row
    async with tenant_scope(ctx) as session:
        report = await ReadinessRepository(session, ctx).evaluate(project_id=p1)
        assert report.readiness_level == "R4"
        assert "autonomy_policy_absent_or_invalid" in report.to_dict()["missing_r5_gates"]


@pytest.mark.db
async def test_db_r5_invalid_autonomy_overrides_no_r5(rd_ctx, admin_engine):
    # An autonomy row exists but with invalid persisted overrides (validate_overrides raises),
    # so the gate is validity — not mere row existence.
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    await _declare_all_r5_categories(ctx, p1, d1)
    await _set_engine_gates(ctx, p1, autonomy=False, budget=True)
    # inject an invalid-overrides autonomy row directly (bypasses upsert validation)
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level, overrides) "
                "VALUES (:t,:p,2,'{\"bogus_action\": \"ALLOW\"}'::jsonb)"
            ),
            {"t": str(t1), "p": str(p1)},
        )
    async with tenant_scope(ctx) as session:
        report = await ReadinessRepository(session, ctx).evaluate(project_id=p1)
        assert report.readiness_level == "R4"
        assert "autonomy_policy_absent_or_invalid" in report.to_dict()["missing_r5_gates"]


@pytest.mark.db
async def test_db_r5_missing_or_zero_budget_no_r5(rd_ctx):
    t1, p1, d1 = rd_ctx["t1"], rd_ctx["p1"], rd_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_chain(ctx, p1, d1)
    await _declare_all_r5_categories(ctx, p1, d1)
    await _set_engine_gates(ctx, p1, autonomy=True, budget=False)  # no budget
    async with tenant_scope(ctx) as session:
        report = await ReadinessRepository(session, ctx).evaluate(project_id=p1)
        assert report.readiness_level == "R4"
        assert "cost_budget_absent_or_zero" in report.to_dict()["missing_r5_gates"]


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
