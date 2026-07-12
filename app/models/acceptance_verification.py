"""Tenant-owned append-only Slice-46 acceptance-authorship evidence."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AcceptanceCriterionAuthorshipRecord(Base):
    __tablename__ = "acceptance_criterion_authorship_records"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT", name="project_tenant"),
        ForeignKeyConstraint(["acceptance_criterion_id", "project_id", "tenant_id"], ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"], ondelete="RESTRICT", name="criterion_project_tenant"),
        ForeignKeyConstraint(["supersedes_record_id", "acceptance_criterion_id", "project_id", "tenant_id"], ["acceptance_criterion_authorship_records.id", "acceptance_criterion_authorship_records.acceptance_criterion_id", "acceptance_criterion_authorship_records.project_id", "acceptance_criterion_authorship_records.tenant_id"], ondelete="RESTRICT", name="supersedes_chain"),
        ForeignKeyConstraint(["generator_instance_id", "project_id", "tenant_id"], ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"], ondelete="RESTRICT", name="generator_project_tenant"),
        ForeignKeyConstraint(["reviewer_instance_id", "project_id", "tenant_id"], ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"], ondelete="RESTRICT", name="reviewer_project_tenant"),
        ForeignKeyConstraint(["approval_id", "project_id", "tenant_id"], ["approvals.id", "approvals.project_id", "approvals.tenant_id"], ondelete="RESTRICT", name="approval_project_tenant"),
        ForeignKeyConstraint(["extraction_proposal_id", "project_id", "tenant_id"], ["extraction_proposals.id", "extraction_proposals.project_id", "extraction_proposals.tenant_id"], ondelete="RESTRICT", name="extraction_proposal_project_tenant"),
        CheckConstraint("sequence > 0", name="sequence_positive"),
        CheckConstraint("authorship_status IN ('user_authored','user_authored_system_normalized','system_authored_unapproved','system_authored_human_approved','system_authored_independent_approved','disputed')", name="status_valid"),
        CheckConstraint("authorship_provenance IN ('caller_supplied_unverified','db_verified_independent_agent_lineage')", name="provenance_valid"),
        CheckConstraint("source_kind IN ('agent_generated','extraction_promoted')", name="source_kind_valid"),
        CheckConstraint("approval_basis IS NULL OR approval_basis IN ('human_owner','independent_agent_lineage')", name="approval_basis_valid"),
        CheckConstraint("evidence_reference ~ '^sha256:[0-9a-f]{64}$'", name="evidence_digest"),
        UniqueConstraint("id", "acceptance_criterion_id", "project_id", "tenant_id", name="uq_acar_chain_target"),
        UniqueConstraint("acceptance_criterion_id", "sequence", name="uq_acar_criterion_sequence"),
        UniqueConstraint("supersedes_record_id", name="uq_acar_supersedes_once"),
        Index("ix_acar_current", "tenant_id", "project_id", "acceptance_criterion_id", "sequence", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    acceptance_criterion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supersedes_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    authorship_status: Mapped[str] = mapped_column(Text, nullable=False)
    authorship_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    generator_instance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewer_instance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))


class AcceptanceVerificationRun(Base):
    __tablename__ = "acceptance_verification_runs"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT", name="project_tenant"),
        CheckConstraint("scope_digest ~ '^sha256:[0-9a-f]{64}$'", name="scope_digest"),
        CheckConstraint("authorship_digest ~ '^sha256:[0-9a-f]{64}$'", name="authorship_digest"),
        CheckConstraint("verifier_contract_hash ~ '^sha256:[0-9a-f]{64}$'", name="contract_hash"),
        CheckConstraint("schema_version = 'slice46.acceptance_verification.v1'", name="schema_version"),
        CheckConstraint("execution_status IN ('succeeded','failed','refused')", name="execution_status"),
        CheckConstraint("execution_provenance = 'system_executed_structural'", name="execution_provenance"),
        CheckConstraint("verdict IN ('eligible','blocked')", name="verdict"),
        CheckConstraint("failure_code IS NULL OR (octet_length(failure_code) BETWEEN 1 AND 128 AND btrim(failure_code) <> '')", name="failure_code_bounded"),
        CheckConstraint("reported_scope_count BETWEEN 0 AND 10000 AND reported_eligible_count BETWEEN 0 AND 10000 AND reported_unapproved_count BETWEEN 0 AND 10000 AND reported_disputed_count BETWEEN 0 AND 10000 AND reported_missing_or_untrusted_count BETWEEN 0 AND 10000 AND reported_controls_failed_count BETWEEN 0 AND 10000", name="counts_bounded"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_avr_id_project_tenant"),
        Index("ix_acceptance_verification_latest", "tenant_id", "project_id", "scope_digest", "authorship_digest", "verifier_contract_hash", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scope_digest: Mapped[str] = mapped_column(Text, nullable=False)
    authorship_digest: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    verifier_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_scope_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_eligible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_unapproved_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_disputed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_missing_or_untrusted_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_controls_failed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_consistent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))


class AcceptanceVerificationResult(Base):
    __tablename__ = "acceptance_verification_results"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT", name="project_tenant"),
        ForeignKeyConstraint(["acceptance_verification_run_id", "project_id", "tenant_id"], ["acceptance_verification_runs.id", "acceptance_verification_runs.project_id", "acceptance_verification_runs.tenant_id"], ondelete="RESTRICT", name="run_project_tenant"),
        ForeignKeyConstraint(["acceptance_criterion_id", "project_id", "tenant_id"], ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"], ondelete="RESTRICT", name="criterion_project_tenant"),
        ForeignKeyConstraint(["authorship_record_id", "acceptance_criterion_id", "project_id", "tenant_id"], ["acceptance_criterion_authorship_records.id", "acceptance_criterion_authorship_records.acceptance_criterion_id", "acceptance_criterion_authorship_records.project_id", "acceptance_criterion_authorship_records.tenant_id"], ondelete="RESTRICT", name="authorship_project_tenant"),
        UniqueConstraint("acceptance_verification_run_id", "acceptance_criterion_id", name="uq_avres_run_criterion"),
        CheckConstraint("eligibility_status IN ('eligible','missing','untrusted','unapproved','disputed','controls_failed')", name="eligibility_status"),
        CheckConstraint("octet_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code) <> ''", name="reason_code_bounded"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    acceptance_verification_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    acceptance_criterion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    authorship_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    authorship_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorship_provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()"))
