"""Slice 38 — Skill graph + Skill Matching Engine (§8/§26.4) tests.

Docker-free: the §8.2 skill catalog, bounds/regexes, the §8.3 VERBATIM transparent score (with
eval_performance neutralized to 0 until Slice 40, and the high-risk reliability rule zeroing
cost_latency), and build_squad (assignment, distinct reviewers §2.2, no-reviewer B5, missing-skill
factory requests, deterministic tie-break, caps). DB-backed (`db`): the 5-table store + migration
0037 (global uaid_app SELECT-only/admin-written B8, FK-normalized skills B3, immutability B7, RLS,
bounds B6), the repos, and the bit-stable no-A5/readiness guard. Deterministic — no LLM.
"""

import pytest

from app.agents.skills import (
    COST_LATENCY_CLASSES,
    MANIFEST_JSON_MAX_BYTES,
    MAX_CANDIDATES_SCORED_PER_UNIT,
    MAX_MATCH_ROWS,
    MAX_WORK_UNITS,
    RISK_LEVELS,
    RULESET_VERSION,
    SCORE_WEIGHTS,
    SKILL_CATEGORIES,
    SKILL_KEY_RE,
    WORK_UNIT_REF_RE,
    AgentCapability,
    MatchInputs,
    WorkUnit,
    build_squad,
    compute_agent_score,
    compute_capability_match,
    validate_skill_key,
)


# --- Docker-free: catalog / weights / bounds -------------------------------------


def test_skill_categories_are_the_spec_8_2_set():
    # §8.2 (spec:721-749) — a representative spread must be present; snake_case machine values.
    for k in (
        "backend_engineering",
        "security",
        "knowledge_graph_engineering",
        "release_management",
    ):
        assert k in SKILL_CATEGORIES
    assert len(SKILL_CATEGORIES) == 27
    assert all(SKILL_KEY_RE.match(k) for k in SKILL_CATEGORIES)


def test_score_weights_are_verbatim_8_3():
    assert SCORE_WEIGHTS == {
        "capability_match": 0.30,
        "domain_fit": 0.15,
        "tool_access_fit": 0.15,
        "eval_performance": 0.20,
        "reviewer_availability": 0.10,
        "cost_latency_fit": 0.10,
    }
    assert RULESET_VERSION == "slice38.v1"


def test_bounds_and_enums():
    assert (MAX_WORK_UNITS, MAX_CANDIDATES_SCORED_PER_UNIT, MAX_MATCH_ROWS) == (128, 32, 4096)
    assert MANIFEST_JSON_MAX_BYTES == 262144
    assert COST_LATENCY_CLASSES == ("low", "medium", "high")
    assert RISK_LEVELS == ("low", "medium", "high")


def test_validate_skill_key():
    assert validate_skill_key("backend_engineering") == "backend_engineering"
    for bad in ("Backend", "with space", "", "x" * 80, "1leading"):
        with pytest.raises(ValueError):
            validate_skill_key(bad)


def test_work_unit_ref_regex():
    assert WORK_UNIT_REF_RE.match("API-001")
    assert not WORK_UNIT_REF_RE.match("bad ref!")


# --- Docker-free: §8.3 transparent score -----------------------------------------


def _inputs(**over):
    base = dict(
        capability_match=1.0,
        domain_fit=1.0,
        tool_access_fit=1.0,
        eval_performance=0.0,
        reviewer_availability=1.0,
        cost_latency_fit=1.0,
        risk_penalty=0.0,
        high_risk=False,
        eval_source="absent_until_slice40",
    )
    base.update(over)
    return MatchInputs(**base)


def test_compute_capability_match():
    assert compute_capability_match(("a", "b"), {"a", "b", "c"}) == 1.0
    assert compute_capability_match(("a", "b"), {"a"}) == 0.5
    assert compute_capability_match(("a",), set()) == 0.0
    assert compute_capability_match((), {"a"}) == 0.0  # degenerate: no required skills


def test_compute_agent_score_verbatim_and_eval_neutralized():
    b = compute_agent_score(_inputs())
    # 0.30+0.15+0.15 + (eval 0)*0.20 + 0.10 + 0.10 - 0 = 0.80 (max achievable until Slice 40 evals).
    assert b.total_score == 0.80
    assert b.eval_performance == 0.0 and b.eval_source == "absent_until_slice40"
    # breakdown echoes the inputs used (transparency).
    assert b.capability_match == 1.0 and b.cost_latency_fit == 1.0


