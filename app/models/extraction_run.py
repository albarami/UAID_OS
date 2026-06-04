"""``extraction_runs`` — tenant-owned, append-only LLM extraction outcomes (Slice 14a).

One IMMUTABLE final-outcome row per extraction (terminal ``status``), with an
app-minted ``id`` (the ``run_id`` used to key the cost event before insert). Append-only:
SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked by triggers (migration ``0017``). The
``document_id`` is composite-FK pinned to the same tenant/project and DB-checked to be an
**accepted** document. No document content / proposed text is stored here.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_STATUSES = ("succeeded", "failed", "blocked_by_budget", "refused_injection")


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
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
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _STATUSES)})", name="status_valid"
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_extraction_runs_id_project_tenant"),
        Index("ix_extraction_runs_tenant_project", "tenant_id", "project_id"),
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
    status: Mapped[str] = mapped_column(Text, nullable=False)
    cost_external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
