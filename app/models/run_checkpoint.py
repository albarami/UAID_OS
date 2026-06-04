"""``run_checkpoints`` — tenant-owned LangGraph checkpoint blobs (Slice 8a, §23.2).

MUTABLE working state (not an audit ledger): grants SELECT/INSERT/DELETE so the
custom checkpointer can persist checkpoints and ``adelete_thread`` can clean up a
thread's working state. The durable, IMMUTABLE history lives in ``run_steps``.

Checkpoint payloads are serialized by LangGraph's own serializer to BYTEA — they
hold workflow state (potentially tenant content), which is exactly why this table
is tenant-owned + RLS (the D2 rationale).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RunCheckpoint(Base):
    __tablename__ = "run_checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        UniqueConstraint(
            "tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id", name="uq_run_checkpoints_id"
        ),
        # thread_id is always the run's id — guards against same-tenant cross-run rows.
        CheckConstraint("thread_id = run_id::text", name="thread_matches_run"),
        Index("ix_run_checkpoints_thread", "tenant_id", "thread_id", "checkpoint_ns"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    checkpoint_ns: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    checkpoint_id: Mapped[str] = mapped_column(Text, nullable=False)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    checkpoint_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
