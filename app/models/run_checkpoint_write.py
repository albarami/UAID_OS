"""``run_checkpoint_writes`` — tenant-owned LangGraph pending writes (Slice 8a).

MUTABLE working state: grants SELECT/INSERT/UPDATE/DELETE (a write may be re-emitted
on a super-step replay → upsert; ``adelete_thread`` cleans up). ``task_path`` is
persisted at rest (the installed ``aput_writes`` carries it) even though
``CheckpointTuple.pending_writes`` returns only ``(task_id, channel, value)``.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RunCheckpointWrite(Base):
    __tablename__ = "run_checkpoint_writes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
            "task_id",
            "idx",
            name="uq_run_checkpoint_writes_id",
        ),
        CheckConstraint("thread_id = run_id::text", name="thread_matches_run"),
        Index(
            "ix_run_checkpoint_writes_cp",
            "tenant_id",
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
        ),
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
    task_id: Mapped[str] = mapped_column(Text, nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    task_path: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
