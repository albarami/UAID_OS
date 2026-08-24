"""Slice 84 / F-021 load-bearing probes for cost_events, global skills, and RA RLS."""

from __future__ import annotations

import re

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.slice84_support import (
    BINDING_NOT_EXACT,
    CANNOT_TRUNCATE_FK,
    COST_EVENTS_IMMUTABLE,
    GLOBAL_TABLES,
    PYTHON_CANDIDATE_LOOKUP,
    RLS_RA_POLICY,
    append_only_msg,
    disabled_trigger,
    err_text,
    expect_db_error,
    expect_exact_primary,
    mint_global_skill_rows,
    perm_msg,
    pg_primary_message,
    ra_insert_params,
    raw_risk_acceptance_insert_sql,
    runtime_sql,
    seed_s84_ctx,
    trigger_fire_state,
    valid_global_inserts,
)

_GRANT_ABSENT = (
    "null value in column",
    "violates not-null constraint",
    "violates foreign key constraint",
    "violates check constraint",
    "duplicate key value violates unique constraint",
)


@pytest_asyncio.fixture
async def s84_ctx(admin_engine):
    return await seed_s84_ctx(admin_engine)


async def _admin_truncate(admin_engine, sql: str) -> None:
    async with admin_engine.begin() as conn:
        await conn.execute(text(sql))


@pytest.mark.db
async def test_p_green_1a_cost_events_cascade_hits_named_trigger(s84_ctx, admin_engine):
    """Admin TRUNCATE cost_events CASCADE → cost_events immutability trigger (P0001)."""
    from app.repositories.cost import CostEventRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(s84_ctx["t1"])
    async with tenant_scope(ctx) as session:
        await CostEventRepository(session, ctx).record(
            project_id=s84_ctx["p1"], component="ci_cd", amount_usd="1", actor="a"
        )
    with pytest.raises(Exception) as ei:
        await _admin_truncate(admin_engine, "TRUNCATE cost_events CASCADE")
    expect_db_error(
        ei.value,
        COST_EVENTS_IMMUTABLE,
        "P0001",
        absent=("cannot truncate", "append-only"),
    )


@pytest.mark.db
async def test_p_green_1b_plain_truncate_is_the_slice51_fk(admin_engine):
    """Plain TRUNCATE cost_events hits cost_forecast_ledger_event_refs FK (0050:285)."""
    with pytest.raises(Exception) as ei:
        await _admin_truncate(admin_engine, "TRUNCATE cost_events")
    expect_db_error(ei.value, CANNOT_TRUNCATE_FK, "0A000", absent=(COST_EVENTS_IMMUTABLE,))


@pytest.mark.db
async def test_p_mut_1_disabling_named_trigger_unmasks_neighbour(admin_engine):
    """Disable only cost_events_no_truncate; CASCADE no longer names cost_events."""
    async with disabled_trigger(admin_engine, "cost_events", "cost_events_no_truncate"):
        async with admin_engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(text("TRUNCATE cost_events CASCADE"))
                outcome = "success"
                msg = ""
            except Exception as exc:
                outcome = "error"
                msg = err_text(exc)
            finally:
                await trans.rollback()
    assert await trigger_fire_state(admin_engine, "cost_events_no_truncate") == "O"
    assert COST_EVENTS_IMMUTABLE not in msg
    # Observed: CASCADE then hits the referencing ledger-ref append-only trigger.
    assert outcome == "error"
    assert "cost_forecast_ledger_event_refs is append-only" in msg


@pytest.mark.db
async def test_p_green_2a_cascade_is_table_specific(admin_engine):
    """TRUNCATE {table} CASCADE raises that table's append-only primary message."""
    for table in GLOBAL_TABLES:
        with pytest.raises(Exception) as ei:
            await _admin_truncate(admin_engine, f"TRUNCATE {table} CASCADE")
        expect_exact_primary(ei.value, append_only_msg(table), "P0001")


@pytest.mark.db
async def test_p_green_2b_plain_truncate_fk_vs_leaf_trigger(admin_engine):
    """FK-referenced tables stop at 0A000; agent_provided_skills reaches its trigger."""
    for table in ("skills", "agent_skill_capabilities"):
        with pytest.raises(Exception) as ei:
            await _admin_truncate(admin_engine, f"TRUNCATE {table}")
        expect_db_error(ei.value, CANNOT_TRUNCATE_FK, "0A000", absent=("append-only",))
    with pytest.raises(Exception) as ei:
        await _admin_truncate(admin_engine, "TRUNCATE agent_provided_skills")
    expect_exact_primary(ei.value, append_only_msg("agent_provided_skills"), "P0001")


