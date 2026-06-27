# Slice 38 — Skill graph + Skill Matching Engine — PLAN v4

**Status:** AWAITING PLAN REVIEW (v1–v3 REJECTED; v4 **= v3 + B9/B10 version-label & sequencing cleanup**; B1–B8 settled) — **plan-only; no branch / no code / no migration / no tests / no PR beyond this planning artifact.**

> **Revision log — v3 → v4 (B9/B10 — label & sequencing consistency):**
> - **B9 — all version labels consistent at v4** (the title, the §1 body, and the §2 heading were stale at `v2`; only the historical revision-log entries below reference older versions).
> - **B10 — §9 sequencing step 3 corrected** to the §5 admin-path design (admin-path module functions `register_skill`/`register_capability` + runtime `capability_view` SELECT + tenant-audited `SquadRepository`).
> - **No change to settled B1–B8 content.**
>
> **Revision log — v2 → v3 (B8 — global-table trust zone):**
> - **B8 — global admin tables grant `uaid_app` SELECT ONLY** (cf. Slice-6 `0007:231-232`, verified). The runtime role can **read** the vocab/capability map but **cannot INSERT/UPDATE/DELETE/TRUNCATE** it; global writes happen **only via the admin role** (migration seed / admin session), matching the module-level `register_blueprint`/`register_version` admin functions (`registry.py:102,125`). This closes the v2 hole where `uaid_app` could mutate **unaudited** global state outside tenant audit (trust-zone break). Tenant `squad_manifests`/`skill_matches` are unchanged (runtime SELECT/INSERT, RLS, tenant-audited). **All other v2 fixes stand unchurned** (Neo4j, ODs, `skill_matches`, FK-normalized skills, no-reviewer, bounds, immutability).
>
> **Revision log — v1 → v2 (Neo4j ruling + B1–B7 accepted):**
> - **Neo4j ruling — Postgres/Alembic ONLY (D-38-0).** The skill "graph" is modeled **relationally in Postgres** (adjacency via FK rows); **NO Neo4j, NO external graph store, NO `NEO4J_*` env reads** (legacy `.env` keys are ignored — CLAUDE.md "Other `.env` keys … are ignored"). Verified: README `5-8` (Postgres/Redis/Chroma), `docker-compose.yml` (no Neo4j), `pyproject.toml` (no driver), CLAUDE.md (KG-store is future).
> - **B1 — all decisions BOUND** (former OD-1…4 ruled: proceed now; admin-curated capability map; **no read endpoint** this slice; **no global platform audit**). The "MAY endpoint" language is removed.
> - **B2 — transparent match records persisted.** New tenant-scoped, append-only **`skill_matches`** table storing the **full §8.3 per-component breakdown** per (work-unit, candidate agent) — score transparency is DB-persisted, not just computed.
> - **B3 — capability integrity DB-bound.** Skill references are **normalized + FK-proven**: `agent_provided_skills(capability_id, skill_id→skills, can_review)` — an unknown skill key **cannot persist** (FK). Tools/domains are bounded JSON (no catalog to FK).
> - **B4 — global-audit contradiction resolved.** **No global platform audit this slice** (cf. Slice-6 global registration, `registry.py:5-19`); only the **tenant** `squad_manifests`/`skill_matches` writes are audited (tenant-GUC `audit_append`).
> - **B5 — no-reviewer behavior bound** (D-38-11): no distinct capable reviewer ⇒ `reviewer_availability=0.0` + empty `reviewers[]` + a `missing_skills:"reviewer:<skill>"` + an `agent_factory_requests` entry — never self-review (§2.2). Tested.
> - **B6 — exact bounds/caps + regexes bound** (§3.1) with pure + DB tests.
> - **B7 — exact immutability bound**: `skills` = permanent vocab (immutable append-only); `agent_skill_capabilities` + `agent_provided_skills` = **append-only, latest-wins** (no UPDATE/DELETE/TRUNCATE). "append-only-ish" removed.

