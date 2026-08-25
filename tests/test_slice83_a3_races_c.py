"""Slice 83 commit-13: A3 barriers for keys, scan, shortcut, oracle, QA."""

from __future__ import annotations

import pytest

from tests.slice83_a3_copy import mutate_copied_child
from tests.slice83_a3_release_support import (
    SHA_A,
    SHA_B,
    SHA_C,
    SHA_D,
    collapsed_hash_key,
    judgment_writer,
    key_id,
    key_writer,
    oracle_writer,
    qa_writer,
    scan_writer,
    seed_judgment_world,
    seed_oracle_world,
    seed_qa_world,
    seed_scan_world,
    seed_shortcut_world,
    shortcut_writer,
)
from tests.slice83_a3_support import (
    assert_a3_green,
    assert_a3_mutation,
    race_admin,
    race_runtime,
    row_id,
)
from tests.slice83_support import seed_org_tenant_project, unique_row_count

pytestmark = pytest.mark.db


def _distinct(table: str, parent: str, extra: str) -> str:
    return f"SELECT count(DISTINCT {parent}) FROM {table} WHERE {extra}"


async def test_a3_keys_green(admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    result = await race_admin(
        admin_engine=admin_engine,
        writer=key_writer(world["tenant"], "s83a3ka"),
        writer_w2=key_writer(world["tenant"], "s83a3kb"),
        count_sql=_distinct("tenant_api_keys", "id", "tenant_id=:t"),
        count_params={"t": world["tenant"]},
    )
    assert_a3_green(result, parent_of=key_id)
    print("A3-KEYS-GREEN", result.unique_row_count)


async def test_a3_keys_mutation(admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    with collapsed_hash_key():
        await assert_a3_mutation(
            lambda: race_admin(
                admin_engine=admin_engine,
                writer=key_writer(world["tenant"], "s83a3kma"),
                writer_w2=key_writer(world["tenant"], "s83a3kmb"),
                count_sql=_distinct("tenant_api_keys", "id", "tenant_id=:t"),
                count_params={"t": world["tenant"]},
            ),
            parent_of=key_id,
            constraint="uq_tenant_api_keys_key_hash",
        )
    print("A3-KEYS-MUT")


async def test_a3_scan_green(rls_engine, admin_engine):
    world = await seed_scan_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=scan_writer(world, SHA_C),
        writer_w2=scan_writer(world, SHA_D),
        count_sql=_distinct(
            "security_scan_category_results",
            "security_scan_run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    findings = await unique_row_count(
        admin_engine,
        _distinct(
            "release_findings",
            "security_scan_category_result_id",
            "tenant_id=:t AND project_id=:p AND scan_finding_fingerprint IS NOT NULL",
        ),
        {"t": world["tenant"], "p": world["project"]},
    )
    assert findings >= 2
    print("A3-SCAN-GREEN", result.unique_row_count, findings)


async def test_a3_scan_mutation(rls_engine, admin_engine):
    world = await seed_scan_world(admin_engine)
    await mutate_copied_child(
        table="security_scan_category_results",
        constraint="uq_sscr_run_category",
        parent_writer=scan_writer(world, SHA_C),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "security_scan_category_results",
            "security_scan_run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-SCAN-MUT")


async def test_a3_shortcut_green(rls_engine, admin_engine):
    world = await seed_shortcut_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=shortcut_writer(world, SHA_A),
        writer_w2=shortcut_writer(world, SHA_B),
        count_sql=_distinct(
            "shortcut_detector_category_results",
            "shortcut_detector_run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-SHORTCUT-GREEN", result.unique_row_count)


async def test_a3_shortcut_mutation(rls_engine, admin_engine):
    world = await seed_shortcut_world(admin_engine)
    await mutate_copied_child(
        table="shortcut_detector_category_results",
        constraint=("uq_sdcr_run_category", "uq_sdrr_category_reviewer"),
        parent_writer=shortcut_writer(world, SHA_A),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "shortcut_detector_category_results",
            "shortcut_detector_run_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-SHORTCUT-MUT")


async def test_a3_oracle_green(rls_engine, admin_engine):
    world = await seed_oracle_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=oracle_writer(world, SHA_A),
        writer_w2=oracle_writer(world, SHA_B),
        count_sql=_distinct(
            "test_results",
            "test_oracle_run_id",
            "tenant_id=:t AND project_id=:p AND evaluator_instance_id IS NULL",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-ORACLE-GREEN", result.unique_row_count)


async def test_a3_oracle_mutation(rls_engine, admin_engine):
    world = await seed_oracle_world(admin_engine)
    await mutate_copied_child(
        table="test_results",
        constraint="uq_test_results_deterministic_case",
        parent_writer=oracle_writer(world, SHA_A),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "test_results",
            "test_oracle_run_id",
            "tenant_id=:t AND project_id=:p AND evaluator_instance_id IS NULL",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-ORACLE-MUT")


async def test_a3_judgment_green(rls_engine, admin_engine):
    world = await seed_judgment_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=judgment_writer(world, SHA_C),
        writer_w2=judgment_writer(world, SHA_D),
        count_sql=_distinct(
            "test_results",
            "test_oracle_run_id",
            "tenant_id=:t AND project_id=:p AND evaluator_instance_id IS NOT NULL",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-JUDGMENT-GREEN", result.unique_row_count)


async def test_a3_judgment_mutation(rls_engine, admin_engine):
    world = await seed_judgment_world(admin_engine)
    await mutate_copied_child(
        table="test_results",
        constraint="uq_test_results_judgment_vote",
        parent_writer=judgment_writer(world, SHA_C),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "test_results",
            "test_oracle_run_id",
            "tenant_id=:t AND project_id=:p AND evaluator_instance_id IS NOT NULL",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-JUDGMENT-MUT")


async def test_a3_qa_green(rls_engine, admin_engine):
    world = await seed_qa_world(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=qa_writer(world),
        count_sql=_distinct(
            "reviewer_quality_case_results",
            "reviewer_quality_record_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a3_green(result, parent_of=row_id)
    print("A3-QA-GREEN", result.unique_row_count)


async def test_a3_qa_mutation(rls_engine, admin_engine):
    world = await seed_qa_world(admin_engine)
    await mutate_copied_child(
        table="reviewer_quality_case_results",
        constraint=("uq_rqcr_record_case", "uq_rqdr_case_defect"),
        parent_writer=qa_writer(world),
        parent_id_of=row_id,
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        count_sql=_distinct(
            "reviewer_quality_case_results",
            "reviewer_quality_record_id",
            "tenant_id=:t AND project_id=:p",
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    print("A3-QA-MUT")
