"""Immutable tenant-owned Slice-49 evidence-pack attempts and core assemblies."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
_SOURCE_KINDS = (
    "intake_artifact",
    "intake_provenance",
    "release_candidate_issue_binding",
    "risk_acceptance_record",
    "release_finding",
    "release_issue",
    "review_report",
    "test_oracle_run",
    "security_scan_run",
    "shortcut_detector_run",
    "acceptance_verification_run",
    "reviewer_quality_record",
)
_SECTIONS = (
    "scope",
    "traceability",
    "candidate_issues",
    "risk_acceptances",
    "review_reports",
    "test_oracles",
    "security_scans",
    "shortcut_detectors",
    "acceptance_verification",
    "reviewer_quality",
    "sanad_provenance",
    "audit_checkpoint",
)


class EvidencePackGenerationRun(Base):
    __tablename__ = "evidence_pack_generation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
            name="audit_checkpoint",
        ),
        CheckConstraint("schema_version='uaid.evidence_pack.v1.2'", name="schema_version"),
        CheckConstraint(
            "semantic_contract_version='slice49.evidence_pack.v1'",
            name="semantic_version",
        ),
        CheckConstraint(
            "projection_contract_version='slice49.evidence_projection.v1'",
            name="projection_version",
        ),
        CheckConstraint(
            "audit_contract_version='slice49.evidence_audit.v1'",
            name="audit_version",
        ),
        CheckConstraint(
            f"semantic_contract_hash ~ '{_HASH}' AND projection_contract_hash ~ '{_HASH}' "
            f"AND audit_contract_hash ~ '{_HASH}' AND release_ref_digest ~ '{_HASH}'",
            name="hashes",
        ),
        CheckConstraint(
            "execution_status IN ('succeeded','incomplete','failed','refused')",
            name="status",
        ),
        CheckConstraint(
            "execution_provenance='system_assembled_evidence_pack'",
            name="provenance",
        ),
        CheckConstraint(
            "(execution_status='succeeded' AND failure_code IS NULL "
            "AND missing_required_section_count=0 AND inconsistent_section_count=0) OR "
            "(execution_status='incomplete' AND failure_code IS NOT NULL "
            "AND (missing_required_section_count>0 OR inconsistent_section_count>0)) OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL)",
            name="result_shape",
        ),
        CheckConstraint(
            "failure_code IS NULL OR (char_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code)<>'')",
            name="failure_code",
        ),
        CheckConstraint(
            "missing_required_section_count BETWEEN 0 AND 12 "
            "AND inconsistent_section_count BETWEEN 0 AND 12 "
            "AND source_ref_count BETWEEN 0 AND 50000 "
            "AND traceability_edge_count BETWEEN 0 AND 50000 "
            "AND ((execution_status IN ('succeeded','incomplete') "
            "AND section_count=12 AND canonical_byte_count BETWEEN 2 AND 8388608) "
            "OR (execution_status IN ('failed','refused') "
            "AND section_count=0 AND canonical_byte_count=0))",
            name="counts",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_epgr_id_project_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audit_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    release_ref_digest: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    projection_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    projection_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    audit_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    audit_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_required_section_count: Mapped[int] = mapped_column(Integer, nullable=False)
    inconsistent_section_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ref_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_count: Mapped[int] = mapped_column(Integer, nullable=False)
    traceability_edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EvidencePack(Base):
    __tablename__ = "evidence_packs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["generation_run_id", "project_id", "tenant_id"],
            ["evidence_pack_generation_runs.id", "evidence_pack_generation_runs.project_id", "evidence_pack_generation_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
            name="audit_checkpoint",
        ),
        CheckConstraint("assembly_status IN ('complete','incomplete')", name="status"),
        CheckConstraint(
            "repo_binding_state IN ('agreed','missing_trusted_binding','trusted_binding_disagreement')",
            name="repo_state",
        ),
        CheckConstraint(
            f"(repo_binding_state='agreed' AND repo_binding_hash ~ '{_HASH}' "
            "AND commit_sha ~ '^[0-9a-f]{40}$') OR "
            "(repo_binding_state<>'agreed' AND repo_binding_hash IS NULL AND commit_sha IS NULL)",
            name="repo_shape",
        ),
        CheckConstraint(
            f"artifact_scope_digest ~ '{_HASH}' AND issue_binding_digest ~ '{_HASH}' "
            f"AND source_set_digest ~ '{_HASH}' AND traceability_digest ~ '{_HASH}' "
            f"AND core_content_hash ~ '{_HASH}'",
            name="digests",
        ),
        CheckConstraint(
            "verdict_status='absent_deferred_slice50' "
            "AND signature_status='unsigned_signer_tier_not_implemented'",
            name="attestations_deferred",
        ),
        CheckConstraint(
            "source_ref_count BETWEEN 0 AND 50000 AND section_count=12 "
            "AND traceability_edge_count BETWEEN 0 AND 50000 "
            "AND octet_length(canonical_core_text) BETWEEN 2 AND 8388608",
            name="bounds",
        ),
        UniqueConstraint("generation_run_id", name="uq_evidence_packs_generation_run"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_ep_id_project_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audit_checkpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assembly_status: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_scope_digest: Mapped[str] = mapped_column(Text, nullable=False)
    issue_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    source_set_digest: Mapped[str] = mapped_column(Text, nullable=False)
    traceability_digest: Mapped[str] = mapped_column(Text, nullable=False)
    repo_binding_state: Mapped[str] = mapped_column(Text, nullable=False)
    repo_binding_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    projection_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    audit_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_core_text: Mapped[str] = mapped_column(Text, nullable=False)
    core_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_status: Mapped[str] = mapped_column(Text, nullable=False)
    signature_status: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_count: Mapped[int] = mapped_column(Integer, nullable=False)
    traceability_edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EvidencePackSourceRef(Base):
    __tablename__ = "evidence_pack_source_refs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        CheckConstraint(
            "source_kind IN (" + ",".join(repr(value) for value in _SOURCE_KINDS) + ")",
            name="source_kind",
        ),
        CheckConstraint(
            "char_length(truth_tier) BETWEEN 1 AND 128 AND btrim(truth_tier)<>''",
            name="truth_tier",
        ),
        CheckConstraint(f"projection_digest ~ '{_HASH}'", name="projection_digest"),
        CheckConstraint("ordinal BETWEEN 1 AND 50000", name="ordinal"),
        UniqueConstraint("evidence_pack_id", "ordinal", name="uq_epsr_pack_ordinal"),
        UniqueConstraint(
            "evidence_pack_id", "source_kind", "source_id", name="uq_epsr_pack_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    truth_tier: Mapped[str] = mapped_column(Text, nullable=False)
    projection_digest: Mapped[str] = mapped_column(Text, nullable=False)
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EvidencePackSectionResult(Base):
    __tablename__ = "evidence_pack_section_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        CheckConstraint(
            "section_code IN (" + ",".join(repr(value) for value in _SECTIONS) + ")",
            name="section_code",
        ),
        CheckConstraint(
            "presence_code IN ('present','present_zero_rows','missing_required_source',"
            "'inconsistent_source','unsupported_this_slice','deferred_to_slice_50',"
            "'deferred_to_slice_60')",
            name="presence_code",
        ),
        CheckConstraint("item_count BETWEEN 0 AND 10000", name="item_count"),
        CheckConstraint(f"section_digest ~ '{_HASH}'", name="section_digest"),
        CheckConstraint(
            "failure_code IS NULL OR (char_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code)<>'')",
            name="failure_code",
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 12", name="ordinal"),
        UniqueConstraint("evidence_pack_id", "section_code", name="uq_eps_pack_section"),
        UniqueConstraint("evidence_pack_id", "ordinal", name="uq_eps_pack_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    section_code: Mapped[str] = mapped_column(Text, nullable=False)
    presence_code: Mapped[str] = mapped_column(Text, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_digest: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
