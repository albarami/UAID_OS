"""``extraction_proposals`` — tenant-owned, inert AI-proposed intake items (Slice 14a).

Each row is a NON-authoritative proposal produced by the LLM, carrying a verbatim
``evidence_quote`` verified to exist in the source document. Content/identity is
immutable; ``status`` is one-way ``pending -> approved|rejected`` and a review requires a
``reviewed_by`` distinct from ``extracted_by`` (§2.2) — all enforced by the
``extraction_proposals_guard`` trigger (migration ``0017``). SELECT/INSERT/UPDATE (no
DELETE). Promotion to the canonical spine is Slice 14b (not here).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.intake.compiler import ARTIFACT_KINDS, ASSUMPTION_CLASSIFICATIONS
from app.models.base import Base

_KINDS_SQL = ", ".join(repr(k) for k in ARTIFACT_KINDS)
_CLASSIFICATIONS_SQL = ", ".join(repr(c) for c in ASSUMPTION_CLASSIFICATIONS)
_CLASSIFICATION_CHECK = (
    f"(proposed_kind = 'assumption' AND proposed_classification IS NOT NULL "
    f"AND proposed_classification IN ({_CLASSIFICATIONS_SQL})) "
    "OR (proposed_kind <> 'assumption' AND proposed_classification IS NULL)"
)
_STATUSES = ("pending", "approved", "rejected")


class ExtractionProposal(Base):
    __tablename__ = "extraction_proposals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["extraction_run_id", "project_id", "tenant_id"],
            ["extraction_runs.id", "extraction_runs.project_id", "extraction_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        ForeignKeyConstraint(
            ["source_document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            ondelete="RESTRICT",
            name="document_project_tenant",
        ),
        CheckConstraint(f"proposed_kind IN ({_KINDS_SQL})", name="proposed_kind_valid"),
        CheckConstraint(_CLASSIFICATION_CHECK, name="proposed_classification_valid"),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _STATUSES)})", name="status_valid"
        ),
        # FK target for the Slice-14b extraction_promotions composite FK.
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_extraction_proposals_id_project_tenant"
        ),
        Index("ix_extraction_proposals_tenant_run", "tenant_id", "extraction_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposed_kind: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    extracted_by: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
