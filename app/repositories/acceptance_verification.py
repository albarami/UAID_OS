"""Repository-controlled Slice-46 structural acceptance verification."""

from __future__ import annotations

import hashlib
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.audit import record as audit_record
from app.models.acceptance_verification import (
    AcceptanceCriterionAuthorshipRecord,
    AcceptanceVerificationResult,
    AcceptanceVerificationRun,
)
from app.models.intake_artifact import IntakeArtifact
from app.tenancy import TenantContext, TenantScopedRepository
from app.verify.acceptance import (
    AUTHORSHIP_CONTRACT_VERSION,
    SCHEMA_VERSION,
    AuthorshipEvidence,
    Gate8Evidence,
    evaluate_authorship,
    verifier_contract_hash,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _digest(material: str) -> str:
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()


class AcceptanceVerificationRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AcceptanceCriterionAuthorshipRecord)

    async def _current_record(
        self, project_id: uuid.UUID, criterion_id: uuid.UUID
    ) -> AcceptanceCriterionAuthorshipRecord | None:
        return (
            await self.session.execute(
                select(AcceptanceCriterionAuthorshipRecord)
                .where(
                    AcceptanceCriterionAuthorshipRecord.tenant_id == self.context.tenant_id,
                    AcceptanceCriterionAuthorshipRecord.project_id == project_id,
                    AcceptanceCriterionAuthorshipRecord.acceptance_criterion_id == criterion_id,
                )
                .order_by(
                    AcceptanceCriterionAuthorshipRecord.sequence.desc(),
                    AcceptanceCriterionAuthorshipRecord.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _check_digest(value: str) -> None:
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            raise ValueError("evidence_reference must be a canonical sha256 digest")

    async def record_independent_approval(
        self,
        *,
        project_id: uuid.UUID,
        acceptance_criterion_id: uuid.UUID,
        generator_instance_id: uuid.UUID,
        reviewer_instance_id: uuid.UUID,
        approval_id: uuid.UUID,
        evidence_reference: str,
        actor: str,
    ) -> AcceptanceCriterionAuthorshipRecord:
        self._check_digest(evidence_reference)
        current = await self._current_record(project_id, acceptance_criterion_id)
        row = AcceptanceCriterionAuthorshipRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            acceptance_criterion_id=acceptance_criterion_id,
            supersedes_record_id=current.id if current else None,
            sequence=(current.sequence + 1) if current else 1,
            authorship_status="system_authored_independent_approved",
            authorship_provenance="db_verified_independent_agent_lineage",
            source_kind="agent_generated",
            generator_instance_id=generator_instance_id,
            reviewer_instance_id=reviewer_instance_id,
            approval_id=approval_id,
            approval_basis="independent_agent_lineage",
            evidence_reference=evidence_reference,
        )
        self.session.add(row)
        await self.session.flush()
        await audit_record(
            self.session,
            action="acceptance.authorship_recorded",
            actor=actor,
            target=f"acceptance_authorship:{row.id}",
            payload={
                "project_id": str(project_id),
                "acceptance_criterion_id": str(acceptance_criterion_id),
                "authorship_status": row.authorship_status,
                "authorship_provenance": row.authorship_provenance,
                "approval_basis": row.approval_basis,
                "sequence": row.sequence,
            },
        )
        return row

    async def record_extraction_unapproved(
        self,
        *,
        project_id: uuid.UUID,
        acceptance_criterion_id: uuid.UUID,
        extraction_proposal_id: uuid.UUID,
        evidence_reference: str,
        actor: str,
    ) -> AcceptanceCriterionAuthorshipRecord:
        self._check_digest(evidence_reference)
        current = await self._current_record(project_id, acceptance_criterion_id)
        row = AcceptanceCriterionAuthorshipRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            acceptance_criterion_id=acceptance_criterion_id,
            supersedes_record_id=current.id if current else None,
            sequence=(current.sequence + 1) if current else 1,
            authorship_status="system_authored_unapproved",
            authorship_provenance="caller_supplied_unverified",
            source_kind="extraction_promoted",
            extraction_proposal_id=extraction_proposal_id,
            evidence_reference=evidence_reference,
        )
        self.session.add(row)
        await self.session.flush()
        await audit_record(
            self.session,
            action="acceptance.authorship_recorded",
            actor=actor,
            target=f"acceptance_authorship:{row.id}",
            payload={
                "project_id": str(project_id),
                "acceptance_criterion_id": str(acceptance_criterion_id),
                "authorship_status": row.authorship_status,
                "authorship_provenance": row.authorship_provenance,
                "sequence": row.sequence,
            },
        )
        return row

    async def record_dispute(
        self,
        *,
        project_id: uuid.UUID,
        acceptance_criterion_id: uuid.UUID,
        evidence_reference: str,
        actor: str,
    ) -> AcceptanceCriterionAuthorshipRecord:
        self._check_digest(evidence_reference)
        current = await self._current_record(project_id, acceptance_criterion_id)
        if current is None:
            raise ValueError("a dispute must supersede an existing authorship record")
        row = AcceptanceCriterionAuthorshipRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            acceptance_criterion_id=acceptance_criterion_id,
            supersedes_record_id=current.id,
            sequence=current.sequence + 1,
            authorship_status="disputed",
            authorship_provenance="caller_supplied_unverified",
            source_kind=current.source_kind,
            extraction_proposal_id=current.extraction_proposal_id,
            generator_instance_id=current.generator_instance_id,
            reviewer_instance_id=current.reviewer_instance_id,
            approval_id=current.approval_id,
            approval_basis=current.approval_basis,
            evidence_reference=evidence_reference,
        )
        self.session.add(row)
        await self.session.flush()
        await audit_record(
            self.session,
            action="acceptance.authorship_disputed",
            actor=actor,
            target=f"acceptance_authorship:{row.id}",
            payload={
                "project_id": str(project_id),
                "acceptance_criterion_id": str(acceptance_criterion_id),
                "authorship_status": row.authorship_status,
                "sequence": row.sequence,
            },
        )
        return row

    async def record_failed_verification(
        self, project_id: uuid.UUID, *, failure_code: str, actor: str
    ) -> AcceptanceVerificationRun:
        if not isinstance(failure_code, str) or not failure_code.strip() or len(failure_code) > 128:
            raise ValueError("failure_code must be a non-blank bounded string")
        scope = await self._scope(project_id)
        if not scope:
            raise ValueError("acceptance verification scope is empty")
        records = await self._current_records(project_id, scope)
        scope_hash, authorship_hash = self._binding(scope, records)
        run = AcceptanceVerificationRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            scope_digest=scope_hash,
            authorship_digest=authorship_hash,
            schema_version=SCHEMA_VERSION,
            verifier_contract_hash=verifier_contract_hash(),
            execution_status="failed",
            execution_provenance="system_executed_structural",
            failure_code=failure_code,
            reported_scope_count=0,
            reported_eligible_count=0,
            reported_unapproved_count=0,
            reported_disputed_count=0,
            reported_missing_or_untrusted_count=0,
            reported_controls_failed_count=0,
            evidence_consistent=False,
            verdict="blocked",
        )
        self.session.add(run)
        await self.session.flush()
        await audit_record(
            self.session,
            action="acceptance.verification_failed",
            actor=actor,
            target=f"acceptance_verification_run:{run.id}",
            payload={"project_id": str(project_id), "failure_code": failure_code},
        )
        return run

    async def _scope(self, project_id: uuid.UUID) -> list[IntakeArtifact]:
        parent = aliased(IntakeArtifact)
        return list(
            (
                await self.session.execute(
                    select(IntakeArtifact)
                    .join(
                        parent,
                        (parent.id == IntakeArtifact.parent_id)
                        & (parent.project_id == IntakeArtifact.project_id)
                        & (parent.tenant_id == IntakeArtifact.tenant_id),
                    )
                    .where(
                        IntakeArtifact.tenant_id == self.context.tenant_id,
                        IntakeArtifact.project_id == project_id,
                        IntakeArtifact.kind == "acceptance_criterion",
                        parent.kind == "requirement",
                    )
                    .order_by(IntakeArtifact.id)
                )
            ).scalars()
        )

    async def _current_records(
        self, project_id: uuid.UUID, scope: list[IntakeArtifact]
    ) -> dict[uuid.UUID, AcceptanceCriterionAuthorshipRecord]:
        if not scope:
            return {}
        rows = list(
            (
                await self.session.execute(
                    select(AcceptanceCriterionAuthorshipRecord)
                    .where(
                        AcceptanceCriterionAuthorshipRecord.tenant_id == self.context.tenant_id,
                        AcceptanceCriterionAuthorshipRecord.project_id == project_id,
                        AcceptanceCriterionAuthorshipRecord.acceptance_criterion_id.in_(
                            [item.id for item in scope]
                        ),
                    )
                    .order_by(
                        AcceptanceCriterionAuthorshipRecord.acceptance_criterion_id,
                        AcceptanceCriterionAuthorshipRecord.sequence.desc(),
                        AcceptanceCriterionAuthorshipRecord.id.desc(),
                    )
                )
            ).scalars()
        )
        current: dict[uuid.UUID, AcceptanceCriterionAuthorshipRecord] = {}
        for row in rows:
            current.setdefault(row.acceptance_criterion_id, row)
        return current

    @staticmethod
    def _binding(
        scope: list[IntakeArtifact],
        records: dict[uuid.UUID, AcceptanceCriterionAuthorshipRecord],
    ) -> tuple[str, str]:
        ordered = sorted(str(item.id) for item in scope)
        scope_hash = _digest(",".join(ordered))
        authorship_hash = _digest(
            ",".join(
                f"{criterion_id}:{records[uuid.UUID(criterion_id)].id if uuid.UUID(criterion_id) in records else 'missing'}"
                for criterion_id in ordered
            )
        )
        return scope_hash, authorship_hash

    @staticmethod
    def _result_for(
        criterion_id: uuid.UUID, record: AcceptanceCriterionAuthorshipRecord | None
    ) -> tuple[str, str]:
        if record is None:
            return "missing", "authorship_missing"
        result = evaluate_authorship(
            AuthorshipEvidence(
                acceptance_criterion_id=str(criterion_id),
                authorship_status=record.authorship_status,
                authorship_provenance=record.authorship_provenance,
                source_kind=record.source_kind,
                approval_basis=record.approval_basis,
                source_db_proven=True,
                approval_db_bound=record.approval_id is not None,
                reviewer_active=record.reviewer_instance_id is not None,
                reviewer_qualified=record.reviewer_instance_id is not None,
                distinct_blueprint=record.reviewer_instance_id is not None,
                distinct_version=record.reviewer_instance_id is not None,
                distinct_model_route=record.reviewer_instance_id is not None,
                current_record=True,
            )
        )
        return result.eligibility_status, result.reason_code

    async def verify_project(
        self, project_id: uuid.UUID, *, actor: str
    ) -> AcceptanceVerificationRun:
        scope = await self._scope(project_id)
        if not scope:
            raise ValueError("acceptance verification scope is empty")
        records = await self._current_records(project_id, scope)
        decisions = {
            item.id: self._result_for(item.id, records.get(item.id)) for item in scope
        }
        scope_hash, authorship_hash = self._binding(scope, records)
        counts = {
            key: sum(status == key for status, _reason in decisions.values())
            for key in ("eligible", "unapproved", "disputed", "missing", "untrusted", "controls_failed")
        }
        eligible = counts["eligible"] == len(scope)
        run = AcceptanceVerificationRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            scope_digest=scope_hash,
            authorship_digest=authorship_hash,
            schema_version=SCHEMA_VERSION,
            verifier_contract_hash=verifier_contract_hash(),
            execution_status="succeeded",
            execution_provenance="system_executed_structural",
            failure_code=None,
            reported_scope_count=len(scope),
            reported_eligible_count=counts["eligible"],
            reported_unapproved_count=counts["unapproved"],
            reported_disputed_count=counts["disputed"],
            reported_missing_or_untrusted_count=counts["missing"] + counts["untrusted"],
            reported_controls_failed_count=counts["controls_failed"],
            evidence_consistent=True,
            verdict="eligible" if eligible else "blocked",
        )
        self.session.add(run)
        await self.session.flush()
        for item in scope:
            record = records.get(item.id)
            status, reason = decisions[item.id]
            self.session.add(
                AcceptanceVerificationResult(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    acceptance_verification_run_id=run.id,
                    acceptance_criterion_id=item.id,
                    authorship_record_id=record.id if record else None,
                    authorship_status=record.authorship_status if record else None,
                    authorship_provenance=record.authorship_provenance if record else None,
                    source_kind=record.source_kind if record else None,
                    eligibility_status=status,
                    reason_code=reason,
                )
            )
        await self.session.flush()
        await audit_record(
            self.session,
            action="acceptance.verification_completed",
            actor=actor,
            target=f"acceptance_verification_run:{run.id}",
            payload={
                "project_id": str(project_id),
                "schema_version": SCHEMA_VERSION,
                "authorship_contract_version": AUTHORSHIP_CONTRACT_VERSION,
                "scope_count": len(scope),
                "eligible_count": counts["eligible"],
                "unapproved_count": counts["unapproved"],
                "disputed_count": counts["disputed"],
                "missing_or_untrusted_count": counts["missing"] + counts["untrusted"],
                "verdict": run.verdict,
            },
        )
        return run

    async def coverage_for_project(self, project_id: uuid.UUID) -> Gate8Evidence:
        scope = await self._scope(project_id)
        if not scope:
            return Gate8Evidence(scope_resolved=True, binding_resolved=False)
        records = await self._current_records(project_id, scope)
        scope_hash, authorship_hash = self._binding(scope, records)
        latest = (
            await self.session.execute(
                select(AcceptanceVerificationRun)
                .where(
                    AcceptanceVerificationRun.tenant_id == self.context.tenant_id,
                    AcceptanceVerificationRun.project_id == project_id,
                    AcceptanceVerificationRun.scope_digest == scope_hash,
                    AcceptanceVerificationRun.authorship_digest == authorship_hash,
                    AcceptanceVerificationRun.verifier_contract_hash == verifier_contract_hash(),
                )
                .order_by(AcceptanceVerificationRun.created_at.desc(), AcceptanceVerificationRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return Gate8Evidence(scope_resolved=True, binding_resolved=True, scope_count=len(scope))
        results = list(
            (
                await self.session.execute(
                    select(AcceptanceVerificationResult).where(
                        AcceptanceVerificationResult.acceptance_verification_run_id == latest.id,
                        AcceptanceVerificationResult.tenant_id == self.context.tenant_id,
                    )
                )
            ).scalars()
        )
        def count(status: str) -> int:
            return sum(row.eligibility_status == status for row in results)

        return Gate8Evidence(
            scope_resolved=True,
            binding_resolved=True,
            scope_count=len(scope),
            run_present=True,
            verification_failed=latest.execution_status in {"failed", "refused"},
            missing_authorship_count=count("missing"),
            untrusted_count=count("untrusted"),
            disputed_count=count("disputed"),
            unapproved_count=count("unapproved"),
            controls_failed_count=count("controls_failed"),
            eligible_count=count("eligible"),
            evidence_consistent=latest.evidence_consistent and len(results) == len(scope),
        )
