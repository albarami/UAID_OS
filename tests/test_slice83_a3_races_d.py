"""Slice 83 commit-13: A3 barriers for rollback and release-verdict leaves."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.models.rollback_verification import RollbackVerificationRun
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
    force_row_id,
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
    with force_row_id(RollbackVerificationRun, uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
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
            ),
            parent_of=row_id,
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
    with patch("app.repositories.release_verdicts.uuid.uuid4", return_value=uuid.uuid4()):
        await assert_a3_mutation(
            lambda: race_runtime(
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
            ),
            parent_of=run_id,
        )
    print("A3-VERDICT-MUT")
