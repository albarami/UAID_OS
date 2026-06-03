# CLAUDE.md — UAID OS

Read this first in any session. Re-read after a context reset or compaction.

## What this project is
**UAID OS** (Universal Autonomous Integration & Delivery OS) is a domain-agnostic
**autonomous delivery control plane**: you hand it a documentation package for any
build, and it judges build-readiness (R0–R5), compiles missing specs where safe,
dynamically staffs specialist AI agents, then builds → reviews → tests → deploys
under a graded autonomy policy (A0–A5). "Done" is proven by an **evidence pack**,
never an agent's claim.

The authoritative design is `docs/UAID_OS_Standalone_System_Spec_and_Intake_Standard_v1_2.md`
(~3,000 lines). Build to that spec. Section references below (§) point into it.

## Current status (2026-06-03)
**Phase 1 (§26.1) in progress — Slices 1, 1b, 2, 3, 4, 5, 6 merged; Slice 7 (cost
ledger) on branch `feat/control-plane-cost-ledger`, pending review/merge.**
Beyond the original scaffold: the persistence spine (async SQLAlchemy + Alembic, four
tenant-scoped tables, app-layer scoping, honest liveness/readiness), DB-level tenant
isolation via Postgres RLS (Slice 1b), a tamper-evident hash-chained audit log
(Slice 2), a deterministic autonomy policy engine (Slice 3), an approval engine
(Slice 4), a tool broker skeleton (deny-by-default decision chokepoint composing
policy + approval, Slice 5), an agent registry (global blueprints + immutable
content-hashed versions + tenant-scoped instances, Slice 6), **and a cost ledger
(immutable `cost_events` + per-project `budgets` + a deterministic stop-condition
decision, Slice 7)**. The rest of the engine described in the spec (intake compiler,
agent factory, maker-checker-verifier, evidence packs, etc.) is **not** implemented.
Do not assume any spec capability exists
unless it is listed under "What exists" below.

Slice plan/status live in `.planning/PHASE-1-PLAN.md`. **Tenant isolation now holds
at two layers simultaneously:** app-layer (repository scoping + schema FKs, INV-1..4)
and DB-level RLS (INV-5). RLS is enforced because the runtime connects as a dedicated
**non-superuser role `uaid_app`** (superusers/owners bypass RLS); migrations run as
the admin `app` role only.

## What exists

### Stack (installed, Python 3.11 via uv — see `pyproject.toml` / `uv.lock`)
- **FastAPI + uvicorn** — web/API surface (`app/main.py`)
- **SQLAlchemy 2 + asyncpg + Alembic** (Postgres + migrations), **redis**, **chromadb** (vector store)
- **langgraph** (agent orchestration), **anthropic** + **openai** SDKs (LLM calls)
- **numpy + scipy** (deterministic compute) — `app/compute/`
- **pytest + pytest-asyncio + ruff** (dev)

### Code skeleton
- `app/main.py` — FastAPI app; `/health/live` + `/health/ready` (real `SELECT 1`,
  503 when DB down) and a `/demo` endpoint that exercises the kernel below. The old
  fake `/health` was removed. DB engine disposed on shutdown via lifespan.
- `app/health.py` — liveness/readiness handlers; readiness's DB ping is injected
  via a FastAPI dependency (`get_db_ping`) so it is overridable in route tests.
- `app/db.py` — lazy async engine + session factory from `settings.database_url`
  (the **runtime `uaid_app`** role); `ping()` (real round-trip for readiness),
  `get_session()` dependency, `dispose_engine()`.
- `app/models/` — `Base` (deterministic constraint naming) + the four spine tables:
  `organizations` (root), `tenants` (isolation boundary), `projects`, `project_runs`
  (both tenant-owned: `tenant_id NOT NULL` FK→`tenants`; runs pinned to their project's
  tenant by composite FK `(project_id, tenant_id)→projects(id, tenant_id)`).
