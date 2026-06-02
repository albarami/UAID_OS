.PHONY: dev up down logs test fmt
dev:
	uv run python -m uvicorn app.main:app --reload --port 8000
up:
	docker compose up -d
down:
	docker compose down
logs:
	docker compose logs -f
test:
	uv run pytest
fmt:
	uv run ruff format . && uv run ruff check --fix .
