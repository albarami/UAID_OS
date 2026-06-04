"""``documents`` — tenant-owned intake sandbox store (Slice 9, §16.3).

Customer-supplied documents are UNTRUSTED DATA, persisted tenant-owned + RLS. Content
and identity are immutable after insert; ``status`` is one-way (`accepted→quarantined`);
content integrity (size + ``sha256:`` hash) is verified at the DB. All three are enforced
by the combined ``BEFORE INSERT OR UPDATE`` trigger in migration ``0011`` (DML-enforced
for ordinary roles incl. the owner; not tamper-proof vs. a DB superuser). Audit records
metadata + marker identifiers only — never the document body (§17.5).
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint("status IN ('accepted', 'quarantined')", name="status_valid"),
        CheckConstraint(
            "content_type IN ('text/plain', 'text/markdown')", name="content_type_allowed"
        ),
        CheckConstraint(
            "source IN ('customer_upload', 'api_ingest', 'manual')", name="source_allowed"
        ),
        CheckConstraint("octet_length(filename) BETWEEN 1 AND 255", name="filename_bounded"),
        CheckConstraint("octet_length(content) BETWEEN 1 AND 1048576", name="content_bounded"),
        CheckConstraint("size_bytes >= 0", name="size_non_negative"),
        CheckConstraint("content_hash ~ '^sha256:[0-9a-f]{64}$'", name="content_hash_format"),
        UniqueConstraint("tenant_id", "project_id", "content_hash", name="uq_documents_content"),
        # FK target for intake_provenance's document composite FK (Slice 11): pins a
        # document-backed source to the SAME document + project + tenant.
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_documents_id_project_tenant"
        ),
        Index("ix_documents_tenant_project", "tenant_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    scan_result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
