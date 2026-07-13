"""Slice 38 — Skill graph + Skill Matching Engine (§8/§26.4) tests.

Docker-free: the §8.2 skill catalog, bounds/regexes, the §8.3 VERBATIM transparent score (with
eval_performance neutralized to 0 until Slice 40, and the high-risk reliability rule zeroing
cost_latency), and build_squad (assignment, distinct reviewers §2.2, no-reviewer B5, missing-skill
factory requests, deterministic tie-break, caps). DB-backed (`db`): the 5-table store + migration
0037 (global uaid_app SELECT-only/admin-written B8, FK-normalized skills B3, immutability B7, RLS,
bounds B6), the repos, and the bit-stable no-A5/readiness guard. Deterministic — no LLM.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.repositories.production_autonomy import ProductionAutonomyRepository
from app.repositories.readiness import ReadinessRepository
from app.repositories.skills import (
    SquadRepository,
    capability_view,
    list_skills,
    register_capability,
    register_skill,
)
from app.tenancy import TenantContext, tenant_scope


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


def test_compute_reviewer_availability():
    from app.agents.skills import compute_reviewer_availability

    caps = [
        _cap("b1", "B", {"backend_engineering"}),
        _cap("r1", "R", {"backend_engineering"}, reviews={"backend_engineering"}),
    ]
    wu = _wu("API-001", {"backend_engineering"})
    assert compute_reviewer_availability(wu, "b1", caps) == 1.0  # r1 is a distinct reviewer
    assert (
        compute_reviewer_availability(wu, "r1", caps) == 0.0
    )  # only r1 reviews — but it's the builder


def test_validate_work_unit_rejects_bad_inputs():
    from app.agents.skills import validate_work_unit

    validate_work_unit(_wu("API-001", {"backend_engineering"}))  # ok
    for bad in (
        _wu("bad ref!", {"backend_engineering"}),
        _wu("API-001", {"Bad_Skill"}),  # skill regex
        _wu("API-001", {"backend_engineering"}, tools=("Bad Tool",)),  # tool regex
        _wu("API-001", {"backend_engineering"}, domain="Bad Domain"),  # domain regex
        _wu("API-001", {"backend_engineering"}, risk_level="extreme"),  # risk enum
        _wu("API-001", {"backend_engineering"}, cost_latency_fit=2.0),  # 0..1
        _wu("API-001", set()),  # no required skills
    ):
        with pytest.raises(ValueError):
            validate_work_unit(bad)


def test_validate_capability_rejects_bad_inputs():
    from app.agents.skills import MAX_PROVIDED_SKILLS, validate_capability

    validate_capability(_cap("b1", "B", {"backend_engineering"}))  # ok
    with pytest.raises(ValueError):
        validate_capability(_cap("b1", "B", {"Bad_Skill"}))  # skill regex
    with pytest.raises(ValueError):
        validate_capability(
            _cap("b1", "B", {"backend_engineering"}, tools=("Bad Tool",))
        )  # tool regex
    with pytest.raises(ValueError):
        validate_capability(_cap("b1", "B", {"backend_engineering"}, cost="extreme"))  # cost enum
    with pytest.raises(ValueError):
        validate_capability(
            _cap("b1", "B", {f"s_{i}" for i in range(MAX_PROVIDED_SKILLS + 1)})
        )  # count


def test_compute_agent_score_rejects_out_of_bounds_inputs():
    with pytest.raises(ValueError):
        compute_agent_score(_inputs(capability_match=2.0))
    with pytest.raises(ValueError):
        compute_agent_score(_inputs(risk_penalty=5.0))


def test_build_squad_validates_capabilities():
    # build_squad rejects a malformed capability up front.
    with pytest.raises(ValueError):
        build_squad([_wu("API-001", {"backend_engineering"})], [_cap("b1", "B", {"Bad_Skill"})])


# --- DB-backed: 5-table store + migration 0037 (B8/B3/B7/B6/RLS) -----------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def sk_ctx(admin_engine):
    """org/t1/t2/p1 + a GLOBAL blueprint with an admin-curated capability + one provided skill
    (referencing the migration-seeded `backend_engineering` skill)."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('SkOrg',:s) RETURNING id",
            s=f"sk-org-{sfx}",
        )
        t1 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t1',:s) RETURNING id",
            o=org,
            s=f"sk-t1-{sfx}",
        )
        t2 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t2',:s) RETURNING id",
            o=org,
            s=f"sk-t2-{sfx}",
        )
        p1 = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
            t=t1,
            s=f"sk-p1-{sfx}",
        )
        bp = await _scalar(
            c,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) VALUES (:k,'Backend','build',:a) RETURNING id",
            k=f"backend-{sfx}",
            a="builder",
        )
        cap = await _scalar(
            c,
            "INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class, provided_tools, domains) "
            "VALUES (:b,'medium','[]'::jsonb,'[]'::jsonb) RETURNING id",
            b=bp,
        )
        # a UNIQUE skill per fixture run, so the global (cross-test-accumulating) capability map
        # yields exactly THIS blueprint as the candidate for this test's work-unit.
        sk = f"sk_{sfx}"
        await c.execute(
            text("INSERT INTO skills (key, category) VALUES (:k, 'backend_engineering')"), {"k": sk}
        )
        await c.execute(
            text(
                "INSERT INTO agent_provided_skills (capability_id, skill_id, can_review) "
                "SELECT :c, id, false FROM skills WHERE key=:k"
            ),
            {"c": cap, "k": sk},
        )
    return {
        "t1": t1,
        "t2": t2,
        "p1": p1,
        "bp": bp,
        "bp_key": f"backend-{sfx}",
        "cap": cap,
        "sfx": sfx,
        "skill": sk,
    }


