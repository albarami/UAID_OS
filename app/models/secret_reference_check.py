"""``secret_reference_checks`` — tenant-owned, append-only secrets-reference evidence (Slice 32,
R5 App. A l.2968 / §26.3 / spec:1094).

One immutable row per observation of whether a declared ``secrets_and_credentials_manifest`` reference
**resolves in its approved manager**. Append-only (migration ``0031``). Records **only**
``(manager, reference_name, outcome, resolved)`` — **there is NO value column** (structural guarantee that
no secret value is ever persisted). ``manager`` is bounded safe text (any declared identifier); a non-``env``
manager is DB-forced to ``unsupported_manager`` + not-resolved (B1). ``reference_name`` is a bounded safe
shape that accepts legitimate names like ``prod/db_password`` (B2 — no value denylist). Honesty:
``resolved = (outcome = 'resolved')``. **Store-only — never flips an A5 gate / readiness level this slice.**
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


class SecretReferenceCheck(Base):
    __tablename__ = "secret_reference_checks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name="ck_src_provenance_valid",
        ),
        CheckConstraint("manager ~ '^[a-z0-9_.:-]{1,64}$'", name="ck_src_manager_shape"),
        # Shape via char-class + separate length bound: Postgres regex {m,n} caps n at 255
        # (RE_DUP_MAX), so a {1,256} bound is invalid — the length CHECK carries the 256 bound.
        CheckConstraint(
            "reference_name ~ '^[A-Za-z0-9_./:-]+$'", name="ck_src_reference_name_shape"
        ),
        CheckConstraint(
            "char_length(reference_name) BETWEEN 1 AND 256", name="ck_src_reference_name_len"
        ),
        CheckConstraint(
            "outcome IN ('resolved','not_found','unsupported_manager','probe_error')",
            name="ck_src_outcome_valid",
        ),
        # Honesty invariant: resolved iff outcome is 'resolved'.
        CheckConstraint("resolved = (outcome = 'resolved')", name="ck_src_resolved_invariant"),
        # B1: a non-'env' (unsupported) manager must be recorded as unsupported_manager + not resolved.
        CheckConstraint(
            "manager = 'env' OR (outcome = 'unsupported_manager' AND resolved = false)",
            name="ck_src_unsupported_manager_rule",
        ),
        Index(
            "ix_src_tenant_project_ref_created",
            "tenant_id",
            "project_id",
            "manager",
            "reference_name",
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
    manager: Mapped[str] = mapped_column(Text, nullable=False)
    reference_name: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
