"""Slice 83 commit-10: A2 barriers for remaining tenant/platform leaves (batch 1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.tenancy import TenantContext
from tests.slice83_a1_support import seed_control_loop, seed_emergency_project
from tests.slice83_a2_c_support import (
    assert_a2_serializable,
    binding_idempotency_writer,
    commit_serializable,
    emergency_hash,
    evaluation_writer,
    hotfix_writer,
    link_writer,
    promote_writer,
    race_pair,
    race_serializable,
    reviewer_writer,
    seed_hotfix_incident,
    seed_open_incident,
    seed_staffed_contract,
    seed_stab_world,
    stab_writer,
    ticket_writer,
    without_uniques,
)
from tests.slice83_a2_support import (
    assert_a2_green,
    assert_preseed_breaks_green,
    commit_writer,
    race_runtime,
)
from tests.slice83_support import seed_approved_requirement

pytestmark = pytest.mark.db


def assert_hotfix_green(result) -> None:
    """A2 GREEN plus the insert-winner: W1 must persist a run, not take the skip path."""
    assert_a2_green(result, "uq_ops_self_healing_runs_idempotency", reconciles=True)
    assert result.w1_value is not None


async def test_a2_ecb_idempotency_green(rls_engine, admin_engine):
    world = await seed_emergency_project(admin_engine)
    key = emergency_hash("s83-ecb")
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=binding_idempotency_writer(world, key),
        count_sql=(
            "SELECT count(*) FROM emergency_control_bindings "
            "WHERE tenant_id=:t AND project_id=:p AND idempotency_key_hash=:k"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "k": key},
    )
    assert_a2_green(result, "uq_ecb_idempotency")
    print("A2-ECB-GREEN", result.unique_row_count)


async def test_a2_ecb_idempotency_mutation(rls_engine, admin_engine):
    world = await seed_emergency_project(admin_engine)
    key = emergency_hash("s83-ecb-m")
    await commit_writer(rls_engine, world["tenant"], binding_idempotency_writer(world, key))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=binding_idempotency_writer(world, key),
            count_sql=(
                "SELECT count(*) FROM emergency_control_bindings "
                "WHERE tenant_id=:t AND project_id=:p AND idempotency_key_hash=:k"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "k": key},
        ),
        "uq_ecb_idempotency",
    )
    print("A2-ECB-MUT")


async def test_a2_extraction_promotions_green(rls_engine, admin_engine):
    world = await seed_approved_requirement(admin_engine)
    ctx = TenantContext(world["tenant"])
    result = await race_pair(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=promote_writer(ctx, world["proposal"], f"REQ-A2-{uuid.uuid4().hex[:8]}"),
        writer_w2=promote_writer(ctx, world["proposal"], f"REQ-A2-{uuid.uuid4().hex[:8]}"),
        count_sql=(
            "SELECT count(*) FROM extraction_promotions "
            "WHERE tenant_id=:t AND extraction_proposal_id=:p"
        ),
        count_params={"t": world["tenant"], "p": world["proposal"]},
    )
    assert_a2_green(result, "uq_extraction_promotions_proposal", reconciles=True)
    print("A2-PROMO-GREEN", result.unique_row_count)


async def test_a2_extraction_promotions_mutation(rls_engine, admin_engine):
    world = await seed_approved_requirement(admin_engine)
    ctx = TenantContext(world["tenant"])
    await commit_writer(
        rls_engine,
        world["tenant"],
        promote_writer(ctx, world["proposal"], f"REQ-A2-{uuid.uuid4().hex[:8]}"),
    )
    await assert_preseed_breaks_green(
        lambda: race_pair(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=promote_writer(ctx, world["proposal"], f"REQ-A2-{uuid.uuid4().hex[:8]}"),
            writer_w2=promote_writer(ctx, world["proposal"], f"REQ-A2-{uuid.uuid4().hex[:8]}"),
            count_sql=(
                "SELECT count(*) FROM extraction_promotions "
                "WHERE tenant_id=:t AND extraction_proposal_id=:p"
            ),
            count_params={"t": world["tenant"], "p": world["proposal"]},
        ),
        "uq_extraction_promotions_proposal",
        reconciles=True,
    )
    print("A2-PROMO-MUT")


async def test_a2_gle_loop_green(rls_engine, admin_engine):
    world = await seed_control_loop(rls_engine, admin_engine)
    result = await race_serializable(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=evaluation_writer(world),
        count_sql="SELECT count(*) FROM go_live_evaluations WHERE control_loop_run_id=:c",
        count_params={"c": world["cycle"]},
    )
    assert_a2_serializable(result, "uq_gle_loop")
    print("A2-GLE-GREEN", result.unique_row_count)


async def test_a2_gle_loop_mutation(rls_engine, admin_engine):
    world = await seed_control_loop(rls_engine, admin_engine)
    await commit_serializable(rls_engine, world["tenant"], evaluation_writer(world))
    try:
        result = await race_serializable(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=evaluation_writer(world),
            count_sql="SELECT count(*) FROM go_live_evaluations WHERE control_loop_run_id=:c",
            count_params={"c": world["cycle"]},
        )
    except IntegrityError:
        print("A2-GLE-MUT")
        return
    held = True
    try:
        assert_a2_serializable(result, "uq_gle_loop")
    except AssertionError:
        held = False
    assert held is False, "pre-seeded evaluation race still satisfied A2 GREEN"
    print("A2-GLE-MUT")


async def test_a2_incident_tickets_green(rls_engine, admin_engine):
    world = await seed_open_incident(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=ticket_writer(world["ctx"], world["project"], world["incident_id"]),
        count_sql="SELECT count(*) FROM ops_incident_tickets WHERE incident_id=:i",
        count_params={"i": world["incident_id"]},
    )
    assert_a2_green(result, "uq_ops_incident_tickets_incident")
    print("A2-TICKET-GREEN", result.unique_row_count)


async def test_a2_incident_tickets_mutation(rls_engine, admin_engine):
    world = await seed_open_incident(admin_engine)
    await commit_writer(
        admin_engine,
        world["tenant"],
        ticket_writer(world["ctx"], world["project"], world["incident_id"]),
    )
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=ticket_writer(world["ctx"], world["project"], world["incident_id"]),
            count_sql="SELECT count(*) FROM ops_incident_tickets WHERE incident_id=:i",
            count_params={"i": world["incident_id"]},
        ),
        "uq_ops_incident_tickets_incident",
    )
    print("A2-TICKET-MUT")


async def test_a2_self_healing_runs_green(rls_engine, admin_engine):
    world = await seed_hotfix_incident(admin_engine)
    key = f"hf-{world['sfx']}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=hotfix_writer(world["ctx"], world["project"], world["incident_id"], key),
        count_sql=(
            "SELECT count(*) FROM ops_self_healing_runs "
            "WHERE tenant_id=:t AND project_id=:p AND incident_id=:i AND idempotency_key=:k"
        ),
        count_params={
            "t": world["tenant"],
            "p": world["project"],
            "i": world["incident_id"],
            "k": key,
        },
    )
    assert_hotfix_green(result)
    print("A2-HF-GREEN", result.unique_row_count)


async def test_a2_self_healing_runs_mutation(rls_engine, admin_engine):
    world = await seed_hotfix_incident(admin_engine)
    key = f"hf-{world['sfx']}"
    seeded = await commit_writer(
        admin_engine,
        world["tenant"],
        hotfix_writer(world["ctx"], world["project"], world["incident_id"], key),
    )
    assert seeded is not None
    try:
        result = await race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=hotfix_writer(
                world["ctx"],
                world["project"],
                world["incident_id"],
                key,
                reload_winner=False,
            ),
            count_sql=(
                "SELECT count(*) FROM ops_self_healing_runs "
                "WHERE tenant_id=:t AND project_id=:p AND incident_id=:i AND idempotency_key=:k"
            ),
            count_params={
                "t": world["tenant"],
                "p": world["project"],
                "i": world["incident_id"],
                "k": key,
            },
        )
    except IntegrityError:
        print("A2-HF-MUT")
        return
    held = True
    try:
        assert_hotfix_green(result)
    except AssertionError:
        held = False
    assert held is False, "pre-seeded race still satisfied A2 GREEN"
    print("A2-HF-MUT")


async def test_a2_stab_windows_green(rls_engine, admin_engine):
    world = await seed_stab_world(admin_engine)
    key = f"stab-{world['sfx']}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=stab_writer(world["ctx"], world["project"], key),
        count_sql=(
            "SELECT count(*) FROM ops_stabilization_windows "
            "WHERE tenant_id=:t AND project_id=:p AND idempotency_key=:k"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "k": key},
    )
    assert_a2_green(result, "uq_ops_stab_windows_idempotency", reconciles=True)
    print("A2-STAB-GREEN", result.unique_row_count)


async def test_a2_stab_windows_mutation(rls_engine, admin_engine):
    world = await seed_stab_world(admin_engine)
    key = f"stab-{world['sfx']}"
    seeded = await commit_writer(
        admin_engine, world["tenant"], stab_writer(world["ctx"], world["project"], key)
    )
    assert seeded is not None
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=stab_writer(world["ctx"], world["project"], key),
            count_sql=(
                "SELECT count(*) FROM ops_stabilization_windows "
                "WHERE tenant_id=:t AND project_id=:p AND idempotency_key=:k"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "k": key},
        ),
        "uq_ops_stab_windows_idempotency",
        reconciles=True,
    )
    print("A2-STAB-MUT")


async def test_a2_artifact_links_green(rls_engine, admin_engine):
    world = await seed_staffed_contract(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=link_writer(world["ctx"], world["contract_id"], world["requirement_id"]),
        count_sql=(
            "SELECT count(*) FROM task_contract_artifact_links "
            "WHERE task_contract_id=:c AND artifact_id=:a AND link_kind='source_requirement'"
        ),
        count_params={"c": world["contract_id"], "a": world["requirement_id"]},
    )
    assert_a2_green(result, "uq_tc_artifact_links_triple")
    print("A2-LINK-GREEN", result.unique_row_count)


async def test_a2_artifact_links_mutation(rls_engine, admin_engine):
    world = await seed_staffed_contract(admin_engine)
    await commit_writer(
        rls_engine,
        world["tenant"],
        link_writer(world["ctx"], world["contract_id"], world["requirement_id"]),
    )
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=link_writer(world["ctx"], world["contract_id"], world["requirement_id"]),
            count_sql=(
                "SELECT count(*) FROM task_contract_artifact_links "
                "WHERE task_contract_id=:c AND artifact_id=:a AND link_kind='source_requirement'"
            ),
            count_params={"c": world["contract_id"], "a": world["requirement_id"]},
        ),
        "uq_tc_artifact_links_triple",
    )
    print("A2-LINK-MUT")


async def test_a2_reviewers_registration_green(rls_engine, admin_engine):
    world = await seed_staffed_contract(admin_engine)
    writer = reviewer_writer(world["ctx"], world["contract_id"], world["reviewer_id"])
    async with without_uniques(admin_engine, ("uq_tc_reviewers_triple",)):
        result = await race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=writer,
            count_sql=(
                "SELECT count(*) FROM task_contract_reviewers "
                "WHERE task_contract_id=:c AND reviewer_instance_id=:r AND layer='role_specific'"
            ),
            count_params={"c": world["contract_id"], "r": world["reviewer_id"]},
        )
    assert_a2_green(result, "uq_tc_reviewers_registration")
    print("A2-REV-REG-GREEN", result.unique_row_count)


async def test_a2_reviewers_registration_mutation(rls_engine, admin_engine):
    world = await seed_staffed_contract(admin_engine)
    writer = reviewer_writer(world["ctx"], world["contract_id"], world["reviewer_id"])
    await commit_writer(rls_engine, world["tenant"], writer)
    async with without_uniques(admin_engine, ("uq_tc_reviewers_triple",)):
        await assert_preseed_breaks_green(
            lambda: race_runtime(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=writer,
                count_sql=(
                    "SELECT count(*) FROM task_contract_reviewers "
                    "WHERE task_contract_id=:c AND reviewer_instance_id=:r "
                    "AND layer='role_specific'"
                ),
                count_params={"c": world["contract_id"], "r": world["reviewer_id"]},
            ),
            "uq_tc_reviewers_registration",
        )
    print("A2-REV-REG-MUT")