@pytest.mark.db
async def test_db_skills_seeded(admin_engine, sk_ctx):
    async with admin_engine.connect() as c:
        present = {r[0] for r in (await c.execute(text("SELECT key FROM skills"))).all()}
    assert set(SKILL_CATEGORIES) <= present  # the §8.2 vocabulary is migration-seeded (admin path)


@pytest.mark.db
async def test_db_runtime_cannot_write_any_global_table(rls_engine, sk_ctx):
    # B8 — uaid_app: SELECT ok; INSERT/UPDATE/DELETE/TRUNCATE denied on ALL THREE global tables.
    async with rls_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM skills"))).scalar_one() >= 1
    for table in ("skills", "agent_skill_capabilities", "agent_provided_skills"):
        for sql in (
            f"INSERT INTO {table} DEFAULT VALUES",
            f"UPDATE {table} SET id = id WHERE false",
            f"DELETE FROM {table} WHERE false",
            f"TRUNCATE {table}",
        ):
            async with rls_engine.connect() as conn:
                with pytest.raises(Exception):
                    await conn.execute(text(sql))
                    await conn.commit()


@pytest.mark.db
async def test_db_provided_skill_fk_rejects_unknown_skill(admin_engine, sk_ctx):
    # B3 — an unknown skill_id cannot persist (composite/FK to skills).
    with pytest.raises(Exception, match="foreign key|violates"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO agent_provided_skills (capability_id, skill_id, can_review) "
                    "VALUES (:cap, gen_random_uuid(), false)"
                ),
                {"cap": str(sk_ctx["cap"])},
            )


@pytest.mark.db
async def test_db_global_tables_immutable(admin_engine, sk_ctx):
    # B7 — even admin cannot UPDATE/DELETE/TRUNCATE any of the 3 global tables (block triggers).
    for sql in (
        "UPDATE skills SET description='z' WHERE key='security'",
        "UPDATE agent_skill_capabilities SET cost_latency_class='low' WHERE id=:cap",
        "DELETE FROM agent_provided_skills WHERE capability_id=:cap",
        "DELETE FROM agent_skill_capabilities WHERE id=:cap",
        "TRUNCATE skills",
        "TRUNCATE agent_skill_capabilities",
        "TRUNCATE agent_provided_skills",
    ):
        # blocked either by the append-only trigger or (for FK-referenced tables) by TRUNCATE-on-FK.
        with pytest.raises(Exception, match="append-only|immutable|cannot truncate"):
            async with admin_engine.begin() as c:
                await c.execute(text(sql), {"cap": str(sk_ctx["cap"])})


