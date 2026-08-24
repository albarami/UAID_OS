"""Slice 63 policy-change and grant lifecycle probes (§5.2.d)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.admin.rbac import OPERATOR_PROVENANCE
from tests.admin_support import (
    in_savepoint,
    insert_action,
    insert_grant,
    seed_admin_world,
    set_guc,
    set_trigger,
    trigger_state,
)

_GUARD = "admin_policy_changes_guard"
_GRANT_GUARD = "admin_role_grants_guard"


async def _policy(session, tenant_id, project_id, level=3) -> object:
    return (
        await session.execute(
            text(
                "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level) "
                "VALUES (:t, :p, :l) RETURNING id"
            ),
            {"t": tenant_id, "p": project_id, "l": level},
        )
    ).scalar_one()


async def _change(session, tenant_id, project_id, action_id, policy_id, previous, new):
    await in_savepoint(
        session,
        lambda: session.execute(
            text(
                "INSERT INTO admin_policy_changes ("
                "tenant_id, project_id, admin_action_id, autonomy_policy_id, "
                "previous_autonomy_level, new_autonomy_level, override_key_count) "
                "VALUES (:t, :p, :a, :pol, :prev, :new, 0)"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "a": action_id,
                "pol": policy_id,
                "prev": previous,
                "new": new,
            },
        ),
    )


@pytest.mark.db
async def test_p_change_refused_action(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_operator")
    pol = await _policy(db_session, w["t1"], w["p1"], level=3)
    action = await insert_action(
        db_session,
        w["t1"],
        w["p1"],
        decision="refused_insufficient_role",
        role="tenant_operator",
    )
    with pytest.raises(DBAPIError, match="admin_policy_change_action_not_allowed"):
        await _change(db_session, w["t1"], w["p1"], action, pol, 3, 3)
    await set_trigger(db_session, "admin_policy_changes", _GUARD, enabled=False)
    await _change(db_session, w["t1"], w["p1"], action, pol, 3, 3)
    await set_trigger(db_session, "admin_policy_changes", _GUARD, enabled=True)
    assert await trigger_state(db_session, _GUARD) == "O"


@pytest.mark.db
async def test_p_change_level_mismatch(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    pol = await _policy(db_session, w["t1"], w["p1"], level=3)
    action = await insert_action(db_session, w["t1"], w["p1"])
    with pytest.raises(DBAPIError, match="admin_policy_change_level_mismatch"):
        await _change(db_session, w["t1"], w["p1"], action, pol, 3, 2)
    await set_trigger(db_session, "admin_policy_changes", _GUARD, enabled=False)
    await _change(db_session, w["t1"], w["p1"], action, pol, 3, 2)
    await set_trigger(db_session, "admin_policy_changes", _GUARD, enabled=True)


@pytest.mark.db
async def test_p_change_tighten_level_moved(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    pol = await _policy(db_session, w["t1"], w["p1"], level=3)
    action = await insert_action(
        db_session, w["t1"], w["p1"], kind="tighten_autonomy_overrides"
    )
    with pytest.raises(DBAPIError, match="admin_policy_change_tighten_level_moved"):
        await _change(db_session, w["t1"], w["p1"], action, pol, 2, 3)
    await set_trigger(db_session, "admin_policy_changes", _GUARD, enabled=False)
    await _change(db_session, w["t1"], w["p1"], action, pol, 2, 3)
    await set_trigger(db_session, "admin_policy_changes", _GUARD, enabled=True)


@pytest.mark.db
async def test_p_grant_insert_status(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError, match="grant_must_be_born_active"):
        await in_savepoint(
            db_session,
            lambda: db_session.execute(
                text(
                    "INSERT INTO admin_role_grants ("
                    "tenant_id, principal_subject, admin_role, status, "
                    "granted_by, granted_by_provenance) "
                    "VALUES (:t, 'bob', 'tenant_admin', 'revoked', 'op', :prov)"
                ),
                {"t": w["t1"], "prov": OPERATOR_PROVENANCE},
            ),
        )
    await set_trigger(db_session, "admin_role_grants", _GRANT_GUARD, enabled=False)
    await db_session.execute(
        text(
            "INSERT INTO admin_role_grants ("
            "tenant_id, principal_subject, admin_role, status, "
            "granted_by, granted_by_provenance) "
            "VALUES (:t, 'bob', 'tenant_admin', 'revoked', 'op', :prov)"
        ),
        {"t": w["t1"], "prov": OPERATOR_PROVENANCE},
    )
    await set_trigger(db_session, "admin_role_grants", _GRANT_GUARD, enabled=True)
    assert await trigger_state(db_session, _GRANT_GUARD) == "O"
    with pytest.raises(DBAPIError, match="grant_must_be_born_active"):
        await in_savepoint(
            db_session,
            lambda: db_session.execute(
                text(
                    "INSERT INTO admin_role_grants ("
                    "tenant_id, principal_subject, admin_role, status, "
                    "granted_by, granted_by_provenance) "
                    "VALUES (:t, 'carol', 'tenant_admin', 'revoked', 'op', :prov)"
                ),
                {"t": w["t1"], "prov": OPERATOR_PROVENANCE},
            ),
        )


@pytest.mark.db
async def test_p_grant_update_widen(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    gid = await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    await db_session.execute(
        text("UPDATE admin_role_grants SET status='revoked' WHERE id=:i"),
        {"i": gid},
    )
    with pytest.raises(DBAPIError, match="grant_status_one_way"):
        await in_savepoint(
            db_session,
            lambda: db_session.execute(
                text("UPDATE admin_role_grants SET status='active' WHERE id=:i"),
                {"i": gid},
            ),
        )
    gid2 = await insert_grant(db_session, w["t1"], "dave", "tenant_operator")
    with pytest.raises(DBAPIError, match="grant_identity_immutable"):
        await in_savepoint(
            db_session,
            lambda: db_session.execute(
                text("UPDATE admin_role_grants SET admin_role='tenant_admin' WHERE id=:i"),
                {"i": gid2},
            ),
        )
    await set_trigger(db_session, "admin_role_grants", _GRANT_GUARD, enabled=False)
    await db_session.execute(
        text("UPDATE admin_role_grants SET status='active' WHERE id=:i"),
        {"i": gid},
    )
    await db_session.execute(
        text("UPDATE admin_role_grants SET admin_role='tenant_admin' WHERE id=:i"),
        {"i": gid2},
    )
    await set_trigger(db_session, "admin_role_grants", _GRANT_GUARD, enabled=True)
    assert await trigger_state(db_session, _GRANT_GUARD) == "O"
