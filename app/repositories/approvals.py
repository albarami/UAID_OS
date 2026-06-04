"""Tenant-scoped approval lifecycle (Slice 4, §18).

request → await → resolve (approve/reject/cancel), plus on-demand non-response
expiry. Every transition writes an `approval_events` row and an `audit_log`
entry (safe metadata). Must be used inside ``tenant_scope`` (GUC set).

`requested_by`/`resolved_by` are UNTRUSTED caller labels until request-auth
exists; `approver_provenance` stays ``caller_supplied_unverified``. These records
are NOT verified human approvals.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.states import (
    InvalidApprovalRequest,
    InvalidApprovalTransition,
    RiskTier,
    Status,
    auto_transition,
    compute_deadline,
)
from app.approvals.states import is_blocked as _gate_is_blocked
from app.audit import record as audit_record
from app.models.approval import Approval
from app.models.approval_event import ApprovalEvent
from app.policy.matrix import is_mandatory_action
from app.tenancy import TenantContext, TenantScopedRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, Approval)

    async def request(
        self,
        *,
        project_id: uuid.UUID,
        action: str,
        risk_tier: str,
        requested_by: str,
        requires_explicit_approval: bool | None = None,
        subject_ref: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> Approval:
        tier = RiskTier(risk_tier)  # rejects unknown tiers
        mandatory = is_mandatory_action(action)
        if mandatory and requires_explicit_approval is False:
            raise InvalidApprovalRequest(
                "mandatory-approval action cannot be marked requires_explicit_approval=False"
            )
        explicit = mandatory or (requires_explicit_approval is True)

        requested_at = _now()
        approval = Approval(
            project_id=project_id,
            action=action,
            subject_ref=subject_ref,
            risk_tier=tier.value,
            requires_explicit_approval=explicit,
            status=Status.PENDING.value,
            requested_by=requested_by,
            requested_at=requested_at,
            deadline_at=compute_deadline(requested_at, tier, requires_explicit=explicit),
            payload=dict(payload or {}),
        )
        await self.add(approval)  # stamps tenant_id from context
        await self.session.flush()
        await self._record(approval, event="requested", actor=requested_by, from_status=None)
        return approval

    async def approve(
        self, *, approval_id: uuid.UUID, actor: str, note: str | None = None
    ) -> Approval:
        return await self._resolve_by_human(approval_id, Status.APPROVED, actor, note)

    async def reject(
        self, *, approval_id: uuid.UUID, actor: str, note: str | None = None
    ) -> Approval:
        return await self._resolve_by_human(approval_id, Status.REJECTED, actor, note)

    async def cancel(
        self, *, approval_id: uuid.UUID, actor: str, note: str | None = None
    ) -> Approval:
        return await self._resolve_by_human(approval_id, Status.CANCELLED, actor, note)

    async def expire_if_overdue(
        self, *, approval_id: uuid.UUID, now: datetime | None = None
    ) -> Approval | None:
        approval = await self.get(approval_id)
        if approval is None or approval.status != Status.PENDING.value:
            return approval
        target = auto_transition(
            RiskTier(approval.risk_tier),
            approval.requires_explicit_approval,
            approval.requested_at,
            now or _now(),
        )
        if target is None:
            return approval  # stays PENDING (explicit, high/production, or pre-deadline)
        await self._transition(approval_id, target, resolved_by=None)
        approval = await self.get(approval_id)
        await self._record(approval, event=target.value, actor="system", from_status=Status.PENDING)
        return approval

    async def get(self, approval_id: uuid.UUID) -> Approval | None:
        stmt = select(Approval).where(
            Approval.id == approval_id, Approval.tenant_id == self.context.tenant_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_pending(self):
        stmt = select(Approval).where(
            Approval.tenant_id == self.context.tenant_id,
            Approval.status == Status.PENDING.value,
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def latest_for(
        self, project_id: uuid.UUID, action: str, subject_ref: str | None = None
    ) -> Approval | None:
        """Latest approval for (project, action), optionally scoped to a subject_ref.

        ``subject_ref=None`` does not filter on subject_ref (preserves the
        action-level semantics used by ``is_blocked``); a concrete value (e.g.
        ``"tool:<name>"``) restricts the match — an action-level (NULL subject_ref)
        or different-subject approval will not be returned.
        """
        stmt = select(Approval).where(
            Approval.tenant_id == self.context.tenant_id,
            Approval.project_id == project_id,
            Approval.action == action,
        )
        if subject_ref is not None:
            stmt = stmt.where(Approval.subject_ref == subject_ref)
        stmt = stmt.order_by(Approval.requested_at.desc()).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def is_blocked(
        self, project_id: uuid.UUID, action: str, subject_ref: str | None = None
    ) -> bool:
        """Gate: is the dependent action blocked by the latest relevant approval?

        ``subject_ref=None`` keeps the action-level semantics (Slice 4); a concrete
        value (e.g. ``"run:<id>:node:<name>"``) scopes the gate to that subject — an
        action-level (NULL subject_ref) or different-subject approval will not satisfy it.
        """
        approval = await self.latest_for(project_id, action, subject_ref=subject_ref)
        if approval is None:
            return True  # no approval on record ⇒ blocked
        return _gate_is_blocked(
            Status(approval.status), requires_explicit=approval.requires_explicit_approval
        )

    # --- internals ------------------------------------------------------------

    async def _resolve_by_human(
        self, approval_id: uuid.UUID, target: Status, actor: str, note: str | None
    ) -> Approval:
        await self._transition(approval_id, target, resolved_by=actor)
        approval = await self.get(approval_id)
        await self._record(
            approval, event=target.value, actor=actor, from_status=Status.PENDING, note=note
        )
        return approval

    async def _transition(
        self, approval_id: uuid.UUID, target: Status, *, resolved_by: str | None
    ) -> None:
        # Guarded: only a PENDING row transitions (fail-closed on concurrent resolve).
        values: dict[str, Any] = {"status": target.value}
        if resolved_by is not None:
            values["resolved_by"] = resolved_by
            values["resolved_at"] = func.now()
        stmt = (
            update(Approval)
            .where(
                Approval.id == approval_id,
                Approval.tenant_id == self.context.tenant_id,
                Approval.status == Status.PENDING.value,
            )
            .values(**values)
            .returning(Approval.id)
        )
        if (await self.session.execute(stmt)).first() is None:
            raise InvalidApprovalTransition(
                f"approval {approval_id} is not PENDING (already resolved or not found)"
            )

    async def _record(
        self,
        approval: Approval,
        *,
        event: str,
        actor: str,
        from_status: Status | None,
        note: str | None = None,
    ) -> None:
        ev = ApprovalEvent(approval_id=approval.id, event_type=event, actor=actor, note=note)
        await self.add(ev)  # stamps tenant_id
        await self.session.flush()
        await audit_record(
            self.session,
            action=f"approval.{event}",
            actor=actor,
            target=f"approval:{approval.id}",
            payload={
                "approval_id": str(approval.id),
                "project_id": str(approval.project_id),
                "action": approval.action,
                "risk_tier": approval.risk_tier,
                "requires_explicit_approval": approval.requires_explicit_approval,
                "approver_provenance": approval.approver_provenance,
                "from_status": from_status.value if from_status else None,
                "to_status": approval.status,
            },
        )
