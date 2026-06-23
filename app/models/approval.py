"""``approvals`` — tenant-owned approval requests (Slice 4, §18).

`requires_explicit_approval` is the non-bypassable flag (True for §2.6 actions):
when True, only an APPROVED status unblocks the dependent action. `risk_tier`
drives only the non-response/UX behavior. Slice 27: `requested_by_provenance` (requester) and
`approver_provenance` (resolver) carry `request_authenticated` when that party is a request-
authenticated principal — key-custody-based, **not** a human signature — else
`caller_supplied_unverified`.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from app.models.base import Base, TimestampMixin

_STATUSES = ("pending", "approved", "rejected", "cancelled", "expired", "proceeded_by_policy")
_TIERS = ("low", "medium", "high", "production")


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        # Enables the composite FK from approval_events(approval_id, tenant_id).
        UniqueConstraint("id", "tenant_id"),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _STATUSES)})", name="status_valid"
        ),
        CheckConstraint(
            f"risk_tier IN ({', '.join(repr(t) for t in _TIERS)})", name="risk_tier_valid"
        ),
        # Slice 27: requester vs resolver provenance, each constrained to the identity-axis tiers.
        CheckConstraint(
            "requested_by_provenance IN ('caller_supplied_unverified', 'request_authenticated')",
            name="requested_by_provenance_valid",
        ),
        CheckConstraint(
            "approver_provenance IN ('caller_supplied_unverified', 'request_authenticated')",
            name="approver_provenance_valid",
        ),
        Index(None, "tenant_id"),
        Index("ix_approvals_tenant_id_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    subject_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_tier: Mapped[str] = mapped_column(Text, nullable=False)
    requires_explicit_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    # Slice 27: provenance of the requester identity (resolver provenance is approver_provenance).
    requested_by_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
