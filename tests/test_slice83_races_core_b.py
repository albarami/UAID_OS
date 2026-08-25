"""Slice 83 commit-4 GREEN extras and mutations (P-GREEN-1b/3b/3c/6b/6c, P-MUT)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import registry as agent_registry
from app.agents.registry import (
    RegistryError,
    VersionLabelConflict,
    register_blueprint,
    register_version,
)
from app.concurrency import ConcurrentWriteUnresolved
from app.models.agent_version import COMPONENT_HASH_FIELDS
from app.repositories.catalog_adoptions import CatalogAdoptionRepository
from app.repositories.cost import BudgetRepository
from app.repositories.cost_forecasts import CostForecastRepository
from app.repositories.extraction import ExtractionRepository, PromotionRefConflict
from app.repositories.intake import IntakeRepository
from app.tenancy import TenantContext
from tests.admin_support import pg_state
from tests.ecosystem_catalog_support import register_vet_list_pm, seed_project
from tests.slice83_pre_fix import (
    pre_fix_adopt,
    pre_fix_budget_upsert,
    pre_fix_promote_proposal,
    pre_fix_record_policy_version,
    pre_fix_register_blueprint,
    pre_fix_register_version,
)
from tests.slice83_support import (
    READ_COMMITTED,
    assert_integrity_error_on,
    bind_tenant,
    component_hashes,
    forecast_policy_payload,
    patched_out_conflict_handling,
    reported_constraint,
    run_two_writers,
    seed_approved_requirement,
    seed_org_tenant_project,
    two_admin_writers,
    two_committed_transactions,
    unique_row_count,
)

pytestmark = pytest.mark.db


async def test_p_green_1b_budget_sequential_two_commits(rls_engine, admin_engine):
    """P-GREEN-1b: sequential two-commit upsert; not a race. GUC rebound per txn."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def first(session: AsyncSession):
        row = await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="1",
            max_daily_cost_usd="1",
            actor="s83-1b",
        )
        return {"id": row.id, "created_at": row.created_at, "updated_at": row.updated_at}

    async def second(session: AsyncSession):
        return await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="2",
            max_daily_cost_usd="2",
            actor="s83-1b",
        )

    async def confirm(session: AsyncSession):
        return await BudgetRepository(session, ctx).get(world["project"])

    result = await two_committed_transactions(
        engine=rls_engine,
        tenant_id=world["tenant"],
        first=first,
        second=second,
        confirm=confirm,
    )
    try:
        await result.session.begin()
        await bind_tenant(result.session, world["tenant"])
        same_session = await BudgetRepository(result.session, ctx).get(world["project"])
        assert result.second.max_total_cost_usd == Decimal("2")
        assert result.second.max_daily_cost_usd == Decimal("2")
        assert same_session is not None
        assert same_session.max_total_cost_usd == Decimal("2")
        assert result.confirmed.max_total_cost_usd == Decimal("2")
        assert result.confirmed.max_daily_cost_usd == Decimal("2")
        assert result.second.updated_at > result.first["updated_at"]
        assert result.second.created_at == result.first["created_at"]
        assert result.confirmed.updated_at > result.first["updated_at"]
        assert result.confirmed.created_at == result.first["created_at"]
        count = await unique_row_count(
            admin_engine,
            "SELECT count(*) FROM budgets WHERE tenant_id=:t AND project_id=:p",
            {"t": world["tenant"], "p": world["project"]},
        )
        assert count == 1
        print("P-GREEN-1b", result.second.max_total_cost_usd, result.second.updated_at)
    finally:
        await result.session.close()
        await result.confirm_session.close()


async def test_p_green_3b_version_label_conflict(admin_engine):
    """P-GREEN-3b: same label, different prompt_hash → VersionLabelConflict."""
    async with AsyncSession(admin_engine) as session:
        blueprint = await register_blueprint(
            session,
            key=f"s83-3b-{uuid.uuid4().hex[:12]}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-3b",
        )
        blueprint_id = blueprint.id
        await session.commit()
    hashes_a = component_hashes("a" * 64)
    hashes_b = component_hashes("b" * 64)

    async def writer_a(session: AsyncSession):
        return await register_version(
            session,
            blueprint_id=blueprint_id,
            version_label="v1",
            model_route="fake",
            actor="s83-3b",
            **hashes_a,
        )

    async def writer_b(session: AsyncSession):
        return await register_version(
            session,
            blueprint_id=blueprint_id,
            version_label="v1",
            model_route="fake",
            actor="s83-3b",
            **hashes_b,
        )

    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        writer=writer_a,
        writer_w2=writer_b,
        count_sql=(
            "SELECT count(*) FROM agent_versions WHERE blueprint_id=:b AND version_label='v1'"
        ),
        count_params={"b": blueprint_id},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert result.w1_error is None
    assert type(result.w2_error) is VersionLabelConflict
    assert str(result.w2_error) == "agent version label already registered with different content"
    assert result.unique_row_count == 1
    for field in COMPONENT_HASH_FIELDS:
        assert getattr(result.w1_value, field) == hashes_a[field]
    print("P-GREEN-3b", type(result.w2_error).__name__, result.unique_row_count)


