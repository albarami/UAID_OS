"""Slice 83 commit-7: A1 GREEN + mutation for the four module-owned writers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.acceptance_verification import AcceptanceVerificationRepository
from app.repositories.go_live_decisions import (
    GoLiveDecisionRepository,
    GoLiveDecisionRepositoryError,
)
from app.tenancy import TenantContext
from tests.admin_support import pg_state
from tests.slice83_a1_support import (
    DIGEST,
    SKIP_PROJECT_LOCK,
    seed_ac_bridge,
    seed_control_loop,
    without_uniques,
)
from tests.slice83_support import (
    READ_COMMITTED,
    assert_integrity_error_on,
    assert_no_integrity_error,
    reported_constraint,
    run_two_writers,
    seed_org_tenant_project,
)

pytestmark = pytest.mark.db

_CHAIN = "acceptance authorship chain must linearly supersede the current record"


async def test_a1_projects_for_update_privilege(rls_engine, admin_engine):
    """Runtime role can lock ``projects``; that is the only new lock target."""
    world = await seed_org_tenant_project(admin_engine)
    async with rls_engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(world["tenant"])},
        )
        locked = (
            await conn.execute(
                text("SELECT id FROM public.projects WHERE id=:p AND tenant_id=:t FOR UPDATE"),
                {"p": world["project"], "t": world["tenant"]},
            )
        ).scalar_one()
        await trans.rollback()
    async with admin_engine.connect() as conn:
        grants = (
            (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.role_table_grants "
                        "WHERE grantee='uaid_app' AND privilege_type='UPDATE' "
                        "AND table_schema='public' AND table_name='projects'"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert locked == world["project"]
    assert grants == ["projects"]
    print("A1-PRIV", locked, grants)


async def test_a1_acceptance_first_write_green(rls_engine, admin_engine):
    """Leaves 10–11 GREEN: loser re-derives; one seq-1 row; no 23505."""
    world = await seed_ac_bridge(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await AcceptanceVerificationRepository(session, ctx).record_extraction_unapproved(
            project_id=world["project"],
            acceptance_criterion_id=world["ac"],
            extraction_proposal_id=world["proposal"],
            evidence_reference=DIGEST,
            actor="s83-a1",
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM acceptance_criterion_authorship_records "
            "WHERE tenant_id=:t AND acceptance_criterion_id=:a"
        ),
        count_params={"t": world["tenant"], "a": world["ac"]},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.w1_value.sequence == 1
    assert result.w1_value.supersedes_record_id is None
    assert result.w2_error is not None
    assert isinstance(result.w2_error, Exception)
    assert pg_state(result.w2_error) == "P0001"
    assert _CHAIN in str(result.w2_error)
    print(
        "A1-AC-GREEN",
        result.w1_value.id,
        type(result.w2_error).__name__,
        pg_state(result.w2_error),
    )


async def test_a1_acceptance_sequence_mutation(rls_engine, admin_engine):
    """Leaf 10 mutation: no project lock → 23505 on ``uq_acar_criterion_sequence``."""
    world = await seed_ac_bridge(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await AcceptanceVerificationRepository(session, ctx).record_extraction_unapproved(
            project_id=world["project"],
            acceptance_criterion_id=world["ac"],
            extraction_proposal_id=world["proposal"],
            evidence_reference=DIGEST,
            actor="s83-a1",
        )

    with patch(
        "app.repositories.acceptance_verification.lock_project_row",
        SKIP_PROJECT_LOCK,
    ):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer,
            count_sql=(
                "SELECT count(*) FROM acceptance_criterion_authorship_records "
                "WHERE tenant_id=:t AND acceptance_criterion_id=:a"
            ),
            count_params={"t": world["tenant"], "a": world["ac"]},
        )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_acar_criterion_sequence")
    assert result.unique_row_count == 1
    print("A1-AC-SEQ-MUT", reported_constraint(result.w2_error), result.unique_row_count)


async def test_a1_acceptance_supersedes_green(rls_engine, admin_engine):
    """Leaf 11 GREEN: two disputes serialize; one supersession of the seed row."""
    world = await seed_ac_bridge(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(rls_engine) as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(world["tenant"])},
        )
        seed = await AcceptanceVerificationRepository(session, ctx).record_extraction_unapproved(
            project_id=world["project"],
            acceptance_criterion_id=world["ac"],
            extraction_proposal_id=world["proposal"],
            evidence_reference=DIGEST,
            actor="s83-a1",
        )
        seed_id = seed.id
        await session.commit()

    async def writer(session: AsyncSession):
        return await AcceptanceVerificationRepository(session, ctx).record_dispute(
            project_id=world["project"],
            acceptance_criterion_id=world["ac"],
            evidence_reference=DIGEST,
            actor="s83-a1",
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM acceptance_criterion_authorship_records "
            "WHERE tenant_id=:t AND supersedes_record_id=:s"
        ),
        count_params={"t": world["tenant"], "s": seed_id},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.w1_value.supersedes_record_id == seed_id
    assert result.w2_error is not None
    assert isinstance(result.w2_error, Exception)
    assert pg_state(result.w2_error) == "P0001"
    assert _CHAIN in str(result.w2_error)
    print("A1-AC-SUP-GREEN", result.w1_value.id, type(result.w2_error).__name__)


async def test_a1_acceptance_supersedes_mutation(rls_engine, admin_engine):
    """Leaf 11 mutation: drop the sequence axis so only ``uq_acar_supersedes_once`` fires."""
    world = await seed_ac_bridge(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(rls_engine) as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(world["tenant"])},
        )
        seed = await AcceptanceVerificationRepository(session, ctx).record_extraction_unapproved(
            project_id=world["project"],
            acceptance_criterion_id=world["ac"],
            extraction_proposal_id=world["proposal"],
            evidence_reference=DIGEST,
            actor="s83-a1",
        )
        seed_id = seed.id
        await session.commit()

    async def writer(session: AsyncSession):
        return await AcceptanceVerificationRepository(session, ctx).record_dispute(
            project_id=world["project"],
            acceptance_criterion_id=world["ac"],
            evidence_reference=DIGEST,
            actor="s83-a1",
        )

    async with without_uniques(admin_engine, ("uq_acar_criterion_sequence",)):
        with patch(
            "app.repositories.acceptance_verification.lock_project_row",
            SKIP_PROJECT_LOCK,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer,
                count_sql=(
                    "SELECT count(*) FROM acceptance_criterion_authorship_records "
                    "WHERE tenant_id=:t AND supersedes_record_id=:s"
                ),
                count_params={"t": world["tenant"], "s": seed_id},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_acar_supersedes_once")
    print("A1-AC-SUP-MUT", reported_constraint(result.w2_error))


async def test_a1_control_loop_first_event_green(rls_engine, admin_engine):
    """Leaves 7+9 GREEN: first events serialize; loser is a named transition refusal."""
    world = await seed_control_loop(rls_engine, admin_engine)

    async def writer(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).append_event(
            control_loop_run_id=world["cycle"],
            stage_code="read_project_state",
            outcome_code="capability_unavailable_not_executed",
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=("SELECT count(*) FROM control_loop_events WHERE control_loop_run_id=:c"),
        count_params={"c": world["cycle"]},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.w1_value.ordinal == 1
    assert result.w1_value.previous_event_id is None
    assert type(result.w2_error) is GoLiveDecisionRepositoryError
    assert str(result.w2_error) == "control_loop_event_transition_invalid"
    print("A1-CLE-FIRST-GREEN", result.w1_value.id, result.w2_error)


async def test_a1_control_loop_ordinal_mutation(rls_engine, admin_engine):
    """Leaf 7 mutation: drop the root index so only ``uq_cle_run_ordinal`` fires."""
    world = await seed_control_loop(rls_engine, admin_engine)

    async def writer(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).append_event(
            control_loop_run_id=world["cycle"],
            stage_code="read_project_state",
            outcome_code="capability_unavailable_not_executed",
        )

    async with without_uniques(admin_engine, ("uq_cle_loop_root",)):
        with patch(
            "app.repositories.go_live_decisions.lock_project_row",
            SKIP_PROJECT_LOCK,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer,
                count_sql=("SELECT count(*) FROM control_loop_events WHERE control_loop_run_id=:c"),
                count_params={"c": world["cycle"]},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_cle_run_ordinal")
    print("A1-CLE-ORD-MUT", reported_constraint(result.w2_error))


async def test_a1_control_loop_root_mutation(rls_engine, admin_engine):
    """Leaf 9 mutation: drop the ordinal axis so only ``uq_cle_loop_root`` fires."""
    world = await seed_control_loop(rls_engine, admin_engine)

    async def writer(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).append_event(
            control_loop_run_id=world["cycle"],
            stage_code="read_project_state",
            outcome_code="capability_unavailable_not_executed",
        )

    async with without_uniques(admin_engine, ("uq_cle_run_ordinal",)):
        with patch(
            "app.repositories.go_live_decisions.lock_project_row",
            SKIP_PROJECT_LOCK,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer,
                count_sql=(
                    "SELECT count(*) FROM control_loop_events "
                    "WHERE control_loop_run_id=:c AND previous_event_id IS NULL"
                ),
                count_params={"c": world["cycle"]},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_cle_loop_root")
    print("A1-CLE-ROOT-MUT", reported_constraint(result.w2_error))


async def test_a1_control_loop_previous_green(rls_engine, admin_engine):
    """Leaf 8 GREEN: second-stage events serialize onto one predecessor."""
    world = await seed_control_loop(rls_engine, admin_engine)
    async with AsyncSession(rls_engine) as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(world["tenant"])},
        )
        first = await GoLiveDecisionRepository(session, world["ctx"]).append_event(
            control_loop_run_id=world["cycle"],
            stage_code="read_project_state",
            outcome_code="capability_unavailable_not_executed",
        )
        first_id = first.id
        await session.commit()

    async def writer(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).append_event(
            control_loop_run_id=world["cycle"],
            stage_code="inspect_existing_work_evidence",
            outcome_code="capability_unavailable_not_executed",
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=("SELECT count(*) FROM control_loop_events WHERE previous_event_id=:e"),
        count_params={"e": first_id},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.w1_value.previous_event_id == first_id
    assert type(result.w2_error) is GoLiveDecisionRepositoryError
    print("A1-CLE-PREV-GREEN", result.w1_value.id, result.w2_error)


async def test_a1_control_loop_previous_mutation(rls_engine, admin_engine):
    """Leaf 8 mutation: drop ordinal so only ``uq_cle_previous`` fires."""
    world = await seed_control_loop(rls_engine, admin_engine)
    async with AsyncSession(rls_engine) as session:
        await session.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(world["tenant"])},
        )
        first = await GoLiveDecisionRepository(session, world["ctx"]).append_event(
            control_loop_run_id=world["cycle"],
            stage_code="read_project_state",
            outcome_code="capability_unavailable_not_executed",
        )
        first_id = first.id
        await session.commit()

    async def writer(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).append_event(
            control_loop_run_id=world["cycle"],
            stage_code="inspect_existing_work_evidence",
            outcome_code="capability_unavailable_not_executed",
        )

    async with without_uniques(admin_engine, ("uq_cle_run_ordinal",)):
        with patch(
            "app.repositories.go_live_decisions.lock_project_row",
            SKIP_PROJECT_LOCK,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer,
                count_sql=("SELECT count(*) FROM control_loop_events WHERE previous_event_id=:e"),
                count_params={"e": first_id},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_cle_previous")
    print("A1-CLE-PREV-MUT", reported_constraint(result.w2_error))