> **Persona.** Senior agent-platform / release-governance backend architect (Sanad-provenance + security-reviewer hats).
> **Track / placement.** Roadmap §5 **Track A (cont.) — Phase 4 entry** (`GO-LIVE-END-TO-END-ROADMAP.md:333-345`). First Phase-4 slice after Phase-3 connectors (26–34) + Track-B (35–37) merged. **Foundational — flips NO A5 gate**; go-live false.

> **Provenance (Sanad — verified this session):**
> - **§8.1** (`spec:694-711`): determine required capabilities + which agents perform the work; 12 match dimensions incl. **risk**.
> - **§8.2** (`spec:713-749`): graph `Project → requirement → task → skill → agent capability → tool access → reviewer → evidence requirement` + 27 skill categories.
> - **§8.3** (`spec:751-766`): **transparent** score `capability_match*0.30 + domain_fit*0.15 + tool_access_fit*0.15 + eval_performance*0.20 + reviewer_availability*0.10 + cost_latency_fit*0.10 − risk_penalty`; "High-risk work must favor reliability over cost or speed."
> - **§8.4** (`spec:768-795`): `project_squad` — `active_agents[{id,role,assigned_tasks[],reviewers[]}]`, `missing_skills[]`, `agent_factory_requests[]`.
> - **§26.4** (`spec:2474-2485`): Phase-4 = skill graph (this) + registry (Slice 6) + realization (39) + evals/QA (40) + security/monitoring/replacement (41).
> - **Reuse**: `app/agents/registry.py` `ARCHETYPES` (11) + **global** `agent_blueprints`; `app/tenancy.py`; Slice-26 latest-wins + Slice-22…25/37 append-only store patterns; Slice-37 FK-proven-provenance lesson.
> - **Confirmed by grep — NO skill code exists**; migration head `0036` ⇒ this slice is **`0037`**.

---

## 0. Scope & non-goals
- **Scope.** A **DETERMINISTIC (no-LLM), Postgres-only** Skill Matching Engine: (1) a **global skill catalog** (§8.2 categories, FK-referenceable); (2) a **global agent→skill capability map** over Slice-6 blueprints, with **FK-normalized skills** (B3); (3) the **§8.3 transparent score** as a pure function with the full per-component breakdown; (4) per-build, tenant-scoped, append-only **`skill_matches`** (the persisted breakdown, B2) + a **`squad_manifests`** snapshot (§8.4 shape) over **declared work-units**.
- **Non-goals.** NO agent realization (39) / broker wiring / eval execution or qualification (40) / security review (41) / agent execution. **NO LLM, no tool broker, NO Neo4j/external graph store, NO `NEO4J_*` reads.** NO task-contract model (§13.2 = Slice 42; work-units are declared inputs). **NO A5/readiness/go-live change** (bit-stable; go-live false). **No HTTP endpoint this slice** (deferred). Deterministic only — no ML skill inference.

## 1. The honest-inputs constraint (unchanged crux)
§8.3's inputs do not all have a real source at Slice 38; this plan classifies each and **never fabricates** a missing one:
| §8.3 component | Weight | Source at Slice 38 | Rule |
|---|---|---|---|
| `capability_match` | 0.30 | **Real** — FK-normalized provided-skills ∩ work-unit required-skills | computed fraction `0..1` |
| `domain_fit` | 0.15 | **Declared** (caller) | `caller_supplied_unverified`; `0.0` if undeclared |
| `tool_access_fit` | 0.15 | **Real** — capability `provided_tools` ∩ required tools | computed `0..1` |
| `eval_performance` | 0.20 | **DEFERRED → Slice 40** | **neutral `0.0`**, persisted `eval_source='absent_until_slice40'`; NEVER invented |
| `reviewer_availability` | 0.10 | **Real** — ≥1 distinct capable reviewer (B5) | `0/1` |
| `cost_latency_fit` | 0.10 | **Declared** (caller) | `0.0` if undeclared |
| `risk_penalty` | − | **Declared** work-unit `risk_level` | high-risk → §8.3 reliability rule (D-38-5) |
**Stated in the manifest + every match row:** with `eval_performance` neutralized until Slice 40, a score is a **transparent ranking aid, NOT a qualification or authorization**.