@pytest.mark.db
async def test_p_green_2c_grant_matrix(admin_engine):
    """uaid_app SELECT true; INSERT/UPDATE/DELETE/TRUNCATE false (0037:315-317)."""
    async with admin_engine.connect() as conn:
        for table in GLOBAL_TABLES:
            for priv, expected in (
                ("SELECT", True),
                ("INSERT", False),
                ("UPDATE", False),
                ("DELETE", False),
                ("TRUNCATE", False),
            ):
                got = (
                    await conn.execute(
                        text("SELECT has_table_privilege('uaid_app', :t, :p)"),
                        {"t": table, "p": priv},
                    )
                ).scalar_one()
                assert bool(got) is expected, (table, priv, got)


@pytest.mark.db
async def test_p_green_2d_2e_valid_insert_is_grant_not_shape(s84_ctx, rls_engine, admin_engine):
    """ACL 42501 on a row that inserts as admin over minted parents (rolled back)."""
    minted = mint_global_skill_rows(s84_ctx["bp"])
    inserts = valid_global_inserts(minted)
    async with admin_engine.connect() as conn:
        pair = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM agent_provided_skills "
                    "WHERE capability_id=:c AND skill_id=:s"
                ),
                {"c": str(minted.capability_id), "s": str(minted.skill_id)},
            )
        ).scalar_one()
        keys = (
            await conn.execute(
                text("SELECT count(*) FROM skills WHERE key=:k"),
                {"k": minted.skill_key},
            )
        ).scalar_one()
    assert pair == 0 and keys == 0
    # 2d: ACL is evaluated before any constraint, so parents are irrelevant here.
    for table, (sql, params) in inserts.items():
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                await conn.execute(text(sql), params)
                await conn.commit()
        expect_db_error(ei.value, perm_msg(table), "42501", absent=_GRANT_ABSENT)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for table in GLOBAL_TABLES:
                sql, params = inserts[table]
                result = await conn.execute(text(sql), params)
                assert result.rowcount == 1, table
        finally:
            await trans.rollback()
    async with admin_engine.connect() as conn:
        pair = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM agent_provided_skills "
                    "WHERE capability_id=:c AND skill_id=:s"
                ),
                {"c": str(minted.capability_id), "s": str(minted.skill_id)},
            )
        ).scalar_one()
        keys = (
            await conn.execute(
                text("SELECT count(*) FROM skills WHERE key=:k"),
                {"k": minted.skill_key},
            )
        ).scalar_one()
    assert pair == 0 and keys == 0


@pytest.mark.db
async def test_p_green_2f_admin_masking_controls(s84_ctx, admin_engine):
    """Admin DEFAULT VALUES → 23502; unknown skill_id → fk_aps_skill.

    These are the errors a granted INSERT would produce, and the pre-Slice-84
    unmatched pytest.raises(Exception) at tests/test_skills.py:373-387 would
    accept either of them as if it were the grant refusal.
    """
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("INSERT INTO skills DEFAULT VALUES"))
            pytest.fail("admin DEFAULT VALUES unexpectedly succeeded")
        except Exception as exc:
            expect_db_error(
                exc,
                'null value in column "key" of relation "skills" violates not-null constraint',
                "23502",
            )
        finally:
            await trans.rollback()
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(
                text(
                    "INSERT INTO agent_provided_skills (capability_id, skill_id, can_review) "
                    "VALUES (:cap, gen_random_uuid(), false)"
                ),
                {"cap": str(s84_ctx["cap"])},
            )
            pytest.fail("admin unknown skill_id unexpectedly succeeded")
        except Exception as exc:
            expect_db_error(exc, 'violates foreign key constraint "fk_aps_skill"', "23503")
        finally:
            await trans.rollback()


@pytest.mark.db
async def test_p_mut_2_disabling_named_truncate_unmasks_message(admin_engine):
    """Disable {table}_no_truncate; P-GREEN-2a exact-primary equality must fail."""
    for table in GLOBAL_TABLES:
        trigger = f"{table}_no_truncate"
        expected = append_only_msg(table)
        async with disabled_trigger(admin_engine, table, trigger):
            async with admin_engine.connect() as conn:
                trans = await conn.begin()
                try:
                    await conn.execute(text(f"TRUNCATE {table} CASCADE"))
                    green_would_fail = True
                except Exception as exc:
                    primary = pg_primary_message(exc)
                    assert primary != expected, primary
                    with pytest.raises(AssertionError):
                        expect_exact_primary(exc, expected, "P0001")
                    if table == "skills":
                        assert primary == append_only_msg("agent_provided_skills")
                    green_would_fail = True
                finally:
                    await trans.rollback()
        assert await trigger_fire_state(admin_engine, trigger) == "O"
        assert green_would_fail


