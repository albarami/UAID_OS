"""Tenant-scoped cost-ledger repositories (Slice 7, §19).

``CostEventRepository`` records incurred cost (append-only, idempotent on a
source-namespaced key) and computes on-demand totals; ``BudgetRepository`` manages
per-project ceilings (audited with before/after caps). ``evaluate`` composes them
into the §19.7 stop decision. Run inside ``tenant_scope`` (GUC set). ``actor`` is an
untrusted caller label until request-auth exists.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.cost import (
    BudgetCeilings,
    CostStopDecision,
    IdempotencyConflict,
    evaluate_stop,
    to_decimal,
    validate_component,
)
from app.models.budget import Budget
from app.models.cost_event import CostEvent
from app.tenancy import TenantContext, TenantScopedRepository

# Material ledger fields compared on an idempotency-key collision (actor and
# description are intentionally excluded — actor is untrusted, description is non-material).
_MATERIAL_FIELDS = ("project_id", "run_id", "component", "amount_usd", "quantity", "source_system")

_SCALE6 = Decimal("0.000001")


def _money_str(value: Decimal | None) -> str | None:
    """Audit money values at a consistent NUMERIC(18,6) scale (or None)."""
    return None if value is None else str(value.quantize(_SCALE6))


class CostEventRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, CostEvent)

    async def record(
        self,
        *,
        project_id: uuid.UUID,
        component: str,
        amount_usd,
        run_id: uuid.UUID | None = None,
        quantity=None,
        source_system: str = "internal",
        external_ref: str | None = None,
        description: str | None = None,
        actor: str,
        occurred_at: datetime | None = None,
    ) -> CostEvent:
        """Record an incurred cost. Always records valid costs (even over budget).

        Idempotent on ``(tenant, source_system, external_ref)`` when ``external_ref``
        is set: a true retry returns the existing row; reuse with different material
        data raises ``IdempotencyConflict``. Audited only on an actual insert.
        """
        validate_component(component)
        amount = to_decimal(amount_usd, "amount_usd")
        qty = to_decimal(quantity, "quantity") if quantity is not None else None

        values = {
            "tenant_id": self.context.tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "component": component,
            "amount_usd": amount,
            "quantity": qty,
            "source_system": source_system,
            "external_ref": external_ref,
            "description": description,
            "actor": actor,
        }
        if occurred_at is not None:
            values["occurred_at"] = occurred_at

        # No idempotency key ⇒ always a fresh event.
        if external_ref is None:
            event = CostEvent(**values)
            self.session.add(event)
            await self.session.flush()
            await self._audit(event)
            return event

        # Concurrency-safe idempotent insert: ON CONFLICT DO NOTHING does NOT abort
        # the transaction, so the session stays usable on a collision.
        stmt = (
            pg_insert(CostEvent)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "source_system", "external_ref"],
                index_where=CostEvent.external_ref.isnot(None),
            )
            .returning(CostEvent.id)
        )
        new_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if new_id is not None:
            event = await self.get(new_id)
            await self._audit(event)
            return event

        # Collision: re-select and compare material fields.
        existing = await self._by_idempotency(source_system, external_ref)
        self._assert_material_match(existing, values, compare_occurred_at=occurred_at is not None)
        return existing

    async def total_spent(self, project_id: uuid.UUID) -> Decimal:
        stmt = select(func.sum(CostEvent.amount_usd)).where(
            CostEvent.tenant_id == self.context.tenant_id,
            CostEvent.project_id == project_id,
        )
        return (await self.session.execute(stmt)).scalar_one() or Decimal("0")

    async def daily_spent(self, project_id: uuid.UUID, day: date) -> Decimal:
        # Deterministic UTC half-open window [start, start+1d) — never a
        # session-timezone-dependent ``occurred_at::date`` cast.
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        stmt = select(func.sum(CostEvent.amount_usd)).where(
            CostEvent.tenant_id == self.context.tenant_id,
            CostEvent.project_id == project_id,
            CostEvent.occurred_at >= start,
            CostEvent.occurred_at < end,
        )
        return (await self.session.execute(stmt)).scalar_one() or Decimal("0")

    async def _by_idempotency(self, source_system: str, external_ref: str) -> CostEvent:
        stmt = select(CostEvent).where(
            CostEvent.tenant_id == self.context.tenant_id,
            CostEvent.source_system == source_system,
            CostEvent.external_ref == external_ref,
        )
        return (await self.session.execute(stmt)).scalar_one()

    @staticmethod
    def _assert_material_match(existing: CostEvent, values: dict, *, compare_occurred_at: bool):
        for field in _MATERIAL_FIELDS:
            if getattr(existing, field) != values[field]:
                raise IdempotencyConflict(
                    f"idempotency key reused with different {field}: "
                    f"existing={getattr(existing, field)!r} requested={values[field]!r}"
                )
        if compare_occurred_at and existing.occurred_at != values["occurred_at"]:
            raise IdempotencyConflict("idempotency key reused with different occurred_at")

    async def _audit(self, event: CostEvent) -> None:
        # Safe metadata only — never the free-text description.
        await audit_record(
            self.session,
            action="cost_event.recorded",
            actor=event.actor,
            target=f"cost_event:{event.id}",
            payload={
                "project_id": str(event.project_id),
                "run_id": str(event.run_id) if event.run_id else None,
                "component": event.component,
                "amount_usd": str(event.amount_usd),
                "source_system": event.source_system,
                "external_ref": event.external_ref,
            },
        )


class BudgetRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, Budget)

    async def get(self, project_id: uuid.UUID) -> Budget | None:
        stmt = select(Budget).where(
            Budget.tenant_id == self.context.tenant_id,
            Budget.project_id == project_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        *,
        project_id: uuid.UUID,
        max_total_cost_usd,
        max_daily_cost_usd=None,
        actor: str,
    ) -> Budget:
        total = to_decimal(max_total_cost_usd, "max_total_cost_usd")
        daily = (
            to_decimal(max_daily_cost_usd, "max_daily_cost_usd")
            if max_daily_cost_usd is not None
            else None
        )

        existing = await self.get(project_id)
        old_total = existing.max_total_cost_usd if existing else None
        old_daily = existing.max_daily_cost_usd if existing else None
        if existing is not None:
            existing.max_total_cost_usd = total
            existing.max_daily_cost_usd = daily
            budget = existing
        else:
            budget = Budget(
                project_id=project_id, max_total_cost_usd=total, max_daily_cost_usd=daily
            )
            await self.add(budget)  # stamps tenant_id
        await self.session.flush()
        await audit_record(
            self.session,
            action="budget.set",
            actor=actor,
            target=f"budget:project:{project_id}",
            payload={
                "project_id": str(project_id),
                "old_total": _money_str(old_total),
                "new_total": _money_str(total),
                "old_daily": _money_str(old_daily),
                "new_daily": _money_str(daily),
            },
        )
        return budget


async def evaluate(
    session: AsyncSession,
    context: TenantContext,
    *,
    project_id: uuid.UUID,
    as_of_date: date | None = None,
) -> CostStopDecision:
    """Compose budget + on-demand totals into the §19.7 stop decision (never halting)."""
    budget_row = await BudgetRepository(session, context).get(project_id)
    ceilings = (
        None
        if budget_row is None
        else BudgetCeilings(
            max_total_cost_usd=budget_row.max_total_cost_usd,
            max_daily_cost_usd=budget_row.max_daily_cost_usd,
        )
    )
    events = CostEventRepository(session, context)
    total = await events.total_spent(project_id)
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date()
    daily = await events.daily_spent(project_id, as_of_date)
    return evaluate_stop(total_spent=total, daily_spent=daily, budget=ceilings)
