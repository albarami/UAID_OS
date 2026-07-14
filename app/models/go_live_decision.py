"""Tenant-owned Slice-55 control-loop and non-executing decision evidence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_HASH = r"^sha256:[0-9a-f]{64}$"


class ControlLoopRun(Base):
    __tablename__ = "control_loop_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "control_loop_contract_version='slice55.control_loop.v1'", name="contract"
        ),
        CheckConstraint(
            f"idempotency_digest ~ '{_HASH}' AND control_loop_contract_hash ~ '{_HASH}'",
            name="digests",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_clr_id_project_tenant"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_digest", name="uq_clr_idempotency"
        ),
        Index("ix_clr_tenant_project_created", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_digest: Mapped[str] = mapped_column(Text, nullable=False)
    control_loop_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    control_loop_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ControlLoopEvent(Base):
    __tablename__ = "control_loop_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["control_loop_run_id", "project_id", "tenant_id"],
            ["control_loop_runs.id", "control_loop_runs.project_id", "control_loop_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["previous_event_id", "project_id", "tenant_id"],
            ["control_loop_events.id", "control_loop_events.project_id", "control_loop_events.tenant_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 64", name="ordinal"),
        CheckConstraint(
            "char_length(stage_code) BETWEEN 1 AND 128 AND btrim(stage_code)<>'' AND "
            "char_length(outcome_code) BETWEEN 1 AND 128 AND btrim(outcome_code)<>''",
            name="codes",
        ),
        CheckConstraint(
            f"evidence_reference_digest IS NULL OR evidence_reference_digest ~ '{_HASH}'",
            name="digest",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_cle_id_project_tenant"),
        UniqueConstraint("control_loop_run_id", "ordinal", name="uq_cle_run_ordinal"),
        UniqueConstraint("previous_event_id", name="uq_cle_previous"),
        Index("ix_cle_tenant_loop_ordinal", "tenant_id", "control_loop_run_id", "ordinal"),
        Index(
            "uq_cle_loop_root",
            "control_loop_run_id",
            unique=True,
            postgresql_where=text("previous_event_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    control_loop_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    previous_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    stage_code: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_code: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class GoLiveEvaluation(Base):
    __tablename__ = "go_live_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["control_loop_run_id", "project_id", "tenant_id"],
            ["control_loop_runs.id", "control_loop_runs.project_id", "control_loop_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["preapproval_request_id", "project_id", "tenant_id"],
            ["production_preapproval_requests.id", "production_preapproval_requests.project_id", "production_preapproval_requests.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["preapproval_attestation_id", "project_id", "tenant_id"],
            ["production_preapproval_attestations.id", "production_preapproval_attestations.project_id", "production_preapproval_attestations.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            ["autonomy_policies.id", "autonomy_policies.project_id", "autonomy_policies.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["emergency_control_binding_id", "project_id", "tenant_id"],
            ["emergency_control_bindings.id", "emergency_control_bindings.project_id", "emergency_control_bindings.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["emergency_stop_event_id", "project_id", "tenant_id"],
            ["emergency_stop_events.id", "emergency_stop_events.project_id", "emergency_stop_events.tenant_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "ruleset_version='slice54.v1' AND evaluation_contract_version='slice55.go_live_evaluation.v1'",
            name="contracts",
        ),
        CheckConstraint(
            f"evaluation_contract_hash ~ '{_HASH}' AND gate_result_digest ~ '{_HASH}' AND "
            f"decision_binding_digest ~ '{_HASH}' AND "
            f"(autonomy_policy_digest IS NULL OR autonomy_policy_digest ~ '{_HASH}')",
            name="digests",
        ),
        CheckConstraint("passed_gate_count BETWEEN 0 AND 13", name="passed_count"),
        CheckConstraint("policy_decision IN ('needs_approval','deny','allow')", name="policy"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_gle_id_project_tenant"),
        UniqueConstraint("control_loop_run_id", name="uq_gle_loop"),
        Index("ix_gle_tenant_project_created", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    control_loop_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    gate_result_digest: Mapped[str] = mapped_column(Text, nullable=False)
    passed_gate_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    all_gates_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    preapproval_gate_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_decision: Mapped[str] = mapped_column(Text, nullable=False)
    emergency_latch_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    release_candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    evidence_pack_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    release_verdict_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    preapproval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    preapproval_attestation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    preapproval_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    autonomy_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    autonomy_policy_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    autonomy_policy_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    emergency_control_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    emergency_stop_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    decision_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class GoLiveEvaluationGateResult(Base):
    __tablename__ = "go_live_evaluation_gate_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evaluation_id", "project_id", "tenant_id"],
            ["go_live_evaluations.id", "go_live_evaluations.project_id", "go_live_evaluations.tenant_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("gate_number BETWEEN 1 AND 13 AND ordinal BETWEEN 1 AND 13", name="numbers"),
        CheckConstraint(
            "status IN ('passed','failed','insufficient_evidence','no_evidence_source')",
            name="status",
        ),
        CheckConstraint(
            "char_length(gate_name_code) BETWEEN 1 AND 128 AND btrim(gate_name_code)<>'' AND "
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''",
            name="codes",
        ),
        CheckConstraint(f"safe_context_digest ~ '{_HASH}'", name="digest"),
        UniqueConstraint("evaluation_id", "gate_number", name="uq_glegr_gate"),
        UniqueConstraint("evaluation_id", "ordinal", name="uq_glegr_ordinal"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_glegr_id_project_tenant"),
        Index("ix_glegr_tenant_evaluation_gate", "tenant_id", "evaluation_id", "gate_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gate_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    gate_name_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    safe_context_digest: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class GoLiveDecision(Base):
    __tablename__ = "go_live_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["control_loop_run_id", "project_id", "tenant_id"],
            ["control_loop_runs.id", "control_loop_runs.project_id", "control_loop_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evaluation_id", "project_id", "tenant_id"],
            ["go_live_evaluations.id", "go_live_evaluations.project_id", "go_live_evaluations.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["previous_decision_id", "project_id", "tenant_id"],
            ["go_live_decisions.id", "go_live_decisions.project_id", "go_live_decisions.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["preapproval_request_id", "project_id", "tenant_id"],
            ["production_preapproval_requests.id", "production_preapproval_requests.project_id", "production_preapproval_requests.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["preapproval_attestation_id", "project_id", "tenant_id"],
            ["production_preapproval_attestations.id", "production_preapproval_attestations.project_id", "production_preapproval_attestations.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            ["autonomy_policies.id", "autonomy_policies.project_id", "autonomy_policies.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["emergency_control_binding_id", "project_id", "tenant_id"],
            ["emergency_control_bindings.id", "emergency_control_bindings.project_id", "emergency_control_bindings.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["emergency_stop_event_id", "project_id", "tenant_id"],
            ["emergency_stop_events.id", "emergency_stop_events.project_id", "emergency_stop_events.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status='decided_not_executed'", name="status"),
        CheckConstraint(
            "authority_truth_tier='request_authenticated_key_custody_under_recorded_policy_not_human_signature'",
            name="authority",
        ),
        CheckConstraint(
            "production_action_executed=false AND can_go_live_autonomously_snapshot=false",
            name="hard_false",
        ),
        CheckConstraint(
            f"evaluation_digest ~ '{_HASH}' AND decision_binding_digest ~ '{_HASH}' AND "
            f"autonomy_policy_digest ~ '{_HASH}' AND scope_limitation_digest ~ '{_HASH}' AND "
            f"(prev_entry_hash IS NULL OR prev_entry_hash ~ '{_HASH}') AND entry_hash ~ '{_HASH}'",
            name="digests",
        ),
        UniqueConstraint("evaluation_id", name="uq_gld_evaluation"),
        UniqueConstraint("previous_decision_id", name="uq_gld_previous"),
        UniqueConstraint("entry_hash", name="uq_gld_entry_hash"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_gld_id_project_tenant"),
        Index("ix_gld_tenant_project_seq", "tenant_id", "project_id", "decision_seq"),
        Index(
            "uq_gld_project_root",
            "tenant_id",
            "project_id",
            unique=True,
            postgresql_where=text("previous_decision_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    decision_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    control_loop_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    preapproval_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    preapproval_attestation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    autonomy_policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    autonomy_policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    emergency_control_binding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    emergency_stop_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_digest: Mapped[str] = mapped_column(Text, nullable=False)
    decision_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    authority_truth_tier: Mapped[str] = mapped_column(Text, nullable=False)
    production_action_executed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    can_go_live_autonomously_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scope_limitation_digest: Mapped[str] = mapped_column(Text, nullable=False)
    previous_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    prev_entry_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
