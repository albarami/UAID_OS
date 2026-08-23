"""Tenant-owned Slice-59 stabilization-window assessment store. Non-closing."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.ops.stabilization import (
    ASSESSOR_PROVENANCES,
    CLOCK_BASIS,
    CLOSURE_RESULTS,
    CRITERION_COUNT,
    CRITERION_STATUSES,
    DIGEST_RE,
    FOLLOW_UP_POSTURES,
    IMPROVEMENT_COUNT,
    IMPROVEMENT_STATUSES,
    REFRESH_POSTURE,
    RULESET_VERSION,
    WINDOW_STATUS,
)
from app.ops.stabilization_db_checks import (
    ASSESSOR_SHAPE_SQL,
    CRITERION_CHECK_CONSTRAINTS,
    IMPROVEMENT_CHECK_CONSTRAINTS,
    WINDOW_COUNTER_SQL,
)

_IN_STATUS = ", ".join(repr(item) for item in CRITERION_STATUSES)
_IN_IMP_STATUS = ", ".join(repr(item) for item in IMPROVEMENT_STATUSES)
_IN_FOLLOW = ", ".join(repr(item) for item in FOLLOW_UP_POSTURES)
_IN_PROV = ", ".join(repr(item) for item in ASSESSOR_PROVENANCES)
_IN_CLOSURE = ", ".join(repr(item) for item in CLOSURE_RESULTS)


class OpsStabilizationWindow(Base):
    """One stabilization-window assessment. Status is ``open`` only."""

    __tablename__ = "ops_stabilization_windows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["category_id", "project_id", "tenant_id"],
            [
                "intake_categories.id",
                "intake_categories.project_id",
                "intake_categories.tenant_id",
            ],
            ondelete="RESTRICT",
            name="category_project_tenant",
        ),
        ForeignKeyConstraint(
            ["extends_window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
            name="extends_window_project_tenant",
        ),
        CheckConstraint(f"ruleset_version='{RULESET_VERSION}'", name="ruleset_version"),
        CheckConstraint(f"status='{WINDOW_STATUS}'", name="status"),
        CheckConstraint(f"clock_basis='{CLOCK_BASIS}'", name="clock_basis"),
        CheckConstraint(f"criterion_count={CRITERION_COUNT}", name="criterion_count"),
        CheckConstraint(f"improvement_count={IMPROVEMENT_COUNT}", name="improvement_count"),
        CheckConstraint(WINDOW_COUNTER_SQL, name="status_counters"),
        CheckConstraint("extension_required IS TRUE", name="extension_required"),
        CheckConstraint(f"follow_up_posture IN ({_IN_FOLLOW})", name="follow_up_posture"),
        CheckConstraint(f"assessor_provenance IN ({_IN_PROV})", name="assessor_provenance"),
        CheckConstraint(ASSESSOR_SHAPE_SQL, name="assessor_shape"),
        CheckConstraint(
            "char_length(assessor_subject) BETWEEN 1 AND 200 "
            "AND assessor_subject = btrim(assessor_subject)",
            name="assessor_subject",
        ),
        CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        CheckConstraint(f"policy_digest ~ '{DIGEST_RE}'", name="policy_digest"),
        CheckConstraint(f"request_digest ~ '{DIGEST_RE}'", name="request_digest"),
        CheckConstraint(f"input_digest ~ '{DIGEST_RE}'", name="input_digest"),
        CheckConstraint(
            "monitoring_max_age_hours BETWEEN 1 AND 168 "
            "AND deployment_max_age_hours BETWEEN 1 AND 168",
            name="age_hours",
        ),
        CheckConstraint(
            "monitoring_target_ref IS NULL OR ("
            "char_length(monitoring_target_ref) BETWEEN 1 AND 2048 "
            "AND monitoring_target_ref = btrim(monitoring_target_ref))",
            name="monitoring_target_ref",
        ),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_stab_windows_id_project_tenant"
        ),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "idempotency_key",
            name="uq_ops_stab_windows_idempotency",
        ),
        Index("ix_ops_stab_windows_latest", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clock_basis: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    policy_digest: Mapped[str] = mapped_column(Text, nullable=False)
    monitoring_target_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitoring_max_age_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    deployment_max_age_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    assessor_subject: Mapped[str] = mapped_column(Text, nullable=False)
    assessor_actor_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessor_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_posture: Mapped[str] = mapped_column(Text, nullable=False)
    extension_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    extends_window_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    criterion_count: Mapped[int] = mapped_column(Integer, nullable=False)
    improvement_count: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    not_observed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    not_evaluable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    request_digest: Mapped[str] = mapped_column(Text, nullable=False)
    input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsStabilizationCriterionResult(Base):
    """One seq 1–8 criterion child. Seq 5 is the only passable row."""

    __tablename__ = "ops_stabilization_criterion_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
            name="window_project_tenant",
        ),
        ForeignKeyConstraint(
            ["monitoring_snapshot_id", "project_id", "tenant_id"],
            [
                "monitoring_status_snapshots.id",
                "monitoring_status_snapshots.project_id",
                "monitoring_status_snapshots.tenant_id",
            ],
            ondelete="RESTRICT",
            name="monitoring_project_tenant",
        ),
        ForeignKeyConstraint(
            ["rollback_verification_run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="rollback_project_tenant",
        ),
        ForeignKeyConstraint(
            ["handover_id", "project_id", "tenant_id"],
            [
                "ops_support_handovers.id",
                "ops_support_handovers.project_id",
                "ops_support_handovers.tenant_id",
            ],
            ondelete="RESTRICT",
            name="handover_project_tenant",
        ),
        CheckConstraint(f"status IN ({_IN_STATUS})", name="status"),
        *[CheckConstraint(sql, name=name) for name, sql in CRITERION_CHECK_CONSTRAINTS],
        UniqueConstraint("tenant_id", "window_id", "seq", name="uq_ops_stab_criteria_window_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    window_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    criterion_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    monitoring_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    rollback_verification_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    handover_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsImprovementResult(Base):
    """One seq 1–8 improvement inventory child. Descriptive only."""

    __tablename__ = "ops_improvement_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
            name="window_project_tenant",
        ),
        ForeignKeyConstraint(
            ["findings_report_id", "project_id", "tenant_id"],
            [
                "intake_findings_reports.id",
                "intake_findings_reports.project_id",
                "intake_findings_reports.tenant_id",
            ],
            ondelete="RESTRICT",
            name="findings_project_tenant",
        ),
        ForeignKeyConstraint(
            ["cost_forecast_run_id", "project_id", "tenant_id"],
            [
                "cost_forecast_runs.id",
                "cost_forecast_runs.project_id",
                "cost_forecast_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="forecast_project_tenant",
        ),
        CheckConstraint(f"status IN ({_IN_IMP_STATUS})", name="status"),
        CheckConstraint(
            f"refresh_posture IS NULL OR refresh_posture='{REFRESH_POSTURE}'",
            name="refresh_posture",
        ),
        *[CheckConstraint(sql, name=name) for name, sql in IMPROVEMENT_CHECK_CONSTRAINTS],
        UniqueConstraint(
            "tenant_id", "window_id", "seq", name="uq_ops_improvement_results_window_seq"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    window_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    improvement_class: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    findings_report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cost_forecast_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    metric_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refresh_posture: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsStabilizationClosureAttempt(Base):
    """Persisted closure refusal. Never closes the window."""

    __tablename__ = "ops_stabilization_closure_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["window_id", "project_id", "tenant_id"],
            [
                "ops_stabilization_windows.id",
                "ops_stabilization_windows.project_id",
                "ops_stabilization_windows.tenant_id",
            ],
            ondelete="RESTRICT",
            name="window_project_tenant",
        ),
        CheckConstraint(f"result_code IN ({_IN_CLOSURE})", name="result_code"),
        CheckConstraint(
            "char_length(actor) BETWEEN 1 AND 200 AND actor = btrim(actor)",
            name="actor",
        ),
        Index("ix_ops_stab_closure_latest", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    window_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    result_code: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
