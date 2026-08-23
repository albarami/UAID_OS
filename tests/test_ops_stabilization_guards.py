"""Slice 59 direct-SQL guard proofs. Seq 3 and seq 4 have no passed status."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.ops.incident_service import record_support_handover
from app.ops.incidents import HandoverPayload
from app.repositories.intake_categories import IntakeCategoryRepository
from app.tenancy import TenantContext, tenant_scope
from tests.ops_stabilization_support import (
    CRITERIA_ROWS,
    MONITORING_URL,
    declare_window,
    insert_default_children,
    insert_raw_snapshot,
    insert_sql_window,
    window_data,
)


@pytest.mark.db
async def test_direct_sql_forgeries_rejected(inc_ctx, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    tenant, project = inc_ctx["t1"], inc_ctx["p1"]
    category = await declare_window(ctx, project)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(
                db_session, tenant, project, category.id, as_of_sql="now() - interval '1 day'"
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(
                db_session, tenant, project, category.id, policy_digest_sql=":d"
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(db_session, tenant, project, category.id, age_mon=0)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(db_session, tenant, project, category.id, age_dep=169)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(
                db_session, tenant, project, category.id, extension_required=False
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(
                db_session, tenant, project, category.id, extends_window_id=category.id
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(
                db_session,
                tenant,
                project,
                category.id,
                target_ref="https://other.example.com/status",
            )
    window_id = await insert_sql_window(db_session, tenant, project, category.id)
    for seq, key, _status, _reason in CRITERIA_ROWS:
        if seq == 5:
            continue
        with pytest.raises(DBAPIError):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(
                        "INSERT INTO ops_stabilization_criterion_results ("
                        "tenant_id, project_id, window_id, seq, criterion_key, status, reason) "
                        "VALUES (:t,:p,:w,:seq,:key,'passed','forged')"
                    ),
                    {"t": tenant, "p": project, "w": window_id, "seq": seq, "key": key},
                )
    await insert_default_children(db_session, tenant, project, window_id)
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_stabilization_criterion_results ("
                    "tenant_id, project_id, window_id, seq, criterion_key, status, reason) "
                    "VALUES (:t,:p,:w,1,'zero_open_critical_incidents_for_days',"
                    "'not_evaluable','no_production_coverage_clock')"
                ),
                {"t": tenant, "p": project, "w": window_id},
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_improvement_results ("
                    "tenant_id, project_id, window_id, seq, improvement_class, status, reason) "
                    "VALUES (:t,:p,:w,1,'lessons_learned','not_observed','no_lessons_store')"
                ),
                {"t": tenant, "p": project, "w": window_id},
            )


@pytest.mark.db
async def test_localhost_seq3_pass_and_wrong_target_rejected(inc_ctx, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    tenant, project = inc_ctx["t1"], inc_ctx["p1"]
    local = "https://localhost/x"
    category = await declare_window(ctx, project, data=window_data(status_url=local))
    snap_id = await insert_raw_snapshot(db_session, tenant, project, local)
    window_id = await insert_sql_window(db_session, tenant, project, category.id, target_ref=local)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_stabilization_criterion_results ("
                    "tenant_id, project_id, window_id, seq, criterion_key, status, reason, "
                    "monitoring_snapshot_id) VALUES ("
                    ":t,:p,:w,3,'monitoring_confirmed_active','passed',"
                    "'monitoring_active_app_derived_not_db_provable',:s)"
                ),
                {"t": tenant, "p": project, "w": window_id, "s": snap_id},
            )
    other = await insert_raw_snapshot(
        db_session, tenant, project, "https://other.example.com/status"
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_stabilization_criterion_results ("
                    "tenant_id, project_id, window_id, seq, criterion_key, status, reason, "
                    "monitoring_snapshot_id) VALUES ("
                    ":t,:p,:w,3,'monitoring_confirmed_active','not_evaluable',"
                    "'monitoring_active_app_derived_not_db_provable',:s)"
                ),
                {"t": tenant, "p": project, "w": window_id, "s": other},
            )


@pytest.mark.db
async def test_seq5_pass_requires_latest_complete_handover(inc_ctx, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    tenant, project = inc_ctx["t1"], inc_ctx["p1"]
    category = await declare_window(ctx, project)
    incomplete = await record_support_handover(
        ctx,
        project,
        actor="stab-test",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_incomplete"
        ),
    )
    complete = await record_support_handover(
        ctx,
        project,
        actor="stab-test",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_complete"
        ),
    )
    window_id = await insert_sql_window(db_session, tenant, project, category.id)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_stabilization_criterion_results ("
                    "tenant_id, project_id, window_id, seq, criterion_key, status, reason, "
                    "handover_id) VALUES ("
                    ":t,:p,:w,5,'support_handover_complete','passed',"
                    "'handover_recorded_complete',:h)"
                ),
                {"t": tenant, "p": project, "w": window_id, "h": incomplete.id},
            )
    newer_incomplete = await record_support_handover(
        ctx,
        project,
        actor="stab-test",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_incomplete"
        ),
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_stabilization_criterion_results ("
                    "tenant_id, project_id, window_id, seq, criterion_key, status, reason, "
                    "handover_id) VALUES ("
                    ":t,:p,:w,5,'support_handover_complete','passed',"
                    "'handover_recorded_complete',:h)"
                ),
                {"t": tenant, "p": project, "w": window_id, "h": complete.id},
            )
    await db_session.execute(
        text(
            "INSERT INTO ops_stabilization_criterion_results ("
            "tenant_id, project_id, window_id, seq, criterion_key, status, reason, "
            "handover_id) VALUES ("
            ":t,:p,:w,5,'support_handover_complete','failed',"
            "'handover_recorded_incomplete',:h)"
        ),
        {"t": tenant, "p": project, "w": window_id, "h": newer_incomplete.id},
    )


@pytest.mark.db
async def test_wrong_category_provider_and_tampered_counters(inc_ctx, db_session):
    ctx = TenantContext(inc_ctx["t1"])
    tenant, project = inc_ctx["t1"], inc_ctx["p1"]
    await declare_window(ctx, project)
    async with tenant_scope(ctx) as session:
        domain = await IntakeCategoryRepository(session, ctx).declare(
            project_id=project,
            category="domain_pack",
            actor="stab-test",
            data={},
            origin="test",
        )
        wrong_provider = await IntakeCategoryRepository(session, ctx).declare(
            project_id=inc_ctx["p1b"],
            category="operations_observability_support",
            actor="stab-test",
            data=window_data(provider="other"),
            origin="test",
        )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(
                db_session, tenant, project, domain.id, target_ref=MONITORING_URL
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_sql_window(
                db_session,
                tenant,
                inc_ctx["p1b"],
                wrong_provider.id,
                target_ref=MONITORING_URL,
            )
    category = (
        await db_session.execute(
            text(
                "SELECT id FROM intake_categories WHERE project_id=:p "
                "AND category='operations_observability_support'"
            ),
            {"p": project},
        )
    ).scalar_one()
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            window_id = await insert_sql_window(
                db_session,
                tenant,
                project,
                category,
                passed=8,
                failed=0,
                missing=0,
                unevaluable=0,
            )
            await insert_default_children(db_session, tenant, project, window_id)
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
