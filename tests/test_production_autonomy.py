"""A5 production-autonomy evaluator skeleton tests (Slice 21 + 22 + 23 + 24, Appendix B).

Fail-closed and **non-authorizing**: only gate #1 (R5 intake complete) can pass today; the **seven**
partial-context gates (#2/#5/#6/#7/#8/#9/#12) return ``insufficient_evidence`` and the **five**
sourceless gates (#3/#4/#10/#11/#13) return ``no_evidence_source:<subsystem>``. Gates #5/#6 (Slice 23)
are ``insufficient_evidence:no_finding_provenance_or_scan_source`` with open/critical finding-count
context; gate #7 (Slice 22 + 24 + 25) is ``insufficient_evidence`` — reason narrows from
``no_issue_provenance_or_release_binding`` to ``no_issue_provenance`` once a frozen release candidate
exists; ``ruleset_version`` is ``slice25.v1``.
``a5_satisfied`` and ``can_go_live_autonomously`` are always false. Docker-free for the pure engine;
``db`` for the repository (compute-on-read, no persistence; the open-issue store adds migration
``0023``).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.production_autonomy import (
    A5_RULESET_VERSION,
    evaluate_production_autonomy,
)

# Slice 22: gate #7 (risk-acceptance) moved from no_evidence_source to insufficient_evidence
# (the store now exists, but the open-issue store does not).
# Slice 23: gates #5/#6 (security/shortcut findings) moved from no_evidence_source to
# insufficient_evidence (the stores now exist, but authoritative scan coverage does not).
PARTIAL_GATES = {2, 5, 6, 7, 8, 9, 12}
SOURCELESS_GATES = {3, 4, 10, 11, 13}


def _eval(readiness_level="R5", **ctx):
    """All context primitives default True so we prove they still never pass a gate."""
    return evaluate_production_autonomy(
        "p",
        readiness_level=readiness_level,
        autonomy_policy_present=ctx.get("autonomy_policy_present", True),
        cost_policy_present=ctx.get("cost_policy_present", True),
        environments_declared=ctx.get("environments_declared", True),
        generated_ac_provenance_ok=ctx.get("generated_ac_provenance_ok", True),
    )


def _gate(rep, number):
    return next(g for g in rep.to_dict()["gates"] if g["number"] == number)


# --- Docker-free: pure engine -------------------------------------------------


def test_only_r5_gate_passes_when_readiness_r5():
    d = _eval(readiness_level="R5").to_dict()
    assert _gate_status(d, 1) == "passed"
    assert d["passed_gate_count"] == 1
    assert all(g["status"] != "passed" for g in d["gates"] if g["number"] != 1)


def test_gate1_insufficient_when_readiness_below_r5():
    rep = _eval(readiness_level="R4")
    g1 = _gate(rep, 1)
    assert g1["status"] == "insufficient_evidence"
    assert "R4" in g1["reason"]
    assert rep.to_dict()["passed_gate_count"] == 0


def test_partial_context_gates_are_insufficient_evidence():
    # context booleans all True, yet the partial gates never pass — they are context only.
    rep = _eval(readiness_level="R5")
    for n in PARTIAL_GATES:
        assert _gate(rep, n)["status"] == "insufficient_evidence", n


def test_sourceless_gates_are_no_evidence_source():
    rep = _eval(readiness_level="R5")
    for n in SOURCELESS_GATES:
        g = _gate(rep, n)
        assert g["status"] == "no_evidence_source", n
        assert g["reason"].startswith("no_evidence_source:"), n


def test_a5_never_satisfied_and_go_live_always_false():
    # even with R5 + every context primitive True, A5 is not satisfied and go-live stays false.
    d = _eval(readiness_level="R5").to_dict()
    assert d["a5_satisfied"] is False
    assert d["can_go_live_autonomously"] is False
    reasons = " ".join(d["can_go_live_reasons"]).lower()
    assert "preapproval" in reasons or "pre-approval" in reasons or "preapproved" in reasons


def test_report_keys_and_ruleset():
    d = _eval(readiness_level="R5").to_dict()
    for key in (
        "project_id",
        "a5_satisfied",
        "can_go_live_autonomously",
        "can_go_live_reasons",
        "gates",
        "passed_gate_count",
        "unmet_gates",
        "ruleset_version",
    ):
        assert key in d, key
    assert len(d["gates"]) == 13
    assert len(d["unmet_gates"]) == 12  # all but gate #1 at R5
    assert d["ruleset_version"] == A5_RULESET_VERSION == "slice25.v1"
    # status vocabulary is exactly the three allowed values
    assert {g["status"] for g in d["gates"]} <= {
        "passed",
        "insufficient_evidence",
        "no_evidence_source",
    }
    # Slice 22: every gate entry serializes a `context` dict (gates without context ⇒ {}).
    assert all("context" in g and isinstance(g["context"], dict) for g in d["gates"])


def test_gate7_reason_depends_on_frozen_release():
    # no frozen release ⇒ full reason; ≥1 frozen release ⇒ narrowed reason (still insufficient).
    g7_none = _gate(_eval(readiness_level="R5"), 7)
    assert g7_none["gate"] == "approved_risk_acceptance_records"
    assert g7_none["status"] == "insufficient_evidence"
    assert g7_none["reason"] == "no_issue_provenance_or_release_binding"
    g7_frozen = _gate(
        evaluate_production_autonomy("p", readiness_level="R5", frozen_release_candidate_count=1),
        7,
    )
    assert g7_frozen["status"] == "insufficient_evidence"  # never passes
    assert g7_frozen["reason"] == "no_issue_provenance"
    for k in (
        "active_risk_acceptance_count",
        "open_issue_count",
        "open_blocking_issue_count",
        "open_unaccepted_blocking_issue_count",
        "frozen_release_candidate_count",
        "latest_frozen_release_candidate_id",
        "latest_frozen_release_ref",
        "bound_open_issue_count",
        "bound_open_blocking_issue_count",
        "bound_open_unaccepted_blocking_issue_count",
    ):
        assert k in g7_none["context"]


def test_gate7_context_carries_issue_counts():
    rep = evaluate_production_autonomy(
        "p",
        readiness_level="R5",
        active_risk_acceptance_count=3,
        open_issue_count=4,
        open_blocking_issue_count=2,
        open_unaccepted_blocking_issue_count=2,
    )
    g7 = _gate(rep, 7)
    assert g7["context"]["active_risk_acceptance_count"] == 3
    assert g7["context"]["open_issue_count"] == 4
    assert g7["context"]["open_blocking_issue_count"] == 2
    assert g7["context"]["open_unaccepted_blocking_issue_count"] == 2


def test_gate7_context_carries_release_binding_keys():
    rep = evaluate_production_autonomy(
        "p",
        readiness_level="R5",
        frozen_release_candidate_count=2,
        latest_frozen_release_candidate_id="rc-1",
        latest_frozen_release_ref="REL-9",
        bound_open_issue_count=5,
        bound_open_blocking_issue_count=3,
        bound_open_unaccepted_blocking_issue_count=3,
    )
    g7 = _gate(rep, 7)
    assert g7["reason"] == "no_issue_provenance"  # frozen release present
    assert g7["context"]["frozen_release_candidate_count"] == 2
    assert g7["context"]["latest_frozen_release_ref"] == "REL-9"
    assert g7["context"]["bound_open_blocking_issue_count"] == 3
    assert g7["status"] == "insufficient_evidence"
    assert rep.to_dict()["a5_satisfied"] is False
    assert g7["status"] == "insufficient_evidence"  # counts are context only, never passes
    assert rep.to_dict()["a5_satisfied"] is False


def test_gates_5_6_are_insufficient_no_finding_provenance():
    rep = _eval(readiness_level="R5")
    for n, gate, count_keys in (
        (
            5,
            "no_unaccepted_critical_security_findings",
            ("open_security_finding_count", "open_unaccepted_critical_security_finding_count"),
        ),
        (
            6,
            "no_unaccepted_critical_shortcut_findings",
            ("open_shortcut_finding_count", "open_unaccepted_critical_shortcut_finding_count"),
        ),
    ):
        g = _gate(rep, n)
        assert g["gate"] == gate
        assert g["status"] == "insufficient_evidence"
        assert g["reason"] == "no_finding_provenance_or_scan_source"
        for k in count_keys:
            assert k in g["context"]


def test_gates_5_6_context_carries_counts_but_never_pass():
    rep = evaluate_production_autonomy(
        "p",
        readiness_level="R5",
        open_security_finding_count=2,
        open_unaccepted_critical_security_finding_count=1,
        open_shortcut_finding_count=3,
        open_unaccepted_critical_shortcut_finding_count=0,
    )
    g5 = _gate(rep, 5)
    g6 = _gate(rep, 6)
    assert g5["context"]["open_unaccepted_critical_security_finding_count"] == 1
    assert g6["context"]["open_shortcut_finding_count"] == 3
    assert g5["status"] == "insufficient_evidence" and g6["status"] == "insufficient_evidence"
    assert rep.to_dict()["a5_satisfied"] is False


def test_fail_closed_defaults():
    # only readiness_level supplied; all context defaults False — still well-formed, nothing extra passes.
    rep = evaluate_production_autonomy("p", readiness_level="R5")
    d = rep.to_dict()
    assert d["passed_gate_count"] == 1  # only gate #1 (R5)
    assert d["a5_satisfied"] is False and d["can_go_live_autonomously"] is False


def _gate_status(d, number):
    return next(g for g in d["gates"] if g["number"] == number)["status"]


# --- DB-backed: repository (compute-on-read, no persistence) -------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def pa_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('PaOrg',:s) RETURNING id",
            s=f"pa-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"pa-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"pa-{proj}-{sfx}",
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


async def _seed_full_r5(ctx, project_id, doc_id):
    """Reuse the Slice-20 R5 recipe: full spine + all declarable categories + autonomy row + budget."""
    from app.intake.categories import DECLARABLE_INTAKE_CATEGORIES
    from app.intake.compiler import SourceInput
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.cost import BudgetRepository
    from app.repositories.intake import IntakeRepository
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.tenancy import tenant_scope

    src = [SourceInput(origin=f"document:{doc_id}", document_id=doc_id)]
    async with tenant_scope(ctx) as session:
        repo = IntakeRepository(session, ctx)
        req = await repo.add_artifact(
            project_id=project_id,
            kind="requirement",
            ref="REQ-1",
            title="r",
            sources=src,
            actor="c",
        )
        ac = await repo.add_artifact(
            project_id=project_id,
            kind="acceptance_criterion",
            ref="AC-1",
            title="a",
            parent_id=req.id,
            sources=src,
            actor="c",
        )
        await repo.add_artifact(
            project_id=project_id,
            kind="test_oracle",
            ref="OR-1",
            title="o",
            parent_id=ac.id,
            sources=src,
            actor="c",
        )
        cats = IntakeCategoryRepository(session, ctx)
        for cat in DECLARABLE_INTAKE_CATEGORIES:
            await cats.declare(
                project_id=project_id,
                category=cat,
                source_document_id=doc_id,
                locator="§ ref",
                actor="planner",
            )
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=project_id, autonomy_level=2, actor="admin"
        )
        await BudgetRepository(session, ctx).upsert(
            project_id=project_id, max_total_cost_usd="100", actor="admin"
        )


@pytest.mark.db
async def test_db_reads_readiness_r5_passes_gate1(pa_ctx):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, d1 = pa_ctx["t1"], pa_ctx["p1"], pa_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_r5(ctx, p1, d1)
    async with tenant_scope(ctx) as session:
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    d = rep.to_dict()
    assert _gate_status(d, 1) == "passed"
    assert d["a5_satisfied"] is False
    assert d["can_go_live_autonomously"] is False


@pytest.mark.db
async def test_db_below_r5_gate1_insufficient(pa_ctx):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pa_ctx["t1"], pa_ctx["p1"]
    ctx = TenantContext(t1)  # empty spine ⇒ readiness R0
    async with tenant_scope(ctx) as session:
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    assert _gate_status(rep.to_dict(), 1) == "insufficient_evidence"


@pytest.mark.db
async def test_db_evaluate_is_read_only(pa_ctx, admin_engine):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, d1 = pa_ctx["t1"], pa_ctx["p1"], pa_ctx["doc_p1"]
    ctx = TenantContext(t1)
    await _seed_full_r5(ctx, p1, d1)

    async def _readiness_count():
        async with admin_engine.connect() as c:
            return (
                await c.execute(
                    text("SELECT count(*) FROM readiness_reports WHERE tenant_id=:t"), {"t": t1}
                )
            ).scalar_one()

    before = await _readiness_count()
    async with tenant_scope(ctx) as session:
        await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    # compute-on-read: no persisted snapshot written anywhere
    assert await _readiness_count() == before


@pytest.mark.db
async def test_db_gate7_reads_active_risk_acceptance_count(pa_ctx):
    # The A5 repo wires RiskAcceptanceRepository.count_active_nonblocking into gate #7 context;
    # gate #7 stays insufficient_evidence (never passes) regardless of the count.
    from datetime import date

    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pa_ctx["t1"], pa_ctx["p1"]
    ctx = TenantContext(t1)
    payload = {
        "release_id": "REL-1",
        "issue_id": "I1",
        "severity": "low",
        "reason_for_acceptance": "r",
        "business_impact": "b",
        "rollback_or_mitigation_plan": "rb",
        "required_follow_up_ticket": "T-1",
        "expiry_date": date(2099, 1, 1),
        "owner": "o",
        "approver": "a",
        "accepted_by": ["o", "a"],
        "approval_authority_source": "approval_matrix",
    }
    async with tenant_scope(ctx) as session:
        await RiskAcceptanceRepository(session, ctx).create(
            project_id=p1, payload=payload, actor="planner"
        )
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    g7 = _gate(rep, 7)
    assert g7["status"] == "insufficient_evidence"
    assert g7["reason"] == "no_issue_provenance_or_release_binding"
    assert g7["context"]["active_risk_acceptance_count"] == 1
    assert rep.to_dict()["a5_satisfied"] is False


@pytest.mark.db
async def test_db_gates_5_6_read_finding_counts(pa_ctx):
    # The A5 repo wires ReleaseFindingRepository counts into gates #5/#6 context; both stay
    # insufficient_evidence (never pass) regardless of the counts.
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.release_findings import ReleaseFindingRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pa_ctx["t1"], pa_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = ReleaseFindingRepository(session, ctx)
        await repo.create(
            project_id=p1,
            payload={
                "finding_type": "security",
                "category": "authz",
                "severity": "critical",
                "summary": "s",
                "detail": "d",
                "source": "manual",
            },
            actor="a",
        )
        await repo.create(
            project_id=p1,
            payload={
                "finding_type": "shortcut",
                "category": "fake_integration",
                "severity": "high",
                "summary": "s",
                "detail": "d",
                "source": "manual",
            },
            actor="a",
        )
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    g5, g6 = _gate(rep, 5), _gate(rep, 6)
    assert g5["context"]["open_security_finding_count"] == 1
    assert g5["context"]["open_unaccepted_critical_security_finding_count"] == 1
    assert g6["context"]["open_shortcut_finding_count"] == 1
    assert g6["context"]["open_unaccepted_critical_shortcut_finding_count"] == 0
    assert g5["status"] == "insufficient_evidence" and g6["status"] == "insufficient_evidence"
    assert rep.to_dict()["a5_satisfied"] is False


@pytest.mark.db
async def test_db_gate7_reads_issue_counts(pa_ctx):
    # The A5 repo wires ReleaseIssueRepository counts into gate #7 context; it stays
    # insufficient_evidence (never passes) regardless of the counts.
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pa_ctx["t1"], pa_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = ReleaseIssueRepository(session, ctx)
        await repo.create(
            project_id=p1,
            payload={
                "issue_category": "deployment",
                "severity": "high",
                "blocking": True,
                "summary": "s",
                "detail": "d",
                "source": "manual",
            },
            actor="a",
        )
        await repo.create(
            project_id=p1,
            payload={
                "issue_category": "evidence",
                "severity": "low",
                "blocking": False,
                "summary": "s",
                "detail": "d",
                "source": "manual",
            },
            actor="a",
        )
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    g7 = _gate(rep, 7)
    assert g7["context"]["open_issue_count"] == 2
    assert g7["context"]["open_blocking_issue_count"] == 1
    assert g7["context"]["open_unaccepted_blocking_issue_count"] == 1
    assert g7["status"] == "insufficient_evidence"
    assert g7["reason"] == "no_issue_provenance_or_release_binding"
    assert rep.to_dict()["a5_satisfied"] is False


@pytest.mark.db
async def test_db_gate7_narrows_with_frozen_release_candidate(pa_ctx):
    # A frozen release candidate (with a bound issue) supplies the release-binding half: gate #7
    # reason narrows to no_issue_provenance and surfaces bound-issue context, but never passes.
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pa_ctx["t1"], pa_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        issue = await ReleaseIssueRepository(session, ctx).create(
            project_id=p1,
            payload={
                "issue_category": "deployment",
                "severity": "high",
                "blocking": True,
                "summary": "s",
                "detail": "d",
                "source": "manual",
            },
            actor="a",
        )
        rc_repo = ReleaseCandidateRepository(session, ctx)
        rc = await rc_repo.create(project_id=p1, payload={"release_ref": "REL-A"}, actor="rm")
        await rc_repo.bind_issue(candidate_id=rc.id, release_issue_id=issue.id, actor="rm")
        await rc_repo.freeze(candidate_id=rc.id, actor="rm")
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    g7 = _gate(rep, 7)
    assert g7["status"] == "insufficient_evidence"
    assert g7["reason"] == "no_issue_provenance"
    assert g7["context"]["frozen_release_candidate_count"] == 1
    assert g7["context"]["latest_frozen_release_candidate_id"] == str(rc.id)
    assert g7["context"]["latest_frozen_release_ref"] == "REL-A"
    assert g7["context"]["bound_open_issue_count"] == 1
    assert g7["context"]["bound_open_blocking_issue_count"] == 1
    assert rep.to_dict()["a5_satisfied"] is False
