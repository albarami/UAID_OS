"""Slice 1b — Row-Level Security (INV-5) proofs.

All behavioral proofs use the NON-SUPERUSER ``uaid_app`` runtime connection
(``rls_engine``); seeding is done with admin creds (``admin_engine``). Plus
catalog/metadata enforcement: RLS enabled+forced, policies present, and the
``uaid_app`` role is non-superuser / non-bypassrls / not a table owner.
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.repositories.projects import ProjectRepository
from app.tenancy import TenantContext, tenant_scope

pytestmark = pytest.mark.db

# Bind the tenant id at execute time; `true` => transaction-local GUC.
_SET_GUC = text("SELECT set_config('app.current_tenant', :tenant, true)")


@pytest_asyncio.fixture
async def seeded(admin_engine):
    """Seed (as admin, bypassing RLS) one org with tenants A/B and a project each."""
    async with admin_engine.begin() as c:
        org_id = (
            await c.execute(
                text(
                    "INSERT INTO organizations (name, slug) VALUES ('RLSOrg','rls-org') "
                    "RETURNING id"
                )
            )
        ).scalar_one()
        tenant_a = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o,'A','rls-a') RETURNING id"
                ),
                {"o": org_id},
            )
        ).scalar_one()
        tenant_b = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o,'B','rls-b') RETURNING id"
                ),
                {"o": org_id},
            )
        ).scalar_one()
        proj_a = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) "
                    "VALUES (:t,'PA','rls-pa') RETURNING id"
                ),
                {"t": tenant_a},
            )
        ).scalar_one()
        proj_b = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) "
                    "VALUES (:t,'PB','rls-pb') RETURNING id"
                ),
                {"t": tenant_b},
            )
        ).scalar_one()
        run_a = (
            await c.execute(
                text(
                    "INSERT INTO project_runs (tenant_id, project_id) VALUES (:t,:p) RETURNING id"
                ),
                {"t": tenant_a, "p": proj_a},
            )
        ).scalar_one()
        run_b = (
            await c.execute(
                text(
                    "INSERT INTO project_runs (tenant_id, project_id) VALUES (:t,:p) RETURNING id"
                ),
                {"t": tenant_b, "p": proj_b},
            )
        ).scalar_one()

    yield SimpleNamespace(
        org_id=org_id,
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        proj_a=proj_a,
        proj_b=proj_b,
        run_a=run_a,
        run_b=run_b,
    )

    # Teardown (admin): remove all rows for these tenants (incl. repo-created ones).
    async with admin_engine.begin() as c:
        await c.execute(
            text("DELETE FROM project_runs WHERE tenant_id IN (:a,:b)"),
            {"a": tenant_a, "b": tenant_b},
        )
        await c.execute(
            text("DELETE FROM projects WHERE tenant_id IN (:a,:b)"),
            {"a": tenant_a, "b": tenant_b},
        )
        await c.execute(
            text("DELETE FROM tenants WHERE id IN (:a,:b)"), {"a": tenant_a, "b": tenant_b}
        )
        await c.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})


# --- INV-5 behavioral proofs (as uaid_app) ------------------------------------


async def test_inv5_raw_select_isolated_per_tenant(rls_engine, seeded):
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(_SET_GUC, {"tenant": str(seeded.tenant_a)})
            a_ids = (await conn.execute(text("SELECT id FROM projects"))).scalars().all()
        async with conn.begin():
            await conn.execute(_SET_GUC, {"tenant": str(seeded.tenant_b)})
            b_ids = (await conn.execute(text("SELECT id FROM projects"))).scalars().all()
    assert a_ids == [seeded.proj_a]
    assert b_ids == [seeded.proj_b]


async def test_inv5_deny_by_default_without_guc(rls_engine, seeded):
    async with rls_engine.connect() as conn:
        async with conn.begin():
            rows = (await conn.execute(text("SELECT id FROM projects"))).scalars().all()
    assert rows == []


async def test_inv5_cross_tenant_insert_blocked_by_with_check(rls_engine, seeded):
    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(_SET_GUC, {"tenant": str(seeded.tenant_a)})
                # GUC = A, but try to write a row owned by B -> WITH CHECK violation.
                await conn.execute(
                    text(
                        "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'evil','rls-evil')"
                    ),
                    {"t": str(seeded.tenant_b)},
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


async def test_inv5_project_runs_isolated_per_tenant(rls_engine, seeded):
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(_SET_GUC, {"tenant": str(seeded.tenant_a)})
            a_ids = (await conn.execute(text("SELECT id FROM project_runs"))).scalars().all()
        async with conn.begin():
            await conn.execute(_SET_GUC, {"tenant": str(seeded.tenant_b)})
            b_ids = (await conn.execute(text("SELECT id FROM project_runs"))).scalars().all()
    assert a_ids == [seeded.run_a]
    assert b_ids == [seeded.run_b]


async def test_inv5_project_runs_deny_by_default_without_guc(rls_engine, seeded):
    async with rls_engine.connect() as conn:
        async with conn.begin():
            rows = (await conn.execute(text("SELECT id FROM project_runs"))).scalars().all()
    assert rows == []


async def test_inv5_project_runs_cross_tenant_write_blocked(rls_engine, seeded):
    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(_SET_GUC, {"tenant": str(seeded.tenant_a)})
                # GUC = A; write a run for tenant B (valid composite FK to B's
                # project) -> RLS WITH CHECK must reject it.
                await conn.execute(
                    text("INSERT INTO project_runs (tenant_id, project_id) VALUES (:t,:p)"),
                    {"t": str(seeded.tenant_b), "p": str(seeded.proj_b)},
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


async def test_inv5_app_repository_works_when_bound(admin_engine, seeded):
    # Reads (bound via tenant_scope as uaid_app) see only tenant A.
    async with tenant_scope(TenantContext(seeded.tenant_a)) as session:
        repo = ProjectRepository(session, TenantContext(seeded.tenant_a))
        listed = await repo.list()
        assert [p.id for p in listed] == [seeded.proj_a]
        # Writes for the bound tenant pass WITH CHECK.
        created = await repo.create(name="RepoProj", slug="rls-repo-proj")
        await session.flush()
        created_id = created.id

    # Verify (admin) the created row really belongs to tenant A.
    async with admin_engine.connect() as c:
        owner_tenant = (
            await c.execute(text("SELECT tenant_id FROM projects WHERE id = :i"), {"i": created_id})
        ).scalar_one()
    assert owner_tenant == seeded.tenant_a


# --- Metadata / catalog enforcement -------------------------------------------


async def test_rls_enabled_and_forced_on_tenant_tables(admin_engine):
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('projects','project_runs')"
                )
            )
        ).all()
    by = {r[0]: (r[1], r[2]) for r in rows}
    assert by["projects"] == (True, True)
    assert by["project_runs"] == (True, True)


async def test_tenant_isolation_policies_are_correct(admin_engine):
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT tablename, policyname, cmd, qual, with_check FROM pg_policies "
                    "WHERE tablename IN ('projects','project_runs')"
                )
            )
        ).all()
    by_table = {r[0]: r for r in rows}
    for table in ("projects", "project_runs"):
        assert table in by_table, f"no policy on {table}"
        _, policyname, cmd, qual, with_check = by_table[table]
        assert policyname == "tenant_isolation"
        assert cmd == "ALL"
        assert qual is not None
        assert with_check is not None
        for expr in (qual, with_check):
            assert "tenant_id" in expr
            assert "current_setting" in expr
            assert "app.current_tenant" in expr


async def test_uaid_app_role_is_non_superuser_non_bypassrls(admin_engine):
    async with admin_engine.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcanlogin, rolcreatedb, "
                    "rolcreaterole, rolreplication FROM pg_roles WHERE rolname = 'uaid_app'"
                )
            )
        ).one()
    rolsuper, rolbypassrls, rolcanlogin, rolcreatedb, rolcreaterole, rolreplication = row
    assert rolsuper is False
    assert rolbypassrls is False
    assert rolcanlogin is True
    assert rolcreatedb is False
    assert rolcreaterole is False
    assert rolreplication is False


async def test_uaid_app_is_not_table_owner(admin_engine):
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT tablename, tableowner FROM pg_tables "
                    "WHERE tablename IN ('projects','project_runs')"
                )
            )
        ).all()
    owners = {r[0]: r[1] for r in rows}
    assert owners["projects"] != "uaid_app"
    assert owners["project_runs"] != "uaid_app"
