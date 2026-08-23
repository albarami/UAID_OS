"""Global append-only Slice 62 aggregate snapshot. No tenant id."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ecosystem.learning_db_checks import BUCKET_CHECK_CONSTRAINTS, RUN_CHECK_CONSTRAINTS
from app.models.base import Base


class CrossProjectAggregateRun(Base):
    """One global 62-row snapshot."""

    __tablename__ = "cross_project_aggregate_runs"
    __table_args__ = (
        *[CheckConstraint(sql, name=name) for name, sql in RUN_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ruleset_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'slice62.v1'")
    )
    contract_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'slice62.aggregates.v1'")
    )
    bucket_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    published_bucket_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    publisher: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'slice62.learning_publish'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class CrossProjectAggregateBucket(Base):
    """One universe key in a snapshot. ``published`` is GENERATED."""

    __tablename__ = "cross_project_aggregate_buckets"
    __table_args__ = (
        UniqueConstraint("run_id", "signal_class", "bucket_key", name="uq_cpab_run_class_key"),
        *[CheckConstraint(sql, name=name) for name, sql in BUCKET_CHECK_CONSTRAINTS],
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cross_project_aggregate_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    signal_class: Mapped[str] = mapped_column(Text, nullable=False)
    bucket_key: Mapped[str] = mapped_column(Text, nullable=False)
    n_events: Mapped[int] = mapped_column(Integer, nullable=False)
    n_projects: Mapped[int] = mapped_column(Integer, nullable=False)
    n_tenants: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_sum: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    metric_unit: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[bool] = mapped_column(
        Boolean,
        Computed("n_projects >= 3 AND n_tenants >= 2", persisted=True),
        nullable=False,
    )
