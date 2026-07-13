"""Immutable tenant-owned Slice-50 release-verdict attempts and attestations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_HASH = r"^sha256:[0-9a-f]{64}$"


class ReleaseVerdictRun(Base):
    __tablename__ = "release_verdict_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        CheckConstraint(
            "input_contract_version='slice50.release_verdict_input.v1' "
            "AND verdict_contract_version='slice50.release_verdict.v1' "
            "AND projection_contract_version='slice50.verdict_projection.v1'",
            name="contracts",
        ),
        CheckConstraint(
            f"input_digest ~ '{_HASH}' AND verdict_contract_hash ~ '{_HASH}' "
            f"AND (core_content_hash IS NULL OR core_content_hash ~ '{_HASH}')",
            name="hashes",
        ),
        CheckConstraint("execution_status IN ('succeeded','failed','refused')", name="status"),
        CheckConstraint("execution_provenance='system_derived_release_verdict'", name="provenance"),
        CheckConstraint(
            "(execution_status='succeeded' AND evidence_pack_id IS NOT NULL "
            "AND core_content_hash IS NOT NULL AND failure_code IS NULL) OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL)",
            name="result_shape",
        ),
        CheckConstraint(
            "failure_code IS NULL OR (char_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code)<>'')",
            name="failure_code",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_rvr_id_project_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    input_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    projection_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    core_content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ReleaseVerdict(Base):
    __tablename__ = "release_verdicts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "release_verdict_runs.id",
                "release_verdict_runs.project_id",
                "release_verdict_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
            name="audit_checkpoint",
        ),
        CheckConstraint(
            "input_contract_version='slice50.release_verdict_input.v1' "
            "AND verdict_contract_version='slice50.release_verdict.v1' "
            "AND projection_contract_version='slice50.verdict_projection.v1' "
            "AND decision_scope='known_bound_issue_disposition' "
            "AND execution_provenance='system_derived_release_verdict'",
            name="contracts",
        ),
        CheckConstraint(
            f"input_digest ~ '{_HASH}' AND core_content_hash ~ '{_HASH}' "
            f"AND issue_binding_digest ~ '{_HASH}' AND source_set_digest ~ '{_HASH}' "
            f"AND traceability_digest ~ '{_HASH}' AND verdict_contract_hash ~ '{_HASH}'",
            name="hashes",
        ),
        CheckConstraint(
            "issue_count BETWEEN 0 AND 10000 AND missing_evidence_count BETWEEN 0 AND issue_count "
            "AND blocking_issue_count BETWEEN 0 AND issue_count "
            "AND limitation_count BETWEEN 0 AND issue_count "
            "AND unverified_authority_count BETWEEN 0 AND limitation_count",
            name="counts",
        ),
        UniqueConstraint("run_id", name="uq_release_verdicts_run"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_rv_id_project_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audit_checkpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    core_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    issue_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    source_set_digest: Mapped[str] = mapped_column(Text, nullable=False)
    traceability_digest: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    input_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    projection_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    decision_scope: Mapped[str] = mapped_column(Text, nullable=False)
    execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, nullable=False)
    limitation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unverified_authority_count: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_verdict: Mapped[str] = mapped_column(
        Text,
        Computed(
            "CASE WHEN missing_evidence_count>0 THEN 'failed_missing_evidence' "
            "WHEN blocking_issue_count>0 THEN 'failed_blocking_issue' "
            "WHEN unverified_authority_count>0 THEN 'requires_human_decision' "
            "WHEN limitation_count>0 THEN 'passed_with_limitations' ELSE 'passed' END"
        ),
        nullable=False,
    )
    canonical_verdict: Mapped[str] = mapped_column(
        Text,
        Computed(
            "CASE WHEN missing_evidence_count>0 OR blocking_issue_count>0 THEN 'failed' "
            "WHEN unverified_authority_count>0 THEN 'blocked' "
            "WHEN limitation_count>0 THEN 'passed_with_accepted_risk' ELSE 'passed' END"
        ),
        nullable=False,
    )
    reason_code: Mapped[str] = mapped_column(
        Text,
        Computed(
            "CASE WHEN missing_evidence_count>0 THEN 'bound_issue_provenance_incomplete' "
            "WHEN blocking_issue_count>0 THEN 'open_blocking_or_hard_refusal_issue' "
            "WHEN unverified_authority_count>0 THEN 'risk_acceptance_authority_unverified' "
            "WHEN limitation_count>0 THEN 'bound_release_limitations_authoritatively_accepted' "
            "ELSE 'bound_release_issue_disposition_clean' END"
        ),
        nullable=False,
    )
    gate_eligible: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "missing_evidence_count=0 AND blocking_issue_count=0 AND unverified_authority_count=0"
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ReleaseVerdictIssueResult(Base):
    __tablename__ = "release_verdict_issue_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
            name="verdict_project_tenant",
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        ForeignKeyConstraint(
            ["issue_id", "tenant_id"],
            ["release_issues.id", "release_issues.tenant_id"],
            ondelete="RESTRICT",
            name="issue_tenant",
        ),
        ForeignKeyConstraint(
            ["risk_acceptance_record_id", "tenant_id"],
            ["risk_acceptance_records.id", "risk_acceptance_records.tenant_id"],
            ondelete="RESTRICT",
            name="risk_tenant",
        ),
        CheckConstraint(
            "issue_status IN ('open','resolved','accepted','superseded')", name="status"
        ),
        CheckConstraint(
            "issue_category IN ('security','shortcut','test_or_acceptance','cost',"
            "'deployment','rollback','monitoring','evidence','approval','other') "
            "AND severity IN ('low','medium','high','critical')",
            name="taxonomy",
        ),
        CheckConstraint(
            "char_length(source_provenance) BETWEEN 1 AND 128 AND btrim(source_provenance)<>''",
            name="provenance",
        ),
        CheckConstraint(
            f"issue_projection_digest ~ '{_HASH}' AND "
            f"(risk_projection_digest IS NULL OR risk_projection_digest ~ '{_HASH}')",
            name="digests",
        ),
        CheckConstraint(
            "ordinal BETWEEN 1 AND 10000 AND "
            "(exact_risk_acceptance OR (risk_acceptance_record_id IS NULL "
            "AND risk_projection_digest IS NULL AND NOT risk_authority_verified))",
            name="shape",
        ),
        UniqueConstraint("verdict_id", "binding_id", name="uq_rvir_verdict_binding"),
        UniqueConstraint("verdict_id", "ordinal", name="uq_rvir_verdict_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    binding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("release_candidate_issue_bindings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    risk_acceptance_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    blocking_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_finding_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    issue_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    trusted_provenance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hard_blocker: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exact_risk_acceptance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_authority_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    issue_projection_digest: Mapped[str] = mapped_column(Text, nullable=False)
    risk_projection_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
