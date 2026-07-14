"""Slice-53 production pre-approval persistence and current gate evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.approval import Approval
from app.models.approval_notification import ApprovalNotification
from app.models.autonomy_policy import AutonomyPolicy
from app.models.evidence_pack import EvidencePack, EvidencePackGenerationRun
from app.models.intake_category import IntakeCategory
from app.models.production_preapproval import (
    ProductionApprovalPolicyApprover,
    ProductionApprovalPolicyVersion,
    ProductionPreapprovalAttestation,
    ProductionPreapprovalLifecycleEvent,
    ProductionPreapprovalRequest,
)
from app.models.release_candidate import ReleaseCandidate
from app.models.release_verdict import ReleaseVerdict, ReleaseVerdictRun
from app.policy.engine import Decision
from app.release.production_approval import (
    CONDITIONS_CONTRACT_VERSION,
    POLICY_CONTRACT_VERSION,
    POLICY_SOURCE_PROVENANCE,
    PREAPPROVAL_CONTRACT_VERSION,
    RecordedProductionApprovalPolicy,
    autonomy_policy_digest,
    fixed_conditions_digest,
    ordered_value_digest,
    parse_recorded_policy,
    preapproval_is_expired,
    release_binding_digest,
)
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.evidence_packs import EvidencePackRepository, EvidencePackRepositoryError
from app.repositories.intake_categories import IntakeCategoryRepository
from app.tenancy import TenantContext, TenantScopedRepository


class ProductionPreapprovalRepositoryError(ValueError):
    """Safe, code-only failure from the production pre-approval repository."""


@dataclass(frozen=True)
class CurrentPreapprovalSources:
    candidate: ReleaseCandidate | None = None
    core: EvidencePack | None = None
    core_reaudited: bool = False
    verdict: ReleaseVerdict | None = None
    policy_category: IntakeCategory | None = None
    checklist_category: IntakeCategory | None = None
    parsed_policy: RecordedProductionApprovalPolicy | None = None
    autonomy_policy: AutonomyPolicy | None = None
    autonomy_eligible: bool = False


@dataclass(frozen=True)
class ProductionPreapprovalCoverage:
    candidate_present: bool = False
    core_present: bool = False
    core_reaudited: bool = False
    verdict_present: bool = False
    verdict_gate_eligible: bool = False
    policy_present: bool = False
    policy_valid: bool = False
    approver_count: int = 0
    autonomy_policy_eligible: bool = False
    request_present: bool = False
    binding_current: bool = False
    requester_authenticated: bool = False
    notification_valid: bool = False
    request_status: str | None = None
    attestation_present: bool = False
    approver_authenticated: bool = False
    approver_in_policy: bool = False
    separation_ok: bool = False
    lifecycle_status: str | None = None
    expired: bool = False
    evidence_consistent: bool = False
    gate_eligible: bool = False
    requester_actor_type: str | None = None
    approver_actor_type: str | None = None
    policy_contract_version: str | None = None
    condition_contract_version: str | None = None
    contract_version: str | None = None
    request_id: uuid.UUID | None = None
    attestation_id: uuid.UUID | None = None

    def gate_kwargs(self) -> dict[str, object]:
        excluded = {"request_id", "attestation_id"}
        values = {
            key: value for key, value in self.__dict__.items() if key not in excluded
        }
        return {f"preapproval_{key}": value for key, value in values.items()}


class ProductionPreapprovalRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ProductionPreapprovalRequest)

    async def _latest_candidate(self, project_id: uuid.UUID) -> ReleaseCandidate | None:
        return (
            await self.session.execute(
                select(ReleaseCandidate)
                .where(
                    ReleaseCandidate.tenant_id == self.context.tenant_id,
                    ReleaseCandidate.project_id == project_id,
                    ReleaseCandidate.status == "frozen",
                )
                .order_by(ReleaseCandidate.frozen_at.desc(), ReleaseCandidate.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _latest_core(self, candidate_id: uuid.UUID) -> EvidencePack | None:
        run = (
            await self.session.execute(
                select(EvidencePackGenerationRun)
                .where(
                    EvidencePackGenerationRun.tenant_id == self.context.tenant_id,
                    EvidencePackGenerationRun.release_candidate_id == candidate_id,
                )
                .order_by(
                    EvidencePackGenerationRun.created_at.desc(),
                    EvidencePackGenerationRun.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        return (
            await self.session.execute(
                select(EvidencePack).where(
                    EvidencePack.tenant_id == self.context.tenant_id,
                    EvidencePack.generation_run_id == run.id,
                )
            )
        ).scalar_one_or_none()

    async def _latest_verdict(
        self, candidate_id: uuid.UUID, core_id: uuid.UUID
    ) -> ReleaseVerdict | None:
        run = (
            await self.session.execute(
                select(ReleaseVerdictRun)
                .where(
                    ReleaseVerdictRun.tenant_id == self.context.tenant_id,
                    ReleaseVerdictRun.release_candidate_id == candidate_id,
                )
                .order_by(ReleaseVerdictRun.created_at.desc(), ReleaseVerdictRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None or run.execution_status != "succeeded" or run.evidence_pack_id != core_id:
            return None
        return (
            await self.session.execute(
                select(ReleaseVerdict).where(
                    ReleaseVerdict.tenant_id == self.context.tenant_id,
                    ReleaseVerdict.run_id == run.id,
                )
            )
        ).scalar_one_or_none()

    async def current_sources(self, project_id: uuid.UUID) -> CurrentPreapprovalSources:
        candidate = await self._latest_candidate(project_id)
        if candidate is None:
            return CurrentPreapprovalSources()
        core = await self._latest_core(candidate.id)
        core_reaudited = False
        if core is not None and core.assembly_status == "complete":
            try:
                await EvidencePackRepository(self.session, self.context).audit_pack(core.id)
                core_reaudited = True
            except EvidencePackRepositoryError:
                core_reaudited = False
        verdict = await self._latest_verdict(candidate.id, core.id) if core is not None else None
        categories = IntakeCategoryRepository(self.session, self.context)
        policy_category = await categories.get_category(project_id, "human_approval_policy")
        checklist_category = await categories.get_category(project_id, "go_live_checklist")
        parsed = None
        if (
            policy_category is not None
            and policy_category.status == "declared"
            and checklist_category is not None
            and checklist_category.status == "declared"
        ):
            try:
                parsed = parse_recorded_policy(policy_category.data, checklist_category.data)
            except ValueError:
                parsed = None
        autonomy_repo = AutonomyPolicyRepository(self.session, self.context)
        autonomy = await autonomy_repo.get_for_project(project_id)
        autonomy_eligible = bool(
            autonomy is not None
            and await autonomy_repo.decision_for(project_id, "deploy_production")
            is Decision.NEEDS_APPROVAL
        )
        return CurrentPreapprovalSources(
            candidate=candidate,
            core=core,
            core_reaudited=core_reaudited,
            verdict=verdict,
            policy_category=policy_category,
            checklist_category=checklist_category,
            parsed_policy=parsed,
            autonomy_policy=autonomy,
            autonomy_eligible=autonomy_eligible,
        )

    async def require_current_sources(self, project_id: uuid.UUID) -> CurrentPreapprovalSources:
        sources = await self.current_sources(project_id)
        if sources.candidate is None:
            raise ProductionPreapprovalRepositoryError("no_current_frozen_release_candidate")
        if sources.core is None:
            raise ProductionPreapprovalRepositoryError("no_complete_reauditable_evidence_core")
        if not sources.core_reaudited:
            raise ProductionPreapprovalRepositoryError("release_core_reaudit_failed")
        if sources.verdict is None or not sources.verdict.gate_eligible:
            raise ProductionPreapprovalRepositoryError("no_current_gate_eligible_release_verdict")
        if sources.parsed_policy is None:
            raise ProductionPreapprovalRepositoryError("release_approval_policy_missing_or_invalid")
        if not sources.autonomy_eligible or sources.autonomy_policy is None:
            raise ProductionPreapprovalRepositoryError("a5_autonomy_policy_missing_or_ineligible")
        return sources

    async def find_request_by_idempotency(
        self, project_id: uuid.UUID, key_hash: str
    ) -> ProductionPreapprovalRequest | None:
        return (
            await self.session.execute(
                select(ProductionPreapprovalRequest).where(
                    ProductionPreapprovalRequest.tenant_id == self.context.tenant_id,
                    ProductionPreapprovalRequest.project_id == project_id,
                    ProductionPreapprovalRequest.request_idempotency_key_hash == key_hash,
                )
            )
        ).scalar_one_or_none()

    async def append_policy_snapshot(
        self,
        *,
        project_id: uuid.UUID,
        sources: CurrentPreapprovalSources,
    ) -> ProductionApprovalPolicyVersion:
        parsed = sources.parsed_policy
        if parsed is None or sources.policy_category is None or sources.checklist_category is None:
            raise ProductionPreapprovalRepositoryError("release_approval_policy_missing_or_invalid")
        row = ProductionApprovalPolicyVersion(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            human_approval_category_id=sources.policy_category.id,
            go_live_checklist_category_id=sources.checklist_category.id,
            policy_contract_version=POLICY_CONTRACT_VERSION,
            source_provenance=POLICY_SOURCE_PROVENANCE,
            policy_digest=parsed.policy_digest,
            checklist_digest=parsed.checklist_digest,
            approval_channel=parsed.approval_channel,
            production_realtime=parsed.production_realtime,
            production_nonresponse_code=parsed.production_nonresponse_code,
            governance_requirements_digest=parsed.governance_requirements_digest,
            approver_count=parsed.approver_count,
            approver_set_digest=ordered_value_digest(parsed.approver_subject_hashes),
        )
        self.session.add(row)
        await self.session.flush([row])
        for ordinal, value in enumerate(parsed.approver_subject_hashes, 1):
            self.session.add(
                ProductionApprovalPolicyApprover(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    policy_version_id=row.id,
                    ordinal=ordinal,
                    principal_subject_hash=value,
                )
            )
        await self.session.flush()
        return row

    async def append_request(
        self,
        *,
        project_id: uuid.UUID,
        request_id: uuid.UUID,
        sources: CurrentPreapprovalSources,
        policy_version: ProductionApprovalPolicyVersion,
        generic_approval: Approval,
        notification: ApprovalNotification,
        requester_subject_hash: str,
        requester_actor_type: str,
        request_idempotency_key_hash: str,
    ) -> ProductionPreapprovalRequest:
        candidate, core, verdict, autonomy = (
            sources.candidate,
            sources.core,
            sources.verdict,
            sources.autonomy_policy,
        )
        if candidate is None or core is None or verdict is None or autonomy is None:
            raise ProductionPreapprovalRepositoryError("current_release_binding_incomplete")
        autonomy_digest = autonomy_policy_digest(
            policy_id=autonomy.id,
            autonomy_level=autonomy.autonomy_level,
            overrides=autonomy.overrides,
            updated_at=autonomy.updated_at,
        )
        condition_hash = fixed_conditions_digest()
        binding = release_binding_digest(
            release_candidate_id=str(candidate.id),
            evidence_pack_id=str(core.id),
            release_verdict_id=str(verdict.id),
            core_content_hash=core.core_content_hash,
            issue_binding_digest=core.issue_binding_digest,
            source_set_digest=core.source_set_digest,
            traceability_digest=core.traceability_digest,
            verdict_input_digest=verdict.input_digest,
            verdict_contract_hash=verdict.verdict_contract_hash,
            autonomy_policy_digest=autonomy_digest,
            policy_digest=policy_version.policy_digest,
            checklist_digest=policy_version.checklist_digest,
            condition_contract_hash=condition_hash,
        )
        row = ProductionPreapprovalRequest(
            id=request_id,
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_candidate_id=candidate.id,
            evidence_pack_id=core.id,
            release_verdict_id=verdict.id,
            policy_version_id=policy_version.id,
            autonomy_policy_id=autonomy.id,
            generic_approval_id=generic_approval.id,
            approval_notification_id=notification.id,
            preapproval_contract_version=PREAPPROVAL_CONTRACT_VERSION,
            condition_contract_version=CONDITIONS_CONTRACT_VERSION,
            condition_contract_hash=condition_hash,
            release_binding_digest=binding,
            core_content_hash=core.core_content_hash,
            issue_binding_digest=core.issue_binding_digest,
            source_set_digest=core.source_set_digest,
            traceability_digest=core.traceability_digest,
            verdict_input_digest=verdict.input_digest,
            verdict_contract_hash=verdict.verdict_contract_hash,
            autonomy_policy_digest=autonomy_digest,
            requester_subject_hash=requester_subject_hash,
            requester_actor_type=requester_actor_type,
            requester_provenance="request_authenticated",
            request_idempotency_key_hash=request_idempotency_key_hash,
            requested_at=generic_approval.requested_at,
        )
        self.session.add(row)
        await self.session.flush([row])
        return row

    async def get_request(
        self, project_id: uuid.UUID, request_id: uuid.UUID
    ) -> ProductionPreapprovalRequest | None:
        return (
            await self.session.execute(
                select(ProductionPreapprovalRequest).where(
                    ProductionPreapprovalRequest.tenant_id == self.context.tenant_id,
                    ProductionPreapprovalRequest.project_id == project_id,
                    ProductionPreapprovalRequest.id == request_id,
                )
            )
        ).scalar_one_or_none()

    async def latest_request(self, project_id: uuid.UUID) -> ProductionPreapprovalRequest | None:
        return (
            await self.session.execute(
                select(ProductionPreapprovalRequest)
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

    async def policy_has_member(self, policy_version_id: uuid.UUID, member_hash: str) -> bool:
        return (
            await self.session.execute(
                select(ProductionApprovalPolicyApprover.id).where(
                    ProductionApprovalPolicyApprover.tenant_id == self.context.tenant_id,
                    ProductionApprovalPolicyApprover.policy_version_id == policy_version_id,
                    ProductionApprovalPolicyApprover.principal_subject_hash == member_hash,
                )
            )
        ).scalar_one_or_none() is not None

    async def append_attestation(
        self,
        *,
        request: ProductionPreapprovalRequest,
        approval: Approval,
        approver_subject_hash: str,
        approver_actor_type: str,
        resolution_idempotency_key_hash: str,
        expires_at: datetime,
    ) -> ProductionPreapprovalAttestation:
        if approval.resolved_at is None:
            raise ProductionPreapprovalRepositoryError("approved_resolution_timestamp_missing")
        row = ProductionPreapprovalAttestation(
            tenant_id=self.context.tenant_id,
            project_id=request.project_id,
            request_id=request.id,
            generic_approval_id=request.generic_approval_id,
            policy_version_id=request.policy_version_id,
            release_candidate_id=request.release_candidate_id,
            evidence_pack_id=request.evidence_pack_id,
            release_verdict_id=request.release_verdict_id,
            requester_subject_hash=request.requester_subject_hash,
            requester_actor_type=request.requester_actor_type,
            requester_provenance=request.requester_provenance,
            approver_subject_hash=approver_subject_hash,
            approver_actor_type=approver_actor_type,
            approver_provenance="request_authenticated",
            resolution_idempotency_key_hash=resolution_idempotency_key_hash,
            approved_at=approval.resolved_at,
            valid_from=approval.resolved_at,
            expires_at=expires_at,
            policy_membership_ok=True,
        )
        self.session.add(row)
        await self.session.flush([row])
        return row

    async def append_lifecycle_event(
        self,
        *,
        attestation: ProductionPreapprovalAttestation,
        previous_event_id: uuid.UUID | None,
        event_type: str,
        actor_subject_hash: str,
        actor_type: str,
        reason_code: str,
        idempotency_key_hash: str,
    ) -> ProductionPreapprovalLifecycleEvent:
        row = ProductionPreapprovalLifecycleEvent(
            tenant_id=self.context.tenant_id,
            project_id=attestation.project_id,
            attestation_id=attestation.id,
            previous_event_id=previous_event_id,
            event_type=event_type,
            actor_subject_hash=actor_subject_hash,
            actor_type=actor_type,
            actor_provenance="request_authenticated",
            reason_code=reason_code,
            idempotency_key_hash=idempotency_key_hash,
        )
        self.session.add(row)
        await self.session.flush([row])
        return row

    async def get_attestation(
        self, project_id: uuid.UUID, attestation_id: uuid.UUID
    ) -> ProductionPreapprovalAttestation | None:
        return (
            await self.session.execute(
                select(ProductionPreapprovalAttestation).where(
                    ProductionPreapprovalAttestation.tenant_id == self.context.tenant_id,
                    ProductionPreapprovalAttestation.project_id == project_id,
                    ProductionPreapprovalAttestation.id == attestation_id,
                )
            )
        ).scalar_one_or_none()

    async def _attestation_for_request(
        self, request_id: uuid.UUID
    ) -> ProductionPreapprovalAttestation | None:
        return (
            await self.session.execute(
                select(ProductionPreapprovalAttestation).where(
                    ProductionPreapprovalAttestation.tenant_id == self.context.tenant_id,
                    ProductionPreapprovalAttestation.request_id == request_id,
                )
            )
        ).scalar_one_or_none()

    async def latest_lifecycle(
        self, attestation_id: uuid.UUID
    ) -> ProductionPreapprovalLifecycleEvent | None:
        return (
            await self.session.execute(
                select(ProductionPreapprovalLifecycleEvent)
                .where(
                    ProductionPreapprovalLifecycleEvent.tenant_id == self.context.tenant_id,
                    ProductionPreapprovalLifecycleEvent.attestation_id == attestation_id,
                )
                .order_by(
                    ProductionPreapprovalLifecycleEvent.created_at.desc(),
                    ProductionPreapprovalLifecycleEvent.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def coverage_for_project(
        self, project_id: uuid.UUID, *, as_of: datetime | None = None
    ) -> ProductionPreapprovalCoverage:
        now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        sources = await self.current_sources(project_id)
        base = {
            "candidate_present": sources.candidate is not None,
            "core_present": sources.core is not None,
            "core_reaudited": sources.core_reaudited,
            "verdict_present": sources.verdict is not None,
            "verdict_gate_eligible": bool(sources.verdict and sources.verdict.gate_eligible),
            "policy_present": bool(sources.policy_category and sources.checklist_category),
            "policy_valid": sources.parsed_policy is not None,
            "approver_count": (
                sources.parsed_policy.approver_count if sources.parsed_policy is not None else 0
            ),
            "autonomy_policy_eligible": sources.autonomy_eligible,
            "policy_contract_version": (
                POLICY_CONTRACT_VERSION if sources.parsed_policy is not None else None
            ),
            "condition_contract_version": CONDITIONS_CONTRACT_VERSION,
            "contract_version": PREAPPROVAL_CONTRACT_VERSION,
        }
        request = await self.latest_request(project_id)
        if request is None:
            return ProductionPreapprovalCoverage(**base)
        approval = (
            await self.session.execute(
                select(Approval).where(
                    Approval.tenant_id == self.context.tenant_id,
                    Approval.id == request.generic_approval_id,
                )
            )
        ).scalar_one_or_none()
        notification = (
            await self.session.execute(
                select(ApprovalNotification).where(
                    ApprovalNotification.tenant_id == self.context.tenant_id,
                    ApprovalNotification.id == request.approval_notification_id,
                )
            )
        ).scalar_one_or_none()
        attestation = await self._attestation_for_request(request.id)
        lifecycle = await self.latest_lifecycle(attestation.id) if attestation is not None else None
        parsed = sources.parsed_policy
        autonomy = sources.autonomy_policy
        expected_binding = None
        if (
            sources.candidate
            and sources.core
            and sources.verdict
            and parsed
            and autonomy
        ):
            autonomy_digest = autonomy_policy_digest(
                policy_id=autonomy.id,
                autonomy_level=autonomy.autonomy_level,
                overrides=autonomy.overrides,
                updated_at=autonomy.updated_at,
            )
            expected_binding = release_binding_digest(
                release_candidate_id=str(sources.candidate.id),
                evidence_pack_id=str(sources.core.id),
                release_verdict_id=str(sources.verdict.id),
                core_content_hash=sources.core.core_content_hash,
                issue_binding_digest=sources.core.issue_binding_digest,
                source_set_digest=sources.core.source_set_digest,
                traceability_digest=sources.core.traceability_digest,
                verdict_input_digest=sources.verdict.input_digest,
                verdict_contract_hash=sources.verdict.verdict_contract_hash,
                autonomy_policy_digest=autonomy_digest,
                policy_digest=parsed.policy_digest,
                checklist_digest=parsed.checklist_digest,
                condition_contract_hash=fixed_conditions_digest(),
            )
        binding_current = bool(
            expected_binding
            and request.release_binding_digest == expected_binding
            and sources.candidate
            and request.release_candidate_id == sources.candidate.id
            and sources.core
            and request.evidence_pack_id == sources.core.id
            and sources.verdict
            and request.release_verdict_id == sources.verdict.id
            and autonomy
            and request.autonomy_policy_id == autonomy.id
        )
        approver_hash = (
            attestation.approver_subject_hash
            if attestation is not None
            else approval.resolved_by if approval is not None else None
        )
        approver_authenticated = bool(
            approval
            and approval.status == "approved"
            and approval.approver_provenance == "request_authenticated"
            and approver_hash
        )
        approver_in_policy = bool(
            approver_hash
            and await self.policy_has_member(request.policy_version_id, approver_hash)
        )
        separation = bool(
            approver_hash and request.requester_subject_hash != approver_hash
        )
        notification_valid = bool(
            notification
            and notification.approval_id == request.generic_approval_id
            and notification.risk_tier == "production"
            and notification.routing_mode == "realtime"
            and notification.channel == "dashboard"
            and notification.status == "delivered"
        )
        expired = bool(attestation and preapproval_is_expired(attestation.expires_at, now))
        consistent = bool(
            approval
            and approval.action == "deploy_production"
            and approval.risk_tier == "production"
            and approval.requires_explicit_approval
            and approval.requested_by == request.requester_subject_hash
            and approval.requested_by_provenance == "request_authenticated"
            and notification_valid
            and attestation
            and attestation.generic_approval_id == approval.id
            and attestation.policy_version_id == request.policy_version_id
            and attestation.release_candidate_id == request.release_candidate_id
            and attestation.evidence_pack_id == request.evidence_pack_id
            and attestation.release_verdict_id == request.release_verdict_id
            and attestation.identity_separation_ok
            and attestation.policy_membership_ok
            and attestation.gate_eligible_at_creation
            and lifecycle
        )
        gate_eligible = bool(
            consistent
            and binding_current
            and lifecycle
            and lifecycle.event_type == "approved_anchor"
            and not expired
            and approval
            and approval.status == "approved"
        )
        return ProductionPreapprovalCoverage(
            **base,
            request_present=True,
            binding_current=binding_current,
            requester_authenticated=request.requester_provenance == "request_authenticated",
            notification_valid=notification_valid,
            request_status=approval.status if approval is not None else None,
            attestation_present=attestation is not None,
            approver_authenticated=approver_authenticated,
            approver_in_policy=approver_in_policy,
            separation_ok=separation,
            lifecycle_status=lifecycle.event_type if lifecycle is not None else None,
            expired=expired,
            evidence_consistent=consistent,
            gate_eligible=gate_eligible,
            requester_actor_type=request.requester_actor_type,
            approver_actor_type=(attestation.approver_actor_type if attestation else None),
            request_id=request.id,
            attestation_id=attestation.id if attestation else None,
        )

    async def audit_event(
        self,
        *,
        action: str,
        project_id: uuid.UUID,
        target_id: uuid.UUID,
        actor_code: str,
        status_code: str,
        request_id: uuid.UUID | None = None,
    ) -> None:
        await audit_record(
            self.session,
            action=action,
            actor=actor_code,
            target=str(target_id),
            payload={
                "project_id": str(project_id),
                "request_id": str(request_id) if request_id is not None else None,
                "status_code": status_code,
                "identity_provenance": "request_authenticated",
                "identity_claim": "key_custody_under_recorded_policy",
                "preapproval_contract_version": PREAPPROVAL_CONTRACT_VERSION,
            },
        )


__all__ = [
    "CurrentPreapprovalSources",
    "ProductionPreapprovalCoverage",
    "ProductionPreapprovalRepository",
    "ProductionPreapprovalRepositoryError",
]
