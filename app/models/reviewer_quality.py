"""Controlled fixture catalog and tenant-owned reviewer QA evidence (Slice 48)."""

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
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.verify.reviewer_qa import REPLACEMENT_DECISION

_HASH = r"^sha256:[0-9a-f]{64}$"
_CRITICAL_RATE = (
    "CASE WHEN critical_label_count>0 THEN "
    "missed_critical_label_count::numeric/critical_label_count ELSE NULL END"
)
_MAJOR_RATE = (
    "CASE WHEN major_label_count>0 THEN "
    "missed_major_label_count::numeric/major_label_count ELSE NULL END"
)
_FALSE_APPROVAL_RATE = (
    "CASE WHEN defective_case_count>0 THEN "
    "false_approval_count::numeric/defective_case_count ELSE NULL END"
)
_FALSE_REJECTION_RATE = (
    "CASE WHEN clean_case_count>0 THEN "
    "false_rejection_count::numeric/clean_case_count ELSE NULL END"
)
_INCONCLUSIVE = (
    "execution_status<>'succeeded' OR NOT coverage_complete OR critical_label_count=0 "
    "OR defective_case_count=0 OR clean_case_count=0"
)
_BREACHED = (
    "missed_critical_label_count::numeric/NULLIF(critical_label_count,0)>max_critical_defect_miss_rate "
    "OR false_approval_count::numeric/NULLIF(defective_case_count,0)>max_false_approval_rate"
)
_STATUS = (
    f"CASE WHEN {_INCONCLUSIVE} THEN 'inconclusive' WHEN {_BREACHED} "
    "THEN 'threshold_breached' ELSE 'challenge_qualified' END"
)
_DECISION = (
    f"CASE WHEN NOT ({_INCONCLUSIVE}) AND ({_BREACHED}) "
    f"THEN '{REPLACEMENT_DECISION}' ELSE 'none' END"
)


