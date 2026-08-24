"""Slice 63 policy-write lock probes (§5.2.a and §5.2.a.1)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.admin.policy_sql import writer_create_sql
from tests.admin_lock_support import (
    GUARD,
    action as _action,
    as_app as _as_app,
    assert_priv_cycle,
    disable_rls as _disable_rls,
    enable_rls as _enable_rls,
    grant as _grant,
    guc as _guc,
    harm_in_savepoint as _harm_in_savepoint,
    policy as _policy,
    restore_writer as _restore_writer,
    seed_committed_project,
    tighten_relax_case as _tighten_relax_case,
)
from tests.admin_support import call_writer, seed_admin_world, set_trigger


@pytest.mark.db
async def test_p_writer_requires_allowed_action_reachable(db_session):
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"], role="tenant_operator")
    await _policy(db_session, w["t1"], w["p1"])
    action = await _action(
        db_session,
        w["t1"],
        w["p1"],
        decision="refused_insufficient_role",
        role="tenant_operator",
    )
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    await db_session.execute(text(writer_create_sql(omit_allowed=True)))

    async def _harm() -> None:
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))
        level = (
            await db_session.execute(
                text("SELECT autonomy_level FROM autonomy_policies WHERE project_id=:p"),
                {"p": w["p1"]},
            )
        ).scalar_one()
        chg = (
            await db_session.execute(
                text("SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a"),
                {"a": action},
            )
        ).scalar_one()
        assert level == 4 and chg == 1

    await _harm_in_savepoint(db_session, _harm)
    await _restore_writer(db_session)
    with pytest.raises(DBAPIError, match="admin_action_not_allowed"):
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=5, overrides="{}"
        ))


@pytest.mark.db
async def test_p_writer_requires_allowed_action_own_reason(db_session):
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"], role="tenant_operator")
    await _policy(db_session, w["t1"], w["p1"])
    action = await _action(
        db_session,
        w["t1"],
        w["p1"],
        decision="refused_insufficient_role",
        role="tenant_operator",
    )
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    with pytest.raises(DBAPIError, match="admin_action_not_allowed") as ei:
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))
    assert ei.value.orig.sqlstate == "P0001"
    await _restore_writer(db_session)
    with pytest.raises(DBAPIError, match="admin_action_not_allowed"):
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))


@pytest.mark.db
async def test_p_writer_requires_policy_kind_reachable(db_session):
    """Setup drops kind + required-role CHECKs so a non-policy kind can be inserted."""
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    await _policy(db_session, w["t1"], w["p1"])
    await db_session.execute(text("ALTER TABLE admin_actions DROP CONSTRAINT ck_admin_actions_kind_valid"))
    await db_session.execute(
        text("ALTER TABLE admin_actions DROP CONSTRAINT ck_admin_actions_required_role_bound")
    )
    action = await _action(
        db_session, w["t1"], w["p1"], kind="not_a_policy_kind", required="tenant_admin"
    )
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    await db_session.execute(text(writer_create_sql(omit_kind=True)))

    async def _harm() -> None:
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))
        chg = (
            await db_session.execute(
                text("SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a"),
                {"a": action},
            )
        ).scalar_one()
        assert chg == 1

    await _harm_in_savepoint(db_session, _harm)
    await _restore_writer(db_session)
    with pytest.raises(DBAPIError, match="admin_action_not_policy_kind"):
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))


@pytest.mark.db
async def test_p_writer_requires_policy_kind_own_reason(db_session):
    """Neighbour (ledger guard) disabled; writer kind clause stays enabled."""
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    await _policy(db_session, w["t1"], w["p1"])
    await db_session.execute(text("ALTER TABLE admin_actions DROP CONSTRAINT ck_admin_actions_kind_valid"))
    await db_session.execute(
        text("ALTER TABLE admin_actions DROP CONSTRAINT ck_admin_actions_required_role_bound")
    )
    action = await _action(
        db_session, w["t1"], w["p1"], kind="not_a_policy_kind", required="tenant_admin"
    )
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    with pytest.raises(DBAPIError, match="admin_action_not_policy_kind") as ei:
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))
    assert ei.value.orig.sqlstate == "P0001"
    await _restore_writer(db_session)


@pytest.mark.db
async def test_p_writer_guc_unset_reachable(db_session):
    """RLS on the three tables is disabled in setup; neighbour is RLS, not the ledger trigger."""
    w = await seed_admin_world(db_session)
    await _grant(db_session, w["t1"])
    await _policy(db_session, w["t1"], w["p1"])
    action = await _action(db_session, w["t1"], w["p1"])
    await _disable_rls(db_session)
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    await db_session.execute(text(writer_create_sql(guc_fallback=True)))

    async def _harm() -> None:
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))
        chg = (
            await db_session.execute(
                text("SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a"),
                {"a": action},
            )
        ).scalar_one()
        assert chg == 1

    await _harm_in_savepoint(db_session, _harm)
    await db_session.execute(text(writer_create_sql()))
    await _enable_rls(db_session)
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=True)
    with pytest.raises(DBAPIError, match="tenant_guc_unset"):
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))


@pytest.mark.db
async def test_p_writer_guc_unset_own_reason(db_session):
    w = await seed_admin_world(db_session)
    await _grant(db_session, w["t1"])
    await _policy(db_session, w["t1"], w["p1"])
    action = await _action(db_session, w["t1"], w["p1"])
    await _disable_rls(db_session)
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    with pytest.raises(DBAPIError, match="tenant_guc_unset") as ei:
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))
    assert ei.value.orig.sqlstate == "P0001"
    await _enable_rls(db_session)
    await _restore_writer(db_session)
    force = (
        await db_session.execute(
            text(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                "WHERE relname = 'autonomy_policies'"
            )
        )
    ).scalar_one()
    assert force is True
    with pytest.raises(DBAPIError, match="tenant_guc_unset"):
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=4, overrides="{}"
        ))


@pytest.mark.db
async def test_p_writer_no_existing_policy_reachable(db_session):
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    action = await _action(db_session, w["t1"], w["p1"], kind="tighten_autonomy_overrides")
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    await db_session.execute(
        text(writer_create_sql(omit_no_existing=True, omit_tighten_level=True))
    )

    async def _harm() -> None:
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=2,
            overrides='{"run_tests":{"allow":false}}',
        ))
        pol = (
            await db_session.execute(
                text("SELECT count(*) FROM autonomy_policies WHERE project_id=:p"),
                {"p": w["p1"]},
            )
        ).scalar_one()
        chg = (
            await db_session.execute(
                text(
                    "SELECT previous_autonomy_level FROM admin_policy_changes "
                    "WHERE admin_action_id=:a"
                ),
                {"a": action},
            )
        ).scalar_one()
        assert pol == 1 and chg is None

    await _harm_in_savepoint(db_session, _harm)
    await _restore_writer(db_session)
    with pytest.raises(DBAPIError, match="no_existing_policy"):
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=2,
            overrides='{"run_tests":{"allow":false}}',
        ))


@pytest.mark.db
async def test_p_writer_no_existing_policy_own_reason(db_session):
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    action = await _action(db_session, w["t1"], w["p1"], kind="tighten_autonomy_overrides")
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    await db_session.execute(text(writer_create_sql(omit_tighten_level=True)))
    with pytest.raises(DBAPIError, match="no_existing_policy") as ei:
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=2,
            overrides='{"run_tests":{"allow":false}}',
        ))
    assert ei.value.orig.sqlstate == "P0001"
    await _restore_writer(db_session)
    with pytest.raises(DBAPIError, match="no_existing_policy"):
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=2,
            overrides='{"run_tests":{"allow":false}}',
        ))


@pytest.mark.db
async def test_p_tighten_changes_level_reachable(db_session):
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    await _policy(db_session, w["t1"], w["p1"], level=2)
    action = await _action(db_session, w["t1"], w["p1"], kind="tighten_autonomy_overrides")
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    await db_session.execute(text(writer_create_sql(omit_tighten_level=True)))

    async def _harm() -> None:
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=3,
            overrides='{"run_tests":{"allow":false}}',
        ))
        row = (
            await db_session.execute(
                text(
                    "SELECT p.autonomy_level, c.previous_autonomy_level, c.new_autonomy_level "
                    "FROM autonomy_policies p JOIN admin_policy_changes c "
                    "ON c.autonomy_policy_id = p.id WHERE c.admin_action_id=:a"
                ),
                {"a": action},
            )
        ).one()
        assert row == (3, 2, 3)

    await _harm_in_savepoint(db_session, _harm)
    await _restore_writer(db_session)
    with pytest.raises(DBAPIError, match="tighten_may_not_change_level"):
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=3,
            overrides='{"run_tests":{"allow":false}}',
        ))
    stored = (
        await db_session.execute(
            text("SELECT autonomy_level FROM autonomy_policies WHERE project_id=:p"),
            {"p": w["p1"]},
        )
    ).scalar_one()
    assert stored == 2


@pytest.mark.db
async def test_p_tighten_changes_level_own_reason(db_session):
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    await _policy(db_session, w["t1"], w["p1"], level=2)
    action = await _action(db_session, w["t1"], w["p1"], kind="tighten_autonomy_overrides")
    await set_trigger(db_session, "admin_policy_changes", GUARD, enabled=False)
    with pytest.raises(DBAPIError, match="tighten_may_not_change_level") as ei:
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=3,
            overrides='{"run_tests":{"allow":false}}',
        ))
    assert ei.value.orig.sqlstate == "P0001"
    stored = (
        await db_session.execute(
            text("SELECT autonomy_level FROM autonomy_policies WHERE project_id=:p"),
            {"p": w["p1"]},
        )
    ).scalar_one()
    assert stored == 2
    await _restore_writer(db_session)
    with pytest.raises(DBAPIError, match="tighten_may_not_change_level"):
        await _as_app(db_session, lambda: call_writer(
            db_session,
            action_id=action,
            project_id=w["p1"],
            level=3,
            overrides='{"run_tests":{"allow":false}}',
        ))


@pytest.mark.db
async def test_p_writer_spends_action_atomically(db_session):
    w = await seed_admin_world(db_session)
    await _guc(db_session, w["t1"])
    await _grant(db_session, w["t1"])
    await _policy(db_session, w["t1"], w["p1"], level=1, overrides="{}")
    action = await _action(db_session, w["t1"], w["p1"])
    await _as_app(db_session, lambda: call_writer(
        db_session, action_id=action, project_id=w["p1"], level=2, overrides="{}"
    ))
    with pytest.raises(DBAPIError, match="admin_action_already_spent"):
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=3, overrides="{}"
        ))
    level = (
        await db_session.execute(
            text("SELECT autonomy_level FROM autonomy_policies WHERE project_id=:p"),
            {"p": w["p1"]},
        )
    ).scalar_one()
    chg = (
        await db_session.execute(
            text("SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a"),
            {"a": action},
        )
    ).scalar_one()
    assert level == 2 and chg == 1

    async def _replay() -> None:
        await db_session.execute(
            text(
                "ALTER TABLE public.admin_policy_changes "
                "DROP CONSTRAINT uq_admin_policy_changes_action"
            )
        )
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=3, overrides="{}"
        ))
        chg2 = (
            await db_session.execute(
                text("SELECT count(*) FROM admin_policy_changes WHERE admin_action_id=:a"),
                {"a": action},
            )
        ).scalar_one()
        assert chg2 == 2

    await _harm_in_savepoint(db_session, _replay)
    present = (
        await db_session.execute(
            text(
                "SELECT 1 FROM pg_constraint WHERE conname = 'uq_admin_policy_changes_action'"
            )
        )
    ).scalar_one()
    assert present == 1
    with pytest.raises(DBAPIError, match="admin_action_already_spent"):
        await _as_app(db_session, lambda: call_writer(
            db_session, action_id=action, project_id=w["p1"], level=3, overrides="{}"
        ))


@pytest.mark.db
async def test_p_tighten_relax_empty_map(db_session):
    await _tighten_relax_case(
        db_session,
        stored='{"run_tests":{"allow":false}}',
        new="{}",
    )


@pytest.mark.db
async def test_p_tighten_relax_drops_disable(db_session):
    await _tighten_relax_case(
        db_session,
        stored='{"run_tests":{"allow":false}}',
        new='{"run_tests":{"min_level":3}}',
    )


@pytest.mark.db
async def test_p_tighten_relax_lowers_min_level(db_session):
    await _tighten_relax_case(
        db_session,
        stored='{"deploy_staging":{"min_level":4}}',
        new='{"deploy_staging":{"min_level":3}}',
    )


@pytest.mark.db
async def test_p_priv_autonomy_policies_insert(rls_engine, admin_engine):
    tenant, project = await seed_committed_project(admin_engine, prefix="PrivOrg")
    await assert_priv_cycle(
        rls_engine,
        admin_engine,
        tenant=tenant,
        stmt=text(
            "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level, overrides) "
            "VALUES (:t, :p, 2, '{}'::jsonb)"
        ),
        params={"t": tenant, "p": project},
        priv="INSERT",
    )


@pytest.mark.db
async def test_p_priv_autonomy_policies_update(rls_engine, admin_engine):
    tenant, project = await seed_committed_project(
        admin_engine, prefix="PrivUOrg", with_policy=True
    )
    await assert_priv_cycle(
        rls_engine,
        admin_engine,
        tenant=tenant,
        stmt=text("UPDATE autonomy_policies SET autonomy_level=5 WHERE project_id=:p"),
        params={"p": project},
        priv="UPDATE",
    )
