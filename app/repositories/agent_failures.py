"""Tenant-scoped agent-failure repository (Slice 41, §9.6 replacement policy).

``record_failure`` stores a **REPORTED** (caller-supplied, unverified — B1/B2) §9.6
failure-pattern classification against a same-tenant agent instance (append-only; the
``project_id`` is derived from the instance, never caller input). ``evaluate_replacement``
is the **compute-on-read** §9.6 prescription + retry-cap DECISION (OD-3/D-41-4) — no write,
no persistence, non-authorizing, and it executes NOTHING (no auto-suspend, OD-1; the
prescribed responses are recorded recommendations). A nonexistent/cross-tenant instance
yields the generic no-failure decision (no existence oracle, the Slice-21 no-leak model).
Audit carries safe metadata only — never ``summary``/``detail``/``evidence_ref``. Run inside
``tenant_scope``. ``reported_by``/``source`` are UNTRUSTED labels.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.failure_policy import (
    MAX_FAILURE_ATTEMPTS,
    ReplacementDecision,
    effective_response,
    prescribe,
    validate_failure_event,
)
from app.audit import record as audit_record
from app.models.agent_failure_event import AgentFailureEvent
from app.models.agent_instance import AgentInstance
from app.tenancy import TenantContext, TenantScopedRepository


class AgentFailureRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AgentFailureEvent)

    async def record_failure(
        self,
        *,
        instance_id: uuid.UUID,
        failure_pattern: str,
        severity: str,
        source: str,
        reported_by: str,
        evidence_ref: str | None = None,
        summary: str | None = None,
        detail: str | None = None,
        source_provenance: str = "caller_supplied_unverified",
    ) -> AgentFailureEvent:
        validate_failure_event(
            failure_pattern=failure_pattern,
            severity=severity,
            source=source,
            reported_by=reported_by,
            evidence_ref=evidence_ref,
            summary=summary,
            detail=detail,
            source_provenance=source_provenance,
        )
        stmt = select(AgentInstance).where(
            AgentInstance.id == instance_id,
            AgentInstance.tenant_id == self.context.tenant_id,
        )
        instance = (await self.session.execute(stmt)).scalars().first()
        if instance is None:
            raise ValueError(f"unknown instance for this tenant: {instance_id}")
        event = AgentFailureEvent(
            tenant_id=self.context.tenant_id,
            project_id=instance.project_id,
            instance_id=instance.id,
            failure_pattern=failure_pattern,
            severity=severity,
            source=source,
            source_provenance=source_provenance,
            evidence_ref=evidence_ref,
            summary=summary,
            detail=detail,
            reported_by=reported_by,
        )
        self.session.add(event)
        await self.session.flush()
        await audit_record(
            self.session,
            action="agent_failure.recorded",
            actor=reported_by,
            target=f"agent_failure_event:{event.id}",
            payload={
                "agent_failure_event_id": str(event.id),
                "instance_id": str(instance.id),
                "project_id": str(instance.project_id),
                "failure_pattern": failure_pattern,
                "severity": severity,
                "source": source,
                "source_provenance": source_provenance,
            },
        )
        return event

    async def evaluate_replacement(self, instance_id: uuid.UUID) -> ReplacementDecision:
        """The compute-on-read §9.6 decision — reads events, computes pure, writes nothing."""
        events = await self.failures_for(instance_id)
        attempt_count = len(events)
        latest_pattern = events[0].failure_pattern if events else None
        return ReplacementDecision(
            instance_id=str(instance_id),
            attempt_count=attempt_count,
            latest_pattern=latest_pattern,
            prescribed_response=None if latest_pattern is None else prescribe(latest_pattern),
            budget_exhausted=attempt_count >= MAX_FAILURE_ATTEMPTS,
            effective_response=effective_response(
                attempt_count=attempt_count, latest_pattern=latest_pattern
            ),
        )

    async def failures_for(self, instance_id: uuid.UUID) -> Sequence[AgentFailureEvent]:
        stmt = (
            select(AgentFailureEvent)
            .where(
                AgentFailureEvent.tenant_id == self.context.tenant_id,
                AgentFailureEvent.instance_id == instance_id,
            )
            .order_by(AgentFailureEvent.created_at.desc(), AgentFailureEvent.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def attempt_count(self, instance_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(AgentFailureEvent)
            .where(
                AgentFailureEvent.tenant_id == self.context.tenant_id,
                AgentFailureEvent.instance_id == instance_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one()
