"""``release_issues`` — tenant-owned open-issue / blocker store (Slice 24, spec §24.1 / Appendix B #7).

Tenant-owned + RLS; **no DELETE**. A DB guard (migration ``0023``) enforces the lifecycle:
created ``open``; one-way ``open`` → ``resolved``|``accepted``|``superseded``; **critical (and any
hard-refusal ``blocking_category``) issues can never be accepted**; ``critical`` implies
``blocking``; ``accepted`` requires a usable risk-acceptance record (active + non-expired +
non-blocking + same tenant/project + ``issue_id == issue.id``). Per transition only the relevant
lifecycle fields are mutable; all identity/prose/source fields are immutable after create.
``source``/``source_provenance`` are UNVERIFIED — not authoritative issue provenance. These issues
never enable go-live.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class ReleaseIssue(Base):
    __tablename__ = "release_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        # nullable composite FK to the accepted risk-acceptance record (same tenant).
        ForeignKeyConstraint(
            ["risk_acceptance_record_id", "tenant_id"],
            ["risk_acceptance_records.id", "risk_acceptance_records.tenant_id"],
            ondelete="RESTRICT",
            name="risk_acceptance_tenant",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_release_issues_id_tenant"),
        Index(
            "ix_release_issues_tenant_project_status",
            "tenant_id",
            "project_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    issue_category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocking_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    risk_acceptance_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
