"""Tenant-owned append-only Slice-53 production pre-approval evidence graph."""

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


class ProductionApprovalPolicyVersion(Base):
    __tablename__ = "production_approval_policy_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["human_approval_category_id", "project_id", "tenant_id"],
            ["intake_categories.id", "intake_categories.project_id", "intake_categories.tenant_id"],
            ondelete="RESTRICT",
            name="policy_category_project_tenant",
        ),
        ForeignKeyConstraint(
            ["go_live_checklist_category_id", "project_id", "tenant_id"],
            ["intake_categories.id", "intake_categories.project_id", "intake_categories.tenant_id"],
            ondelete="RESTRICT",
            name="checklist_category_project_tenant",
        ),
        CheckConstraint(
            "policy_contract_version='slice53.production_approval_policy.v1' AND "
            "source_provenance='caller_supplied_unverified_structured_approval_policy'",
            name="contracts",
        ),
        CheckConstraint(
            f"policy_digest ~ '{_HASH}' AND checklist_digest ~ '{_HASH}' AND "
            f"governance_requirements_digest ~ '{_HASH}' AND approver_set_digest ~ '{_HASH}'",
            name="digests",
        ),
        CheckConstraint(
            "approval_channel='dashboard' AND production_realtime AND "
            "production_nonresponse_code='block_until_approval'",
            name="production_policy",
        ),
        CheckConstraint("approver_count BETWEEN 1 AND 100", name="approver_count"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_papv_id_project_tenant"),
        Index("ix_papv_tenant_project_created", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    human_approval_category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    go_live_checklist_category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    checklist_digest: Mapped[str] = mapped_column(Text, nullable=False)
    approval_channel: Mapped[str] = mapped_column(Text, nullable=False)
    production_realtime: Mapped[bool] = mapped_column(Boolean, nullable=False)
    production_nonresponse_code: Mapped[str] = mapped_column(Text, nullable=False)
    governance_requirements_digest: Mapped[str] = mapped_column(Text, nullable=False)
    approver_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    approver_set_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

class ProductionApprovalPolicyApprover(Base):
    __tablename__ = "production_approval_policy_approvers"
    __table_args__ = (
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
        CheckConstraint("ordinal BETWEEN 1 AND 100", name="ordinal"),
        CheckConstraint(f"principal_subject_hash ~ '{_HASH}'", name="subject_hash"),
        UniqueConstraint("policy_version_id", "ordinal", name="uq_papa_policy_ordinal"),
        UniqueConstraint(
            "policy_version_id", "principal_subject_hash", name="uq_papa_policy_subject"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    principal_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ProductionPreapprovalRequest(Base):
    __tablename__ = "production_preapproval_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
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
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
            name="verdict_project_tenant",
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
            ["generic_approval_id", "project_id", "tenant_id"],
            ["approvals.id", "approvals.project_id", "approvals.tenant_id"],
            ondelete="RESTRICT",
            name="approval_project_tenant",
        ),
        ForeignKeyConstraint(
            ["approval_notification_id"], ["approval_notifications.id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            "preapproval_contract_version='slice53.production_preapproval.v1' AND "
            "condition_contract_version='slice53.production_preapproval_conditions.v1'",
            name="contracts",
        ),
        CheckConstraint(
            f"condition_contract_hash ~ '{_HASH}' AND release_binding_digest ~ '{_HASH}' AND "
            f"core_content_hash ~ '{_HASH}' AND issue_binding_digest ~ '{_HASH}' AND "
            f"source_set_digest ~ '{_HASH}' AND traceability_digest ~ '{_HASH}' AND "
            f"verdict_input_digest ~ '{_HASH}' AND verdict_contract_hash ~ '{_HASH}' AND "
            f"autonomy_policy_digest ~ '{_HASH}' AND requester_subject_hash ~ '{_HASH}' AND "
            f"request_idempotency_key_hash ~ '{_HASH}'",
            name="digests",
        ),
        CheckConstraint(
            "requester_actor_type IN ('human','service') AND requester_provenance='request_authenticated'",
            name="requester",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_ppr_id_project_tenant"),
        UniqueConstraint("generic_approval_id", name="uq_ppr_generic_approval"),
        UniqueConstraint(
            "tenant_id", "project_id", "request_idempotency_key_hash", name="uq_ppr_idempotency"
        ),
        Index("ix_ppr_tenant_project_created", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    autonomy_policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generic_approval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_notification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    preapproval_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    condition_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    condition_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    release_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    core_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    issue_binding_digest: Mapped[str] = mapped_column(Text, nullable=False)
    source_set_digest: Mapped[str] = mapped_column(Text, nullable=False)
    traceability_digest: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    verdict_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    autonomy_policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    requester_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    requester_actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    requester_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    request_idempotency_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ProductionPreapprovalAttestation(Base):
    __tablename__ = "production_preapproval_attestations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["request_id", "project_id", "tenant_id"],
            [
                "production_preapproval_requests.id",
                "production_preapproval_requests.project_id",
                "production_preapproval_requests.tenant_id",
            ],
            ondelete="RESTRICT",
            name="request_project_tenant",
        ),
        ForeignKeyConstraint(
            ["generic_approval_id", "project_id", "tenant_id"],
            ["approvals.id", "approvals.project_id", "approvals.tenant_id"],
            ondelete="RESTRICT",
            name="approval_project_tenant",
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
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
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
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
            name="verdict_project_tenant",
        ),
        CheckConstraint(
            f"requester_subject_hash ~ '{_HASH}' AND approver_subject_hash ~ '{_HASH}' AND "
            f"resolution_idempotency_key_hash ~ '{_HASH}'",
            name="digests",
        ),
        CheckConstraint(
            "requester_actor_type IN ('human','service') AND approver_actor_type='human' AND "
            "requester_provenance='request_authenticated' AND approver_provenance='request_authenticated'",
            name="identity",
        ),
        CheckConstraint(
            "valid_from=approved_at AND expires_at>approved_at AND "
            "expires_at<=approved_at + interval '24 hours'",
            name="validity",
        ),
        UniqueConstraint("request_id", name="uq_ppa_request"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_ppa_id_project_tenant"),
        UniqueConstraint(
            "tenant_id", "project_id", "resolution_idempotency_key_hash", name="uq_ppa_idempotency"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    generic_approval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requester_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    requester_actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    requester_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    approver_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    approver_actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    approver_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_idempotency_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attestation_result: Mapped[str] = mapped_column(
        Text, Computed("'approved'::text"), nullable=False
    )
    identity_separation_ok: Mapped[bool] = mapped_column(
        Boolean, Computed("requester_subject_hash<>approver_subject_hash"), nullable=False
    )
    policy_membership_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    gate_eligible_at_creation: Mapped[bool] = mapped_column(
        Boolean,
        Computed(
            "requester_subject_hash<>approver_subject_hash AND "
            "requester_provenance='request_authenticated' AND "
            "approver_provenance='request_authenticated' AND approver_actor_type='human' AND "
            "policy_membership_ok AND expires_at>approved_at"
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ProductionPreapprovalLifecycleEvent(Base):
    __tablename__ = "production_preapproval_lifecycle_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["attestation_id", "project_id", "tenant_id"],
            [
                "production_preapproval_attestations.id",
                "production_preapproval_attestations.project_id",
                "production_preapproval_attestations.tenant_id",
            ],
            ondelete="RESTRICT",
            name="attestation_project_tenant",
        ),
        ForeignKeyConstraint(
            ["previous_event_id", "project_id", "tenant_id"],
            [
                "production_preapproval_lifecycle_events.id",
                "production_preapproval_lifecycle_events.project_id",
                "production_preapproval_lifecycle_events.tenant_id",
            ],
            ondelete="RESTRICT",
            name="previous_project_tenant",
        ),
        CheckConstraint(
            "event_type IN ('approved_anchor','revoked','superseded')", name="event_type"
        ),
        CheckConstraint(
            f"actor_subject_hash ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}'",
            name="digests",
        ),
        CheckConstraint(
            "actor_type IN ('human','service') AND actor_provenance='request_authenticated'",
            name="actor",
        ),
        CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''",
            name="reason_code",
        ),
        CheckConstraint(
            "(event_type='approved_anchor' AND previous_event_id IS NULL) OR "
            "(event_type IN ('revoked','superseded') AND previous_event_id IS NOT NULL)",
            name="chain_shape",
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_pple_id_project_tenant"),
        UniqueConstraint("attestation_id", "event_type", name="uq_pple_attestation_event"),
        UniqueConstraint("previous_event_id", name="uq_pple_previous"),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_pple_idempotency"
        ),
        Index(
            "ix_pple_tenant_project_attestation_created",
            "tenant_id",
            "project_id",
            "attestation_id",
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
    attestation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    previous_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