- `app/tenancy.py` — `TenantContext` + `TenantScopedRepository` (app-layer INV-4) **and
  `tenant_scope(context)`**: an async context manager that opens a transaction and sets
  the `app.current_tenant` GUC (`set_config(..., true)`) on the **same** connection that
  runs the queries — the runtime binding RLS reads (INV-5). Cross-tenant writes raise
  `CrossTenantError` (app layer) and are blocked by RLS `WITH CHECK` (DB layer).
- `app/repositories/projects.py` — tenant-scoped CRUD for `projects` (use inside `tenant_scope`).
- `app/audit.py` — audit-log service (Slice 2, §16.6). `record(session, *, action, actor,
  target, payload)` appends via the DB `audit_append` function (tenant derived from the
  `app.current_tenant` GUC — **no tenant param**; call inside `tenant_scope`); returns only
  `{id, entry_hash, created_at}`. `verify_chain(admin_session)` runs the full-chain check
  (admin only). No engine/admin creds in the module.
- `app/models/audit_log.py` — **read-only** ORM model for `audit_logs` (writes go via the
  DB function, never the ORM).
- `app/policy/` — autonomy policy engine (Slice 3, §5/§2.6). `levels.py`
  (`AutonomyLevel` A0–A5), `matrix.py` (code authority matrix + **tighten-only**
  `apply_overrides`/`validate_overrides`; §2.6 actions flagged `mandatory_approval`
  and structurally non-bypassable), `engine.py` (pure deny-by-default
  `check_authority(action, level, overrides) -> Decision{ALLOW,DENY,NEEDS_APPROVAL}`).
- `app/models/autonomy_policy.py` — tenant-owned `autonomy_policies` (per-project
  level + overrides jsonb; composite FK to projects). `app/repositories/autonomy_policies.py`
  — `decision_for` (**fail-closed**: missing policy ⇒ DENY, invalid persisted override ⇒ DENY)
  and `upsert` (validates overrides, audits the change via `audit_append` with safe metadata;
  `actor` is an **untrusted** caller label until request-auth exists).
- `app/approvals/states.py` — pure approval state machine (Slice 4, §18): `Status`
  (pending/approved/rejected/cancelled/expired/proceeded_by_policy), `RiskTier`, transition
  validation, non-response policy (`compute_deadline`/`auto_transition`, §18.5 24h), and the
  fail-closed `is_blocked` gate. The **non-bypassable** rule: `requires_explicit_approval`
  (forced True for §2.6 actions via `app.policy.matrix.is_mandatory_action`) ⇒ only `APPROVED`
  unblocks; low-risk non-response can never bypass it. `PROCEEDED_BY_POLICY` unblocks only
  non-explicit low-risk after deadline; `EXPIRED` (medium) stays blocking; high/production never lapse.
- `app/models/approval.py` + `app/models/approval_event.py` — tenant-owned `approvals`
  (RLS; SELECT/INSERT/UPDATE, **no DELETE**) and append-only `approval_events`
  (RLS; SELECT/INSERT only). `app/repositories/approvals.py` — `ApprovalRepository`:
  request/approve/reject/cancel/expire_if_overdue + `is_blocked` gate + `latest_for(project,
  action, subject_ref=None)`; each transition writes an `approval_events` row + an `audit_log`
  entry. `requested_by`/`resolved_by` **untrusted**; `approver_provenance='caller_supplied_unverified'`
  — NOT verified human approvals. No scheduler (on-demand expiry).
- `app/tools/` — tool broker skeleton (Slice 5, §11). `registry.py` (code `TOOL_REGISTRY`
  catalog; deny-by-default unknown tools; `sanitize_params` — mapping-only, secret-key redaction,
  ≤16 KiB), `broker.py` (`broker_call` decision pipeline → `BrokerDecision`). Composes Slice 3
  authority + Slice 4 approval, **tool-scoped** (`subject_ref="tool:<name>"`). Two provenance
  gates keep it a safe **skeleton (no real execution)**: an unverified approval ⇒
  `NEEDS_AUTHENTICATED_APPROVAL`; the success terminal is `ALLOWED_UNVERIFIED_IDENTITY` (never
  bare ALLOWED). `app/models/tool_call.py` (tenant-owned, append-only, redacted params) +
  `app/models/agent_tool_allowlist.py` (append-only **grant/revoke ledger** with a monotonic
  `seq`; latest event decides). `app/repositories/tools.py` — `ToolAllowlistRepository`
  (grant/revoke/is_allowed, audited) + `ToolCallRepository.record` (records every attempt +
  audit; audit never includes params). `agent_id` is an **untrusted** label (the Slice-6
  agent registry is **not** wired to the broker yet).
