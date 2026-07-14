"""Durable-runtime engine + deterministic demo graphs (Slice 8a/8b, §23.2).

UAID-checkpointed LangGraph runs that persist to UAID-owned RLS tables; the demo
nodes only mutate graph state and record ``run_steps`` rows — no un-mediated
network/provider I/O.

What this module provides:

- **Slice 8a — crash/resume substrate** (`start_demo_run`/`resume_demo_run`): a
  two-node graph that checkpoints between super-steps and resumes from a fresh
  process/session without re-executing completed steps.
- **Slice 8b — approval wait/resume** (`start_approval_run`/`resume_approval_run`):
  a sentinel ``approval_gate`` precedes the protected node so protected work never
  runs before approval. The engine requests a ``workflow.resume`` approval
  (tier ``high``, ``requires_explicit_approval=True``, subject
  ``run:<id>:node:<protected>``) and marks the run ``blocked``; on resume,
  ``APPROVED`` ⇒ run the protected node → complete, a terminal denial ⇒ the run
  fails, ``PENDING`` ⇒ stays blocked.
- **Slice 8b — node retry/backoff** (`run_retry_demo`/`run_failing_demo`): LangGraph
  ``RetryPolicy`` over a retryable ``TransientNodeError``; ``retried`` is recorded
  only for attempts > 1; non-retryable / exhausted ⇒ the run fails.
- **Slice 8b — cost STOP→pause** (`start_costguard_run`/`resume_costguard_run`):
  consults the Slice-7 cost ``evaluate`` stop signal at the step boundary (before the
  next node); STOP ⇒ ``running→paused`` without executing the node.

Still deferred: the §23.3 business control loop; real tool execution; broker↔runtime
wiring; distributed workers/queues; LangGraph native ``interrupt()``/``Command(resume=)``
(the approval-gate decision lives in the audited approval engine, not LangGraph state).
"""

import uuid
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.approvals.states import Status
from app.repositories.approvals import ApprovalRepository
from app.repositories.cost import evaluate as cost_evaluate
from app.repositories.emergency_controls import EmergencyControlRepository
from app.repositories.runs import RunRepository
from app.runtime.checkpointer import UAIDCheckpointer
from app.tenancy import TenantContext

DEMO_NODES = ("node_a", "node_b")

# --- Slice 8b: runtime integration constants ---------------------------------
WORKFLOW_RESUME_ACTION = "workflow.resume"  # not a §2.6 mandatory action
WORKFLOW_WAIT_RISK_TIER = "high"  # D-1: explicit waits "block until approval"
PROTECTED_NODE = "protected_node"
_RETRY_INTERVAL = 0.001  # keep retry backoff negligible in tests


class TransientNodeError(Exception):
    """A retryable, application-level node failure (must NOT abort the DB tx)."""


class PermanentNodeError(Exception):
    """A non-retryable node failure ⇒ the run fails."""


def workflow_subject(run_id: uuid.UUID, node: str) -> str:
    return f"run:{run_id}:node:{node}"


class DemoState(TypedDict):
    a: int
    b: int


def _config(run_id: uuid.UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(run_id), "checkpoint_ns": ""}}


async def _emergency_boundary(repo: RunRepository, project_id, run_id) -> None:
    """Post-commit step boundary: no future node begins while the latch is active."""
    await EmergencyControlRepository(repo.session, repo.context).enforce_boundary(
        project_id, run_id
    )


def _build_demo_graph(repo: RunRepository, project_id, run_id, checkpointer):
    async def _record(node: str) -> None:
        await _emergency_boundary(repo, project_id, run_id)
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
    await _emergency_boundary(repo, project_id, run_id)
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
    await _emergency_boundary(repo, project_id, run_id)
    await repo.record_step(run_id=run_id, project_id=project_id, event_type="run_resumed")
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_demo_graph(repo, project_id, run_id, checkpointer)
    config = _config(run_id)
    state = await graph.ainvoke(None, config)
    snapshot = await graph.aget_state(config)
    if not snapshot.next:  # graph reached END
        await repo.mark_completed(run_id=run_id, actor=actor)
    return state


# =============================================================================
# Slice 8b — approval wait/resume
# =============================================================================


class ApprovalState(TypedDict, total=False):
    protected: bool


def _build_approval_graph(repo: RunRepository, project_id, run_id, checkpointer):
    async def approval_gate(state: ApprovalState) -> dict:
        await _emergency_boundary(repo, project_id, run_id)
        # Sentinel: NO protected work, NO state mutation. Just a checkpoint boundary
        # before the protected node so nothing protected runs pre-approval.
        return {}

    async def protected_node(state: ApprovalState) -> dict:
        await _emergency_boundary(repo, project_id, run_id)
        await repo.record_step(
            run_id=run_id, project_id=project_id, event_type="step_completed", node=PROTECTED_NODE
        )
        return {"protected": True}

    g = StateGraph(ApprovalState)
    g.add_node("approval_gate", approval_gate)
    g.add_node(PROTECTED_NODE, protected_node)
    g.add_edge(START, "approval_gate")
    g.add_edge("approval_gate", PROTECTED_NODE)
    g.add_edge(PROTECTED_NODE, END)
    return g.compile(checkpointer=checkpointer, interrupt_after=["approval_gate"])