async def test_p_green_3c_unresolved_injected(monkeypatch, admin_engine):
    """P-GREEN-3c: rung 4 is unreachable by construction; proven by injection."""

    async def no_row(*_a, **_k):
        return None

    monkeypatch.setattr(agent_registry, "_reselect_version_by_content_hash", no_row)
    monkeypatch.setattr(agent_registry, "_reselect_version_by_label", no_row)
    monkeypatch.setattr(agent_registry, "_version_insert_id", no_row)
    async with AsyncSession(admin_engine) as session:
        blueprint = await register_blueprint(
            session,
            key=f"s83-3c-{uuid.uuid4().hex[:12]}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-3c",
        )
        try:
            await register_version(
                session,
                blueprint_id=blueprint.id,
                version_label="v1",
                model_route="fake",
                actor="s83-3c",
                **component_hashes(),
            )
        except RegistryError:
            raise AssertionError("ConcurrentWriteUnresolved must not be a RegistryError")
        except ConcurrentWriteUnresolved as exc:
            assert type(exc) is ConcurrentWriteUnresolved
            assert "uq_agent_versions_content_hash" in str(exc)
            assert "uq_agent_versions_blueprint_id_version_label" in str(exc)
            print("P-GREEN-3c", type(exc).__name__, str(exc))
        else:
            raise AssertionError("expected ConcurrentWriteUnresolved")


async def test_p_green_6b_promotion_ref_conflict(rls_engine, admin_engine):
    """P-GREEN-6b: two proposals forced onto one ref; savepoint leaves loser empty."""
    world = await seed_approved_requirement(admin_engine, extra=1)
    ctx = TenantContext(world["tenant"])
    pid_a, pid_b = world["proposals"]
    shared_ref = "REQ-EXT-shared01"

    async def writer_a(session: AsyncSession):
        return await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=pid_a, actor="s83-6b", ref=shared_ref
        )

    async def writer_b(session: AsyncSession):
        return await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=pid_b, actor="s83-6b", ref=shared_ref
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer_a,
        writer_w2=writer_b,
        count_sql=(
            "SELECT count(*) FROM intake_artifacts WHERE tenant_id=:t AND project_id=:p AND ref=:r"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "r": shared_ref},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert result.w1_error is None
    assert type(result.w2_error) is PromotionRefConflict
    assert str(result.w2_error) == "artifact ref already used by a different promotion"
    loser_promos = await unique_row_count(
        admin_engine,
        "SELECT count(*) FROM extraction_promotions WHERE extraction_proposal_id=:pid",
        {"pid": pid_b},
    )
    loser_arts = await unique_row_count(
        admin_engine,
        "SELECT count(*) FROM intake_artifacts WHERE tenant_id=:t AND "
        "data->>'extraction_proposal_id'=:pid",
        {"t": world["tenant"], "pid": str(pid_b)},
    )
    assert loser_promos == 0 and loser_arts == 0
    assert result.unique_row_count == 1
    print("P-GREEN-6b", type(result.w2_error).__name__, loser_promos, loser_arts)


async def test_p_green_6c_non_unique_integrity_propagates(monkeypatch, rls_engine, admin_engine):
    """P-GREEN-6c: non-23505 IntegrityError inside the savepoint is re-raised unchanged.

    Fault-injected: 23503 is not naturally reachable after the AC parent pre-check.
    """

    class _FkFailure(Exception):
        sqlstate = "23503"
        pgcode = "23503"

    async def boom(self, *args, **kwargs):
        raise IntegrityError("INSERT", {}, _FkFailure("fk"))

    monkeypatch.setattr(IntakeRepository, "add_artifact", boom)
    world = await seed_approved_requirement(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with rls_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        await bind_tenant(session, world["tenant"])
        try:
            await ExtractionRepository(session, ctx).promote_proposal(
                proposal_id=world["proposal"], actor="s83-6c"
            )
        except IntegrityError as exc:
            assert type(exc) is IntegrityError
            assert pg_state(exc) == "23503"
            assert not isinstance(exc, PromotionRefConflict)
            assert type(exc) is not ConcurrentWriteUnresolved
            print("P-GREEN-6c", type(exc).__name__, pg_state(exc))
        else:
            raise AssertionError("expected IntegrityError")
        finally:
            await session.close()
            await trans.rollback()


async def test_p_mut_1_budget_pre_fix(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="1",
            max_daily_cost_usd="1",
            actor="s83-mut",
        )

    with patched_out_conflict_handling(BudgetRepository, "upsert", pre_fix_budget_upsert):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer,
            count_sql="SELECT count(*) FROM budgets WHERE tenant_id=:t AND project_id=:p",
            count_params={"t": world["tenant"], "p": world["project"]},
        )
    assert_integrity_error_on(result.w2_error, "uq_budgets_tenant_id_project_id")
    print("P-MUT-1", type(result.w2_error).__name__, reported_constraint(result.w2_error))


