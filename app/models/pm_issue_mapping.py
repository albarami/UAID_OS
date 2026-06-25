"""``pm_issue_mappings`` — tenant-owned, append-only PM/issue-tracker mapping (Slice 34, §12.3 / §26.3).

One immutable row per observation of an external PM (Jira) issue's state — **mapping-only** (no
``release_issues`` created or linked this slice). Records observed facts only: ``external_ref`` /
``external_status`` (raw Jira status, bounded) / ``board_column`` (a §12.3 column or ``unmapped``) /
``title_present`` (presence, **not** the title). **There is NO title/description/credential/release_issue_id
column** (structural: no secret/free-text, no ``release_issues`` coupling). Idempotent **latest-wins** keyed
by ``(tenant_id, project_id, external_system, instance_key, external_ref)`` (B7). ``connector_verified`` =
OBSERVATION-verified, **not** issue-provenance-complete. **Store/infra-only — never flips an A5 gate.**
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_BOARD_COLUMNS = (
    "backlog",
    "analysis",
    "requirements_review",
    "ready_for_development",
    "in_progress",
    "developer_self_check",
    "specialist_review",
    "changes_requested",
    "qa_testing",
    "security_review",
    "shortcut_detection",
    "acceptance_verification",
    "evidence_audit",
    "ready_for_release",
    "released",
    "done",
    "unmapped",
)


class PMIssueMapping(Base):
    __tablename__ = "pm_issue_mappings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name="ck_pim_provenance_valid",
        ),
        CheckConstraint("external_system IN ('jira')", name="ck_pim_external_system_valid"),
        CheckConstraint("instance_key ~ '^[a-z0-9_.:-]{1,64}$'", name="ck_pim_instance_key_shape"),
        CheckConstraint(
            "external_ref ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'", name="ck_pim_external_ref_shape"
        ),
        CheckConstraint(
            "external_ref !~* '(gh[opusr]_|github_pat_)'", name="ck_pim_external_ref_not_tokenish"
        ),
        CheckConstraint(
            "char_length(external_status) BETWEEN 1 AND 256", name="ck_pim_external_status_len"
        ),
        CheckConstraint(
            "board_column IN (" + ", ".join(repr(c) for c in _BOARD_COLUMNS) + ")",
            name="ck_pim_board_column_valid",
        ),
        Index(
            "ix_pim_tenant_project_system_instance_ref_created",
            "tenant_id",
            "project_id",
            "external_system",
            "instance_key",
            "external_ref",
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
    external_system: Mapped[str] = mapped_column(Text, nullable=False)
    instance_key: Mapped[str] = mapped_column(Text, nullable=False)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    external_status: Mapped[str] = mapped_column(Text, nullable=False)
    board_column: Mapped[str] = mapped_column(Text, nullable=False)
    title_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
