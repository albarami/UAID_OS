"""``document_classifications`` — tenant-owned, inert document classifications (Slice 35).

One row per classification attempt (1:1 with its run — D-35-1 single table). Records the run
``outcome`` and, on success, an inert proposed ``(document_type, authority_tier, bounded
verbatim evidence_quote)`` awaiting a distinct-reviewer decision (§2.2). Append-only except
the one-way review lifecycle: SELECT/INSERT/UPDATE; no DELETE/TRUNCATE (migration ``0034``).
The ``document_id`` is composite-FK pinned to the same tenant/project and DB-checked to be an
**accepted** document. The stored ``evidence_quote`` is a bounded verbatim excerpt of the
document; it is never audited/logged, and no "no-secret" guarantee is claimed (no denylist).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.intake.classifier import AUTHORITY_TIERS, DOCUMENT_TYPES, OUTCOMES, REVIEW_STATUSES
from app.models.base import Base

_DT = ", ".join(repr(v) for v in DOCUMENT_TYPES)
_AT = ", ".join(repr(v) for v in AUTHORITY_TIERS)
_OUT = ", ".join(repr(v) for v in OUTCOMES)
_REV = ", ".join(repr(v) for v in REVIEW_STATUSES)


class DocumentClassification(Base):
    __tablename__ = "document_classifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            ondelete="RESTRICT",
            name="document_project_tenant",
        ),
        CheckConstraint(f"outcome IN ({_OUT})", name="outcome_valid"),
        CheckConstraint(
            f"proposed_document_type IS NULL OR proposed_document_type IN ({_DT})",
            name="proposed_document_type_valid",
        ),
        CheckConstraint(
            f"proposed_authority_tier IS NULL OR proposed_authority_tier IN ({_AT})",
            name="proposed_authority_tier_valid",
        ),
        CheckConstraint(f"review_status IN ({_REV})", name="review_status_valid"),
        Index(
            "ix_document_classifications_latest",
            "tenant_id",
            "project_id",
            "document_id",
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
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    cost_external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_document_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_authority_tier: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_applicable'")
    )
    classified_by: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