async def start_approval_run(
    session, context: TenantContext, *, project_id, run_id, actor: str = "runtime"
) -> str:
    """Run up to the sentinel gate, then request approval + block. Protected node does NOT run.

    Returns the run's resulting status.
    """
    repo = RunRepository(session, context)
    await _emergency_boundary(repo, project_id, run_id)
    await repo.mark_running(run_id=run_id, actor=actor)
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_approval_graph(repo, project_id, run_id, checkpointer)
    config = _config(run_id)
    await graph.ainvoke({}, config)
    snapshot = await graph.aget_state(config)
    if PROTECTED_NODE in (snapshot.next or ()):
        subject = workflow_subject(run_id, PROTECTED_NODE)
        approvals = ApprovalRepository(session, context)
        existing = await approvals.latest_for(
            project_id, WORKFLOW_RESUME_ACTION, subject_ref=subject
        )
        if existing is None:
            await approvals.request(
                project_id=project_id,
                action=WORKFLOW_RESUME_ACTION,
                risk_tier=WORKFLOW_WAIT_RISK_TIER,
                requested_by=actor,
                requires_explicit_approval=True,
                subject_ref=subject,
            )
        await repo.mark_blocked_on_approval(
            run_id=run_id, actor=actor, payload={"subject": subject}
        )
        return "blocked"
    # No protected work ahead (shouldn't happen for this graph) — complete.
    await repo.mark_completed(run_id=run_id, actor=actor)
    return "completed"


async def resume_approval_run(
    session, context: TenantContext, *, project_id, run_id, actor: str = "runtime"
) -> str:
    """Resume a blocked run: APPROVED ⇒ run protected node→complete; terminal denial ⇒ fail;
    PENDING ⇒ stay blocked. Returns the resulting status."""
    repo = RunRepository(session, context)
    await _emergency_boundary(repo, project_id, run_id)
    approvals = ApprovalRepository(session, context)
    subject = workflow_subject(run_id, PROTECTED_NODE)
    if await approvals.is_blocked(project_id, WORKFLOW_RESUME_ACTION, subject_ref=subject):
        approval = await approvals.latest_for(
            project_id, WORKFLOW_RESUME_ACTION, subject_ref=subject
        )
        status = approval.status if approval else None
        if status is None or status == Status.PENDING.value:
            return "blocked"  # still awaiting a decision — no transition
        # Terminal non-approved (rejected/cancelled/expired/proceeded_by_policy) ⇒ fail.
        await repo.mark_failed(
            run_id=run_id, actor=actor, payload={"reason": f"approval_{status}", "subject": subject}
        )
        return "failed"
    # APPROVED ⇒ resume past the gate and run the protected node.
    await repo.mark_resumed(run_id=run_id, actor=actor, payload={"subject": subject})
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_approval_graph(repo, project_id, run_id, checkpointer)
    config = _config(run_id)
    await graph.ainvoke(None, config)
    snapshot = await graph.aget_state(config)
    if not snapshot.next:
        await repo.mark_completed(run_id=run_id, actor=actor)
        return "completed"
    return "running"


# =============================================================================
# Slice 8b — node retry/backoff
# =============================================================================


class RetryState(TypedDict, total=False):
    value: int


def _build_retry_graph(repo, project_id, run_id, checkpointer, *, fail_times, max_attempts):
    attempts = {"n": 0}

    async def flaky(state: RetryState) -> dict:
        await _emergency_boundary(repo, project_id, run_id)
        attempts["n"] += 1
        n = attempts["n"]
        if n > 1:  # a retry is an attempt AFTER an earlier failure
            await repo.record_step(
                run_id=run_id,
                project_id=project_id,
                event_type="retried",
                node="flaky",
                payload={"attempt": n},
            )
        if n <= fail_times:
            raise TransientNodeError(f"transient failure on attempt {n}")
        await repo.record_step(
            run_id=run_id, project_id=project_id, event_type="step_completed", node="flaky"
        )
        return {"value": n}

    g = StateGraph(RetryState)
    g.add_node(
        "flaky",
        flaky,
        retry_policy=RetryPolicy(
            max_attempts=max_attempts,
            retry_on=TransientNodeError,
            initial_interval=_RETRY_INTERVAL,
            max_interval=_RETRY_INTERVAL,
            jitter=False,
        ),
    )
    g.add_edge(START, "flaky")
    g.add_edge("flaky", END)
    return g.compile(checkpointer=checkpointer)


