"""Slice 7 — cost ledger (§19) tests.

Docker-free: money validation, stop-decision truth table, component validator.
DB-backed (`db`): accumulation, source-namespaced idempotency + conflict, UTC daily
bounds, quantity DB check, over-budget recording, budget upsert/audit/evaluate,
cost_events immutability, RLS + cross-tenant, FK pinning, catalog/grants/triggers.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401  (kept for parity/clarity)

from app.cost import (
    BudgetCeilings,
    InvalidAmount,
    InvalidComponent,
    StopReason,
    evaluate_stop,
    to_decimal,
    validate_component,
)
from app.repositories.cost import (
    BudgetRepository,
    CostEventRepository,
    IdempotencyConflict,
    evaluate,
)
from app.tenancy import TenantContext, tenant_scope

_DAY = date(2026, 1, 1)


# --- Docker-free --------------------------------------------------------------


def test_evaluate_stop_truth_table():
    b = BudgetCeilings(max_total_cost_usd=Decimal("100"), max_daily_cost_usd=Decimal("30"))
    assert (
        evaluate_stop(total_spent=Decimal("50"), daily_spent=Decimal("10"), budget=b).stop is False
    )
    # missing budget => fail-closed
    nb = evaluate_stop(total_spent=Decimal("0"), daily_spent=Decimal("0"), budget=None)
    assert nb.stop and nb.reason is StopReason.NO_BUDGET
    # total at ceiling (>=) => stop
    t = evaluate_stop(total_spent=Decimal("100"), daily_spent=Decimal("0"), budget=b)
    assert t.stop and t.reason is StopReason.BUDGET_EXCEEDED
    # daily at ceiling (>=) => stop
    d = evaluate_stop(total_spent=Decimal("10"), daily_spent=Decimal("30"), budget=b)
    assert d.stop and d.reason is StopReason.DAILY_BUDGET_EXCEEDED
    # no daily cap configured => daily never stops
    b2 = BudgetCeilings(max_total_cost_usd=Decimal("100"), max_daily_cost_usd=None)
    assert (
        evaluate_stop(total_spent=Decimal("0"), daily_spent=Decimal("9999"), budget=b2).stop
        is False
    )


def test_to_decimal_rejects_unsafe_inputs():
    for bad in (1.5, True, False):
        with pytest.raises(InvalidAmount):
            to_decimal(bad, "amount_usd")
    with pytest.raises(InvalidAmount):
        to_decimal("-1", "amount_usd")  # negative
    with pytest.raises(InvalidAmount):
        to_decimal(Decimal("NaN"), "amount_usd")  # non-finite
    with pytest.raises(InvalidAmount):
        to_decimal(Decimal("Infinity"), "amount_usd")
    with pytest.raises(InvalidAmount):
        to_decimal("1.1234567", "amount_usd")  # >6 dp


def test_to_decimal_accepts_safe_inputs():
    assert to_decimal(Decimal("10.50"), "a") == Decimal("10.50")
    assert to_decimal("0.000001", "a") == Decimal("0.000001")
    assert to_decimal(5, "a") == Decimal("5")


def test_validate_component():
    assert validate_component("model_inference") == "model_inference"
    with pytest.raises(InvalidComponent):
        validate_component("teleportation")


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(c, sql, **params):
    return (await c.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def cost_ctx(admin_engine):
    """Org + two tenants; tenant1 has P1/R1 and P2/R2; tenant2 has PX/RX."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('CostOrg',:s) RETURNING id",
            s=f"cost-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"cost-{label}-{sfx}",
            )
        for proj, tn, run in (("p1", "t1", "r1"), ("p2", "t1", "r2"), ("px", "t2", "rx")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"cost-{proj}-{sfx}",
            )
            out[run] = await _scalar(
                c,
                "INSERT INTO project_runs (tenant_id, project_id, status) "
                "VALUES (:t,:p,'running') RETURNING id",
                t=out[tn],
                p=out[proj],
            )
    return out


def _at(day: date, hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=timezone.utc)


# --- DB-backed: accumulation, idempotency, UTC bounds -------------------------


@pytest.mark.db
async def test_total_and_daily_spent_accumulate(cost_ctx):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = CostEventRepository(session, ctx)
        await repo.record(
            project_id=p1,
            component="model_inference",
            amount_usd="1.50",
            actor="a",
            occurred_at=_at(_DAY),
        )
        await repo.record(
            project_id=p1,
            component="tool_execution",
            amount_usd="0.250000",
            actor="a",
            occurred_at=_at(_DAY),
        )
        await repo.record(
            project_id=p1,
            component="ci_cd",
            amount_usd="2",
            actor="a",
            occurred_at=_at(date(2026, 1, 2)),
        )
        assert await repo.total_spent(p1) == Decimal("3.75")
        assert await repo.daily_spent(p1, _DAY) == Decimal("1.75")


