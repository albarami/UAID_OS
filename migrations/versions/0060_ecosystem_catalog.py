"""ecosystem catalog listing mechanism

Revision ID: 0060
Revises: 0059
Create Date: 2026-08-23

Slice 61a — global append-only catalog listing mechanism. Purely additive.
Registers nothing. Does not alter A5, readiness, go-live, or any pre-existing
object. Identity is the row; connector children freeze at first vetting.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.ecosystem.catalog_db_checks import (
    ADOPTION_CHECK_CONSTRAINTS,
    ASSET_CHECK_CONSTRAINTS,
    LISTING_CHECK_CONSTRAINTS,
    RESULT_CHECK_CONSTRAINTS,
    SCOPE_CHECK_CONSTRAINTS,
    SPEC_CHECK_CONSTRAINTS,
    VETTING_CHECK_CONSTRAINTS,
)
from app.ecosystem.catalog_ddl import (
    drop_catalog_guards,
    install_catalog_guards,
    populated_downgrade_sql,
)

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_assets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_kind", sa.Text(), nullable=False),
        sa.Column("asset_key", sa.Text(), nullable=False),
        sa.Column("version_label", sa.Text(), nullable=False),
        sa.Column("registered_by", sa.Text(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("domain_label", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_kind", "asset_key", "version_label", name="uq_ca_kind_key_version"
        ),
        sa.UniqueConstraint("id", "asset_kind", name="uq_ca_id_kind"),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"),
        *[sa.CheckConstraint(sql, name=name) for name, sql in ASSET_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "connector_catalog_specs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("asset_kind", sa.Text(), nullable=False),
        sa.Column("protocol_module", sa.Text(), nullable=False),
        sa.Column("protocol_name", sa.Text(), nullable=False),
        sa.Column("fake_name", sa.Text(), nullable=False),
        sa.Column("service_module", sa.Text(), nullable=False),
        sa.Column("live_adapter_status", sa.Text(), nullable=False),
        sa.Column("live_adapter_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_ccs_asset_id"),
        sa.ForeignKeyConstraint(
            ["asset_id", "asset_kind"],
            ["catalog_assets.id", "catalog_assets.asset_kind"],
            ondelete="RESTRICT",
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in SPEC_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "connector_catalog_tool_scope",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("asset_kind", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "tool_name", name="uq_ccts_asset_tool"),
        sa.ForeignKeyConstraint(
            ["asset_id", "asset_kind"],
            ["catalog_assets.id", "catalog_assets.asset_kind"],
            ondelete="RESTRICT",
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in SCOPE_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "catalog_vetting_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("vetting_kind", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "asset_id", name="uq_cvr_id_asset"),
        sa.ForeignKeyConstraint(["asset_id"], ["catalog_assets.id"], ondelete="RESTRICT"),
        *[sa.CheckConstraint(sql, name=name) for name, sql in VETTING_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "catalog_vetting_check_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("vetting_record_id", sa.UUID(), nullable=False),
        sa.Column("check_name", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vetting_record_id", "check_name", name="uq_cvcr_record_name"),
        sa.ForeignKeyConstraint(
            ["vetting_record_id"], ["catalog_vetting_records.id"], ondelete="RESTRICT"
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in RESULT_CHECK_CONSTRAINTS],
    )
    op.create_table(
        "catalog_listings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("vetting_record_id", sa.UUID(), nullable=False),
        sa.Column("listing_state", sa.Text(), nullable=False),
        sa.Column("listed_by", sa.Text(), nullable=False),
        sa.Column("delisted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delisted_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "asset_id", name="uq_cl_id_asset"),
        sa.ForeignKeyConstraint(["asset_id"], ["catalog_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["vetting_record_id", "asset_id"],
            ["catalog_vetting_records.id", "catalog_vetting_records.asset_id"],
            ondelete="RESTRICT",
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in LISTING_CHECK_CONSTRAINTS],
    )
    op.create_index(
        "uq_cl_live_asset",
        "catalog_listings",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("listing_state = 'listed'"),
    )
    op.create_table(
        "tenant_catalog_adoptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("adopted_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "listing_id", name="uq_tca_tenant_project_listing"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id", "asset_id"],
            ["catalog_listings.id", "catalog_listings.asset_id"],
            ondelete="RESTRICT",
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in ADOPTION_CHECK_CONSTRAINTS],
    )
    install_catalog_guards()


def downgrade() -> None:
    op.execute(populated_downgrade_sql())
    drop_catalog_guards()
    op.drop_table("tenant_catalog_adoptions")
    op.drop_index("uq_cl_live_asset", table_name="catalog_listings")
    op.drop_table("catalog_listings")
    op.drop_table("catalog_vetting_check_results")
    op.drop_table("catalog_vetting_records")
    op.drop_table("connector_catalog_tool_scope")
    op.drop_table("connector_catalog_specs")
    op.drop_table("catalog_assets")
