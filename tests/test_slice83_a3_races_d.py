"""Slice 83 commit-13: A3 barriers for rollback and release-verdict leaves."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.repositories.go_live_decisions import GoLiveDecisionRepository
from tests.slice83_a1_ledger_support import SKIP_SERIALIZABLE
from tests.slice83_a2_support import commit_writer
from tests.slice83_a3_copy import mutate_copied_child
from tests.slice83_a3_ops_support import evaluation_for, gate_child_writer, seed_two_cycles
from tests.slice83_a3_release_support import run_id
from tests.slice83_a3_release_support_b import (
    rollback_writer,
    seed_rollback_world,
    seed_verdict_world,
    verdict_writer,
)
from tests.slice83_a3_support import (
    assert_a3_green,
    assert_a3_mutation,
    assert_a3_scoped_parents,
    minted_id,
    race_runtime,
    row_id,
)

pytestmark = pytest.mark.db


def _distinct(table: str, parent: str, extra: str) -> str:
    return f"SELECT count(DISTINCT {parent}) FROM {table} WHERE {extra}"


async def test_a3_rollback_green(rls_engine, admin_engine):
    world = await seed_rollback_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=rollback_writer(world),
        count_sql=_distinct(
            "rollback_verification_phase_results",
            "run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-ROLLBACK-GREEN", result.unique_row_count)


async def test_a3_rollback_mutation(rls_engine, admin_engine):
    world = await seed_rollback_world(admin_engine)
    await mutate_copied_child(
        table="rollback_verification_phase_results",
        constraint=("uq_rvpr_run_ordinal", "uq_rvpr_run_phase"),
        parent_writer=rollback_writer(world),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "rollback_verification_phase_results",
            "run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-ROLLBACK-MUT")


async def test_a3_verdict_green(rls_engine, admin_engine):
    world = await seed_verdict_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=verdict_writer(world),
        count_sql=_distinct(
            "release_verdict_issue_results",
            "verdict_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=run_id)
    print("A3-VERDICT-GREEN", result.unique_row_count)


async def test_a3_verdict_mutation(rls_engine, admin_engine):
    world = await seed_verdict_world(admin_engine)
    await mutate_copied_child(
        table="release_verdict_issue_results",
        constraint=("uq_rvir_verdict_binding", "uq_rvir_verdict_ordinal"),
        parent_writer=verdict_writer(world),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "release_verdict_issue_results",
            "verdict_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-VERDICT-MUT")


async def test_a3_glegr_green(rls_engine, admin_engine):
    world = await seed_two_cycles(rls_engine, admin_engine)
    with patch.object(GoLiveDecisionRepository, "require_serializable", SKIP_SERIALIZABLE):
        result = await race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=evaluation_for(world, world["cycle"]),
            writer_w2=evaluation_for(world, world["cycle2"]),
            count_sql=_distinct(
                "go_live_evaluation_gate_results",
                "evaluation_id",
                "tenant_id=:t AND project_id=:p",
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        )
    first, second = assert_a3_green(result, parent_of=row_id, require_count=False)
    await assert_a3_scoped_parents(
        admin_engine,
        table="go_live_evaluation_gate_results",
        parent_column="evaluation_id",
        first=first,
        second=second,
    )
    print("A3-GLEGR-GREEN", first, second)


async def test_a3_glegr_mutation(rls_engine, admin_engine):
    world = await seed_two_cycles(rls_engine, admin_engine)
    with patch.object(GoLiveDecisionRepository, "require_serializable", SKIP_SERIALIZABLE):
        evaluation = await commit_writer(
            rls_engine, world["tenant"], evaluation_for(world, world["cycle"])
        )
    await assert_a3_mutation(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=gate_child_writer(world, evaluation.id),
            writer_w2=gate_child_writer(world, evaluation.id),
            count_sql=_distinct(
                "go_live_evaluation_gate_results",
                "evaluation_id",
                "tenant_id=:t AND project_id=:p",
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        ),
        parent_of=minted_id,
        constraint=("uq_glegr_gate", "uq_glegr_ordinal"),
    )
    print("A3-GLEGR-MUT")
