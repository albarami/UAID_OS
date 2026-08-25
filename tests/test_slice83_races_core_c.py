"""Slice 83 P-MUT-1b, P-MUT-1c, P-MUT-12."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.concurrency import ConcurrentWriteUnresolved
from app.cost import to_decimal
from app.models.budget import Budget
from app.repositories.cost import BudgetRepository, _money_str
from app.repositories.extraction import ExtractionRepository, PromotionRefConflict
from app.repositories.extraction_promotion import _ExtractionPromotionMixin
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext
from tests.admin_support import pg_state
from tests.slice83_support import (
    bind_tenant,
    seed_approved_requirement,
    seed_org_tenant_project,
    two_committed_transactions,
)

pytestmark = pytest.mark.db


async def _upsert_without_populate_existing(
    self,
    *,
    project_id,
    max_total_cost_usd,
    max_daily_cost_usd=None,
    actor: str,
):
    total = to_decimal(max_total_cost_usd, "max_total_cost_usd")
    daily = (
        to_decimal(max_daily_cost_usd, "max_daily_cost_usd")
        if max_daily_cost_usd is not None
        else None
    )
    existing = await self.get(project_id)
    old_total = existing.max_total_cost_usd if existing else None
    old_daily = existing.max_daily_cost_usd if existing else None
    stmt = (
        pg_insert(Budget)
        .values(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            max_total_cost_usd=total,
            max_daily_cost_usd=daily,
        )
        .on_conflict_do_update(
            constraint="uq_budgets_tenant_id_project_id",
            set_={
                "max_total_cost_usd": total,
                "max_daily_cost_usd": daily,
                "updated_at": func.now(),
            },
        )
        .returning(Budget.id)
    )
    budget_id = (await self.session.execute(stmt)).scalar_one()
    budget = (await self.session.execute(select(Budget).where(Budget.id == budget_id))).scalar_one()
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


async def _upsert_without_updated_at(
    self,
    *,
    project_id,
    max_total_cost_usd,
    max_daily_cost_usd=None,
    actor: str,
):
    total = to_decimal(max_total_cost_usd, "max_total_cost_usd")
    daily = (
        to_decimal(max_daily_cost_usd, "max_daily_cost_usd")
        if max_daily_cost_usd is not None
        else None
    )
    existing = await self.get(project_id)
    old_total = existing.max_total_cost_usd if existing else None
    old_daily = existing.max_daily_cost_usd if existing else None
    stmt = (
        pg_insert(Budget)
        .values(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            max_total_cost_usd=total,
            max_daily_cost_usd=daily,
        )
        .on_conflict_do_update(
            constraint="uq_budgets_tenant_id_project_id",
            set_={
                "max_total_cost_usd": total,
                "max_daily_cost_usd": daily,
            },
        )
        .returning(Budget.id)
    )
    budget_id = (await self.session.execute(stmt)).scalar_one()
    budget = (
        await self.session.execute(
            select(Budget).where(Budget.id == budget_id).execution_options(populate_existing=True)
        )
    ).scalar_one()
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


async def test_p_mut_1b_populate_existing_and_updated_at(monkeypatch, rls_engine, admin_engine):
    """P-MUT-1b: drop populate_existing ⇒ stale returned caps; drop updated_at ⇒ no advance."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def first(session: AsyncSession):
        row = await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="1",
            max_daily_cost_usd="1",
            actor="s83-1b",
        )
        return {"created_at": row.created_at, "updated_at": row.updated_at}

    async def second(session: AsyncSession):
        return await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="2",
            max_daily_cost_usd="2",
            actor="s83-1b",
        )

    async def confirm(session: AsyncSession):
        return await BudgetRepository(session, ctx).get(world["project"])

    monkeypatch.setattr(BudgetRepository, "upsert", _upsert_without_populate_existing)
    stale = await two_committed_transactions(
        engine=rls_engine,
        tenant_id=world["tenant"],
        first=first,
        second=second,
        confirm=confirm,
    )
    try:
        assert stale.second.max_total_cost_usd == Decimal("1")
        assert stale.confirmed.max_total_cost_usd == Decimal("2")
        print(
            "P-MUT-1b populate_existing",
            f"returned_caps={stale.second.max_total_cost_usd},{stale.second.max_daily_cost_usd}",
            f"stored_caps={stale.confirmed.max_total_cost_usd},{stale.confirmed.max_daily_cost_usd}",
        )
    finally:
        await stale.session.close()
        await stale.confirm_session.close()

    world2 = await seed_org_tenant_project(admin_engine)
    ctx2 = TenantContext(world2["tenant"])

    async def first2(session: AsyncSession):
        row = await BudgetRepository(session, ctx2).upsert(
            project_id=world2["project"],
            max_total_cost_usd="1",
            max_daily_cost_usd="1",
            actor="s83-1b",
        )
        return {"updated_at": row.updated_at}

    async def second2(session: AsyncSession):
        return await BudgetRepository(session, ctx2).upsert(
            project_id=world2["project"],
            max_total_cost_usd="2",
            max_daily_cost_usd="2",
            actor="s83-1b",
        )

    async def confirm2(session: AsyncSession):
        return await BudgetRepository(session, ctx2).get(world2["project"])

    monkeypatch.setattr(BudgetRepository, "upsert", _upsert_without_updated_at)
    frozen = await two_committed_transactions(
        engine=rls_engine,
        tenant_id=world2["tenant"],
        first=first2,
        second=second2,
        confirm=confirm2,
    )
    try:
        assert frozen.confirmed.updated_at == frozen.first["updated_at"]
        print("P-MUT-1b updated_at", frozen.first["updated_at"], frozen.confirmed.updated_at)
    finally:
        await frozen.session.close()
        await frozen.confirm_session.close()


