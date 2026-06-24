"""``pull_request_evidence_snapshots`` — tenant-owned, append-only PR-evidence (Slice 29, §12.3-12.4).

One immutable row per observation of a pull request (the App.-B #7/#8 provenance *feed*). Append-only:
SELECT/INSERT only for the runtime role, with UPDATE/DELETE/TRUNCATE blocked by triggers (migration
``0028``). ``provenance`` is a two-tier axis: the caller path writes ``caller_supplied_unverified``; the
connector path writes ``connector_verified`` (both writable from this slice — the app validators decide
the path; the DB allows both). ``repo_ref`` reuses the Slice-26/28 ``owner/repo`` slug + token denylist.
``presence_flags`` record §12.4 **presence** (declared/observed, never adequacy); ``check_status_summary``
is **observed-only** (nullable, NOT required-check satisfaction); ``merged_to_declared_protected_branch_observed``
is a cross-referenced observation (true only when verified branch-protection evidence backs it);
``approval_count`` is DB-enforced ``= jsonb_array_length(approver_principals)``. These snapshots **never
flip an A5 gate** (store-only — ``production_autonomy`` is untouched, ruleset stays ``slice28.v1``).
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


class PullRequestEvidenceSnapshot(Base):
    __tablename__ = "pull_request_evidence_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name="ck_pres_provenance_valid",
        ),
        CheckConstraint("provider IN ('github')", name="ck_pres_provider_valid"),
        CheckConstraint("pr_number > 0", name="ck_pres_pr_number_pos"),
        CheckConstraint("pr_state IN ('open','closed','merged')", name="ck_pres_pr_state_valid"),
        CheckConstraint("approval_count >= 0", name="ck_pres_approval_count_nonneg"),
        CheckConstraint(
            "repo_ref ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$'",
            name="ck_pres_repo_ref_slug",
        ),
        CheckConstraint(
            "repo_ref !~* '/(gh[opusr]_|github_pat_)'",
            name="ck_pres_repo_ref_not_tokenish",
        ),
        CheckConstraint(
            "merge_commit_sha IS NULL OR merge_commit_sha ~ '^[0-9a-f]{7,64}$'",
            name="ck_pres_merge_commit_sha",
        ),
        Index(
            "ix_pres_tenant_project_pr_created",
            "tenant_id",
            "project_id",
            "provider",
            "repo_ref",
            "pr_number",
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
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # --- provider PR facts (Q2) ---
    pr_state: Mapped[str] = mapped_column(Text, nullable=False)
    merged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merge_commit_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_to_declared_protected_branch_observed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # --- observed check status (B-29-1) — NULL = not observed ---
    check_status_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # --- §12.4 presence (Q2) ---
    presence_flags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # --- normalized identity facts (Q3, B-29-5/6/7) ---
    author_principal: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver_principals: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    reviewer_principals: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    requested_reviewer_principals: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    requested_reviewers_observed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    merger_principal: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # --- structural-only separation flags (Q3) ---
    self_approval_observed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    self_merge_observed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    review_separation_observed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # --- traceability (Q5, repo-validated existence/kind/project) ---
    traceability_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # --- provenance / freshness ---
    provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
