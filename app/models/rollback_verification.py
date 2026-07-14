"""Tenant-owned append-only Slice-52 rollback verification evidence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_RAW_HASH = r"^[0-9a-f]{64}$"
_PACK_HASH = r"^sha256:[0-9a-f]{64}$"


class RollbackVerificationRun(Base):
    __tablename__ = "rollback_verification_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
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
            ["staging_target_snapshot_id", "project_id", "tenant_id"],
            [
                "deployment_target_snapshots.id",
                "deployment_target_snapshots.project_id",
                "deployment_target_snapshots.tenant_id",
            ],
            ondelete="RESTRICT",
            name="staging_snapshot_project_tenant",
        ),
        CheckConstraint(
            "drill_contract_version='slice52.rollback_drill.v1' AND "
            "verification_contract_version='slice52.rollback_verification.v1' AND "
            "staging_target_contract_version='slice52.staging_target.v1'",
            name="contracts",
        ),
        CheckConstraint(
            "artifact_provenance IN ('connector_verified_ci_rollback','no_artifact') AND "
            "execution_observation IN ('connector_observed_ci','connector_observation_failed')",
            name="provenance",
        ),
        CheckConstraint(
            "attempt_status IN ('succeeded','failed','refused')", name="attempt_status"
        ),
        CheckConstraint(
            "workflow_conclusion IS NULL OR workflow_conclusion IN "
            "('success','failure','cancelled','timed_out','action_required')",
            name="workflow_conclusion",
        ),
        CheckConstraint("drill_result IN ('passed','failed','incomplete')", name="drill_result"),
        CheckConstraint(
            f"repo_binding_hash ~ '{_PACK_HASH}' AND commit_sha ~ '^[0-9a-f]{{40}}$' AND "
            f"core_content_hash ~ '{_PACK_HASH}' AND artifact_scope_digest ~ '{_PACK_HASH}' AND "
            f"issue_binding_digest ~ '{_PACK_HASH}' AND source_set_digest ~ '{_PACK_HASH}' AND "
            f"traceability_digest ~ '{_PACK_HASH}' AND staging_target_binding_hash ~ '{_RAW_HASH}' AND "
            f"runner_manifest_hash ~ '{_RAW_HASH}' AND "
            f"(provider_run_ref_hash IS NULL OR provider_run_ref_hash ~ '{_RAW_HASH}') AND "
            f"(staging_snapshot_digest IS NULL OR staging_snapshot_digest ~ '{_RAW_HASH}') AND "
            f"(from_artifact_digest IS NULL OR from_artifact_digest ~ '{_RAW_HASH}') AND "
            f"(to_artifact_digest IS NULL OR to_artifact_digest ~ '{_RAW_HASH}') AND "
            f"(artifact_content_hash IS NULL OR artifact_content_hash ~ '{_RAW_HASH}') AND "
            f"(phase_digest IS NULL OR phase_digest ~ '{_RAW_HASH}')",
            name="hashes",
        ),
        CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>'' AND "
            "scope_limitation_code='from_version_connector_observed_not_deployment_fk'",
            name="codes",
        ),
        CheckConstraint("phase_count BETWEEN 0 AND 5", name="phase_count"),
        CheckConstraint(
            "(attempt_status='succeeded' AND staging_target_snapshot_id IS NOT NULL "
            "AND artifact_provenance='connector_verified_ci_rollback' "
            "AND execution_observation='connector_observed_ci' "
            "AND from_artifact_digest IS NOT NULL AND to_artifact_digest IS NOT NULL "
            "AND from_artifact_digest<>to_artifact_digest AND artifact_content_hash IS NOT NULL "
            "AND provider_run_ref_hash IS NOT NULL "
            "AND phase_digest IS NOT NULL AND phase_count=5 AND artifact_completed_at IS NOT NULL "
            "AND workflow_conclusion IS NOT NULL AND evidence_consistent) OR "
            "(attempt_status IN ('failed','refused') AND artifact_provenance='no_artifact' "
            "AND execution_observation='connector_observation_failed' "
            "AND from_artifact_digest IS NULL AND to_artifact_digest IS NULL "
            "AND provider_run_ref_hash IS NULL AND artifact_content_hash IS NULL "
            "AND phase_digest IS NULL AND phase_count=0 "
            "AND artifact_completed_at IS NULL AND drill_result='incomplete' "
            "AND NOT evidence_consistent AND NOT gate_eligible)",
            name="result_shape",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_rbvr_id_project_tenant"),
        Index(
            "ix_rvr_tenant_project_created",
            "tenant_id",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    staging_target_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    drill_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    verification_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    staging_target_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    execution_observation: Mapped[str] = mapped_column(Text, nullable=False)
    repo_binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    core_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_scope_digest: Mapped[str] = mapped_column(Text, nullable=False)
    issue_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    source_set_digest: Mapped[str] = mapped_column(Text, nullable=False)
    traceability_digest: Mapped[str] = mapped_column(Text, nullable=False)
    staging_target_binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    staging_snapshot_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_artifact_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_artifact_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    runner_manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)
    provider_run_ref_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    phase_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phase_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    drill_result: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_consistent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gate_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope_limitation_code: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class RollbackVerificationPhaseResult(Base):
    __tablename__ = "rollback_verification_phase_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 5", name="ordinal"),
        CheckConstraint(
            "phase_code IN ('baseline_a_probe','forward_deploy_b','forward_b_probe',"
            "'rollback_to_a','post_rollback_a_probe')",
            name="phase_code",
        ),
        CheckConstraint("phase_status IN ('passed','failed','not_run')", name="phase_status"),
        CheckConstraint(
            "result_code IN ('healthy','unhealthy','operation_complete','operation_failed',"
            "'not_run_after_failure')",
            name="result_code",
        ),
        CheckConstraint(
            f"target_binding_hash ~ '{_RAW_HASH}' AND expected_version_digest ~ '{_RAW_HASH}' "
            f"AND (observed_version_digest IS NULL OR observed_version_digest ~ '{_RAW_HASH}')",
            name="hashes",
        ),
        CheckConstraint("completed_at>started_at", name="timestamps"),
        UniqueConstraint("run_id", "ordinal", name="uq_rvpr_run_ordinal"),
        UniqueConstraint("run_id", "phase_code", name="uq_rvpr_run_phase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    phase_code: Mapped[str] = mapped_column(Text, nullable=False)
    phase_status: Mapped[str] = mapped_column(Text, nullable=False)
    result_code: Mapped[str] = mapped_column(Text, nullable=False)
    target_binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expected_version_digest: Mapped[str] = mapped_column(Text, nullable=False)
    observed_version_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    operation_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