- `app/agents/` — agent registry (Slice 6, §9.7/§17.4/§22.2). `registry.py`: `ARCHETYPES`
  (§9.5.1 set), `compute_content_hash` (deterministic `sha256:` over the §22.2 snapshot),
  admin-path `register_blueprint`/`register_version` (validate the six component hashes;
  idempotent on `content_hash`; changed content ⇒ new version), and `AgentInstanceRepository`
  (tenant-scoped instantiate/bind_to_run/suspend/retire, each audited). `app/models/agent_blueprint.py`
  (**global**, admin-curated role identity) + `app/models/agent_version.py` (**global**, **immutable**:
  UPDATE/DELETE/TRUNCATE triggers; stores hashes only — no tenant content) + `app/models/agent_instance.py`
  (**tenant-owned**, RLS; `version_id` only; triple FK pins run→project→tenant; binding columns
  immutable + `active_run_id` set-once via trigger; partial unique on live `(tenant,project,instance_key)`).
  `actor` is an **untrusted** label. **Skeleton: no Agent Factory / eval execution / model routing /
  agent execution / broker wiring.**
- `app/cost.py` + `app/repositories/cost.py` — cost ledger (Slice 7, §19). `app/cost.py` (pure):
  `COST_COMPONENTS` (§19.2), `to_decimal` money guard (rejects float/bool/negative/non-finite/>6dp),
  `evaluate_stop` (deny-by-default: missing budget ⇒ STOP `no_budget`; threshold `>=`), exceptions
  (`InvalidAmount`/`InvalidComponent`/`IdempotencyConflict`). `app/repositories/cost.py`:
  `CostEventRepository.record` (validates + **always records incurred cost, even over budget**;
  **source-namespaced idempotency** via `INSERT … ON CONFLICT DO NOTHING` + re-select — identical
  retry returns the row, material mismatch raises `IdempotencyConflict`; audited on insert only),
  `total_spent`/`daily_spent` (on-demand SUM; daily uses **UTC half-open bounds**), `BudgetRepository`
  (`get`/`upsert` audited with **before/after caps**), module-level `evaluate` (§19.7 stop decision,
  **returned not halting**). `app/models/cost_event.py` (**tenant-owned, IMMUTABLE**:
  UPDATE/DELETE/TRUNCATE triggers; `NUMERIC(18,6)`; CHECK amount/quantity ≥ 0 + DB-enforced
  `component` in the §19.2 set; triple FK pins run→project→tenant; partial unique idempotency
  index) + `app/models/budget.py` (tenant-owned;
  one per project). `actor` is an **untrusted** label. **Budget changes are audited but NOT verified
  human approvals.** **Skeleton: no price cards / provider calls / model routing / billing UI /
  workflow runtime (stop signal is decision-only) / broker-agent wiring.**
