"""Slice 40 — agent qualification eval (§9.4 step 6-7 / §9.5.1) tests.

Docker-free: the pure scorer (derive_counts / coverage_complete / expected_verdict mirroring the DB
GENERATED verdict). DB-backed (`db`): the migration-seeded global `archetype_evals` library (SELECT-only),
the tenant `qualification_runs` (+ FK `qualification_case_results`) whose counts/coverage are
deferred-trigger-verified from the children and whose aggregate/verdict are GENERATED (a fake `passed` is
DB-rejected — B3), the run-scoped QA+Security approvals (B7), the one-way `unqualified→qualified`
transition (migration 0039), the broker-REACH unlock, and the bit-stable no-A5/readiness guard.
Deterministic only — no LLM, no agent run, no eval harness. Eval-result provenance is unverified.
"""

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.agents.qualification import (
    CASE_CATEGORIES,
    QUALIFICATION_ARCHETYPES,
    VERDICTS,
    coverage_complete,
    derive_counts,
    expected_verdict,
    validate_case_results,
)
from app.agents.registry import ARCHETYPES


def _case(ref, category, passed, is_critical=False):
    return {
        "case_ref": ref,
        "case_category": category,
        "passed": passed,
        "is_critical": is_critical,
    }


def test_constants():
    assert QUALIFICATION_ARCHETYPES == ARCHETYPES  # runtime enum, incl. 'ai_evaluation' (B2)
    assert CASE_CATEGORIES == ("positive", "negative", "edge", "adversarial", "incomplete")
    assert VERDICTS == ("passed", "failed")


def test_derive_counts():
    cases = [
        _case("c1", "positive", True),
        _case("c2", "negative", False),
        _case("c3", "edge", False, is_critical=True),  # critical FAILURE
        _case("c4", "adversarial", True, is_critical=True),  # critical but passed ⇒ not a failure
    ]
    total, passed, critical_failures, categories = derive_counts(cases)
    assert (total, passed, critical_failures) == (4, 2, 1)
    assert categories == {"positive", "negative", "edge", "adversarial"}


def test_coverage_complete():
    present = {"positive", "negative", "edge", "adversarial", "incomplete"}
    assert (
        coverage_complete(present, ["positive", "negative", "edge", "adversarial", "incomplete"])
        is True
    )
    assert coverage_complete({"positive", "negative"}, ["positive", "negative", "edge"]) is False


def test_expected_verdict_mirrors_the_db_rule():
    base = dict(min_cases=5, min_aggregate_score=Decimal("0.850"), require_zero_critical=True)
    # passes: 5/5 = 1.0 ≥ 0.85, zero critical, covered
    assert (
        expected_verdict(
            total=5, passed=5, critical_failure_count=0, coverage_complete=True, **base
        )
        == "passed"
    )
    # below threshold: 4/5 = 0.8 < 0.85
    assert (
        expected_verdict(
            total=5, passed=4, critical_failure_count=0, coverage_complete=True, **base
        )
        == "failed"
    )
    # zero-critical violated
    assert (
        expected_verdict(
            total=5, passed=5, critical_failure_count=1, coverage_complete=True, **base
        )
        == "failed"
    )
    # coverage incomplete
    assert (
        expected_verdict(
            total=5, passed=5, critical_failure_count=0, coverage_complete=False, **base
        )
        == "failed"
    )
    # below min_cases
    assert (
        expected_verdict(
            total=3, passed=3, critical_failure_count=0, coverage_complete=True, **base
        )
        == "failed"
    )


def test_validate_case_results_rejects_bad_shapes():
    validate_case_results([_case("c1", "positive", True)])  # ok
    bad = [
        [_case("c1", "not_a_category", True)],  # bad category
        [_case("", "positive", True)],  # empty ref
        [
            {"case_ref": "c1", "case_category": "positive", "passed": "yes", "is_critical": False}
        ],  # non-bool
        [{"case_ref": "c1", "case_category": "positive", "passed": True}],  # missing is_critical
    ]
    for cases in bad:
        with pytest.raises(ValueError):
            validate_case_results(cases)


# --- DB-backed: library + runs + transition (migration 0039) --------------------