@pytest.mark.db
async def test_db_skill_match_component_bounds(admin_engine, sk_ctx):
    # B6 — a score component > 1.0 fails the CHECK.
    async with admin_engine.begin() as c:
        mid = await _scalar(
            c,
            "INSERT INTO squad_manifests (tenant_id, project_id, manifest, work_unit_count, "
            "missing_skill_count, ruleset_version, built_by) VALUES (:t,:p,'{}'::jsonb,0,0,'slice38.v1','a') RETURNING id",
            t=str(sk_ctx["t1"]),
            p=str(sk_ctx["p1"]),
        )
    with pytest.raises(Exception, match="check|violates"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO skill_matches (tenant_id, project_id, manifest_id, work_unit_ref, "
                    "blueprint_id, capability_match, domain_fit, tool_access_fit, eval_performance, "
                    "eval_source, reviewer_availability, cost_latency_fit, risk_penalty, total_score) "
                    "VALUES (:t,:p,:m,'API-001',:b, 9.0,0,0,0,'absent_until_slice40',0,0,0,9.0)"
                ),
                {
                    "t": str(sk_ctx["t1"]),
                    "p": str(sk_ctx["p1"]),
                    "m": str(mid),
                    "b": str(sk_ctx["bp"]),
                },
            )


@pytest.mark.db
async def test_db_squad_manifest_rls_cross_tenant(rls_engine, sk_ctx):
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(sk_ctx["t1"])}
        )
        mid = await _scalar(
            conn,
            "INSERT INTO squad_manifests (tenant_id, project_id, manifest, work_unit_count, "
            "missing_skill_count, ruleset_version, built_by) VALUES (:t,:p,'{}'::jsonb,0,0,'slice38.v1','a') RETURNING id",
            t=str(sk_ctx["t1"]),
            p=str(sk_ctx["p1"]),
        )
        await conn.commit()
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(sk_ctx["t2"])}
        )
        n = (
            await conn.execute(
                text("SELECT count(*) FROM squad_manifests WHERE id=:i"), {"i": str(mid)}
            )
        ).scalar_one()
        assert n == 0


@pytest.mark.db
async def test_db_squad_manifest_append_only(admin_engine, sk_ctx):
    async with admin_engine.begin() as c:
        mid = await _scalar(
            c,
            "INSERT INTO squad_manifests (tenant_id, project_id, manifest, work_unit_count, "
            "missing_skill_count, ruleset_version, built_by) VALUES (:t,:p,'{}'::jsonb,0,0,'slice38.v1','a') RETURNING id",
            t=str(sk_ctx["t1"]),
            p=str(sk_ctx["p1"]),
        )
    with pytest.raises(Exception, match="append-only|immutable"):
        async with admin_engine.begin() as c:
            await c.execute(text("DELETE FROM squad_manifests WHERE id=:i"), {"i": str(mid)})


# --- DB-backed: repository (admin-path register + tenant SquadRepository) ---------


@pytest.mark.db
async def test_register_capability_rejects_unknown_skill(admin_engine, sk_ctx):
    async with AsyncSession(admin_engine) as s:
        with pytest.raises(ValueError, match="unknown skill"):
            await register_capability(
                s, blueprint_id=sk_ctx["bp"], provided_skills=["not_a_real_skill"]
            )


@pytest.mark.db
async def test_squad_build_and_record_persists_manifest_and_matches(sk_ctx):
    # sk_ctx's blueprint provides backend_engineering ⇒ assigned; eval_performance neutral (Slice 40).
    ctx = TenantContext(sk_ctx["t1"])
    async with tenant_scope(ctx) as session:
        repo = SquadRepository(session, ctx)
        rec = await repo.build_and_record(
            project_id=sk_ctx["p1"],
            work_units=[WorkUnit(ref="API-001", required_skills=(sk_ctx["skill"],))],
            built_by="planner",
        )
        assert rec.work_unit_count == 1
        assert "API-001" in rec.manifest["active_agents"][0]["assigned_tasks"]
        matches = await repo.matches_for(rec.id)
        assert len(matches) == 1
        assert matches[0].blueprint_id == sk_ctx["bp"]
        assert matches[0].eval_source == "absent_until_slice40"
        assert float(matches[0].total_score) == 0.45  # 0.30 capability + 0.15 tool, eval 0


