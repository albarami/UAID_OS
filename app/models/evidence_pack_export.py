"""Tenant-owned Slice-60 offline auditor bundle store. Append-only."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.release.export_bundle_db_checks import (
    FILE_CHECK_CONSTRAINTS,
    RECORD_CHECK_CONSTRAINTS,
    SIGNATURE_CHECK_CONSTRAINTS,
)


class EvidencePackExportRecord(Base):
    """One offline auditor bundle. Validity is never stored on this row."""

    __tablename__ = "evidence_pack_export_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
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
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
            name="verdict_project_tenant",
        ),
        ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
            name="audit_checkpoint",
        ),
        *[CheckConstraint(sql, name=name) for name, sql in RECORD_CHECK_CONSTRAINTS],
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_epr_id_project_tenant"),
        UniqueConstraint(
            "tenant_id",
            "evidence_pack_id",
            "idempotency_key",
            name="uq_epr_idempotency",
        ),
        Index("ix_epr_latest", "tenant_id", "evidence_pack_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_verdict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audit_checkpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    bundle_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_digest: Mapped[str] = mapped_column(Text, nullable=False)
    redaction_policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    redaction_policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    core_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    immutable_log_reference: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(Text, nullable=False)
    auditor_access_mode: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EvidencePackExportFile(Base):
    """One persisted bundle file. ``byte_count`` and hash are DB-derived from ``content``."""

    __tablename__ = "evidence_pack_export_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["export_record_id", "project_id", "tenant_id"],
            [
                "evidence_pack_export_records.id",
                "evidence_pack_export_records.project_id",
                "evidence_pack_export_records.tenant_id",
            ],
            ondelete="RESTRICT",
            name="record_project_tenant",
        ),
        *[CheckConstraint(sql, name=name) for name, sql in FILE_CHECK_CONSTRAINTS],
        UniqueConstraint("export_record_id", "ordinal", name="uq_epef_ordinal"),
        UniqueConstraint("export_record_id", "file_name", name="uq_epef_file_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    export_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class EvidencePackManifestSignature(Base):
    """Detached Ed25519 signature over file 3. No public key is stored."""

    __tablename__ = "evidence_pack_manifest_signatures"
    __table_args__ = (
        ForeignKeyConstraint(
            ["export_record_id", "project_id", "tenant_id"],
            [
                "evidence_pack_export_records.id",
                "evidence_pack_export_records.project_id",
                "evidence_pack_export_records.tenant_id",
            ],
            ondelete="RESTRICT",
            name="record_project_tenant",
        ),
        *[CheckConstraint(sql, name=name) for name, sql in SIGNATURE_CHECK_CONSTRAINTS],
        UniqueConstraint("export_record_id", name="uq_epms_export_record"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    export_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(Text, nullable=False)
    signature_b64: Mapped[str] = mapped_column(Text, nullable=False)
    signed_bytes_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
