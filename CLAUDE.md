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

## Current status (2026-06-02)
**Phase 1 (§26.1) in progress — Slice 1 (persistence spine + tenancy) landed.**
Beyond the original scaffold, the control-plane persistence spine now exists:
async SQLAlchemy + Alembic, the four core tenant-scoped tables, app-layer tenant
scoping, and honest liveness/readiness. The rest of the engine described in the
spec (intake compiler, agent factory, maker-checker-verifier, evidence packs,
tool broker, policy/approval engines, etc.) is **not** implemented. Do not assume
any spec capability exists unless it is listed under "What exists" below.

Slice plan and status live in `.planning/PHASE-1-PLAN.md`. RLS is **not** yet
applied — it is the next slice (1b) and the only DB-level tenancy enforcement;
until then, tenant isolation is enforced at the app layer (repository) + schema
FKs, proven by tests.

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
- `app/db.py` — lazy async engine + session factory from `settings.database_url`;
  `ping()` (real round-trip for readiness), `get_session()` dependency, `dispose_engine()`.
- `app/models/` — `Base` (deterministic constraint naming) + the four spine tables:
  `organizations` (root), `tenants` (isolation boundary), `projects`, `project_runs`
  (both tenant-owned: `tenant_id NOT NULL` FK→`tenants`; runs pinned to their project's
  tenant by composite FK `(project_id, tenant_id)→projects(id, tenant_id)`).
- `app/tenancy.py` — `TenantContext` + `TenantScopedRepository`: tenant-owned data
  cannot be read/written without an explicit context; cross-tenant writes raise
  `CrossTenantError` (app-layer INV-4; DB-level RLS is Slice 1b).
- `app/repositories/projects.py` — tenant-scoped CRUD for `projects`.
- `migrations/` — Alembic (async `env.py`; URL from `ALEMBIC_DATABASE_URL` or settings);
  `versions/0001_control_plane_spine.py` is the spine migration. No `CREATE EXTENSION`.
- `app/config.py` — `Settings` (pydantic-settings) loaded from `.env`. Currently reads
  `DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `CHROMA_URL`, `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`. Other keys present in `.env` (OpenRouter, Manus, Semantic Scholar,
  Perplexity) are **ignored** until added as fields here.
- `app/core/provenance.py` — **Sanad / No-Free-Facts** primitive: a `Fact` must carry
  ≥1 `Source` or it raises `NoFreeFactsError`; `.isnad` renders the source chain.
  Minimal starting primitive — maps to spec §3.4, *not* the full provenance store.
- `app/core/reasoning.py` — **Muhasabah gate** primitive: `muhasabah_gate(answer, facts,
  extra_checks)` self-audits an output before it is returned. Minimal — maps to spec
  §3.2 (Al-Muhasibi wrapper), *not* the full reasoning kernel.
- `app/agents/` — empty package, reserved for agent implementations.
- `app/compute/` — reserved for deterministic NumPy/SciPy calculation cores.
- `tests/` — `test_provenance.py`, `test_health.py` (Docker-free) + `test_tenancy.py`
  (DB-backed, marked `db`) and `conftest.py` (auto-creates/migrates `app_test`,
  per-test transaction rollback). **`make test` → 6 passing (Docker-free);
  `make test-db` → 8 passing (DB-backed, incl. a real `/health/ready` round-trip).**

### Infra / tooling files
- `docker-compose.yml` — postgres:16, redis:7, chromadb. Pinned to compose project
  `name: uaid_os`. **Verified working** via `make up` (confirmed with `docker inspect`):
  - postgres `:5432` — **healthy** via Compose healthcheck (`pg_isready`).
  - redis `:6379` — **healthy** via Compose healthcheck (`redis-cli ping`).
  - chroma `:8001` — **running** (no Compose healthcheck; the image has no
    curl/wget/python to script one). Connectivity verified externally: `HTTP 200`
    on `/api/v2/heartbeat`.
  `make down` stops them; data persists in volumes `uaid_os_{pgdata,redisdata,chromadata}`.
- `Makefile` (`test`, `test-db`, `test-db-create/migrate/drop`, `up/down/dev/fmt`),
  `alembic.ini`, `.gitignore`, `.env.example`, `.python-version`.

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
make test    # Docker-free tests (no services needed) — 6 passing
make test-db # DB-backed tests (needs `make up`) — 8 passing; creates+migrates app_test
make fmt     # ruff format + lint
make up      # start Postgres/Redis/Chroma (needs Docker)
make dev     # run API at http://localhost:8000  (/health/live, /health/ready, /demo)
```
`make test` runs `pytest -m "not db"` (Docker-free); `make test-db` runs `-m db`
against `app_test`. Either can also be run directly with `uv run pytest`.

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
- Multi-tenant isolation (§17): **partially present** — app-layer scoping + schema FKs
  landed in Slice 1; **DB-level RLS is not yet applied** (Slice 1b, next).
- Everything else in the Phase 1–7 roadmap (§26) beyond Slice 1.

## Secrets
`.env` holds **live API keys** and is **gitignored** (verified not tracked). It was
restored from a pre-scaffold backup after scaffolding. Never commit it. Consider
rotating any key that has been exposed in a non-private context.