@pytest.mark.db
async def test_squad_latest_and_history(sk_ctx):
    ctx = TenantContext(sk_ctx["t1"])
    wus = [WorkUnit(ref="API-001", required_skills=(sk_ctx["skill"],))]
    async with tenant_scope(ctx) as session:
        repo = SquadRepository(session, ctx)
        await repo.build_and_record(project_id=sk_ctx["p1"], work_units=wus, built_by="a")
        second = await repo.build_and_record(project_id=sk_ctx["p1"], work_units=wus, built_by="a")
        assert (await repo.latest(sk_ctx["p1"])).id == second.id
        assert len(await repo.history(sk_ctx["p1"])) >= 2


@pytest.mark.db
async def test_squad_does_not_change_a5_or_readiness(sk_ctx):
    # Foundational, bit-stable: building a squad flips no A5 gate and touches no readiness snapshot.
    ctx = TenantContext(sk_ctx["t1"])
    async with tenant_scope(ctx) as session:
        pa = ProductionAutonomyRepository(session, ctx)
        before = (await pa.evaluate(sk_ctx["p1"])).to_dict()
        readiness_before = await ReadinessRepository(session, ctx).latest(sk_ctx["p1"])
        await SquadRepository(session, ctx).build_and_record(
            project_id=sk_ctx["p1"],
            work_units=[WorkUnit(ref="API-001", required_skills=(sk_ctx["skill"],))],
            built_by="a",
        )
        after = (await pa.evaluate(sk_ctx["p1"])).to_dict()
        readiness_after = await ReadinessRepository(session, ctx).latest(sk_ctx["p1"])
    assert before == after  # bit-stable
    assert after["ruleset_version"] == "slice51.v1"  # current A5 ruleset; unchanged by this feature
    assert readiness_before is None and readiness_after is None


@pytest.mark.db
async def test_db_list_skills_ordered(admin_engine, sk_ctx):
    async with AsyncSession(admin_engine) as s:
        first = [sk["key"] for sk in await list_skills(s)]
        second = [sk["key"] for sk in await list_skills(s)]
    assert first == second and len(first) == len(
        set(first)
    )  # deterministic (ORDER BY key), no dups
    assert set(SKILL_CATEGORIES) <= set(first)


@pytest.mark.db
async def test_db_admin_can_register_skill_and_capability(admin_engine, sk_ctx):
    key = f"customsk_{sk_ctx['sfx']}"
    async with AsyncSession(admin_engine) as s:
        await register_skill(s, key=key, category="security")
        cap = await register_capability(
            s,
            blueprint_id=sk_ctx["bp"],
            provided_skills=[key],
            reviewer_skills=[key],
            provided_tools=["github"],
            domains=["fintech"],
        )
        await s.commit()
        assert cap is not None
    async with AsyncSession(admin_engine) as s:
        assert any(sk["key"] == key for sk in await list_skills(s))


@pytest.mark.db
async def test_db_capability_rejects_bad_json_elements(admin_engine, sk_ctx):
    for col, val in (
        ("provided_tools", "[123]"),
        ("provided_tools", '["Bad Tool"]'),
        ("domains", '["Bad Domain"]'),
    ):
        with pytest.raises(Exception, match="invalid|violates|check"):
            async with admin_engine.begin() as c:
                await c.execute(
                    text(
                        f"INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class, {col}) "
                        "VALUES (:b, 'medium', CAST(:v AS jsonb))"
                    ),
                    {"b": str(sk_ctx["bp"]), "v": val},
                )


@pytest.mark.db
async def test_db_capability_rejects_too_many_tools(admin_engine, sk_ctx):
    big = "[" + ",".join(f'"t_{i}"' for i in range(65)) + "]"  # 65 > 64
    with pytest.raises(Exception, match="tools_array|violates|check"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class, provided_tools) "
                    "VALUES (:b, 'medium', CAST(:v AS jsonb))"
                ),
                {"b": str(sk_ctx["bp"]), "v": big},
            )


