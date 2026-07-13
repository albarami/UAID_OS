"""Slice-49 evidence-pack assembly persistence and internal export boundary."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from types import MappingProxyType
from typing import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.audit import verify_chain
from app.models.audit_chain_verification import AuditChainVerification
from app.models.evidence_pack import (
    EvidencePack,
    EvidencePackGenerationRun,
    EvidencePackSectionResult,
    EvidencePackSourceRef,
)
from app.models.release_candidate import ReleaseCandidate
from app.models.release_candidate_issue_binding import ReleaseCandidateIssueBinding
from app.models.release_finding import ReleaseFinding
from app.models.release_issue import ReleaseIssue
from app.models.risk_acceptance_record import RiskAcceptanceRecord
from app.models.intake_artifact import IntakeArtifact
from app.models.intake_provenance import IntakeProvenance
from app.models.review_report import ReviewReport
from app.models.test_oracle_run import TestOracleRun
from app.models.security_scan_run import SecurityScanRun
from app.models.shortcut_detector_run import ShortcutDetectorRun
from app.models.acceptance_verification import AcceptanceVerificationRun
from app.release.evidence_export import (
    CanonicalExportUnavailable,
    ExportArtifact,
    build_canonical_export,
    build_core_preview,
    build_markdown_export,
    build_unsigned_manifest,
)
from app.release.evidence_pack import (
    AUDIT_CONTRACT_HASH,
    AUDIT_CONTRACT_VERSION,
    CANONICAL_SCHEMA_VERSION,
    EVIDENCE_PACK_CONTRACT_VERSION,
    EXECUTION_PROVENANCE,
    INVENTORY_SECTIONS,
    PROJECTION_CONTRACT_HASH,
    PROJECTION_CONTRACT_VERSION,
    SEMANTIC_CONTRACT_HASH,
    AuditCheckpointRef,
    CoreAssembly,
    EvidencePackContractError,
    EvidenceSourceRef,
    SectionInventory,
    canonical_json_bytes,
    digest_bytes,
    derive_repo_commit_binding,
    project_source_record,
    assemble_core as assemble_core_payload,
    validate_semantic_payload,
)
from app.tenancy import TenantContext, TenantScopedRepository


class EvidencePackRepositoryError(ValueError):
    """Evidence-pack generation or re-audit failed closed."""


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def record_audit_chain_verification(session: AsyncSession) -> AuditCheckpointRef:
    """Admin-only lock/verify/tip-capture transaction step.

    The caller owns the transaction. Runtime ``uaid_app`` cannot call
    ``audit_verify`` or insert the resulting global row.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(421)"))
    verification = await verify_chain(session)
    tip = (
        await session.execute(
            text("SELECT seq,entry_hash FROM audit_logs ORDER BY seq DESC LIMIT 1")
        )
    ).mappings().one_or_none()
    ok = bool(verification["ok"] and tip is not None)
    row = AuditChainVerification(
        verifier_contract_version=AUDIT_CONTRACT_VERSION,
        verifier_contract_hash=AUDIT_CONTRACT_HASH,
        verification_ok=ok,
        first_bad_seq=None if ok else int(verification["first_bad_seq"] or 0),
        verified_through_seq=int(tip["seq"]) if ok else None,
        verified_through_entry_hash=str(tip["entry_hash"]) if ok else None,
    )
    session.add(row)
    await session.flush()
    return AuditCheckpointRef(
        id=row.id,
        verification_ok=row.verification_ok,
        verified_through_seq=row.verified_through_seq,
        verified_through_entry_hash=row.verified_through_entry_hash,
        verifier_contract_version=row.verifier_contract_version,
        verifier_contract_hash=row.verifier_contract_hash,
        created_at=row.created_at,
        first_bad_seq=row.first_bad_seq,
    )


class EvidencePackRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, EvidencePack)

    async def record_audit_checkpoint(self) -> AuditCheckpointRef:
        return await record_audit_chain_verification(self.session)

    @staticmethod
    def _safe_metadata(pack: EvidencePack, run: EvidencePackGenerationRun) -> dict[str, object]:
        return {
            "id": str(pack.id),
            "generation_run_id": str(pack.generation_run_id),
            "release_candidate_id": str(pack.release_candidate_id),
            "audit_checkpoint_id": str(pack.audit_checkpoint_id),
            "assembly_status": pack.assembly_status,
            "artifact_scope_digest": pack.artifact_scope_digest,
            "issue_binding_digest": pack.issue_binding_digest,
            "source_set_digest": pack.source_set_digest,
            "traceability_digest": pack.traceability_digest,
            "repo_binding_state": pack.repo_binding_state,
            "repo_binding_hash": pack.repo_binding_hash,
            "commit_sha": pack.commit_sha,
            "schema_version": pack.schema_version,
            "semantic_contract_version": pack.semantic_contract_version,
            "semantic_contract_hash": run.semantic_contract_hash,
            "projection_contract_version": pack.projection_contract_version,
            "projection_contract_hash": run.projection_contract_hash,
            "audit_contract_version": pack.audit_contract_version,
            "audit_contract_hash": run.audit_contract_hash,
            "core_content_hash": pack.core_content_hash,
            "source_ref_count": pack.source_ref_count,
            "section_count": pack.section_count,
            "traceability_edge_count": pack.traceability_edge_count,
            "source_cutoff": pack.source_cutoff,
            "generated_at": pack.generated_at,
            "created_at": pack.created_at,
        }

    async def get_history(self, release_candidate_id: uuid.UUID) -> tuple[dict[str, object], ...]:
        """Newest-first safe metadata; canonical bytes and projections stay internal."""
        rows = (
            await self.session.execute(
                select(EvidencePack, EvidencePackGenerationRun)
                .join(
                    EvidencePackGenerationRun,
                    EvidencePackGenerationRun.id == EvidencePack.generation_run_id,
                )
                .where(
                    EvidencePack.tenant_id == self.context.tenant_id,
                    EvidencePack.release_candidate_id == release_candidate_id,
                )
                .order_by(EvidencePack.created_at.desc(), EvidencePack.id.desc())
            )
        ).all()
        return tuple(self._safe_metadata(pack, run) for pack, run in rows)

    async def get_latest_exact_binding(
        self,
        *,
        release_candidate_id: uuid.UUID,
        audit_checkpoint_id: uuid.UUID,
        artifact_scope_digest: str,
        issue_binding_digest: str,
        source_set_digest: str,
    ) -> dict[str, object] | None:
        """Latest row for the exact candidate, source snapshot, checkpoint, and contracts."""
        row = (
            await self.session.execute(
                select(EvidencePack, EvidencePackGenerationRun)
                .join(
                    EvidencePackGenerationRun,
                    EvidencePackGenerationRun.id == EvidencePack.generation_run_id,
                )
                .where(
                    EvidencePack.tenant_id == self.context.tenant_id,
                    EvidencePack.release_candidate_id == release_candidate_id,
                    EvidencePack.audit_checkpoint_id == audit_checkpoint_id,
                    EvidencePack.artifact_scope_digest == artifact_scope_digest,
                    EvidencePack.issue_binding_digest == issue_binding_digest,
                    EvidencePack.source_set_digest == source_set_digest,
                    EvidencePackGenerationRun.semantic_contract_hash == SEMANTIC_CONTRACT_HASH,
                    EvidencePackGenerationRun.projection_contract_hash == PROJECTION_CONTRACT_HASH,
                    EvidencePackGenerationRun.audit_contract_hash == AUDIT_CONTRACT_HASH,
                )
                .order_by(EvidencePack.created_at.desc(), EvidencePack.id.desc())
                .limit(1)
            )
        ).one_or_none()
        return None if row is None else self._safe_metadata(*row)

    async def record_failed_attempt(
        self,
        *,
        project_id: uuid.UUID,
        release_candidate_id: uuid.UUID,
        audit_checkpoint_id: uuid.UUID | None,
        failure_code: str,
        actor: str,
    ) -> EvidencePackGenerationRun:
        """Retain a safe failed/refused attempt after its work transaction rolled back."""
        allowed = {
            "source_projection_contract_failed",
            "source_inventory_contract_failed",
            "source_cap_exceeded",
            "binding_inconsistent",
            "assembly_contract_failed",
        }
        if failure_code not in allowed:
            raise EvidencePackRepositoryError("failure_code_not_allowed")
        candidate = (
            await self.session.execute(
                select(ReleaseCandidate).where(
                    ReleaseCandidate.id == release_candidate_id,
                    ReleaseCandidate.project_id == project_id,
                    ReleaseCandidate.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if candidate is None or candidate.status != "frozen" or candidate.frozen_at is None:
            raise EvidencePackRepositoryError("currently_frozen_candidate_required")
        if audit_checkpoint_id is not None:
            checkpoint = await self.session.get(AuditChainVerification, audit_checkpoint_id)
            if checkpoint is None:
                raise EvidencePackRepositoryError("audit_checkpoint_not_found")
        now = await self.session.scalar(select(func.clock_timestamp()))
        run = EvidencePackGenerationRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_candidate_id=release_candidate_id,
            audit_checkpoint_id=audit_checkpoint_id,
            release_ref_digest=digest_bytes(candidate.release_ref),
            schema_version=CANONICAL_SCHEMA_VERSION,
            semantic_contract_version=EVIDENCE_PACK_CONTRACT_VERSION,
            semantic_contract_hash=SEMANTIC_CONTRACT_HASH,
            projection_contract_version=PROJECTION_CONTRACT_VERSION,
            projection_contract_hash=PROJECTION_CONTRACT_HASH,
            audit_contract_version=AUDIT_CONTRACT_VERSION,
            audit_contract_hash=AUDIT_CONTRACT_HASH,
            execution_status="failed",
            execution_provenance=EXECUTION_PROVENANCE,
            failure_code=failure_code,
            missing_required_section_count=0,
            inconsistent_section_count=0,
            source_ref_count=0,
            section_count=0,
            traceability_edge_count=0,
            canonical_byte_count=0,
            source_cutoff=candidate.frozen_at,
            generated_at=now,
        )
        self.session.add(run)
        await self.session.flush()
        await audit_record(
            self.session,
            action="evidence_pack.generation_failed",
            actor=actor,
            target=str(run.id),
            payload={
                "project_id": str(project_id),
                "release_candidate_id": str(release_candidate_id),
                "failure_code": failure_code,
            },
        )
        return run

    async def _latest_rows(
        self,
        model,
        *,
        project_id: uuid.UUID,
        as_of: datetime,
        partition_by: tuple,
    ) -> list:
        rank = func.row_number().over(
            partition_by=partition_by,
            order_by=(model.created_at.desc(), model.id.desc()),
        ).label("latest_rank")
        ranked = (
            select(model.id.label("record_id"), rank)
            .where(
                model.tenant_id == self.context.tenant_id,
                model.project_id == project_id,
                model.created_at <= as_of,
            )
            .subquery()
        )
        return list(
            (
                await self.session.execute(
                    select(model)
                    .join(ranked, ranked.c.record_id == model.id)
                    .where(ranked.c.latest_rank == 1)
                    .order_by(model.created_at, model.id)
                )
            ).scalars()
        )

    async def assemble_core(
        self,
        *,
        project_id: uuid.UUID,
        release_candidate_id: uuid.UUID,
        audit_checkpoint_id: uuid.UUID,
        actor: str,
    ) -> EvidencePack:
        """Derive and persist the conservative twelve-section inventory."""
        candidate = (
            await self.session.execute(
                select(ReleaseCandidate).where(
                    ReleaseCandidate.id == release_candidate_id,
                    ReleaseCandidate.project_id == project_id,
                    ReleaseCandidate.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if candidate is None or candidate.status != "frozen" or candidate.frozen_at is None:
            raise EvidencePackRepositoryError("currently_frozen_candidate_required")
        checkpoint = await self.session.get(AuditChainVerification, audit_checkpoint_id)
        if checkpoint is None or not checkpoint.verification_ok:
            raise EvidencePackRepositoryError("successful_audit_checkpoint_required")
        checkpoint_ref = AuditCheckpointRef(
            id=checkpoint.id,
            verification_ok=checkpoint.verification_ok,
            verified_through_seq=checkpoint.verified_through_seq,
            verified_through_entry_hash=checkpoint.verified_through_entry_hash,
            verifier_contract_version=checkpoint.verifier_contract_version,
            verifier_contract_hash=checkpoint.verifier_contract_hash,
            created_at=checkpoint.created_at,
            first_bad_seq=checkpoint.first_bad_seq,
        )
        generated_at = await self.session.scalar(select(func.clock_timestamp()))

        artifacts = list(
            (
                await self.session.execute(
                    select(IntakeArtifact)
                    .where(
                        IntakeArtifact.tenant_id == self.context.tenant_id,
                        IntakeArtifact.project_id == project_id,
                        IntakeArtifact.created_at <= candidate.frozen_at,
                    )
                    .order_by(IntakeArtifact.created_at, IntakeArtifact.id)
                )
            ).scalars()
        )
        artifact_ids = [row.id for row in artifacts]
        provenance = []
        if artifact_ids:
            provenance = list(
                (
                    await self.session.execute(
                        select(IntakeProvenance)
                        .where(
                            IntakeProvenance.tenant_id == self.context.tenant_id,
                            IntakeProvenance.project_id == project_id,
                            IntakeProvenance.artifact_id.in_(artifact_ids),
                            IntakeProvenance.created_at <= candidate.frozen_at,
                        )
                        .order_by(IntakeProvenance.created_at, IntakeProvenance.id)
                    )
                ).scalars()
            )
        bindings = list(
            (
                await self.session.execute(
                    select(ReleaseCandidateIssueBinding)
                    .where(
                        ReleaseCandidateIssueBinding.tenant_id == self.context.tenant_id,
                        ReleaseCandidateIssueBinding.project_id == project_id,
                        ReleaseCandidateIssueBinding.release_candidate_id == candidate.id,
                    )
                    .order_by(
                        ReleaseCandidateIssueBinding.created_at,
                        ReleaseCandidateIssueBinding.id,
                    )
                )
            ).scalars()
        )
        issue_ids = [row.release_issue_id for row in bindings]
        issues = []
        if issue_ids:
            issues = list(
                (
                    await self.session.execute(
                        select(ReleaseIssue)
                        .where(
                            ReleaseIssue.tenant_id == self.context.tenant_id,
                            ReleaseIssue.project_id == project_id,
                            ReleaseIssue.id.in_(issue_ids),
                        )
                        .order_by(ReleaseIssue.created_at, ReleaseIssue.id)
                    )
                ).scalars()
            )
        finding_ids = [row.source_finding_id for row in issues if row.source_finding_id]
        findings = []
        if finding_ids:
            findings = list(
                (
                    await self.session.execute(
                        select(ReleaseFinding)
                        .where(
                            ReleaseFinding.tenant_id == self.context.tenant_id,
                            ReleaseFinding.project_id == project_id,
                            ReleaseFinding.id.in_(finding_ids),
                        )
                        .order_by(ReleaseFinding.created_at, ReleaseFinding.id)
                    )
                ).scalars()
            )
        risk_acceptances = list(
            (
                await self.session.execute(
                    select(RiskAcceptanceRecord)
                    .where(
                        RiskAcceptanceRecord.tenant_id == self.context.tenant_id,
                        RiskAcceptanceRecord.project_id == project_id,
                        RiskAcceptanceRecord.release_id == candidate.release_ref,
                    )
                    .order_by(RiskAcceptanceRecord.created_at, RiskAcceptanceRecord.id)
                )
            ).scalars()
        )
        review_reports = await self._latest_rows(
            ReviewReport,
            project_id=project_id,
            as_of=generated_at,
            partition_by=(
                ReviewReport.task_contract_id,
                ReviewReport.reviewer_instance_id,
                ReviewReport.layer,
            ),
        )
        test_oracles = await self._latest_rows(
            TestOracleRun,
            project_id=project_id,
            as_of=generated_at,
            partition_by=(
                TestOracleRun.oracle_artifact_id,
                TestOracleRun.definition_hash,
                TestOracleRun.repo_binding_hash,
                TestOracleRun.commit_sha,
            ),
        )
        security_scans = await self._latest_rows(
            SecurityScanRun,
            project_id=project_id,
            as_of=generated_at,
            partition_by=(
                SecurityScanRun.repo_binding_hash,
                SecurityScanRun.commit_sha,
                SecurityScanRun.scanner_manifest_hash,
            ),
        )
        shortcut_runs = await self._latest_rows(
            ShortcutDetectorRun,
            project_id=project_id,
            as_of=generated_at,
            partition_by=(
                ShortcutDetectorRun.repo_binding_hash,
                ShortcutDetectorRun.commit_sha,
                ShortcutDetectorRun.detector_contract_hash,
            ),
        )
        acceptance_runs = await self._latest_rows(
            AcceptanceVerificationRun,
            project_id=project_id,
            as_of=generated_at,
            partition_by=(
                AcceptanceVerificationRun.scope_digest,
                AcceptanceVerificationRun.authorship_digest,
                AcceptanceVerificationRun.verifier_contract_hash,
            ),
        )
        from app.repositories.reviewer_quality import ReviewerQualityRepository

        reviewer_refs = await ReviewerQualityRepository(
            self.session, self.context
        ).evidence_pack_safe_projection(project_id=project_id, as_of=generated_at)

        groups = {
            "scope": [project_source_record("intake_artifact", row) for row in artifacts],
            "sanad_provenance": [
                project_source_record("intake_provenance", row) for row in provenance
            ],
            "candidate_issues": [
                *(
                    project_source_record("release_candidate_issue_binding", row)
                    for row in bindings
                ),
                *(project_source_record("release_issue", row) for row in issues),
                *(project_source_record("release_finding", row) for row in findings),
            ],
            "risk_acceptances": [
                project_source_record("risk_acceptance_record", row)
                for row in risk_acceptances
            ],
            "review_reports": [
                project_source_record("review_report", row) for row in review_reports
            ],
            "test_oracles": [
                project_source_record("test_oracle_run", row) for row in test_oracles
            ],
            "security_scans": [
                project_source_record("security_scan_run", row) for row in security_scans
            ],
            "shortcut_detectors": [
                project_source_record("shortcut_detector_run", row) for row in shortcut_runs
            ],
            "acceptance_verification": [
                project_source_record("acceptance_verification_run", row)
                for row in acceptance_runs
            ],
            "reviewer_quality": reviewer_refs,
        }
        all_refs = [row for rows in groups.values() for row in rows]
        ref_ids = {(row.source_kind, str(row.source_id)) for row in all_refs}
        traceability: list[dict[str, str]] = []

        def edge(kind: str, from_kind: str, from_id, to_kind: str, to_id) -> None:
            if (from_kind, str(from_id)) in ref_ids and (to_kind, str(to_id)) in ref_ids:
                traceability.append(
                    {
                        "edge_kind": kind,
                        "from_kind": from_kind,
                        "from_id": str(from_id),
                        "to_kind": to_kind,
                        "to_id": str(to_id),
                    }
                )

        for row in provenance:
            edge("sanad_source_for", "intake_provenance", row.id, "intake_artifact", row.artifact_id)
        for row in artifacts:
            if row.parent_id:
                edge("canonical_parent", "intake_artifact", row.id, "intake_artifact", row.parent_id)
        for row in bindings:
            edge(
                "candidate_issue_membership",
                "release_candidate_issue_binding",
                row.id,
                "release_issue",
                row.release_issue_id,
            )
        for row in issues:
            if row.source_finding_id:
                edge("finding_bridge", "release_issue", row.id, "release_finding", row.source_finding_id)
        groups["traceability"] = []

        required_nonempty = {
            "scope",
            "traceability",
            "review_reports",
            "test_oracles",
            "security_scans",
            "shortcut_detectors",
            "acceptance_verification",
            "reviewer_quality",
            "sanad_provenance",
            "audit_checkpoint",
        }
        section_values = {
            "scope": [row.as_dict() for row in groups["scope"]],
            "traceability": traceability,
            "candidate_issues": [row.as_dict() for row in groups["candidate_issues"]],
            "risk_acceptances": [row.as_dict() for row in groups["risk_acceptances"]],
            "review_reports": [row.as_dict() for row in groups["review_reports"]],
            "test_oracles": [row.as_dict() for row in groups["test_oracles"]],
            "security_scans": [row.as_dict() for row in groups["security_scans"]],
            "shortcut_detectors": [row.as_dict() for row in groups["shortcut_detectors"]],
            "acceptance_verification": [
                row.as_dict() for row in groups["acceptance_verification"]
            ],
            "reviewer_quality": [row.as_dict() for row in groups["reviewer_quality"]],
            "sanad_provenance": [row.as_dict() for row in groups["sanad_provenance"]],
            "audit_checkpoint": [checkpoint_ref.as_dict()],
        }
        inventories = []
        for section in INVENTORY_SECTIONS:
            values = section_values[section]
            missing = section in required_nonempty and not values
            inventories.append(
                SectionInventory(
                    section_code=section,
                    presence_code=(
                        "missing_required_source"
                        if missing
                        else ("present" if values else "present_zero_rows")
                    ),
                    item_count=len(values),
                    section_digest=digest_bytes(canonical_json_bytes(values)),
                    required=True,
                    failure_code="missing_required_source" if missing else None,
                )
            )
        trusted_observations = [
            {
                "repo_binding_hash": row.projection.get("repo_binding_hash"),
                "commit_sha": row.projection.get("commit_sha"),
                "truth_tier": row.truth_tier,
            }
            for section in ("test_oracles", "security_scans", "shortcut_detectors")
            for row in groups[section]
        ]
        core = assemble_core_payload(
            project_id=project_id,
            release_candidate_id=release_candidate_id,
            release_ref_digest=digest_bytes(candidate.release_ref),
            generated_at=generated_at,
            frozen_at=candidate.frozen_at,
            artifact_scope_digest=digest_bytes(
                canonical_json_bytes([row.projection_digest for row in groups["scope"]])
            ),
            issue_binding_digest=digest_bytes(
                canonical_json_bytes(
                    [
                        project_source_record(
                            "release_candidate_issue_binding", row
                        ).projection_digest
                        for row in bindings
                    ]
                )
            ),
            source_refs=all_refs,
            inventories=inventories,
            traceability=traceability,
            audit_checkpoint=checkpoint_ref,
            repo_commit_binding=derive_repo_commit_binding(trusted_observations),
        )
        return await self._persist_core(
            project_id=project_id,
            release_candidate_id=release_candidate_id,
            core=core,
            source_refs=all_refs,
            inventories=inventories,
            traceability_edge_count=len(traceability),
            actor=actor,
        )

    async def _persist_core(
        self,
        *,
        project_id: uuid.UUID,
        release_candidate_id: uuid.UUID,
        core: CoreAssembly,
        source_refs: Sequence[EvidenceSourceRef],
        inventories: Sequence[SectionInventory],
        traceability_edge_count: int,
        actor: str,
    ) -> EvidencePack:
        """Persist one code-owned assembly atomically.

        This is an internal orchestration seam. Public generation must derive
        ``core`` and its inventory from repository reads, never caller truth.
        """
        candidate = (
            await self.session.execute(
                select(ReleaseCandidate).where(
                    ReleaseCandidate.id == release_candidate_id,
                    ReleaseCandidate.project_id == project_id,
                    ReleaseCandidate.tenant_id == self.context.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if candidate is None or candidate.status != "frozen" or candidate.frozen_at is None:
            raise EvidencePackRepositoryError("currently_frozen_candidate_required")
        if core.payload["project_id"] != str(project_id):
            raise EvidencePackRepositoryError("core_project_mismatch")
        if core.payload["release_id"] != str(release_candidate_id):
            raise EvidencePackRepositoryError("core_candidate_mismatch")
        if core.payload["scope"]["frozen_at"] != candidate.frozen_at.isoformat().replace(
            "+00:00", "Z"
        ):
            raise EvidencePackRepositoryError("core_candidate_cutoff_mismatch")
        if list(core.payload["source_refs"]) != [
            row.as_dict()
            for row in sorted(
                source_refs,
                key=lambda item: (item.source_kind, str(item.source_id), item.source_created_at),
            )
        ]:
            raise EvidencePackRepositoryError("core_source_set_mismatch")
        inventory_by_code = {row.section_code: row for row in inventories}
        if set(inventory_by_code) != set(INVENTORY_SECTIONS):
            raise EvidencePackRepositoryError("core_inventory_mismatch")
        checkpoint_id = uuid.UUID(core.payload["integrity"]["audit_checkpoint"]["id"])
        checkpoint = await self.session.get(AuditChainVerification, checkpoint_id)
        if checkpoint is None or not checkpoint.verification_ok:
            raise EvidencePackRepositoryError("successful_audit_checkpoint_required")

        missing_count = sum(
            row.presence_code == "missing_required_source" and row.required
            for row in inventories
        )
        inconsistent_count = sum(
            row.presence_code == "inconsistent_source" for row in inventories
        )
        run_status = "succeeded" if core.assembly_status == "complete" else "incomplete"
        run = EvidencePackGenerationRun(
            id=uuid.uuid4(),
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_candidate_id=release_candidate_id,
            audit_checkpoint_id=checkpoint_id,
            release_ref_digest=core.payload["scope"]["release_ref_digest"],
            schema_version=CANONICAL_SCHEMA_VERSION,
            semantic_contract_version=EVIDENCE_PACK_CONTRACT_VERSION,
            semantic_contract_hash=SEMANTIC_CONTRACT_HASH,
            projection_contract_version=PROJECTION_CONTRACT_VERSION,
            projection_contract_hash=PROJECTION_CONTRACT_HASH,
            audit_contract_version=AUDIT_CONTRACT_VERSION,
            audit_contract_hash=AUDIT_CONTRACT_HASH,
            execution_status=run_status,
            execution_provenance=EXECUTION_PROVENANCE,
            failure_code=None if run_status == "succeeded" else "required_sources_incomplete",
            missing_required_section_count=missing_count,
            inconsistent_section_count=inconsistent_count,
            source_ref_count=len(source_refs),
            section_count=len(inventories),
            traceability_edge_count=traceability_edge_count,
            canonical_byte_count=len(core.canonical_text.encode("utf-8")),
            source_cutoff=candidate.frozen_at,
            generated_at=_parse_time(core.payload["generated_at"]),
        )
        binding = core.payload["repo_commit_binding"]
        pack = EvidencePack(
            id=uuid.uuid4(),
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            generation_run_id=run.id,
            release_candidate_id=release_candidate_id,
            audit_checkpoint_id=checkpoint_id,
            assembly_status=core.assembly_status,
            artifact_scope_digest=core.payload["scope"]["artifact_scope_digest"],
            issue_binding_digest=core.payload["scope"]["issue_binding_digest"],
            source_set_digest=core.source_set_digest,
            traceability_digest=core.traceability_digest,
            repo_binding_state=binding["state"],
            repo_binding_hash=binding["repo_binding_hash"],
            commit_sha=binding["commit_sha"],
            schema_version=CANONICAL_SCHEMA_VERSION,
            semantic_contract_version=EVIDENCE_PACK_CONTRACT_VERSION,
            projection_contract_version=PROJECTION_CONTRACT_VERSION,
            audit_contract_version=AUDIT_CONTRACT_VERSION,
            canonical_core_text=core.canonical_text,
            core_content_hash=core.content_hash,
            verdict_status="absent_deferred_slice50",
            signature_status="unsigned_signer_tier_not_implemented",
            source_ref_count=len(source_refs),
            section_count=len(inventories),
            traceability_edge_count=traceability_edge_count,
            source_cutoff=candidate.frozen_at,
            generated_at=_parse_time(core.payload["generated_at"]),
        )
        self.session.add(run)
        await self.session.flush([run])
        self.session.add(pack)
        await self.session.flush([pack])
        ordered_refs = sorted(
            source_refs,
            key=lambda item: (item.source_kind, str(item.source_id), item.source_created_at),
        )
        self.session.add_all(
            [
                EvidencePackSourceRef(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    evidence_pack_id=pack.id,
                    source_kind=row.source_kind,
                    source_id=row.source_id,
                    truth_tier=row.truth_tier,
                    projection_digest=row.projection_digest,
                    source_created_at=row.source_created_at,
                    ordinal=index,
                )
                for index, row in enumerate(ordered_refs, 1)
            ]
        )
        self.session.add_all(
            [
                EvidencePackSectionResult(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    evidence_pack_id=pack.id,
                    section_code=code,
                    presence_code=inventory_by_code[code].presence_code,
                    item_count=inventory_by_code[code].item_count,
                    section_digest=inventory_by_code[code].section_digest,
                    required=inventory_by_code[code].required,
                    failure_code=inventory_by_code[code].failure_code,
                    ordinal=index,
                )
                for index, code in enumerate(INVENTORY_SECTIONS, 1)
            ]
        )
        await self.session.flush()
        await audit_record(
            self.session,
            action="evidence_pack.core_assembled",
            actor=actor,
            target=str(pack.id),
            payload={
                "project_id": str(project_id),
                "release_candidate_id": str(release_candidate_id),
                "assembly_status": core.assembly_status,
                "source_ref_count": len(source_refs),
                "section_count": len(inventories),
                "repo_binding_state": binding["state"],
                "content_hash": core.content_hash,
            },
        )
        return pack

    async def _reaudit(self, pack_id: uuid.UUID) -> CoreAssembly:
        pack = await self.get(pack_id)
        if pack is None:
            raise EvidencePackRepositoryError("evidence_pack_not_found")
        try:
            payload = json.loads(pack.canonical_core_text)
        except json.JSONDecodeError as exc:
            raise EvidencePackRepositoryError("stored_core_json_invalid") from exc
        exact = canonical_json_bytes(payload)
        if exact.decode("utf-8") != pack.canonical_core_text:
            raise EvidencePackRepositoryError("stored_core_not_canonical")
        if digest_bytes(exact) != pack.core_content_hash:
            raise EvidencePackRepositoryError("stored_core_hash_mismatch")
        try:
            validate_semantic_payload(payload, canonical_export=False)
        except EvidencePackContractError as exc:
            raise EvidencePackRepositoryError(exc.code) from exc
        refs = (
            await self.session.execute(
                select(EvidencePackSourceRef)
                .where(
                    EvidencePackSourceRef.evidence_pack_id == pack.id,
                    EvidencePackSourceRef.project_id == pack.project_id,
                    EvidencePackSourceRef.tenant_id == self.context.tenant_id,
                )
                .order_by(EvidencePackSourceRef.ordinal)
            )
        ).scalars().all()
        sections = (
            await self.session.execute(
                select(EvidencePackSectionResult)
                .where(
                    EvidencePackSectionResult.evidence_pack_id == pack.id,
                    EvidencePackSectionResult.project_id == pack.project_id,
                    EvidencePackSectionResult.tenant_id == self.context.tenant_id,
                )
                .order_by(EvidencePackSectionResult.ordinal)
            )
        ).scalars().all()
        if len(refs) != pack.source_ref_count or len(sections) != pack.section_count:
            raise EvidencePackRepositoryError("stored_child_count_mismatch")
        projected_refs = payload["source_refs"]
        if len(projected_refs) != len(refs):
            raise EvidencePackRepositoryError("stored_source_projection_count_mismatch")
        for row, projected in zip(refs, projected_refs, strict=True):
            if (
                projected["source_kind"] != row.source_kind
                or projected["source_id"] != str(row.source_id)
                or projected["truth_tier"] != row.truth_tier
                or projected["projection_digest"] != row.projection_digest
            ):
                raise EvidencePackRepositoryError("stored_source_projection_mismatch")
        inventory = payload["source_inventory"]
        for row, projected in zip(sections, inventory, strict=True):
            if (
                projected["section_code"] != row.section_code
                or projected["presence_code"] != row.presence_code
                or projected["item_count"] != row.item_count
                or projected["section_digest"] != row.section_digest
                or projected["required"] != row.required
                or projected["failure_code"] != row.failure_code
            ):
                raise EvidencePackRepositoryError("stored_section_projection_mismatch")
        checkpoint = await self.session.get(AuditChainVerification, pack.audit_checkpoint_id)
        checkpoint_payload = payload["integrity"]["audit_checkpoint"]
        if (
            checkpoint is None
            or not checkpoint.verification_ok
            or checkpoint_payload["id"] != str(checkpoint.id)
            or checkpoint_payload["verified_through_seq"] != checkpoint.verified_through_seq
            or checkpoint_payload["verified_through_entry_hash"]
            != checkpoint.verified_through_entry_hash
        ):
            raise EvidencePackRepositoryError("stored_audit_checkpoint_mismatch")
        return CoreAssembly(
            payload=MappingProxyType(payload),
            canonical_text=pack.canonical_core_text,
            content_hash=pack.core_content_hash,
            assembly_status=pack.assembly_status,
            source_set_digest=pack.source_set_digest,
            traceability_digest=pack.traceability_digest,
        )

    async def audit_pack(self, pack_id: uuid.UUID) -> CoreAssembly:
        """Recompute the semantic audit from exact stored bytes and normalized children."""
        return await self._reaudit(pack_id)

    async def export_core_preview(self, pack_id: uuid.UUID, *, actor: str) -> ExportArtifact:
        core = await self._reaudit(pack_id)
        artifact = build_core_preview(core)
        await audit_record(
            self.session,
            action="evidence_pack.core_preview_exported",
            actor=actor,
            target=str(pack_id),
            payload={
                "file_name": artifact.file_name,
                "byte_count": len(artifact.content),
                "content_hash": digest_bytes(artifact.content),
                "export_kind": "not_canonical_export",
            },
        )
        return artifact

    async def export_markdown(self, pack_id: uuid.UUID, *, actor: str) -> ExportArtifact:
        core = await self._reaudit(pack_id)
        artifact = build_markdown_export(core)
        await audit_record(
            self.session,
            action="evidence_pack.markdown_exported",
            actor=actor,
            target=str(pack_id),
            payload={
                "file_name": artifact.file_name,
                "byte_count": len(artifact.content),
                "content_hash": digest_bytes(artifact.content),
                "export_kind": "not_canonical_export",
            },
        )
        return artifact

    async def export_unsigned_manifest(self, pack_id: uuid.UUID, *, actor: str) -> ExportArtifact:
        core = await self._reaudit(pack_id)
        artifact = build_unsigned_manifest(build_core_preview(core))
        await audit_record(
            self.session,
            action="evidence_pack.unsigned_manifest_exported",
            actor=actor,
            target=str(pack_id),
            payload={
                "file_name": artifact.file_name,
                "byte_count": len(artifact.content),
                "content_hash": digest_bytes(artifact.content),
                "export_kind": "unsigned_hash_manifest",
            },
        )
        return artifact

    async def export_canonical_json(self, pack_id: uuid.UUID, *, actor: str) -> ExportArtifact:
        core = await self._reaudit(pack_id)
        await audit_record(
            self.session,
            action="evidence_pack.canonical_export_refused",
            actor=actor,
            target=str(pack_id),
            payload={"reason_code": "real_verdict_attestation_required"},
        )
        return build_canonical_export(core, verdict_attestation=None)


__all__ = [
    "CanonicalExportUnavailable",
    "EvidencePackRepository",
    "EvidencePackRepositoryError",
    "record_audit_chain_verification",
]
