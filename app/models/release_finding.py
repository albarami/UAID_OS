"""``release_findings`` — tenant-owned security/shortcut release findings (Slice 23, §13.4/§916-920).

Tenant-owned + RLS; **no DELETE**. A DB guard (migration ``0022``) enforces the lifecycle:
created ``open``; one-way ``open`` → ``resolved``|``false_positive``|``accepted``|``superseded``;
**critical findings can never be accepted**; ``accepted`` requires a usable risk-acceptance record
(active + non-expired + non-blocking + same tenant/project + ``issue_id == finding.id``). Per
transition only the relevant lifecycle fields are mutable; all identity/prose/source fields are
immutable after create. Manual findings remain ``caller_supplied_unverified``. Slice 44 adds a
connector-verified security-scan path whose rows composite-link to one trusted category observation;
that provenance proves bounded observation lineage, not scanner infallibility. Findings never enable
go-live by themselves.
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


class ReleaseFinding(Base):
    __tablename__ = "release_findings"
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
        ForeignKeyConstraint(
            ["security_scan_category_result_id", "project_id", "tenant_id", "category"],
            [
                "security_scan_category_results.id",
                "security_scan_category_results.project_id",
                "security_scan_category_results.tenant_id",
                "security_scan_category_results.category",
            ],
            ondelete="RESTRICT",
            name="security_scan_category_project_tenant",
        ),
        UniqueConstraint("id", "tenant_id", name="uq_release_findings_id_tenant"),
        Index(
            "uq_release_findings_scan_fingerprint",
            "tenant_id",
            "security_scan_category_result_id",
            "scan_finding_fingerprint",
            unique=True,
            postgresql_where=text("security_scan_category_result_id IS NOT NULL"),
        ),
        Index(
            "ix_release_findings_tenant_project_type_status",
            "tenant_id",
            "project_id",
            "finding_type",
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
    finding_type: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
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
    security_scan_category_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    scan_finding_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
