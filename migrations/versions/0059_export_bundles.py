"""signed offline auditor bundle store

Revision ID: 0059
Revises: 0058
Create Date: 2026-08-23

Slice 60 — tenant-owned Ed25519-signed export bundle. Purely additive. Does not
alter evidence_packs, A5, readiness, or go-live. Does not add uq_ep_id_project_tenant.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.release.export_bundle_db_checks import (
    FILE_CHECK_CONSTRAINTS,
    RECORD_CHECK_CONSTRAINTS,
    SIGNATURE_CHECK_CONSTRAINTS,
)
from app.release.export_bundle_ddl import (
    drop_export_bundle_guards,
    install_export_bundle_guards,
    populated_downgrade_sql,
)

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_pack_export_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("release_verdict_id", sa.UUID(), nullable=False),
        sa.Column("audit_checkpoint_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("bundle_contract_version", sa.Text(), nullable=False),
        sa.Column("manifest_digest", sa.Text(), nullable=False),
        sa.Column("redaction_policy_version", sa.Text(), nullable=False),
        sa.Column("redaction_policy_digest", sa.Text(), nullable=False),
        sa.Column("core_content_hash", sa.Text(), nullable=False),
        sa.Column("immutable_log_reference", sa.Text(), nullable=False),
        sa.Column("signing_key_id", sa.Text(), nullable=False),
        sa.Column("auditor_access_mode", sa.Text(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("total_byte_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in RECORD_CHECK_CONSTRAINTS],
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_epr_id_project_tenant"),
        sa.UniqueConstraint(
            "tenant_id",
            "evidence_pack_id",
            "idempotency_key",
            name="uq_epr_idempotency",
        ),
    )
    op.create_index(
        "ix_epr_latest",
        "evidence_pack_export_records",
        ["tenant_id", "evidence_pack_id", "created_at"],
    )
    op.create_table(
        "evidence_pack_export_files",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("export_record_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in FILE_CHECK_CONSTRAINTS],
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["export_record_id", "project_id", "tenant_id"],
            [
                "evidence_pack_export_records.id",
                "evidence_pack_export_records.project_id",
                "evidence_pack_export_records.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("export_record_id", "ordinal", name="uq_epef_ordinal"),
        sa.UniqueConstraint("export_record_id", "file_name", name="uq_epef_file_name"),
    )
    op.create_table(
        "evidence_pack_manifest_signatures",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("export_record_id", sa.UUID(), nullable=False),
        sa.Column("signature_algorithm", sa.Text(), nullable=False),
        sa.Column("signing_key_id", sa.Text(), nullable=False),
        sa.Column("signature_b64", sa.Text(), nullable=False),
        sa.Column("signed_bytes_digest", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        *[sa.CheckConstraint(sql, name=name) for name, sql in SIGNATURE_CHECK_CONSTRAINTS],
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["export_record_id", "project_id", "tenant_id"],
            [
                "evidence_pack_export_records.id",
                "evidence_pack_export_records.project_id",
                "evidence_pack_export_records.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("export_record_id", name="uq_epms_export_record"),
    )
    install_export_bundle_guards()


def downgrade() -> None:
    op.execute(populated_downgrade_sql())
    drop_export_bundle_guards()
    op.drop_table("evidence_pack_manifest_signatures")
    op.drop_table("evidence_pack_export_files")
    op.drop_index("ix_epr_latest", table_name="evidence_pack_export_records")
    op.drop_table("evidence_pack_export_records")
