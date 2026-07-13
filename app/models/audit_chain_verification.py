"""Restricted global audit-chain checkpoints for Slice 49 evidence packs."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditChainVerification(Base):
    __tablename__ = "audit_chain_verifications"
    __table_args__ = (
        CheckConstraint(
            "verifier_contract_version='slice49.evidence_audit.v1'",
            name="contract_version",
        ),
        CheckConstraint(
            "verifier_contract_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="contract_hash",
        ),
        CheckConstraint(
            "(verification_ok AND first_bad_seq IS NULL "
            "AND verified_through_seq IS NOT NULL AND verified_through_seq>0 "
            "AND verified_through_entry_hash ~ '^[0-9a-f]{64}$') OR "
            "(NOT verification_ok AND first_bad_seq IS NOT NULL "
            "AND verified_through_seq IS NULL AND verified_through_entry_hash IS NULL)",
            name="result_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    verifier_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    verifier_contract_hash: Mapped[str] = mapped_column(Text, nullable=False)
    verification_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_bad_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verified_through_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verified_through_entry_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
