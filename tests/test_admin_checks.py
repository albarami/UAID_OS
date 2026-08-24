"""Slice 63 privilege, append-only, RLS, and catalog assertions."""

from __future__ import annotations

import inspect
import pathlib
import subprocess

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.admin.rbac import OPERATOR_PROVENANCE, RULESET_VERSION
from app.identity import AuthenticatedActor
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.tenancy import TenantContext
from tests.admin_check_support import (
    assert_catalog,
    committed_world as _committed_world,
    priv_statement as _priv_statement,
)
from tests.admin_support import (
    in_savepoint,
    insert_action,
    insert_grant,
    pg_state,
    seed_admin_world,
    set_guc,
    set_trigger,
    trigger_state,
)


@pytest.mark.db
@pytest.mark.parametrize(
    "table,priv,extra_trigger",
    [
        ("admin_role_grants", "INSERT", None),
        ("admin_role_grants", "UPDATE", None),
        ("admin_role_grants", "DELETE", "admin_role_grants_no_delete"),
        ("admin_actions", "UPDATE", "admin_actions_no_update_delete"),
        ("admin_actions", "DELETE", "admin_actions_no_update_delete"),
        ("admin_policy_changes", "INSERT", None),
        ("admin_policy_changes", "UPDATE", "admin_policy_changes_no_update_delete"),
        ("admin_policy_changes", "DELETE", "admin_policy_changes_no_update_delete"),
        ("tenant_admin_events", "INSERT", None),
        ("tenant_admin_events", "UPDATE", "tenant_admin_events_no_update_delete"),
        ("tenant_admin_events", "DELETE", "tenant_admin_events_no_update_delete"),
    ],
    ids=lambda v: v if isinstance(v, str) else (v or "none"),
)
async def test_p_priv_matrix(admin_engine, rls_engine, table, priv, extra_trigger):
    world = await _committed_world(admin_engine)
    async with admin_engine.begin() as c:
        await c.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(world["t"])},
        )
        gid = (
            await c.execute(
                text(
                    "INSERT INTO admin_role_grants ("
                    "tenant_id, principal_subject, admin_role, status, "
                    "granted_by, granted_by_provenance) "
                    "VALUES (:t, :p, 'tenant_admin', 'active', 'op', :prov) RETURNING id"
                ),
                {
                    "t": world["t"],
                    "p": f"priv-{world['sfx']}-{table}-{priv}",
                    "prov": OPERATOR_PROVENANCE,
                },
            )
        ).scalar_one()
        aid = (
            await c.execute(
                text(
                    "INSERT INTO admin_actions ("
                    "tenant_id, project_id, action_kind, actor_principal, actor_provenance, "
                    "required_role, actor_role, decision, ruleset_version) "
                    "VALUES (:t, :p, 'set_autonomy_policy', :prin, "
                    "'request_authenticated', 'tenant_admin', 'tenant_admin', "
                    "'allowed', :rs) RETURNING id"
                ),
                {
                    "t": world["t"],
                    "p": world["p"],
                    "prin": f"priv-{world['sfx']}-{table}-{priv}",
                    "rs": RULESET_VERSION,
                },
            )
        ).scalar_one()
        await c.execute(
            text(
                "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level) "
                "VALUES (:t, :p, 2)"
            ),
            {"t": world["t"], "p": world["p"]},
        )
        pol = (
            await c.execute(
                text("SELECT id FROM autonomy_policies WHERE project_id=:p"),
                {"p": world["p"]},
            )
        ).scalar_one()
        cid = None
        if table == "admin_policy_changes" and priv != "INSERT":
            cid = (
                await c.execute(
                    text(
                        "INSERT INTO admin_policy_changes ("
                        "tenant_id, project_id, admin_action_id, autonomy_policy_id, "
                        "previous_autonomy_level, new_autonomy_level, override_key_count) "
                        "VALUES (:t, :p, :a, :pol, 2, 2, 0) RETURNING id"
                    ),
                    {"t": world["t"], "p": world["p"], "a": aid, "pol": pol},
                )
            ).scalar_one()
        eid = None
        if table == "tenant_admin_events" and priv != "INSERT":
            eid = (
                await c.execute(
                    text(
                        "INSERT INTO tenant_admin_events ("
                        "tenant_id, organization_id, event_kind, performed_by, "
                        "performed_by_provenance) "
                        "VALUES (:t, :o, 'tenant_reinstated', 'op', :prov) RETURNING id"
                    ),
                    {"t": world["t"], "o": world["org"], "prov": OPERATOR_PROVENANCE},
                )
            ).scalar_one()
    ids = {"grant": gid, "action": aid, "change": cid, "event": eid, "policy": pol}
    stmt = _priv_statement(table, priv, world, ids)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(world["t"])},
            )
            nested = await conn.begin_nested()
            with pytest.raises(DBAPIError) as ei:
                await conn.execute(stmt)
            assert pg_state(ei.value) == "42501"
            assert table in str(ei.value).lower()
            await nested.rollback()
    async with admin_engine.begin() as c:
        await c.execute(text(f"GRANT {priv} ON public.{table} TO uaid_app"))
        if extra_trigger:
            await c.execute(text(f"ALTER TABLE public.{table} DISABLE TRIGGER {extra_trigger}"))
    try:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(world["t"])},
                )
                await conn.execute(stmt)
    finally:
        async with admin_engine.begin() as c:
            await c.execute(text(f"REVOKE {priv} ON public.{table} FROM uaid_app"))
            if extra_trigger:
                await c.execute(
                    text(f"ALTER TABLE public.{table} ENABLE TRIGGER {extra_trigger}")
                )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(world["t"])},
            )
            nested = await conn.begin_nested()
            with pytest.raises(DBAPIError) as ei:
                await conn.execute(stmt)
            assert pg_state(ei.value) == "42501"
            await nested.rollback()


