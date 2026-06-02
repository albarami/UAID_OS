"""``projects`` — tenant-owned. Carries a denormalized ``tenant_id`` and a
``UNIQUE(id, tenant_id)`` so ``project_runs`` can reference it with a composite
FK that makes cross-tenant runs structurally impossible (INV-3).
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug"),
        # Enables the composite FK from project_runs(project_id, tenant_id).
        UniqueConstraint("id", "tenant_id"),
        Index(None, "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)

    runs: Mapped[list["ProjectRun"]] = relationship(  # noqa: F821
        back_populates="project"
    )
