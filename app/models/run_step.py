"""``run_steps`` — tenant-owned, IMMUTABLE append-only run history (Slice 8a, §23.2).

The durable record of run lifecycle + state transitions used for state
reconstruction / incident review. Append-only and DB-immutable: UPDATE/DELETE/
TRUNCATE blocked by triggers (migration ``0009``); grants SELECT/INSERT only.
``adelete_thread`` (checkpoint cleanup) never touches this table. ``payload``
carries safe metadata only.

(8b will add further ``event_type`` values — e.g. retried / blocked_on_approval —
via its own migration.)
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_EVENT_TYPES = (
    "run_started",
    "step_completed",
    "run_resumed",
    "run_completed",
    "run_failed",
)


class RunStep(Base):
    __tablename__ = "run_steps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint(
            f"event_type IN ({', '.join(repr(e) for e in _EVENT_TYPES)})",
            name="event_type_valid",
        ),
        Index("ix_run_steps_run_seq", "tenant_id", "run_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    node: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    status_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