## 2. BOUND decisions (v4 — final, all closed)
- **D-38-0 — Postgres/Alembic only**; no Neo4j/external graph store; no `NEO4J_*` reads (Neo4j ruling).
- **D-38-1 — Deterministic, no LLM** (§8.3 is arithmetic).
- **D-38-2 — `skills` GLOBAL + admin-curated, immutable append-only, NOT RLS** (shared vocab, cf. `agent_blueprints`); seeded with the §8.2 27 categories; `key` regex-bounded + UNIQUE.
- **D-38-3 — capability map GLOBAL + admin-curated, append-only latest-wins** (B7), keyed by **blueprint**; **skills FK-normalized** via `agent_provided_skills` (B3 — unknown skill keys cannot persist); tools/domains bounded JSON; `cost_latency_class` enum.
- **D-38-4 — §8.3 score is a PURE function** `compute_agent_score(MatchInputs) -> ScoreBreakdown` with verbatim weights; returns total **and** every weighted component (transparency); inputs bounded `0.0..1.0`; total reported raw (ranking only, never a threshold/authorization).
- **D-38-5 — High-risk reliability (§8.3 l.766)**: `risk_level='high'` ⇒ `cost_latency_fit` contribution **zeroed** before the sum **and** `risk_penalty` applies.
- **D-38-6 — Work-units are a DECLARED input** `{ref, required_skills[], required_tools[], domain?, risk_level, cost_latency_fit?}` (NOT spine artifacts; task contracts = Slice 42).
- **D-38-7 — `squad_manifests` + `skill_matches` tenant-scoped, append-only** (B2): one manifest per build (§8.4 shape) + one `skill_matches` row per (work-unit, scored candidate) carrying the **full breakdown**; RLS; audit safe-metadata only.
- **D-38-8 — `eval_performance` neutral-until-Slice-40** = `0.0` + `eval_source='absent_until_slice40'`; never fabricated.
- **D-38-9 — NO read endpoint this slice** (OD-3 ruling; deferred to a later surfacing slice).
- **D-38-10 — Migration `0037`; store/infra-only; bit-stable** (`production_autonomy.py`/`readiness.py` UNTOUCHED; go-live false).
- **D-38-11 — No reviewer self-assignment (§2.2) + no-reviewer behavior (B5)**: reviewers are distinct capable reviewer-archetype agents ≠ the assigned builder; if none exists ⇒ `reviewer_availability=0.0` + empty `reviewers[]` + `missing_skills:"reviewer:<skill>"` + an `agent_factory_requests` entry.
- **D-38-12 — No global platform audit (B4/OD-4)**: global skill/capability registration is **unaudited** (no tenant GUC; cf. Slice 6); only tenant `squad_manifests`/`skill_matches` are audited.
- **D-38-13 — Global tables are `uaid_app` SELECT-only, admin-written (B8)**: `skills`/`agent_skill_capabilities`/`agent_provided_skills` grant **SELECT only** to the runtime role; INSERTs occur **only via an admin session / migration seed** (cf. Slice-6 `0007:231-232`). The runtime role can never mutate unaudited global state — a trust-zone invariant, not just a convention.

