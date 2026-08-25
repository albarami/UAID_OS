"""Slice 83 commit-9: A2 independent-insert barriers (first sixteen unregistered leaves)."""

from __future__ import annotations

import uuid

import pytest

from app.tenancy import TenantContext
from tests.slice83_a2_support import (
    assert_a2_green,
    assert_preseed_breaks_green,
    candidate_writer,
    category_writer,
    commit_writer,
    cost_writer,
    documents_writer,
    grant_writer,
    projects_writer,
    race_runtime,
    skills_writer,
)
from tests.slice83_support import seed_org_tenant_project, two_admin_writers

pytestmark = pytest.mark.db


async def test_a2_projects_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    slug = f"s83-{uuid.uuid4().hex[:10]}"
    ctx = TenantContext(world["tenant"])
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=projects_writer(ctx, slug),
        count_sql="SELECT count(*) FROM projects WHERE tenant_id=:t AND slug=:s",
        count_params={"t": world["tenant"], "s": slug},
    )
    assert_a2_green(result, "uq_projects_tenant_id_slug")
    print("A2-PROJECTS-GREEN", result.unique_row_count)


async def test_a2_projects_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    slug = f"s83-{uuid.uuid4().hex[:10]}"
    ctx = TenantContext(world["tenant"])
    await commit_writer(rls_engine, world["tenant"], projects_writer(ctx, slug))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=projects_writer(ctx, slug),
            count_sql="SELECT count(*) FROM projects WHERE tenant_id=:t AND slug=:s",
            count_params={"t": world["tenant"], "s": slug},
        ),
        "uq_projects_tenant_id_slug",
    )
    print("A2-PROJECTS-MUT")


async def test_a2_skills_green(admin_engine):
    key = f"s83_{uuid.uuid4().hex[:12]}"
    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level="READ COMMITTED",
        writer=skills_writer(key),
        count_sql="SELECT count(*) FROM skills WHERE key=:k",
        count_params={"k": key},
    )
    assert_a2_green(result, "uq_skills_key")
    print("A2-SKILLS-GREEN", result.unique_row_count)


async def test_a2_skills_mutation(admin_engine):
    key = f"s83_{uuid.uuid4().hex[:12]}"
    await commit_writer(admin_engine, None, skills_writer(key))
    await assert_preseed_breaks_green(
        lambda: two_admin_writers(
            admin_engine=admin_engine,
            isolation_level="READ COMMITTED",
            writer=skills_writer(key),
            count_sql="SELECT count(*) FROM skills WHERE key=:k",
            count_params={"k": key},
        ),
        "uq_skills_key",
    )
    print("A2-SKILLS-MUT")


async def test_a2_admin_role_grants_green(admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    principal = f"s83-{uuid.uuid4().hex[:10]}@example.test"
    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level="READ COMMITTED",
        writer=grant_writer(world["tenant"], principal),
        count_sql=(
            "SELECT count(*) FROM admin_role_grants WHERE tenant_id=:t "
            "AND principal_subject=:p AND admin_role='tenant_viewer'"
        ),
        count_params={"t": world["tenant"], "p": principal},
    )
    assert_a2_green(result, "uq_admin_role_grants_tenant_id_principal_subject_admin_role")
    print("A2-GRANTS-GREEN", result.unique_row_count)


async def test_a2_admin_role_grants_mutation(admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    principal = f"s83-{uuid.uuid4().hex[:10]}@example.test"
    await commit_writer(admin_engine, None, grant_writer(world["tenant"], principal))
    await assert_preseed_breaks_green(
        lambda: two_admin_writers(
            admin_engine=admin_engine,
            isolation_level="READ COMMITTED",
            writer=grant_writer(world["tenant"], principal),
            count_sql=(
                "SELECT count(*) FROM admin_role_grants WHERE tenant_id=:t "
                "AND principal_subject=:p AND admin_role='tenant_viewer'"
            ),
            count_params={"t": world["tenant"], "p": principal},
        ),
        "uq_admin_role_grants_tenant_id_principal_subject_admin_role",
    )
    print("A2-GRANTS-MUT")


async def test_a2_documents_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    body = f"s83 document {uuid.uuid4().hex}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=documents_writer(ctx, world["project"], body),
        count_sql=(
            "SELECT count(*) FROM documents WHERE tenant_id=:t AND project_id=:p AND content=:c"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "c": body},
    )
    assert_a2_green(result, "uq_documents_content", reconciles=True)
    print("A2-DOCS-GREEN", result.unique_row_count)


