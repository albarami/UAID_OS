from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.dashboard import router as dashboard_router
from app.config import settings  # noqa: F401  (imported so .env loads at startup)
from app.core.provenance import Fact, Source
from app.core.reasoning import muhasabah_gate
from app.db import dispose_engine
from app.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Engine is created lazily on first use; dispose cleanly on shutdown.
    yield
    await dispose_engine()


app = FastAPI(title="uaid-os", lifespan=lifespan)

app.include_router(health_router)
app.include_router(dashboard_router)


@app.get("/demo")
def demo() -> dict[str, object]:
    fact = Fact(
        claim="Doha is the capital of Qatar",
        sources=[Source(origin="worldfactbook", locator="Qatar")],
    )
    gate = muhasabah_gate("Doha is the capital of Qatar.", [fact])
    return {"isnad": fact.isnad, "gate_passed": gate.passed, "failures": gate.failures}
