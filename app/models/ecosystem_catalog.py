"""Slice-61a ecosystem catalog ORM. Identity is the row. Append-only except listing delist."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ecosystem.catalog_db_checks import (
    ADOPTION_CHECK_CONSTRAINTS,
    ASSET_CHECK_CONSTRAINTS,
    LISTING_CHECK_CONSTRAINTS,
    RESULT_CHECK_CONSTRAINTS,
    SCOPE_CHECK_CONSTRAINTS,
    SPEC_CHECK_CONSTRAINTS,
    VETTING_CHECK_CONSTRAINTS,
)
from app.models.base import Base


class CatalogAsset(Base):
    """Global catalog identity row. Kind-specific tails are iff-NULLable."""

    __tablename__ = "catalog_assets"
    __table_args__ = (
        UniqueConstraint("asset_kind", "asset_key", "version_label", name="uq_ca_kind_key_version"),
        UniqueConstraint("id", "asset_kind", name="uq_ca_id_kind"),
        ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"),
        *[CheckConstraint(sql, name=name) for name, sql in ASSET_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_kind: Mapped[str] = mapped_column(Text, nullable=False)
    asset_key: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    registered_by: Mapped[str] = mapped_column(Text, nullable=False)
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    domain_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ConnectorCatalogSpec(Base):
    """One declared connector spec, pinned to a connector asset."""

    __tablename__ = "connector_catalog_specs"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_ccs_asset_id"),
        ForeignKeyConstraint(
            ["asset_id", "asset_kind"],
            ["catalog_assets.id", "catalog_assets.asset_kind"],
            ondelete="RESTRICT",
        ),
        *[CheckConstraint(sql, name=name) for name, sql in SPEC_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_kind: Mapped[str] = mapped_column(Text, nullable=False)
    protocol_module: Mapped[str] = mapped_column(Text, nullable=False)
    protocol_name: Mapped[str] = mapped_column(Text, nullable=False)
    fake_name: Mapped[str] = mapped_column(Text, nullable=False)
    service_module: Mapped[str] = mapped_column(Text, nullable=False)
    live_adapter_status: Mapped[str] = mapped_column(Text, nullable=False)
    live_adapter_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ConnectorCatalogToolScope(Base):
    """One declared tool name for a connector asset."""

    __tablename__ = "connector_catalog_tool_scope"
    __table_args__ = (
        UniqueConstraint("asset_id", "tool_name", name="uq_ccts_asset_tool"),
        ForeignKeyConstraint(
            ["asset_id", "asset_kind"],
            ["catalog_assets.id", "catalog_assets.asset_kind"],
            ondelete="RESTRICT",
        ),
        *[CheckConstraint(sql, name=name) for name, sql in SCOPE_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_kind: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CatalogVettingRecord(Base):
    """Admin-path vetting record. Provenance is app-stamped."""

    __tablename__ = "catalog_vetting_records"
    __table_args__ = (
        UniqueConstraint("id", "asset_id", name="uq_cvr_id_asset"),
        ForeignKeyConstraint(["asset_id"], ["catalog_assets.id"], ondelete="RESTRICT"),
        *[CheckConstraint(sql, name=name) for name, sql in VETTING_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vetting_kind: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CatalogVettingCheckResult(Base):
    """One typed checker result. UNIQUE(vetting_record_id, check_name)."""

    __tablename__ = "catalog_vetting_check_results"
    __table_args__ = (
        UniqueConstraint("vetting_record_id", "check_name", name="uq_cvcr_record_name"),
        ForeignKeyConstraint(
            ["vetting_record_id"], ["catalog_vetting_records.id"], ondelete="RESTRICT"
        ),
        *[CheckConstraint(sql, name=name) for name, sql in RESULT_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    vetting_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    check_name: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CatalogListing(Base):
    """Global listing. One-way listed → delisted. DELETE/TRUNCATE blocked."""

    __tablename__ = "catalog_listings"
    __table_args__ = (
        UniqueConstraint("id", "asset_id", name="uq_cl_id_asset"),
        ForeignKeyConstraint(["asset_id"], ["catalog_assets.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["vetting_record_id", "asset_id"],
            ["catalog_vetting_records.id", "catalog_vetting_records.asset_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_cl_live_asset",
            "asset_id",
            unique=True,
            postgresql_where=text("listing_state = 'listed'"),
        ),
        *[CheckConstraint(sql, name=name) for name, sql in LISTING_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vetting_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    listing_state: Mapped[str] = mapped_column(Text, nullable=False)
    listed_by: Mapped[str] = mapped_column(Text, nullable=False)
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delisted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class TenantCatalogAdoption(Base):
    """Tenant-owned adoption record. Not a grant."""

    __tablename__ = "tenant_catalog_adoptions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_id", "listing_id", name="uq_tca_tenant_project_listing"
        ),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["listing_id", "asset_id"],
            ["catalog_listings.id", "catalog_listings.asset_id"],
            ondelete="RESTRICT",
        ),
        *[CheckConstraint(sql, name=name) for name, sql in ADOPTION_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    adopted_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
