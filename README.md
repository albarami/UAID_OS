# UAID OS

Salim-standard AI service scaffold.

## Stack
- FastAPI ............ app/main.py
- Postgres + Redis + ChromaDB ... docker-compose.yml
- Async SQLAlchemy 2 + Alembic ... app/db.py, app/models/, migrations/
- Sanad provenance / No-Free-Facts ... app/core/provenance.py
- Muhasabah self-audit gate ... app/core/reasoning.py
- Deterministic compute (NumPy/SciPy) ... app/compute/
- Python 3.11 via uv

## Run
    make up      # start Postgres / Redis / Chroma (Docker)
    make dev     # run API on http://localhost:8000
    make fmt     # format + lint

## Tests
Two commands by design:

    make test                          # Docker-free: pure-logic + route tests only
    RLS_DB_PASSWORD=... make test-db   # DB-backed tests; requires `make up`

`make test` never touches Postgres. DB-backed tests (migration apply, tenancy
invariants INV-1..4, real readiness round-trip, **and RLS INV-5 + catalog
enforcement**) are marked `db` and run only under `make test-db`. That target
bootstraps the non-superuser `uaid_app` role (needs `RLS_DB_PASSWORD`), then
creates+migrates the dedicated `app_test` database **as admin** (schema built by
Alembic — never `create_all`), then runs `-m db` with the runtime `uaid_app`
connection. Helper targets: `make test-db-create`, `make test-db-migrate`,
`make test-db-drop`, `make db-bootstrap-rls-role`.

## Endpoints
- Liveness:  http://localhost:8000/health/live   (200 `{"status":"alive"}`, no dependency calls)
- Readiness: http://localhost:8000/health/ready  (real `SELECT 1`; 200 when DB up, 503 when down)
- Demo:      http://localhost:8000/demo

## Security model — tenant isolation (two layers)
Tenant-owned tables (`projects`, `project_runs`) are protected at two layers:
- **App layer:** `TenantContext` + `TenantScopedRepository` require an explicit
  tenant and filter every query (INV-1..4).
- **DB layer (RLS):** Postgres Row-Level Security, `ENABLE`d + `FORCE`d, with a
  deny-by-default `tenant_isolation` policy keyed on the `app.current_tenant` GUC.
  Use `app.tenancy.tenant_scope(context)` so the GUC is set on the same
  transaction as the queries (INV-5).

Two DB roles:
- **`uaid_app`** — non-superuser (`NOSUPERUSER NOBYPASSRLS`), the **runtime**
  connection; RLS applies to it. Created by `make db-bootstrap-rls-role` from
  `RLS_DB_PASSWORD` (never committed).
- **`app`** — owner/superuser; used **only** for migrations, role bootstrap, and
  test seeding (superusers bypass RLS, so the runtime must not use it).

## Migrations (admin only)
    ALEMBIC_DATABASE_URL=$ADMIN_DATABASE_URL uv run alembic upgrade head   # or: make migrate

The URL is resolved in `migrations/env.py` from `ALEMBIC_DATABASE_URL` (if set)
or `app.config.settings.admin_database_url` — **admin credentials only; migrations
never run as `uaid_app`** (which lacks DDL rights). No `CREATE EXTENSION` is used —
UUID PKs rely on core `gen_random_uuid()` (Postgres 13+; we pin 16).