async def test_p_mut_2_blueprint_pre_fix(admin_engine):
    key = f"s83-m2-{uuid.uuid4().hex[:12]}"

    async def writer(session: AsyncSession):
        return await agent_registry.register_blueprint(
            session,
            key=key,
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-mut",
        )

    with patched_out_conflict_handling(
        agent_registry, "register_blueprint", pre_fix_register_blueprint
    ):
        result = await two_admin_writers(
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            writer=writer,
            count_sql="SELECT count(*) FROM agent_blueprints WHERE key=:k",
            count_params={"k": key},
        )
    assert_integrity_error_on(result.w2_error, "uq_agent_blueprints_key")
    print("P-MUT-2", reported_constraint(result.w2_error))


async def test_p_mut_3_version_pre_fix(admin_engine):
    async with AsyncSession(admin_engine) as session:
        blueprint = await register_blueprint(
            session,
            key=f"s83-m3-{uuid.uuid4().hex[:12]}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-mut",
        )
        blueprint_id = blueprint.id
        await session.commit()
    hashes = component_hashes()

    async def writer(session: AsyncSession):
        return await agent_registry.register_version(
            session,
            blueprint_id=blueprint_id,
            version_label="v1",
            model_route="fake",
            actor="s83-mut",
            **hashes,
        )

    with patched_out_conflict_handling(
        agent_registry, "register_version", pre_fix_register_version
    ):
        result = await two_admin_writers(
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            writer=writer,
            count_sql=(
                "SELECT count(*) FROM agent_versions WHERE blueprint_id=:b AND version_label='v1'"
            ),
            count_params={"b": blueprint_id},
        )
    named = reported_constraint(result.w2_error)
    assert named in {
        "uq_agent_versions_blueprint_id_version_label",
        "uq_agent_versions_content_hash",
    }
    assert_integrity_error_on(result.w2_error, named)
    print("P-MUT-3", named)


async def test_p_mut_4_adopt_pre_fix(rls_engine, admin_engine):
    async with AsyncSession(admin_engine) as session:
        seeded = await seed_project(session)
        _asset, _vetting, listing = await register_vet_list_pm(session)
        tenant = seeded["tenant"]
        project = seeded["project"]
        listing_id = listing.id
        await session.commit()
    ctx = TenantContext(tenant)

    async def writer(session: AsyncSession):
        return await CatalogAdoptionRepository(session, ctx).adopt(
            project, listing_id, adopted_by="s83-mut"
        )

    with patched_out_conflict_handling(CatalogAdoptionRepository, "adopt", pre_fix_adopt):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=tenant,
            writer=writer,
            count_sql=(
                "SELECT count(*) FROM tenant_catalog_adoptions "
                "WHERE tenant_id=:t AND project_id=:p AND listing_id=:l"
            ),
            count_params={"t": tenant, "p": project, "l": listing_id},
        )
    assert_integrity_error_on(result.w2_error, "uq_tca_tenant_project_listing")
    print("P-MUT-4", reported_constraint(result.w2_error))


async def test_p_mut_5_policy_pre_fix(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    payload = forecast_policy_payload()

    async def writer(session: AsyncSession):
        return await CostForecastRepository(session, ctx).record_policy_version(
            project_id=world["project"],
            payload=payload,
            source_label="s83-policy",
            evidence_ref="s83-evidence",
            actor="s83-mut",
        )

    with patched_out_conflict_handling(
        CostForecastRepository, "record_policy_version", pre_fix_record_policy_version
    ):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer,
            count_sql=(
                "SELECT count(*) FROM cost_forecast_policy_versions "
                "WHERE tenant_id=:t AND project_id=:p"
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        )
    assert_integrity_error_on(result.w2_error, "uq_cfpv_project_digest")
    print("P-MUT-5", reported_constraint(result.w2_error))


async def test_p_mut_6_promote_pre_fix(rls_engine, admin_engine):
    world = await seed_approved_requirement(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=world["proposal"], actor="s83-mut"
        )

    with patched_out_conflict_handling(
        ExtractionRepository, "promote_proposal", pre_fix_promote_proposal
    ):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer,
            count_sql=(
                "SELECT count(*) FROM extraction_promotions "
                "WHERE tenant_id=:t AND extraction_proposal_id=:pid"
            ),
            count_params={"t": world["tenant"], "pid": world["proposal"]},
        )
    named = reported_constraint(result.w2_error)
    assert named in {"uq_intake_artifacts_ref", "uq_extraction_promotions_proposal"}
    assert_integrity_error_on(result.w2_error, named)
    print("P-MUT-6", named)
