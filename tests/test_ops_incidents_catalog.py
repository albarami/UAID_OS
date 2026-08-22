"""Slice 57 catalog, RLS, append-only, and idempotency-race proofs."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.ops.incident_service import open_incident, record_support_handover
from app.ops.incidents import HandoverPayload, IncidentPayload
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.tenancy import TenantContext, tenant_scope
from tests.ops_incidents_support import INCIDENT_TABLES


def _payload() -> IncidentPayload:
    return IncidentPayload(category="error", severity="high", summary="api 5xx burst")


async def _set_policy(ctx, project_id, level):
    async with tenant_scope(ctx) as session:
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=project_id,
            autonomy_level=level,
            overrides={},
            actor="inc-test",
        )


@pytest.mark.db
async def test_catalog_rls_append_only_and_race(inc_ctx, admin_engine, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    p1 = inc_ctx["p1"]
    await _set_policy(ctx, p1, 1)
    snap = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"cat-{inc_ctx['suffix']}"
    )
    handover = await record_support_handover(
        ctx,
        p1,
        actor="inc-test",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_complete"
        ),
    )
    assert snap.ticket_id is not None
    assert snap.latest_evaluation_id is not None
    async with admin_engine.connect() as conn:
        for table in INCIDENT_TABLES:
            row = (
                await conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": table},
                )
            ).one()
            assert row == (True, True)
            grants = {
                item[0]
                for item in (
                    await conn.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:t AND grantee='uaid_app'"
                        ),
                        {"t": table},
                    )
                ).all()
            }
            if table == "ops_incidents":
                assert grants == {"SELECT", "INSERT", "UPDATE"}
            else:
                assert grants == {"SELECT", "INSERT"}
        uniques = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE constraint_name IN ("
                        "'uq_ops_signal_results_id_project_tenant',"
                        "'uq_pm_issue_mappings_id_project_tenant')"
                    )
                )
            ).all()
        }
        event_id = (
            await conn.execute(
                text("SELECT id FROM ops_incident_events WHERE incident_id=:i LIMIT 1"),
                {"i": snap.id},
            )
        ).scalar_one()
        result_id = (
            await conn.execute(
                text(
                    "SELECT id FROM ops_incident_action_results WHERE evaluation_id=:e LIMIT 1"
                ),
                {"e": snap.latest_evaluation_id},
            )
        ).scalar_one()
    assert uniques == {
        "uq_ops_signal_results_id_project_tenant",
        "uq_pm_issue_mappings_id_project_tenant",
    }
    row_ids = {
        "ops_incidents": snap.id,
        "ops_incident_events": event_id,
        "ops_incident_tickets": snap.ticket_id,
        "ops_support_handovers": handover.id,
        "ops_incident_action_evaluations": snap.latest_evaluation_id,
        "ops_incident_action_results": result_id,
    }
    append_only = tuple(table for table in INCIDENT_TABLES if table != "ops_incidents")
    for table in append_only:
        row_id = row_ids[table]
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(f"UPDATE {table} SET created_at = created_at WHERE id=:i"),
                    {"i": row_id},
                )
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(f"DELETE FROM {table} WHERE id=:i"), {"i": row_id}
                )
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(f"TRUNCATE {table} CASCADE"))
    with pytest.raises(DBAPIError, match="not deletable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM ops_incidents WHERE id=:i"), {"i": snap.id}
            )
    with pytest.raises(DBAPIError, match="not deletable"):
        async with db_session.begin_nested():
            await db_session.execute(text("TRUNCATE ops_incidents CASCADE"))
    with pytest.raises(DBAPIError, match="immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE ops_incidents SET summary='x' WHERE id=:i"), {"i": snap.id}
            )
    await db_session.execute(
        text(
            "UPDATE ops_incidents SET status='investigating', updated_at=clock_timestamp() "
            "WHERE id=:i"
        ),
        {"i": snap.id},
    )
    key = f"race-{inc_ctx['suffix']}"
    results = await asyncio.gather(
        open_incident(ctx, p1, actor="a", payload=_payload(), idempotency_key=key),
        open_incident(ctx, p1, actor="b", payload=_payload(), idempotency_key=key),
    )
    assert {item.id for item in results} == {results[0].id}
