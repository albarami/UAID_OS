# Phase 1 — Control-Plane Foundation · PLAN

**Status:** revised after plan review (REJECT for revision). Blocking fixes 1–4 applied; D1 + D5 decided. Awaiting re-review of THIS plan before any code.
**Spec basis:** §26.1 (Phase 1 scope), §17 (tenancy), §23.2/§23.4 (runtime + state model), §16.6 (audit), §5/§2.6 (autonomy), §18 (human-in-the-loop), §11 (tool broker), §19 (cost).

This plan is built one **vertical slice** at a time. Slices 2+ are summarized here; each gets a slice-level detail pass (like Slice 1 below) for review **before** its own implementation.

---

## Ways of working (guardrails, locked)
- One vertical slice at a time; **pause for review** between slices.
- Tests land **with** each slice; no feature work beyond the approved slice.
- No stubs presented as real; no fake "done"; prefer an honest blocker.
- No secrets printed; `.env` never committed; migrations are deterministic & reviewable (no `create_all` at app startup).

---

## Tenancy model (applies to every slice)
**Mechanism:** shared Postgres DB + `tenant_id` row scoping. **Hierarchy:** `organizations → tenants → projects → project_runs`. `tenant_id` is denormalized onto every tenant-owned row for direct scoping and RLS.

### Invariants
| ID | Invariant | Enforced by | How a test proves it |
|----|-----------|-------------|----------------------|
| INV-1 | Tenant-owned tables have `tenant_id NOT NULL` | schema | column is `nullable=False`; inserting NULL → `IntegrityError` |
| INV-2 | `tenant_id` FK → `tenants(id)` | schema FK (`ON DELETE RESTRICT`) | insert bogus `tenant_id` → `IntegrityError` |
| INV-3 | `project_runs.tenant_id` == its project's `tenant_id` | composite FK `(project_id, tenant_id) → projects(id, tenant_id)` | insert run with project from T_a but `tenant_id`=T_b → `IntegrityError` |
| INV-4 | No tenant-owned read/write without explicit tenant context | tenant-scoped repository requires a `TenantContext(tenant_id)`; all queries filtered by `tenant_id` | repo scoped to T_a returns nothing for T_b rows; a write under T_a targeting T_b is rejected |
| INV-5 | DB blocks cross-tenant rows even on raw SQL | Postgres **RLS** (Slice 1b): non-superuser app role + policies `USING (tenant_id = current_setting('app.current_tenant')::uuid)` | set T_a GUC; raw `SELECT` sees only T_a rows; no GUC → 0 rows (deny by default) |

**Note on `audit_logs` (Slice 2):** it is tenant-*aware*, not strictly tenant-owned — platform-level events carry `tenant_id NULL`. INV-1 applies to tenant-owned **business** tables; the audit table's exception is explicit and tested separately.

---

## Health / readiness semantics (applies from Slice 1)
- `GET /health/live` → `200 {"status":"alive"}`. Liveness only; **no** dependency calls.
- `GET /health/ready` → real checks. `200 {"status":"ready","components":{"db":"ok"}}` when all required deps are healthy; `503 {"status":"not_ready","components":{"db":"down","error":"..."}}` when any required dep is down. Performs a real `SELECT 1` round-trip.
- The scaffold's fake `GET /health → {"status":"ok"}` is **removed**. (`/demo` is left untouched — non-goal.)
- Slice 1 readiness checks `db` only; `redis`/`chroma` are added to readiness in their own slices.

---

## Slice 1 — Persistence spine + tenancy  *(detailed)*

**Scope:** Async SQLAlchemy 2 + Alembic against the running Postgres; the four core tables; tenant-scoped repository plumbing; honest liveness/readiness. Nothing else.

