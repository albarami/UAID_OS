from fastapi import FastAPI

from app.config import settings  # noqa: F401  (imported so .env loads at startup)
from app.core.provenance import Fact, Source
from app.core.reasoning import muhasabah_gate

app = FastAPI(title="app")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/demo")
def demo() -> dict[str, object]:
    fact = Fact(
        claim="Doha is the capital of Qatar",
        sources=[Source(origin="worldfactbook", locator="Qatar")],
    )
    gate = muhasabah_gate("Doha is the capital of Qatar.", [fact])
    return {"isnad": fact.isnad, "gate_passed": gate.passed, "failures": gate.failures}