## 3. Pure module — `app/agents/skills.py`
### 3.1 constants + bounds (B6)
`SKILL_CATEGORIES` (§8.2 27 values). `SCORE_WEIGHTS` (§8.3 verbatim). Regexes: `SKILL_KEY_RE=^[a-z][a-z0-9_]{1,63}$`, `TOOL_KEY_RE=^[a-z][a-z0-9_.]{1,63}$`, `DOMAIN_RE=^[a-z][a-z0-9_]{1,63}$`, `WORK_UNIT_REF_RE=^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$`. Caps: `MAX_WORK_UNITS=128`, `MAX_REQUIRED_SKILLS_PER_UNIT=32`, `MAX_REQUIRED_TOOLS_PER_UNIT=32`, `MAX_PROVIDED_SKILLS=128`, `MAX_PROVIDED_TOOLS=64`, `MAX_DOMAINS=32`, `MAX_CANDIDATES_SCORED_PER_UNIT=32`, `MAX_MATCH_ROWS=4096`, `MANIFEST_JSON_MAX_BYTES=262144`. `COST_LATENCY_CLASSES=(low,medium,high)`, `RISK_LEVELS=(low,medium,high)`. `RULESET_VERSION="slice38.v1"`.
### 3.2 score + builders
`MatchInputs` (7 bounded components + `eval_source`) + `ScoreBreakdown` (each weighted contribution + total). `compute_capability_match`/`compute_tool_access_fit` (fraction covered, `0..1`); `compute_reviewer_availability` (0/1, B5). `compute_agent_score(MatchInputs) -> ScoreBreakdown` (verbatim sum; D-38-5 high-risk zeroes cost_latency). `build_squad(work_units, capability_view) -> (SquadManifest, list[MatchRecord])`: validate/bound inputs; per work-unit score candidates with `capability_match>0` (cap `MAX_CANDIDATES_SCORED_PER_UNIT`); assign best (tie-break `score desc, blueprint_ref asc`); pick distinct reviewers (B5/D-38-11); collect `missing_skills` + one `agent_factory_requests` per missing skill (incl. missing reviewers); emit the §8.4 manifest + the per-(unit,candidate) match records. Pure, deterministic.

## 4. Storage + migration `0037` (5 tables; purely additive)
**GLOBAL (admin-curated, NOT RLS; **admin-written** via migration seed / admin session — `uaid_app` gets **SELECT ONLY** (B8, cf. Slice-6 `0007:231-232`); immutable/append-only block triggers ⇒ no UPDATE/DELETE/TRUNCATE by anyone):**
- **`skills`** — `id`/`key`(UNIQUE, CHECK `SKILL_KEY_RE`)/`category`(CHECK ∈ SKILL_CATEGORIES)/`description`(bounded)/`created_at`. Permanent vocab (B7).
- **`agent_skill_capabilities`** — `id`/`blueprint_id`(FK→`agent_blueprints`)/`cost_latency_class`(CHECK enum)/`provided_tools`(jsonb, CHECK bounded string array ≤`MAX_PROVIDED_TOOLS`, each `TOOL_KEY_RE`)/`domains`(jsonb, CHECK bounded ≤`MAX_DOMAINS`)/`created_at`. Append-only latest-wins (B7).
- **`agent_provided_skills`** — `id`/`capability_id`(FK→`agent_skill_capabilities`)/`skill_id`(**FK→`skills`** — B3 existence)/`can_review`(bool)/`created_at`; UNIQUE(`capability_id`,`skill_id`). Append-only.
**TENANT-OWNED (RLS ENABLE+FORCE + `tenant_isolation`; SELECT/INSERT only; audited):**
- **`squad_manifests`** — `id`/`tenant_id`/`project_id`/`manifest`(jsonb, CHECK `octet_length ≤ MANIFEST_JSON_MAX_BYTES`)/`work_unit_count`(CHECK 0..`MAX_WORK_UNITS`)/`missing_skill_count`(CHECK≥0)/`ruleset_version`/`built_by`/`created_at`(clock_timestamp). Composite FK `(project_id,tenant_id)→projects`; **UNIQUE(id,project_id,tenant_id)** (child FK target).
- **`skill_matches`** — `id`/`tenant_id`/`project_id`/`manifest_id`/`work_unit_ref`(CHECK `WORK_UNIT_REF_RE`)/`blueprint_id`(FK→`agent_blueprints`)/`capability_match`/`domain_fit`/`tool_access_fit`/`eval_performance`/`eval_source`/`reviewer_availability`/`cost_latency_fit`/`risk_penalty`/`total_score`(all NUMERIC, component CHECK `0..1`)/`created_at`. Composite FK `(manifest_id,project_id,tenant_id)→squad_manifests`. (B2 — persisted transparency.)
Slice-6 tables untouched; reuses `agent_blueprints`.

