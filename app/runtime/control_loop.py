"""Slice-55 bounded control-loop orchestration primitives.

The module stops at a ``decided_not_executed`` decision boundary.  Its capability
runner deliberately exposes only the six coordinator-ruled, already-merged
functions; it contains no production or staging deployment action.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.cost import evaluate as cost_evaluate
from app.repositories.emergency_controls import EmergencyControlRepository
from app.repositories.evidence_packs import EvidencePackRepository
from app.repositories.go_live_decisions import (
    GoLiveDecisionRepository,
    GoLiveDecisionRepositoryError,
)
from app.repositories.production_autonomy import ProductionAutonomyRepository
from app.repositories.production_preapprovals import ProductionPreapprovalRepository
from app.repositories.runs import RunRepository
from app.release.production_autonomy import GateResult, ProductionAutonomyReport
from app.runtime.checkpointer import UAIDCheckpointer
from app.tenancy import TenantContext

CONTROL_LOOP_NODES = (
    "read_project_state",
    "inspect_existing_work_evidence",
    "observe_existing_review_and_verification_evidence",
    "assemble_or_reaudit_evidence_pack",
    "check_cost_and_authority_limits",
    "observe_staging_evidence",
    "evaluate_a5_gate",
    "finalize_go_live_decision",
)

ALLOWLISTED_INVOCATIONS = (
    "ProductionAutonomyRepository.evaluate",
    "EvidencePackRepository.audit_pack",
    "ProductionPreapprovalRepository.coverage_for_project",
    "AutonomyPolicyRepository.decision_for",
    "EmergencyControlRepository.status",
    "app.repositories.cost.evaluate",
)


@dataclass(frozen=True, slots=True)
class GuardOutcome:
    status: str
    value: Any | None


async def run_guarded_stage(
    *,
    emergency_active: Callable[[], Awaitable[bool]],
    cost_stop: Callable[[], Awaitable[bool]],
    stage: Callable[[], Awaitable[Any]],
) -> GuardOutcome:
    """Run one local stage after the ruled emergency→cost boundary."""
    if await emergency_active():
        return GuardOutcome("paused_emergency_stop", None)
    if await cost_stop():
        return GuardOutcome("paused_cost_stop", None)
    return GuardOutcome("completed", await stage())


class ControlLoopCapabilities:
    """Exact ruled invocation adapter; no dynamic dispatch or extension hook."""

    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        project_id: uuid.UUID,
    ) -> None:
        self.session = session
        self.context = context
        self.project_id = project_id

    async def evaluate_a5(self, *, as_of=None):
        return await ProductionAutonomyRepository(self.session, self.context).evaluate(
            self.project_id, as_of=as_of
        )

    async def reaudit_evidence_pack(self, pack_id: uuid.UUID):
        return await EvidencePackRepository(self.session, self.context).audit_pack(pack_id)

    async def read_preapproval_coverage(self, *, as_of=None):
        return await ProductionPreapprovalRepository(
            self.session, self.context
        ).coverage_for_project(self.project_id, as_of=as_of)

    async def check_autonomy_policy(self):
        return await AutonomyPolicyRepository(self.session, self.context).decision_for(
            self.project_id, "deploy_production"
        )

    async def read_emergency_status(self):
        return await EmergencyControlRepository(self.session, self.context).status(
            self.project_id
        )

    async def evaluate_cost_stop(self, *, as_of_date=None):
        return await cost_evaluate(
            self.session,
            self.context,
            project_id=self.project_id,
            as_of_date=as_of_date,
        )


class ControlLoopState(TypedDict, total=False):
    """Checkpoint-safe bounded state; values are IDs, codes, booleans, and safe A5 data."""

    project_id: str
    project_run_id: str
    control_loop_run_id: str
    outcome_code: str
    completed_stages: tuple[str, ...]
    last_completed_stage: str | None
    binding_ids: dict[str, str]
    preapproval_expires_at: str | None
    preapproval_gate_eligible: bool
    policy_decision: str
    emergency_latch_active: bool
    a5_report: dict[str, object]
    evaluation_id: str
    decision_id: str
    decision_status: str


def _config(project_run_id: uuid.UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(project_run_id), "checkpoint_ns": ""}}


class _ControlLoopExecutor:
    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        project_id: uuid.UUID,
        project_run_id: uuid.UUID,
        control_loop_run_id: uuid.UUID,
        as_of: datetime,
    ) -> None:
        self.session = session
        self.context = context
        self.project_id = project_id
        self.project_run_id = project_run_id
        self.control_loop_run_id = control_loop_run_id
        self.as_of = as_of
        self.capabilities = ControlLoopCapabilities(
            session, context, project_id=project_id
        )
        self.decisions = GoLiveDecisionRepository(session, context)
        self.runs = RunRepository(session, context)

    async def _guard(self, stage_code: str) -> dict[str, object] | None:
        emergency = await self.capabilities.read_emergency_status()
        if emergency.state == "active":
            await self.runs.mark_paused_for_emergency(run_id=self.project_run_id)
            await self.decisions.append_event(
                control_loop_run_id=self.control_loop_run_id,
                stage_code=stage_code,
                outcome_code="paused_emergency_stop",
            )
            return {"outcome_code": "paused_emergency_stop"}
        cost = await self.capabilities.evaluate_cost_stop(as_of_date=self.as_of.date())
        if cost.stop:
            await self.runs.mark_paused_for_cost(
                run_id=self.project_run_id,
                actor="control_loop_runtime",
                payload={"reason": cost.reason.value if cost.reason else "cost_stop"},
            )
            await self.decisions.append_event(
                control_loop_run_id=self.control_loop_run_id,
                stage_code=stage_code,
                outcome_code="paused_cost_stop",
            )
            return {"outcome_code": "paused_cost_stop"}
        return None

    async def _binding_snapshot(self, coverage, emergency) -> tuple[dict[str, str], datetime | None]:
        return await self.decisions.load_binding_snapshot(
            project_id=self.project_id,
            request_id=coverage.request_id,
            attestation_id=coverage.attestation_id,
            emergency_binding_id=emergency.binding_id,
            emergency_event_id=emergency.event_id,
        )

    async def execute(self, stage_code: str, state: ControlLoopState) -> dict[str, object]:
        completed = tuple(state.get("completed_stages", ()))
        if stage_code in completed:
            return {}
        blocked = await self._guard(stage_code)
        if blocked is not None:
            return blocked

        updates: dict[str, object] = {
            "outcome_code": "running",
            "last_completed_stage": stage_code,
            "completed_stages": completed + (stage_code,),
        }
        outcome = "completed"
        evidence_digest = None

        if stage_code == "assemble_or_reaudit_evidence_pack":
            coverage = await self.capabilities.read_preapproval_coverage(as_of=self.as_of)
            emergency = await self.capabilities.read_emergency_status()
            binding_ids, expires_at = await self._binding_snapshot(coverage, emergency)
            updates["binding_ids"] = binding_ids
            updates["preapproval_expires_at"] = (
                expires_at.isoformat() if expires_at is not None else None
            )
            pack_id = binding_ids.get("evidence_pack_id")
            if pack_id is None:
                outcome = "evidence_pack_unavailable_not_executed"
            else:
                core = await self.capabilities.reaudit_evidence_pack(uuid.UUID(pack_id))
                evidence_digest = core.content_hash
                outcome = "evidence_pack_reaudited"
        elif stage_code == "check_cost_and_authority_limits":
            coverage = await self.capabilities.read_preapproval_coverage(as_of=self.as_of)
            policy = await self.capabilities.check_autonomy_policy()
            emergency = await self.capabilities.read_emergency_status()
            binding_ids, expires_at = await self._binding_snapshot(coverage, emergency)
            updates.update(
                {
                    "preapproval_gate_eligible": coverage.gate_eligible,
                    "policy_decision": policy.value,
                    "emergency_latch_active": emergency.state == "active",
                    "binding_ids": binding_ids,
                    "preapproval_expires_at": (
                        expires_at.isoformat() if expires_at is not None else None
                    ),
                }
            )
        elif stage_code == "observe_staging_evidence":
            outcome = "staging_evidence_observed_not_deployed"
        elif stage_code == "evaluate_a5_gate":
            report = await self.capabilities.evaluate_a5(as_of=self.as_of)
            updates["a5_report"] = report.to_dict()
            outcome = "a5_evaluation_completed"
        elif stage_code == "finalize_go_live_decision":
            report_payload = state.get("a5_report")
            if not isinstance(report_payload, dict):
                raise GoLiveDecisionRepositoryError("a5_evaluation_missing")
            report = ProductionAutonomyReport(
                project_id=str(report_payload["project_id"]),
                gates=[
                    GateResult(
                        number=int(item["number"]),
                        gate=str(item["gate"]),
                        status=str(item["status"]),
                        reason=str(item["reason"]),
                        context=dict(item.get("context", {})),
                    )
                    for item in report_payload["gates"]
                ],
            )
            expiry_value = state.get("preapproval_expires_at")
            expiry = (
                datetime.fromisoformat(str(expiry_value))
                if expiry_value is not None
                else None
            )
            evaluation = await self.decisions.record_evaluation(
                control_loop_run_id=self.control_loop_run_id,
                report=report,
                preapproval_gate_eligible=bool(
                    state.get("preapproval_gate_eligible", False)
                ),
                policy_decision=str(state.get("policy_decision", "deny")),
                emergency_latch_active=bool(state.get("emergency_latch_active", True)),
                binding_ids=dict(state.get("binding_ids", {})),
                preapproval_expires_at=expiry,
                evaluated_at=self.as_of,
            )
            updates["evaluation_id"] = str(evaluation.id)
            if (
                report.a5_satisfied
                and evaluation.preapproval_gate_eligible
                and evaluation.policy_decision == "needs_approval"
                and not evaluation.emergency_latch_active
            ):
                decision = await self.decisions.finalize_decision(evaluation.id)
                updates.update(
                    {
                        "decision_id": str(decision.id),
                        "decision_status": decision.status,
                        "outcome_code": "decided_not_executed",
                    }
                )
                outcome = "decision_recorded"
                await self.runs.mark_completed(
                    run_id=self.project_run_id, actor="control_loop_runtime"
                )
            else:
                updates["outcome_code"] = "blocked_evidence_or_authority"
                outcome = "blocked_evidence_or_authority"
                await self.runs.mark_blocked_control_loop(
                    run_id=self.project_run_id,
                    actor="control_loop_runtime",
                    payload={
                        "reason_code": "go_live_predicate_not_satisfied",
                        "passed_gate_count": evaluation.passed_gate_count,
                    },
                )

        await self.decisions.append_event(
            control_loop_run_id=self.control_loop_run_id,
            stage_code=stage_code,
            outcome_code=outcome,
            evidence_reference_digest=evidence_digest,
        )
        return updates


def _build_control_loop_graph(executor: _ControlLoopExecutor, checkpointer):
    graph = StateGraph(ControlLoopState)
    for stage_code in CONTROL_LOOP_NODES:
        async def node(state: ControlLoopState, stage: str = stage_code) -> dict[str, object]:
            return await executor.execute(stage, state)

        graph.add_node(stage_code, node)
    graph.add_edge(START, CONTROL_LOOP_NODES[0])
    for index, stage_code in enumerate(CONTROL_LOOP_NODES[:-1]):
        next_stage = CONTROL_LOOP_NODES[index + 1]

        def route(state: ControlLoopState) -> str:
            return (
                "stop"
                if state.get("outcome_code")
                in {"paused_emergency_stop", "paused_cost_stop"}
                else "continue"
            )

        graph.add_conditional_edges(
            stage_code,
            route,
            {"stop": END, "continue": next_stage},
        )
    graph.add_edge(CONTROL_LOOP_NODES[-1], END)
    return graph.compile(checkpointer=checkpointer)


async def _record_infrastructure_failure(executor: _ControlLoopExecutor) -> None:
    """Retain only a code-owned failure outcome; never persist exception text."""
    try:
        await executor.decisions.append_event(
            control_loop_run_id=executor.control_loop_run_id,
            stage_code="control_loop_runtime",
            outcome_code="failed_infrastructure",
        )
        await executor.runs.mark_failed(
            run_id=executor.project_run_id,
            actor="control_loop_runtime",
            payload={"reason_code": "control_loop_infrastructure_failure"},
        )
    except Exception:
        # The original operation already failed.  A broken transaction cannot
        # safely be reused to manufacture evidence; the outer transaction will
        # roll back and the caller still receives only the fixed safe code.
        pass


async def start_control_loop(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    project_run_id: uuid.UUID,
    idempotency_key: str,
    as_of: datetime | None = None,
) -> dict[str, object]:
    now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    decisions = GoLiveDecisionRepository(session, context)
    cycle = await decisions.start_cycle(
        project_id=project_id,
        project_run_id=project_run_id,
        idempotency_key=idempotency_key,
    )
    runs = RunRepository(session, context)
    checkpointer = UAIDCheckpointer(
        session, context, project_id=project_id, run_id=project_run_id
    )
    executor = _ControlLoopExecutor(
        session,
        context,
        project_id=project_id,
        project_run_id=project_run_id,
        control_loop_run_id=cycle.id,
        as_of=now,
    )
    graph = _build_control_loop_graph(executor, checkpointer)
    config = _config(project_run_id)
    run = await runs.get(project_run_id)
    if run is None or run.project_id != project_id:
        raise GoLiveDecisionRepositoryError("project_run_unavailable")
    if run.status != "created":
        snapshot = await graph.aget_state(config)
        replay = dict(snapshot.values or {})
        if replay.get("control_loop_run_id") != str(cycle.id):
            raise GoLiveDecisionRepositoryError("control_loop_replay_state_unavailable")
        return replay
    await runs.mark_running(run_id=project_run_id, actor="control_loop_runtime")
    try:
        state = await graph.ainvoke(
            ControlLoopState(
                project_id=str(project_id),
                project_run_id=str(project_run_id),
                control_loop_run_id=str(cycle.id),
                outcome_code="running",
                completed_stages=(),
                last_completed_stage=None,
            ),
            config,
        )
    except Exception:
        await _record_infrastructure_failure(executor)
        raise GoLiveDecisionRepositoryError("control_loop_infrastructure_failure") from None
    return dict(state)


async def resume_control_loop(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    project_run_id: uuid.UUID,
    control_loop_run_id: uuid.UUID,
    as_of: datetime | None = None,
) -> dict[str, object]:
    """Resume the same bounded cycle; completed stage effects remain idempotent."""
    now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    decisions = GoLiveDecisionRepository(session, context)
    cycle = await decisions._require_cycle(control_loop_run_id)
    if cycle.project_id != project_id or cycle.project_run_id != project_run_id:
        raise GoLiveDecisionRepositoryError("control_loop_binding_mismatch")
    capabilities = ControlLoopCapabilities(session, context, project_id=project_id)
    emergency = await capabilities.read_emergency_status()
    cost = await capabilities.evaluate_cost_stop(as_of_date=now.date())
    checkpointer = UAIDCheckpointer(
        session, context, project_id=project_id, run_id=project_run_id
    )
    executor = _ControlLoopExecutor(
        session,
        context,
        project_id=project_id,
        project_run_id=project_run_id,
        control_loop_run_id=control_loop_run_id,
        as_of=now,
    )
    graph = _build_control_loop_graph(executor, checkpointer)
    config = _config(project_run_id)
    snapshot = await graph.aget_state(config)
    state = dict(snapshot.values or {})
    if emergency.state == "active":
        state["outcome_code"] = "paused_emergency_stop"
        return state
    if cost.stop:
        state["outcome_code"] = "paused_cost_stop"
        return state
    run = await RunRepository(session, context).get(project_run_id)
    if run is None or run.project_id != project_id:
        raise GoLiveDecisionRepositoryError("project_run_unavailable")
    if run.status not in {"paused", "blocked"}:
        raise GoLiveDecisionRepositoryError("control_loop_not_resumable")
    await RunRepository(session, context).mark_resumed(
        run_id=project_run_id,
        actor="control_loop_runtime",
        payload={"reason_code": "control_loop_resumed"},
    )
    state["outcome_code"] = "running"
    try:
        resumed = await graph.ainvoke(ControlLoopState(**state), config)
    except Exception:
        await _record_infrastructure_failure(executor)
        raise GoLiveDecisionRepositoryError("control_loop_infrastructure_failure") from None
    return dict(resumed)
