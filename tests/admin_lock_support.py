"""Helpers for Slice 63 policy-write lock probes. Not a production path."""

from __future__ import annotations

from sqlalchemy import text

from app.admin.policy_sql import WRITER_BODY, writer_create_sql
from app.admin.rbac import OPERATOR_PROVENANCE, RULESET_VERSION
from tests.admin_support import (
    as_uaid_app,
    call_writer,
    function_body,
    seed_admin_world,
    set_trigger,
    trigger_state,
)

GUARD = "admin_policy_changes_guard"


async def guc(session, tenant_id) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


async def grant(session, tenant_id, principal="alice", role="tenant_admin") -> None:
    await session.execute(
        text(
            "INSERT INTO admin_role_grants ("
            "tenant_id, principal_subject, admin_role, status, "
            "granted_by, granted_by_provenance) "
            "VALUES (:t, :p, :r, 'active', 'op', :prov)"
        ),
        {"t": tenant_id, "p": principal, "r": role, "prov": OPERATOR_PROVENANCE},
    )


async def policy(
    session, tenant_id, project_id, level=2, overrides='{"run_tests":{"allow":false}}'
):
    await session.execute(
        text(
            "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level, overrides) "
            "VALUES (:t, :p, :l, CAST(:o AS jsonb))"
        ),
        {"t": tenant_id, "p": project_id, "l": level, "o": overrides},
    )


async def action(
    session,
    tenant_id,
    project_id,
    *,
    kind="set_autonomy_policy",
    decision="allowed",
    role="tenant_admin",
    required=None,
    provenance="request_authenticated",
):
    required = required or (
        "tenant_admin" if kind == "set_autonomy_policy" else "tenant_operator"
    )
    return (
        await session.execute(
            text(
                "INSERT INTO admin_actions ("
                "tenant_id, project_id, action_kind, actor_principal, actor_provenance, "
                "required_role, actor_role, decision, ruleset_version) "
                "VALUES (:t, :p, :k, 'alice', :pr, :req, :ar, :d, :rs) RETURNING id"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "k": kind,
                "pr": provenance,
                "req": required,
                "ar": None
                if decision in ("refused_no_grant", "refused_unauthenticated_actor")
                else role,
                "d": decision,
                "rs": RULESET_VERSION,
            },
        )
    ).scalar_one()


async def as_app(session, coro_factory):
    return await as_uaid_app(session, coro_factory)


async def restore_writer(session) -> None:
    await session.execute(text(writer_create_sql()))
    await set_trigger(session, "admin_policy_changes", GUARD, enabled=True)
    restored = await function_body(session, "admin_write_autonomy_policy")
    assert restored.strip() == WRITER_BODY.strip()
    assert await trigger_state(session, GUARD) == "O"


async def harm_in_savepoint(session, write_and_assert) -> None:
    """Run the reachable write, assert harm, then undo the write (keep DDL)."""
    nested = await session.begin_nested()
    try:
        await write_and_assert()
    finally:
        await nested.rollback()


async def disable_rls(session) -> None:
    for table in ("autonomy_policies", "admin_actions", "admin_policy_changes"):
        await session.execute(text(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY"))
        await session.execute(text(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY"))


async def enable_rls(session) -> None:
    for table in ("autonomy_policies", "admin_actions", "admin_policy_changes"):
        await session.execute(text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        await session.execute(text(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY"))


async def tighten_relax_case(session, *, stored: str, new: str) -> None:
    import json

    w = await seed_admin_world(session)
    await guc(session, w["t1"])
    await grant(session, w["t1"])
    await policy(session, w["t1"], w["p1"], level=2, overrides=stored)
    act = await action(session, w["t1"], w["p1"], kind="tighten_autonomy_overrides")
    from sqlalchemy.exc import DBAPIError
    import pytest

    with pytest.raises(DBAPIError, match="tighten_would_relax_overrides"):
        await as_app(
            session,
            lambda: call_writer(
                session, action_id=act, project_id=w["p1"], level=2, overrides=new
            ),
        )
    await session.execute(text(writer_create_sql(omit_monotonic=True)))
    await as_app(
        session,
        lambda: call_writer(
            session, action_id=act, project_id=w["p1"], level=2, overrides=new
        ),
    )
    got = (
        await session.execute(
            text("SELECT overrides FROM autonomy_policies WHERE project_id=:p"),
            {"p": w["p1"]},
        )
    ).scalar_one()
    assert dict(got) == json.loads(new)
    await restore_writer(session)
    action2 = await action(session, w["t1"], w["p1"], kind="tighten_autonomy_overrides")
    await session.execute(
        text(
            "UPDATE autonomy_policies SET overrides = CAST(:o AS jsonb), autonomy_level=2 "
            "WHERE project_id=:p"
        ),
        {"o": stored, "p": w["p1"]},
    )
    with pytest.raises(DBAPIError, match="tighten_would_relax_overrides"):
        await as_app(
            session,
            lambda: call_writer(
                session, action_id=action2, project_id=w["p1"], level=2, overrides=new
            ),
        )


async def seed_committed_project(admin_engine, *, prefix: str, with_policy: bool = False):
    import uuid

    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES (:n,:s) RETURNING id"),
                {"n": prefix, "s": f"{prefix.lower()}-{sfx}"},
            )
        ).scalar_one()
        tenant = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o,'t',:s) RETURNING id"
                ),
                {"o": org, "s": f"{prefix.lower()}-t-{sfx}"},
            )
        ).scalar_one()
        project = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id"
                ),
                {"t": tenant, "s": f"{prefix.lower()}-p-{sfx}"},
            )
        ).scalar_one()
        if with_policy:
            await c.execute(
                text(
                    "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level) "
                    "VALUES (:t, :p, 2)"
                ),
                {"t": tenant, "p": project},
            )
    return tenant, project


async def assert_priv_cycle(rls_engine, admin_engine, *, tenant, stmt, params, priv: str):
    import pytest
    from sqlalchemy.exc import DBAPIError

    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant)},
            )
            nested = await conn.begin_nested()
            with pytest.raises(DBAPIError) as ei:
                await conn.execute(stmt, params)
            assert ei.value.orig.sqlstate == "42501"
            assert "autonomy_policies" in str(ei.value).lower()
            await nested.rollback()
    async with admin_engine.begin() as c:
        await c.execute(text(f"GRANT {priv} ON public.autonomy_policies TO uaid_app"))
    try:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(tenant)},
                )
                await conn.execute(stmt, params)
    finally:
        async with admin_engine.begin() as c:
            await c.execute(text(f"REVOKE {priv} ON public.autonomy_policies FROM uaid_app"))
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant)},
            )
            nested = await conn.begin_nested()
            with pytest.raises(DBAPIError) as ei:
                await conn.execute(stmt, params)
            assert ei.value.orig.sqlstate == "42501"
            await nested.rollback()
