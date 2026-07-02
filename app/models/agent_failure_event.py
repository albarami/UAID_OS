"""``agent_failure_events`` — tenant-owned, append-only REPORTED §9.6 failure events (Slice 41).

Each row is a **REPORTED** failure-pattern classification against a same-tenant agent instance —
caller-supplied and **unverified** (B1/B2: required ``source`` origin label + ``source_provenance``
CHECK-locked to ``caller_supplied_unverified`` this slice; no diagnosis/classifier exists). The
composite FK ``(instance_id, project_id, tenant_id) → agent_instances`` pins the event to the
instance's own project+tenant. Every user text field is bounded AND non-blank — a
``char_length`` cap plus a blank-after-``btrim`` refusal over the ``str.strip()`` whitespace
set (B3; whitespace-only provenance/text is rejected at the DB too, review round 1).
Append-only: SELECT/INSERT only (migration ``0040`` block triggers + grants are the authoritative
backstop) — the events are the audit trail for the compute-on-read replacement decision (OD-3).
``summary``/``detail`` may carry source-derived material (audit/logs never carry them; no
no-secret guarantee). A failure event never executes, suspends, or authorizes anything (OD-1).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
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

from app.agents.failure_policy import (
    FAILURE_PATTERNS,
    MAX_DETAIL,
    MAX_EVIDENCE_REF,
    MAX_REPORTED_BY,
    MAX_SOURCE,
    MAX_SUMMARY,
    SEVERITIES,
    SOURCE_PROVENANCES,
)
from app.models.base import Base

_FP = ", ".join(repr(p) for p in FAILURE_PATTERNS)
_SEV = ", ".join(repr(s) for s in SEVERITIES)
_PROV = ", ".join(repr(p) for p in SOURCE_PROVENANCES)

# The Python str.strip() whitespace set as a Postgres E-literal (mirrors migration 0040):
# the DB non-blank backstop is exactly as strong as the pure validator's .strip() gate.
_TRIM = r"E' \t\n\r\x0b\x0c'"


def _bounded_required(column: str, cap: int) -> str:
    return f"char_length({column}) BETWEEN 1 AND {cap} AND btrim({column}, {_TRIM}) <> ''"


def _bounded_optional(column: str, cap: int) -> str:
    return f"{column} IS NULL OR ({_bounded_required(column, cap)})"


class AgentFailureEvent(Base):
    __tablename__ = "agent_failure_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            ondelete="RESTRICT",
            name="instance_project_tenant",
        ),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(f"failure_pattern IN ({_FP})", name="failure_pattern_valid"),
        CheckConstraint(f"severity IN ({_SEV})", name="severity_valid"),
        # B1 — only the unverified tier is writable this slice (future verified tiers extend it).
        CheckConstraint(f"source_provenance IN ({_PROV})", name="source_provenance_valid"),
        # B3 — DB backstops for the pure-validator bounds: char_length cap AND
        # non-blank-after-trim (whitespace-only refused; NULL passes on optional fields).
        CheckConstraint(_bounded_required("source", MAX_SOURCE), name="source_len"),
        CheckConstraint(
            _bounded_optional("evidence_ref", MAX_EVIDENCE_REF), name="evidence_ref_len"
        ),
        CheckConstraint(_bounded_optional("summary", MAX_SUMMARY), name="summary_len"),
        CheckConstraint(_bounded_optional("detail", MAX_DETAIL), name="detail_len"),
        CheckConstraint(_bounded_required("reported_by", MAX_REPORTED_BY), name="reported_by_len"),
        Index("ix_agent_failure_events_instance", "tenant_id", "instance_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    failure_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
