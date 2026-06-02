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

    make test       # Docker-free: pure-logic + route tests only (DB tests deselected)
    make test-db    # DB-backed tests; requires `make up`. Creates+migrates `app_test`, runs `-m db`

`make test` never touches Postgres. DB-backed tests (migration apply, tenancy
invariants, real readiness round-trip) are marked `db` and run only under
`make test-db`, against a dedicated `app_test` database whose schema is built by
Alembic (`alembic upgrade head`) — never `create_all`. Helper targets:
`make test-db-create`, `make test-db-migrate`, `make test-db-drop`.

## Endpoints
- Liveness:  http://localhost:8000/health/live   (200 `{"status":"alive"}`, no dependency calls)
- Readiness: http://localhost:8000/health/ready  (real `SELECT 1`; 200 when DB up, 503 when down)
- Demo:      http://localhost:8000/demo

## Migrations
    ALEMBIC_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app \
      uv run alembic upgrade head    # apply to the dev `app` DB

The URL is resolved in `migrations/env.py` from `ALEMBIC_DATABASE_URL` (if set)
or `app.config.settings.database_url`. No `CREATE EXTENSION` is used — UUID PKs
rely on core `gen_random_uuid()` (Postgres 13+; we pin 16).