async def test_p_mut_1c_missing_txn2_rebind(rls_engine, admin_engine):
    """P-MUT-1c: omit txn-2 set_config ⇒ SQLSTATE 42501 on budgets RLS."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    session = AsyncSession(rls_engine, expire_on_commit=False)
    await session.begin()
    await bind_tenant(session, world["tenant"])
    await BudgetRepository(session, ctx).upsert(
        project_id=world["project"],
        max_total_cost_usd="1",
        max_daily_cost_usd="1",
        actor="s83-1c",
    )
    await session.commit()
    await session.begin()
    try:
        await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="2",
            max_daily_cost_usd="2",
            actor="s83-1c",
        )
    except Exception as exc:
        assert pg_state(exc) == "42501"
        assert "budgets" in str(exc)
        print("P-MUT-1c", pg_state(exc), str(exc).split("\n")[0])
    else:
        raise AssertionError("expected 42501")
    finally:
        await session.close()


async def test_p_mut_12_wide_handler_relabels(monkeypatch, rls_engine, admin_engine):
    """P-MUT-12: bare except IntegrityError relabels a non-23505 as PromotionRefConflict."""

    class _FkFailure(Exception):
        sqlstate = "23503"
        pgcode = "23503"

    async def boom(self, *args, **kwargs):
        raise IntegrityError("INSERT", {}, _FkFailure("fk"))

    original = _ExtractionPromotionMixin.promote_proposal

    async def wide(self, *args, **kwargs):
        try:
            return await original(self, *args, **kwargs)
        except IntegrityError:
            recovered = await self.promotion_for(kwargs.get("proposal_id") or args[0])
            if recovered is not None:
                return await IntakeRepository(self.session, self.context).get_artifact(
                    recovered.artifact_id
                )
            raise PromotionRefConflict("artifact ref already used by a different promotion")

    monkeypatch.setattr(IntakeRepository, "add_artifact", boom)
    monkeypatch.setattr(ExtractionRepository, "promote_proposal", wide)
    world = await seed_approved_requirement(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with rls_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        await bind_tenant(session, world["tenant"])
        try:
            await ExtractionRepository(session, ctx).promote_proposal(
                proposal_id=world["proposal"], actor="s83-m12"
            )
        except PromotionRefConflict as exc:
            assert type(exc) is PromotionRefConflict
            assert type(exc) is not ConcurrentWriteUnresolved
            print("P-MUT-12", type(exc).__name__, str(exc))
        else:
            raise AssertionError("wide handler must relabel 23503 as PromotionRefConflict")
        finally:
            await session.close()
            await trans.rollback()