**Files likely touched**
- `pyproject.toml` — add `alembic`.
- `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_*.py` — async Alembic, `target_metadata = Base.metadata`.
- `app/db.py` — async engine + session factory from `settings.database_url`; `ping()` for readiness; lifespan create/dispose.
- `app/models/base.py` — `DeclarativeBase` + constraint **naming convention** (deterministic autogenerate).
- `app/models/{organization,tenant,project,project_run}.py`.
- `app/tenancy.py` — `TenantContext` + tenant-scoped repository base (requires tenant_id, filters all queries).
- `app/repositories/projects.py` — minimal tenant-scoped CRUD (used to prove INV-4).
- `app/main.py` — replace fake `/health` with `/health/live` + `/health/ready`; DB lifespan.
- `tests/conftest.py`, `tests/test_tenancy.py`, `tests/test_health.py` (updated).
- `Makefile` — add `test-db-create`, `test-db-migrate`, `test-db-drop`, `test-db` targets; document the `make test` (Docker-free) vs `make test-db` (DB-backed) split.
- `README.md` — update the `/health` reference to `/health/live` + `/health/ready`; document the two test commands.
- `CLAUDE.md` — update "What exists" (replace the `/health` endpoint description; note Alembic + async engine + spine tables + the test-DB split) so docs do not drift from the new reality.

**Schema changes — exact proposed tables**

**Extension / default assumptions (deterministic):** UUID PK defaults use `gen_random_uuid()`, which is in **PostgreSQL core since v13**. We are pinned to `postgres:16` (verified in `docker-compose.yml`), so the migration relies on the **core** function and does **not** create the `pgcrypto` extension. `pgcrypto` would only be required to target Postgres < 13, which we do not. `now()` for timestamps is likewise core. No `CREATE EXTENSION` runs in migration `0001`.

`organizations` *(root; not tenant-owned)*
- `id` UUID PK, default `gen_random_uuid()`
- `name` TEXT NOT NULL
- `slug` TEXT NOT NULL, **UNIQUE**
- `created_at` TIMESTAMPTZ NOT NULL default `now()`
- `updated_at` TIMESTAMPTZ NOT NULL default `now()`

`tenants` *(isolation boundary; its `id` IS the `tenant_id` used everywhere)*
- `id` UUID PK, default `gen_random_uuid()`
- `organization_id` UUID NOT NULL → `organizations(id)` ON DELETE RESTRICT
- `name` TEXT NOT NULL
- `slug` TEXT NOT NULL
- `status` TEXT NOT NULL default `'active'`, CHECK in (`active`,`suspended`)
- `created_at`, `updated_at` TIMESTAMPTZ NOT NULL default `now()`
- **UNIQUE(organization_id, slug)**; INDEX(organization_id)

`projects` *(tenant-owned)*
- `id` UUID PK, default `gen_random_uuid()`
- `tenant_id` UUID **NOT NULL** → `tenants(id)` ON DELETE RESTRICT
- `name` TEXT NOT NULL
- `slug` TEXT NOT NULL
- `created_at`, `updated_at` TIMESTAMPTZ NOT NULL default `now()`
- **UNIQUE(tenant_id, slug)**; **UNIQUE(id, tenant_id)** (enables the composite FK below); INDEX(tenant_id)

`project_runs` *(tenant-owned)*
- `id` UUID PK, default `gen_random_uuid()`
- `tenant_id` UUID **NOT NULL** → `tenants(id)` ON DELETE RESTRICT
- `project_id` UUID **NOT NULL**
- `status` TEXT NOT NULL default `'created'`, CHECK in (`created`,`running`,`paused`,`blocked`,`completed`,`failed`)
- `created_at`, `updated_at` TIMESTAMPTZ NOT NULL default `now()`
- **FK (project_id, tenant_id) → projects(id, tenant_id)** ON DELETE RESTRICT (enforces INV-3); INDEX(tenant_id); INDEX(project_id)

**Relationships:** `organizations 1—* tenants 1—* projects 1—* project_runs`.

**Tests**
- Migration: `alembic upgrade head` applies; `downgrade base` reverses cleanly; autogenerate shows **no drift**.
- Tenancy: INV-1..INV-4 each proven (see invariant table); a `projects` query scoped to T_a cannot see T_b's rows.
- Health (unit/route, no DB): `live` → 200; `ready` → 503 when the DB ping is forced to raise via FastAPI dependency override. This proves the *route* returns 503 on a failed ping — it is **not** proof that the system fails when the real DB is down (see integration evidence below).
- Health (integration, real DB): `ready` → 200 with Postgres up; `ready` → 503 with Postgres actually stopped.
- Tenancy + migration tests are DB-backed (see Test database & execution below).