@pytest.mark.db
async def test_idempotency_retry_conflict_and_session_usable(cost_ctx, admin_engine):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = CostEventRepository(session, ctx)
        e1 = await repo.record(
            project_id=p1,
            component="model_inference",
            amount_usd="10.00",
            source_system="provider_a",
            external_ref="evt_1",
            actor="a",
        )
        # identical retry => same row, no double-count
        e2 = await repo.record(
            project_id=p1,
            component="model_inference",
            amount_usd="10.00",
            source_system="provider_a",
            external_ref="evt_1",
            actor="a",
        )
        assert e2.id == e1.id
        # different amount with same key => conflict, session still usable
        with pytest.raises(IdempotencyConflict):
            await repo.record(
                project_id=p1,
                component="model_inference",
                amount_usd="999.00",
                source_system="provider_a",
                external_ref="evt_1",
                actor="a",
            )
        # different project with same key => conflict
        with pytest.raises(IdempotencyConflict):
            await repo.record(
                project_id=cost_ctx["p2"],
                component="model_inference",
                amount_usd="10.00",
                source_system="provider_a",
                external_ref="evt_1",
                actor="a",
            )
        # session usable + no double count
        assert await repo.total_spent(p1) == Decimal("10.00")
    # exactly ONE audit row for the inserted event (retry/conflicts wrote none)
    async with admin_engine.connect() as c:
        n = (
            await c.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE tenant_id=:t "
                    "AND action='cost_event.recorded'"
                ),
                {"t": t1},
            )
        ).scalar_one()
    assert n == 1


@pytest.mark.db
async def test_idempotency_namespacing(cost_ctx):
    t1, t2, p1, px = cost_ctx["t1"], cost_ctx["t2"], cost_ctx["p1"], cost_ctx["px"]
    async with tenant_scope(TenantContext(t1)) as session:
        repo = CostEventRepository(session, TenantContext(t1))
        a = await repo.record(
            project_id=p1,
            component="ci_cd",
            amount_usd="1",
            source_system="prov_a",
            external_ref="X",
            actor="a",
        )
        b = await repo.record(
            project_id=p1,
            component="ci_cd",
            amount_usd="1",
            source_system="prov_b",
            external_ref="X",
            actor="a",
        )
        assert a.id != b.id  # same ref, different source_system => separate
        n1 = await repo.record(project_id=p1, component="ci_cd", amount_usd="1", actor="a")
        n2 = await repo.record(project_id=p1, component="ci_cd", amount_usd="1", actor="a")
        assert n1.id != n2.id  # NULL external_ref always inserts
    # same source/ref under a different tenant => separate
    async with tenant_scope(TenantContext(t2)) as session:
        c = await CostEventRepository(session, TenantContext(t2)).record(
            project_id=px,
            component="ci_cd",
            amount_usd="1",
            source_system="prov_a",
            external_ref="X",
            actor="a",
        )
        assert c.id != a.id


@pytest.mark.db
async def test_daily_spent_uses_utc_half_open_bounds(cost_ctx):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = CostEventRepository(session, ctx)
        await repo.record(
            project_id=p1,
            component="ci_cd",
            amount_usd="5",
            actor="a",
            occurred_at=datetime(2026, 1, 1, 23, 59, 59, tzinfo=timezone.utc),
        )
        await repo.record(
            project_id=p1,
            component="ci_cd",
            amount_usd="7",
            actor="a",
            occurred_at=datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc),
        )
        assert await repo.daily_spent(p1, date(2026, 1, 1)) == Decimal("5")
        assert await repo.daily_spent(p1, date(2026, 1, 2)) == Decimal("7")


# --- DB-backed: quantity check, over-budget, budgets/evaluate -----------------


@pytest.mark.db
async def test_quantity_non_negative(cost_ctx, rls_engine):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = CostEventRepository(session, ctx)
        # app-layer rejects negative quantity
        with pytest.raises(InvalidAmount):
            await repo.record(
                project_id=p1, component="ci_cd", amount_usd="1", quantity="-2", actor="a"
            )
        # NULL and positive accepted
        await repo.record(project_id=p1, component="ci_cd", amount_usd="1", actor="a")
        await repo.record(
            project_id=p1, component="ci_cd", amount_usd="1", quantity="3.5", actor="a"
        )
    # raw uaid_app insert with negative quantity rejected by the DB CHECK
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(
                        "INSERT INTO cost_events (tenant_id, project_id, component, amount_usd, quantity, actor) "
                        "VALUES (:t,:p,'ci_cd',1,-2,'a')"
                    ),
                    {"t": str(t1), "p": str(p1)},
                )
    assert "quantity_non_negative" in str(ei.value).lower() or "check" in str(ei.value).lower()


