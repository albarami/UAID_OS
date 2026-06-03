"""``autonomy_policies`` — tenant-owned per-project autonomy level + overrides.

Tenant-owned (RLS-protected like `projects`/`project_runs`). `autonomy_level` is
0–5 (A0–A5); `overrides` holds tighten-only per-action overrides (§5.3). A run
inherits its project's policy. A project with no row denies everything
(fail-closed; enforced in the repository's `decision_for`).
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AutonomyPolicy(Base, TimestampMixin):
    __tablename__ = "autonomy_policies"
    __table_args__ = (
        # Pin the policy to its project's tenant (mirrors project_runs).
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint("autonomy_level BETWEEN 0 AND 5", name="autonomy_level_valid"),
        UniqueConstraint("tenant_id", "project_id"),
        Index(None, "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    autonomy_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    overrides: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