- `migrations/` — Alembic (async `env.py`; URL = `ALEMBIC_DATABASE_URL` → `admin_database_url`,
  **admin only — never `uaid_app`**). `0001` (spine); `0002` (ENABLE+FORCE RLS on
  `projects`/`project_runs`, deny-by-default `tenant_isolation` policy, grants to `uaid_app`);
  `0003_audit_log.py` (append-only hash-chained `audit_logs`: SECURITY DEFINER `audit_append`
  [GUC-derived tenant, minimal return] + `audit_verify` owned by `audit_writer`, shared
  `audit_entry_hash` helper, REVOKE UPDATE/DELETE + append-only trigger; core `sha256`, no extension);
  `0004_autonomy_policies.py` (tenant-owned `autonomy_policies`: ENABLE+FORCE RLS +
  `tenant_isolation` policy; grants `SELECT, INSERT, UPDATE` to `uaid_app` — **no DELETE**);
  `0005_approvals.py` (tenant-owned `approvals` [SELECT/INSERT/UPDATE, no DELETE] + append-only
  `approval_events` [SELECT/INSERT only]; both ENABLE+FORCE RLS + `tenant_isolation`);
  `0006_tool_broker.py` (tenant-owned append-only `tool_calls` + `agent_tool_allowlist` ledger
  [both SELECT/INSERT only]; both ENABLE+FORCE RLS + `tenant_isolation`);
  `0007_agent_registry.py` (**global** `agent_blueprints` + **immutable** `agent_versions`
  [`uaid_app` SELECT-only; UPDATE/DELETE/TRUNCATE triggers] + **tenant-owned** `agent_instances`
  [ENABLE+FORCE RLS + `tenant_isolation`; SELECT/INSERT/UPDATE, no DELETE; binding-immutability
  trigger]; adds `UNIQUE(id, project_id, tenant_id)` to `project_runs` for the triple FK);
  `0008_cost_ledger.py` (**tenant-owned, IMMUTABLE** `cost_events` [UPDATE/DELETE/TRUNCATE triggers +
  REVOKE; `uaid_app` SELECT/INSERT only; partial unique idempotency index] + tenant-owned `budgets`
  [SELECT/INSERT/UPDATE, no DELETE]; both ENABLE+FORCE RLS + `tenant_isolation`).
- `scripts/bootstrap_rls_role.sql` — idempotent roles: `uaid_app` (LOGIN, password from
  `RLS_DB_PASSWORD` via psql `\getenv`, never committed) **and `audit_writer`** (NOLOGIN, no
  password — the limited SECURITY DEFINER owner of the audit functions). Run by `make db-bootstrap-rls-role`.
- `app/config.py` — `Settings` (pydantic-settings) loaded from `.env`. Reads
  `DATABASE_URL` + `TEST_DATABASE_URL` (**runtime `uaid_app`**), `ADMIN_DATABASE_URL` +
  `TEST_ADMIN_DATABASE_URL` (**admin `app`**, migrations/bootstrap/seed only),
  `REDIS_URL`, `CHROMA_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`. `RLS_DB_PASSWORD` is
  consumed by the Makefile (not a Settings field). Other `.env` keys (OpenRouter, Manus,
  Semantic Scholar, Perplexity) are **ignored** until added here.
- `app/core/provenance.py` — **Sanad / No-Free-Facts** primitive: a `Fact` must carry
  ≥1 `Source` or it raises `NoFreeFactsError`; `.isnad` renders the source chain.
  Minimal starting primitive — maps to spec §3.4, *not* the full provenance store.
- `app/core/reasoning.py` — **Muhasabah gate** primitive: `muhasabah_gate(answer, facts,
  extra_checks)` self-audits an output before it is returned. Minimal — maps to spec
  §3.2 (Al-Muhasibi wrapper), *not* the full reasoning kernel.
- `app/compute/` — reserved for deterministic NumPy/SciPy calculation cores.
- `tests/` — `test_provenance.py`, `test_health.py` (Docker-free) + `test_tenancy.py`,
  `test_rls.py`, `test_audit.py`, `test_policy.py`, `test_approvals.py`, `test_tools.py`,
  `test_agents.py`, `test_cost.py` (DB-backed `db` + Docker-free units) and `conftest.py` (admin
  fixtures build/seed `app_test`; `rls_engine` as `uaid_app`; per-test transaction rollback; auto-dispose
  of the `app.db` engine).
  **`make test` → 72 passing (Docker-free, incl. pure policy/approval/broker logic + agent-registry
  content-hash/validation + cost money/stop-decision); `make test-db` → 103 passing (DB-backed: tenancy,
  readiness, RLS, audit, policy, approval, tool-broker, agent-registry, and cost-ledger
  accumulation/idempotency-conflict/UTC-bounds/immutability/RLS/FK-pinning/budget-audit/
  catalog). `make test-db` requires `RLS_DB_PASSWORD`.**

