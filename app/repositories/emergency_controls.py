"""Slice-54 emergency-control persistence, currentness, and runtime boundary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.autonomy_policy import AutonomyPolicy
from app.models.emergency_control import (
    EmergencyControlAuthorityMember,
    EmergencyControlBinding,
    EmergencyRollbackAuthorization,
    EmergencyStopEvent,
    EmergencyStopRunEffect,
)
from app.models.intake_category import IntakeCategory
from app.models.production_preapproval import ProductionApprovalPolicyApprover
from app.models.project import Project
from app.models.project_run import ProjectRun
from app.models.rollback_verification import RollbackVerificationRun
from app.policy.engine import Decision
from app.release.emergency_stop import (
    AUTHORITY_PROVENANCE,
    EMERGENCY_CONTROL_CONTRACT_VERSION,
    EMERGENCY_STOP_CONTRACT_VERSION,
    POLICY_PROVENANCE,
    ROLLBACK_AUTHORITY_CONTRACT_VERSION,
    EmergencyControlCoverage,
    authority_set_digest,
    release_rollback_binding_digest,
)
from app.release.production_approval import (
    autonomy_policy_digest,
    canonical_digest,
    parse_recorded_policy,
)
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.production_preapprovals import (
    CurrentPreapprovalSources,
    ProductionPreapprovalRepository,
)
from app.repositories.rollback_verifications import RollbackVerificationRepository
from app.repositories.runs import RunRepository
from app.tenancy import TenantContext, TenantScopedRepository


class EmergencyControlRepositoryError(ValueError):
    """Safe, code-only repository failure."""


class EmergencyStopActive(RuntimeError):
    """Raised at an execution boundary while the project latch is active."""


@dataclass(frozen=True)
class CurrentAuthoritySources:
    policy_category: IntakeCategory | None = None
    checklist_category: IntakeCategory | None = None
    parsed_policy: object | None = None
    autonomy_policy: AutonomyPolicy | None = None
    autonomy_eligible: bool = False


@dataclass(frozen=True)
class EmergencyControlStatus:
    binding_id: uuid.UUID | None
    event_id: uuid.UUID | None
    state: str
    rollback_authority_bound: bool
    gate_eligible: bool
    reason_code: str


async def lock_project_row(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> Project:
    project = (
        await session.execute(
            select(Project)
            .where(
                Project.id == project_id,
                Project.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if project is None:
        raise EmergencyControlRepositoryError("emergency_control_unavailable")
    return project


async def latest_stop_event(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> EmergencyStopEvent | None:
    return (
        await session.execute(
            select(EmergencyStopEvent)
            .where(
                EmergencyStopEvent.tenant_id == context.tenant_id,
                EmergencyStopEvent.project_id == project_id,
            )
            .order_by(EmergencyStopEvent.created_at.desc(), EmergencyStopEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def assert_project_not_stopped(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> None:
    """Serialize a start/resume with latch mutation and fail while active."""

    await lock_project_row(session, context, project_id)
    head = await latest_stop_event(session, context, project_id)
    if head is not None and head.state_after == "active":
        raise EmergencyStopActive("project emergency stop is active")


class EmergencyControlRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, EmergencyControlBinding)

    async def current_authority_sources(self, project_id: uuid.UUID) -> CurrentAuthoritySources:
        categories = IntakeCategoryRepository(self.session, self.context)
        policy = await categories.get_category(project_id, "human_approval_policy")
        checklist = await categories.get_category(project_id, "go_live_checklist")
        parsed = None
        if (
            policy is not None
            and policy.status == "declared"
            and checklist is not None
            and checklist.status == "declared"
        ):
            try:
                parsed = parse_recorded_policy(policy.data, checklist.data)
            except ValueError:
                parsed = None
        autonomy_repo = AutonomyPolicyRepository(self.session, self.context)
        autonomy = await autonomy_repo.get_for_project(project_id)
        autonomy_eligible = bool(
            autonomy is not None
            and await autonomy_repo.decision_for(project_id, "deploy_production")
            is Decision.NEEDS_APPROVAL
        )
        return CurrentAuthoritySources(
            policy_category=policy,
            checklist_category=checklist,
            parsed_policy=parsed,
            autonomy_policy=autonomy,
            autonomy_eligible=autonomy_eligible,
        )

    async def latest_binding(self, project_id: uuid.UUID) -> EmergencyControlBinding | None:
        return (
            await self.session.execute(
                select(EmergencyControlBinding)
                .where(
                    EmergencyControlBinding.tenant_id == self.context.tenant_id,
                    EmergencyControlBinding.project_id == project_id,
                )
                .order_by(
                    EmergencyControlBinding.created_at.desc(),
                    EmergencyControlBinding.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _members(self, binding_id: uuid.UUID) -> tuple[EmergencyControlAuthorityMember, ...]:
        rows = (
            (
                await self.session.execute(
                    select(EmergencyControlAuthorityMember)
                    .where(
                        EmergencyControlAuthorityMember.tenant_id == self.context.tenant_id,
                        EmergencyControlAuthorityMember.binding_id == binding_id,
                    )
                    .order_by(EmergencyControlAuthorityMember.ordinal)
                )
            )
            .scalars()
            .all()
        )
        return tuple(rows)

    async def member_for_actor(
        self, binding: EmergencyControlBinding, actor_subject_hash: str
    ) -> EmergencyControlAuthorityMember | None:
        return (
            await self.session.execute(
                select(EmergencyControlAuthorityMember).where(
                    EmergencyControlAuthorityMember.tenant_id == self.context.tenant_id,
                    EmergencyControlAuthorityMember.project_id == binding.project_id,
                    EmergencyControlAuthorityMember.binding_id == binding.id,
                    EmergencyControlAuthorityMember.principal_subject_hash == actor_subject_hash,
                )
            )
        ).scalar_one_or_none()

    async def _assert_current_member(
        self,
        binding: EmergencyControlBinding,
        member: EmergencyControlAuthorityMember,
    ) -> None:
        sources = await self.current_authority_sources(binding.project_id)
        parsed = sources.parsed_policy
        autonomy = sources.autonomy_policy
        autonomy_current = bool(
            autonomy is not None
            and binding.autonomy_policy_id == autonomy.id
            and binding.autonomy_policy_digest
            == autonomy_policy_digest(
                policy_id=autonomy.id,
                autonomy_level=autonomy.autonomy_level,
                overrides=autonomy.overrides,
                updated_at=autonomy.updated_at,
            )
        )
        if (
            parsed is None
            or not autonomy_current
            or not sources.autonomy_eligible
            or binding.policy_digest != parsed.policy_digest
            or binding.checklist_digest != parsed.checklist_digest
            or member.principal_subject_hash not in parsed.approver_subject_hashes
        ):
            raise EmergencyControlRepositoryError("emergency_authority_membership_unavailable")

    async def find_binding_by_idempotency(
        self, project_id: uuid.UUID, key_hash: str
    ) -> EmergencyControlBinding | None:
        return (
            await self.session.execute(
                select(EmergencyControlBinding).where(
                    EmergencyControlBinding.tenant_id == self.context.tenant_id,
                    EmergencyControlBinding.project_id == project_id,
                    EmergencyControlBinding.idempotency_key_hash == key_hash,
                )
            )
        ).scalar_one_or_none()

    async def _current_release_binding(
        self, project_id: uuid.UUID
    ) -> tuple[object | None, object | None, RollbackVerificationRun | None, str | None]:
        preapproval = ProductionPreapprovalRepository(self.session, self.context)
        sources = await preapproval.current_sources(project_id)
        if sources.candidate is None or sources.core is None or not sources.core_reaudited:
            return None, None, None, None
        coverage = await RollbackVerificationRepository(
            self.session, self.context
        ).coverage_for_project(project_id)
        if not (
            coverage.run_present
            and not coverage.attempt_failed
            and coverage.binding_current
            and coverage.phase_coverage_complete
            and coverage.evidence_consistent
            and coverage.drill_passed
            and coverage.gate_eligible
            and coverage.execution_observation == "connector_observed_ci"
        ):
            return sources.candidate, sources.core, None, None
        run = (
            await self.session.execute(
                select(RollbackVerificationRun)
                .where(
                    RollbackVerificationRun.tenant_id == self.context.tenant_id,
                    RollbackVerificationRun.project_id == project_id,
                    RollbackVerificationRun.release_candidate_id == sources.candidate.id,
                    RollbackVerificationRun.evidence_pack_id == sources.core.id,
                    RollbackVerificationRun.attempt_status == "succeeded",
                    RollbackVerificationRun.gate_eligible.is_(True),
                )
                .order_by(
                    RollbackVerificationRun.created_at.desc(),
                    RollbackVerificationRun.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None or run.phase_digest is None:
            return sources.candidate, sources.core, None, None
        digest = release_rollback_binding_digest(
            release_candidate_id=str(sources.candidate.id),
            evidence_pack_id=str(sources.core.id),
            rollback_verification_run_id=str(run.id),
            core_content_hash=sources.core.core_content_hash,
            rollback_artifact_scope_digest=run.artifact_scope_digest,
            rollback_phase_digest=run.phase_digest,
        )
        return sources.candidate, sources.core, run, digest

    async def append_binding(
        self,
        *,
        project_id: uuid.UUID,
        actor_subject_hash: str,
        actor_type: str,
        idempotency_key_hash: str,
    ) -> EmergencyControlBinding:
        sources = await self.current_authority_sources(project_id)
        parsed = sources.parsed_policy
        autonomy = sources.autonomy_policy
        if parsed is None or autonomy is None or not sources.autonomy_eligible:
            raise EmergencyControlRepositoryError("emergency_authority_policy_unavailable")
        if parsed.approver_count < 2 or actor_subject_hash not in parsed.approver_subject_hashes:
            raise EmergencyControlRepositoryError("emergency_authority_membership_unavailable")
        pa_sources = CurrentPreapprovalSources(
            policy_category=sources.policy_category,
            checklist_category=sources.checklist_category,
            parsed_policy=parsed,
            autonomy_policy=autonomy,
            autonomy_eligible=True,
        )
        pa_repo = ProductionPreapprovalRepository(self.session, self.context)
        policy_version = await pa_repo.append_policy_snapshot(
            project_id=project_id, sources=pa_sources
        )
        policy_members = (
            (
                await self.session.execute(
                    select(ProductionApprovalPolicyApprover)
                    .where(
                        ProductionApprovalPolicyApprover.tenant_id == self.context.tenant_id,
                        ProductionApprovalPolicyApprover.policy_version_id == policy_version.id,
                    )
                    .order_by(ProductionApprovalPolicyApprover.ordinal)
                )
            )
            .scalars()
            .all()
        )
        candidate, core, rollback_run, release_digest = await self._current_release_binding(
            project_id
        )
        autonomy_digest = autonomy_policy_digest(
            policy_id=autonomy.id,
            autonomy_level=autonomy.autonomy_level,
            overrides=autonomy.overrides,
            updated_at=autonomy.updated_at,
        )
        row = EmergencyControlBinding(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            policy_version_id=policy_version.id,
            autonomy_policy_id=autonomy.id,
            release_candidate_id=candidate.id if rollback_run is not None else None,
            evidence_pack_id=core.id if rollback_run is not None else None,
            rollback_verification_run_id=rollback_run.id if rollback_run is not None else None,
            emergency_control_contract_version=EMERGENCY_CONTROL_CONTRACT_VERSION,
            emergency_stop_contract_version=EMERGENCY_STOP_CONTRACT_VERSION,
            rollback_authority_contract_version=ROLLBACK_AUTHORITY_CONTRACT_VERSION,
            source_provenance=POLICY_PROVENANCE,
            binding_attempt_status="succeeded",
            reason_code=(
                "stop_and_rollback_authority_bound"
                if rollback_run is not None
                else "stop_authority_bound_release_evidence_missing"
            ),
            policy_digest=parsed.policy_digest,
            checklist_digest=parsed.checklist_digest,
            approver_set_digest=policy_version.approver_set_digest,
            autonomy_policy_digest=autonomy_digest,
            release_rollback_binding_digest=release_digest,
            authority_member_count=len(policy_members),
            configured_by_subject_hash=actor_subject_hash,
            configured_by_actor_type=actor_type,
            configured_by_provenance=AUTHORITY_PROVENANCE,
            idempotency_key_hash=idempotency_key_hash,
        )
        self.session.add(row)
        await self.session.flush([row])
        actor_member = None
        for policy_member in policy_members:
            member = EmergencyControlAuthorityMember(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                binding_id=row.id,
                policy_version_id=policy_version.id,
                policy_approver_id=policy_member.id,
                ordinal=policy_member.ordinal,
                principal_subject_hash=policy_member.principal_subject_hash,
                may_activate_stop=True,
                may_clear_stop=True,
                may_authorize_rollback=True,
            )
            self.session.add(member)
            if member.principal_subject_hash == actor_subject_hash:
                actor_member = member
        await self.session.flush()
        if actor_member is None:
            raise EmergencyControlRepositoryError("emergency_authority_membership_unavailable")
        head = await latest_stop_event(self.session, self.context, project_id)
        if head is None:
            anchor = EmergencyStopEvent(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                binding_id=row.id,
                previous_event_id=None,
                event_type="armed_anchor",
                actor_member_id=actor_member.id,
                actor_subject_hash=actor_subject_hash,
                actor_type=actor_type,
                actor_provenance=AUTHORITY_PROVENANCE,
                reason_code="emergency_stop_mechanism_armed",
                idempotency_key_hash=canonical_digest({"armed_anchor_for_binding": str(row.id)}),
            )
            self.session.add(anchor)
            await self.session.flush([anchor])
        await self._audit(
            "emergency_control.bound",
            project_id,
            row.id,
            row.reason_code,
            {"member_count": len(policy_members), "rollback_bound": rollback_run is not None},
        )
        return row

    async def append_event(
        self,
        *,
        binding: EmergencyControlBinding,
        previous: EmergencyStopEvent,
        member: EmergencyControlAuthorityMember,
        event_type: str,
        idempotency_key_hash: str,
    ) -> EmergencyStopEvent:
        row = EmergencyStopEvent(
            tenant_id=self.context.tenant_id,
            project_id=binding.project_id,
            binding_id=binding.id,
            previous_event_id=previous.id,
            event_type=event_type,
            actor_member_id=member.id,
            actor_subject_hash=member.principal_subject_hash,
            actor_type="human",
            actor_provenance=AUTHORITY_PROVENANCE,
            reason_code=(
                "emergency_stop_activated"
                if event_type == "activated"
                else "emergency_stop_cleared"
            ),
            idempotency_key_hash=idempotency_key_hash,
        )
        self.session.add(row)
        await self.session.flush([row])
        return row

    async def activate(
        self,
        *,
        binding: EmergencyControlBinding,
        member: EmergencyControlAuthorityMember,
        idempotency_key_hash: str,
    ) -> tuple[EmergencyStopEvent, int]:
        await lock_project_row(self.session, self.context, binding.project_id)
        await self._assert_current_member(binding, member)
        head = await latest_stop_event(self.session, self.context, binding.project_id)
        if head is None or head.state_after != "armed":
            raise EmergencyControlRepositoryError("emergency_stop_unavailable")
        event = await self.append_event(
            binding=binding,
            previous=head,
            member=member,
            event_type="activated",
            idempotency_key_hash=idempotency_key_hash,
        )
        runs = (
            (
                await self.session.execute(
                    select(ProjectRun)
                    .where(
                        ProjectRun.tenant_id == self.context.tenant_id,
                        ProjectRun.project_id == binding.project_id,
                        ProjectRun.status.in_(("created", "running", "paused", "blocked")),
                    )
                    .order_by(ProjectRun.id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        run_repo = RunRepository(self.session, self.context)
        for run in runs:
            before = run.status
            if before == "running":
                await run_repo.mark_paused_for_emergency(run_id=run.id)
                steps = await run_repo.latest_step(run.id)
                effect_code, after, step_id = "paused", "paused", steps.id
            elif before == "created":
                effect_code, after, step_id = "not_started", before, None
            elif before == "paused":
                effect_code, after, step_id = "already_paused", before, None
            else:
                effect_code, after, step_id = "already_blocked", before, None
            self.session.add(
                EmergencyStopRunEffect(
                    tenant_id=self.context.tenant_id,
                    project_id=binding.project_id,
                    activation_event_id=event.id,
                    run_id=run.id,
                    emergency_run_step_id=step_id,
                    status_before=before,
                    status_after=after,
                    effect_code=effect_code,
                )
            )
        await self.session.flush()
        await self._audit(
            "emergency_stop.activated",
            binding.project_id,
            event.id,
            "local_runtime_stop_activated",
            {"affected_run_count": len(runs)},
        )
        return event, len(runs)

    async def clear(
        self,
        *,
        binding: EmergencyControlBinding,
        member: EmergencyControlAuthorityMember,
        idempotency_key_hash: str,
    ) -> EmergencyStopEvent:
        await lock_project_row(self.session, self.context, binding.project_id)
        await self._assert_current_member(binding, member)
        head = await latest_stop_event(self.session, self.context, binding.project_id)
        if head is None or head.state_after != "active":
            raise EmergencyControlRepositoryError("emergency_stop_unavailable")
        if head.actor_subject_hash == member.principal_subject_hash:
            raise EmergencyControlRepositoryError("distinct_clear_authority_required")
        row = await self.append_event(
            binding=binding,
            previous=head,
            member=member,
            event_type="cleared",
            idempotency_key_hash=idempotency_key_hash,
        )
        await self._audit(
            "emergency_stop.cleared",
            binding.project_id,
            row.id,
            "local_runtime_stop_cleared",
            {"automatic_resume": False},
        )
        return row

    async def authorize_rollback(
        self,
        *,
        binding: EmergencyControlBinding,
        member: EmergencyControlAuthorityMember,
        idempotency_key_hash: str,
    ) -> EmergencyRollbackAuthorization:
        await lock_project_row(self.session, self.context, binding.project_id)
        await self._assert_current_member(binding, member)
        candidate, core, run, digest = await self._current_release_binding(binding.project_id)
        if (
            not binding.rollback_authority_bound
            or candidate is None
            or core is None
            or run is None
            or digest is None
            or binding.release_candidate_id != candidate.id
            or binding.evidence_pack_id != core.id
            or binding.rollback_verification_run_id != run.id
            or binding.release_rollback_binding_digest != digest
        ):
            raise EmergencyControlRepositoryError("rollback_authority_binding_unavailable")
        row = EmergencyRollbackAuthorization(
            tenant_id=self.context.tenant_id,
            project_id=binding.project_id,
            binding_id=binding.id,
            release_candidate_id=candidate.id,
            evidence_pack_id=core.id,
            rollback_verification_run_id=run.id,
            actor_member_id=member.id,
            actor_subject_hash=member.principal_subject_hash,
            actor_type="human",
            actor_provenance=AUTHORITY_PROVENANCE,
            release_rollback_binding_digest=digest,
            authorization_contract_version=ROLLBACK_AUTHORITY_CONTRACT_VERSION,
            result_code="authorized_not_executed",
            scope_limitation_code="production_rollback_not_executed",
            idempotency_key_hash=idempotency_key_hash,
        )
        self.session.add(row)
        await self.session.flush([row])
        await self._audit(
            "emergency_rollback.authorized",
            binding.project_id,
            row.id,
            "authorized_not_executed",
            {"production_action_executed": False},
        )
        return row

    async def status(self, project_id: uuid.UUID) -> EmergencyControlStatus:
        binding = await self.latest_binding(project_id)
        head = await latest_stop_event(self.session, self.context, project_id)
        return EmergencyControlStatus(
            binding_id=binding.id if binding else None,
            event_id=head.id if head else None,
            state=head.state_after if head else "unconfigured",
            rollback_authority_bound=bool(binding and binding.rollback_authority_bound),
            gate_eligible=bool(
                binding
                and binding.gate_eligible_at_creation
                and head
                and head.state_after == "armed"
            ),
            reason_code=binding.reason_code if binding else "no_emergency_control_binding",
        )

    async def enforce_boundary(
        self, project_id: uuid.UUID, run_id: uuid.UUID | None = None
    ) -> None:
        await lock_project_row(self.session, self.context, project_id)
        head = await latest_stop_event(self.session, self.context, project_id)
        if head is None or head.state_after != "active":
            return
        if run_id is not None:
            run = (
                await self.session.execute(
                    select(ProjectRun)
                    .where(
                        ProjectRun.tenant_id == self.context.tenant_id,
                        ProjectRun.project_id == project_id,
                        ProjectRun.id == run_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if run is not None and run.status == "running":
                await RunRepository(self.session, self.context).mark_paused_for_emergency(
                    run_id=run.id
                )
        raise EmergencyStopActive("project emergency stop is active")

    async def coverage_for_project(self, project_id: uuid.UUID) -> EmergencyControlCoverage:
        sources = await self.current_authority_sources(project_id)
        parsed = sources.parsed_policy
        binding = await self.latest_binding(project_id)
        head = await latest_stop_event(self.session, self.context, project_id)
        if binding is None:
            return EmergencyControlCoverage(
                policy_present=bool(sources.policy_category and sources.checklist_category),
                policy_valid=parsed is not None,
            )
        members = await self._members(binding.id)
        membership_complete = bool(
            parsed is not None
            and tuple(m.principal_subject_hash for m in members)
            == tuple(parsed.approver_subject_hashes)
            and binding.approver_set_digest
            == authority_set_digest(tuple(m.principal_subject_hash for m in members))
        )
        policy_current = bool(
            parsed is not None
            and binding.policy_digest == parsed.policy_digest
            and binding.checklist_digest == parsed.checklist_digest
        )
        autonomy_current = bool(
            sources.autonomy_policy is not None
            and sources.autonomy_eligible
            and binding.autonomy_policy_id == sources.autonomy_policy.id
            and binding.autonomy_policy_digest
            == autonomy_policy_digest(
                policy_id=sources.autonomy_policy.id,
                autonomy_level=sources.autonomy_policy.autonomy_level,
                overrides=sources.autonomy_policy.overrides,
                updated_at=sources.autonomy_policy.updated_at,
            )
        )
        (
            current_candidate,
            current_core,
            current_rollback,
            current_digest,
        ) = await self._current_release_binding(project_id)
        rollback_current = bool(
            binding.rollback_authority_bound
            and current_candidate is not None
            and current_core is not None
            and current_rollback is not None
            and binding.release_candidate_id == current_candidate.id
            and binding.evidence_pack_id == current_core.id
            and binding.rollback_verification_run_id == current_rollback.id
            and binding.release_rollback_binding_digest == current_digest
        )
        contracts_current = (
            binding.emergency_control_contract_version == EMERGENCY_CONTROL_CONTRACT_VERSION
            and binding.emergency_stop_contract_version == EMERGENCY_STOP_CONTRACT_VERSION
            and binding.rollback_authority_contract_version == ROLLBACK_AUTHORITY_CONTRACT_VERSION
        )
        consistent = bool(
            policy_current
            and autonomy_current
            and membership_complete
            and head is not None
            and head.state_after in {"armed", "active"}
            and binding.evidence_consistent
        )
        return EmergencyControlCoverage(
            policy_present=bool(sources.policy_category and sources.checklist_category),
            policy_valid=parsed is not None,
            binding_present=True,
            latest_binding_failed_or_refused=binding.binding_attempt_status
            in {"failed", "refused"},
            contracts_current=contracts_current,
            authority_membership_complete=membership_complete,
            authority_member_count=len(members),
            mechanism_initialized=head is not None,
            stop_state_consistent=bool(head and head.state_after in {"armed", "active"}),
            stop_active=bool(head and head.state_after == "active"),
            rollback_authority_bound=binding.rollback_authority_bound,
            rollback_binding_current=rollback_current,
            rollback_verification_current=current_rollback is not None,
            evidence_consistent=consistent,
            control_contract_version=binding.emergency_control_contract_version,
            stop_contract_version=binding.emergency_stop_contract_version,
            rollback_authority_contract_version=binding.rollback_authority_contract_version,
        )

    async def _audit(
        self,
        action: str,
        project_id: uuid.UUID,
        target_id: uuid.UUID,
        result_code: str,
        extra: dict[str, object] | None = None,
    ) -> None:
        payload = {
            "project_id": str(project_id),
            "operation_code": action,
            "result_code": result_code,
            **(extra or {}),
        }
        await audit_record(
            self.session,
            action=action,
            actor="emergency_control_authority",
            target=f"emergency_control:{target_id}",
            payload=payload,
        )
