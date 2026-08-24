"""Tenant-owned admin RBAC rows (Slice 63)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.admin.db_checks import ACTION_CHECK_CONSTRAINTS, GRANT_CHECK_CONSTRAINTS
from app.models.base import Base


class AdminRoleGrant(Base):
    """Tenant-owned role grant. Runtime role is SELECT-only."""

    __tablename__ = "admin_role_grants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "principal_subject", "admin_role"),
        UniqueConstraint("id", "tenant_id"),
        UniqueConstraint(
            "id",
            "tenant_id",
            "principal_subject",
            "admin_role",
            name="uq_admin_role_grants_identity",
        ),
        *[CheckConstraint(sql, name=conv(name)) for name, sql in GRANT_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    principal_subject: Mapped[str] = mapped_column(Text, nullable=False)
    admin_role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    granted_by: Mapped[str] = mapped_column(Text, nullable=False)
    granted_by_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class AdminAction(Base):
    """Tenant-owned admin action. Runtime role may INSERT."""

    __tablename__ = "admin_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "project_id", "tenant_id"),
        *[CheckConstraint(sql, name=conv(name)) for name, sql in ACTION_CHECK_CONSTRAINTS],
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
    action_kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor_principal: Mapped[str] = mapped_column(Text, nullable=False)
    actor_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    required_role: Mapped[str] = mapped_column(Text, nullable=False)
    actor_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
