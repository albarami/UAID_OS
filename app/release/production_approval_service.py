"""Authoritative Slice-53 request/resolve/revoke workflow.

All identity comes from ``TenantContext.actor``.  Persisted actor values are one-way subject digests;
audit actors are bounded role codes.  This service creates evidence only and never invokes a
deployment, broker, connector, or control-loop transition.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.approvals.channels.adapter import DashboardChannel
from app.approvals.channels.service import request_and_notify_approval
from app.approvals.states import InvalidApprovalRequest, InvalidApprovalTransition
from app.models.approval import Approval
from app.models.production_preapproval import ProductionPreapprovalAttestation
from app.release.production_approval import (
    actor_evidence,
    canonical_digest,
    idempotency_digest,
    subject_digest,
)
from app.repositories.approvals import ApprovalRepository
from app.repositories.production_preapprovals import (
    ProductionPreapprovalRepository,
    ProductionPreapprovalRepositoryError,
)
from app.tenancy import TenantContext


class ProductionPreapprovalNotFound(LookupError):
    """Safe not-found result; callers must not distinguish cross-tenant from absent."""


class ProductionPreapprovalConflict(ValueError):
    """Safe fail-closed workflow conflict."""


@dataclass(frozen=True)
class ProductionPreapprovalResult:
    request_id: uuid.UUID
    attestation_id: uuid.UUID | None
    status: str
    reason_code: str


class ProductionApprovalService:
    def __init__(self, session: AsyncSession, context: TenantContext):
        self.session = session
        self.context = context
        self.repo = ProductionPreapprovalRepository(session, context)

    def _actor(self):
        if self.context.actor is None:
            raise ProductionPreapprovalConflict("request_authentication_required")
        return self.context.actor

    async def request(
        self, *, project_id: uuid.UUID, idempotency_key: str
    ) -> ProductionPreapprovalResult:
        actor = self._actor()
        key_hash = idempotency_digest(idempotency_key)
        existing = await self.repo.find_request_by_idempotency(project_id, key_hash)
        if existing is not None:
            approval = await ApprovalRepository(self.session, self.context).get(
                existing.generic_approval_id
            )
            return ProductionPreapprovalResult(
                existing.id,
                None,
                approval.status if approval is not None else "inconsistent",
                "idempotent_replay",
            )
        sources = await self.repo.require_current_sources(project_id)
        policy = await self.repo.append_policy_snapshot(project_id=project_id, sources=sources)
        request_id = uuid.uuid4()
        requester_hash = subject_digest(actor.subject)
        approval, notification = await request_and_notify_approval(
            self.session,
            self.context,
            project_id=project_id,
            action="deploy_production",
            risk_tier="production",
            requested_by="request_authenticated_requester",
            actor="request_authenticated_requester",
            channel=DashboardChannel(),
            requires_explicit_approval=True,
            subject_ref=f"production_preapproval:{request_id}",
            payload={},
            identity_storage_subject=requester_hash,
            audit_actor="request_authenticated_requester",
        )
        request = await self.repo.append_request(
            project_id=project_id,
            request_id=request_id,
            sources=sources,
            policy_version=policy,
            generic_approval=approval,
            notification=notification,
            requester_subject_hash=requester_hash,
            requester_actor_type=actor.actor_type,
            request_idempotency_key_hash=key_hash,
        )
        await self.repo.audit_event(
            action="production_preapproval.requested",
            project_id=project_id,
            target_id=request.id,
            actor_code="request_authenticated_requester",
            status_code="pending",
            request_id=request.id,
        )
        return ProductionPreapprovalResult(request.id, None, "pending", "request_recorded")

    async def _request_and_approval(
        self, project_id: uuid.UUID, request_id: uuid.UUID
    ) -> tuple[object, Approval]:
        request = await self.repo.get_request(project_id, request_id)
        if request is None:
            raise ProductionPreapprovalNotFound("production_preapproval_not_found")
        approval = await ApprovalRepository(self.session, self.context).get(
            request.generic_approval_id
        )
        if approval is None:
            raise ProductionPreapprovalConflict("production_preapproval_inconsistent")
        return request, approval

    async def _require_current_request(self, project_id: uuid.UUID, request_id: uuid.UUID) -> None:
        coverage = await self.repo.coverage_for_project(project_id)
        if coverage.request_id != request_id or not coverage.binding_current:
            raise ProductionPreapprovalConflict("production_preapproval_not_current")

    async def _require_policy_approver(
        self, request, *, require_separation: bool = True
    ) -> str:
        actor = self._actor()
        actor_hash = subject_digest(actor.subject)
        if actor.actor_type != "human" or not await self.repo.policy_has_member(
            request.policy_version_id, actor_hash
        ):
            raise ProductionPreapprovalConflict("approver_not_in_recorded_policy")
        evidence = actor_evidence(
            requester=None,
            approver=actor,
            member_subject_hashes=(actor_hash,),
        )
        if not evidence.approver_authenticated:
            raise ProductionPreapprovalConflict("approver_not_request_authenticated")
        if require_separation and request.requester_subject_hash == actor_hash:
            raise ProductionPreapprovalConflict("separation_of_duties_failed")
        return actor_hash

    async def approve(
        self, *, project_id: uuid.UUID, request_id: uuid.UUID, idempotency_key: str
    ) -> ProductionPreapprovalResult:
        request, approval = await self._request_and_approval(project_id, request_id)
        existing_attestation = await self.repo._attestation_for_request(request.id)
        if approval.status == "approved" and existing_attestation is not None:
            return ProductionPreapprovalResult(
                request.id, existing_attestation.id, "approved", "idempotent_replay"
            )
        if approval.status != "pending":
            raise ProductionPreapprovalConflict("production_preapproval_already_resolved")
        await self._require_current_request(project_id, request_id)
        actor = self._actor()
        approver_hash = await self._require_policy_approver(request)
        try:
            approval = await ApprovalRepository(self.session, self.context).approve(
                approval_id=approval.id,
                actor="request_authenticated_approver",
                identity_storage_subject=approver_hash,
                audit_actor="request_authenticated_approver",
            )
        except (InvalidApprovalRequest, InvalidApprovalTransition) as exc:
            raise ProductionPreapprovalConflict("production_preapproval_resolution_conflict") from exc
        await self.session.refresh(approval)
        if approval.resolved_at is None:
            raise ProductionPreapprovalConflict("production_preapproval_resolution_inconsistent")
        resolution_hash = idempotency_digest(idempotency_key)
        attestation = await self.repo.append_attestation(
            request=request,
            approval=approval,
            approver_subject_hash=approver_hash,
            approver_actor_type=actor.actor_type,
            resolution_idempotency_key_hash=resolution_hash,
            expires_at=approval.resolved_at + timedelta(hours=24),
        )
        await self.repo.append_lifecycle_event(
            attestation=attestation,
            previous_event_id=None,
            event_type="approved_anchor",
            actor_subject_hash=approver_hash,
            actor_type=actor.actor_type,
            reason_code="request_authenticated_preapproval_recorded",
            idempotency_key_hash=canonical_digest(
                {"event": "approved_anchor", "resolution_key_hash": resolution_hash}
            ),
        )
        await self._supersede_prior(
            project_id=project_id,
            current_attestation=attestation,
            actor_subject_hash=approver_hash,
            actor_type=actor.actor_type,
            idempotency_key_hash=resolution_hash,
        )
        await self.repo.audit_event(
            action="production_preapproval.approved",
            project_id=project_id,
            target_id=attestation.id,
            actor_code="request_authenticated_approver",
            status_code="approved_key_custody_under_recorded_policy",
            request_id=request.id,
        )
        return ProductionPreapprovalResult(
            request.id, attestation.id, "approved", "request_authenticated_preapproval_recorded"
        )

    async def _supersede_prior(
        self,
        *,
        project_id: uuid.UUID,
        current_attestation: ProductionPreapprovalAttestation,
        actor_subject_hash: str,
        actor_type: str,
        idempotency_key_hash: str,
    ) -> None:
        prior = (
            await self.session.execute(
                select(ProductionPreapprovalAttestation)
                .where(
                    ProductionPreapprovalAttestation.tenant_id == self.context.tenant_id,
                    ProductionPreapprovalAttestation.project_id == project_id,
                    ProductionPreapprovalAttestation.id != current_attestation.id,
                )
                .order_by(
                    ProductionPreapprovalAttestation.created_at.desc(),
                    ProductionPreapprovalAttestation.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if prior is None:
            return
        head = await self.repo.latest_lifecycle(prior.id)
        if head is None or head.event_type != "approved_anchor":
            return
        await self.repo.append_lifecycle_event(
            attestation=prior,
            previous_event_id=head.id,
            event_type="superseded",
            actor_subject_hash=actor_subject_hash,
            actor_type=actor_type,
            reason_code="newer_current_binding_preapproval_approved",
            idempotency_key_hash=canonical_digest(
                {
                    "event": "superseded",
                    "prior_attestation": str(prior.id),
                    "resolution_key_hash": idempotency_key_hash,
                }
            ),
        )

    async def reject(
        self, *, project_id: uuid.UUID, request_id: uuid.UUID, idempotency_key: str
    ) -> ProductionPreapprovalResult:
        request, approval = await self._request_and_approval(project_id, request_id)
        if approval.status == "rejected":
            return ProductionPreapprovalResult(request.id, None, "rejected", "idempotent_replay")
        if approval.status != "pending":
            raise ProductionPreapprovalConflict("production_preapproval_already_resolved")
        await self._require_current_request(project_id, request_id)
        approver_hash = await self._require_policy_approver(request)
        idempotency_digest(idempotency_key)
        await ApprovalRepository(self.session, self.context).reject(
            approval_id=approval.id,
            actor="request_authenticated_approver",
            identity_storage_subject=approver_hash,
            audit_actor="request_authenticated_approver",
        )
        await self.repo.audit_event(
            action="production_preapproval.rejected",
            project_id=project_id,
            target_id=request.id,
            actor_code="request_authenticated_approver",
            status_code="rejected",
            request_id=request.id,
        )
        return ProductionPreapprovalResult(request.id, None, "rejected", "request_rejected")

    async def cancel(
        self, *, project_id: uuid.UUID, request_id: uuid.UUID, idempotency_key: str
    ) -> ProductionPreapprovalResult:
        request, approval = await self._request_and_approval(project_id, request_id)
        actor = self._actor()
        actor_hash = subject_digest(actor.subject)
        if actor_hash != request.requester_subject_hash:
            raise ProductionPreapprovalConflict("only_requester_may_cancel")
        if approval.status == "cancelled":
            return ProductionPreapprovalResult(request.id, None, "cancelled", "idempotent_replay")
        if approval.status != "pending":
            raise ProductionPreapprovalConflict("production_preapproval_already_resolved")
        idempotency_digest(idempotency_key)
        await ApprovalRepository(self.session, self.context).cancel(
            approval_id=approval.id,
            actor="request_authenticated_requester",
            identity_storage_subject=actor_hash,
            audit_actor="request_authenticated_requester",
        )
        await self.repo.audit_event(
            action="production_preapproval.cancelled",
            project_id=project_id,
            target_id=request.id,
            actor_code="request_authenticated_requester",
            status_code="cancelled",
            request_id=request.id,
        )
        return ProductionPreapprovalResult(request.id, None, "cancelled", "request_cancelled")

    async def revoke(
        self, *, project_id: uuid.UUID, attestation_id: uuid.UUID, idempotency_key: str
    ) -> ProductionPreapprovalResult:
        attestation = await self.repo.get_attestation(project_id, attestation_id)
        if attestation is None:
            raise ProductionPreapprovalNotFound("production_preapproval_not_found")
        request = await self.repo.get_request(project_id, attestation.request_id)
        if request is None:
            raise ProductionPreapprovalConflict("production_preapproval_inconsistent")
        actor = self._actor()
        actor_hash = await self._require_policy_approver(
            request, require_separation=False
        )
        head = await self.repo.latest_lifecycle(attestation.id)
        if head is not None and head.event_type == "revoked":
            return ProductionPreapprovalResult(request.id, attestation.id, "revoked", "idempotent_replay")
        if head is None or head.event_type != "approved_anchor":
            raise ProductionPreapprovalConflict("production_preapproval_not_revocable")
        event = await self.repo.append_lifecycle_event(
            attestation=attestation,
            previous_event_id=head.id,
            event_type="revoked",
            actor_subject_hash=actor_hash,
            actor_type=actor.actor_type,
            reason_code="request_authenticated_preapproval_revoked",
            idempotency_key_hash=idempotency_digest(idempotency_key),
        )
        await self.repo.audit_event(
            action="production_preapproval.revoked",
            project_id=project_id,
            target_id=event.id,
            actor_code="request_authenticated_approver",
            status_code="revoked",
            request_id=request.id,
        )
        return ProductionPreapprovalResult(request.id, attestation.id, "revoked", "revoked")

    async def current(self, *, project_id: uuid.UUID) -> ProductionPreapprovalResult:
        coverage = await self.repo.coverage_for_project(project_id)
        if coverage.request_id is None:
            raise ProductionPreapprovalNotFound("production_preapproval_not_found")
        status = coverage.request_status or "inconsistent"
        if coverage.lifecycle_status in {"revoked", "superseded"}:
            status = coverage.lifecycle_status
        elif coverage.expired:
            status = "expired"
        return ProductionPreapprovalResult(
            coverage.request_id,
            coverage.attestation_id,
            status,
            "current" if coverage.gate_eligible else "not_gate_eligible",
        )


__all__ = [
    "ProductionApprovalService",
    "ProductionPreapprovalConflict",
    "ProductionPreapprovalNotFound",
    "ProductionPreapprovalResult",
    "ProductionPreapprovalRepositoryError",
]
