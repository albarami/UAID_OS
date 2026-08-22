"""Tenant-scoped Slice-55 evaluation and non-executing decision persistence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.go_live_decision import (
    ControlLoopEvent,
    ControlLoopRun,
    GoLiveDecision,
    GoLiveEvaluation,
    GoLiveEvaluationGateResult,
)
from app.models.autonomy_policy import AutonomyPolicy
from app.models.emergency_control import EmergencyStopEvent
from app.models.production_preapproval import (
    ProductionPreapprovalAttestation,
    ProductionPreapprovalRequest,
)
from app.release.go_live_decision import (
    CONTROL_LOOP_CONTRACT_VERSION,
    GO_LIVE_EVALUATION_CONTRACT_VERSION,
    GateSnapshot,
    canonical_gate_digest,
    validate_event_transition,
)
from app.release.production_autonomy import A5_RULESET_VERSION, ProductionAutonomyReport
from app.tenancy import TenantContext, TenantScopedRepository, tenant_scope


class GoLiveDecisionRepositoryError(ValueError):
    """Safe, code-owned repository failure."""


RETRYABLE_TRANSACTION_SQLSTATES = frozenset({"40001", "40P01"})
SERIALIZABLE_MAX_ATTEMPTS = 5
RETRY_BACKOFF_BASE_SECONDS = 0.005
RETRY_BACKOFF_JITTER_SECONDS = 0.003
_WorkResult = TypeVar("_WorkResult")


def transaction_sqlstate(exc: BaseException) -> str | None:
    """Return a nested PostgreSQL SQLSTATE without changing the exception."""
    pending: list[BaseException] = [exc]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(current, attribute, None)
            if isinstance(value, str):
                return value
        for attribute in ("orig", "__cause__", "__context__"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException):
                pending.append(nested)
    return None


def is_retryable_transaction_error(exc: BaseException) -> bool:
    """Return whether ``exc`` carries a retryable PostgreSQL transaction code."""
    return transaction_sqlstate(exc) in RETRYABLE_TRANSACTION_SQLSTATES


def _retry_delay_seconds(attempt: int) -> float:
    exponential = RETRY_BACKOFF_BASE_SECONDS * (2**attempt)
    return exponential + random.uniform(0.0, RETRY_BACKOFF_JITTER_SECONDS)


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hash_text(value: str) -> str:
    return _hash_bytes(value.encode("utf-8"))


def _context_digest(value: Mapping[str, object]) -> str:
    return _hash_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    )


def _uuid_or_none(values: Mapping[str, str], key: str) -> uuid.UUID | None:
    value = values.get(key)
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise GoLiveDecisionRepositoryError(f"invalid_binding_id:{key}") from exc


def _evaluation_binding_digest(
    *,
    binding_ids: Mapping[str, str],
    preapproval_gate_eligible: bool,
    policy_decision: str,
    emergency_latch_active: bool,
) -> str:
    ordered = (
        "release_candidate_id",
        "evidence_pack_id",
        "release_verdict_id",
        "preapproval_request_id",
        "preapproval_attestation_id",
        "autonomy_policy_id",
        "autonomy_policy_digest",
        "autonomy_policy_updated_at",
        "emergency_control_binding_id",
        "emergency_stop_event_id",
    )
    fields = [binding_ids.get(key, "") for key in ordered]
    fields.extend(
        (
            str(preapproval_gate_eligible).lower(),
            policy_decision,
            str(emergency_latch_active).lower(),
            A5_RULESET_VERSION,
            GO_LIVE_EVALUATION_CONTRACT_VERSION,
        )
    )
    return _hash_text("|".join(fields))


async def run_serializable_tenant_work(
    context: TenantContext,
    work: Callable[[AsyncSession], Awaitable[_WorkResult]],
) -> _WorkResult:
    """Run ``work(session)`` in a fresh SERIALIZABLE tenant transaction.

    Serialization failures retry the complete transaction, not a savepoint.
    """
    for attempt in range(SERIALIZABLE_MAX_ATTEMPTS):
        try:
            async with tenant_scope(context, isolation_level="SERIALIZABLE") as session:
                isolation = await session.scalar(text("SHOW transaction_isolation"))
                if isolation != "serializable":
                    raise GoLiveDecisionRepositoryError("serializable_isolation_required")
                return await work(session)
        except Exception as exc:
            if (
                not is_retryable_transaction_error(exc)
                or attempt + 1 >= SERIALIZABLE_MAX_ATTEMPTS
            ):
                raise
            await asyncio.sleep(_retry_delay_seconds(attempt))
    raise AssertionError("bounded retry loop exhausted without returning or raising")


class GoLiveDecisionRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ControlLoopRun)

    async def start_cycle(
        self,
        *,
        project_id: uuid.UUID,
        project_run_id: uuid.UUID,
        idempotency_key: str,
    ) -> ControlLoopRun:
        if not idempotency_key or len(idempotency_key.encode()) > 256:
            raise GoLiveDecisionRepositoryError("idempotency_key_invalid")
        digest = _hash_text(idempotency_key)
        contract_hash = _hash_text(CONTROL_LOOP_CONTRACT_VERSION)
        stmt = (
            pg_insert(ControlLoopRun)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                project_run_id=project_run_id,
                idempotency_digest=digest,
                control_loop_contract_version=CONTROL_LOOP_CONTRACT_VERSION,
                control_loop_contract_hash=contract_hash,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "project_id", "idempotency_digest"]
            )
            .returning(ControlLoopRun.id)
        )
        new_id = (await self.session.execute(stmt)).scalar_one_or_none()
        row = (
            await self.session.execute(
                select(ControlLoopRun).where(
                    ControlLoopRun.tenant_id == self.context.tenant_id,
                    ControlLoopRun.project_id == project_id,
                    ControlLoopRun.idempotency_digest == digest,
                )
            )
        ).scalar_one()
        if new_id is None and row.project_run_id != project_run_id:
            raise GoLiveDecisionRepositoryError("idempotency_conflict")
        if new_id is not None:
            await audit_record(
                self.session,
                action="control_loop.started",
                actor="control_loop_runtime",
                target="control_loop_run",
                payload={
                    "project_id": str(project_id),
                    "control_loop_run_id": str(row.id),
                    "contract_version": CONTROL_LOOP_CONTRACT_VERSION,
                },
            )
        return row

    async def require_serializable(self) -> None:
        """Fail closed unless this transaction is already SERIALIZABLE."""
        isolation = await self.session.scalar(text("SHOW transaction_isolation"))
        if isolation != "serializable":
            raise GoLiveDecisionRepositoryError("serializable_isolation_required")

    async def require_evaluation(self, evaluation_id: uuid.UUID) -> GoLiveEvaluation:
        row = (
            await self.session.execute(
                select(GoLiveEvaluation).where(
                    GoLiveEvaluation.id == evaluation_id,
                    GoLiveEvaluation.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise GoLiveDecisionRepositoryError("evaluation_unavailable")
        return row

    def preview_evaluation_digests(
        self,
        *,
        report: ProductionAutonomyReport,
        preapproval_gate_eligible: bool,
        policy_decision: str,
        emergency_latch_active: bool,
        binding_ids: Mapping[str, str],
    ) -> dict[str, str]:
        """Derive current digests without persisting an evaluation row."""
        snapshots = tuple(
            GateSnapshot(
                gate_number=gate.number,
                gate_name=gate.gate,
                status=gate.status,
                reason=gate.reason,
                safe_context_digest=_context_digest(gate.context),
            )
            for gate in report.gates
        )
        return {
            "gate_result_digest": canonical_gate_digest(snapshots),
            "decision_binding_digest": _evaluation_binding_digest(
                binding_ids=binding_ids,
                preapproval_gate_eligible=preapproval_gate_eligible,
                policy_decision=policy_decision,
                emergency_latch_active=emergency_latch_active,
            ),
        }

    async def _require_cycle(self, cycle_id: uuid.UUID) -> ControlLoopRun:
        row = (
            await self.session.execute(
                select(ControlLoopRun).where(
                    ControlLoopRun.id == cycle_id,
                    ControlLoopRun.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise GoLiveDecisionRepositoryError("control_loop_unavailable")
        return row

    async def append_event(
        self,
        *,
        control_loop_run_id: uuid.UUID,
        stage_code: str,
        outcome_code: str,
        evidence_reference_digest: str | None = None,
    ) -> ControlLoopEvent:
        cycle = await self._require_cycle(control_loop_run_id)
        prior = (
            await self.session.execute(
                select(ControlLoopEvent)
                .where(
                    ControlLoopEvent.tenant_id == self.context.tenant_id,
                    ControlLoopEvent.control_loop_run_id == cycle.id,
                )
                .order_by(ControlLoopEvent.ordinal.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        try:
            validate_event_transition(
                prior.stage_code if prior is not None else None,
                prior.outcome_code if prior is not None else None,
                stage_code,
                outcome_code,
            )
        except ValueError as exc:
            raise GoLiveDecisionRepositoryError("control_loop_event_transition_invalid") from exc
        ordinal = 1 if prior is None else prior.ordinal + 1
        if ordinal > 64:
            raise GoLiveDecisionRepositoryError("control_loop_event_limit")
        event = ControlLoopEvent(
            tenant_id=self.context.tenant_id,
            project_id=cycle.project_id,
            control_loop_run_id=cycle.id,
            ordinal=ordinal,
            previous_event_id=prior.id if prior else None,
            stage_code=stage_code,
            outcome_code=outcome_code,
            evidence_reference_digest=evidence_reference_digest,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def record_evaluation(
        self,
        *,
        control_loop_run_id: uuid.UUID,
        report: ProductionAutonomyReport,
        preapproval_gate_eligible: bool,
        policy_decision: str,
        emergency_latch_active: bool,
        binding_ids: Mapping[str, str],
        preapproval_expires_at: datetime | None = None,
        evaluated_at: datetime | None = None,
    ) -> GoLiveEvaluation:
        await self.require_serializable()
        cycle = await self._require_cycle(control_loop_run_id)
        if report.project_id != str(cycle.project_id):
            raise GoLiveDecisionRepositoryError("evaluation_project_mismatch")
        if policy_decision not in {"needs_approval", "deny", "allow"}:
            raise GoLiveDecisionRepositoryError("policy_decision_invalid")
        snapshots = tuple(
            GateSnapshot(
                gate_number=gate.number,
                gate_name=gate.gate,
                status=gate.status,
                reason=gate.reason,
                safe_context_digest=_context_digest(gate.context),
            )
            for gate in report.gates
        )
        gate_digest = canonical_gate_digest(snapshots)
        binding_digest = _evaluation_binding_digest(
            binding_ids=binding_ids,
            preapproval_gate_eligible=preapproval_gate_eligible,
            policy_decision=policy_decision,
            emergency_latch_active=emergency_latch_active,
        )
        evaluation = GoLiveEvaluation(
            tenant_id=self.context.tenant_id,
            project_id=cycle.project_id,
            control_loop_run_id=cycle.id,
            evaluated_at=(evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc),
            ruleset_version=A5_RULESET_VERSION,
            evaluation_contract_version=GO_LIVE_EVALUATION_CONTRACT_VERSION,
            evaluation_contract_hash=_hash_text(GO_LIVE_EVALUATION_CONTRACT_VERSION),
            gate_result_digest=gate_digest,
            passed_gate_count=sum(gate.status == "passed" for gate in snapshots),
            all_gates_passed=all(gate.status == "passed" for gate in snapshots),
            preapproval_gate_eligible=preapproval_gate_eligible,
            policy_decision=policy_decision,
            emergency_latch_active=emergency_latch_active,
            release_candidate_id=_uuid_or_none(binding_ids, "release_candidate_id"),
            evidence_pack_id=_uuid_or_none(binding_ids, "evidence_pack_id"),
            release_verdict_id=_uuid_or_none(binding_ids, "release_verdict_id"),
            preapproval_request_id=_uuid_or_none(binding_ids, "preapproval_request_id"),
            preapproval_attestation_id=_uuid_or_none(
                binding_ids, "preapproval_attestation_id"
            ),
            preapproval_expires_at=preapproval_expires_at,
            autonomy_policy_id=_uuid_or_none(binding_ids, "autonomy_policy_id"),
            autonomy_policy_digest=binding_ids.get("autonomy_policy_digest"),
            autonomy_policy_updated_at=(
                datetime.fromisoformat(binding_ids["autonomy_policy_updated_at"])
                if binding_ids.get("autonomy_policy_updated_at")
                else None
            ),
            emergency_control_binding_id=_uuid_or_none(
                binding_ids, "emergency_control_binding_id"
            ),
            emergency_stop_event_id=_uuid_or_none(binding_ids, "emergency_stop_event_id"),
            decision_binding_digest=binding_digest,
        )
        self.session.add(evaluation)
        await self.session.flush()
        self.session.add_all(
            [
                GoLiveEvaluationGateResult(
                    tenant_id=self.context.tenant_id,
                    project_id=cycle.project_id,
                    evaluation_id=evaluation.id,
                    gate_number=gate.gate_number,
                    gate_name_code=gate.gate_name,
                    status=gate.status,
                    reason_code=gate.reason,
                    safe_context_digest=gate.safe_context_digest,
                    ordinal=gate.gate_number,
                )
                for gate in snapshots
            ]
        )
        await self.session.flush()
        await self.session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await self.session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        await audit_record(
            self.session,
            action="control_loop.a5_evaluated",
            actor="control_loop_runtime",
            target="go_live_evaluation",
            payload={
                "project_id": str(cycle.project_id),
                "control_loop_run_id": str(cycle.id),
                "evaluation_id": str(evaluation.id),
                "passed_gate_count": evaluation.passed_gate_count,
                "all_gates_passed": evaluation.all_gates_passed,
                "ruleset_version": A5_RULESET_VERSION,
            },
        )
        return evaluation

    async def finalize_decision(self, evaluation_id: uuid.UUID) -> GoLiveDecision:
        await self.require_serializable()
        try:
            # Translate a function RAISE without retrying a savepoint. A 40001
            # still aborts the whole Postgres transaction; owned work retries it.
            async with self.session.begin_nested():
                decision_id = (
                    await self.session.execute(
                        text("SELECT public.slice55_finalize_decision(:evaluation)"),
                        {"evaluation": evaluation_id},
                    )
                ).scalar_one()
        except DBAPIError as exc:
            if is_retryable_transaction_error(exc):
                raise
            message = str(getattr(exc, "orig", exc))
            code = (
                "predicate_not_satisfied"
                if "predicate not satisfied" in message
                else "decision_finalization_refused"
            )
            raise GoLiveDecisionRepositoryError(code) from exc
        return (
            await self.session.execute(
                select(GoLiveDecision).where(
                    GoLiveDecision.id == decision_id,
                    GoLiveDecision.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one()

    async def latest_decision(self, project_id: uuid.UUID) -> GoLiveDecision | None:
        return (
            await self.session.execute(
                select(GoLiveDecision)
                .where(
                    GoLiveDecision.tenant_id == self.context.tenant_id,
                    GoLiveDecision.project_id == project_id,
                )
                .order_by(GoLiveDecision.decision_seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def current_decision(
        self, project_id: uuid.UUID, *, as_of: datetime | None = None
    ) -> GoLiveDecision | None:
        """Return only a latest-cycle, still-bound historical decision.

        This is not production authorization; a future execution slice must run a
        new full evaluation rather than relying on this read.
        """
        now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        latest_cycle = (
            await self.session.execute(
                select(ControlLoopRun)
                .where(
                    ControlLoopRun.tenant_id == self.context.tenant_id,
                    ControlLoopRun.project_id == project_id,
                )
                .order_by(ControlLoopRun.created_at.desc(), ControlLoopRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        decision = await self.latest_decision(project_id)
        if latest_cycle is None or decision is None or decision.control_loop_run_id != latest_cycle.id:
            return None
        evaluation = (
            await self.session.execute(
                select(GoLiveEvaluation).where(
                    GoLiveEvaluation.id == decision.evaluation_id,
                    GoLiveEvaluation.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if (
            evaluation is None
            or evaluation.preapproval_expires_at is None
            or evaluation.preapproval_expires_at <= now
        ):
            return None
        latest_request_id = (
            await self.session.execute(
                select(ProductionPreapprovalRequest.id)
                .where(
                    ProductionPreapprovalRequest.tenant_id == self.context.tenant_id,
                    ProductionPreapprovalRequest.project_id == project_id,
                )
                .order_by(
                    ProductionPreapprovalRequest.created_at.desc(),
                    ProductionPreapprovalRequest.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        latest_emergency_id = (
            await self.session.execute(
                select(EmergencyStopEvent.id)
                .where(
                    EmergencyStopEvent.tenant_id == self.context.tenant_id,
                    EmergencyStopEvent.project_id == project_id,
                )
                .order_by(EmergencyStopEvent.created_at.desc(), EmergencyStopEvent.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        autonomy_id = (
            await self.session.execute(
                select(AutonomyPolicy).where(
                    AutonomyPolicy.tenant_id == self.context.tenant_id,
                    AutonomyPolicy.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if (
            latest_request_id != decision.preapproval_request_id
            or latest_emergency_id != decision.emergency_stop_event_id
            or autonomy_id is None
            or autonomy_id.id != decision.autonomy_policy_id
            or autonomy_id.updated_at != evaluation.autonomy_policy_updated_at
            or decision.autonomy_policy_digest != evaluation.autonomy_policy_digest
        ):
            return None
        return decision

    async def load_binding_snapshot(
        self,
        *,
        project_id: uuid.UUID,
        request_id: uuid.UUID | None,
        attestation_id: uuid.UUID | None,
        emergency_binding_id: uuid.UUID | None,
        emergency_event_id: uuid.UUID | None,
    ) -> tuple[dict[str, str], datetime | None]:
        """Load exact FK material only; authority/currentness stays in ruled readers."""
        if request_id is None or attestation_id is None:
            return {}, None
        request = (
            await self.session.execute(
                select(ProductionPreapprovalRequest).where(
                    ProductionPreapprovalRequest.id == request_id,
                    ProductionPreapprovalRequest.project_id == project_id,
                    ProductionPreapprovalRequest.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        attestation = (
            await self.session.execute(
                select(ProductionPreapprovalAttestation).where(
                    ProductionPreapprovalAttestation.id == attestation_id,
                    ProductionPreapprovalAttestation.request_id == request_id,
                    ProductionPreapprovalAttestation.project_id == project_id,
                    ProductionPreapprovalAttestation.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        autonomy = (
            await self.session.execute(
                select(AutonomyPolicy).where(
                    AutonomyPolicy.id == request.autonomy_policy_id,
                    AutonomyPolicy.project_id == project_id,
                    AutonomyPolicy.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none() if request is not None else None
        if request is None or attestation is None or autonomy is None:
            return {}, None
        values = {
            "release_candidate_id": str(request.release_candidate_id),
            "evidence_pack_id": str(request.evidence_pack_id),
            "release_verdict_id": str(request.release_verdict_id),
            "preapproval_request_id": str(request.id),
            "preapproval_attestation_id": str(attestation.id),
            "autonomy_policy_id": str(request.autonomy_policy_id),
            "autonomy_policy_digest": request.autonomy_policy_digest,
            "autonomy_policy_updated_at": autonomy.updated_at.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
        }
        if emergency_binding_id is not None:
            values["emergency_control_binding_id"] = str(emergency_binding_id)
        if emergency_event_id is not None:
            values["emergency_stop_event_id"] = str(emergency_event_id)
        return values, attestation.expires_at