**Test database & execution (D5 — approved)**
- **Database:** dedicated `app_test`, separate from the dev `app` DB. Same running Postgres container (`make up`); no second service.
- **Bootstrap (deterministic, via Make targets):**
  - `make test-db-create` — `CREATE DATABASE app_test` via an admin/maintenance connection (`psql` to the default `postgres` DB on the running container); idempotent (`IF NOT EXISTS`-style guard, no error if it already exists).
  - `make test-db-migrate` — `alembic upgrade head` against `app_test` (driven by a `TEST_DATABASE_URL` env override; never touches `app`).
  - `make test-db-drop` — `DROP DATABASE IF EXISTS app_test` for a clean reset.
  - `make test-db` — convenience target: ensure-create → migrate → run the DB-backed test suite. `conftest.py` also auto-creates `app_test` from the maintenance connection if absent, so a bare `make test-db` works in one step; the explicit targets exist for CI and manual reset.
- **Isolation:** per-test transaction rollback — a function-scoped fixture opens a connection, begins an outer transaction, binds the `AsyncSession` to it (with SAVEPOINT/nested-transaction restart so the code under test may itself commit), and **rolls back** after each test. No test mutates persistent state.
- **Schema source:** `app_test` schema is built **only** by `alembic upgrade head` — never `create_all`, keeping migrations the single source of truth.
- **What `make test` requires after Slice 1:** `make test` stays **Docker-free** — it runs the pure-logic + route tests (existing provenance/reasoning tests, `/health/live`, and the readiness-503 dependency-override route test). The DB-backed tests (migration apply/reverse, tenancy invariants, real readiness round-trip) run under the **separate** `make test-db`, which requires `make up`. The 3 existing tests therefore keep passing without Docker. This split is documented in `README.md`.

**Evidence to present at checkpoint**
- `alembic upgrade head` + `downgrade base` logs; empty autogenerate diff.
- `psql \d+` of all four tables showing NOT NULL, FKs, composite FK, uniques, checks.
- `pytest` summary (tenancy + health green, counts) for both `make test` and `make test-db`.
- **Readiness — unit/route evidence:** the dependency-override test showing the `/health/ready` route returns **503** when the ping dependency raises. Labeled explicitly as a *route-level* test, **not** proof the system fails on a real DB outage.
- **Readiness — integration evidence:** a live demo with the **real Postgres container stopped** (`make down` or stop the container), showing `/health/ready` returns **503**, then **200** after `make up`. This is the actual "fails when the DB is down" proof.

**Explicit non-goals (Slice 1)**
- No RLS yet (Slice 1b), no audit/policy/approval/agent/cost tables, no workflow logic.
- No request-level auth (who sets the tenant context from an HTTP request) — that is a separate decision/slice before Slice 10.
- No connection-pool tuning beyond sane defaults; no Redis/Chroma in readiness yet.

---

## Slices 2–10 — *(summary; each detailed before its build)*

### Slice 1b — Tenancy hardening: Postgres RLS  *(D1: must complete before Slices 3+)* — **IMPLEMENTED (pending review/merge)**
- **Scope:** ENABLE+FORCE RLS on `projects`/`project_runs`; dedicated non-superuser runtime role `uaid_app`; `app.current_tenant` GUC via `set_config(..., true)` per transaction; deny-by-default policy.
- **Files (actual):** `migrations/versions/0002_rls_tenant_isolation.py`, `scripts/bootstrap_rls_role.sql`, `app/tenancy.py` (`tenant_scope`), `app/config.py` (admin/runtime URLs), `migrations/env.py` (admin-only resolution), `tests/conftest.py` (admin + `uaid_app` fixtures), `tests/test_rls.py`, `Makefile`, `.env.example`, docs.
- **Schema:** no new tables; RLS + policies + grants to `uaid_app`. Role created by `make db-bootstrap-rls-role` (not Alembic).
- **Tests/evidence:** INV-5 (isolation, deny-by-default, cross-tenant write blocked, repo works when bound) + catalog (RLS enabled+forced, policies, role attrs, owner) — **`make test-db` → 16 passing**. At rev 0001 (no RLS/grants) `uaid_app` is denied — confirms RLS does the work.
- **Non-goals (held):** column-level security; request→tenant auth; RLS on `organizations`/`tenants`.

