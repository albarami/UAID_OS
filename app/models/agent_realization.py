"""``agent_realizations`` + ``agent_realization_reviewers`` — tenant-owned realization records (Slice 39).

``agent_realizations`` wraps a Slice-6 ``agent_instance`` with the §9.2 runtime realization: the
``qualification_status`` (only ``unqualified`` is INSERT-able this slice — B4; the ``qualified`` transition
is Slice 40) and the FK-backed reviewer linkage (``agent_realization_reviewers``; the §2.2 self-review guard
in migration ``0038`` resolves the ACTUAL blueprint via instance→version — B3, no denormalized blueprint).
Both are RLS, SELECT/INSERT-only (migration ``0038`` block triggers are the authoritative backstop). The
Slice-6 ``agent_instances`` row stays the immutable binding; the qualification lifecycle lives here.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.factory import QUALIFICATION_STATUSES
from app.models.base import Base

_QS = ", ".join(repr(s) for s in QUALIFICATION_STATUSES)


class AgentRealization(Base):
    __tablename__ = "agent_realizations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            ondelete="RESTRICT",
            name="instance_project_tenant",
        ),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(f"qualification_status IN ({_QS})", name="qualification_status_valid"),
        UniqueConstraint("instance_id", name="uq_agent_realizations_instance"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_agent_realizations_id_project_tenant"
        ),
        Index("ix_agent_realizations_instance", "tenant_id", "instance_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qualification_status: Mapped[str] = mapped_column(Text, nullable=False)
    realized_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class AgentRealizationReviewer(Base):
    __tablename__ = "agent_realization_reviewers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["realization_id", "project_id", "tenant_id"],
            [
                "agent_realizations.id",
                "agent_realizations.project_id",
                "agent_realizations.tenant_id",
            ],
            ondelete="RESTRICT",
            name="realization_project_tenant",
        ),
        ForeignKeyConstraint(
            ["reviewer_blueprint_id"],
            ["agent_blueprints.id"],
            ondelete="RESTRICT",
            name="reviewer_blueprint",
        ),
        UniqueConstraint(
            "realization_id", "reviewer_blueprint_id", name="uq_agent_realization_reviewers_pair"
        ),
        Index("ix_agent_realization_reviewers_realization", "tenant_id", "realization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    realization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_blueprint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