## 5. Repository — `app/repositories/skills.py`
- **Admin-path module functions** (take an **admin session**, like Slice-6 `register_blueprint`/`register_version` — NOT runnable as `uaid_app`, B8): `register_skill(admin_session, …)`, `register_capability(admin_session, …)` (validates skill keys exist), `list_skills`. **Unaudited (D-38-12; admin-path, no tenant GUC).** `capability_view(session)` (latest capability per blueprint + its FK-proven skills) is a **SELECT** read usable by the runtime (`uaid_app`) during a build.
- `SquadRepository(TenantScopedRepository)`: `build_and_record(project_id, work_units, built_by) -> SquadManifest` (load `capability_view`, call pure `build_squad`, persist the manifest + all `skill_matches` in one txn, audit safe-metadata only — counts/per-build only, never declared domain/risk prose), `latest(project_id)`, `history(project_id)`, `matches_for(manifest_id)`. Inside `tenant_scope`. `built_by` UNTRUSTED.

## 6. A5 / readiness impact
- **NONE — bit-stable.** `production_autonomy.py`/`readiness.py` UNTOUCHED; `before==after` A5 + readiness-level-unchanged regression. Foundational; go-live false.

## 7. Tenant / RLS / FK / audit / immutability
Global tables NOT RLS (shared vocab/role props, cf. blueprints) — **`uaid_app` SELECT-only; admin-written (B8, cf. `0007:231-232`)**; immutable/append-only block triggers ⇒ no UPDATE/DELETE/TRUNCATE by anyone (B7). Tenant tables RLS ENABLE+FORCE + `tenant_isolation`, append-only, composite FK to project+tenant + the `skill_matches→squad_manifests` composite FK; audit safe-metadata only (counts — never declared prose); skill keys FK-proven (B3). No secret material anywhere; no `NEO4J_*`.

## 8. Tests (DB-backed + Docker-free)
- **Pure (B6/B5):** `SKILL_CATEGORIES`/regex+bound validators; `compute_capability_match` (full/partial/none); `compute_agent_score` — **verbatim §8.3 weights**, full breakdown, `eval_performance=0` neutralized, **D-38-5 high-risk zeroes cost_latency**; `build_squad` — assignment, **reviewer≠builder (§2.2)**, **no-reviewer ⇒ availability 0 + missing_skills `reviewer:<skill>` + factory request (B5)**, `missing_skills`/`agent_factory_requests`, deterministic tie-break, all caps enforced.
- **DB (B3/B6/B7):** **`agent_provided_skills` FK rejects an unknown `skill_id` (B3, direct-SQL)** + cross-ref UNIQUE; **B8 — `uaid_app` cannot INSERT/UPDATE/DELETE/TRUNCATE the global tables (direct-SQL privilege test) while the admin role can seed/register**; `skills`/capabilities **no-UPDATE/DELETE/TRUNCATE (B7)**; bounded-JSON / enum / regex / count CHECK rejections (B6); `squad_manifests`+`skill_matches` RLS cross-tenant; manifest oversize rejected; `skill_matches→squad_manifests` composite FK cross-tenant; latest-wins capability_view; latest/history ordering.
- **No-A5/readiness (db):** `build_and_record` ⇒ `production_autonomy` `before==after` + readiness unchanged + ruleset unchanged.
- **Audit:** tenant build audited (counts only, no declared prose); global registration **not** audited (D-38-12).
- `make test` + fresh `make test-db` + alembic `0037` round-trip; CI green.

