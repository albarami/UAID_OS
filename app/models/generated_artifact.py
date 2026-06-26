"""``generated_artifacts`` — tenant-owned, inert NON-BINDING canonical-artifact drafts (Slice 36).

One row per generation attempt. A ``succeeded`` row holds an inert §6.3-typed draft (``title``/``body``)
stamped ``system_authored_unapproved`` (§7.2) with the generator lineage recorded (§7.4). An independent
approval carrying bound §7.3 evidence moves it to ``system_authored_human_approved`` /
``system_authored_independent_approved`` (binding-eligible) or ``disputed`` — NEVER into the binding spine
this slice (store/infra-only; promotion deferred). SELECT/INSERT/UPDATE; no DELETE/TRUNCATE (migration
``0035``). ``source_document_id`` is composite-FK pinned to an ACCEPTED same-project/tenant document. The
stored ``title``/``body`` may contain source-derived sensitive material and is NEVER audited/logged.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.intake.generator import APPROVAL_BASES, ARTIFACT_TYPES, AUTHORSHIP_STATUSES, OUTCOMES
from app.models.base import Base

_AT = ", ".join(repr(v) for v in ARTIFACT_TYPES)
_AUTH = ", ".join(repr(v) for v in AUTHORSHIP_STATUSES)
_OUT = ", ".join(repr(v) for v in OUTCOMES)
_BASES = ", ".join(repr(v) for v in APPROVAL_BASES)


class GeneratedArtifact(Base):
    __tablename__ = "generated_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["source_document_id", "project_id", "tenant_id"],
            ["documents.id", "documents.project_id", "documents.tenant_id"],
            ondelete="RESTRICT",
            name="document_project_tenant",
        ),
        CheckConstraint(f"artifact_type IN ({_AT})", name="artifact_type_valid"),
        CheckConstraint(f"outcome IN ({_OUT})", name="outcome_valid"),
        CheckConstraint(f"authorship_status IN ({_AUTH})", name="authorship_status_valid"),
        # B1/v3 — the deferred bases (domain_authority, reference_oracle) are structurally forbidden.
        CheckConstraint(
            f"approval_basis IS NULL OR approval_basis IN ({_BASES})", name="approval_basis_valid"
        ),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_generated_artifacts_id_project_tenant"
        ),
        Index(
            "ix_generated_artifacts_latest",
            "tenant_id",
            "project_id",
            "source_document_id",
            "artifact_type",
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
    source_document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    cost_external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorship_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'system_authored_unapproved'")
    )
    generated_by: Mapped[str] = mapped_column(Text, nullable=False)
    generator_prompt_family: Mapped[str] = mapped_column(Text, nullable=False)
    generator_model_route: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_prompt_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_authority: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_model_route: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
