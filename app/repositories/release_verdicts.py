"""Tenant-scoped Slice-50 release-verdict evaluation and exact-binding reads."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.evidence_pack import EvidencePack, EvidencePackGenerationRun
from app.models.release_candidate import ReleaseCandidate
from app.models.release_candidate_issue_binding import ReleaseCandidateIssueBinding
from app.models.release_issue import ReleaseIssue
from app.models.release_verdict import (
    ReleaseVerdict,
    ReleaseVerdictIssueResult,
    ReleaseVerdictRun,
)
from app.models.risk_acceptance_record import RiskAcceptanceRecord
from app.release.evidence_pack import canonical_json_bytes, digest_bytes, project_source_record
from app.release.issues import TRUSTED_FINDING_PROVENANCE, is_hard_blocker
from app.release.release_manager import (
    DECISION_SCOPE,
    EXECUTION_PROVENANCE,
    INPUT_CONTRACT_VERSION,
    PROJECTION_CONTRACT_VERSION,
    VERDICT_CONTRACT_HASH,
    VERDICT_CONTRACT_VERSION,
    IssueDisposition,
    ReleaseVerdictInput,
    canonical_input_digest,
    evaluate_release_verdict,
)
from app.repositories.evidence_packs import EvidencePackRepository, EvidencePackRepositoryError
from app.tenancy import TenantContext, TenantScopedRepository


class ReleaseVerdictRepositoryError(ValueError):
    """A verdict could not be derived from exact current DB evidence."""


@dataclass(frozen=True)
class ReleaseVerdictCoverage:
    evidence_core_present: bool = False
    evidence_core_audited: bool = False
    verdict_run_present: bool = False
    verdict_attempt_failed: bool = False
    verdict_binding_current: bool = False
    verdict_evidence_consistent: bool = False
    spec_verdict: str | None = None
    gate_eligible: bool = False
    reason_code: str | None = None
    decision_scope: str | None = None
    execution_provenance: str | None = None

    def gate_kwargs(self) -> dict[str, object]:
        return {
            "release_evidence_core_present": self.evidence_core_present,
            "release_evidence_core_audited": self.evidence_core_audited,
            "release_verdict_run_present": self.verdict_run_present,
            "release_verdict_attempt_failed": self.verdict_attempt_failed,
            "release_verdict_binding_current": self.verdict_binding_current,
            "release_verdict_evidence_consistent": self.verdict_evidence_consistent,
            "release_verdict_spec_verdict": self.spec_verdict,
            "release_verdict_gate_eligible": self.gate_eligible,
            "release_verdict_reason_code": self.reason_code,
            "release_verdict_decision_scope": self.decision_scope,
            "release_verdict_execution_provenance": self.execution_provenance,
        }


@dataclass(frozen=True)
class _IssueRow:
    binding: ReleaseCandidateIssueBinding
    issue: ReleaseIssue
    risk: RiskAcceptanceRecord | None


class ReleaseVerdictRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ReleaseVerdict)

    async def _candidate(
        self, project_id: uuid.UUID, release_candidate_id: uuid.UUID
    ) -> ReleaseCandidate:
        row = (
            await self.session.execute(
                select(ReleaseCandidate)
                .where(
                    ReleaseCandidate.id == release_candidate_id,
                    ReleaseCandidate.project_id == project_id,
                    ReleaseCandidate.tenant_id == self.context.tenant_id,
                )
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if row is None or row.status != "frozen" or row.frozen_at is None:
            raise ReleaseVerdictRepositoryError("exact_frozen_candidate_required")
        return row

    async def _issue_rows(self, candidate_id: uuid.UUID) -> tuple[_IssueRow, ...]:
        rows = (
            await self.session.execute(
                select(ReleaseCandidateIssueBinding, ReleaseIssue, RiskAcceptanceRecord)
                .join(
                    ReleaseIssue, ReleaseIssue.id == ReleaseCandidateIssueBinding.release_issue_id
                )
                .outerjoin(
                    RiskAcceptanceRecord,
                    RiskAcceptanceRecord.id == ReleaseIssue.risk_acceptance_record_id,
                )
                .where(
                    ReleaseCandidateIssueBinding.release_candidate_id == candidate_id,
                    ReleaseCandidateIssueBinding.tenant_id == self.context.tenant_id,
                )
                .order_by(
                    ReleaseCandidateIssueBinding.created_at,
                    ReleaseCandidateIssueBinding.id,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
        if len(rows) > 10_000:
            raise ReleaseVerdictRepositoryError("issue_result_count_invalid")
        return tuple(_IssueRow(*row) for row in rows)

    @staticmethod
    def _core_ref_map(core_payload: dict[str, object]) -> dict[tuple[str, str], dict[str, object]]:
        refs = core_payload.get("source_refs")
        if not isinstance(refs, list):
            raise ReleaseVerdictRepositoryError("core_source_refs_invalid")
        result: dict[tuple[str, str], dict[str, object]] = {}
        for ref in refs:
            if not isinstance(ref, dict):
                raise ReleaseVerdictRepositoryError("core_source_refs_invalid")
            kind = ref.get("source_kind")
            source_id = ref.get("source_id")
            if not isinstance(kind, str) or not isinstance(source_id, str):
                raise ReleaseVerdictRepositoryError("core_source_refs_invalid")
            key = (kind, source_id)
            if key in result:
                raise ReleaseVerdictRepositoryError("core_source_refs_invalid")
            result[key] = ref
        return result

    @staticmethod
    def _require_current_core_issue_refs(
        core_payload: dict[str, object], rows: tuple[_IssueRow, ...]
    ) -> None:
        refs = ReleaseVerdictRepository._core_ref_map(core_payload)
        candidate_ref_count = sum(
            kind
            in {
                "release_candidate_issue_binding",
                "release_issue",
                "release_finding",
            }
            for kind, _ in refs
        )
        inventories = core_payload.get("source_inventory")
        candidate_inventory = (
            next(
                (
                    item
                    for item in inventories
                    if isinstance(item, dict) and item.get("section_code") == "candidate_issues"
                ),
                None,
            )
            if isinstance(inventories, list)
            else None
        )
        if (
            candidate_inventory is None
            or candidate_inventory.get("item_count") != candidate_ref_count
            or candidate_inventory.get("presence_code") not in {"present", "present_zero_rows"}
        ):
            raise ReleaseVerdictRepositoryError("candidate_issue_inventory_mismatch")
        if sum(kind == "release_issue" for kind, _ in refs) != len(rows) or sum(
            kind == "release_candidate_issue_binding" for kind, _ in refs
        ) != len(rows):
            raise ReleaseVerdictRepositoryError("candidate_issue_membership_mismatch")
        for row in rows:
            issue_ref = project_source_record("release_issue", row.issue)
            binding_ref = project_source_record("release_candidate_issue_binding", row.binding)
            if refs.get((issue_ref.source_kind, str(issue_ref.source_id))) != issue_ref.as_dict():
                raise ReleaseVerdictRepositoryError("core_issue_projection_stale")
            if (
                refs.get((binding_ref.source_kind, str(binding_ref.source_id)))
                != binding_ref.as_dict()
            ):
                raise ReleaseVerdictRepositoryError("core_issue_binding_stale")
            if row.risk is not None:
                risk_ref = project_source_record("risk_acceptance_record", row.risk)
                if refs.get((risk_ref.source_kind, str(risk_ref.source_id))) != risk_ref.as_dict():
                    raise ReleaseVerdictRepositoryError("core_risk_projection_stale")

    @staticmethod
    def _risk_is_exact(candidate: ReleaseCandidate, row: _IssueRow) -> bool:
        risk = row.risk
        if risk is None:
            return False
        from datetime import date

        return bool(
            risk.tenant_id == candidate.tenant_id
            and risk.project_id == candidate.project_id
            and risk.release_id == candidate.release_ref
            and risk.subject_type == "release_issue"
            and risk.issue_id == str(row.issue.id)
            and risk.status == "active"
            and risk.expiry_date >= date.today()
            and risk.blocking_category is None
        )

    def _input(
        self, candidate: ReleaseCandidate, rows: tuple[_IssueRow, ...]
    ) -> ReleaseVerdictInput:
        return ReleaseVerdictInput(
            assembly_complete=True,
            inventory_complete=True,
            issue_binding_exact=True,
            input_current=True,
            issues=tuple(
                IssueDisposition(
                    binding_id=str(row.binding.id),
                    issue_id=str(row.issue.id),
                    status=row.issue.status,
                    trusted_provenance=(
                        row.issue.source_provenance == TRUSTED_FINDING_PROVENANCE
                        and row.issue.source_finding_id is not None
                    ),
                    blocking=row.issue.blocking,
                    hard_blocker=is_hard_blocker(row.issue.severity, row.issue.blocking_category),
                    exact_risk_acceptance=self._risk_is_exact(candidate, row),
                    # No verified human/approval-matrix authority tier exists in Slice 50.
                    risk_authority_verified=False,
                )
                for row in rows
            ),
        )

    async def evaluate_and_record(
        self,
        *,
        project_id: uuid.UUID,
        release_candidate_id: uuid.UUID,
        evidence_pack_id: uuid.UUID,
        actor: str,
    ) -> ReleaseVerdict:
        candidate = await self._candidate(project_id, release_candidate_id)
        packs = EvidencePackRepository(self.session, self.context)
        core = await packs.audit_pack(evidence_pack_id)
        pack = await packs.get(evidence_pack_id)
        if (
            pack is None
            or pack.project_id != project_id
            or pack.release_candidate_id != release_candidate_id
            or pack.assembly_status != "complete"
        ):
            raise ReleaseVerdictRepositoryError("exact_complete_evidence_core_required")
        rows = await self._issue_rows(release_candidate_id)
        self._require_current_core_issue_refs(core.payload, rows)
        current_binding_digest = digest_bytes(
            canonical_json_bytes(
                [
                    project_source_record(
                        "release_candidate_issue_binding", row.binding
                    ).projection_digest
                    for row in rows
                ]
            )
        )
        if current_binding_digest != pack.issue_binding_digest:
            raise ReleaseVerdictRepositoryError("core_issue_binding_digest_stale")
        input_value = self._input(candidate, rows)
        decision = evaluate_release_verdict(input_value)
        input_digest = canonical_input_digest(input_value)
        await self.session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        run = ReleaseVerdictRun(
            id=uuid.uuid4(),
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_candidate_id=release_candidate_id,
            evidence_pack_id=evidence_pack_id,
            input_contract_version=INPUT_CONTRACT_VERSION,
            verdict_contract_version=VERDICT_CONTRACT_VERSION,
            projection_contract_version=PROJECTION_CONTRACT_VERSION,
            input_digest=input_digest,
            core_content_hash=pack.core_content_hash,
            verdict_contract_hash=VERDICT_CONTRACT_HASH,
            execution_status="succeeded",
            execution_provenance=EXECUTION_PROVENANCE,
            failure_code=None,
        )
        active = tuple(
            row for row in input_value.issues if row.status not in {"resolved", "superseded"}
        )
        verdict = ReleaseVerdict(
            id=uuid.uuid4(),
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            run_id=run.id,
            release_candidate_id=release_candidate_id,
            evidence_pack_id=evidence_pack_id,
            audit_checkpoint_id=pack.audit_checkpoint_id,
            input_digest=input_digest,
            core_content_hash=pack.core_content_hash,
            issue_binding_digest=pack.issue_binding_digest,
            source_set_digest=pack.source_set_digest,
            traceability_digest=pack.traceability_digest,
            verdict_contract_hash=VERDICT_CONTRACT_HASH,
            input_contract_version=INPUT_CONTRACT_VERSION,
            verdict_contract_version=VERDICT_CONTRACT_VERSION,
            projection_contract_version=PROJECTION_CONTRACT_VERSION,
            decision_scope=DECISION_SCOPE,
            execution_provenance=EXECUTION_PROVENANCE,
            issue_count=len(rows),
            missing_evidence_count=sum(
                not issue.trusted_provenance for issue in input_value.issues
            ),
            blocking_issue_count=sum(issue.blocking or issue.hard_blocker for issue in active),
            limitation_count=sum(not issue.blocking and not issue.hard_blocker for issue in active),
            unverified_authority_count=sum(
                (not issue.blocking and not issue.hard_blocker)
                and (not issue.exact_risk_acceptance or not issue.risk_authority_verified)
                for issue in active
            ),
        )
        self.session.add(run)
        await self.session.flush([run])
        self.session.add(verdict)
        await self.session.flush([verdict])
        for ordinal, (row, disposition) in enumerate(zip(rows, input_value.issues, strict=True), 1):
            issue_ref = project_source_record("release_issue", row.issue)
            risk_ref = (
                project_source_record("risk_acceptance_record", row.risk)
                if row.risk is not None
                else None
            )
            self.session.add(
                ReleaseVerdictIssueResult(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    verdict_id=verdict.id,
                    release_candidate_id=release_candidate_id,
                    binding_id=row.binding.id,
                    issue_id=row.issue.id,
                    risk_acceptance_record_id=row.issue.risk_acceptance_record_id,
                    ordinal=ordinal,
                    issue_category=row.issue.issue_category,
                    severity=row.issue.severity,
                    blocking_category=row.issue.blocking_category,
                    source_finding_id=row.issue.source_finding_id,
                    issue_status=row.issue.status,
                    source_provenance=row.issue.source_provenance,
                    trusted_provenance=disposition.trusted_provenance,
                    blocking=disposition.blocking,
                    hard_blocker=disposition.hard_blocker,
                    exact_risk_acceptance=disposition.exact_risk_acceptance,
                    risk_authority_verified=False,
                    issue_projection_digest=issue_ref.projection_digest,
                    risk_projection_digest=(
                        risk_ref.projection_digest if risk_ref is not None else None
                    ),
                )
            )
        await self.session.flush()
        await self.session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await audit_record(
            self.session,
            action="release.verdict_recorded",
            actor=actor,
            target=str(verdict.id),
            payload={
                "project_id": str(project_id),
                "release_candidate_id": str(release_candidate_id),
                "evidence_pack_id": str(evidence_pack_id),
                "spec_verdict": decision.spec_verdict,
                "canonical_verdict": decision.canonical_verdict,
                "reason_code": decision.reason_code,
                "decision_scope": DECISION_SCOPE,
                "issue_count": len(rows),
                "gate_eligible": decision.gate_eligible,
            },
        )
        await self.session.refresh(verdict)
        if (
            verdict.spec_verdict != decision.spec_verdict
            or verdict.canonical_verdict != decision.canonical_verdict
            or verdict.reason_code != decision.reason_code
            or verdict.gate_eligible != decision.gate_eligible
        ):
            raise ReleaseVerdictRepositoryError("database_verdict_disagrees_with_contract")
        return verdict

    async def record_failed_attempt(
        self,
        *,
        project_id: uuid.UUID,
        release_candidate_id: uuid.UUID,
        evidence_pack_id: uuid.UUID,
        failure_code: str,
        actor: str,
    ) -> ReleaseVerdictRun:
        """Append a bounded failed attempt; it never creates a verdict attestation."""

        if not isinstance(failure_code, str) or not failure_code.strip() or len(failure_code) > 128:
            raise ReleaseVerdictRepositoryError("failure_code_invalid")
        candidate = await self._candidate(project_id, release_candidate_id)
        pack = await EvidencePackRepository(self.session, self.context).get(evidence_pack_id)
        if (
            pack is None
            or pack.project_id != project_id
            or pack.release_candidate_id != release_candidate_id
        ):
            raise ReleaseVerdictRepositoryError("exact_evidence_core_required")
        rows = await self._issue_rows(candidate.id)
        input_digest = canonical_input_digest(self._input(candidate, rows))
        await self.session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        run = ReleaseVerdictRun(
            id=uuid.uuid4(),
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            release_candidate_id=release_candidate_id,
            evidence_pack_id=evidence_pack_id,
            input_contract_version=INPUT_CONTRACT_VERSION,
            verdict_contract_version=VERDICT_CONTRACT_VERSION,
            projection_contract_version=PROJECTION_CONTRACT_VERSION,
            input_digest=input_digest,
            core_content_hash=pack.core_content_hash,
            verdict_contract_hash=VERDICT_CONTRACT_HASH,
            execution_status="failed",
            execution_provenance=EXECUTION_PROVENANCE,
            failure_code=failure_code,
        )
        self.session.add(run)
        await self.session.flush([run])
        await self.session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await audit_record(
            self.session,
            action="release.verdict_failed",
            actor=actor,
            target=str(run.id),
            payload={
                "project_id": str(project_id),
                "release_candidate_id": str(release_candidate_id),
                "evidence_pack_id": str(evidence_pack_id),
                "failure_code": failure_code,
                "execution_status": "failed",
            },
        )
        return run

    async def _latest_candidate(self, project_id: uuid.UUID) -> ReleaseCandidate | None:
        return (
            await self.session.execute(
                select(ReleaseCandidate)
                .where(
                    ReleaseCandidate.project_id == project_id,
                    ReleaseCandidate.tenant_id == self.context.tenant_id,
                    ReleaseCandidate.status == "frozen",
                )
                .order_by(ReleaseCandidate.frozen_at.desc(), ReleaseCandidate.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def coverage_for_project(self, project_id: uuid.UUID) -> ReleaseVerdictCoverage:
        candidate = await self._latest_candidate(project_id)
        if candidate is None:
            return ReleaseVerdictCoverage()
        pack_run = (
            await self.session.execute(
                select(EvidencePackGenerationRun)
                .where(
                    EvidencePackGenerationRun.release_candidate_id == candidate.id,
                    EvidencePackGenerationRun.project_id == project_id,
                    EvidencePackGenerationRun.tenant_id == self.context.tenant_id,
                )
                .order_by(
                    EvidencePackGenerationRun.created_at.desc(), EvidencePackGenerationRun.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if pack_run is None:
            return ReleaseVerdictCoverage()
        pack = (
            await self.session.execute(
                select(EvidencePack).where(EvidencePack.generation_run_id == pack_run.id)
            )
        ).scalar_one_or_none()
        if pack is None:
            return ReleaseVerdictCoverage(
                verdict_attempt_failed=pack_run.execution_status in {"failed", "refused"},
                reason_code=pack_run.failure_code,
            )
        audited = False
        try:
            await EvidencePackRepository(self.session, self.context).audit_pack(pack.id)
            audited = (
                pack.assembly_status == "complete" and pack_run.execution_status == "succeeded"
            )
        except EvidencePackRepositoryError:
            audited = False
        run = (
            await self.session.execute(
                select(ReleaseVerdictRun)
                .where(
                    ReleaseVerdictRun.release_candidate_id == candidate.id,
                    ReleaseVerdictRun.project_id == project_id,
                    ReleaseVerdictRun.tenant_id == self.context.tenant_id,
                )
                .order_by(ReleaseVerdictRun.created_at.desc(), ReleaseVerdictRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return ReleaseVerdictCoverage(evidence_core_present=True, evidence_core_audited=audited)
        verdict = (
            await self.session.execute(
                select(ReleaseVerdict).where(ReleaseVerdict.run_id == run.id)
            )
        ).scalar_one_or_none()
        rows = await self._issue_rows(candidate.id)
        current_digest = canonical_input_digest(self._input(candidate, rows))
        current = bool(
            run.evidence_pack_id == pack.id
            and run.core_content_hash == pack.core_content_hash
            and run.input_digest == current_digest
            and run.verdict_contract_hash == VERDICT_CONTRACT_HASH
        )
        consistent = bool(
            verdict is not None
            and verdict.decision_scope == DECISION_SCOPE
            and verdict.execution_provenance == EXECUTION_PROVENANCE
            and verdict.input_digest == current_digest
            and verdict.core_content_hash == pack.core_content_hash
        )
        return ReleaseVerdictCoverage(
            evidence_core_present=True,
            evidence_core_audited=audited,
            verdict_run_present=True,
            verdict_attempt_failed=run.execution_status != "succeeded",
            verdict_binding_current=current,
            verdict_evidence_consistent=consistent,
            spec_verdict=verdict.spec_verdict if verdict is not None else None,
            gate_eligible=verdict.gate_eligible if verdict is not None else False,
            reason_code=verdict.reason_code if verdict is not None else run.failure_code,
            decision_scope=verdict.decision_scope if verdict is not None else None,
            execution_provenance=(
                verdict.execution_provenance if verdict is not None else run.execution_provenance
            ),
        )


__all__ = [
    "ReleaseVerdictCoverage",
    "ReleaseVerdictRepository",
    "ReleaseVerdictRepositoryError",
]
