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

### Slice 2 — Append-only audit log (§16.6)
- **Scope:** `audit_logs`, hash-chained (`prev_hash`→`entry_hash`), append-only; a writer API other slices call.
- **Files:** `app/models/audit_log.py`, `app/audit.py`, `migrations/`, `tests/test_audit.py`.
- **Schema:** `audit_logs(id, tenant_id NULL-allowed, actor, action, target, payload jsonb, prev_hash, entry_hash, created_at)`; UPDATE/DELETE revoked for the app role (or trigger).
- **Tests:** chain verifies; tamper detected; UPDATE/DELETE rejected.
- **Evidence:** chain-verify output; mutation rejected.
- **Non-goals:** external log sink, cryptographic signing (later).

### Slice 3 — Policy engine: autonomy A0–A5 + authority matrix (§5, §2.6)
- **Scope:** autonomy level per project/run; `check_authority(action, ctx) → allow | deny | needs_approval`; deny-by-default.
- **Files:** `app/policy/` (engine + matrix), `app/models/autonomy_policy.py`, `tests/test_policy.py`.
- **Schema:** `autonomy_policies` (tenant-owned).
- **Tests:** A2 allows branch/PR, denies prod deploy; unknown action denied.
- **Evidence:** decision matrix in test output.
- **Non-goals:** wiring into real tools (Slice 5); UI.

### Slice 4 — Approval engine (§18)
- **Scope:** `approvals` + `approval_events`; request→await→resolve; non-response policy (logic only).
- **Files:** `app/models/approval.py`, `app/approvals.py`, tests.
- **Schema:** `approvals`, `approval_events` (tenant-owned).
- **Tests:** pending blocks dependent action; approve/reject transitions; high-risk blocks until approval.
- **Evidence:** state transitions; gate blocks until approved.
- **Non-goals:** real channels (Slack/email); timeout scheduler.

### Slice 5 — Tool broker skeleton (§11)
- **Scope:** controlled call interface; per-agent allowlist; deny-by-default; every call recorded; authority via Slice 3.
- **Files:** `app/tools/broker.py`, `app/models/tool_call.py`, tests.
- **Schema:** `tool_calls` (tenant-owned); minimal `connectors` registry.
- **Tests:** disallowed tool denied + audited; allowed tool recorded; unknown tool denied.
- **Evidence:** audit entries per call; denial logged.
- **Non-goals:** real connectors (GitHub/CI), MCP servers.

### Slice 6 — Agent registry (§9.7, §17.4)
- **Scope:** global `agent_blueprints`; immutable `agent_versions` (hashes); tenant-scoped `agent_instances`.
- **Files:** `app/models/agent.py`, `app/agents/registry.py`, tests.
- **Schema:** `agent_blueprints` (global), `agent_versions` (immutable), `agent_instances` (tenant-owned).
- **Tests:** used version cannot be mutated; instances tenant-scoped.
- **Evidence:** immutability + scoping proven.
- **Non-goals:** Agent Factory / eval library (Phase 4); model routing.

### Slice 7 — Cost ledger (§19)
- **Scope:** `cost_events`; running totals; budget ceilings; stop-condition check.
- **Files:** `app/models/cost_event.py`, `app/cost.py`, tests.
- **Schema:** `cost_events`, `budgets` (tenant-owned).
- **Tests:** accumulation; ceiling breach → stop signal; daily cap.
- **Evidence:** breach triggers stop condition.
- **Non-goals:** provider price-card integration; model routing.

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
Slice 1 merged (PR #1). **Slice 1b (Postgres RLS) implemented on branch
`feat/control-plane-rls-1b`, pending review/commit.** Per D1, 1b must land before
Slices 3+. Next slice after 1b merges: Slice 2 (append-only audit log) — do not
start until greenlit.