@pytest.mark.db
async def test_db_provided_skills_count_capped(admin_engine, sk_ctx):
    pfx = f"skc{sk_ctx['sfx']}_"
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO skills (key, category) SELECT :p || g, 'security' FROM generate_series(1, 130) g"
            ),
            {"p": pfx},
        )
        cap = await _scalar(
            c,
            "INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class) VALUES (:b,'medium') RETURNING id",
            b=str(sk_ctx["bp"]),
        )
    with pytest.raises(Exception, match="128 skills per capability|more than 128"):
        async with admin_engine.begin() as c:
            for i in range(1, 130):  # the 129th trips the per-capability guard (same-txn count)
                await c.execute(
                    text(
                        "INSERT INTO agent_provided_skills (capability_id, skill_id) SELECT :cap, id FROM skills WHERE key = :k"
                    ),
                    {"cap": str(cap), "k": f"{pfx}{i}"},
                )


@pytest.mark.db
async def test_db_manifest_oversize_rejected(admin_engine, sk_ctx):
    big = '{"x":"' + "y" * 270000 + '"}'  # > 262144 bytes
    with pytest.raises(Exception, match="manifest_bounded|violates|check"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO squad_manifests (tenant_id, project_id, manifest, work_unit_count, "
                    "missing_skill_count, ruleset_version, built_by) VALUES (:t,:p,CAST(:m AS jsonb),0,0,'slice38.v1','a')"
                ),
                {"t": str(sk_ctx["t1"]), "p": str(sk_ctx["p1"]), "m": big},
            )


@pytest.mark.db
async def test_db_skill_match_cross_tenant_manifest_fk_rejected(admin_engine, sk_ctx):
    async with admin_engine.begin() as c:
        mid = await _scalar(
            c,
            "INSERT INTO squad_manifests (tenant_id, project_id, manifest, work_unit_count, "
            "missing_skill_count, ruleset_version, built_by) VALUES (:t,:p,'{}'::jsonb,0,0,'slice38.v1','a') RETURNING id",
            t=str(sk_ctx["t1"]),
            p=str(sk_ctx["p1"]),
        )
        px = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PX',:s) RETURNING id",
            t=str(sk_ctx["t2"]),
            s=f"skpx-{sk_ctx['sfx']}",
        )
    with pytest.raises(Exception, match="foreign key|manifest_project_tenant"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO skill_matches (tenant_id, project_id, manifest_id, work_unit_ref, blueprint_id, "
                    "capability_match, domain_fit, tool_access_fit, eval_performance, eval_source, "
                    "reviewer_availability, cost_latency_fit, risk_penalty, total_score) "
                    "VALUES (:t,:p,:m,'API-001',:b,1,0,0,0,'absent_until_slice40',0,0,0,0.3)"
                ),
                {"t": str(sk_ctx["t2"]), "p": str(px), "m": str(mid), "b": str(sk_ctx["bp"])},
            )


@pytest.mark.db
async def test_db_capability_view_latest_wins(admin_engine, sk_ctx):
    sk2 = f"skl_{sk_ctx['sfx']}"
    async with admin_engine.begin() as c:
        await c.execute(
            text("INSERT INTO skills (key, category) VALUES (:k,'security')"), {"k": sk2}
        )
        cap2 = await _scalar(
            c,
            "INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class) VALUES (:b,'high') RETURNING id",
            b=str(sk_ctx["bp"]),
        )
        await c.execute(
            text(
                "INSERT INTO agent_provided_skills (capability_id, skill_id) SELECT :cap, id FROM skills WHERE key=:k"
            ),
            {"cap": str(cap2), "k": sk2},
        )
    async with AsyncSession(admin_engine) as s:
        caps, _ = await capability_view(s)
    mine = next(cp for cp in caps if cp.blueprint_ref == sk_ctx["bp_key"])
    assert mine.cost_latency_class == "high"  # the LATEST capability, not the fixture's 'medium'
    assert sk2 in mine.provided_skills


