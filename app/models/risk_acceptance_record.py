"""``risk_acceptance_records`` — tenant-owned go-live risk-acceptance records (Slice 22, §24.1/§27.10).

A signed acceptance of a known, non-blocking open issue so a release may proceed (§24.1). Tenant-owned
+ RLS; **no DELETE**. After creation only ``status`` and ``updated_at`` are mutable — a DB guard
trigger (migration ``0021``) rejects any other column change. Lifecycle is one-way
``active`` → ``expired``|``revoked``|``superseded``. ``approver_provenance`` is
``caller_supplied_unverified`` by default, or (Slice 27) ``request_authenticated`` under **actor-bound**
signer semantics — **key-custody-based, not** a human signature; records never enable go-live.
``blocking_category`` (if set) names a
hard-refusal category — such records are rejected at creation and never counted.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RiskAcceptanceRecord(Base):
    __tablename__ = "risk_acceptance_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id", "release_id"],
            [
                "release_candidates.tenant_id",
                "release_candidates.project_id",
                "release_candidates.release_ref",
            ],
            ondelete="RESTRICT",
            name="fk_risk_acceptance_release_ref",
        ),
        CheckConstraint(
            "subject_type IS NULL OR subject_type IN ('release_issue','release_finding')",
            name="subject_type_valid",
        ),
        # FK target for risk_acceptance_events (record pinned to its tenant).
        UniqueConstraint("id", "tenant_id", name="uq_risk_acceptance_records_id_tenant"),
        Index(
            "ix_risk_acceptance_records_tenant_project_status",
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
    # Slice 47 keeps the spec-facing string but FK-pins new release refs to release_candidates.
    release_id: Mapped[str] = mapped_column(Text, nullable=False)
    issue_id: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL is legacy-only; the Slice-47 guard requires a subject kind on every new row.
    subject_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    affected_requirements: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    reason_for_acceptance: Mapped[str] = mapped_column(Text, nullable=False)
    business_impact: Mapped[str] = mapped_column(Text, nullable=False)
    compensating_controls: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    rollback_or_mitigation_plan: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_links: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    required_follow_up_ticket: Mapped[str] = mapped_column(Text, nullable=False)
    included_in_release_notes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    approver: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_by: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    approval_authority_source: Mapped[str] = mapped_column(Text, nullable=False)
    blocking_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The only fields mutable after creation (guard trigger): status + updated_at.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    approver_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