### Infra / tooling files
- `docker-compose.yml` — postgres:16, redis:7, chromadb. Pinned to compose project
  `name: uaid_os`. **Verified working** via `make up` (confirmed with `docker inspect`):
  - postgres `:5432` — **healthy** via Compose healthcheck (`pg_isready`).
  - redis `:6379` — **healthy** via Compose healthcheck (`redis-cli ping`).
  - chroma `:8001` — **running** (no Compose healthcheck; the image has no
    curl/wget/python to script one). Connectivity verified externally: `HTTP 200`
    on `/api/v2/heartbeat`.
  `make down` stops them; data persists in volumes `uaid_os_{pgdata,redisdata,chromadata}`.
- `Makefile` (`test`, `test-db`, `test-db-create/migrate/drop`, `db-bootstrap-rls-role`,
  `migrate`, `require-rls-pw`, `up/down/dev/fmt`), `alembic.ini`, `.gitignore`,
  `.env.example`, `.python-version`. `make test-db` fails closed if `RLS_DB_PASSWORD` is unset.
  The DB admin `psql` is parameterized via `PSQL` (default: `docker exec … uaid_os-postgres-1`;
  CI overrides with `PSQL=psql` to use a service container over TCP).
- `.github/workflows/ci.yml` — GitHub Actions CI on PRs + pushes to `main`: `uv sync`,
  `ruff check`, `make test` (Docker-free), and `make test-db` against a `postgres:16`
  **service** (CI-only non-secret creds; `RLS_DB_PASSWORD=uaid_app`). No real `.env`/secrets.

### Source-of-truth docs (preserved in `docs/`)
- The standalone spec (above).
- `docs/UAID_OS_Intake_Template_Pack_v1_2/` — the 26 canonical intake files.
  - `00`–`25` are **blank templates** (forms a customer fills per build); `19`–`22`
    carry the spec's default policy values.
  - `schemas/` (7 files) are **real, reusable schema/policy definitions**
    (agent realization, archetype eval methodology, reviewer QA, risk acceptance,
    model change, stabilization window, and `evidence_pack_schema.json`). Treat
    `schemas/` as canonical when implementing validation — they are product assets,
    not throwaway templates.

## How to run
```
make test                                  # Docker-free tests (no services) — 72 passing
RLS_DB_PASSWORD=... make test-db           # DB-backed tests (needs `make up`) — 103 passing
make fmt                                   # ruff format + lint
make up                                    # start Postgres/Redis/Chroma (needs Docker)
make dev                                   # run API at http://localhost:8000
```
`make test` runs `pytest -m "not db"` (Docker-free). `make test-db` bootstraps the
`uaid_app` role (needs `RLS_DB_PASSWORD`), creates+migrates `app_test` **as admin**,
then runs `-m db` with the runtime `uaid_app` connection. Migrations never run as
`uaid_app`. Endpoints: `/health/live`, `/health/ready`, `/demo`.

## Conventions to uphold (from the spec — non-negotiable, including in our own code)
- **No fake done.** No placeholders/stubs/hardcoded outputs presented as real. Prefer
  an honest blocker over fake completion. (§2.1)
- **Evidence decides done.** Narratives aren't proof; tests/diffs/logs/reviews are. (§2.3, §15)
- **No agent approves its own work** — independent review for consequential outputs. (§2.2)
- **Fail closed on unsupported facts** — every factual/decision claim needs provenance
  (use the Sanad primitive). (§2.4)
- **Autonomy needs boundaries** — production deploys, secret changes, deletions, etc.
  require approval. (§2.6)

## Not yet present (future build items — not blockers for the skeleton)
- Durable workflow runtime with resume + deterministic replay (§23.2) — can start on
  langgraph + Postgres checkpointing; consider Temporal later.
