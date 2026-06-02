.PHONY: dev up down logs test test-db test-db-create test-db-migrate test-db-drop fmt

TEST_DATABASE_URL ?= postgresql+asyncpg://app:app@localhost:5432/app_test

dev:
	uv run python -m uvicorn app.main:app --reload --port 8000
up:
	docker compose up -d
down:
	docker compose down
logs:
	docker compose logs -f

# Docker-free: pure-logic + route tests only (DB-backed tests are deselected).
test:
	uv run pytest -m "not db"

# DB-backed tests: ensure app_test exists, migrate it, then run only `db` tests.
# Requires `make up`.
test-db: test-db-create test-db-migrate
	DATABASE_URL=$(TEST_DATABASE_URL) TEST_DATABASE_URL=$(TEST_DATABASE_URL) ALEMBIC_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -m db

# Creates the canonical `app_test` DB. If TEST_DATABASE_URL is overridden to a
# different DB name, conftest.py auto-creates it on first use as a fallback.
test-db-create:
	docker exec uaid_os-postgres-1 psql -U app -d postgres -tc \
	  "SELECT 1 FROM pg_database WHERE datname='app_test'" | grep -q 1 || \
	  docker exec uaid_os-postgres-1 psql -U app -d postgres -c "CREATE DATABASE app_test"

test-db-migrate:
	ALEMBIC_DATABASE_URL=$(TEST_DATABASE_URL) uv run alembic upgrade head

test-db-drop:
	docker exec uaid_os-postgres-1 psql -U app -d postgres -c "DROP DATABASE IF EXISTS app_test"

fmt:
	uv run ruff format . && uv run ruff check --fix .