@pytest.mark.db
async def test_p_ao_and_rls_and_catalog(db_session, rls_engine, admin_engine):
    """Append-only, RLS, and §5.3 catalog assertions."""
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    aid = await insert_action(db_session, w["t1"], w["p1"])
    await db_session.execute(
        text(
            "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level) "
            "VALUES (:t, :p, 2)"
        ),
        {"t": w["t1"], "p": w["p1"]},
    )
    pol = (
        await db_session.execute(
            text("SELECT id FROM autonomy_policies WHERE project_id=:p"),
            {"p": w["p1"]},
        )
    ).scalar_one()
    cid = (
        await db_session.execute(
            text(
                "INSERT INTO admin_policy_changes ("
                "tenant_id, project_id, admin_action_id, autonomy_policy_id, "
                "previous_autonomy_level, new_autonomy_level, override_key_count) "
                "VALUES (:t, :p, :a, :pol, 2, 2, 0) RETURNING id"
            ),
            {"t": w["t1"], "p": w["p1"], "a": aid, "pol": pol},
        )
    ).scalar_one()
    eid = (
        await db_session.execute(
            text(
                "INSERT INTO tenant_admin_events ("
                "tenant_id, organization_id, event_kind, performed_by, "
                "performed_by_provenance) VALUES (:t, :o, 'tenant_reinstated', 'op', :prov) "
                "RETURNING id"
            ),
            {"t": w["t1"], "o": w["org"], "prov": OPERATOR_PROVENANCE},
        )
    ).scalar_one()

    async def _ao(table, stmt, trigger, setup_disable=None):
        if setup_disable:
            await set_trigger(db_session, setup_disable[0], setup_disable[1], enabled=False)
        with pytest.raises(DBAPIError, match="append-only") as ei:
            await in_savepoint(db_session, lambda: db_session.execute(text(stmt)))
        assert table in str(ei.value)
        await set_trigger(db_session, table, trigger, enabled=False)
        nested = await db_session.begin_nested()
        try:
            await db_session.execute(text(stmt))
        finally:
            await nested.rollback()
        await set_trigger(db_session, table, trigger, enabled=True)
        if setup_disable:
            await set_trigger(db_session, setup_disable[0], setup_disable[1], enabled=True)
        assert await trigger_state(db_session, trigger) == "O"

    gid2 = await insert_grant(db_session, w["t1"], "unreferenced", "tenant_viewer")
    await _ao(
        "admin_role_grants",
        f"DELETE FROM admin_role_grants WHERE id='{gid2}'",
        "admin_role_grants_no_delete",
    )
    await _ao(
        "admin_role_grants",
        "TRUNCATE public.admin_role_grants, public.tenant_admin_events",
        "admin_role_grants_no_truncate",
        setup_disable=("tenant_admin_events", "tenant_admin_events_no_truncate"),
    )
    with pytest.raises(DBAPIError) as trunc:
        await in_savepoint(
            db_session, lambda: db_session.execute(text("TRUNCATE public.admin_role_grants"))
        )
    assert pg_state(trunc.value) == "0A000"
    await _ao(
        "admin_actions",
        f"UPDATE admin_actions SET decision='allowed' WHERE id='{aid}'",
        "admin_actions_no_update_delete",
    )
    await insert_grant(db_session, w["t1"], "unspent", "tenant_admin")
    aid2 = await insert_action(db_session, w["t1"], w["p1"], principal="unspent")
    await _ao(
        "admin_actions",
        f"DELETE FROM admin_actions WHERE id='{aid2}'",
        "admin_actions_no_update_delete",
    )
    await _ao(
        "admin_actions",
        "TRUNCATE public.admin_actions, public.admin_policy_changes",
        "admin_actions_no_truncate",
        setup_disable=("admin_policy_changes", "admin_policy_changes_no_truncate"),
    )
    await _ao(
        "admin_policy_changes",
        f"UPDATE admin_policy_changes SET new_autonomy_level=2 WHERE id='{cid}'",
        "admin_policy_changes_no_update_delete",
    )
    await _ao(
        "admin_policy_changes",
        f"DELETE FROM admin_policy_changes WHERE id='{cid}'",
        "admin_policy_changes_no_update_delete",
    )
    await _ao(
        "admin_policy_changes",
        "TRUNCATE public.admin_policy_changes",
        "admin_policy_changes_no_truncate",
    )
    await _ao(
        "tenant_admin_events",
        f"UPDATE tenant_admin_events SET event_kind='tenant_reinstated' WHERE id='{eid}'",
        "tenant_admin_events_no_update_delete",
    )
    await _ao(
        "tenant_admin_events",
        f"DELETE FROM tenant_admin_events WHERE id='{eid}'",
        "tenant_admin_events_no_update_delete",
    )
    await _ao(
        "tenant_admin_events",
        "TRUNCATE public.tenant_admin_events",
        "tenant_admin_events_no_truncate",
    )

    await assert_catalog(admin_engine, db_session)
    assert not hasattr(AutonomyPolicyRepository, "upsert")
    root = pathlib.Path(__file__).resolve().parents[1]
    forbidden = 0
    for path in root.rglob("*.py"):
        if path.name in {"0062_enterprise_admin.py", "ddl.py", "guards_sql.py", "policy_sql.py"}:
            continue
        text_src = path.read_text()
        if "INSERT INTO autonomy_policies" in text_src or "UPDATE autonomy_policies" in text_src:
            if "tests/" in str(path) or "migrations/" in str(path):
                continue
            forbidden += 1
    assert forbidden == 0
    helper = (root / "tests/admin_support.py").read_text()
    assert "INSERT INTO autonomy_policies" not in helper
    assert "apply_policy_change" in helper
    heads = subprocess.check_output(["uv", "run", "alembic", "heads"], text=True)
    assert "0062" in heads and heads.count("(head)") == 1
    import app.admin as admin_pkg
    for _n, mod in inspect.getmembers(admin_pkg, inspect.ismodule):
        assert "fastapi" not in getattr(mod, "__dict__", {})
    from app.main import app as fastapi_app
    paths = {getattr(r, "path", "") for r in fastapi_app.routes}
    assert not any("/admin" in p for p in paths)


