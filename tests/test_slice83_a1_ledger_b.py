"""Slice 83 commit-8: A1 barriers for emergency activate and go-live finalize."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.release.emergency_control_service import EmergencyControlService
from app.repositories.go_live_decisions import (
    GoLiveDecisionRepository,
    GoLiveDecisionRepositoryError,
)
from tests.admin_support import pg_state
from tests.slice83_a1_ledger_support import (
    SKIP_SERIALIZABLE,
    commit_one_finalize,
    purge_gld_project,
    seed_armed_stop,
    seed_gld_evaluations,
    without_finalize_row_locks,
    without_uniques,
)
from tests.slice83_a1_support import SKIP_PROJECT_LOCK
from tests.slice83_support import (
    READ_COMMITTED,
    SERIALIZABLE,
    assert_integrity_error_on,
    assert_no_integrity_error,
    reported_constraint,
    run_two_writers,
)

pytestmark = pytest.mark.db

_RETRYABLE = ("40001", "40P01")


def _sqlstate(exc: BaseException | None) -> str | None:
    """SQLSTATE of a captured writer error, or None if it is not an Exception."""
    if not isinstance(exc, Exception):
        return None
    return pg_state(exc)


def assert_gld_unique_refused(exc: BaseException | None, constraint: str) -> None:
    """``finalize_decision`` maps a unique violation onto the owned refusal."""
    assert type(exc) is GoLiveDecisionRepositoryError
    assert exc.args[0] == "decision_finalization_refused"
    assert pg_state(exc) == "23505"
    assert reported_constraint(exc) == constraint


async def test_a1_emergency_activate_previous_green(rls_engine, admin_engine):
    """Leaf 12 GREEN: two activate calls; one previous link off the armed head."""
    world = await seed_armed_stop(rls_engine, admin_engine)

    async def writer_a(session: AsyncSession):
        return await EmergencyControlService(session, world["ctx"]).activate(
            project_id=world["project"], idempotency_key="s83-act-a"
        )

    async def writer_b(session: AsyncSession):
        return await EmergencyControlService(session, world["ctx"]).activate(
            project_id=world["project"], idempotency_key="s83-act-b"
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer_a,
        writer_w2=writer_b,
        count_sql=(
            "SELECT count(*) FROM emergency_stop_events "
            "WHERE tenant_id=:t AND project_id=:p AND event_type='activated'"
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None
    print("A1-ESE-PREV-GREEN", result.unique_row_count, type(result.w2_error).__name__)


async def test_a1_emergency_activate_previous_mutation(rls_engine, admin_engine):
    """Leaf 12 mutation: no project lock → 23505 on ``uq_ese_previous``."""
    world = await seed_armed_stop(rls_engine, admin_engine)

    async def writer_a(session: AsyncSession):
        return await EmergencyControlService(session, world["ctx"]).activate(
            project_id=world["project"], idempotency_key="s83-act-ma"
        )

    async def writer_b(session: AsyncSession):
        return await EmergencyControlService(session, world["ctx"]).activate(
            project_id=world["project"], idempotency_key="s83-act-mb"
        )

    async with without_uniques(admin_engine, ("uq_ese_idempotency",)):
        with patch("app.repositories.emergency_controls.lock_project_row", SKIP_PROJECT_LOCK):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer_a,
                writer_w2=writer_b,
                count_sql=(
                    "SELECT count(*) FROM emergency_stop_events "
                    "WHERE tenant_id=:t AND project_id=:p AND event_type='activated'"
                ),
                count_params={"t": world["tenant"], "p": world["project"]},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_ese_previous")
    print("A1-ESE-PREV-MUT", result.unique_row_count)


async def test_a1_emergency_activate_idempotency_green(rls_engine, admin_engine):
    """Leaf 14 GREEN: same activation key; one activated row."""
    world = await seed_armed_stop(rls_engine, admin_engine)

    async def writer(session: AsyncSession):
        return await EmergencyControlService(session, world["ctx"]).activate(
            project_id=world["project"], idempotency_key="s83-act-same"
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM emergency_stop_events "
            "WHERE tenant_id=:t AND project_id=:p AND event_type='activated'"
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    print("A1-ESE-IDEM-GREEN", result.unique_row_count, type(result.w2_error).__name__)


async def test_a1_emergency_activate_idempotency_mutation(rls_engine, admin_engine):
    """Leaf 14 mutation: no project lock → 23505 on ``uq_ese_idempotency``."""
    world = await seed_armed_stop(rls_engine, admin_engine)

    async def writer(session: AsyncSession):
        return await EmergencyControlService(session, world["ctx"]).activate(
            project_id=world["project"], idempotency_key="s83-act-same-m"
        )

    async with without_uniques(admin_engine, ("uq_ese_previous",)):
        with patch("app.repositories.emergency_controls.lock_project_row", SKIP_PROJECT_LOCK):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer,
                count_sql=(
                    "SELECT count(*) FROM emergency_stop_events "
                    "WHERE tenant_id=:t AND project_id=:p AND event_type='activated'"
                ),
                count_params={"t": world["tenant"], "p": world["project"]},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_ese_idempotency")
    print("A1-ESE-IDEM-MUT", result.unique_row_count)


async def test_a1_gld_first_write_green(rls_engine, admin_engine):
    """Leaves 4–5 GREEN: first two finalizes form one verified chain."""
    world = await seed_gld_evaluations(admin_engine, count=2)
    eval_a, eval_b = world["evaluations"]

    async def writer_a(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_a)

    async def writer_b(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_b)

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=SERIALIZABLE,
        tenant_id=world["tenant"],
        writer=writer_a,
        writer_w2=writer_b,
        retryable_loser_sqlstates=_RETRYABLE,
        count_sql=(
            "SELECT count(*) FROM go_live_decisions "
            "WHERE tenant_id=:t AND project_id=:p AND previous_decision_id IS NULL"
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None
    if result.w2_error is not None:
        assert _sqlstate(result.w2_error) in _RETRYABLE
    async with admin_engine.connect() as conn:
        chain = (
            await conn.execute(
                text("SELECT public.slice55_verify_decision_chain(:p)"),
                {"p": world["project"]},
            )
        ).scalar_one()
    assert chain is True
    print("A1-GLD-FIRST-GREEN", result.unique_row_count, chain, type(result.w2_error).__name__)


async def test_a1_gld_previous_green(rls_engine, admin_engine):
    """Leaf 3 GREEN: concurrent second finalizes chain off one prior."""
    world = await seed_gld_evaluations(admin_engine, count=3)
    eval_0, eval_a, eval_b = world["evaluations"]
    prior_id = await commit_one_finalize(rls_engine, world, eval_0)

    async def writer_a(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_a)

    async def writer_b(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_b)

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=SERIALIZABLE,
        tenant_id=world["tenant"],
        writer=writer_a,
        writer_w2=writer_b,
        retryable_loser_sqlstates=_RETRYABLE,
        count_sql=(
            "SELECT count(*) FROM go_live_decisions "
            "WHERE tenant_id=:t AND project_id=:p AND previous_decision_id=:prior"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "prior": prior_id},
    )
    assert result.unique_row_count == 1
    if result.w2_error is not None and _sqlstate(result.w2_error) not in _RETRYABLE:
        assert type(result.w2_error) is GoLiveDecisionRepositoryError
    async with admin_engine.connect() as conn:
        chain = (
            await conn.execute(
                text("SELECT public.slice55_verify_decision_chain(:p)"),
                {"p": world["project"]},
            )
        ).scalar_one()
    assert chain is True
    print("A1-GLD-PREV-GREEN", prior_id, result.unique_row_count, chain)


async def test_a1_gld_evaluation_green(rls_engine, admin_engine):
    """Leaf 6 GREEN: same evaluation; loser is ``decision_finalization_refused``."""
    world = await seed_gld_evaluations(admin_engine, count=1)
    evaluation_id = world["evaluations"][0]

    async def writer(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(
            evaluation_id
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=SERIALIZABLE,
        tenant_id=world["tenant"],
        writer=writer,
        retryable_loser_sqlstates=_RETRYABLE,
        count_sql="SELECT count(*) FROM go_live_decisions WHERE evaluation_id=:e",
        count_params={"e": evaluation_id},
    )
    assert result.unique_row_count == 1
    assert result.w1_error is None
    assert result.w2_error is not None
    if _sqlstate(result.w2_error) not in _RETRYABLE:
        assert type(result.w2_error) is GoLiveDecisionRepositoryError
        assert result.w2_error.args[0] == "decision_finalization_refused"
    print("A1-GLD-EVAL-GREEN", result.unique_row_count, type(result.w2_error).__name__)


async def test_a1_gld_project_root_mutation(rls_engine, admin_engine):
    """Leaf 4 mutation: no row locks → 23505 on ``uq_gld_project_root``."""
    world = await seed_gld_evaluations(admin_engine, count=2)
    eval_a, eval_b = world["evaluations"]

    async def writer_a(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_a)

    async def writer_b(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_b)

    async with without_finalize_row_locks(admin_engine):
        with patch(
            "app.repositories.go_live_decisions.GoLiveDecisionRepository.require_serializable",
            SKIP_SERIALIZABLE,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer_a,
                writer_w2=writer_b,
                count_sql=(
                    "SELECT count(*) FROM go_live_decisions "
                    "WHERE tenant_id=:t AND project_id=:p AND previous_decision_id IS NULL"
                ),
                count_params={"t": world["tenant"], "p": world["project"]},
            )
    assert result.w1_error is None
    assert_gld_unique_refused(result.w2_error, "uq_gld_project_root")
    print("A1-GLD-ROOT-MUT", result.unique_row_count)


async def test_a1_gld_hash_mutation(rls_engine, admin_engine):
    """Leaf 5 mutation: sibling uniques dropped → chain verify fails."""
    world = await seed_gld_evaluations(admin_engine, count=2)
    eval_a, eval_b = world["evaluations"]

    async def writer_a(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_a)

    async def writer_b(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_b)

    async with without_uniques(admin_engine, ("uq_gld_project_root", "uq_gld_previous")):
        async with without_finalize_row_locks(admin_engine):
            with patch(
                "app.repositories.go_live_decisions.GoLiveDecisionRepository.require_serializable",
                SKIP_SERIALIZABLE,
            ):
                result = await run_two_writers(
                    engine=rls_engine,
                    admin_engine=admin_engine,
                    isolation_level=READ_COMMITTED,
                    tenant_id=world["tenant"],
                    writer=writer_a,
                    writer_w2=writer_b,
                    count_sql=(
                        "SELECT count(*) FROM go_live_decisions WHERE tenant_id=:t AND project_id=:p"
                    ),
                    count_params={"t": world["tenant"], "p": world["project"]},
                )
            async with admin_engine.connect() as conn:
                chain = (
                    await conn.execute(
                        text("SELECT public.slice55_verify_decision_chain(:p)"),
                        {"p": world["project"]},
                    )
                ).scalar_one()
        await purge_gld_project(admin_engine, world["project"])
    assert result.w1_error is None
    assert result.w2_error is None
    assert result.unique_row_count == 2
    assert chain is False
    print("A1-GLD-HASH-MUT", result.unique_row_count, chain)


async def test_a1_gld_evaluation_mutation(rls_engine, admin_engine):
    """Leaf 6 mutation: no row locks → 23505 on ``uq_gld_evaluation``."""
    world = await seed_gld_evaluations(admin_engine, count=1)
    evaluation_id = world["evaluations"][0]

    async def writer(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(
            evaluation_id
        )

    async with without_uniques(admin_engine, ("uq_gld_project_root",)):
        async with without_finalize_row_locks(admin_engine):
            with patch(
                "app.repositories.go_live_decisions.GoLiveDecisionRepository.require_serializable",
                SKIP_SERIALIZABLE,
            ):
                result = await run_two_writers(
                    engine=rls_engine,
                    admin_engine=admin_engine,
                    isolation_level=READ_COMMITTED,
                    tenant_id=world["tenant"],
                    writer=writer,
                    count_sql="SELECT count(*) FROM go_live_decisions WHERE evaluation_id=:e",
                    count_params={"e": evaluation_id},
                )
    assert result.w1_error is None
    assert_gld_unique_refused(result.w2_error, "uq_gld_evaluation")
    print("A1-GLD-EVAL-MUT", result.unique_row_count)


async def test_a1_gld_previous_mutation(rls_engine, admin_engine):
    """Leaf 3 mutation: no row locks → 23505 on ``uq_gld_previous``."""
    world = await seed_gld_evaluations(admin_engine, count=3)
    eval_0, eval_a, eval_b = world["evaluations"]
    prior_id = await commit_one_finalize(rls_engine, world, eval_0)

    async def writer_a(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_a)

    async def writer_b(session: AsyncSession):
        return await GoLiveDecisionRepository(session, world["ctx"]).finalize_decision(eval_b)

    async with without_uniques(admin_engine, ("uq_gld_entry_hash",)):
        async with without_finalize_row_locks(admin_engine):
            with patch(
                "app.repositories.go_live_decisions.GoLiveDecisionRepository.require_serializable",
                SKIP_SERIALIZABLE,
            ):
                result = await run_two_writers(
                    engine=rls_engine,
                    admin_engine=admin_engine,
                    isolation_level=READ_COMMITTED,
                    tenant_id=world["tenant"],
                    writer=writer_a,
                    writer_w2=writer_b,
                    count_sql=(
                        "SELECT count(*) FROM go_live_decisions "
                        "WHERE tenant_id=:t AND project_id=:p AND previous_decision_id=:prior"
                    ),
                    count_params={
                        "t": world["tenant"],
                        "p": world["project"],
                        "prior": prior_id,
                    },
                )
    assert result.w1_error is None
    assert_gld_unique_refused(result.w2_error, "uq_gld_previous")
    print("A1-GLD-PREV-MUT", result.unique_row_count)
