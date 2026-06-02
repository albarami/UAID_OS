"""Liveness and readiness handlers.

Liveness reports only that the process is up. Readiness performs a real DB
round-trip via the injected ping (overridable in tests) and reports honest
per-component status, returning 503 when any required dependency is down.
"""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.db import ping

router = APIRouter(prefix="/health", tags=["health"])

DbPing = Callable[[], Awaitable[None]]


def get_db_ping() -> DbPing:
    """Dependency returning the DB ping callable (overridden in tests)."""
    return ping


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
async def ready(db_ping: DbPing = Depends(get_db_ping)):
    components: dict[str, str] = {}
    try:
        await db_ping()
        components["db"] = "ok"
    except Exception as exc:  # report honestly; do not mask a real outage
        components["db"] = "down"
        components["error"] = str(exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "components": components},
        )
    return {"status": "ready", "components": components}