### Slice 2 — Append-only audit log (§16.6) — **IMPLEMENTED (plan v4; pending review/merge)** · branch `feat/control-plane-audit-log`
- **Scope (delivered):** `audit_logs` hash-chained (SHA-256, `prev_hash`→`entry_hash`), append-only; written ONLY via SECURITY DEFINER `audit_append` (GUC-derived tenant, fail-closed, minimal return) owned by limited NOLOGIN `audit_writer`; `uaid_app` EXECUTE-only. Shared `audit_entry_hash` helper (injective `jsonb_build_object`); admin-only full-chain `audit_verify`.
- **Files (actual):** `app/audit.py`, `app/models/audit_log.py`, `migrations/versions/0003_audit_log.py`, `tests/test_audit.py`, `scripts/bootstrap_rls_role.sql` (+`audit_writer`), `tests/conftest.py` (engine auto-dispose), docs. `app/db.py` unchanged.
- **Immutability:** REVOKE UPDATE/DELETE + BEFORE UPDATE/DELETE/TRUNCATE trigger. **Tamper-evident, not tamper-proof.**
- **Tests/evidence:** `make test` → 8; `make test-db` → 33 (append/verify, forgery-denied, fail-closed, append-only vs trigger, privilege-denied, tamper-detected, seq-gap tolerated, rollback semantics, minimal return, catalog/privilege). Autogenerate drift empty; downgrade/upgrade reversible.
- **Non-goals (held):** external sink, signing, platform/system events, tenant read API + audit-table RLS (Slice 10).

### Slice 3 — Policy engine: autonomy A0–A5 + authority matrix (§5, §2.6) — **IMPLEMENTED (plan v3; pending review/merge)** · branch `feat/control-plane-policy-engine`
- **Scope (delivered):** code authority matrix; pure deny-by-default `check_authority → ALLOW|DENY|NEEDS_APPROVAL`; **tighten-only** overrides; §2.6 actions (incl. `weaken_test_or_review_standards`) **non-bypassable**; tenant-owned RLS `autonomy_policies` (level + overrides); `decision_for` **fail-closed** (missing row ⇒ DENY; invalid persisted override ⇒ DENY); `upsert` validates + audits (safe metadata; untrusted `actor` label).
- **Files (actual):** `app/policy/{levels,matrix,engine}.py`, `app/models/autonomy_policy.py`, `app/repositories/autonomy_policies.py`, `migrations/versions/0004_autonomy_policies.py`, `tests/test_policy.py`, `app/models/__init__.py`, docs. `app/db.py` unchanged.
- **Grants:** `SELECT, INSERT, UPDATE` to `uaid_app` — **no DELETE**.
- **Tests/evidence:** `make test` → 32; `make test-db` → 44 (matrix semantics, unknown⇒DENY, A4 thresholds, tighten-only/relaxing-rejected + malformed-min_level-rejected, §2.6 non-ALLOW, missing-row⇒DENY, invalid-override⇒DENY incl. unrelated-action + malformed persisted, whole-map fail-closed, RLS isolation + deny-by-default + cross-tenant write blocked, audit-on-upsert, catalog incl. no-DELETE). Autogenerate drift empty; reversible.
- **Non-goals (held):** enforcement wiring (Slice 5); approval workflow (Slice 4); A5 auto-release gates; stop_conditions; per-run override; API/UI.

### Slice 4 — Approval engine (§18) — **IMPLEMENTED (plan v3; pending review/merge)** · branch `feat/control-plane-approval-engine`
- **Scope (delivered):** request→await→resolve lifecycle; five-state machine (pending→approved/rejected/cancelled/expired/proceeded_by_policy); risk-tiered **non-response policy** (§18.5, on-demand, no scheduler); **non-bypassable `requires_explicit_approval`** (forced True for §2.6 actions via `app.policy.matrix.is_mandatory_action` — canonical, no drift); **fail-closed gate** `is_blocked` (no approval ⇒ blocked; explicit ⇒ only APPROVED unblocks); each transition writes `approval_events` + `audit_log`; `approver_provenance='caller_supplied_unverified'` (untrusted labels).
- **Files (actual):** `app/approvals/{__init__,states}.py`, `app/models/approval.py`, `app/models/approval_event.py`, `app/repositories/approvals.py`, `migrations/versions/0005_approvals.py`, `tests/test_approvals.py`, `app/policy/matrix.py` (+`is_mandatory_action`, additive), `app/policy/__init__.py` (export), `app/models/__init__.py`, docs. `app/db.py` unchanged.
- **Grants:** `approvals` SELECT/INSERT/UPDATE (no DELETE); `approval_events` SELECT/INSERT (append-only). Both RLS ENABLE+FORCE + `tenant_isolation`.
- **Tests/evidence:** `make test` → 54; `make test-db` → 58 (transition matrix, non-response per tier, gate truth table, §2.6-low-still-blocked, tri-state explicit, mandatory-false-rejected, expiry low→proceed/medium→expired/high→no-lapse, double-resolve raises, RLS deny-by-default, catalog incl. no-DELETE + append-only). Autogenerate drift empty; reversible.
- **Non-goals (held):** Slice 5 enforcement; real channels; scheduler; API/UI (§18.6); request-auth identity; A5 gates; §18.3/§18.4 machinery.