## 9. Sequencing (TDD)
1. Pure `skills.py` (categories/bounds/score/build_squad) + unit tests. 2. The 5 tables + migration `0037` (FK-normalized skills B3, enum/bound/regex CHECKs B6, immutable/append-only triggers B7, RLS, composite FKs) + DB-guard/RLS tests incl. **FK-unknown-skill + immutability + bounds**. 3. Admin-path module functions `register_skill`/`register_capability` (admin session, unaudited) + runtime `capability_view` SELECT read + tenant-audited `SquadRepository` + DB tests (incl. the B8 `uaid_app`-cannot-write-global privilege test). 4. No-A5/readiness `before==after` + audit-safety. 5. Full gates; CLAUDE.md entry.

## 10. Must NOT claim
- That a high score = a **qualified** agent (qualification = Slice 40; `eval_performance` is neutralized to 0 — a transparent ranking aid, not a competence verdict).
- That the engine **realizes/instantiates/authorizes** any agent (realization = Slice 39); that `agent_factory_requests` create agents (they are requests, §8.4).
- That declared `domain_fit`/`cost_latency_fit`/`risk_level` are **verified** (caller-supplied-unverified).
- That work-units are spine task contracts (§13.2 = Slice 42).
- That any **A5 gate / readiness / go-live** changed (foundational, bit-stable; go-live false).
- That a skill graph implies a graph DB — it is **Postgres relational** (D-38-0).

## 11. Resolved decisions (formerly open; now bound)
- **OD-1 → proceed now** (D-38-1…12; do not wait for Slice 40/42; `eval_performance` neutralized honestly).
- **OD-2 → admin-curated global capability map** (D-38-3; not derived from opaque `agent_versions` hashes).
- **OD-3 → no read endpoint this slice** (D-38-9).
- **OD-4 → no global platform audit; tenant `squad_manifests`/`skill_matches` audit only** (D-38-12).
- **Neo4j → none; Postgres/Alembic only** (D-38-0).

## 12. Definition of done (for the eventual implementation — NOT this PLAN)
A deterministic, **Postgres-only** Skill Matching Engine: a global FK-referenceable skill catalog + an admin-curated, append-only, **FK-normalized** agent→skill capability map; the **§8.3 transparent score** as a pure, fully-broken-down function (verbatim weights; high-risk reliability rule; `eval_performance` neutral-until-Slice-40, never fabricated); and per-build, tenant-scoped, append-only **`skill_matches`** (persisted breakdown) + a **§8.4 `squad_manifests`** snapshot over declared work-units (assignments + distinct reviewers ≠ builder + `missing_skills` + `agent_factory_requests`, with bound no-reviewer behavior). RLS + append-only + FK-proven skills + bounded fields + audit-safe (tenant only); `production_autonomy.py`/`readiness.py` untouched, **bit-stable**, go-live false; migration `0037` round-trips; `make test` + `make test-db` + CI green. **No Neo4j, no realization, no evals, no execution, no LLM, no A5 flip.**

---
**Review note (v3):** v3 fixes **B8** — global tables grant `uaid_app` **SELECT only** (admin-written via migration seed / admin session, cf. Slice-6 `0007:231-232`), closing the v2 hole where the runtime role could mutate unaudited global state; **all v2 fixes preserved unchurned**. v2 bound the **Neo4j ruling** (D-38-0, Postgres-only) and **B1–B7**: all decisions closed (OD-1…4 ruled; no MAY-endpoint), **`skill_matches` persists the §8.3 breakdown** (B2), **skills FK-normalized** so unknown keys can't persist (B3), **no global platform audit** (B4, tenant-only), **no-reviewer behavior bound** (B5), **exact bounds/regexes** (B6), **exact immutability** (B7). The honesty constraint stands: the score is **transparent but evidence-incomplete** (`eval_performance` neutral until Slice 40; work-units declared until Slice 42) — a ranking aid, not a qualification/authorization. Store/infra-only, bit-stable, go-live false; migration `0037` (5 additive tables; reuses `agent_blueprints`). No code/migration/tests/PR until an approved plan + your explicit go.