class ReviewerQAFixtureSuite(Base):
    __tablename__ = "reviewer_qa_fixture_suites"
    __table_args__ = (
        CheckConstraint(f"suite_digest ~ '{_HASH}'", name="ck_rqfs_suite_digest"),
        CheckConstraint(f"qa_contract_hash ~ '{_HASH}'", name="ck_rqfs_contract_hash"),
        CheckConstraint(f"policy_digest ~ '{_HASH}'", name="ck_rqfs_policy_digest"),
        CheckConstraint("case_count BETWEEN 1 AND 500", name="ck_rqfs_case_count"),
        CheckConstraint("defect_label_count BETWEEN 1 AND 5000", name="ck_rqfs_defect_count"),
        UniqueConstraint("fixture_version", name="uq_reviewer_qa_fixture_suites_version"),
        UniqueConstraint("id", "suite_digest", name="uq_rqfs_id_digest"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    fixture_version: Mapped[str] = mapped_column(Text, nullable=False)
    suite_digest: Mapped[str] = mapped_column(Text, nullable=False)
    qa_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    planted_defect_sampling_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    max_critical_defect_miss_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    max_false_approval_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    defect_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ReviewerQAFixtureCase(Base):
    __tablename__ = "reviewer_qa_fixture_cases"
    __table_args__ = (
        CheckConstraint(
            "challenge_family IN ('defect','shortcut','weakened_test','fake_integration','missing_evidence')",
            name="ck_rqfc_family",
        ),
        CheckConstraint(
            "control_kind IS NULL OR control_kind IN "
            "('clean','negative','edge','adversarial','injection','incomplete')",
            name="ck_rqfc_control",
        ),
        CheckConstraint("risk_level IN ('low','medium','high','critical')", name="ck_rqfc_risk"),
        CheckConstraint(
            "expected_verdict IN ('approved','rejected_with_required_changes')",
            name="ck_rqfc_verdict",
        ),
        CheckConstraint(f"fixture_digest ~ '{_HASH}'", name="ck_rqfc_digest"),
        CheckConstraint(
            "char_length(case_ref) BETWEEN 1 AND 128 AND btrim(case_ref)<>''",
            name="ck_rqfc_ref",
        ),
        CheckConstraint(
            "expected_label_count>=0 AND critical_label_count>=0 AND major_label_count>=0 "
            "AND critical_label_count+major_label_count<=expected_label_count",
            name="ck_rqfc_counts",
        ),
        UniqueConstraint("suite_id", "case_ref", name="uq_rqfc_suite_ref"),
        UniqueConstraint("id", "suite_id", name="uq_rqfc_id_suite"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviewer_qa_fixture_suites.id", ondelete="RESTRICT")
    )
    case_ref: Mapped[str] = mapped_column(Text, nullable=False)
    challenge_family: Mapped[str] = mapped_column(Text, nullable=False)
    control_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    expected_verdict: Mapped[str] = mapped_column(Text, nullable=False)
    fixture_digest: Mapped[str] = mapped_column(Text, nullable=False)
    expected_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    major_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ReviewerQAFixtureDefect(Base):
    __tablename__ = "reviewer_qa_fixture_defects"
    __table_args__ = (
        CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_rqfd_severity"),
        CheckConstraint(f"evidence_ref_digest ~ '{_HASH}'", name="ck_rqfd_evidence_digest"),
        CheckConstraint(
            "char_length(defect_key) BETWEEN 1 AND 128 AND btrim(defect_key)<>'' "
            "AND char_length(category) BETWEEN 1 AND 128 AND btrim(category)<>''",
            name="ck_rqfd_codes",
        ),
        ForeignKeyConstraint(
            ["fixture_case_id", "suite_id"],
            ["reviewer_qa_fixture_cases.id", "reviewer_qa_fixture_cases.suite_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("fixture_case_id", "defect_key", name="uq_rqfd_case_key"),
        UniqueConstraint("id", "fixture_case_id", "suite_id", name="uq_rqfd_id_case_suite"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    suite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fixture_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    defect_key: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ref_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ReviewerQualityRecord(Base):
    __tablename__ = "reviewer_quality_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="fk_rqr_project_tenant",
        ),
        ForeignKeyConstraint(
            ["reviewer_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            ondelete="RESTRICT",
            name="fk_rqr_instance_project_tenant",
        ),
        ForeignKeyConstraint(
            ["reviewer_realization_id", "project_id", "tenant_id"],
            ["agent_realizations.id", "agent_realizations.project_id", "agent_realizations.tenant_id"],
            ondelete="RESTRICT",
            name="fk_rqr_realization_project_tenant",
        ),
        ForeignKeyConstraint(
            ["qualification_run_id", "project_id", "tenant_id"],
            ["qualification_runs.id", "qualification_runs.project_id", "qualification_runs.tenant_id"],
            ondelete="RESTRICT",
            name="fk_rqr_qualification_project_tenant",
        ),
        CheckConstraint(f"reviewer_version_hash ~ '{_HASH}'", name="ck_rqr_version_hash"),
        CheckConstraint(f"model_route_hash ~ '{_HASH}'", name="ck_rqr_model_hash"),
        CheckConstraint(f"prompt_hash ~ '{_HASH}'", name="ck_rqr_prompt_hash"),
        CheckConstraint(f"fixture_suite_hash ~ '{_HASH}'", name="ck_rqr_suite_hash"),
        CheckConstraint(f"qa_contract_hash ~ '{_HASH}'", name="ck_rqr_contract_hash"),
        CheckConstraint(f"policy_digest ~ '{_HASH}'", name="ck_rqr_policy_digest"),
        CheckConstraint(
            "execution_status IN ('succeeded','failed','refused')", name="ck_rqr_execution_status"
        ),
        CheckConstraint(
            "execution_provenance='system_executed_reviewer_qa'", name="ck_rqr_provenance"
        ),
        CheckConstraint("blind_to_fixture_labels", name="ck_rqr_blind"),
        CheckConstraint("NOT live_sampling_executed", name="ck_rqr_no_live_sampling"),
        CheckConstraint(
            "failure_code IS NULL OR (char_length(failure_code) BETWEEN 1 AND 128 AND btrim(failure_code)<>'')",
            name="ck_rqr_failure_code",
        ),
        CheckConstraint(
            "case_count>=0 AND defective_case_count>=0 AND clean_case_count>=0 "
            "AND critical_label_count>=0 AND missed_critical_label_count>=0 "
            "AND major_label_count>=0 AND missed_major_label_count>=0 "
            "AND false_approval_count>=0 AND false_rejection_count>=0 "
            "AND matched_evidence_count>=0 AND specific_required_change_count>=0 "
            "AND input_tokens>=0 AND output_tokens>=0 AND total_latency_ms>=0 "
            "AND missed_critical_label_count<=critical_label_count "
            "AND missed_major_label_count<=major_label_count",
            name="ck_rqr_counts",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_rqr_id_project_tenant"),
        Index(
            "ix_reviewer_quality_records_latest",
            "tenant_id",
            "project_id",
            "reviewer_instance_id",
            "reviewer_version_hash",
            "fixture_suite_hash",
            "qa_contract_hash",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_realization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qualification_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_blueprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_blueprints.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_version_hash: Mapped[str] = mapped_column(Text, nullable=False)
    model_route_hash: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    fixture_suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviewer_qa_fixture_suites.id", ondelete="RESTRICT")
    )
    fixture_suite_hash: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    qa_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    blind_to_fixture_labels: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live_sampling_executed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    planted_defect_sampling_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    max_critical_defect_miss_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    max_false_approval_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    defective_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    clean_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missed_critical_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    major_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missed_major_label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    false_approval_count: Mapped[int] = mapped_column(Integer, nullable=False)
    false_rejection_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    specific_required_change_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_miss_rate: Mapped[float | None] = mapped_column(
        Numeric, Computed(_CRITICAL_RATE, persisted=True)
    )
    major_miss_rate: Mapped[float | None] = mapped_column(
        Numeric, Computed(_MAJOR_RATE, persisted=True)
    )
    false_approval_rate: Mapped[float | None] = mapped_column(
        Numeric, Computed(_FALSE_APPROVAL_RATE, persisted=True)
    )
    false_rejection_rate: Mapped[float | None] = mapped_column(
        Numeric, Computed(_FALSE_REJECTION_RATE, persisted=True)
    )
    quality_status: Mapped[str] = mapped_column(
        Text, Computed(_STATUS, persisted=True), nullable=False
    )
    prescribed_decision: Mapped[str] = mapped_column(
        Text, Computed(_DECISION, persisted=True), nullable=False
    )
    coverage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_calibration_due: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewerQualityCaseResult(Base):
    __tablename__ = "reviewer_quality_case_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["reviewer_quality_record_id", "project_id", "tenant_id"],
            ["reviewer_quality_records.id", "reviewer_quality_records.project_id", "reviewer_quality_records.tenant_id"],
            ondelete="RESTRICT",
            name="fk_rqcr_record_project_tenant",
        ),
        ForeignKeyConstraint(
            ["fixture_case_id", "fixture_suite_id"],
            ["reviewer_qa_fixture_cases.id", "reviewer_qa_fixture_cases.suite_id"],
            ondelete="RESTRICT",
            name="fk_rqcr_case_suite",
        ),
        CheckConstraint("execution_status IN ('succeeded','control_refused')", name="ck_rqcr_status"),
        CheckConstraint(
            "reviewer_decision IS NULL OR reviewer_decision IN "
            "('approved','rejected_with_required_changes')",
            name="ck_rqcr_decision",
        ),
        CheckConstraint(f"response_digest IS NULL OR response_digest ~ '{_HASH}'", name="ck_rqcr_digest"),
        CheckConstraint(
            "reported_finding_count>=0 AND matched_evidence_count>=0 "
            "AND specific_required_change_count>=0 AND input_tokens>=0 "
            "AND output_tokens>=0 AND latency_ms>=0",
            name="ck_rqcr_counts",
        ),
        UniqueConstraint("reviewer_quality_record_id", "fixture_case_id", name="uq_rqcr_record_case"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", "fixture_case_id", "fixture_suite_id",
            name="uq_rqcr_defect_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_quality_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fixture_suite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fixture_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    execution_status: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    specific_required_change_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ReviewerQualityDefectResult(Base):
    __tablename__ = "reviewer_quality_defect_results"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "reviewer_quality_case_result_id", "project_id", "tenant_id",
                "fixture_case_id", "fixture_suite_id",
            ],
            [
                "reviewer_quality_case_results.id", "reviewer_quality_case_results.project_id",
                "reviewer_quality_case_results.tenant_id", "reviewer_quality_case_results.fixture_case_id",
                "reviewer_quality_case_results.fixture_suite_id",
            ],
            ondelete="RESTRICT",
            name="fk_rqdr_case_result",
        ),
        ForeignKeyConstraint(
            ["fixture_defect_id", "fixture_case_id", "fixture_suite_id"],
            [
                "reviewer_qa_fixture_defects.id", "reviewer_qa_fixture_defects.fixture_case_id",
                "reviewer_qa_fixture_defects.suite_id",
            ],
            ondelete="RESTRICT",
            name="fk_rqdr_fixture_defect",
        ),
        CheckConstraint("NOT detected OR evidence_matched", name="ck_rqdr_detected_evidence"),
        UniqueConstraint("reviewer_quality_case_result_id", "fixture_defect_id", name="uq_rqdr_case_defect"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_quality_case_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fixture_suite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fixture_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fixture_defect_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