async def test_a2_documents_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    body = f"s83 document {uuid.uuid4().hex}"
    await commit_writer(rls_engine, world["tenant"], documents_writer(ctx, world["project"], body))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=documents_writer(ctx, world["project"], body),
            count_sql=(
                "SELECT count(*) FROM documents WHERE tenant_id=:t AND project_id=:p AND content=:c"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "c": body},
        ),
        "uq_documents_content",
        reconciles=True,
    )
    print("A2-DOCS-MUT")


async def test_a2_cost_events_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    ref = f"s83-cost-{uuid.uuid4().hex[:12]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=cost_writer(ctx, world["project"], ref),
        count_sql=(
            "SELECT count(*) FROM cost_events WHERE tenant_id=:t AND source_system='s83' "
            "AND external_ref=:r"
        ),
        count_params={"t": world["tenant"], "r": ref},
    )
    assert_a2_green(result, "uq_cost_events_idempotency", reconciles=True)
    print("A2-COST-GREEN", result.unique_row_count)


async def test_a2_cost_events_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    ref = f"s83-cost-{uuid.uuid4().hex[:12]}"
    await commit_writer(rls_engine, world["tenant"], cost_writer(ctx, world["project"], ref))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=cost_writer(ctx, world["project"], ref),
            count_sql=(
                "SELECT count(*) FROM cost_events WHERE tenant_id=:t AND source_system='s83' "
                "AND external_ref=:r"
            ),
            count_params={"t": world["tenant"], "r": ref},
        ),
        "uq_cost_events_idempotency",
        reconciles=True,
    )
    print("A2-COST-MUT")


async def test_a2_intake_categories_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=category_writer(ctx, world["project"]),
        count_sql=(
            "SELECT count(*) FROM intake_categories WHERE tenant_id=:t AND project_id=:p "
            "AND category='human_approval_policy'"
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a2_green(result, "uq_intake_categories_cat")
    print("A2-CATS-GREEN", result.unique_row_count)


async def test_a2_intake_categories_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    await commit_writer(rls_engine, world["tenant"], category_writer(ctx, world["project"]))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=category_writer(ctx, world["project"]),
            count_sql=(
                "SELECT count(*) FROM intake_categories WHERE tenant_id=:t AND project_id=:p "
                "AND category='human_approval_policy'"
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        ),
        "uq_intake_categories_cat",
    )
    print("A2-CATS-MUT")


async def test_a2_release_candidates_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    ref = f"rel-{uuid.uuid4().hex[:10]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=candidate_writer(ctx, world["project"], ref),
        count_sql=(
            "SELECT count(*) FROM release_candidates WHERE tenant_id=:t AND project_id=:p "
            "AND release_ref=:r"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "r": ref},
    )
    assert_a2_green(result, "uq_release_candidates_ref")
    print("A2-RC-GREEN", result.unique_row_count)


async def test_a2_release_candidates_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    ref = f"rel-{uuid.uuid4().hex[:10]}"
    await commit_writer(rls_engine, world["tenant"], candidate_writer(ctx, world["project"], ref))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=candidate_writer(ctx, world["project"], ref),
            count_sql=(
                "SELECT count(*) FROM release_candidates WHERE tenant_id=:t AND project_id=:p "
                "AND release_ref=:r"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "r": ref},
        ),
        "uq_release_candidates_ref",
    )
    print("A2-RC-MUT")