### Slice 5 — Tool broker skeleton (§11) — **IMPLEMENTED (plan v3; pending review/merge)** · branch `feat/control-plane-tool-broker`
- **Scope (delivered):** deny-by-default decision chokepoint `broker_call → BrokerDecision`; code `TOOL_REGISTRY`; per-agent allowlist (append-only grant/revoke ledger, monotonic `seq`); composes Slice 3 authority + Slice 4 approval (**tool-scoped** `subject_ref="tool:<name>"`); deterministic `sanitize_params` (mapping-only, secret redaction, ≤16 KiB, `DENIED_INVALID_PARAMS`); records every attempt to tenant-owned append-only `tool_calls` + audit (never params). **Provenance gates:** unverified approval ⇒ `NEEDS_AUTHENTICATED_APPROVAL`; success terminal `ALLOWED_UNVERIFIED_IDENTITY` (no bare ALLOWED; not executable).
- **Files (actual):** `app/tools/{__init__,registry,broker}.py`, `app/models/tool_call.py`, `app/models/agent_tool_allowlist.py`, `app/repositories/tools.py`, `migrations/versions/0006_tool_broker.py`, `tests/test_tools.py`, `app/repositories/approvals.py` (+additive `latest_for`), `app/models/__init__.py`, docs. `app/db.py`/`app/policy/*`/`app/approvals/states.py` untouched.
- **Grants:** `tool_calls` + `agent_tool_allowlist` both `SELECT, INSERT` only (append-only); both ENABLE+FORCE RLS + `tenant_isolation`.
- **Tests/evidence:** `make test` → 61; `make test-db` → 69 (unknown/invalid-params/not-allowlisted/policy-deny denials, allow⇒unverified-identity, contract-requires-approval over policy ALLOW, tool-scoped approval [action-level/other-tool don't satisfy], unverified-approved⇒needs-authenticated, allowlist grant/revoke/regrant, RLS deny-by-default both tables, catalog append-only). Autogenerate drift empty; reversible.
- **Non-goals (held):** real connectors/MCP/credentials/rate-limits/cost/auto-suspension/API-UI; no real execution; agent identity unverified (Slice 6 / request-auth).

### Slice 6 — Agent registry (§9.7, §17.4, §22.2) — **IMPLEMENTED (plan v2; pending review/merge)** · branch `feat/control-plane-agent-registry`
- **Scope (delivered):** GLOBAL admin-curated `agent_blueprints` + GLOBAL **immutable** `agent_versions`
  (full §22.2 snapshot: `model_route` + six `sha256:` component hashes incl. `critical_dependencies_hash`/
  `output_schema_hash` + derived `content_hash`; idempotent on content); TENANT-OWNED RLS `agent_instances`
  (binds a version into a project/run via `version_id` only). `register_blueprint`/`register_version`
  (admin path; archetype + hash-shape validation, deny-by-default); `AgentInstanceRepository`
  (instantiate/bind_to_run/suspend/retire, each audited).
- **Files (actual):** `app/models/{agent_blueprint,agent_version,agent_instance}.py`, `app/agents/{__init__,registry}.py`,
  `migrations/versions/0007_agent_registry.py`, `tests/test_agents.py`, `app/models/__init__.py`,
  `app/models/project_run.py` (+`UNIQUE(id, project_id, tenant_id)` for the triple FK), docs. `app/db.py`/`app/policy/*`/`app/approvals/*`/`app/tools/*` untouched.
- **Immutability:** `agent_versions` UPDATE/DELETE/TRUNCATE triggers + REVOKE (DML-immutable, not tamper-proof
  vs. a DB superuser); `agent_instances` binding columns immutable + `active_run_id` set-once via trigger.
- **Integrity:** triple FK `(active_run_id, project_id, tenant_id) → project_runs(id, project_id, tenant_id)`
  (pins run→project→tenant); composite FK `(project_id, tenant_id)→projects`; partial unique on live
  `(tenant, project, instance_key)`.
- **Grants:** `agent_blueprints`/`agent_versions` → `uaid_app` **SELECT only** (admin-curated);
  `agent_instances` SELECT/INSERT/UPDATE (no DELETE) + ENABLE+FORCE RLS + `tenant_isolation`.
- **Tests/evidence:** `make test` → 68; `make test-db` → 88 (content-hash determinism/sensitivity,
  archetype+sha256 validation, version UPDATE/DELETE/TRUNCATE-immutable [admin], idempotency + new-version,
  global readability, instance RLS deny-by-default + cross-tenant WITH CHECK, run/project/tenant FK pinning,
  binding-column immutability [raw uaid_app] + set-once run, live-key uniqueness + retired-frees-key,
  lifecycle audit trail, tenant-content column-set boundary, catalog/grants/triggers). Drift empty; reversible.
- **Non-goals (held):** Agent Factory / eval execution (Phase 4); model routing; broker↔instance wiring
  (future enforcement slice); §9.6 replacement automation; §22.3 upgrade/requalification workflow; request-auth; API/UI.

### Slice 7 — Cost ledger (§19) — **IMPLEMENTED (plan v3; pending review/merge)** · branch `feat/control-plane-cost-ledger`
- **Scope (delivered):** tenant-owned **immutable** `cost_events` (§19.2 components; source of truth) +
  per-project `budgets` (total + optional daily ceilings) + on-demand SUM aggregation + a **pure
  stop-condition decision** (`evaluate_stop`/`evaluate`, §19.7 `budget_exceeded`). Decided: D-A missing
  budget ⇒ STOP `no_budget` (fail-closed); D-B threshold `>=`; D-C `cost_events` DB-immutable.
- **Files (actual):** `app/cost.py` (pure: components, `to_decimal` money guard, `evaluate_stop`,
  exceptions), `app/repositories/cost.py` (`CostEventRepository` [idempotent `record`, `total_spent`,
  `daily_spent`], `BudgetRepository` [`get`/`upsert`], `evaluate`), `app/models/cost_event.py`,
  `app/models/budget.py`, `migrations/versions/0008_cost_ledger.py`, `tests/test_cost.py`,
  `app/models/__init__.py`, docs. `app/db.py`/`app/policy/*`/`app/approvals/*`/`app/tools/*`/`app/agents/*` untouched.
- **Integrity:** `NUMERIC(18,6)` + Decimal; CHECK amount/quantity ≥ 0; composite FK `(project_id, tenant_id)`;
  triple FK `(run_id, project_id, tenant_id)`; **immutability** UPDATE/DELETE/TRUNCATE triggers + REVOKE;
  **source-namespaced idempotency** (`INSERT … ON CONFLICT DO NOTHING` + re-select; `IdempotencyConflict`
  on material key reuse); daily aggregation by **UTC half-open bounds**; over-budget costs still recorded.
- **Grants:** `cost_events` SELECT/INSERT only (append-only); `budgets` SELECT/INSERT/UPDATE (no DELETE);
  both ENABLE+FORCE RLS + `tenant_isolation`.
- **Tests/evidence:** `make test` → 72; `make test-db` → 103 (money/stop truth-table, accumulation,
  idempotency-retry/conflict/namespacing, UTC boundaries, quantity DB check, over-budget recording,
  budget upsert + before/after audit, evaluate outcomes, immutability [uaid_app + admin], RLS deny-by-default
  + cross-tenant WITH CHECK + cross-tenant budget UPDATE blocked, FK pinning, catalog/grants/triggers).
  Drift empty; reversible `0008 → 0007 → head`.
- **Non-goals (held):** price-card integration; provider calls; model routing; billing UI; workflow runtime
  (stop signal decision-only); forecast-based approvals; per-phase budgets; refunds/credits; multi-currency;
  request-auth (`actor` untrusted); broker/agent wiring; non-cost `stop_if` conditions (Slice 8+).

### Slice 8 — Durable workflow runtime (§23.2)  ← major engine decision
- **Scope:** resumable run state machine on `project_runs`; step persistence; retries/backoff; human-approval waits; deterministic replay.
- **Files:** `app/runtime/` (engine, steps, checkpoints), `migrations/`, tests.
- **Schema:** `run_steps`, `workflow_checkpoints` (or engine-native checkpoint tables).
- **Tests:** kill mid-run → resume from last checkpoint; retry on transient failure; pause-for-approval then resume.
- **Evidence:** resume-after-crash demo; replay determinism.
- **Non-goals:** the full §23.3 business control loop; multi-worker scaling tuning.

### Slice 9 — Document intake sandbox (§16.3)
- **Scope:** `documents` ingested as untrusted data; injection scanning; quarantine; instruction/data labeling.
- **Files:** `app/intake/sandbox.py`, `app/models/document.py`, tests.
- **Schema:** `documents` (tenant-owned) with classification/quarantine fields.
- **Tests:** injected "ignore the reviewer" content is quarantined, never executed.
- **Evidence:** quarantine on a malicious sample; labels applied.
- **Non-goals:** full Documentation Compiler (Phase 2); ML classification.

### Slice 10 — Minimal read API / dashboard (§18.6)
- **Scope:** read-only, tenant-scoped endpoints: run state, open approvals, blockers, cost.
- **Files:** `app/api/` routers, tests.
- **Schema:** none (reads existing).
- **Tests:** tenant-scoped reads; cannot read another tenant.
- **Evidence:** endpoint output; isolation on reads.
- **Non-goals:** web UI (unless decided); request auth → tenant mapping (separate slice/decision).

---

## Decisions

### Decided
- **D1 — RLS placement → DECIDED: Slice 1b** (not folded into Slice 1). RLS lands in its own slice immediately after Slice 1, and **Slice 1b must complete before any higher-level tenant-owned component (Slices 3+)** so no tenant-owned table is ever built without DB-level enforcement scheduled ahead of it. Slice 1 ships with app-layer scoping (INV-4) + the schema-level FKs (INV-1..3); INV-5 (RLS) is proven in 1b.
- **D5 — Test DB → DECIDED: dedicated `app_test` + per-test transaction rollback**, with the bootstrap/Make/fixture details now specified under Slice 1 → "Test database & execution". `make test` stays Docker-free; `make test-db` runs the DB-backed suite.

### Still open (do not block Slice 1)
- **D2 — Workflow engine (Slice 8):** langgraph + Postgres checkpointing **or** Temporal. Decide before Slice 8.
- **D3 — Dashboard (Slice 10):** API-only **or** minimal web UI.
- **D4 — Request auth → tenant resolution:** when/how an HTTP caller is mapped to a tenant (needed before Slice 10 is externally usable). Propose a dedicated slice.

---

## Slice 1 — follow-up hardening backlog (from code review; deferred, not lost)
Surfaced by the Slice 1 code review and explicitly deferred (not folded into the
Slice 1 commit). None is reachable as a bug within current Slice 1 scope.
1. `app/tenancy.py` — `TenantContext` should coerce/validate `tenant_id` to `uuid.UUID`
   so a string-built context cannot make reads and writes disagree. Do **with the
   request→tenant auth slice** (D4), where string ids first appear.
2. `app/health.py` — `/health/ready` 503 body returns raw `str(exc)`; log full error
   server-side and return a generic `db: down` to avoid leaking connection detail.
3. `tests/conftest.py` — `_schema` sets `ALEMBIC_DATABASE_URL` without restoring it;
   save/restore (or `monkeypatch`) to avoid a process-wide env leak.
4. `app/models/base.py` — `updated_at` is ORM-side `onupdate` only; add a DB-side
   trigger/default when raw/bulk update paths land (**Slice 8** run state machine).
5. `app/models/{project,tenant}.py` — drop the standalone single-column indexes that
   are redundant with the leading column of their composite `UNIQUE` (migration change).
6. `app/repositories/projects.py` — first-party-before-third-party import order; tidy
   if/when ruff `I` (isort) is enabled.

## Immediate next action
Slices 1, 1b, 2, 3, 4, 5, 6 merged (PRs #1–#7). **Slice 7 (cost ledger, §19) implemented on
branch `feat/control-plane-cost-ledger`, pending implementation review/commit.**
Next slice after Slice 7 merges: Slice 8 (durable workflow runtime, §23.2 — major engine
decision D2: langgraph + Postgres checkpointing vs. Temporal) — do not start until greenlit.