def test_compute_agent_score_high_risk_zeroes_cost_latency():
    b = compute_agent_score(_inputs(high_risk=True, risk_penalty=0.2))
    # cost_latency zeroed by the §8.3 reliability rule: 0.30+0.15+0.15+0+0.10+0 - 0.2 = 0.50.
    assert b.total_score == 0.50
    assert b.cost_latency_fit == 0.0  # transparently recorded as zeroed


# --- Docker-free: build_squad ----------------------------------------------------


def _cap(ref, role, skills, *, tools=(), domains=(), reviews=(), cost="medium"):
    return AgentCapability(
        blueprint_ref=ref,
        role=role,
        provided_skills=frozenset(skills),
        provided_tools=frozenset(tools),
        domains=frozenset(domains),
        cost_latency_class=cost,
        reviewer_skills=frozenset(reviews),
    )


def _wu(ref, skills, **over):
    return WorkUnit(
        ref=ref,
        required_skills=tuple(skills),
        required_tools=tuple(over.get("tools", ())),
        domain=over.get("domain"),
        risk_level=over.get("risk_level", "low"),
        cost_latency_fit=over.get("cost_latency_fit", 0.0),
    )


def test_build_squad_assigns_best_and_records_matches():
    caps = [
        _cap("backend_v1", "Backend Engineer", {"backend_engineering"}),
        _cap("frontend_v1", "Frontend Engineer", {"frontend_engineering"}),
        _cap(
            "backend_reviewer_v1",
            "Backend Reviewer",
            {"backend_engineering"},
            reviews={"backend_engineering"},
        ),
    ]
    manifest, matches = build_squad([_wu("API-001", {"backend_engineering"})], caps)
    assigned = {a.blueprint_ref for a in manifest.active_agents}
    assert "backend_v1" in assigned
    api = next(a for a in manifest.active_agents if a.blueprint_ref == "backend_v1")
    assert "API-001" in api.assigned_work_units
    assert "backend_reviewer_v1" in api.reviewers  # distinct capable reviewer
    assert any(m.work_unit_ref == "API-001" and m.blueprint_ref == "backend_v1" for m in matches)


def test_build_squad_reviewer_is_never_the_builder():
    # The only backend agent can also review — it must NOT review its own work (§2.2).
    caps = [_cap("backend_v1", "Backend", {"backend_engineering"}, reviews={"backend_engineering"})]
    manifest, _ = build_squad([_wu("API-001", {"backend_engineering"})], caps)
    api = next(a for a in manifest.active_agents if a.blueprint_ref == "backend_v1")
    assert "backend_v1" not in api.reviewers


def test_build_squad_no_distinct_reviewer_flags_factory_request():
    # B5: builder exists, no distinct reviewer ⇒ empty reviewers + reviewer:<skill> + factory request.
    caps = [_cap("backend_v1", "Backend", {"backend_engineering"}, reviews={"backend_engineering"})]
    manifest, matches = build_squad([_wu("API-001", {"backend_engineering"})], caps)
    api = next(a for a in manifest.active_agents if a.blueprint_ref == "backend_v1")
    assert api.reviewers == ()
    assert "reviewer:backend_engineering" in manifest.missing_skills
    assert any("reviewer" in r for r in manifest.agent_factory_requests)
    assert next(m for m in matches if m.blueprint_ref == "backend_v1").reviewer_availability == 0.0


def test_build_squad_missing_skill_emits_factory_request():
    caps = [_cap("backend_v1", "Backend", {"backend_engineering"})]
    manifest, _ = build_squad([_wu("KG-001", {"knowledge_graph_engineering"})], caps)
    assert "knowledge_graph_engineering" in manifest.missing_skills
    assert any("knowledge_graph_engineering" in r for r in manifest.agent_factory_requests)
    assert all("KG-001" not in a.assigned_work_units for a in manifest.active_agents)


def test_build_squad_deterministic_tie_break():
    # Two agents cover the skill equally ⇒ assign the lexicographically smaller blueprint_ref.
    caps = [
        _cap("backend_zzz", "Backend", {"backend_engineering"}),
        _cap("backend_aaa", "Backend", {"backend_engineering"}),
    ]
    manifest, _ = build_squad([_wu("API-001", {"backend_engineering"})], caps)
    api = next(a for a in manifest.active_agents if "API-001" in a.assigned_work_units)
    assert api.blueprint_ref == "backend_aaa"


def test_build_squad_rejects_too_many_work_units():
    caps = [_cap("backend_v1", "Backend", {"backend_engineering"})]
    too_many = [_wu(f"API-{i:03d}", {"backend_engineering"}) for i in range(MAX_WORK_UNITS + 1)]
    with pytest.raises(ValueError):
        build_squad(too_many, caps)