@pytest.mark.db
async def test_db_squad_audit_safe_and_global_unaudited(admin_engine, sk_ctx):
    ctx = TenantContext(sk_ctx["t1"])
    async with tenant_scope(ctx) as session:
        rec = await SquadRepository(session, ctx).build_and_record(
            project_id=sk_ctx["p1"],
            work_units=[WorkUnit(ref="API-001", required_skills=(sk_ctx["skill"],))],
            built_by="planner",
        )
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"squad_manifest:{rec.id}", "t": str(sk_ctx["t1"])},
            )
        ).scalar_one()
        assert payload["squad_manifest_id"] == str(rec.id) and "work_unit_count" in payload
        n = (
            await c.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE action LIKE 'skill%' OR action LIKE 'capability%'"
                )
            )
        ).scalar_one()
        assert n == 0  # global skill/capability registration is unaudited (D-38-12)


@pytest.mark.db
async def test_db_b6_enum_and_regex_rejections(admin_engine, sk_ctx):
    # B6 — direct-SQL CHECK rejections: cost-class enum, skills.key regex, too-many-domains (>32).
    many_domains = "[" + ",".join(f'"d_{i}"' for i in range(33)) + "]"
    cases = [
        (
            "INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class) VALUES (:b, 'extreme')",
            {"b": str(sk_ctx["bp"])},
        ),
        ("INSERT INTO skills (key, category) VALUES ('Bad Key', 'security')", {}),
        (
            "INSERT INTO agent_skill_capabilities (blueprint_id, cost_latency_class, domains) "
            "VALUES (:b, 'medium', CAST(:d AS jsonb))",
            {"b": str(sk_ctx["bp"]), "d": many_domains},
        ),
    ]
    for sql, params in cases:
        with pytest.raises(Exception, match="violates|check|invalid"):
            async with admin_engine.begin() as c:
                await c.execute(text(sql), params)


@pytest.mark.db
async def test_db_skill_match_work_unit_ref_regex_rejected(admin_engine, sk_ctx):
    async with admin_engine.begin() as c:
        mid = await _scalar(
            c,
            "INSERT INTO squad_manifests (tenant_id, project_id, manifest, work_unit_count, "
            "missing_skill_count, ruleset_version, built_by) VALUES (:t,:p,'{}'::jsonb,0,0,'slice38.v1','a') RETURNING id",
            t=str(sk_ctx["t1"]),
            p=str(sk_ctx["p1"]),
        )
    with pytest.raises(Exception, match="work_unit_ref|violates|check"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO skill_matches (tenant_id, project_id, manifest_id, work_unit_ref, blueprint_id, "
                    "capability_match, domain_fit, tool_access_fit, eval_performance, eval_source, "
                    "reviewer_availability, cost_latency_fit, risk_penalty, total_score) "
                    "VALUES (:t,:p,:m,'bad ref!',:b,1,0,0,0,'absent_until_slice40',0,0,0,0.3)"
                ),
                {
                    "t": str(sk_ctx["t1"]),
                    "p": str(sk_ctx["p1"]),
                    "m": str(mid),
                    "b": str(sk_ctx["bp"]),
                },
            )


@pytest.mark.db
async def test_db_skill_match_rls_cross_tenant(rls_engine, sk_ctx):
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(sk_ctx["t1"])}
        )
        mid = await _scalar(
            conn,
            "INSERT INTO squad_manifests (tenant_id, project_id, manifest, work_unit_count, "
            "missing_skill_count, ruleset_version, built_by) VALUES (:t,:p,'{}'::jsonb,0,0,'slice38.v1','a') RETURNING id",
            t=str(sk_ctx["t1"]),
            p=str(sk_ctx["p1"]),
        )
        smid = await _scalar(
            conn,
            "INSERT INTO skill_matches (tenant_id, project_id, manifest_id, work_unit_ref, blueprint_id, "
            "capability_match, domain_fit, tool_access_fit, eval_performance, eval_source, "
            "reviewer_availability, cost_latency_fit, risk_penalty, total_score) "
            "VALUES (:t,:p,:m,'API-001',:b,1,0,0,0,'absent_until_slice40',0,0,0,0.3) RETURNING id",
            t=str(sk_ctx["t1"]),
            p=str(sk_ctx["p1"]),
            m=str(mid),
            b=str(sk_ctx["bp"]),
        )
        await conn.commit()
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(sk_ctx["t2"])}
        )
        n = (
            await conn.execute(
                text("SELECT count(*) FROM skill_matches WHERE id=:i"), {"i": str(smid)}
            )
        ).scalar_one()
        assert n == 0