def _build_failing_graph(repo, project_id, run_id, checkpointer):
    async def broken(state: RetryState) -> dict:
        await _emergency_boundary(repo, project_id, run_id)
        raise PermanentNodeError("non-retryable failure")

    g = StateGraph(RetryState)
    g.add_node(
        "broken", broken, retry_policy=RetryPolicy(max_attempts=3, retry_on=TransientNodeError)
    )
    g.add_edge(START, "broken")
    g.add_edge("broken", END)
    return g.compile(checkpointer=checkpointer)


async def run_retry_demo(
    session,
    context: TenantContext,
    *,
    project_id,
    run_id,
    fail_times: int,
    max_attempts: int,
    actor: str = "runtime",
) -> str:
    """Run a flaky node under RetryPolicy. Returns 'completed' or 'failed'."""
    repo = RunRepository(session, context)
    await _emergency_boundary(repo, project_id, run_id)
    await repo.mark_running(run_id=run_id, actor=actor)
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_retry_graph(
        repo, project_id, run_id, checkpointer, fail_times=fail_times, max_attempts=max_attempts
    )
    try:
        await graph.ainvoke({"value": 0}, _config(run_id))
    except Exception as exc:  # node failure surfaced by LangGraph
        reason = "retry_exhausted" if isinstance(exc, TransientNodeError) else "node_error"
        await repo.mark_failed(
            run_id=run_id, actor=actor, payload={"reason": reason, "error": type(exc).__name__}
        )
        return "failed"
    await repo.mark_completed(run_id=run_id, actor=actor)
    return "completed"


async def run_failing_demo(
    session, context: TenantContext, *, project_id, run_id, actor: str = "runtime"
) -> str:
    """Run a node that raises a non-retryable error ⇒ the run fails (not retried)."""
    repo = RunRepository(session, context)
    await _emergency_boundary(repo, project_id, run_id)
    await repo.mark_running(run_id=run_id, actor=actor)
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_failing_graph(repo, project_id, run_id, checkpointer)
    try:
        await graph.ainvoke({"value": 0}, _config(run_id))
    except Exception as exc:
        reason = "retry_exhausted" if isinstance(exc, TransientNodeError) else "node_error"
        await repo.mark_failed(
            run_id=run_id, actor=actor, payload={"reason": reason, "error": type(exc).__name__}
        )
        return "failed"
    await repo.mark_completed(run_id=run_id, actor=actor)
    return "completed"


# =============================================================================
# Slice 8b — cost pre-step STOP→pause hook (step/run boundary)
# =============================================================================


def _build_cost_graph(repo, project_id, run_id, checkpointer):
    async def work(state: RetryState) -> dict:
        await _emergency_boundary(repo, project_id, run_id)
        await repo.record_step(
            run_id=run_id, project_id=project_id, event_type="step_completed", node="work"
        )
        return {"value": 1}

    g = StateGraph(RetryState)
    g.add_node("work", work)
    g.add_edge(START, "work")
    g.add_edge("work", END)
    return g.compile(checkpointer=checkpointer)


async def start_costguard_run(
    session, context: TenantContext, *, project_id, run_id, actor: str = "runtime"
) -> str:
    """Cost-guarded run: evaluate the §19.7 stop signal BEFORE the next node.

    STOP ⇒ pause before the node executes (no work performed). Returns the status.
    """
    repo = RunRepository(session, context)
    await _emergency_boundary(repo, project_id, run_id)
    await repo.mark_running(run_id=run_id, actor=actor)
    decision = await cost_evaluate(session, context, project_id=project_id)
    if decision.stop:
        await repo.mark_paused_for_cost(
            run_id=run_id, actor=actor, payload={"reason": decision.reason.value}
        )
        return "paused"
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_cost_graph(repo, project_id, run_id, checkpointer)
    await graph.ainvoke({"value": 0}, _config(run_id))
    await repo.mark_completed(run_id=run_id, actor=actor)
    return "completed"


async def resume_costguard_run(
    session, context: TenantContext, *, project_id, run_id, actor: str = "runtime"
) -> str:
    """Resume a cost-paused run: re-evaluate; still STOP ⇒ stay paused; else resume→complete."""
    repo = RunRepository(session, context)
    await _emergency_boundary(repo, project_id, run_id)
    decision = await cost_evaluate(session, context, project_id=project_id)
    if decision.stop:
        return "paused"  # still over budget — no transition
    await repo.mark_resumed(run_id=run_id, actor=actor)
    checkpointer = UAIDCheckpointer(session, context, project_id=project_id, run_id=run_id)
    graph = _build_cost_graph(repo, project_id, run_id, checkpointer)
    await graph.ainvoke({"value": 0}, _config(run_id))
    await repo.mark_completed(run_id=run_id, actor=actor)
    return "completed"
