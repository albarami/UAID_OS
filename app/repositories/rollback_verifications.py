"""Slice-52 connector-observed staging rollback persistence and gate coverage."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.config import settings
from app.models.deployment_target_snapshot import DeploymentTargetSnapshot
from app.models.evidence_pack import EvidencePack
from app.models.rollback_verification import (
    RollbackVerificationPhaseResult,
    RollbackVerificationRun,
)
from app.release.deploy_connector import DeployTargetConnector
from app.release.deploy_evidence_service import refresh_staging_target_evidence
from app.release.project_repo import resolve_declared_repo, resolve_declared_staging_target
from app.release.rollback import (
    ARTIFACT_PROVENANCE,
    EXECUTION_OBSERVATION,
    RUNNER_MANIFEST_HASH,
    SCHEMA_VERSION,
    SCOPE_LIMITATION,
    STAGING_TARGET_CONTRACT_VERSION,
    VERIFICATION_CONTRACT_VERSION,
    RollbackDrillArtifact,
)
from app.release.scm_connector import SCMConnector, SCMConnectorError
from app.repositories.deployments import DeploymentTargetRepository
from app.repositories.evidence_packs import EvidencePackRepository, EvidencePackRepositoryError
from app.repositories.release_candidates import ReleaseCandidateRepository
from app.tenancy import TenantContext, TenantScopedRepository
from app.verify.security_scan import canonical_digest


@dataclass(frozen=True)
class RollbackCoverage:
    scope_resolved: bool = False
    core_present: bool = False
    core_reaudited: bool = False
    repo_binding_agreed: bool = False
    staging_target_valid: bool = False
    staging_snapshot_present: bool = False
    staging_snapshot_available: bool = False
    staging_snapshot_fresh: bool = False
    run_present: bool = False
    attempt_failed: bool = False
    artifact_trusted: bool = False
    binding_current: bool = False
    phase_coverage_complete: bool = False
    evidence_consistent: bool = False
    drill_passed: bool = False
    gate_eligible: bool = False
    phase_count: int = 0
    execution_observation: str | None = None

    def gate_kwargs(self) -> dict:
        return {f"rollback_{key}": value for key, value in self.__dict__.items()}


def _storage_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _snapshot_digest(row: DeploymentTargetSnapshot) -> str:
    return _storage_hash(
        str(row.id),
        _utc_text(row.observed_at),
        str(row.reachable).lower(),
        str(row.provisioned).lower(),
        str(row.target_available).lower(),
        "" if row.observed_http_status is None else str(row.observed_http_status),
        row.provenance,
    )


class RollbackVerificationRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, RollbackVerificationRun)

    async def _latest_pack(self, candidate_id: uuid.UUID) -> EvidencePack | None:
        return (
            await self.session.execute(
                select(EvidencePack)
                .where(
                    EvidencePack.tenant_id == self.context.tenant_id,
                    EvidencePack.release_candidate_id == candidate_id,
                    EvidencePack.assembly_status == "complete",
                )
                .order_by(EvidencePack.created_at.desc(), EvidencePack.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def observe_ci_drill(
        self,
        *,
        project_id: uuid.UUID,
        scm_connector: SCMConnector,
        deploy_connector: DeployTargetConnector,
        service_id: str,
        actor: str,
    ) -> RollbackVerificationRun:
        """Observe one exact-commit artifact, then independently probe the same staging target."""
        candidate = await ReleaseCandidateRepository(self.session, self.context).latest_frozen(
            project_id
        )
        if candidate is None:
            raise ValueError("no current frozen release candidate")
        pack = await self._latest_pack(candidate.id)
        if pack is None:
            raise ValueError("no complete evidence pack core")
        try:
            await EvidencePackRepository(self.session, self.context).audit_pack(pack.id)
        except EvidencePackRepositoryError as exc:
            raise ValueError("evidence pack core re-audit failed") from exc
        declared_repo = await resolve_declared_repo(self.session, self.context, project_id)
        staging = await resolve_declared_staging_target(self.session, self.context, project_id)
        if declared_repo is None or staging is None:
            raise ValueError("repository or staging target is not validly declared")
        repo_hash = canonical_digest(declared_repo[0])
        if (
            pack.repo_binding_state != "agreed"
            or pack.repo_binding_hash != repo_hash
            or pack.commit_sha is None
        ):
            raise ValueError("evidence pack repository binding is missing or disagreed")
        try:
            artifact = await scm_connector.fetch_rollback_drill_artifact(
                repo_ref=declared_repo[0], commit_sha=pack.commit_sha
            )
        except (SCMConnectorError, ValueError):
            return await self._record_failure(
                candidate=candidate,
                pack=pack,
                staging_target_hash=staging.binding_hash,
                reason_code="connector_failure",
                actor=actor,
            )
        if artifact is None:
            return await self._record_failure(
                candidate=candidate,
                pack=pack,
                staging_target_hash=staging.binding_hash,
                reason_code="artifact_missing",
                actor=actor,
            )
        if (
            artifact.schema_version != SCHEMA_VERSION
            or artifact.commit_sha != pack.commit_sha
            or artifact.runner_manifest_hash != RUNNER_MANIFEST_HASH
            or artifact.artifact_provenance != ARTIFACT_PROVENANCE
            or artifact.execution_observation != EXECUTION_OBSERVATION
            or artifact.target_binding_hash != staging.binding_hash
        ):
            return await self._record_failure(
                candidate=candidate,
                pack=pack,
                staging_target_hash=staging.binding_hash,
                reason_code="artifact_contract_or_binding_mismatch",
                actor=actor,
            )
        if artifact.provider_run_ref_hash is None:
            return await self._record_failure(
                candidate=candidate,
                pack=pack,
                staging_target_hash=staging.binding_hash,
                reason_code="provider_run_reference_missing",
                actor=actor,
            )
        refresh = await refresh_staging_target_evidence(
            self.session,
            self.context,
            project_id=project_id,
            agent_id=service_id,
            actor=actor,
            connector=deploy_connector,
        )
        if not refresh.wrote or refresh.snapshot_id is None:
            return await self._record_failure(
                candidate=candidate,
                pack=pack,
                staging_target_hash=staging.binding_hash,
                reason_code=refresh.reason,
                actor=actor,
            )
        snapshot = await self.session.get(DeploymentTargetSnapshot, refresh.snapshot_id)
        if (
            snapshot is None
            or not snapshot.target_available
            or snapshot.observed_at is None
            or snapshot.observed_at <= artifact.completed_at
        ):
            return await self._record_failure(
                candidate=candidate,
                pack=pack,
                staging_target_hash=staging.binding_hash,
                reason_code="staging_target_unavailable_or_not_after_artifact",
                actor=actor,
            )
        return await self._record_observation(
            candidate=candidate,
            pack=pack,
            snapshot=snapshot,
            artifact=artifact,
            actor=actor,
        )

    def _run_base(self, candidate, pack, staging_target_hash: str) -> dict:
        return {
            "tenant_id": self.context.tenant_id,
            "project_id": candidate.project_id,
            "release_candidate_id": candidate.id,
            "evidence_pack_id": pack.id,
            "drill_contract_version": SCHEMA_VERSION,
            "verification_contract_version": VERIFICATION_CONTRACT_VERSION,
            "staging_target_contract_version": STAGING_TARGET_CONTRACT_VERSION,
            "repo_binding_hash": pack.repo_binding_hash,
            "commit_sha": pack.commit_sha,
            "core_content_hash": pack.core_content_hash,
            "artifact_scope_digest": pack.artifact_scope_digest,
            "issue_binding_digest": pack.issue_binding_digest,
            "source_set_digest": pack.source_set_digest,
            "traceability_digest": pack.traceability_digest,
            "staging_target_binding_hash": staging_target_hash,
            "runner_manifest_hash": RUNNER_MANIFEST_HASH,
            "scope_limitation_code": SCOPE_LIMITATION,
        }

    async def _record_failure(
        self, *, candidate, pack, staging_target_hash: str, reason_code: str, actor: str
    ) -> RollbackVerificationRun:
        row = RollbackVerificationRun(
            **self._run_base(candidate, pack, staging_target_hash),
            staging_target_snapshot_id=None,
            artifact_provenance="no_artifact",
            execution_observation="connector_observation_failed",
            staging_snapshot_digest=None,
            from_artifact_digest=None,
            to_artifact_digest=None,
            provider_run_ref_hash=None,
            artifact_content_hash=None,
            workflow_conclusion=None,
            attempt_status="failed",
            reason_code=reason_code[:128],
            phase_count=0,
            phase_digest=None,
            drill_result="incomplete",
            evidence_consistent=False,
            gate_eligible=False,
            artifact_completed_at=None,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, actor)
        return row

    async def _record_observation(
        self,
        *,
        candidate,
        pack: EvidencePack,
        snapshot: DeploymentTargetSnapshot,
        artifact: RollbackDrillArtifact,
        actor: str,
    ) -> RollbackVerificationRun:
        row = RollbackVerificationRun(
            **self._run_base(candidate, pack, artifact.target_binding_hash),
            staging_target_snapshot_id=snapshot.id,
            artifact_provenance=ARTIFACT_PROVENANCE,
            execution_observation=EXECUTION_OBSERVATION,
            staging_snapshot_digest=_snapshot_digest(snapshot),
            from_artifact_digest=artifact.from_artifact_digest,
            to_artifact_digest=artifact.to_artifact_digest,
            provider_run_ref_hash=artifact.provider_run_ref_hash,
            artifact_content_hash=artifact.artifact_content_hash,
            workflow_conclusion=artifact.workflow_conclusion,
            attempt_status="succeeded",
            reason_code="rollback_drill_passed" if artifact.passed else "rollback_drill_failed",
            phase_count=len(artifact.phases),
            phase_digest=artifact.phase_digest,
            drill_result="passed" if artifact.passed else "failed",
            evidence_consistent=True,
            gate_eligible=artifact.passed,
            artifact_completed_at=artifact.completed_at,
        )
        self.session.add(row)
        await self.session.flush()
        for phase in artifact.phases:
            self.session.add(
                RollbackVerificationPhaseResult(
                    tenant_id=self.context.tenant_id,
                    project_id=candidate.project_id,
                    run_id=row.id,
                    ordinal=phase.ordinal,
                    phase_code=phase.phase_code,
                    phase_status=phase.phase_status,
                    result_code=phase.result_code,
                    target_binding_hash=phase.target_binding_hash,
                    expected_version_digest=phase.expected_version_digest,
                    observed_version_digest=phase.observed_version_digest,
                    health_ok=phase.health_ok,
                    operation_ok=phase.operation_ok,
                    started_at=phase.started_at,
                    completed_at=phase.completed_at,
                )
            )
        await self.session.flush()
        await self._audit(row, actor)
        return row

    async def coverage_for_project(
        self, project_id: uuid.UUID, *, as_of: datetime | None = None
    ) -> RollbackCoverage:
        as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidate = await ReleaseCandidateRepository(self.session, self.context).latest_frozen(
            project_id
        )
        if candidate is None:
            return RollbackCoverage()
        pack = await self._latest_pack(candidate.id)
        if pack is None:
            return RollbackCoverage(scope_resolved=True)
        try:
            await EvidencePackRepository(self.session, self.context).audit_pack(pack.id)
            core_reaudited = True
        except EvidencePackRepositoryError:
            core_reaudited = False
        declared_repo = await resolve_declared_repo(self.session, self.context, project_id)
        repo_agreed = bool(
            core_reaudited
            and declared_repo
            and pack.repo_binding_state == "agreed"
            and pack.repo_binding_hash == canonical_digest(declared_repo[0])
            and pack.commit_sha
        )
        staging = await resolve_declared_staging_target(self.session, self.context, project_id)
        if staging is None:
            return RollbackCoverage(
                scope_resolved=True,
                core_present=True,
                core_reaudited=core_reaudited,
                repo_binding_agreed=repo_agreed,
            )
        snapshot = await DeploymentTargetRepository(
            self.session, self.context
        ).latest_deployment_target_for_ref(
            project_id, staging.provider, staging.domain, environment="staging"
        )
        snapshot_present = bool(snapshot and snapshot.provenance == "connector_verified")
        snapshot_available = bool(snapshot_present and snapshot.target_available)
        snapshot_fresh = bool(
            snapshot_present
            and snapshot.observed_at
            and snapshot.observed_at <= as_of
            and as_of - snapshot.observed_at
            <= timedelta(hours=settings.deployment_evidence_max_age_hours)
        )
        latest = (
            await self.session.execute(
                select(RollbackVerificationRun)
                .where(
                    RollbackVerificationRun.tenant_id == self.context.tenant_id,
                    RollbackVerificationRun.project_id == project_id,
                    RollbackVerificationRun.release_candidate_id == candidate.id,
                    RollbackVerificationRun.evidence_pack_id == pack.id,
                    RollbackVerificationRun.staging_target_binding_hash == staging.binding_hash,
                    RollbackVerificationRun.runner_manifest_hash == RUNNER_MANIFEST_HASH,
                    RollbackVerificationRun.drill_contract_version == SCHEMA_VERSION,
                    RollbackVerificationRun.verification_contract_version
                    == VERIFICATION_CONTRACT_VERSION,
                    RollbackVerificationRun.staging_target_contract_version
                    == STAGING_TARGET_CONTRACT_VERSION,
                )
                .order_by(
                    RollbackVerificationRun.created_at.desc(),
                    RollbackVerificationRun.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return RollbackCoverage(
                scope_resolved=True,
                core_present=True,
                core_reaudited=core_reaudited,
                repo_binding_agreed=repo_agreed,
                staging_target_valid=True,
                staging_snapshot_present=snapshot_present,
                staging_snapshot_available=snapshot_available,
                staging_snapshot_fresh=snapshot_fresh,
            )
        phase_count = int(
            (
                await self.session.execute(
                    select(func.count()).where(
                        RollbackVerificationPhaseResult.tenant_id == self.context.tenant_id,
                        RollbackVerificationPhaseResult.run_id == latest.id,
                    )
                )
            ).scalar_one()
        )
        binding_current = bool(
            repo_agreed
            and snapshot
            and latest.staging_target_snapshot_id == snapshot.id
            and latest.repo_binding_hash == pack.repo_binding_hash
            and latest.commit_sha == pack.commit_sha
            and latest.core_content_hash == pack.core_content_hash
            and latest.artifact_scope_digest == pack.artifact_scope_digest
            and latest.issue_binding_digest == pack.issue_binding_digest
            and latest.source_set_digest == pack.source_set_digest
            and latest.traceability_digest == pack.traceability_digest
            and latest.staging_snapshot_digest == _snapshot_digest(snapshot)
        )
        return RollbackCoverage(
            scope_resolved=True,
            core_present=True,
            core_reaudited=core_reaudited,
            repo_binding_agreed=repo_agreed,
            staging_target_valid=True,
            staging_snapshot_present=snapshot_present,
            staging_snapshot_available=snapshot_available,
            staging_snapshot_fresh=snapshot_fresh,
            run_present=True,
            attempt_failed=latest.attempt_status in {"failed", "refused"},
            artifact_trusted=(
                latest.artifact_provenance == ARTIFACT_PROVENANCE
                and latest.execution_observation == EXECUTION_OBSERVATION
            ),
            binding_current=binding_current,
            phase_coverage_complete=phase_count == 5 and latest.phase_count == 5,
            evidence_consistent=latest.evidence_consistent,
            drill_passed=latest.drill_result == "passed",
            gate_eligible=latest.gate_eligible,
            phase_count=phase_count,
            execution_observation=latest.execution_observation,
        )

    async def _audit(self, row: RollbackVerificationRun, actor: str) -> None:
        await audit_record(
            self.session,
            action="release.rollback_drill_observed",
            actor=actor,
            target=f"rollback_verification_run:{row.id}",
            payload={
                "rollback_verification_run_id": str(row.id),
                "project_id": str(row.project_id),
                "release_candidate_id": str(row.release_candidate_id),
                "evidence_pack_id": str(row.evidence_pack_id),
                "staging_target_snapshot_id": (
                    str(row.staging_target_snapshot_id)
                    if row.staging_target_snapshot_id is not None
                    else None
                ),
                "attempt_status": row.attempt_status,
                "reason_code": row.reason_code,
                "drill_result": row.drill_result,
                "phase_count": row.phase_count,
                "artifact_provenance": row.artifact_provenance,
                "execution_observation": row.execution_observation,
                "scope_limitation_code": row.scope_limitation_code,
                "gate_eligible": row.gate_eligible,
                "drill_contract_version": row.drill_contract_version,
                "verification_contract_version": row.verification_contract_version,
                "staging_target_contract_version": row.staging_target_contract_version,
            },
        )
