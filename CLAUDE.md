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
**Phase 1 (§26.1) in progress — Slice 1 (spine + tenancy), Slice 1b (Postgres RLS),
and Slice 2 (append-only audit log) landed** (Slice 2 on branch `feat/control-plane-audit-log`,
pending review/merge at time of writing). Beyond the original scaffold: the
control-plane persistence spine (async SQLAlchemy + Alembic, four tenant-scoped
tables, app-layer scoping, honest liveness/readiness), DB-level tenant isolation
via Postgres RLS (Slice 1b), **and a tamper-evident, hash-chained audit log
(Slice 2)**. The rest of the engine described in the spec (intake compiler, agent
factory, maker-checker-verifier, evidence packs, tool broker, policy/approval
engines, etc.) is **not** implemented. Do not assume any spec capability exists
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
- `migrations/` — Alembic (async `env.py`; URL = `ALEMBIC_DATABASE_URL` → `admin_database_url`,
  **admin only — never `uaid_app`**). `0001` (spine); `0002` (ENABLE+FORCE RLS on
  `projects`/`project_runs`, deny-by-default `tenant_isolation` policy, grants to `uaid_app`);
  `0003_audit_log.py` (append-only hash-chained `audit_logs`: SECURITY DEFINER `audit_append`
  [GUC-derived tenant, minimal return] + `audit_verify` owned by `audit_writer`, shared
  `audit_entry_hash` helper, REVOKE UPDATE/DELETE + append-only trigger; core `sha256`, no extension).
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
- `app/agents/` — empty package, reserved for agent implementations.
- `app/compute/` — reserved for deterministic NumPy/SciPy calculation cores.
- `tests/` — `test_provenance.py`, `test_health.py` (Docker-free) + `test_tenancy.py`,
  `test_rls.py`, `test_audit.py` (DB-backed, marked `db`) and `conftest.py` (admin fixtures
  build/seed `app_test`; `rls_engine` connects as `uaid_app`; per-test transaction rollback;
  auto-dispose of the `app.db` engine between tests). **`make test` → 8 passing (Docker-free);
  `make test-db` → 33 passing (DB-backed: tenancy INV-1..4, readiness, RLS INV-5, and audit
  append/verify/tamper/forgery/append-only + catalog). `make test-db` requires `RLS_DB_PASSWORD`.**

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
make test                                  # Docker-free tests (no services) — 8 passing
RLS_DB_PASSWORD=... make test-db           # DB-backed tests (needs `make up`) — 33 passing
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
- Everything else in the Phase 1–7 roadmap (§26) beyond Slices 1 / 1b / 2.

## Secrets
`.env` holds **live API keys** and is **gitignored** (verified not tracked). It was
restored from a pre-scaffold backup after scaffolding. Never commit it. Consider
rotating any key that has been exposed in a non-private context.
