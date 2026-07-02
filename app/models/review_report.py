"""``review_reports`` — tenant-owned, append-only §13.3 reviewer verdicts (Slice 42).

Each row is a **REPORTED** verdict — content ``caller_supplied_unverified`` (the Slice-41
provenance model; reviewer QA = S48) — but the reporter's **registration is FK-proven**:
the composite FK ``(task_contract_id, reviewer_instance_id, layer, project_id, tenant_id)``
→ ``task_contract_reviewers`` makes a report from an unregistered reviewer or wrong layer
impossible. **``can_merge`` is DB-GENERATED from the verdict** (``GENERATED ALWAYS AS
(verdict = 'approved') STORED`` — never caller-writable, V2-B2; the Slice-40 mechanism).
Shape CHECKs: ``approved`` ⇒ all three finding lists empty (a suspected shortcut is not an
approval, §2.1/§13.4); ``rejected_with_required_changes`` ⇒ failed_criteria + required_changes
non-empty (spec:1279-1295). Recordable only while the contract is reportable (migration
``0041`` window guard); immutable append-only. A verdict never proves quality/acceptance/
oracle-pass (S43/S45/S46/S48).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.task_contract import _bounded_required
from app.review.task_contracts import REVIEW_LAYERS
from app.review.workflow import MAX_REPORT_SOURCE, MAX_SUMMARY, SOURCE_PROVENANCES, VERDICTS

_VERDICTS = ", ".join(repr(v) for v in VERDICTS)
_LAYERS = ", ".join(repr(la) for la in REVIEW_LAYERS)
_PROV = ", ".join(repr(p) for p in SOURCE_PROVENANCES)


class ReviewReport(Base):
    __tablename__ = "review_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            ondelete="RESTRICT",
            name="contract_project_tenant",
        ),
        # The registration binding (D-42-4): a report is FK-impossible unless the exact
        # (contract, reviewer, layer) registration exists — the Slice-40 exact-subject lesson.
        ForeignKeyConstraint(
            ["task_contract_id", "reviewer_instance_id", "layer", "project_id", "tenant_id"],
            [
                "task_contract_reviewers.task_contract_id",
                "task_contract_reviewers.reviewer_instance_id",
                "task_contract_reviewers.layer",
                "task_contract_reviewers.project_id",
                "task_contract_reviewers.tenant_id",
            ],
            ondelete="RESTRICT",
            name="registration",
        ),
        CheckConstraint(f"verdict IN ({_VERDICTS})", name="verdict_valid"),
        CheckConstraint(f"layer IN ({_LAYERS})", name="layer_valid"),
        CheckConstraint(f"source_provenance IN ({_PROV})", name="source_provenance_valid"),
        CheckConstraint(
            "verdict <> 'approved' OR (jsonb_array_length(failed_criteria) = 0 "
            "AND jsonb_array_length(suspected_shortcuts) = 0 "
            "AND jsonb_array_length(required_changes) = 0)",
            name="approved_lists_empty",
        ),
        CheckConstraint(
            "verdict <> 'rejected_with_required_changes' OR "
            "(jsonb_array_length(failed_criteria) >= 1 "
            "AND jsonb_array_length(required_changes) >= 1)",
            name="rejected_lists_required",
        ),
        CheckConstraint(_bounded_required("summary", MAX_SUMMARY), name="summary_len"),
        CheckConstraint(_bounded_required("source", MAX_REPORT_SOURCE), name="source_len"),
        Index(
            "ix_review_reports_contract_layer",
            "tenant_id",
            "task_contract_id",
            "layer",
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
    task_contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    layer: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    # V2-B2 — GENERATED from the verdict; not writable by any caller (the §13.3 read shape).
    can_merge: Mapped[bool] = mapped_column(
        Boolean, Computed("verdict = 'approved'", persisted=True), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    failed_criteria: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    suspected_shortcuts: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    required_changes: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
