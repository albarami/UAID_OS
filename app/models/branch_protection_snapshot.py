"""``branch_protection_snapshots`` — tenant-owned, append-only branch-protection evidence
(Slice 26, Appendix B #3 / §26.3).

One immutable row per observation of a repo's branch-protection configuration (the gate-#3 evidence
class). Append-only: SELECT/INSERT only for the runtime role, with UPDATE/DELETE/TRUNCATE blocked by
triggers (migration ``0025``). ``provenance`` is a two-tier axis: the caller path writes
``caller_supplied_unverified``; the **Slice-28 connector path** writes ``connector_verified`` (migration
``0027`` relaxes the guard). ``repo_ref`` is constrained to a GitHub-first ``owner/repo`` slug with a
token-prefix denylist (``ck_bps_repo_ref_slug`` + ``ck_bps_repo_ref_not_tokenish``);
``required_status_checks`` is a JSON array (``ck_bps_checks_array`` + the §4.1 guard's per-element +
count strict-verify). These snapshots never enable go-live; **gate #3 PASSes (Slice 28) only from
repo-bound latest ``connector_verified`` + fresh + sufficient evidence**.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BranchProtectionSnapshot(Base):
    __tablename__ = "branch_protection_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name="ck_bps_provenance_valid",
        ),
        CheckConstraint("provider IN ('github')", name="ck_bps_provider_valid"),
        CheckConstraint("required_status_check_count >= 0", name="ck_bps_check_count_nonneg"),
        CheckConstraint(
            "repo_ref ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$'",
            name="ck_bps_repo_ref_slug",
        ),
        CheckConstraint(
            "repo_ref !~* '/(gh[opusr]_|github_pat_)'",
            name="ck_bps_repo_ref_not_tokenish",
        ),
        CheckConstraint(
            "jsonb_typeof(required_status_checks) = 'array'",
            name="ck_bps_checks_array",
        ),
        Index(
            "ix_branch_protection_snapshots_tenant_project_created",
            "tenant_id",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    repo_ref: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str] = mapped_column(Text, nullable=False)
    protection_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    required_pull_request_reviews: Mapped[bool] = mapped_column(Boolean, nullable=False)
    required_status_checks: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    required_status_check_count: Mapped[int] = mapped_column(Integer, nullable=False)
    enforce_admins: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    # Caller-asserted observation time (informational; the connector sets it in Slice 28). NULL-able.
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # clock_timestamp() so same-transaction snapshots order deterministically (latest()).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
