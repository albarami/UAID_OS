"""``agent_instances`` — TENANT-OWNED binding of a global ``agent_version`` into a
tenant project/run (§9.7, §17.4).

Tenant-scoped (RLS ENABLE+FORCE + ``tenant_isolation``), mirroring ``approvals`` /
``autonomy_policies``. Stores ``version_id`` only — the blueprint is reached via
``agent_versions.blueprint_id`` (single source of truth).

Structural integrity:
- ``(project_id, tenant_id) -> projects(id, tenant_id)`` pins the instance to its
  project's tenant (INV-3).
- ``(active_run_id, project_id, tenant_id) -> project_runs(id, project_id, tenant_id)``
  pins an active run to the SAME project AND tenant (not merely the same tenant).
  ``active_run_id`` is NULL until bound (MATCH SIMPLE: the FK is dormant while NULL).

Binding immutability (migration ``0007`` trigger): ``tenant_id``, ``project_id``,
``version_id``, ``instance_key`` and ``created_at`` cannot be mutated after insert;
``active_run_id`` is set-once (NULL -> value; no rebinding to a different run).
Mutable lifecycle fields: ``status``, ``active_run_id`` (once), ``updated_at``.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_INSTANCE_STATUSES = ("registered", "active", "suspended", "retired")
# One LIVE binding per (tenant, project, instance_key); retired rows may repeat.
_LIVE_STATUS_PREDICATE = "status IN ('registered', 'active', 'suspended')"


class AgentInstance(Base, TimestampMixin):
    __tablename__ = "agent_instances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["active_run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _INSTANCE_STATUSES)})",
            name="status_valid",
        ),
        Index(
            "uq_agent_instances_live_key",
            "tenant_id",
            "project_id",
            "instance_key",
            unique=True,
            postgresql_where=text(_LIVE_STATUS_PREDICATE),
        ),
        # Slice 39 (B6): composite-FK target for agent_realizations (additive; verified absent).
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_agent_instances_id_project_tenant"
        ),
        Index(None, "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    instance_key: Mapped[str] = mapped_column(String, nullable=False)
    active_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'registered'"))
