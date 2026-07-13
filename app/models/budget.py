"""``budgets`` — tenant-owned per-project cost ceilings (Slice 7, §19.7).

One budget per project (``UNIQUE(tenant_id, project_id)``). Mutable + audited
(SELECT/INSERT/UPDATE, no DELETE), mirroring ``autonomy_policies``: a missing
budget is fail-closed at the decision layer (``evaluate`` ⇒ STOP ``no_budget``),
and every change is audited with before/after caps. **Budget changes are audited
but are NOT verified human approvals** — an approval workflow for budget increases
is deferred (request-auth + Slice-4 wiring out of scope).
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

_MONEY = Numeric(18, 6)


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint("max_total_cost_usd >= 0", name="max_total_non_negative"),
        CheckConstraint(
            "max_daily_cost_usd IS NULL OR max_daily_cost_usd >= 0",
            name="max_daily_non_negative",
        ),
        UniqueConstraint("tenant_id", "project_id"),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_budgets_id_project_tenant"),
        Index(None, "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    max_total_cost_usd: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    max_daily_cost_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
