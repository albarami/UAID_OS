"""``intake_categories`` — tenant-owned declared intake categories (Slice 15, §4.2).

One declaration per ``(tenant, project, category)`` for the declarable §4.2 intake
categories (inputs for a *later* R3–R5 readiness slice; the auditor is untouched here).
Each row carries exactly one source — a document (accepted, same project, + locator) XOR
a bounded origin label — enforced by a CHECK and a guard trigger (migration ``0019``).
Content/identity keys (``id``/``tenant_id``/``project_id``/``category``/``created_at``)
are immutable; rows are never deleted. ``data`` holds non-secret structured metadata only
(the secrets category holds reference metadata, never values; see ``app.intake.categories``).
"""

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.intake.categories import DECLARABLE_INTAKE_CATEGORIES
from app.models.base import Base, TimestampMixin

_CATEGORIES_SQL = ", ".join(repr(c) for c in DECLARABLE_INTAKE_CATEGORIES)
# Exactly one source: a document (with locator, no origin) XOR an origin label.
_SOURCE_XOR = (
    "(source_document_id IS NOT NULL AND locator IS NOT NULL AND origin IS NULL) "
    "OR (source_document_id IS NULL AND locator IS NULL AND origin IS NOT NULL)"
)


class IntakeCategory(Base, TimestampMixin):
    __tablename__ = "intake_categories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        # Document-backed source: pinned to the SAME tenant+project document (dormant when NULL).
        ForeignKeyConstraint(
            ["source_document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            ondelete="RESTRICT",
            name="document_project_tenant",
        ),
        CheckConstraint(f"category IN ({_CATEGORIES_SQL})", name="category_valid"),
        CheckConstraint("status IN ('declared', 'not_applicable')", name="status_valid"),
        CheckConstraint("octet_length(summary) <= 4096", name="summary_bounded"),
        CheckConstraint(
            "origin IS NULL OR octet_length(origin) BETWEEN 1 AND 512", name="origin_bounded"
        ),
        CheckConstraint(_SOURCE_XOR, name="source_xor"),
        UniqueConstraint("tenant_id", "project_id", "category", name="uq_intake_categories_cat"),
        Index("ix_intake_categories_tenant_project", "tenant_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'declared'"))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str | None] = mapped_column(Text, nullable=True)
