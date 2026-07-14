"""Tenant-owned append-only Slice-54 emergency-control evidence graph."""

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
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_HASH = r"^sha256:[0-9a-f]{64}$"


class EmergencyControlBinding(Base):
    __tablename__ = "emergency_control_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "production_approval_policy_versions.id",
                "production_approval_policy_versions.project_id",
                "production_approval_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
            name="policy_project_tenant",
        ),
        ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            ["autonomy_policies.id", "autonomy_policies.project_id", "autonomy_policies.tenant_id"],
            ondelete="RESTRICT",
            name="autonomy_project_tenant",
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
            ["rollback_verification_run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="rollback_project_tenant",
        ),
        CheckConstraint(
            "emergency_control_contract_version='slice54.emergency_control.v1' AND "
            "emergency_stop_contract_version='slice54.emergency_stop.v1' AND "
            "rollback_authority_contract_version='slice54.rollback_authority.v1'",
            name="contracts",
        ),
        CheckConstraint(
            "source_provenance='caller_supplied_unverified_structured_approval_policy' AND "
            "configured_by_provenance='request_authenticated' AND configured_by_actor_type='human'",
            name="provenance",
        ),
        CheckConstraint(
            "binding_attempt_status IN ('succeeded','failed','refused')", name="attempt"
        ),
        CheckConstraint(
            f"policy_digest ~ '{_HASH}' AND checklist_digest ~ '{_HASH}' AND "
            f"approver_set_digest ~ '{_HASH}' AND autonomy_policy_digest ~ '{_HASH}' AND "
            f"configured_by_subject_hash ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}' AND "
            f"(release_rollback_binding_digest IS NULL OR release_rollback_binding_digest ~ '{_HASH}')",
            name="digests",
        ),
        CheckConstraint("authority_member_count BETWEEN 1 AND 100", name="member_count"),
        CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''", name="reason"
        ),
        CheckConstraint(
            "(release_candidate_id IS NULL AND evidence_pack_id IS NULL AND rollback_verification_run_id IS NULL "
            "AND release_rollback_binding_digest IS NULL) OR "
            "(release_candidate_id IS NOT NULL AND evidence_pack_id IS NOT NULL "
            "AND rollback_verification_run_id IS NOT NULL AND release_rollback_binding_digest IS NOT NULL)",
            name="release_binding_shape",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_ecb_id_project_tenant"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_ecb_idempotency"
        ),
        Index("ix_ecb_tenant_project_created", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    autonomy_policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    evidence_pack_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    rollback_verification_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    emergency_control_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    emergency_stop_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_authority_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    binding_attempt_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    checklist_digest: Mapped[str] = mapped_column(Text, nullable=False)
    approver_set_digest: Mapped[str] = mapped_column(Text, nullable=False)
    autonomy_policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    release_rollback_binding_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    authority_member_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    stop_authority_bound: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "binding_attempt_status='succeeded' AND authority_member_count>=2", persisted=True
        ),
        nullable=False,
    )
    rollback_authority_bound: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "binding_attempt_status='succeeded' AND authority_member_count>=2 AND release_candidate_id IS NOT NULL AND evidence_pack_id IS NOT NULL AND rollback_verification_run_id IS NOT NULL",
            persisted=True,
        ),
        nullable=False,
    )
    evidence_consistent: Mapped[bool] = mapped_column(
        Boolean, Computed("binding_attempt_status='succeeded'", persisted=True), nullable=False
    )
    gate_eligible_at_creation: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "binding_attempt_status='succeeded' AND authority_member_count>=2 AND release_candidate_id IS NOT NULL AND evidence_pack_id IS NOT NULL AND rollback_verification_run_id IS NOT NULL",
            persisted=True,
        ),
        nullable=False,
    )
    configured_by_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    configured_by_actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    configured_by_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EmergencyControlAuthorityMember(Base):
    __tablename__ = "emergency_control_authority_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
            name="binding_project_tenant",
        ),
        ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "production_approval_policy_versions.id",
                "production_approval_policy_versions.project_id",
                "production_approval_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
            name="policy_project_tenant",
        ),
        ForeignKeyConstraint(
            ["policy_approver_id"], ["production_approval_policy_approvers.id"], ondelete="RESTRICT"
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 100", name="ordinal"),
        CheckConstraint(f"principal_subject_hash ~ '{_HASH}'", name="subject_hash"),
        CheckConstraint(
            "may_activate_stop AND may_clear_stop AND may_authorize_rollback", name="capabilities"
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_ecam_id_project_tenant"),
        UniqueConstraint("binding_id", "ordinal", name="uq_ecam_binding_ordinal"),
        UniqueConstraint("binding_id", "principal_subject_hash", name="uq_ecam_binding_subject"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    binding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    principal_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    may_activate_stop: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    may_clear_stop: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    may_authorize_rollback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EmergencyStopEvent(Base):
    __tablename__ = "emergency_stop_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
            name="binding_project_tenant",
        ),
        ForeignKeyConstraint(
            ["actor_member_id", "project_id", "tenant_id"],
            [
                "emergency_control_authority_members.id",
                "emergency_control_authority_members.project_id",
                "emergency_control_authority_members.tenant_id",
            ],
            ondelete="RESTRICT",
            name="actor_member_project_tenant",
        ),
        ForeignKeyConstraint(
            ["previous_event_id", "project_id", "tenant_id"],
            [
                "emergency_stop_events.id",
                "emergency_stop_events.project_id",
                "emergency_stop_events.tenant_id",
            ],
            ondelete="RESTRICT",
            name="previous_project_tenant",
        ),
        CheckConstraint("event_type IN ('armed_anchor','activated','cleared')", name="event_type"),
        CheckConstraint(
            "actor_type='human' AND actor_provenance='request_authenticated'", name="actor"
        ),
        CheckConstraint(
            f"actor_subject_hash ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}'", name="digests"
        ),
        CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''", name="reason"
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_ese_id_project_tenant"),
        UniqueConstraint("previous_event_id", name="uq_ese_previous"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_ese_idempotency"
        ),
        Index("ix_ese_tenant_project_created", "tenant_id", "project_id", "created_at"),
        Index(
            "uq_ese_project_root",
            "tenant_id",
            "project_id",
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
    binding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    previous_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    state_after: Mapped[str] = mapped_column(
        Text,
        Computed("CASE WHEN event_type='activated' THEN 'active' ELSE 'armed' END", persisted=True),
        nullable=False,
    )
    actor_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EmergencyStopRunEffect(Base):
    __tablename__ = "emergency_stop_run_effects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["activation_event_id", "project_id", "tenant_id"],
            [
                "emergency_stop_events.id",
                "emergency_stop_events.project_id",
                "emergency_stop_events.tenant_id",
            ],
            ondelete="RESTRICT",
            name="event_project_tenant",
        ),
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint(
            "status_before IN ('created','running','paused','blocked') AND status_after IN ('created','paused','blocked')",
            name="statuses",
        ),
        CheckConstraint(
            "effect_code IN ('paused','already_paused','already_blocked','not_started')",
            name="effect",
        ),
        CheckConstraint(
            "(effect_code='paused' AND status_before='running' AND status_after='paused' AND emergency_run_step_id IS NOT NULL) OR (effect_code<>'paused' AND status_before=status_after AND emergency_run_step_id IS NULL)",
            name="shape",
        ),
        UniqueConstraint("activation_event_id", "run_id", name="uq_esre_event_run"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    activation_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    emergency_run_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status_before: Mapped[str] = mapped_column(Text, nullable=False)
    status_after: Mapped[str] = mapped_column(Text, nullable=False)
    effect_code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EmergencyRollbackAuthorization(Base):
    __tablename__ = "emergency_rollback_authorizations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
            name="binding_project_tenant",
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
            ["rollback_verification_run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="rollback_project_tenant",
        ),
        ForeignKeyConstraint(
            ["actor_member_id", "project_id", "tenant_id"],
            [
                "emergency_control_authority_members.id",
                "emergency_control_authority_members.project_id",
                "emergency_control_authority_members.tenant_id",
            ],
            ondelete="RESTRICT",
            name="actor_member_project_tenant",
        ),
        CheckConstraint(
            "actor_type='human' AND actor_provenance='request_authenticated'", name="actor"
        ),
        CheckConstraint(
            "authorization_contract_version='slice54.rollback_authority.v1' AND result_code='authorized_not_executed' AND scope_limitation_code='production_rollback_not_executed'",
            name="result",
        ),
        CheckConstraint(
            f"actor_subject_hash ~ '{_HASH}' AND release_rollback_binding_digest ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}'",
            name="digests",
        ),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_era_idempotency"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    binding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rollback_verification_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    actor_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    release_rollback_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    authorization_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    result_code: Mapped[str] = mapped_column(Text, nullable=False)
    scope_limitation_code: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