@pytest.mark.db
async def test_invalid_component_rejected_by_db(cost_ctx, rls_engine):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(
                        "INSERT INTO cost_events (tenant_id, project_id, component, amount_usd, actor) "
                        "VALUES (:t,:p,'teleportation',1,'a')"
                    ),
                    {"t": str(t1), "p": str(p1)},
                )
    assert "component_valid" in str(ei.value).lower() or "check" in str(ei.value).lower()
    # a valid component raw insert succeeds (proves the CHECK allows the §19.2 set)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(
                text(
                    "INSERT INTO cost_events (tenant_id, project_id, component, amount_usd, actor) "
                    "VALUES (:t,:p,'model_inference',1,'a')"
                ),
                {"t": str(t1), "p": str(p1)},
            )


@pytest.mark.db
async def test_over_budget_costs_are_still_recorded(cost_ctx):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await BudgetRepository(session, ctx).upsert(
            project_id=p1, max_total_cost_usd="10", actor="admin"
        )
        repo = CostEventRepository(session, ctx)
        await repo.record(
            project_id=p1,
            component="model_inference",
            amount_usd="25",
            actor="a",
            occurred_at=_at(_DAY),
        )
        assert await repo.total_spent(p1) == Decimal("25")  # recorded despite over budget
        decision = await evaluate(session, ctx, project_id=p1, as_of_date=_DAY)
    assert decision.stop and decision.reason is StopReason.BUDGET_EXCEEDED


@pytest.mark.db
async def test_evaluate_outcomes(cost_ctx):
    t1 = cost_ctx["t1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        # missing budget => STOP no_budget
        d0 = await evaluate(session, ctx, project_id=cost_ctx["p1"], as_of_date=_DAY)
        assert d0.stop and d0.reason is StopReason.NO_BUDGET
    async with tenant_scope(ctx) as session:
        budgets = BudgetRepository(session, ctx)
        events = CostEventRepository(session, ctx)
        await budgets.upsert(
            project_id=cost_ctx["p1"],
            max_total_cost_usd="100",
            max_daily_cost_usd="30",
            actor="admin",
        )
        await events.record(
            project_id=cost_ctx["p1"],
            component="ci_cd",
            amount_usd="10",
            actor="a",
            occurred_at=_at(_DAY),
        )
        under = await evaluate(session, ctx, project_id=cost_ctx["p1"], as_of_date=_DAY)
        assert under.stop is False
        # push daily over
        await events.record(
            project_id=cost_ctx["p1"],
            component="ci_cd",
            amount_usd="25",
            actor="a",
            occurred_at=_at(_DAY),
        )
        daily = await evaluate(session, ctx, project_id=cost_ctx["p1"], as_of_date=_DAY)
        assert daily.stop and daily.reason is StopReason.DAILY_BUDGET_EXCEEDED


@pytest.mark.db
async def test_budget_upsert_audits_old_and_new_caps(cost_ctx, admin_engine):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = BudgetRepository(session, ctx)
        await repo.upsert(project_id=p1, max_total_cost_usd="100", actor="admin")
        await repo.upsert(
            project_id=p1, max_total_cost_usd="250", max_daily_cost_usd="40", actor="admin"
        )
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE tenant_id=:t AND action='budget.set' "
                    "ORDER BY seq"
                ),
                {"t": t1},
            )
        ).all()
    create, update = rows[0][0], rows[1][0]
    assert create["old_total"] is None and create["new_total"] == "100.000000"
    assert update["old_total"] == "100.000000" and update["new_total"] == "250.000000"
    assert update["new_daily"] == "40.000000"


# --- DB-backed: immutability, RLS, FK pinning, catalog ------------------------


@pytest.mark.db
async def test_cost_events_immutable(cost_ctx, rls_engine, admin_engine):
    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        e = await CostEventRepository(session, ctx).record(
            project_id=p1, component="ci_cd", amount_usd="1", actor="a"
        )
        eid = e.id
    # raw uaid_app UPDATE/DELETE rejected — blocked by the grant (no UPDATE/DELETE
    # privilege) or the trigger; either way the runtime cannot mutate the ledger.
    for stmt in (
        "UPDATE cost_events SET amount_usd=999 WHERE id=:i",
        "DELETE FROM cost_events WHERE id=:i",
    ):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(stmt), {"i": str(eid)})
        msg = str(ei.value).lower()
        assert "permission denied" in msg or "immutable" in msg
    # admin connection: UPDATE/DELETE/TRUNCATE all rejected by trigger
    for stmt in (
        "UPDATE cost_events SET amount_usd=999 WHERE id=:i",
        "DELETE FROM cost_events WHERE id=:i",
        "TRUNCATE cost_events",
    ):
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(text(stmt), {"i": str(eid)} if ":i" in stmt else {})
        assert "immutable" in str(ei.value).lower()


