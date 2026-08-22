"""Tenant-owned append-only Slice-56 ops observation runs and per-class results."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.ops.db_checks import CHILD_CHECK_CONSTRAINTS
from app.ops.signals import (
    CLASS_SEQ,
    METRIC_KINDS,
    OBSERVATION_STATUSES,
    REASON_CODES,
    RULESET_VERSION,
    SIGNAL_CLASSES,
    SOURCE_KINDS,
    SOURCE_TABLES,
    THRESHOLD_KINDS,
    THRESHOLD_PROVENANCES,
    THRESHOLD_STATES,
    TRUTH_TIERS,
    WINDOW_KINDS,
)

_HASH = r"^sha256:[0-9a-f]{64}$"
_MONEY = Numeric(18, 6)
_RATIO = Numeric(8, 6)
_IN = ", ".join(repr(item) for item in SIGNAL_CLASSES)
_REASON_IN = ", ".join(repr(item) for item in REASON_CODES)
_SEQ_CLASS = " OR ".join(
    f"(seq={seq} AND signal_class='{name}')" for name, seq in CLASS_SEQ.items()
)


class OpsObservationRun(Base):
    """One complete eleven-class assessment. Not production-readiness evidence."""

    __tablename__ = "ops_observation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(f"ruleset_version='{RULESET_VERSION}'", name="ruleset_version"),
        CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        CheckConstraint(f"request_digest ~ '{_HASH}'", name="request_digest"),
        CheckConstraint(f"input_digest ~ '{_HASH}'", name="input_digest"),
        CheckConstraint("signal_count = 11", name="signal_count"),
        CheckConstraint(
            "observed_count >= 0 AND caller_supplied_count >= 0 AND not_observed_count >= 0 "
            "AND observed_count + caller_supplied_count + not_observed_count = 11",
            name="status_counts",
        ),
        CheckConstraint("breached_count BETWEEN 0 AND 11", name="breached_count"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_observation_runs_id_project_tenant"
        ),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "idempotency_key",
            name="uq_ops_observation_runs_idempotency",
        ),
        Index("ix_ops_observation_runs_latest", "tenant_id", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_digest: Mapped[str] = mapped_column(Text, nullable=False)
    input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    caller_supplied_count: Mapped[int] = mapped_column(Integer, nullable=False)
    not_observed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    breached_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsSignalResult(Base):
    """One §25.1 class result. Presence of a row is assessment, not coverage."""

    __tablename__ = "ops_signal_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "ops_observation_runs.id",
                "ops_observation_runs.project_id",
                "ops_observation_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint("seq BETWEEN 1 AND 11", name="seq_bounded"),
        CheckConstraint(f"signal_class IN ({_IN})", name="signal_class"),
        CheckConstraint(_SEQ_CLASS, name="seq_class_pair"),
        CheckConstraint(
            f"observation_status IN ({', '.join(repr(item) for item in OBSERVATION_STATUSES)})",
            name="observation_status",
        ),
        CheckConstraint(
            f"truth_tier IN ({', '.join(repr(item) for item in TRUTH_TIERS)})",
            name="truth_tier",
        ),
        CheckConstraint(
            f"source_kind IN ({', '.join(repr(item) for item in SOURCE_KINDS)})",
            name="source_kind",
        ),
        CheckConstraint(
            f"source_table IN ({', '.join(repr(item) for item in SOURCE_TABLES)})",
            name="source_table",
        ),
        CheckConstraint(
            f"window_kind IN ({', '.join(repr(item) for item in WINDOW_KINDS)})",
            name="window_kind",
        ),
        CheckConstraint(
            f"reason_code IN ({_REASON_IN})",
            name="reason_code",
        ),
        CheckConstraint(
            f"threshold_provenance IN ({', '.join(repr(item) for item in THRESHOLD_PROVENANCES)})",
            name="threshold_provenance",
        ),
        CheckConstraint(
            f"threshold_kind IN ({', '.join(repr(item) for item in THRESHOLD_KINDS)})",
            name="threshold_kind",
        ),
        CheckConstraint(
            f"metric_kind IN ({', '.join(repr(item) for item in METRIC_KINDS)})",
            name="metric_kind",
        ),
        CheckConstraint(
            f"threshold_state IN ({', '.join(repr(item) for item in THRESHOLD_STATES)})",
            name="threshold_state",
        ),
        CheckConstraint(
            f"source_digest IS NULL OR source_digest ~ '{_HASH}'",
            name="source_digest",
        ),
        CheckConstraint(
            "(window_kind='none' AND window_start IS NULL AND window_end IS NULL) OR "
            "(window_kind='cumulative_project' AND window_start IS NULL "
            "AND window_end IS NOT NULL) OR "
            "(window_kind='caller_declared' AND window_start IS NOT NULL "
            "AND window_end IS NOT NULL AND window_start < window_end)",
            name="window_shape",
        ),
        CheckConstraint(
            "(signal_class='cost_anomalies' AND metric_money_daily IS NOT NULL) OR "
            "(signal_class<>'cost_anomalies' AND metric_money_daily IS NULL)",
            name="cost_daily_metric",
        ),
        CheckConstraint(
            "(observation_status<>'not_observed') OR ("
            "truth_tier='none' AND source_kind='none' AND source_table='none' "
            "AND source_ref IS NULL AND source_digest IS NULL "
            "AND metric_kind='none' AND metric_int IS NULL AND metric_ratio IS NULL "
            "AND metric_money IS NULL AND metric_money_daily IS NULL "
            "AND threshold_kind='none' AND threshold_provenance='none' "
            "AND threshold_int IS NULL AND threshold_ratio IS NULL "
            "AND threshold_money IS NULL AND threshold_money_daily IS NULL "
            "AND threshold_state='not_evaluable' AND window_kind='none' "
            "AND window_start IS NULL AND window_end IS NULL)",
            name="not_observed_shape",
        ),
        CheckConstraint(
            "(observation_status<>'observed') OR ("
            "truth_tier='system_derived_ledger' AND source_ref IS NULL "
            "AND source_digest IS NOT NULL AND window_kind='cumulative_project')",
            name="observed_shape",
        ),
        CheckConstraint(
            "(observation_status<>'caller_supplied_unverified') OR ("
            "truth_tier='caller_supplied_unverified' AND source_kind='caller_supplied' "
            "AND source_table='caller_sample' AND source_digest IS NOT NULL "
            "AND window_kind='caller_declared' "
            "AND threshold_provenance='caller_supplied_unverified' "
            "AND threshold_state IN ('ok','breached') "
            "AND metric_money IS NULL AND metric_money_daily IS NULL "
            "AND threshold_money IS NULL AND threshold_money_daily IS NULL "
            "AND ((threshold_state='ok' AND reason_code='caller_threshold_ok') OR "
            "(threshold_state='breached' AND reason_code='caller_threshold_breached')))",
            name="caller_shape",
        ),
        CheckConstraint(
            "(signal_class NOT IN ('uptime','security_alerts','support_tickets',"
            "'incident_reports')) OR observation_status='not_observed'",
            name="locked_not_observed",
        ),
        CheckConstraint(
            "(signal_class NOT IN ('job_failures','cost_anomalies')) OR "
            "observation_status='observed'",
            name="locked_observed",
        ),
        *(CheckConstraint(sql, name=name) for name, sql in CHILD_CHECK_CONSTRAINTS),
        UniqueConstraint("run_id", "seq", name="uq_ops_signal_results_run_seq"),
        UniqueConstraint("run_id", "signal_class", name="uq_ops_signal_results_run_class"),
        UniqueConstraint(
            "id",
            "project_id",
            "tenant_id",
            name="uq_ops_signal_results_id_project_tenant",
        ),
        Index("ix_ops_signal_results_run", "tenant_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_class: Mapped[str] = mapped_column(Text, nullable=False)
    observation_status: Mapped[str] = mapped_column(Text, nullable=False)
    truth_tier: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_table: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_kind: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_kind: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threshold_ratio: Mapped[Decimal | None] = mapped_column(_RATIO, nullable=True)
    threshold_money: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    threshold_money_daily: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    metric_kind: Mapped[str] = mapped_column(Text, nullable=False)
    metric_int: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_ratio: Mapped[Decimal | None] = mapped_column(_RATIO, nullable=True)
    metric_money: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    metric_money_daily: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    threshold_state: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
