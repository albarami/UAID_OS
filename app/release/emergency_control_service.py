"""Authoritative Slice-54 bodyless emergency-control workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emergency_control import EmergencyRollbackAuthorization, EmergencyStopEvent
from app.release.production_approval import idempotency_digest, subject_digest
from app.repositories.emergency_controls import (
    EmergencyControlRepository,
    EmergencyControlRepositoryError,
    lock_project_row,
)
from app.tenancy import TenantContext


class EmergencyControlNotFound(LookupError):
    """Generic absent/cross-tenant result."""


class EmergencyControlConflict(ValueError):
    """Generic fail-closed operation conflict."""


@dataclass(frozen=True)
class EmergencyControlResult:
    binding_id: uuid.UUID | None
    event_id: uuid.UUID | None
    authorization_id: uuid.UUID | None
    state: str
    reason_code: str
    affected_run_count: int = 0


class EmergencyControlService:
    def __init__(self, session: AsyncSession, context: TenantContext):
        self.session = session
        self.context = context
        self.repo = EmergencyControlRepository(session, context)

    def _actor(self):
        actor = self.context.actor
        if (
            actor is None
            or actor.actor_type != "human"
            or actor.provenance != "request_authenticated"
        ):
            raise EmergencyControlConflict("emergency_control_unavailable")
        return actor, subject_digest(actor.subject)

    async def _current_binding_member(self, project_id: uuid.UUID):
        actor, actor_hash = self._actor()
        binding = await self.repo.latest_binding(project_id)
        if binding is None or binding.binding_attempt_status != "succeeded":
            raise EmergencyControlNotFound("emergency_control_unavailable")
        sources = await self.repo.current_authority_sources(project_id)
        parsed = sources.parsed_policy
        if (
            parsed is None
            or binding.policy_digest != parsed.policy_digest
            or binding.checklist_digest != parsed.checklist_digest
            or actor_hash not in parsed.approver_subject_hashes
        ):
            raise EmergencyControlConflict("emergency_control_unavailable")
        member = await self.repo.member_for_actor(binding, actor_hash)
        if member is None:
            raise EmergencyControlConflict("emergency_control_unavailable")
        return actor, binding, member

    async def bind(self, *, project_id: uuid.UUID, idempotency_key: str) -> EmergencyControlResult:
        actor, actor_hash = self._actor()
        key_hash = idempotency_digest(idempotency_key)
        await lock_project_row(self.session, self.context, project_id)
        existing = await self.repo.find_binding_by_idempotency(project_id, key_hash)
        if existing is not None:
            status = await self.repo.status(project_id)
            return EmergencyControlResult(
                existing.id, status.event_id, None, status.state, "idempotent_replay"
            )
        try:
            binding = await self.repo.append_binding(
                project_id=project_id,
                actor_subject_hash=actor_hash,
                actor_type=actor.actor_type,
                idempotency_key_hash=key_hash,
            )
        except EmergencyControlRepositoryError as exc:
            raise EmergencyControlConflict("emergency_control_unavailable") from exc
        status = await self.repo.status(project_id)
        return EmergencyControlResult(
            binding.id, status.event_id, None, status.state, binding.reason_code
        )

    async def _existing_event(
        self, project_id: uuid.UUID, key_hash: str
    ) -> EmergencyStopEvent | None:
        return (
            await self.session.execute(
                select(EmergencyStopEvent).where(
                    EmergencyStopEvent.tenant_id == self.context.tenant_id,
                    EmergencyStopEvent.project_id == project_id,
                    EmergencyStopEvent.idempotency_key_hash == key_hash,
                )
            )
        ).scalar_one_or_none()

    async def activate(
        self, *, project_id: uuid.UUID, idempotency_key: str
    ) -> EmergencyControlResult:
        _, binding, member = await self._current_binding_member(project_id)
        key_hash = idempotency_digest(idempotency_key)
        existing = await self._existing_event(project_id, key_hash)
        if existing is not None:
            if existing.event_type != "activated":
                raise EmergencyControlConflict("emergency_control_unavailable")
            return EmergencyControlResult(
                binding.id, existing.id, None, existing.state_after, "idempotent_replay"
            )
        try:
            event, count = await self.repo.activate(
                binding=binding, member=member, idempotency_key_hash=key_hash
            )
        except EmergencyControlRepositoryError as exc:
            raise EmergencyControlConflict("emergency_control_unavailable") from exc
        return EmergencyControlResult(
            binding.id, event.id, None, "active", "local_runtime_stop_activated", count
        )

    async def clear(self, *, project_id: uuid.UUID, idempotency_key: str) -> EmergencyControlResult:
        _, binding, member = await self._current_binding_member(project_id)
        key_hash = idempotency_digest(idempotency_key)
        existing = await self._existing_event(project_id, key_hash)
        if existing is not None:
            if existing.event_type != "cleared":
                raise EmergencyControlConflict("emergency_control_unavailable")
            return EmergencyControlResult(
                binding.id, existing.id, None, existing.state_after, "idempotent_replay"
            )
        try:
            event = await self.repo.clear(
                binding=binding, member=member, idempotency_key_hash=key_hash
            )
        except EmergencyControlRepositoryError as exc:
            raise EmergencyControlConflict("emergency_control_unavailable") from exc
        return EmergencyControlResult(
            binding.id, event.id, None, "armed", "local_runtime_stop_cleared"
        )

    async def authorize_rollback(
        self, *, project_id: uuid.UUID, idempotency_key: str
    ) -> EmergencyControlResult:
        _, binding, member = await self._current_binding_member(project_id)
        key_hash = idempotency_digest(idempotency_key)
        existing = (
            await self.session.execute(
                select(EmergencyRollbackAuthorization).where(
                    EmergencyRollbackAuthorization.tenant_id == self.context.tenant_id,
                    EmergencyRollbackAuthorization.project_id == project_id,
                    EmergencyRollbackAuthorization.idempotency_key_hash == key_hash,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return EmergencyControlResult(
                binding.id, None, existing.id, "authorized_not_executed", "idempotent_replay"
            )
        try:
            row = await self.repo.authorize_rollback(
                binding=binding, member=member, idempotency_key_hash=key_hash
            )
        except EmergencyControlRepositoryError as exc:
            raise EmergencyControlConflict("emergency_control_unavailable") from exc
        return EmergencyControlResult(
            binding.id,
            None,
            row.id,
            "authorized_not_executed",
            "rollback_authorized_not_executed",
        )

    async def current(self, *, project_id: uuid.UUID) -> EmergencyControlResult:
        await self._current_binding_member(project_id)
        status = await self.repo.status(project_id)
        return EmergencyControlResult(
            status.binding_id,
            status.event_id,
            None,
            status.state,
            status.reason_code,
        )
