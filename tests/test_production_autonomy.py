"""A5 production-autonomy evaluator tests (Slice 21–31, Appendix B).

Fail-closed and **non-authorizing**: **gate #1 (R5 intake)** passes at R5; **gates #2 (deployment
target, Slice 30), #3 (branch protection, Slice 28), and #11 (monitoring/alerts, Slice 31)** are
PASS-capable (each a binding-bound latest-wins ladder; passes on connector_verified + fresh +
sufficient evidence). Gates #4/#5/#6/#7/#8 are fail-closed and PASS-capable from their respective
verified-evidence paths; the baseline has no such evidence, so they return ``insufficient_evidence``.
Gates #9/#12 remain partial-context only;
the remaining sourceless gates (#10/#13) return ``no_evidence_source:<subsystem>``.
Gate #7 uses the Slice-50 generated-verdict ladder over exact Slice-47/49 evidence;
``ruleset_version`` is ``slice50.v1``. ``a5_satisfied`` and
``can_go_live_autonomously`` remain false. Docker-free for the pure engine; ``db``
for the repository (compute-on-read, no persistence).
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
# Slice 26: gate #3 (branch protection) moved from no_evidence_source to insufficient_evidence
# with caller-supplied snapshots. Slice 28 adds the connector-verified write path
# (record_connector_verified_branch_protection, unlocked by migration 0027), so gate #3 is now
# PASS-capable on a repo-bound latest connector_verified + protection-enabled + fresh snapshot
# (see test_gate3_ladder_and_pass / test_gate3_pass_count_depends_on_r5). It still appears in
# PARTIAL_GATES below because this pure-engine baseline passes no branch-protection evidence, so the
# no-evidence default remains insufficient_evidence.
# Slice 30: gate #2 (deployment target) became PASS-capable; Slice 31: gate #11 (monitoring/alerts)
# became PASS-capable. Both still appear in PARTIAL_GATES because this baseline passes no
# deployment/monitoring evidence, so the no-evidence default is insufficient_evidence
# (no_environment_declaration / no_monitoring_declaration).
PARTIAL_GATES = {2, 3, 4, 5, 6, 7, 8, 9, 11, 12}
SOURCELESS_GATES = {10, 13}


def _eval(readiness_level="R5", **ctx):
    """All context primitives default True so we prove they still never pass a gate."""
    return evaluate_production_autonomy(
        "p",
        readiness_level=readiness_level,
        autonomy_policy_present=ctx.get("autonomy_policy_present", True),
        cost_policy_present=ctx.get("cost_policy_present", True),
        environments_declared=ctx.get("environments_declared", True),
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
    assert d["ruleset_version"] == A5_RULESET_VERSION == "slice50.v1"
    # status vocabulary is exactly the three allowed values
    assert {g["status"] for g in d["gates"]} <= {
        "passed",
        "insufficient_evidence",
        "no_evidence_source",
    }
    # Slice 22: every gate entry serializes a `context` dict (gates without context ⇒ {}).
    assert all("context" in g and isinstance(g["context"], dict) for g in d["gates"])


def test_gate7_reason_depends_on_frozen_release():
    # no frozen release ⇒ full reason; ≥1 frozen release without a core ⇒ the Slice-50 core rung.
    g7_none = _gate(_eval(readiness_level="R5"), 7)
    assert g7_none["gate"] == "approved_risk_acceptance_records"
    assert g7_none["status"] == "insufficient_evidence"
    assert g7_none["reason"] == ("insufficient_evidence:no_issue_provenance_or_release_binding")
    g7_frozen = _gate(
        evaluate_production_autonomy("p", readiness_level="R5", frozen_release_candidate_count=1),
        7,
    )
    assert g7_frozen["status"] == "insufficient_evidence"  # never passes
    assert g7_frozen["reason"] == "insufficient_evidence:no_audited_release_evidence_core"
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
    assert g7["reason"] == "insufficient_evidence:no_audited_release_evidence_core"
    assert g7["context"]["frozen_release_candidate_count"] == 2
    assert g7["context"]["latest_frozen_release_ref"] == "REL-9"
    assert g7["context"]["bound_open_blocking_issue_count"] == 3
    assert g7["status"] == "insufficient_evidence"
    assert rep.to_dict()["a5_satisfied"] is False
    assert g7["status"] == "insufficient_evidence"  # counts are context only, never passes
    assert rep.to_dict()["a5_satisfied"] is False


def test_gates_5_6_are_insufficient_without_their_required_evidence():
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
        assert g["reason"] == (
            "insufficient_evidence:security_scan_binding_unresolved"
            if n == 5
            else "insufficient_evidence:shortcut_review_binding_unresolved"
        )
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


def test_gate3_ladder_and_pass():
    # Slice 28: repo-bound, latest-wins ladder, keyed off the latest snapshot for the declared repo.
    name = "branch_protection_and_required_checks_active"

    def g3(**kw):
        return _gate(evaluate_production_autonomy("p", readiness_level="R5", **kw), 3)

    _verified = dict(
        branch_protection_repo_bound=True,
        latest_branch_protection_provenance="connector_verified",
        latest_branch_protection_enabled=True,
        latest_branch_protection_required_pull_request_reviews=True,
        latest_required_status_check_count=2,
        latest_branch_protection_fresh=True,
    )
    # (0) repo not bound (default) ⇒ fail-closed unbound — old snapshots cannot rescue this.
    assert g3()["reason"] == "branch_protection_repo_unbound"
    # (i) bound, no snapshot for the declared repo ⇒ no evidence.
    assert g3(branch_protection_repo_bound=True)["reason"] == "no_branch_protection_evidence"
    # (ii) bound, latest is unverified ⇒ observed_unverified (an older verified snapshot is ignored).
    assert (
        g3(
            branch_protection_repo_bound=True,
            latest_branch_protection_provenance="caller_supplied_unverified",
        )["reason"]
        == "branch_protection_observed_unverified"
    )
    # (iii) bound, verified but stale ⇒ stale.
    assert g3(**{**_verified, "latest_branch_protection_fresh": False})["reason"] == (
        "branch_protection_evidence_stale"
    )
    # (iv) bound, verified, fresh, but no required checks ⇒ insufficient.
    assert g3(**{**_verified, "latest_required_status_check_count": 0})["reason"] == (
        "branch_protection_insufficient"
    )
    # (v) bound, verified, active, fresh ⇒ PASSED.
    g3_pass = g3(**_verified)
    assert g3_pass["gate"] == name
    assert g3_pass["status"] == "passed"
    assert g3_pass["context"]["branch_protection_repo_bound"] is True
    assert "repo_ref" not in g3_pass["context"]  # never the raw repo_ref in the report


def test_gate3_pass_count_depends_on_r5():
    pass_kw = dict(
        branch_protection_repo_bound=True,
        latest_branch_protection_provenance="connector_verified",
        latest_branch_protection_enabled=True,
        latest_branch_protection_required_pull_request_reviews=True,
        latest_required_status_check_count=1,
        latest_branch_protection_fresh=True,
    )
    # gate #3 passes; with R5, gate #1 also passes ⇒ 2.
    r5 = evaluate_production_autonomy("p", readiness_level="R5", **pass_kw).to_dict()
    assert _gate_status(r5, 3) == "passed"
    assert r5["passed_gate_count"] == 2
    assert r5["a5_satisfied"] is False and r5["can_go_live_autonomously"] is False
    # without R5, only gate #3 passes ⇒ 1.
    r4 = evaluate_production_autonomy("p", readiness_level="R4", **pass_kw).to_dict()
    assert _gate_status(r4, 3) == "passed"
    assert r4["passed_gate_count"] == 1


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
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pa_ctx["t1"], pa_ctx["p1"]
    ctx = TenantContext(t1)
    payload = {
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
        issue = await ReleaseIssueRepository(session, ctx).create(
            project_id=p1,
            payload={
                "issue_category": "cost",
                "severity": "low",
                "blocking": False,
                "summary": "fixture",
                "detail": "fixture",
                "source": "test",
            },
            actor="planner",
        )
        candidates = ReleaseCandidateRepository(session, ctx)
        candidate = await candidates.create(
            project_id=p1, payload={"release_ref": "REL-1"}, actor="planner"
        )
        await candidates.bind_issue(
            candidate_id=candidate.id, release_issue_id=issue.id, actor="planner"
        )
        await candidates.freeze(candidate_id=candidate.id, actor="planner")
        payload.update(
            {
                "release_id": candidate.release_ref,
                "issue_id": str(issue.id),
                "subject_type": "release_issue",
            }
        )
        await RiskAcceptanceRepository(session, ctx).create(
            project_id=p1, payload=payload, actor="planner"
        )
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    g7 = _gate(rep, 7)
    assert g7["status"] == "insufficient_evidence"
    assert g7["reason"] == "insufficient_evidence:bound_issue_provenance_incomplete"
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
    assert g7["reason"] == ("insufficient_evidence:no_issue_provenance_or_release_binding")
    assert rep.to_dict()["a5_satisfied"] is False


@pytest.mark.db
async def test_db_gate7_narrows_with_frozen_release_candidate(pa_ctx):
    # A frozen release candidate (with a bound issue) supplies the release-binding half: gate #7
    # reason narrows to incomplete bound provenance and surfaces context, but never passes.
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
    assert g7["reason"] == "insufficient_evidence:bound_issue_provenance_incomplete"
    assert g7["context"]["frozen_release_candidate_count"] == 1
    assert g7["context"]["latest_frozen_release_candidate_id"] == str(rc.id)
    assert g7["context"]["latest_frozen_release_ref"] == "REL-A"
    assert g7["context"]["bound_open_issue_count"] == 1
    assert g7["context"]["bound_open_blocking_issue_count"] == 1
    assert rep.to_dict()["a5_satisfied"] is False


@pytest.mark.db
async def test_db_gate3_reads_branch_protection_counts(pa_ctx):
    # Slice 28: gate #3 binds to the project's DECLARED repo. An UNVERIFIED latest snapshot for that
    # repo ⇒ branch_protection_observed_unverified (verified-tier count 0). Repo-bound, never passes.
    from app.repositories.ci_evidence import CIEvidenceRepository
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pa_ctx["t1"], pa_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1,
            category="existing_assets_and_repositories",
            actor="a",
            data={"primary_repository": "owner/repo", "protected_branch": "main"},
            origin="test",
        )
        await CIEvidenceRepository(session, ctx).record_branch_protection(
            project_id=p1,
            payload={
                "provider": "github",
                "repo_ref": "owner/repo",
                "branch": "main",
                "protection_enabled": True,
                "required_pull_request_reviews": True,
                "required_status_checks": ["ci/build", "ci/test"],
                "enforce_admins": False,
            },
            actor="rev",
        )
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
    g3 = _gate(rep, 3)
    assert g3["status"] == "insufficient_evidence"
    assert g3["reason"] == "branch_protection_observed_unverified"
    assert g3["context"]["branch_protection_repo_bound"] is True
    assert g3["context"]["connector_verified_branch_protection_count"] == 0
    assert g3["context"]["latest_branch_protection_enabled"] is True
    assert g3["context"]["latest_required_status_check_count"] == 2
    assert "repo_ref" not in g3["context"]
    assert rep.to_dict()["a5_satisfied"] is False