_H = "sha256:" + "a" * 64
_PASS_CASES = [(c, True, False) for c in CASE_CATEGORIES]  # 5 cases, all categories, all passed


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def qual_ctx(admin_engine):
    """org → t1/t2, p1(t1)/px(t2), a builder blueprint+version+instance + an UNQUALIFIED realization."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('QOrg',:s) RETURNING id",
            s=f"q-org-{sfx}",
        )
        t1 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t1',:s) RETURNING id",
            o=org,
            s=f"q-t1-{sfx}",
        )
        t2 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t2',:s) RETURNING id",
            o=org,
            s=f"q-t2-{sfx}",
        )
        p1 = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
            t=t1,
            s=f"q-p1-{sfx}",
        )
        px = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"q-px-{sfx}",
        )
        bp = await _scalar(
            c,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) VALUES (:k,'B','b','builder') RETURNING id",
            k=f"b-{sfx}",
        )
        ver1 = await _scalar(
            c,
            "INSERT INTO agent_versions (blueprint_id, version_label, model_route, prompt_hash, tool_policy_hash, "
            "context_policy_hash, eval_suite_hash, critical_dependencies_hash, output_schema_hash, content_hash) "
            "VALUES (:b,'v1','m',:h,:h,:h,:h,:h,:h,:ch) RETURNING id",
            b=bp,
            h=_H,
            ch="sha256:" + sfx + "0" * (64 - len(sfx)),
        )
        inst1 = await _scalar(
            c,
            "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) VALUES (:t,:p,:v,:k) RETURNING id",
            t=t1,
            p=p1,
            v=ver1,
            k=f"k{sfx}",
        )
        real1 = await _scalar(
            c,
            "INSERT INTO agent_realizations (tenant_id, project_id, instance_id, qualification_status, realized_by) VALUES (:t,:p,:i,'unqualified','planner') RETURNING id",
            t=t1,
            p=p1,
            i=inst1,
        )
        be = await _scalar(
            c, "SELECT id FROM archetype_evals WHERE archetype='builder' AND eval_version='v1'"
        )
    return {"t1": t1, "t2": t2, "p1": p1, "px": px, "real1": real1, "builder_eval": be, "sfx": sfx}


async def _insert_run(
    conn,
    ctx,
    *,
    total,
    passed,
    critical,
    coverage,
    cases,
    tenant=None,
    project=None,
    realization=None,
):
    rid = await _scalar(
        conn,
        "INSERT INTO qualification_runs (tenant_id, project_id, realization_id, archetype_eval_id, archetype, eval_version, "
        "min_aggregate_score, require_zero_critical, min_cases, required_categories, total_cases, passed_cases, "
        "critical_failure_count, coverage_complete, evaluated_by) VALUES (:t,:p,:r,:e,'builder','v1',0.850,true,5,"
        '\'["positive","negative","edge","adversarial","incomplete"]\'::jsonb,:tot,:pas,:crit,:cov,\'evaluator\') RETURNING id',
        t=str(tenant or ctx["t1"]),
        p=str(project or ctx["p1"]),
        r=str(realization or ctx["real1"]),
        e=str(ctx["builder_eval"]),
        tot=total,
        pas=passed,
        crit=critical,
        cov=coverage,
    )
    for i, (cat, p, crit) in enumerate(cases):
        await conn.execute(
            text(
                "INSERT INTO qualification_case_results (tenant_id, project_id, run_id, case_ref, case_category, passed, is_critical) VALUES (:t,:p,:r,:ref,:cat,:pas,:crit)"
            ),
            {
                "t": str(tenant or ctx["t1"]),
                "p": str(project or ctx["p1"]),
                "r": str(rid),
                "ref": f"case{i}",
                "cat": cat,
                "pas": p,
                "crit": crit,
            },
        )
    return rid


@pytest.mark.db
async def test_db_library_seeded_matches_registry(admin_engine):
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT archetype, min_aggregate_score, required_categories FROM archetype_evals WHERE eval_version='v1'"
                )
            )
        ).all()
    by = {r[0]: r for r in rows}
    assert set(by) == set(ARCHETYPES)  # no drift between the seed and the runtime enum
    assert (
        float(by["builder"][1]) == 0.85
        and float(by["reviewer"][1]) == 0.90
        and float(by["evidence_auditor"][1]) == 0.95
    )
    assert sorted(by["builder"][2]) == sorted(CASE_CATEGORIES)


@pytest.mark.db
async def test_db_library_uaid_app_select_only(rls_engine):
    with pytest.raises(Exception, match="permission denied"):
        async with rls_engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO archetype_evals (archetype, eval_version, representative_task_set, gold_answer_source, scoring_rubric, min_aggregate_score, require_zero_critical, min_cases, required_categories, refresh_policy) VALUES ('builder','v9','[]'::jsonb,'[]'::jsonb,'[]'::jsonb,0.5,true,5,'[]'::jsonb,'never')"
                )
            )
            await conn.commit()


@pytest.mark.db
async def test_db_run_passing_verdict_is_generated(admin_engine, qual_ctx):
    async with admin_engine.begin() as c:
        rid = await _insert_run(
            c, qual_ctx, total=5, passed=5, critical=0, coverage=True, cases=_PASS_CASES
        )
    async with admin_engine.connect() as c:
        verdict, agg = (
            await c.execute(
                text("SELECT verdict, aggregate_score FROM qualification_runs WHERE id=:i"),
                {"i": str(rid)},
            )
        ).one()
    assert verdict == "passed" and float(agg) == 1.0


@pytest.mark.db
async def test_db_run_failing_verdict(admin_engine, qual_ctx):
    cases = [
        ("positive", True, False),
        ("negative", True, False),
        ("edge", True, False),
        ("adversarial", False, False),
        ("incomplete", False, False),
    ]
    async with admin_engine.begin() as c:
        rid = await _insert_run(
            c, qual_ctx, total=5, passed=3, critical=0, coverage=True, cases=cases
        )
    async with admin_engine.connect() as c:
        verdict = await _scalar(c, "SELECT verdict FROM qualification_runs WHERE id=:i", i=str(rid))
    assert verdict == "failed"  # 3/5 = 0.6 < 0.85


@pytest.mark.db
async def test_db_fake_verdict_rejected_by_deferred_trigger(admin_engine, qual_ctx):
    # B3 — claim passed=5 but only 3 children passed ⇒ the deferred verify trigger rejects at commit.
    cases = [
        ("positive", True, False),
        ("negative", True, False),
        ("edge", True, False),
        ("adversarial", False, False),
        ("incomplete", False, False),
    ]
    with pytest.raises(Exception, match="do not match the recorded child cases"):
        async with admin_engine.begin() as c:
            await _insert_run(
                c, qual_ctx, total=5, passed=5, critical=0, coverage=True, cases=cases
            )


@pytest.mark.db
async def test_db_caller_cannot_write_verdict(admin_engine, qual_ctx):
    with pytest.raises(Exception, match="generated|cannot insert|GENERATED"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO qualification_runs (tenant_id, project_id, realization_id, archetype_eval_id, archetype, eval_version, min_aggregate_score, require_zero_critical, min_cases, required_categories, total_cases, passed_cases, critical_failure_count, coverage_complete, evaluated_by, verdict) VALUES (:t,:p,:r,:e,'builder','v1',0.850,true,5,'[]'::jsonb,5,5,0,true,'x','passed')"
                ),
                {
                    "t": str(qual_ctx["t1"]),
                    "p": str(qual_ctx["p1"]),
                    "r": str(qual_ctx["real1"]),
                    "e": str(qual_ctx["builder_eval"]),
                },
            )


@pytest.mark.db
async def test_db_run_rls_and_append_only(rls_engine, admin_engine, qual_ctx):
    async with admin_engine.begin() as c:
        rid = await _insert_run(
            c, qual_ctx, total=5, passed=5, critical=0, coverage=True, cases=_PASS_CASES
        )
    # RLS: t2 cannot see t1's run
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(qual_ctx["t2"])}
        )
        n = await _scalar(conn, "SELECT count(*) FROM qualification_runs WHERE id=:i", i=str(rid))
        assert n == 0
    # append-only: no UPDATE/DELETE
    for sql in (
        "UPDATE qualification_runs SET evaluated_by='x' WHERE id=:i",
        "DELETE FROM qualification_runs WHERE id=:i",
    ):
        with pytest.raises(Exception, match="append-only"):
            async with admin_engine.begin() as c:
                await c.execute(text(sql), {"i": str(rid)})


@pytest.mark.db
async def test_db_transition_passing_run_backstop(admin_engine, qual_ctx):
    # a PASSING run qualifies; a NULL run and a FAILING run are refused by the guard.
    async with admin_engine.begin() as c:
        passing = await _insert_run(
            c, qual_ctx, total=5, passed=5, critical=0, coverage=True, cases=_PASS_CASES
        )
    fail_cases = [
        ("positive", True, False),
        ("negative", True, False),
        ("edge", True, False),
        ("adversarial", False, False),
        ("incomplete", False, False),
    ]
    async with admin_engine.begin() as c:
        failing = await _insert_run(
            c, qual_ctx, total=5, passed=3, critical=0, coverage=True, cases=fail_cases
        )
    # no run id ⇒ refused
    with pytest.raises(Exception, match="requires qualified_via_run_id"):
        async with admin_engine.begin() as c:
            await c.execute(
                text("UPDATE agent_realizations SET qualification_status='qualified' WHERE id=:r"),
                {"r": str(qual_ctx["real1"])},
            )
    # failing run ⇒ refused
    with pytest.raises(Exception, match="PASSING run"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "UPDATE agent_realizations SET qualification_status='qualified', qualified_via_run_id=:q WHERE id=:r"
                ),
                {"q": str(failing), "r": str(qual_ctx["real1"])},
            )
    # passing run ⇒ qualified
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "UPDATE agent_realizations SET qualification_status='qualified', qualified_via_run_id=:q WHERE id=:r"
            ),
            {"q": str(passing), "r": str(qual_ctx["real1"])},
        )
    async with admin_engine.connect() as c:
        status = await _scalar(
            c,
            "SELECT qualification_status FROM agent_realizations WHERE id=:r",
            r=str(qual_ctx["real1"]),
        )
    assert status == "qualified"
