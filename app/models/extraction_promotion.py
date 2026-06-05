"""``extraction_promotions`` — tenant-owned, append-only promotion link (Slice 14b).

One immutable row per promoted proposal: the bridge from an approved
``extraction_proposal`` to the canonical-spine ``intake_artifacts`` row it became.
``UNIQUE(tenant_id, extraction_proposal_id)`` enforces **promote-once**; composite FKs
pin both the proposal and the artifact to the same tenant+project. Append-only:
SELECT/INSERT only; UPDATE/DELETE/TRUNCATE blocked by triggers (migration ``0018``).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
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

from app.models.base import Base


class ExtractionPromotion(Base):
    __tablename__ = "extraction_promotions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["extraction_proposal_id", "project_id", "tenant_id"],
            [
                "extraction_proposals.id",
                "extraction_proposals.project_id",
                "extraction_proposals.tenant_id",
            ],
            ondelete="RESTRICT",
            name="proposal_project_tenant",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            ondelete="RESTRICT",
            name="artifact_project_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "extraction_proposal_id", name="uq_extraction_promotions_proposal"
        ),
        Index("ix_extraction_promotions_tenant_project", "tenant_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    promoted_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
