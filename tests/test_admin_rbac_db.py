"""Slice 63 admin_actions trigger and CHECK probes (§5.2.b / §5.2.c)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import DBAPIError

from tests.admin_support import (
    add_check,
    as_uaid_app,
    drop_check,
    insert_action,
    insert_grant,
    pg_constraint,
    pg_state,
    prove_commits,
    seed_admin_world,
    set_guc,
    set_trigger,
    trigger_state,
)

_GUARD = "admin_actions_guard"


async def _restore(session) -> None:
    await set_trigger(session, "admin_actions", _GUARD, enabled=True)
    assert await trigger_state(session, _GUARD) == "O"


@pytest.mark.db
async def test_p_allow_no_grant(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError, match="no_active_grant_for_recorded_role") as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(db_session, w["t1"], w["p1"]),
        )
    assert pg_state(ei.value) == "P0001"
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    await as_uaid_app(db_session, lambda: insert_action(db_session, w["t1"], w["p1"]))
    await _restore(db_session)
    with pytest.raises(DBAPIError, match="no_active_grant_for_recorded_role"):
        await as_uaid_app(
            db_session,
            lambda: insert_action(db_session, w["t1"], w["p1"]),
        )


@pytest.mark.db
async def test_p_allow_no_grant_as_admin(db_session):
    """The owner role is bound by the trigger, not by RLS."""
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError, match="no_active_grant_for_recorded_role"):
        await insert_action(db_session, w["t1"], w["p1"])
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    await insert_action(db_session, w["t1"], w["p1"])
    await _restore(db_session)
    with pytest.raises(DBAPIError, match="no_active_grant_for_recorded_role"):
        await insert_action(db_session, w["t1"], w["p1"])


@pytest.mark.db
async def test_p_allow_revoked_grant(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    gid = await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    await db_session.execute(
        __import__("sqlalchemy").text(
            "UPDATE admin_role_grants SET status='revoked' WHERE id=:i"
        ),
        {"i": gid},
    )
    with pytest.raises(DBAPIError, match="no_active_grant_for_recorded_role"):
        await as_uaid_app(
            db_session,
            lambda: insert_action(db_session, w["t1"], w["p1"]),
        )
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    await as_uaid_app(db_session, lambda: insert_action(db_session, w["t1"], w["p1"]))
    await _restore(db_session)


@pytest.mark.db
async def test_p_allow_cross_tenant_grant(db_session):
    w = await seed_admin_world(db_session)
    await insert_grant(db_session, w["t2"], "alice", "tenant_admin")
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError, match="no_active_grant_for_recorded_role"):
        await as_uaid_app(
            db_session,
            lambda: insert_action(db_session, w["t1"], w["p1"]),
        )
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    await as_uaid_app(db_session, lambda: insert_action(db_session, w["t1"], w["p1"]))
    await _restore(db_session)


@pytest.mark.db
async def test_p_allow_not_highest_grant(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_operator")
    await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    with pytest.raises(DBAPIError, match="actor_role_is_not_highest_active_grant") as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                kind="tighten_autonomy_overrides",
                role="tenant_operator",
            ),
        )
    assert pg_state(ei.value) == "P0001"
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    await as_uaid_app(
        db_session,
        lambda: insert_action(
            db_session,
            w["t1"],
            w["p1"],
            kind="tighten_autonomy_overrides",
            role="tenant_operator",
        ),
    )
    await _restore(db_session)


@pytest.mark.db
async def test_p_refuse_insufficient_with_higher_grant(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_viewer")
    await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    with pytest.raises(DBAPIError, match="actor_role_is_not_highest_active_grant"):
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_insufficient_role",
                role="tenant_viewer",
            ),
        )
    await drop_check(db_session, "admin_actions", "ck_admin_actions_insufficient_rank")
    with pytest.raises(DBAPIError, match="sufficient_active_grant_exists"):
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_insufficient_role",
                role="tenant_admin",
            ),
        )
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    await prove_commits(
        db_session,
        lambda: as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_insufficient_role",
                role="tenant_admin",
            ),
        ),
    )
    await _restore(db_session)
    await add_check(db_session, "admin_actions", "ck_admin_actions_insufficient_rank")


@pytest.mark.db
async def test_p_refuse_mislabel(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_viewer")
    with pytest.raises(DBAPIError, match="active_grant_exists_for_principal"):
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_no_grant",
                role=None,
            ),
        )
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    await as_uaid_app(
        db_session,
        lambda: insert_action(
            db_session, w["t1"], w["p1"], decision="refused_no_grant", role=None
        ),
    )
    await _restore(db_session)


@pytest.mark.db
async def test_p_allow_insufficient_rank(db_session):
    """Trigger disabled in setup: its rank clause would mask this CHECK."""
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_operator")
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    with pytest.raises(DBAPIError) as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session, w["t1"], w["p1"], role="tenant_operator"
            ),
        )
    assert pg_constraint(ei.value) == "ck_admin_actions_allowed_rank"
    await drop_check(db_session, "admin_actions", "ck_admin_actions_allowed_rank")
    await prove_commits(
        db_session,
        lambda: as_uaid_app(
            db_session,
            lambda: insert_action(db_session, w["t1"], w["p1"], role="tenant_operator"),
        ),
    )
    await add_check(db_session, "admin_actions", "ck_admin_actions_allowed_rank")
    await _restore(db_session)


@pytest.mark.db
async def test_p_check_insufficient_rank(db_session):
    """Trigger disabled in setup so the CHECK is the surviving refusal."""
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    with pytest.raises(DBAPIError) as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                kind="tighten_autonomy_overrides",
                decision="refused_insufficient_role",
                role="tenant_admin",
            ),
        )
    assert pg_constraint(ei.value) == "ck_admin_actions_insufficient_rank"
    await drop_check(db_session, "admin_actions", "ck_admin_actions_insufficient_rank")
    await prove_commits(
        db_session,
        lambda: as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                kind="tighten_autonomy_overrides",
                decision="refused_insufficient_role",
                role="tenant_admin",
            ),
        ),
    )
    await add_check(db_session, "admin_actions", "ck_admin_actions_insufficient_rank")
    await _restore(db_session)


@pytest.mark.db
async def test_p_check_role_presence(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError) as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_no_grant",
                role="tenant_admin",
            ),
        )
    assert pg_constraint(ei.value) == "ck_admin_actions_role_presence"
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=False)
    with pytest.raises(DBAPIError) as ei2:
        await as_uaid_app(
            db_session,
            lambda: insert_action(db_session, w["t1"], w["p1"], role=None),
        )
    assert pg_constraint(ei2.value) == "ck_admin_actions_role_presence"
    await drop_check(db_session, "admin_actions", "ck_admin_actions_role_presence")
    await prove_commits(
        db_session,
        lambda: as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_no_grant",
                role="tenant_admin",
            ),
        ),
    )
    await set_trigger(db_session, "admin_actions", _GUARD, enabled=True)
    with pytest.raises(DBAPIError):
        await as_uaid_app(
            db_session,
            lambda: insert_action(db_session, w["t1"], w["p1"], role=None),
        )
    await add_check(db_session, "admin_actions", "ck_admin_actions_role_presence")
    await _restore(db_session)


@pytest.mark.db
async def test_p_check_provenance_unauth_mislabel(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError) as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_no_grant",
                role=None,
                provenance="caller_supplied_unverified",
            ),
        )
    assert pg_constraint(ei.value) == "ck_admin_actions_provenance_partition"
    await drop_check(db_session, "admin_actions", "ck_admin_actions_provenance_partition")
    await prove_commits(
        db_session,
        lambda: as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_no_grant",
                role=None,
                provenance="caller_supplied_unverified",
            ),
        ),
    )
    await add_check(db_session, "admin_actions", "ck_admin_actions_provenance_partition")


@pytest.mark.db
async def test_p_check_provenance_verified_unauth(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError) as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_unauthenticated_actor",
                role=None,
                provenance="request_authenticated",
            ),
        )
    assert pg_constraint(ei.value) == "ck_admin_actions_provenance_partition"
    await drop_check(db_session, "admin_actions", "ck_admin_actions_provenance_partition")
    await prove_commits(
        db_session,
        lambda: as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                decision="refused_unauthenticated_actor",
                role=None,
                provenance="request_authenticated",
            ),
        ),
    )
    await add_check(db_session, "admin_actions", "ck_admin_actions_provenance_partition")


@pytest.mark.db
async def test_p_required_role_forged(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    await insert_grant(db_session, w["t1"], "alice", "tenant_operator")
    with pytest.raises(DBAPIError) as ei:
        await as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                required="tenant_operator",
                role="tenant_operator",
            ),
        )
    assert pg_constraint(ei.value) == "ck_admin_actions_required_role_bound"
    await drop_check(db_session, "admin_actions", "ck_admin_actions_required_role_bound")
    await prove_commits(
        db_session,
        lambda: as_uaid_app(
            db_session,
            lambda: insert_action(
                db_session,
                w["t1"],
                w["p1"],
                required="tenant_operator",
                role="tenant_operator",
            ),
        ),
    )
    await add_check(db_session, "admin_actions", "ck_admin_actions_required_role_bound")
