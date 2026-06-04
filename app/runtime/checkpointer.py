"""UAID-owned LangGraph checkpointer (Slice 8a, §23.2 / D2).

A custom ``BaseCheckpointSaver`` that persists checkpoints + pending writes to our
tenant-owned, RLS-protected, Alembic-managed tables — NOT LangGraph's ``.setup()``
tables. Bound to a ``TenantContext`` + ``(project_id, run_id)`` and run inside
``tenant_scope`` (GUC set). ``thread_id == str(run_id)`` (one thread per project_run).

Checkpoint and write values are serialized with LangGraph's own serializer
(``self.serde``) to BYTEA — lossless for non-JSON channel values. The full checkpoint
(including ``channel_values``) is stored as one blob (no separate blob table).
"""

import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langchain_core.runnables import RunnableConfig
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run_checkpoint import RunCheckpoint
from app.models.run_checkpoint_write import RunCheckpointWrite
from app.tenancy import TenantContext


class UAIDCheckpointer(BaseCheckpointSaver):
    """Tenant-scoped, run-bound checkpointer over UAID Postgres tables."""

    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        project_id: uuid.UUID,
        run_id: uuid.UUID,
    ):
        super().__init__()
        self.session = session
        self.context = context
        self.project_id = project_id
        self.run_id = run_id
        self.thread_id = str(run_id)

    def _check_thread(self, config: RunnableConfig) -> None:
        thread_id = config["configurable"]["thread_id"]
        if thread_id != self.thread_id:
            raise ValueError(
                f"checkpointer is bound to run {self.thread_id}, got thread_id {thread_id}"
            )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        self._check_thread(config)
        cfg = config["configurable"]
        ns = cfg.get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_id = cfg.get("checkpoint_id")
        type_, blob = self.serde.dumps_typed(checkpoint)
        meta = get_checkpoint_metadata(config, metadata)
        stmt = (
            pg_insert(RunCheckpoint)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=self.project_id,
                run_id=self.run_id,
                thread_id=self.thread_id,
                checkpoint_ns=ns,
                checkpoint_id=checkpoint_id,
                parent_checkpoint_id=parent_id,
                type=type_,
                checkpoint=blob,
                checkpoint_metadata=dict(meta),
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id"]
            )
        )
        await self.session.execute(stmt)
        return {
            "configurable": {
                "thread_id": self.thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._check_thread(config)
        cfg = config["configurable"]
        ns = cfg.get("checkpoint_ns", "")
        checkpoint_id = cfg["checkpoint_id"]
        for idx, (channel, value) in enumerate(writes):
            write_idx = WRITES_IDX_MAP.get(channel, idx)
            type_, blob = self.serde.dumps_typed(value)
            stmt = (
                pg_insert(RunCheckpointWrite)
                .values(
                    tenant_id=self.context.tenant_id,
                    project_id=self.project_id,
                    run_id=self.run_id,
                    thread_id=self.thread_id,
                    checkpoint_ns=ns,
                    checkpoint_id=checkpoint_id,
                    task_id=task_id,
                    idx=write_idx,
                    channel=channel,
                    type=type_,
                    blob=blob,
                    task_path=task_path,
                )
                .on_conflict_do_update(
                    index_elements=[
                        "tenant_id",
                        "thread_id",
                        "checkpoint_ns",
                        "checkpoint_id",
                        "task_id",
                        "idx",
                    ],
                    set_={
                        "channel": channel,
                        "type": type_,
                        "blob": blob,
                        "task_path": task_path,
                    },
                )
            )
            await self.session.execute(stmt)

    def _bound(self, model):
        """Filters scoping a query to this checkpointer's exact bound identity.

        Belt-and-suspenders beyond RLS: RLS isolates by tenant, but two runs in the
        SAME tenant must not interfere, so we also pin project_id/run_id/thread_id.
        """
        return (
            model.tenant_id == self.context.tenant_id,
            model.project_id == self.project_id,
            model.run_id == self.run_id,
            model.thread_id == self.thread_id,
        )

    async def _pending_writes(self, ns: str, checkpoint_id: str) -> list[tuple[str, str, Any]]:
        stmt = (
            select(RunCheckpointWrite)
            .where(
                *self._bound(RunCheckpointWrite),
                RunCheckpointWrite.checkpoint_ns == ns,
                RunCheckpointWrite.checkpoint_id == checkpoint_id,
            )
            .order_by(RunCheckpointWrite.task_id, RunCheckpointWrite.idx)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        # CheckpointTuple.pending_writes is (task_id, channel, value); task_path is
        # preserved at rest (a column) but not part of the returned tuple.
        return [
            (r.task_id, r.channel, self.serde.loads_typed((r.type, bytes(r.blob)))) for r in rows
        ]

    def _row_to_tuple(self, row: RunCheckpoint, ns: str, pending) -> CheckpointTuple:
        parent_config = (
            {
                "configurable": {
                    "thread_id": self.thread_id,
                    "checkpoint_ns": ns,
                    "checkpoint_id": row.parent_checkpoint_id,
                }
            }
            if row.parent_checkpoint_id
            else None
        )
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": self.thread_id,
                    "checkpoint_ns": ns,
                    "checkpoint_id": row.checkpoint_id,
                }
            },
            checkpoint=self.serde.loads_typed((row.type, bytes(row.checkpoint))),
            metadata=row.checkpoint_metadata,
            parent_config=parent_config,
            pending_writes=pending,
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        self._check_thread(config)
        cfg = config["configurable"]
        ns = cfg.get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)
        stmt = select(RunCheckpoint).where(
            *self._bound(RunCheckpoint),
            RunCheckpoint.checkpoint_ns == ns,
        )
        if checkpoint_id:
            stmt = stmt.where(RunCheckpoint.checkpoint_id == checkpoint_id)
        else:
            stmt = stmt.order_by(RunCheckpoint.checkpoint_id.desc()).limit(1)
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        pending = await self._pending_writes(ns, row.checkpoint_id)
        return self._row_to_tuple(row, ns, pending)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if config is not None and "thread_id" in config.get("configurable", {}):
            self._check_thread(config)
        ns = (config or {}).get("configurable", {}).get("checkpoint_ns", "")
        stmt = select(RunCheckpoint).where(
            *self._bound(RunCheckpoint),
            RunCheckpoint.checkpoint_ns == ns,
        )
        if before is not None:
            if before["configurable"].get("thread_id", self.thread_id) != self.thread_id:
                raise ValueError("`before` refers to a different thread than this checkpointer")
            stmt = stmt.where(RunCheckpoint.checkpoint_id < before["configurable"]["checkpoint_id"])
        stmt = stmt.order_by(RunCheckpoint.checkpoint_id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        for row in rows:
            pending = await self._pending_writes(ns, row.checkpoint_id)
            yield self._row_to_tuple(row, ns, pending)

    async def adelete_thread(self, thread_id: str) -> None:
        # A run-bound checkpointer may only delete its OWN thread's working state.
        if thread_id != self.thread_id:
            raise ValueError(
                f"checkpointer is bound to run {self.thread_id}, refusing to delete thread {thread_id}"
            )
        # Deletes checkpoint WORKING STATE only — never run_steps (the immutable history).
        for model in (RunCheckpointWrite, RunCheckpoint):
            await self.session.execute(delete(model).where(*self._bound(model)))
