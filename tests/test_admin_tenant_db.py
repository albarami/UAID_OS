"""Slice 63 tenant-admin event and suspension probes (§5.2.e / §5.2.i)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.guards_sql import RESOLVER_0026_SQL, RESOLVER_0062_SQL, RESOLVER_FN
from app.admin.rbac import OPERATOR_PROVENANCE
from app.main import app
from app.repositories.api_keys import TenantApiKeyRepository, generate_raw_key, hash_key
from tests.admin_support import (
    add_check,
    drop_check,
    in_savepoint,
    insert_grant,
    pg_constraint,
    prove_commits,
    seed_admin_world,
    set_guc,
    set_trigger,
    trigger_state,
)

_GUARD = "tenant_admin_events_guard"
_RESOLVER = "public.resolve_tenant_api_key(text)"


async def _event(
    session,
    tenant_id,
    org_id,
    *,
    kind="role_granted",
    principal="alice",
    role="tenant_admin",
    grant_id=None,
):
    await in_savepoint(
        session,
        lambda: session.execute(
            text(
                "INSERT INTO tenant_admin_events ("
                "tenant_id, organization_id, event_kind, subject_principal, admin_role, "
                "admin_role_grant_id, performed_by, performed_by_provenance) "
                "VALUES (:t, :o, :k, :p, :r, :g, 'op', :prov)"
            ),
            {
                "t": tenant_id,
                "o": org_id,
                "k": kind,
                "p": principal,
                "r": role,
                "g": grant_id,
                "prov": OPERATOR_PROVENANCE,
            },
        ),
    )


@pytest.mark.db
async def test_p_event_principal_mismatch(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    gid = await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    with pytest.raises(DBAPIError) as ei:
        await _event(db_session, w["t1"], w["org"], principal="bob", grant_id=gid)
    assert pg_constraint(ei.value) == "fk_tae_grant_identity"
    await db_session.execute(
        text("ALTER TABLE public.tenant_admin_events DROP CONSTRAINT fk_tae_grant_identity")
    )
    await prove_commits(
        db_session,
        lambda: _event(db_session, w["t1"], w["org"], principal="bob", grant_id=gid),
    )
    await db_session.execute(
        text(
            "ALTER TABLE public.tenant_admin_events ADD CONSTRAINT fk_tae_grant_identity "
            "FOREIGN KEY (admin_role_grant_id, tenant_id, subject_principal, admin_role) "
            "REFERENCES admin_role_grants (id, tenant_id, principal_subject, admin_role) "
            "ON DELETE RESTRICT"
        )
    )


@pytest.mark.db
async def test_p_event_role_mismatch(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    gid = await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    with pytest.raises(DBAPIError) as ei:
        await _event(
            db_session, w["t1"], w["org"], role="tenant_viewer", grant_id=gid
        )
    assert pg_constraint(ei.value) == "fk_tae_grant_identity"
    await db_session.execute(
        text("ALTER TABLE public.tenant_admin_events DROP CONSTRAINT fk_tae_grant_identity")
    )
    await prove_commits(
        db_session,
        lambda: _event(
            db_session, w["t1"], w["org"], role="tenant_viewer", grant_id=gid
        ),
    )


@pytest.mark.db
async def test_p_check_tae_role_shape(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    gid = await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    with pytest.raises(DBAPIError) as ei:
        await _event(db_session, w["t1"], w["org"], role=None, grant_id=gid)
    assert pg_constraint(ei.value) == "ck_tae_role_shape"
    await drop_check(db_session, "tenant_admin_events", "ck_tae_role_shape")
    await prove_commits(
        db_session,
        lambda: _event(db_session, w["t1"], w["org"], role=None, grant_id=gid),
    )
    await add_check(db_session, "tenant_admin_events", "ck_tae_role_shape")


@pytest.mark.db
async def test_p_event_lies(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    with pytest.raises(DBAPIError, match="event_tenant_status_mismatch"):
        await _event(
            db_session, w["t1"], w["org"], kind="tenant_suspended",
            principal=None, role=None, grant_id=None,
        )
    with pytest.raises(DBAPIError, match="event_organization_status_mismatch"):
        await _event(
            db_session, w["t1"], w["org"], kind="organization_suspended",
            principal=None, role=None, grant_id=None,
        )
    await set_trigger(db_session, "tenant_admin_events", _GUARD, enabled=False)
    await _event(
        db_session, w["t1"], w["org"], kind="tenant_suspended",
        principal=None, role=None, grant_id=None,
    )
    await _event(
        db_session, w["t1"], w["org"], kind="organization_suspended",
        principal=None, role=None, grant_id=None,
    )
    await set_trigger(db_session, "tenant_admin_events", _GUARD, enabled=True)
    assert await trigger_state(db_session, _GUARD) == "O"


@pytest.mark.db
async def test_p_event_wrong_org(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    gid = await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    other = (
        await db_session.execute(
            text("INSERT INTO organizations (name, slug) VALUES ('Other', :s) RETURNING id"),
            {"s": f"other-{w['sfx']}"},
        )
    ).scalar_one()
    with pytest.raises(DBAPIError, match="event_organization_mismatch"):
        await _event(db_session, w["t1"], other, grant_id=gid)
    await set_trigger(db_session, "tenant_admin_events", _GUARD, enabled=False)
    await _event(db_session, w["t1"], other, grant_id=gid)
    await set_trigger(db_session, "tenant_admin_events", _GUARD, enabled=True)


@pytest.mark.db
async def test_p_event_role_grant_status(db_session):
    w = await seed_admin_world(db_session)
    await set_guc(db_session, w["t1"])
    gid = await insert_grant(db_session, w["t1"], "alice", "tenant_admin")
    with pytest.raises(DBAPIError, match="event_grant_status_mismatch"):
        await _event(db_session, w["t1"], w["org"], kind="role_revoked", grant_id=gid)
    await set_trigger(db_session, "tenant_admin_events", _GUARD, enabled=False)
    await _event(db_session, w["t1"], w["org"], kind="role_revoked", grant_id=gid)
    await set_trigger(db_session, "tenant_admin_events", _GUARD, enabled=True)


async def _install_resolver(conn, body: str) -> None:
    await conn.execute(text(f"DROP FUNCTION {RESOLVER_FN}"))
    await conn.execute(text(body))
    await conn.execute(text(f"ALTER FUNCTION {_RESOLVER} OWNER TO api_key_resolver"))
    await conn.execute(text(f"REVOKE ALL ON FUNCTION {_RESOLVER} FROM PUBLIC"))
    await conn.execute(text(f"GRANT EXECUTE ON FUNCTION {_RESOLVER} TO uaid_app"))


async def _resolve(conn, raw: str):
    return (
        await conn.execute(
            text("SELECT tenant_id FROM public.resolve_tenant_api_key(:h)"),
            {"h": hash_key(raw)},
        )
    ).scalar_one_or_none()


async def _http(raw: str, project_id) -> tuple[int, bytes, dict]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            f"/api/projects/{project_id}/runs",
            headers={"Authorization": f"Bearer {raw}"},
        )
    return r.status_code, r.content, dict(r.headers)


@pytest.mark.db
async def test_p_suspend_tenant_blocks(admin_engine):
    w_org = None
    w_tenant = None
    w_project = None
    raw = None
    async with admin_engine.begin() as c:
        org = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('Susp', :s) RETURNING id"),
                {"s": f"susp-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        tenant = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o, 't', :s) RETURNING id"
                ),
                {"o": org, "s": f"susp-t-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        project = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P', :s) RETURNING id"
                ),
                {"t": tenant, "s": f"susp-p-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        w_org, w_tenant, w_project = org, tenant, project
    async with AsyncSession(admin_engine, expire_on_commit=False) as s:
        raw, _ = await TenantApiKeyRepository(s).issue(
            tenant_id=w_tenant, label="k", principal_subject="svc", actor_type="service"
        )
        await s.commit()
    async with admin_engine.connect() as c:
        assert await _resolve(c, raw) == w_tenant
    status, _, _ = await _http(raw, w_project)
    assert status == 200
    async with admin_engine.begin() as c:
        await c.execute(
            text("UPDATE tenants SET status='suspended' WHERE id=:t"), {"t": w_tenant}
        )
    async with admin_engine.connect() as c:
        assert await _resolve(c, raw) is None
    status, body, _ = await _http(raw, w_project)
    assert status == 401
    async with admin_engine.begin() as c:
        await _install_resolver(c, RESOLVER_0026_SQL)
    try:
        async with admin_engine.connect() as c:
            assert await _resolve(c, raw) == w_tenant
    finally:
        async with admin_engine.begin() as c:
            await _install_resolver(c, RESOLVER_0062_SQL)
            await c.execute(
                text("GRANT SELECT ON public.tenants, public.organizations TO api_key_resolver")
            )
    async with admin_engine.connect() as c:
        assert await _resolve(c, raw) is None
    _ = w_org


@pytest.mark.db
async def test_p_suspend_org_blocks(admin_engine):
    async with admin_engine.begin() as c:
        org = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('OrgS', :s) RETURNING id"),
                {"s": f"orgs-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        tenant = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o, 't', :s) RETURNING id"
                ),
                {"o": org, "s": f"orgs-t-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        project = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P', :s) RETURNING id"
                ),
                {"t": tenant, "s": f"orgs-p-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
    async with AsyncSession(admin_engine, expire_on_commit=False) as s:
        raw, _ = await TenantApiKeyRepository(s).issue(
            tenant_id=tenant, label="k", principal_subject="svc", actor_type="service"
        )
        await s.commit()
    async with admin_engine.begin() as c:
        await c.execute(
            text("UPDATE organizations SET status='suspended' WHERE id=:o"), {"o": org}
        )
    async with admin_engine.connect() as c:
        assert await _resolve(c, raw) is None
    assert (await _http(raw, project))[0] == 401
    async with admin_engine.begin() as c:
        await _install_resolver(c, RESOLVER_0026_SQL)
    try:
        async with admin_engine.connect() as c:
            assert await _resolve(c, raw) == tenant
    finally:
        async with admin_engine.begin() as c:
            await _install_resolver(c, RESOLVER_0062_SQL)
            await c.execute(
                text("GRANT SELECT ON public.tenants, public.organizations TO api_key_resolver")
            )


@pytest.mark.db
async def test_p_reinstate_restores(admin_engine):
    async with admin_engine.begin() as c:
        org = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('Rein', :s) RETURNING id"),
                {"s": f"rein-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        tenant = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o, 't', :s) RETURNING id"
                ),
                {"o": org, "s": f"rein-t-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        project = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P', :s) RETURNING id"
                ),
                {"t": tenant, "s": f"rein-p-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
    async with AsyncSession(admin_engine, expire_on_commit=False) as s:
        raw, _ = await TenantApiKeyRepository(s).issue(
            tenant_id=tenant, label="k", principal_subject="svc", actor_type="service"
        )
        await s.commit()
    async with admin_engine.begin() as c:
        await c.execute(text("UPDATE tenants SET status='suspended' WHERE id=:t"), {"t": tenant})
    assert (await _http(raw, project))[0] == 401
    async with admin_engine.begin() as c:
        await c.execute(text("UPDATE tenants SET status='active' WHERE id=:t"), {"t": tenant})
    async with admin_engine.connect() as c:
        assert await _resolve(c, raw) == tenant
    assert (await _http(raw, project))[0] == 200


@pytest.mark.db
async def test_p_org_status_check(db_session):
    w = await seed_admin_world(db_session)
    with pytest.raises(DBAPIError) as ei:
        await in_savepoint(
            db_session,
            lambda: db_session.execute(
                text("UPDATE organizations SET status='bogus' WHERE id=:o"),
                {"o": w["org"]},
            ),
        )
    assert pg_constraint(ei.value) == "ck_organizations_status_valid"
    await drop_check(db_session, "organizations", "ck_organizations_status_valid")
    await prove_commits(
        db_session,
        lambda: db_session.execute(
            text("UPDATE organizations SET status='bogus' WHERE id=:o"),
            {"o": w["org"]},
        ),
    )
    await add_check(db_session, "organizations", "ck_organizations_status_valid")
    with pytest.raises(DBAPIError) as ei2:
        await in_savepoint(
            db_session,
            lambda: db_session.execute(
                text("UPDATE organizations SET status='bogus' WHERE id=:o"),
                {"o": w["org"]},
            ),
        )
    assert pg_constraint(ei2.value) == "ck_organizations_status_valid"


@pytest.mark.db
async def test_a_suspend_no_oracle(admin_engine):
    async with admin_engine.begin() as c:
        org = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('Orcl', :s) RETURNING id"),
                {"s": f"orcl-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        tenant = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o, 't', :s) RETURNING id"
                ),
                {"o": org, "s": f"orcl-t-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
        project = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P', :s) RETURNING id"
                ),
                {"t": tenant, "s": f"orcl-p-{__import__('uuid').uuid4().hex[:8]}"},
            )
        ).scalar_one()
    async with AsyncSession(admin_engine, expire_on_commit=False) as s:
        raw, _ = await TenantApiKeyRepository(s).issue(
            tenant_id=tenant, label="k", principal_subject="svc", actor_type="service"
        )
        await s.commit()
    async with admin_engine.begin() as c:
        await c.execute(text("UPDATE tenants SET status='suspended' WHERE id=:t"), {"t": tenant})
    unknown = generate_raw_key()
    a = await _http(raw, project)
    b = await _http(unknown, project)
    assert a[0] == b[0] == 401
    assert a[1] == b[1]
    skip = {"date", "content-length"}
    ah = {k.lower(): v for k, v in a[2].items() if k.lower() not in skip}
    bh = {k.lower(): v for k, v in b[2].items() if k.lower() not in skip}
    assert ah == bh
