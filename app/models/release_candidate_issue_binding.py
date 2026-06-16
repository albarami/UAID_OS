"""``release_candidate_issue_bindings`` — append-only, freeze-locked issue membership for a release
candidate (Slice 25, Appendix B #7).

Links a ``release_candidates`` row to a ``release_issues`` row (the issues KNOWN for this release —
**not** a completeness claim). Tenant-owned + RLS; **append-only** (SELECT/INSERT only). A binding may
be inserted **only while the candidate is ``draft``**; once the candidate is ``frozen`` the membership
set is immutable (DB guard, migration ``0024``). No unbind. **Option A FK shape (additive — no
``release_issues`` mutation):** the candidate side uses the composite ``(id, project_id, tenant_id)``
target; the issue side uses the existing ``(id, tenant_id)`` target; a trigger verifies the issue's
project matches.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReleaseCandidateIssueBinding(Base):
    __tablename__ = "release_candidate_issue_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
            name="release_candidate_proj_tenant",
        ),
        ForeignKeyConstraint(
            ["release_issue_id", "tenant_id"],
            ["release_issues.id", "release_issues.tenant_id"],
            ondelete="RESTRICT",
            name="release_issue_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "release_candidate_id",
            "release_issue_id",
            name="uq_release_candidate_issue_binding",
        ),
        Index(
            "ix_release_candidate_issue_bindings_candidate",
            "tenant_id",
            "release_candidate_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
