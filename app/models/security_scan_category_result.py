"""Immutable per-category Slice-44 security-scan observations."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SecurityScanCategoryResult(Base):
    __tablename__ = "security_scan_category_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["security_scan_run_id", "project_id", "tenant_id"],
            [
                "security_scan_runs.id",
                "security_scan_runs.project_id",
                "security_scan_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint(
            "category IN ('authz','injection','secrets_exposure','unsafe_tool','supply_chain')",
            name="category",
        ),
        CheckConstraint(
            "coverage_status IN "
            "('completed_clean','completed_with_findings','failed','unsupported')",
            name="coverage_status",
        ),
        CheckConstraint("rule_pack_hash ~ '^sha256:[0-9a-f]{64}$'", name="rule_hash"),
        CheckConstraint("evidence_digest ~ '^sha256:[0-9a-f]{64}$'", name="evidence_digest"),
        CheckConstraint(
            "octet_length(scanner_key) BETWEEN 1 AND 128 AND btrim(scanner_key) <> '' "
            "AND octet_length(scanner_version) BETWEEN 1 AND 128 "
            "AND btrim(scanner_version) <> ''",
            name="scanner_bounds",
        ),
        CheckConstraint(
            "reported_finding_count BETWEEN 0 AND 1000 AND "
            "((coverage_status = 'completed_clean' AND reported_finding_count = 0) OR "
            "(coverage_status = 'completed_with_findings' AND reported_finding_count > 0) OR "
            "(coverage_status IN ('failed','unsupported') AND reported_finding_count = 0))",
            name="finding_shape",
        ),
        CheckConstraint(
            "(category='authz' AND scanner_key='uaid.authz_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:7a7b60f9e5195353abef1603b2480a163fbd98c03293b95f71e49d4852bb1706') OR "
            "(category='injection' AND scanner_key='uaid.injection_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:9314613dc0b93d99fbe5bb70ea3155c7f5d07215b709983b88d9abeb64902b12') OR "
            "(category='secrets_exposure' AND scanner_key='uaid.secrets_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:688d0e8a5e7e58bda15f39195d09dba7282f24db356f73216adcbe43c465d470') OR "
            "(category='unsafe_tool' AND scanner_key='uaid.unsafe_tool_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:5750f7fdadcb7a4df52d391aa4d3d7441f48b54405fb97940a79fd9a7ff209aa') OR "
            "(category='supply_chain' AND scanner_key='uaid.supply_chain_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:7e5b8969bdd62d07a10c3fa79329ca4bda4dceb57162a297ae234f8406b6c10f')",
            name="scanner_contract",
        ),
        UniqueConstraint("security_scan_run_id", "category", name="uq_sscr_run_category"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", "category", name="uq_sscr_attachment_target"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    security_scan_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    scanner_key: Mapped[str] = mapped_column(Text, nullable=False)
    scanner_version: Mapped[str] = mapped_column(Text, nullable=False)
    rule_pack_hash: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_status: Mapped[str] = mapped_column(Text, nullable=False)
    reported_finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
