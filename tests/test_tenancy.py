"""Tenancy invariant tests (INV-1..INV-4), DB-backed against app_test.

INV-5 (Postgres RLS) is Slice 1b and is not covered here.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Organization, Project, ProjectRun, Tenant
from app.repositories.projects import ProjectRepository
from app.tenancy import CrossTenantError, TenantContext

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def two_tenants(db_session):
    org = Organization(name="Org", slug="org")
    db_session.add(org)
    await db_session.flush()
    ta = Tenant(organization_id=org.id, name="A", slug="a")
    tb = Tenant(organization_id=org.id, name="B", slug="b")
    db_session.add_all([ta, tb])
    await db_session.flush()
    return ta, tb


async def test_migration_created_all_spine_tables(db_session):
    """Proves `alembic upgrade head` built the schema (no create_all)."""
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    names = {row[0] for row in result}
    assert {"organizations", "tenants", "projects", "project_runs"} <= names


async def test_inv1_tenant_id_not_null(db_session, two_tenants):
    db_session.add(Project(tenant_id=None, name="p", slug="p"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_inv2_tenant_id_must_reference_real_tenant(db_session, two_tenants):
    db_session.add(Project(tenant_id=uuid.uuid4(), name="p", slug="p"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_inv3_run_tenant_must_match_its_project(db_session, two_tenants):
    ta, tb = two_tenants
    proj_a = Project(tenant_id=ta.id, name="pa", slug="pa")
    db_session.add(proj_a)
    await db_session.flush()
    # Run references T_a's project but claims to belong to T_b.
    db_session.add(ProjectRun(tenant_id=tb.id, project_id=proj_a.id, status="created"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_inv4_read_is_isolated_per_tenant(db_session, two_tenants):
    ta, tb = two_tenants
    repo_a = ProjectRepository(db_session, TenantContext(ta.id))
    created = await repo_a.create(name="pa", slug="pa")
    await db_session.flush()

    repo_b = ProjectRepository(db_session, TenantContext(tb.id))
    assert await repo_b.list() == []
    assert await repo_b.get(created.id) is None
    assert [p.id for p in await repo_a.list()] == [created.id]


async def test_inv4_cross_tenant_write_is_rejected(db_session, two_tenants):
    ta, tb = two_tenants
    repo_a = ProjectRepository(db_session, TenantContext(ta.id))
    foreign = Project(tenant_id=tb.id, name="x", slug="x")
    with pytest.raises(CrossTenantError):
        await repo_a.add(foreign)


async def test_inv4_requires_explicit_tenant_context(db_session):
    with pytest.raises(CrossTenantError):
        ProjectRepository(db_session, None)
