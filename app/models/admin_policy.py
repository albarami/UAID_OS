"""Read-only ORM models for Slice 63 ledgers.

Rows are written by the definer writer or the operator path, never by the
runtime ORM as a bypass of those paths.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.admin.db_checks import CHANGE_CHECK_CONSTRAINTS, EVENT_CHECK_CONSTRAINTS
from app.models.base import Base


class AdminPolicyChange(Base):
    """Append-only policy-change ledger. Runtime role is SELECT-only."""

    __tablename__ = "admin_policy_changes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["admin_action_id", "project_id", "tenant_id"],
            ["admin_actions.id", "admin_actions.project_id", "admin_actions.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            [
                "autonomy_policies.id",
                "autonomy_policies.project_id",
                "autonomy_policies.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("admin_action_id", name="uq_admin_policy_changes_action"),
        *[CheckConstraint(sql, name=conv(name)) for name, sql in CHANGE_CHECK_CONSTRAINTS],
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
    admin_action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    autonomy_policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    previous_autonomy_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    new_autonomy_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    override_key_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class TenantAdminEvent(Base):
    """Append-only tenant-admin event ledger. Runtime role is SELECT-only."""

    __tablename__ = "tenant_admin_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["admin_role_grant_id", "tenant_id", "subject_principal", "admin_role"],
            [
                "admin_role_grants.id",
                "admin_role_grants.tenant_id",
                "admin_role_grants.principal_subject",
                "admin_role_grants.admin_role",
            ],
            name="fk_tae_grant_identity",
            ondelete="RESTRICT",
        ),
        *[CheckConstraint(sql, name=conv(name)) for name, sql in EVENT_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_principal: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_role_grant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    performed_by: Mapped[str] = mapped_column(Text, nullable=False)
    performed_by_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