@pytest.mark.db
async def test_rls_deny_by_default_and_cross_tenant_blocked(cost_ctx, rls_engine):
    t1, t2, p1, px = cost_ctx["t1"], cost_ctx["t2"], cost_ctx["p1"], cost_ctx["px"]
    # seed one cost_event + budget for tenant1
    async with tenant_scope(TenantContext(t1)) as session:
        await CostEventRepository(session, TenantContext(t1)).record(
            project_id=p1, component="ci_cd", amount_usd="1", actor="a"
        )
        await BudgetRepository(session, TenantContext(t1)).upsert(
            project_id=p1, max_total_cost_usd="100", actor="a"
        )
    # no GUC => deny-by-default on both tables
    async with rls_engine.connect() as conn:
        async with conn.begin():
            assert (await conn.execute(text("SELECT count(*) FROM cost_events"))).scalar_one() == 0
            assert (await conn.execute(text("SELECT count(*) FROM budgets"))).scalar_one() == 0
    # GUC=t1, INSERT cost_event for tenant2 => WITH CHECK violation
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(
                        "INSERT INTO cost_events (tenant_id, project_id, component, amount_usd, actor) "
                        "VALUES (:t,:p,'ci_cd',1,'a')"
                    ),
                    {"t": str(t2), "p": str(px)},
                )
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


@pytest.mark.db
async def test_cross_tenant_budget_update_blocked(cost_ctx, rls_engine, admin_engine):
    t1, t2, px = cost_ctx["t1"], cost_ctx["t2"], cost_ctx["px"]
    # tenant2 has a budget
    async with tenant_scope(TenantContext(t2)) as session:
        await BudgetRepository(session, TenantContext(t2)).upsert(
            project_id=px, max_total_cost_usd="100", actor="a"
        )
    # GUC=t1 cannot UPDATE tenant2's budget (RLS USING hides it => 0 rows updated)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            res = await conn.execute(
                text("UPDATE budgets SET max_total_cost_usd=1 WHERE project_id=:p"),
                {"p": str(px)},
            )
            assert res.rowcount == 0  # tenant1 cannot see/update tenant2's budget
    # confirm unchanged
    async with admin_engine.connect() as c:
        val = (
            await c.execute(
                text("SELECT max_total_cost_usd FROM budgets WHERE project_id=:p"), {"p": px}
            )
        ).scalar_one()
    assert val == Decimal("100.000000")


@pytest.mark.db
async def test_fk_pinning(cost_ctx, admin_engine):
    # project from T_a but tenant_id=T_b; and run_id from another project/tenant.
    cases = [
        # tenant2 + project P1 (P1 belongs to tenant1) => project_tenant FK fails
        {"t": cost_ctx["t2"], "p": cost_ctx["p1"], "run": None},
        # tenant1/P1 but run R2 (belongs to P2) => run_project_tenant triple FK fails
        {"t": cost_ctx["t1"], "p": cost_ctx["p1"], "run": cost_ctx["r2"]},
        # tenant1/P1 but run RX (tenant2) => triple FK fails
        {"t": cost_ctx["t1"], "p": cost_ctx["p1"], "run": cost_ctx["rx"]},
    ]
    for case in cases:
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(
                    text(
                        "INSERT INTO cost_events (tenant_id, project_id, run_id, component, amount_usd, actor) "
                        "VALUES (:t,:p,:r,'ci_cd',1,'a')"
                    ),
                    {
                        "t": str(case["t"]),
                        "p": str(case["p"]),
                        "r": str(case["run"]) if case["run"] else None,
                    },
                )
        assert "foreign key" in str(ei.value).lower() or "violates" in str(ei.value).lower()


@pytest.mark.db
async def test_catalog_grants_and_triggers(admin_engine):
    async with admin_engine.connect() as c:
        grants = {}
        for tbl in ("cost_events", "budgets"):
            grants[tbl] = {
                r[0]
                for r in (
                    await c.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:t AND grantee='uaid_app'"
                        ),
                        {"t": tbl},
                    )
                ).all()
            }
            rls = (
                await c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": tbl},
                )
            ).one()
            assert rls == (True, True), tbl
        assert grants["cost_events"] == {"SELECT", "INSERT"}  # append-only
        assert grants["budgets"] == {"SELECT", "INSERT", "UPDATE"}  # no DELETE
        trigs = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                        "AND tgrelid = 'cost_events'::regclass"
                    )
                )
            ).all()
        }
    assert {"cost_events_no_update_delete", "cost_events_no_truncate"} <= trigs