- Knowledge-graph store (added when KG features are built).
- Multi-tenant isolation (§17): **present for the spine** — app-layer scoping + schema FKs
  (Slice 1) **and DB-level RLS** on `projects`/`project_runs` (Slice 1b). Future tenant-owned
  tables must add the same RLS policy + grants when introduced.
- Audit log (§16.6): **present (Slice 2)** — append-only, hash-chained, tenant-event-only.
  Deferred: external log sink, cryptographic signing, platform/system events, reviewer/tenant
  read APIs + audit-table RLS (Slice 10). Tamper-evident, not tamper-proof.
- Policy engine (§5/§2.6): **present (Slice 3)** — A0–A5 + authority matrix, deny-by-default,
  tighten-only overrides, §2.6 mandatory-approval non-bypassable, fail-closed. **Enforced by the
  Slice 5 broker for brokered tool decisions only; no broader runtime/workflow enforcement exists
  yet.** A5 auto-release gates + stop_conditions deferred.
- Approval engine (§18): **present (Slice 4)** — request→await→resolve, risk tiers + non-response
  policy, fail-closed gate, non-bypassable `requires_explicit_approval` for §2.6 actions.
  **Wired into the Slice 5 broker for tool-scoped approval decisions only; no scheduler (on-demand
  expiry), no real channels (Slack/email), no dashboard (§18.6 / Slice 10), no request-auth — approver
  identity is unverified.** Note: the policy `is_mandatory_action` helper was added to `app/policy/matrix.py`.
- Tool broker (§11): **present (Slice 5)** — deny-by-default decision chokepoint composing
  policy + approval, per-agent allowlist ledger, every attempt recorded. **Skeleton: no real
  execution / connectors / MCP / credentials / rate limits / cost / auto-suspension.** Success
  caps at `ALLOWED_UNVERIFIED_IDENTITY`; unverified approvals ⇒ `NEEDS_AUTHENTICATED_APPROVAL`
  (nothing here is executable authorization until request-auth lands).
- Agent registry (§9.7/§17.4/§22.2): **present (Slice 6)** — global admin-curated `agent_blueprints`,
  global **immutable** `agent_versions` (full §22.2 hash snapshot; UPDATE/DELETE/TRUNCATE blocked by
  trigger — *DML-immutable, not tamper-proof vs. a DB superuser*), tenant-scoped RLS `agent_instances`
  (triple FK pins run→project→tenant; binding columns immutable; `active_run_id` set-once; one live
  binding per role handle). **Skeleton: no Agent Factory / qualification-eval execution / model routing /
  agent execution; the broker `agent_id` is NOT wired to instances yet; global registration is not
  audited (tenant-GUC-derived audit; platform-event audit deferred); component hashes are opaque
  caller-supplied inputs (the Factory that generates the artifacts is Phase 4).**
- Cost ledger (§19): **present (Slice 7)** — tenant-owned **immutable** `cost_events`
  (UPDATE/DELETE/TRUNCATE triggers — *DML-immutable, not tamper-proof vs. a DB superuser*;
  `NUMERIC(18,6)`; source-namespaced idempotency with `IdempotencyConflict` on key reuse) +
  per-project `budgets` (audited before/after caps). `evaluate` is **deny-by-default** (missing
  budget ⇒ STOP `no_budget`; threshold `>=`); daily aggregation uses **UTC half-open bounds**.
  Incurred costs are **always recorded, even over budget**. **Budget changes are audited but NOT
  verified human approvals** (approval workflow for increases deferred). **Skeleton: no price cards /
  provider calls / model routing / billing UI / workflow runtime (the stop signal is decision-only,
  not halting) / broker-agent wiring / forecasting / per-phase budgets.**
- Everything else in the Phase 1–7 roadmap (§26) beyond Slices 1 / 1b / 2 / 3 / 4 / 5 / 6 / 7.

## Secrets
`.env` holds **live API keys** and is **gitignored** (verified not tracked). It was
restored from a pre-scaffold backup after scaffolding. Never commit it. Consider
rotating any key that has been exposed in a non-private context.
