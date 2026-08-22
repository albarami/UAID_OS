"""Tenant-owned Slice-57 incident workflow ledger. Not production IR."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.ops.incident_db_checks import CHILD_CHECK_CONSTRAINTS
from app.ops.incidents import (
    ACTION_COUNT,
    CATEGORIES,
    DIGEST_RE,
    EXECUTION_POSTURES,
    HANDOVER_STATUSES,
    POLICY_DECISIONS,
    PROVENANCES,
    REASON_CODES,
    RULESET_VERSION,
    SEVERITIES,
    STATUSES,
    TICKET_DELIVERIES,
    TICKET_KINDS,
)

_IN_CAT = ", ".join(repr(item) for item in CATEGORIES)
_IN_SEV = ", ".join(repr(item) for item in SEVERITIES)
_IN_STATUS = ", ".join(repr(item) for item in STATUSES)
_IN_REASON = ", ".join(repr(item) for item in REASON_CODES)
_IN_DEC = ", ".join(repr(item) for item in POLICY_DECISIONS)
_IN_POST = ", ".join(repr(item) for item in EXECUTION_POSTURES)


class OpsIncident(Base):
    """One caller-opened incident. Not a pager event or risk-acceptance."""

    __tablename__ = "ops_incidents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["source_signal_id", "project_id", "tenant_id"],
            [
                "ops_signal_results.id",
                "ops_signal_results.project_id",
                "ops_signal_results.tenant_id",
            ],
            ondelete="RESTRICT",
            name="source_signal_project_tenant",
        ),
        CheckConstraint(f"ruleset_version='{RULESET_VERSION}'", name="ruleset_version"),
        CheckConstraint(f"category IN ({_IN_CAT})", name="category"),
        CheckConstraint(f"severity IN ({_IN_SEV})", name="severity"),
        CheckConstraint(f"status IN ({_IN_STATUS})", name="status"),
        CheckConstraint("source_provenance='caller_supplied_unverified'", name="source_provenance"),
        CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 2000 AND summary = btrim(summary)",
            name="summary",
        ),
        CheckConstraint(
            "detail IS NULL OR (char_length(detail) BETWEEN 1 AND 8000 AND detail = btrim(detail))",
            name="detail",
        ),
        CheckConstraint(
            "(category<>'other') OR (detail IS NOT NULL)",
            name="other_requires_detail",
        ),
        CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        CheckConstraint(f"request_digest ~ '{DIGEST_RE}'", name="request_digest"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_incidents_id_project_tenant"
        ),
        UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key", name="uq_ops_incidents_idempotency"
        ),
        Index("ix_ops_incidents_latest", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    source_signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsIncidentEvent(Base):
    """Append-only incident lifecycle event. Safe metadata in audit, not here."""

    __tablename__ = "ops_incident_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "project_id", "tenant_id"],
            ["ops_incidents.id", "ops_incidents.project_id", "ops_incidents.tenant_id"],
            ondelete="RESTRICT",
            name="incident_project_tenant",
        ),
        CheckConstraint(
            "char_length(event_type) BETWEEN 1 AND 64 AND event_type = btrim(event_type)",
            name="event_type",
        ),
        CheckConstraint(
            "char_length(actor) BETWEEN 1 AND 200 AND actor = btrim(actor)",
            name="actor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsIncidentTicket(Base):
    """Local bug ticket. Not a Jira create."""

    __tablename__ = "ops_incident_tickets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "project_id", "tenant_id"],
            ["ops_incidents.id", "ops_incidents.project_id", "ops_incidents.tenant_id"],
            ondelete="RESTRICT",
            name="incident_project_tenant",
        ),
        ForeignKeyConstraint(
            ["pm_issue_mapping_id", "project_id", "tenant_id"],
            [
                "pm_issue_mappings.id",
                "pm_issue_mappings.project_id",
                "pm_issue_mappings.tenant_id",
            ],
            ondelete="RESTRICT",
            name="mapping_project_tenant",
        ),
        CheckConstraint(
            "ticket_kind IN (" + ", ".join(repr(item) for item in TICKET_KINDS) + ")",
            name="ticket_kind",
        ),
        CheckConstraint(
            "delivery IN (" + ", ".join(repr(item) for item in TICKET_DELIVERIES) + ")",
            name="delivery",
        ),
        CheckConstraint("status='open'", name="status"),
        UniqueConstraint("tenant_id", "incident_id", name="uq_ops_incident_tickets_incident"),
        UniqueConstraint(
            "id",
            "incident_id",
            "project_id",
            "tenant_id",
            name="uq_ops_incident_tickets_id_incident_project_tenant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ticket_kind: Mapped[str] = mapped_column(Text, nullable=False)
    delivery: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    pm_issue_mapping_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsSupportHandover(Base):
    """Presence-only support handover. Not Slice 59 closure."""

    __tablename__ = "ops_support_handovers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(repr(item) for item in HANDOVER_STATUSES) + ")",
            name="status",
        ),
        CheckConstraint(
            "recorded_by_provenance IN (" + ", ".join(repr(item) for item in PROVENANCES) + ")",
            name="recorded_by_provenance",
        ),
        CheckConstraint(
            "char_length(handed_over_by) BETWEEN 1 AND 200 "
            "AND handed_over_by = btrim(handed_over_by)",
            name="handed_over_by",
        ),
        CheckConstraint(
            "char_length(received_by) BETWEEN 1 AND 200 AND received_by = btrim(received_by)",
            name="received_by",
        ),
        Index("ix_ops_support_handovers_latest", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    handed_over_by: Mapped[str] = mapped_column(Text, nullable=False)
    received_by: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsIncidentActionEvaluation(Base):
    """One seven-row §25.2 prescription snapshot."""

    __tablename__ = "ops_incident_action_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["incident_id", "project_id", "tenant_id"],
            ["ops_incidents.id", "ops_incidents.project_id", "ops_incidents.tenant_id"],
            ondelete="RESTRICT",
            name="incident_project_tenant",
        ),
        ForeignKeyConstraint(
            ["policy_id", "project_id", "tenant_id"],
            [
                "autonomy_policies.id",
                "autonomy_policies.project_id",
                "autonomy_policies.tenant_id",
            ],
            ondelete="RESTRICT",
            name="policy_project_tenant",
        ),
        CheckConstraint(f"ruleset_version='{RULESET_VERSION}'", name="ruleset_version"),
        CheckConstraint(f"action_count={ACTION_COUNT}", name="action_count"),
        CheckConstraint(f"policy_input_digest ~ '{DIGEST_RE}'", name="policy_input_digest"),
        CheckConstraint(
            "(policy_present IS TRUE AND policy_id IS NOT NULL "
            "AND autonomy_level_snapshot BETWEEN 0 AND 5) OR "
            "(policy_present IS FALSE AND policy_id IS NULL "
            "AND autonomy_level_snapshot IS NULL)",
            name="policy_presence",
        ),
        UniqueConstraint(
            "id",
            "incident_id",
            "project_id",
            "tenant_id",
            name="uq_ops_incident_action_evaluations_id_incident_project_tenant",
        ),
        Index(
            "ix_ops_incident_action_evaluations_latest",
            "tenant_id",
            "incident_id",
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
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    action_count: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    autonomy_level_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsIncidentActionResult(Base):
    """One frozen §25.2 action row. Not an actuator."""

    __tablename__ = "ops_incident_action_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evaluation_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_incident_action_evaluations.id",
                "ops_incident_action_evaluations.incident_id",
                "ops_incident_action_evaluations.project_id",
                "ops_incident_action_evaluations.tenant_id",
            ],
            ondelete="RESTRICT",
            name="evaluation_incident_project_tenant",
        ),
        ForeignKeyConstraint(
            ["ticket_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_incident_tickets.id",
                "ops_incident_tickets.incident_id",
                "ops_incident_tickets.project_id",
                "ops_incident_tickets.tenant_id",
            ],
            ondelete="RESTRICT",
            name="ticket_incident_project_tenant",
        ),
        CheckConstraint(f"policy_decision IN ({_IN_DEC})", name="policy_decision"),
        CheckConstraint(f"execution_posture IN ({_IN_POST})", name="execution_posture"),
        CheckConstraint(f"reason_code IN ({_IN_REASON})", name="reason_code"),
        *[CheckConstraint(sql, name=name) for name, sql in CHILD_CHECK_CONSTRAINTS],
        UniqueConstraint("evaluation_id", "seq", name="uq_ops_incident_action_results_eval_seq"),
        UniqueConstraint(
            "evaluation_id", "action", name="uq_ops_incident_action_results_eval_action"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    matrix_action: Mapped[str] = mapped_column(Text, nullable=False)
    policy_decision: Mapped[str] = mapped_column(Text, nullable=False)
    execution_posture: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
