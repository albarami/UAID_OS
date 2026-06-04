"""Tenant-scoped run state machine + append-only ``run_steps`` (Slice 8a, §23.2).

Drives ``project_runs.status`` transitions (validated) and records the immutable
``run_steps`` history; status-changing transitions are audited (Slice 2). Run inside
``tenant_scope`` (GUC set). The full transition table is defined here; Slice 8a only
exercises the start / resume / complete / fail subset (paused/blocked are 8b).
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.project_run import ProjectRun
from app.models.run_step import RunStep
from app.tenancy import TenantContext, TenantScopedRepository

# Validated transition table over the existing project_runs.status set.
_ALLOWED: dict[str, set[str]] = {
    "created": {"running"},
    "running": {"completed", "failed", "paused", "blocked"},
    "paused": {"running", "failed"},
    "blocked": {"running", "failed"},
    "completed": set(),
    "failed": set(),
}


class InvalidRunTransition(Exception):
    """Raised when a project_run status transition is not allowed."""


class RunNotFound(Exception):
    pass


def is_valid_transition(from_status: str, to_status: str) -> bool:
    return to_status in _ALLOWED.get(from_status, set())


class RunRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ProjectRun)

    async def _require(self, run_id: uuid.UUID) -> ProjectRun:
        run = await self.get(run_id)
        if run is None:
            raise RunNotFound(str(run_id))
        return run

    async def record_step(
        self,
        *,
        run_id: uuid.UUID,
        project_id: uuid.UUID,
        event_type: str,
        node: str | None = None,
        status_from: str | None = None,
        status_to: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunStep:
        step = RunStep(
            project_id=project_id,
            run_id=run_id,
            node=node,
            event_type=event_type,
            status_from=status_from,
            status_to=status_to,
            payload=payload or {},
        )
        await self.add(step)  # stamps tenant_id
        await self.session.flush()
        return step

    async def transition(
        self,
        *,
        run_id: uuid.UUID,
        to_status: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> ProjectRun:
        run = await self._require(run_id)
        from_status = run.status
        if not is_valid_transition(from_status, to_status):
            raise InvalidRunTransition(f"{from_status} -> {to_status} is not allowed")
        run.status = to_status
        await self.session.flush()
        await self.record_step(
            run_id=run_id,
            project_id=run.project_id,
            event_type=event_type,
            status_from=from_status,
            status_to=to_status,
            payload=payload,
        )
        # Status-changing transitions are audited (safe metadata only).
        await audit_record(
            self.session,
            action=f"run.{event_type}",
            actor=actor,
            target=f"run:{run_id}",
            payload={
                "run_id": str(run_id),
                "project_id": str(run.project_id),
                "from": from_status,
                "to": to_status,
            },
        )
        return run

    # Convenience wrappers for the 8a lifecycle subset.
    async def mark_running(self, *, run_id, actor) -> ProjectRun:
        return await self.transition(
            run_id=run_id, to_status="running", event_type="run_started", actor=actor
        )

    async def mark_completed(self, *, run_id, actor) -> ProjectRun:
        return await self.transition(
            run_id=run_id, to_status="completed", event_type="run_completed", actor=actor
        )

    async def mark_failed(self, *, run_id, actor, payload=None) -> ProjectRun:
        return await self.transition(
            run_id=run_id, to_status="failed", event_type="run_failed", actor=actor, payload=payload
        )
