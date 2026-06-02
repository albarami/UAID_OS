.PHONY: dev up down logs test test-db test-db-create test-db-migrate test-db-drop \
        db-bootstrap-rls-role migrate require-rls-pw fmt

# --- connection model -------------------------------------------------------
# Runtime  = non-superuser, RLS-enforced role `uaid_app` (password from env).
# Admin    = owner/superuser `app`, used ONLY for migrations / bootstrap / seed.
PGHOST ?= localhost
PGPORT ?= 5432
RLS_USER ?= uaid_app
RLS_DB_PASSWORD ?=
export RLS_DB_PASSWORD

ADMIN_DATABASE_URL      ?= postgresql+asyncpg://app:app@$(PGHOST):$(PGPORT)/app
TEST_ADMIN_DATABASE_URL ?= postgresql+asyncpg://app:app@$(PGHOST):$(PGPORT)/app_test
DATABASE_URL            ?= postgresql+asyncpg://$(RLS_USER):$(RLS_DB_PASSWORD)@$(PGHOST):$(PGPORT)/app
TEST_DATABASE_URL       ?= postgresql+asyncpg://$(RLS_USER):$(RLS_DB_PASSWORD)@$(PGHOST):$(PGPORT)/app_test

dev:
	uv run python -m uvicorn app.main:app --reload --port 8000
up:
	docker compose up -d
down:
	docker compose down
logs:
	docker compose logs -f

# Fail closed if the RLS role password is not provided (never commit/print it).
require-rls-pw:
	@test -n "$(RLS_DB_PASSWORD)" || { \
	  echo "ERROR: RLS_DB_PASSWORD is not set. Export it (do not commit it), e.g.:"; \
	  echo "  export RLS_DB_PASSWORD=...  # then re-run"; \
	  exit 1; }

# Docker-free: pure-logic + route tests only (DB-backed tests are deselected).
test:
	uv run pytest -m "not db"

# DB-backed tests. Schema/migrate run with ADMIN creds; RLS tests connect as the
# runtime `uaid_app` role. Requires `make up` and RLS_DB_PASSWORD.
test-db: require-rls-pw test-db-create db-bootstrap-rls-role test-db-migrate
	@DATABASE_URL="$(TEST_DATABASE_URL)" \
	 TEST_DATABASE_URL="$(TEST_DATABASE_URL)" \
	 TEST_ADMIN_DATABASE_URL="$(TEST_ADMIN_DATABASE_URL)" \
	 ADMIN_DATABASE_URL="$(ADMIN_DATABASE_URL)" \
	 uv run pytest -m db

test-db-create:
	docker exec uaid_os-postgres-1 psql -U app -d postgres -tc \
	  "SELECT 1 FROM pg_database WHERE datname='app_test'" | grep -q 1 || \
	  docker exec uaid_os-postgres-1 psql -U app -d postgres -c "CREATE DATABASE app_test"

# Create/rotate the non-superuser runtime role. ADMIN-run; password via env
# pass-through to psql \getenv (never appears in argv or make output).
db-bootstrap-rls-role: require-rls-pw
	@docker exec -e RLS_DB_PASSWORD -i uaid_os-postgres-1 \
	  psql -U app -d postgres -v ON_ERROR_STOP=1 < scripts/bootstrap_rls_role.sql

# Migrations ALWAYS use ADMIN creds (never `uaid_app`).
test-db-migrate:
	ALEMBIC_DATABASE_URL="$(TEST_ADMIN_DATABASE_URL)" uv run alembic upgrade head

migrate:
	ALEMBIC_DATABASE_URL="$(ADMIN_DATABASE_URL)" uv run alembic upgrade head

test-db-drop:
	docker exec uaid_os-postgres-1 psql -U app -d postgres -c "DROP DATABASE IF EXISTS app_test"

fmt:
	uv run ruff format . && uv run ruff check --fix .
