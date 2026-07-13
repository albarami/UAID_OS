"""``cost_events`` — tenant-owned, IMMUTABLE financial ledger (Slice 7, §19.2).

One row per incurred cost; the source of truth for spend (running totals are
on-demand SUMs, never a denormalized counter). Append-only AND DB-immutable:
``BEFORE UPDATE/DELETE`` (row) + ``BEFORE TRUNCATE`` (statement) triggers + REVOKE
(migration ``0008``). **Honest threat model:** DML-immutable for all roles incl.
the table owner, but a DB superuser/schema owner can still disable triggers or drop
the table (DML-immutable, not tamper-proof vs. privileged actors — same bar as the
audit log).

Idempotency is source-namespaced: a partial UNIQUE on
``(tenant_id, source_system, external_ref) WHERE external_ref IS NOT NULL`` lets a
provider event be recorded safely under retries; reuse of the key with different
material data raises ``IdempotencyConflict`` (see ``app.repositories.cost``).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_MONEY = Numeric(18, 6)
# §19.2 cost components — DB-enforced (mirrors app.cost.COST_COMPONENTS).
_COMPONENTS = (
    "model_inference",
    "tool_execution",
    "cloud_runtime",
    "ci_cd",
    "storage_retrieval",
    "monitoring",
    "human_review",
    "rework",
)


class CostEvent(Base):
    __tablename__ = "cost_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        # Pin an attributed run to the SAME project AND tenant (dormant when NULL).
        ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        CheckConstraint(
            f"component IN ({', '.join(repr(c) for c in _COMPONENTS)})",
            name="component_valid",
        ),
        CheckConstraint("amount_usd >= 0", name="amount_usd_non_negative"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_non_negative"),
        Index(
            "uq_cost_events_idempotency",
            "tenant_id",
            "source_system",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
        Index("ix_cost_events_tenant_project", "tenant_id", "project_id"),
        Index("ix_cost_events_tenant_project_occurred", "tenant_id", "project_id", "occurred_at"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_cost_events_id_project_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    component: Mapped[str] = mapped_column(Text, nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    source_system: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'internal'")
    )
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
