"""``intake_provenance`` — tenant-owned, append-only Sanad source store (Slice 11, §3.4).

One row per source backing an :class:`IntakeArtifact`. ``document_id`` (when set) is
pinned to an accepted document of the SAME tenant+project by a composite FK plus a
``BEFORE INSERT`` trigger that rejects non-``accepted`` documents (migration ``0014``);
a NULL ``document_id`` is a non-document origin (e.g. a recorded human decision) and
skips the document FK (MATCH SIMPLE). Append-only (SELECT/INSERT only).
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntakeProvenance(Base):
    __tablename__ = "intake_provenance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        # Pin the source to its artifact within the same project+tenant.
        ForeignKeyConstraint(
            ["artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            ondelete="RESTRICT",
            name="artifact_project_tenant",
        ),
        # Document-backed source: pinned to the SAME tenant+project document (dormant when NULL).
        ForeignKeyConstraint(
            ["document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            ondelete="RESTRICT",
            name="document_project_tenant",
        ),
        CheckConstraint("octet_length(origin) BETWEEN 1 AND 512", name="origin_bounded"),
        Index("ix_intake_provenance_tenant_artifact", "tenant_id", "artifact_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
