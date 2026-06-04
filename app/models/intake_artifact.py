"""``intake_artifacts`` — tenant-owned, append-only canonical intake spine (Slice 11, §4.2/§4.4).

A unified table for the minimal canonical set, discriminated by ``kind``
(requirement / acceptance_criterion / test_oracle / assumption). Every row is a
Sanad-backed fact: it may not commit without ≥1 ``intake_provenance`` row (a
deferrable constraint trigger, migration ``0014``). Append-only (SELECT/INSERT only;
UPDATE/DELETE/TRUNCATE blocked) — corrections are a future revision model, not edits.

``classification`` carries the §4.4 assumption label and is constrained so that only
``assumption`` rows may (and must) carry one; every other kind must be ``NULL``.
``parent_id`` is a self triple-FK (acceptance_criterion→requirement, test_oracle→
acceptance_criterion) pinned to the same project+tenant. ``actor`` for the change is
an untrusted caller label recorded in the audit log, never here.
"""

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.intake.compiler import ARTIFACT_KINDS, ASSUMPTION_CLASSIFICATIONS
from app.models.base import Base, TimestampMixin

_KINDS_SQL = ", ".join(repr(k) for k in ARTIFACT_KINDS)
_CLASSIFICATIONS_SQL = ", ".join(repr(c) for c in ASSUMPTION_CLASSIFICATIONS)
# Tightened §4.4 check: assumptions MUST carry a valid classification; others MUST be NULL.
# ``classification IS NOT NULL`` is explicit so the assumption clause evaluates to FALSE
# (not NULL) for a missing classification — a CHECK passes on NULL, so without it an
# assumption with no classification would slip through.
_CLASSIFICATION_CHECK = (
    f"(kind = 'assumption' AND classification IS NOT NULL "
    f"AND classification IN ({_CLASSIFICATIONS_SQL})) "
    "OR (kind <> 'assumption' AND classification IS NULL)"
)


class IntakeArtifact(Base, TimestampMixin):
    __tablename__ = "intake_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        # Self triple-FK: a child is pinned to the same project AND tenant (dormant when NULL).
        ForeignKeyConstraint(
            ["parent_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            ondelete="RESTRICT",
            name="parent_project_tenant",
        ),
        CheckConstraint(f"kind IN ({_KINDS_SQL})", name="kind_valid"),
        CheckConstraint("octet_length(ref) BETWEEN 1 AND 128", name="ref_bounded"),
        CheckConstraint("octet_length(title) BETWEEN 1 AND 4096", name="title_bounded"),
        CheckConstraint(_CLASSIFICATION_CHECK, name="classification_valid"),
        UniqueConstraint("tenant_id", "project_id", "kind", "ref", name="uq_intake_artifacts_ref"),
        # FK target for the self/provenance triple-FKs.
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_intake_artifacts_id_project_tenant"
        ),
        Index("ix_intake_artifacts_tenant_project", "tenant_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ref: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
