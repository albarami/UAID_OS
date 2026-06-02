"""``project_runs`` — tenant-owned. A run's tenant is pinned to its project's
tenant by the composite FK ``(project_id, tenant_id) -> projects(id, tenant_id)``
(INV-3); ``tenant_id`` also FKs ``tenants(id)`` directly (INV-2).
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

_RUN_STATUSES = ("created", "running", "paused", "blocked", "completed", "failed")


class ProjectRun(Base, TimestampMixin):
    __tablename__ = "project_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _RUN_STATUSES)})",
            name="status_valid",
        ),
        Index(None, "tenant_id"),
        Index(None, "project_id"),
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
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'created'"))

    project: Mapped["Project"] = relationship(back_populates="runs")  # noqa: F821