async def run_risk_acceptance_cross_tenant(ra_ctx, rls_engine) -> None:
    """Python candidate-lookup plus structurally valid cross-tenant SQL (P-GREEN-5a)."""
    from app.release.risk_acceptance import InvalidRiskAcceptance
    from app.tenancy import TenantContext, tenant_scope
    from tests.test_risk_acceptance import _bound, _repo

    t1, t2, p1 = ra_ctx["t1"], ra_ctx["t2"], ra_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _repo(session, ctx).create(project_id=p1, payload=_bound(ra_ctx), actor="a")
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM risk_acceptance_records"))
            ).scalar_one()
            assert n == 0
    async with tenant_scope(TenantContext(t2)) as session:
        assert await _repo(session, TenantContext(t2)).count_active_nonblocking(p1) == 0
    # Python path never issues INSERT / never reaches RLS (OD-3 / Sol defect 2).
    with pytest.raises(InvalidRiskAcceptance, match=re.escape(PYTHON_CANDIDATE_LOOKUP)) as ei:
        async with tenant_scope(TenantContext(t2)) as session:
            await _repo(session, TenantContext(t2)).create(
                project_id=p1, payload=_bound(ra_ctx), actor="attacker"
            )
    text_ = err_text(ei.value)
    assert "binding is not exact" not in text_
    assert "row-level security" not in text_
    assert "permission denied" not in text_
    with pytest.raises(Exception) as sql_ei:
        await runtime_sql(
            rls_engine,
            t2,
            raw_risk_acceptance_insert_sql(),
            **ra_insert_params(ra_ctx, tenant_id=t1, project_id=p1),
        )
    expect_db_error(
        sql_ei.value,
        BINDING_NOT_EXACT,
        "P0001",
        absent=(
            "foreign key",
            "violates check constraint",
            "null value in column",
            "InvalidRiskAcceptance",
        ),
    )


@pytest.mark.db
async def test_p_green_5a_binding_guard_before_rls(s84_ctx, rls_engine):
    """Cross-tenant SQL INSERT is the Slice-47 binding guard, not RLS (OD-3)."""
    with pytest.raises(Exception) as ei:
        await runtime_sql(
            rls_engine,
            s84_ctx["t2"],
            raw_risk_acceptance_insert_sql(),
            **ra_insert_params(s84_ctx, tenant_id=s84_ctx["t1"], project_id=s84_ctx["p1"]),
        )
    expect_db_error(
        ei.value,
        BINDING_NOT_EXACT,
        "P0001",
        absent=(
            "foreign key",
            "violates check constraint",
            "null value in column",
            "InvalidRiskAcceptance",
        ),
    )


@pytest.mark.db
async def test_p_green_5b_5c_rls_after_guard_disabled(s84_ctx, rls_engine, admin_engine):
    """Identical SQL with only the guard disabled is RLS 42501; tenant-axis fix inserts."""
    sql = raw_risk_acceptance_insert_sql()
    cross = ra_insert_params(s84_ctx, tenant_id=s84_ctx["t1"], project_id=s84_ctx["p1"])
    async with disabled_trigger(
        admin_engine, "risk_acceptance_records", "risk_acceptance_records_guard"
    ):
        with pytest.raises(Exception) as ei:
            await runtime_sql(rls_engine, s84_ctx["t2"], sql, **cross)
        expect_db_error(
            ei.value,
            RLS_RA_POLICY,
            "42501",
            absent=("foreign key", "permission denied", "binding is not exact"),
        )
        async with rls_engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(s84_ctx["t1"])},
                )
                result = await conn.execute(text(sql), cross)
                assert result.rowcount == 1
            finally:
                await trans.rollback()
    assert await trigger_fire_state(admin_engine, "risk_acceptance_records_guard") == "O"


@pytest.mark.db
async def test_p_mut_5_same_row_inserts_when_tenant_matches(s84_ctx, rls_engine, admin_engine):
    """Guard enabled, tenant axis corrected: identical SQL succeeds (rolled back)."""
    sql = raw_risk_acceptance_insert_sql()
    params = ra_insert_params(s84_ctx, tenant_id=s84_ctx["t1"], project_id=s84_ctx["p1"])
    async with rls_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(s84_ctx["t1"])},
            )
            result = await conn.execute(text(sql), params)
            assert result.rowcount == 1
        finally:
            await trans.rollback()
    assert await trigger_fire_state(admin_engine, "risk_acceptance_records_guard") == "O"
