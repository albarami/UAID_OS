"""Tenant-owned skill-matching ORM models (Slice 38) — `squad_manifests` + `skill_matches`.

Both are RLS, append-only (SELECT/INSERT only; migration `0037` block triggers are the authoritative
backstop). `skill_matches` persists the full §8.3 per-component score breakdown (B2). The global vocab
tables (`skills`/`agent_skill_capabilities`/`agent_provided_skills`) are admin-curated and accessed via raw
SQL in `app.repositories.skills` (uaid_app SELECT-only — B8), so they need no runtime ORM model here.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SquadManifestRecord(Base):
    __tablename__ = "squad_manifests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    work_unit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_skill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    built_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class SkillMatch(Base):
    __tablename__ = "skill_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    manifest_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    work_unit_ref: Mapped[str] = mapped_column(Text, nullable=False)
    blueprint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    capability_match: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    domain_fit: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    tool_access_fit: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    eval_performance: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    reviewer_availability: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    cost_latency_fit: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    risk_penalty: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    eval_source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