@pytest.mark.db
async def test_p_rls_matrix(admin_engine, rls_engine):
    a = await _committed_world(admin_engine)
    b = await _committed_world(admin_engine)
    async with admin_engine.begin() as c:
        await c.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(b["t"])},
        )
        await c.execute(
            text(
                "INSERT INTO admin_role_grants ("
                "tenant_id, principal_subject, admin_role, status, "
                "granted_by, granted_by_provenance) "
                "VALUES (:t, 'bob', 'tenant_admin', 'active', 'op', :prov)"
            ),
            {"t": b["t"], "prov": OPERATOR_PROVENANCE},
        )
        await c.execute(
            text(
                "INSERT INTO admin_actions ("
                "tenant_id, project_id, action_kind, actor_principal, actor_provenance, "
                "required_role, actor_role, decision, ruleset_version) "
                "VALUES (:t, :p, 'set_autonomy_policy', 'bob', "
                "'request_authenticated', 'tenant_admin', 'tenant_admin', 'allowed', :rs)"
            ),
            {"t": b["t"], "p": b["p"], "rs": RULESET_VERSION},
        )
        await c.execute(
            text(
                "INSERT INTO tenant_admin_events ("
                "tenant_id, organization_id, event_kind, performed_by, "
                "performed_by_provenance) VALUES (:t, :o, 'tenant_reinstated', 'op', :prov)"
            ),
            {"t": b["t"], "o": b["org"], "prov": OPERATOR_PROVENANCE},
        )
    for table in ("admin_role_grants", "admin_actions", "tenant_admin_events"):
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(a["t"])},
                )
                n = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
                assert n == 0
        async with admin_engine.begin() as c:
            await c.execute(text(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY"))
        try:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"),
                        {"t": str(a["t"])},
                    )
                    n = (
                        await conn.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one()
                    assert n >= 1
        finally:
            async with admin_engine.begin() as c:
                await c.execute(text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
                await c.execute(text(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY"))
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(a["t"])},
            )
            nested = await conn.begin_nested()
            with pytest.raises(DBAPIError) as ei:
                await conn.execute(
                    text(
                        "INSERT INTO admin_actions ("
                        "tenant_id, project_id, action_kind, actor_principal, "
                        "actor_provenance, required_role, actor_role, decision, "
                        "ruleset_version) "
                        "VALUES (:t, :p, 'set_autonomy_policy', 'alice', "
                        "'request_authenticated', 'tenant_admin', 'tenant_admin', "
                        "'allowed', :rs)"
                    ),
                    {"t": b["t"], "p": b["p"], "rs": RULESET_VERSION},
                )
            assert "admin_actions" in str(ei.value).lower()
            await nested.rollback()


@pytest.mark.db
async def test_a_service_writer_audit_and_frozen(db_session, admin_engine):
    from app.admin.policy_admin import apply_policy_change
    from app.admin.tenant_admin import grant_admin_role, reinstate_tenant, suspend_tenant
    from app.audit import verify_chain
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.readiness import ReadinessRepository

    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    ctx = TenantContext(
        w["t1"], actor=AuthenticatedActor(subject="alice", actor_type="service")
    )
    before_a5 = (await ProductionAutonomyRepository(db_session, ctx).evaluate(w["p1"])).to_dict()
    before_r = (await ReadinessRepository(db_session, ctx).evaluate(w["p1"])).to_dict()
    none = TenantContext(
        w["t1"], actor=AuthenticatedActor(subject="nobody", actor_type="service")
    )
    refused = await apply_policy_change(
        db_session,
        none,
        project_id=w["p1"],
        action_kind="set_autonomy_policy",
        autonomy_level=2,
    )
    assert refused.decision.decision == "refused_no_grant"
    assert refused.autonomy_policy_id is None
    await grant_admin_role(
        db_session,
        tenant_id=w["t1"],
        principal_subject="alice",
        admin_role="tenant_admin",
        performed_by="op",
    )
    allowed = await apply_policy_change(
        db_session,
        ctx,
        project_id=w["p1"],
        action_kind="set_autonomy_policy",
        autonomy_level=2,
        overrides={"run_tests": {"allow": False}},
    )
    assert allowed.autonomy_policy_id is not None
    assert allowed.admin_policy_change_id is not None
    await suspend_tenant(db_session, tenant_id=w["t1"], performed_by="op")
    await reinstate_tenant(db_session, tenant_id=w["t1"], performed_by="op")
    after_a5 = (await ProductionAutonomyRepository(db_session, ctx).evaluate(w["p1"])).to_dict()
    after_r = (await ReadinessRepository(db_session, ctx).evaluate(w["p1"])).to_dict()
    assert after_a5["a5_satisfied"] == before_a5["a5_satisfied"]
    assert after_a5["can_go_live_autonomously"] is False
    assert after_a5["ruleset_version"] == before_a5["ruleset_version"]
    assert [g["status"] for g in after_a5["gates"]] == [g["status"] for g in before_a5["gates"]]
    assert after_r["readiness_level"] == before_r["readiness_level"]
    assert after_r["ruleset_version"] == before_r["ruleset_version"]
    actions = (
        await db_session.execute(
            text(
                "SELECT action, payload FROM audit_logs "
                "WHERE action IN ('admin_action.recorded', 'admin_policy_change.recorded')"
            )
        )
    ).all()
    names = {row[0] for row in actions}
    assert "admin_action.recorded" in names
    assert "admin_policy_change.recorded" in names
    blob = str(actions).lower()
    assert "false" not in blob or "allow" not in blob
    assert "sha256:" not in blob
    assert "uaidk_" not in blob
    verified = await verify_chain(db_session)
    assert verified["ok"] is True
