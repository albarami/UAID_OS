"""Minimal durable-runtime engine + deterministic demo graph (Slice 8a, §23.2).

Just enough to prove the substrate: a UAID-checkpointed LangGraph run that
checkpoints between super-steps and resumes from a fresh process/session without
re-executing completed steps. **No approval waits, retry/backoff, cost hook, or
business logic** (those are Slice 8b). The demo nodes only mutate graph state and
record a ``run_steps`` row — no un-mediated network/provider I/O.
"""

import uuid
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.repositories.runs import RunRepository
from app.runtime.checkpointer import UAIDCheckpointer
from app.tenancy import TenantContext

DEMO_NODES = ("node_a", "node_b")


class DemoState(TypedDict):
    a: int
    b: int


def _config(run_id: uuid.UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(run_id), "checkpoint_ns": ""}}


def _build_demo_graph(repo: RunRepository, project_id, run_id, checkpointer):
    async def _record(node: str) -> None:
        await repo.record_step(
            run_id=run_id, project_id=project_id, event_type="step_completed", node=node
        )

    async def node_a(state: DemoState) -> dict:
        await _record("node_a")
        return {"a": 1}

    async def node_b(state: DemoState) -> dict:
        await _record("node_b")
        return {"b": 2}

    g = StateGraph(DemoState)
    g.add_node("node_a", node_a)
    g.add_node("node_b", node_b)
    g.add_edge(START, "node_a")
    g.add_edge("node_a", "node_b")
    g.add_edge("node_b", END)
    # Static interrupt_after = a durability boundary (NOT the human-in-the-loop
    # interrupt() primitive, which is Slice 8b): forces a checkpoint after node_a.
    return g.compile(checkpointer=checkpointer, interrupt_after=["node_a"])


async def start_demo_run(
    session,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    actor: str = "runtime",
) -> dict:
    """Start a run: created→running, then execute until the post-node_a checkpoint."""
    repo = RunRepository(session, context)
    await repo.mark_running(run_id=run_id, actor=actor)
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_demo_graph(repo, project_id, run_id, checkpointer)
    return await graph.ainvoke({"a": 0, "b": 0}, _config(run_id))


async def resume_demo_run(
    session,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    actor: str = "runtime",
) -> dict:
    """Resume from the last checkpoint (fresh checkpointer/session) → continue to END."""
    repo = RunRepository(session, context)
    await repo.record_step(run_id=run_id, project_id=project_id, event_type="run_resumed")
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_demo_graph(repo, project_id, run_id, checkpointer)
    config = _config(run_id)
    state = await graph.ainvoke(None, config)
    snapshot = await graph.aget_state(config)
    if not snapshot.next:  # graph reached END
        await repo.mark_completed(run_id=run_id, actor=actor)
    return state
