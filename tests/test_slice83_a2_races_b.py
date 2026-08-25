"""Slice 83 commit-9 overflow: remaining first-batch A2 independent-insert barriers."""

from __future__ import annotations

import uuid

import pytest

from app.tenancy import TenantContext
from tests.slice83_a1_ledger_support import seed_checkpoint_world
from tests.slice83_a2_support import (
    assert_a2_green,
    assert_preseed_breaks_green,
    binding_writer,
    checkpoint_writer,
    commit_writer,
    connector_writer,
    contract_writer,
    cycle_writer,
    incident_writer,
    instance_writer,
    listing_writer,
    observation_writer,
    race_runtime,
    seed_binding_world,
    seed_listed_asset_inputs,
    seed_run_world,
    seed_version_world,
)
from tests.slice83_support import seed_org_tenant_project, two_admin_writers

pytestmark = pytest.mark.db


async def test_a2_agent_instances_green(rls_engine, admin_engine):
    world = await seed_version_world(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"live-{uuid.uuid4().hex[:10]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=instance_writer(ctx, world["project"], world["version_id"], key),
        count_sql=(
            "SELECT count(*) FROM agent_instances WHERE tenant_id=:t AND project_id=:p "
            "AND instance_key=:k"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "k": key},
    )
    assert_a2_green(result, "uq_agent_instances_live_key")
    print("A2-INST-GREEN", result.unique_row_count)


async def test_a2_agent_instances_mutation(rls_engine, admin_engine):
    world = await seed_version_world(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"live-{uuid.uuid4().hex[:10]}"
    await commit_writer(
        rls_engine,
        world["tenant"],
        instance_writer(ctx, world["project"], world["version_id"], key),
    )
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=instance_writer(ctx, world["project"], world["version_id"], key),
            count_sql=(
                "SELECT count(*) FROM agent_instances WHERE tenant_id=:t AND project_id=:p "
                "AND instance_key=:k"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "k": key},
        ),
        "uq_agent_instances_live_key",
    )
    print("A2-INST-MUT")


async def test_a2_catalog_assets_green(admin_engine):
    key = f"pm-s83-{uuid.uuid4().hex[:10]}"
    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level="READ COMMITTED",
        writer=connector_writer(key),
        count_sql=(
            "SELECT count(*) FROM catalog_assets WHERE asset_kind='connector' "
            "AND asset_key=:k AND version_label='v1'"
        ),
        count_params={"k": key},
    )
    assert_a2_green(result, "uq_ca_kind_key_version")
    print("A2-ASSET-GREEN", result.unique_row_count)


async def test_a2_catalog_assets_mutation(admin_engine):
    key = f"pm-s83-{uuid.uuid4().hex[:10]}"
    await commit_writer(admin_engine, None, connector_writer(key))
    await assert_preseed_breaks_green(
        lambda: two_admin_writers(
            admin_engine=admin_engine,
            isolation_level="READ COMMITTED",
            writer=connector_writer(key),
            count_sql=(
                "SELECT count(*) FROM catalog_assets WHERE asset_kind='connector' "
                "AND asset_key=:k AND version_label='v1'"
            ),
            count_params={"k": key},
        ),
        "uq_ca_kind_key_version",
    )
    print("A2-ASSET-MUT")


async def test_a2_catalog_listings_green(admin_engine):
    world = await seed_listed_asset_inputs(admin_engine)
    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level="READ COMMITTED",
        writer=listing_writer(world["asset_id"], world["vetting_id"]),
        count_sql=(
            "SELECT count(*) FROM catalog_listings WHERE asset_id=:a AND listing_state='listed'"
        ),
        count_params={"a": world["asset_id"]},
    )
    assert_a2_green(result, "uq_cl_live_asset")
    print("A2-LIST-GREEN", result.unique_row_count)


async def test_a2_catalog_listings_mutation(admin_engine):
    world = await seed_listed_asset_inputs(admin_engine)
    await commit_writer(admin_engine, None, listing_writer(world["asset_id"], world["vetting_id"]))
    await assert_preseed_breaks_green(
        lambda: two_admin_writers(
            admin_engine=admin_engine,
            isolation_level="READ COMMITTED",
            writer=listing_writer(world["asset_id"], world["vetting_id"]),
            count_sql=(
                "SELECT count(*) FROM catalog_listings WHERE asset_id=:a AND listing_state='listed'"
            ),
            count_params={"a": world["asset_id"]},
        ),
        "uq_cl_live_asset",
    )
    print("A2-LIST-MUT")


async def test_a2_run_checkpoints_green(rls_engine, admin_engine):
    world = await seed_checkpoint_world(rls_engine, admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=checkpoint_writer(world),
        count_sql=(
            "SELECT count(*) FROM run_checkpoints WHERE tenant_id=:t AND thread_id=:th "
            "AND checkpoint_id='a2-cp'"
        ),
        count_params={"t": world["tenant"], "th": str(world["run"])},
    )
    assert_a2_green(result, "uq_run_checkpoints_id", reconciles=True)
    print("A2-CKPT-GREEN", result.unique_row_count)


async def test_a2_run_checkpoints_mutation(rls_engine, admin_engine):
    world = await seed_checkpoint_world(rls_engine, admin_engine)
    await commit_writer(rls_engine, world["tenant"], checkpoint_writer(world))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=checkpoint_writer(world),
            count_sql=(
                "SELECT count(*) FROM run_checkpoints WHERE tenant_id=:t AND thread_id=:th "
                "AND checkpoint_id='a2-cp'"
            ),
            count_params={"t": world["tenant"], "th": str(world["run"])},
        ),
        "uq_run_checkpoints_id",
        reconciles=True,
    )
    print("A2-CKPT-MUT")


async def test_a2_control_loop_runs_green(rls_engine, admin_engine):
    world = await seed_run_world(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"clr-{uuid.uuid4().hex[:12]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=cycle_writer(ctx, world["project"], world["run"], key),
        count_sql=("SELECT count(*) FROM control_loop_runs WHERE tenant_id=:t AND project_id=:p"),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_a2_green(result, "uq_clr_idempotency", reconciles=True)
    print("A2-CLR-GREEN", result.unique_row_count)


async def test_a2_control_loop_runs_mutation(rls_engine, admin_engine):
    world = await seed_run_world(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"clr-{uuid.uuid4().hex[:12]}"
    await commit_writer(
        rls_engine, world["tenant"], cycle_writer(ctx, world["project"], world["run"], key)
    )
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=cycle_writer(ctx, world["project"], world["run"], key),
            count_sql=(
                "SELECT count(*) FROM control_loop_runs WHERE tenant_id=:t AND project_id=:p"
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        ),
        "uq_clr_idempotency",
        reconciles=True,
    )
    print("A2-CLR-MUT")


async def test_a2_task_contracts_green(rls_engine, admin_engine):
    world = await seed_version_world(admin_engine)
    ctx = TenantContext(world["tenant"])
    inst = await commit_writer(
        rls_engine,
        world["tenant"],
        instance_writer(ctx, world["project"], world["version_id"], f"b-{uuid.uuid4().hex[:8]}"),
    )
    ref = f"T-{uuid.uuid4().hex[:8]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=contract_writer(ctx, inst.id, ref),
        count_sql=(
            "SELECT count(*) FROM task_contracts WHERE tenant_id=:t AND project_id=:p "
            "AND task_ref=:r"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "r": ref},
    )
    assert_a2_green(result, "uq_task_contracts_ref")
    print("A2-TC-GREEN", result.unique_row_count)


async def test_a2_task_contracts_mutation(rls_engine, admin_engine):
    world = await seed_version_world(admin_engine)
    ctx = TenantContext(world["tenant"])
    inst = await commit_writer(
        rls_engine,
        world["tenant"],
        instance_writer(ctx, world["project"], world["version_id"], f"b-{uuid.uuid4().hex[:8]}"),
    )
    ref = f"T-{uuid.uuid4().hex[:8]}"
    await commit_writer(rls_engine, world["tenant"], contract_writer(ctx, inst.id, ref))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=contract_writer(ctx, inst.id, ref),
            count_sql=(
                "SELECT count(*) FROM task_contracts WHERE tenant_id=:t AND project_id=:p "
                "AND task_ref=:r"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "r": ref},
        ),
        "uq_task_contracts_ref",
    )
    print("A2-TC-MUT")


async def test_a2_ops_incidents_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"inc-{uuid.uuid4().hex[:12]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=incident_writer(ctx, world["project"], key),
        count_sql=(
            "SELECT count(*) FROM ops_incidents WHERE tenant_id=:t AND project_id=:p "
            "AND idempotency_key=:k"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "k": key},
    )
    assert_a2_green(result, "uq_ops_incidents_idempotency", reconciles=True)
    print("A2-INC-GREEN", result.unique_row_count)


async def test_a2_ops_incidents_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"inc-{uuid.uuid4().hex[:12]}"
    await commit_writer(rls_engine, world["tenant"], incident_writer(ctx, world["project"], key))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=incident_writer(ctx, world["project"], key),
            count_sql=(
                "SELECT count(*) FROM ops_incidents WHERE tenant_id=:t AND project_id=:p "
                "AND idempotency_key=:k"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "k": key},
        ),
        "uq_ops_incidents_idempotency",
        reconciles=True,
    )
    print("A2-INC-MUT")


async def test_a2_ops_observation_runs_green(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"obs-{uuid.uuid4().hex[:12]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=observation_writer(ctx, world["project"], key),
        count_sql=(
            "SELECT count(*) FROM ops_observation_runs WHERE tenant_id=:t AND project_id=:p "
            "AND idempotency_key=:k"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "k": key},
    )
    assert_a2_green(result, "uq_ops_observation_runs_idempotency", reconciles=True)
    print("A2-OBS-GREEN", result.unique_row_count)


async def test_a2_ops_observation_runs_mutation(rls_engine, admin_engine):
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    key = f"obs-{uuid.uuid4().hex[:12]}"
    await commit_writer(rls_engine, world["tenant"], observation_writer(ctx, world["project"], key))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=observation_writer(ctx, world["project"], key),
            count_sql=(
                "SELECT count(*) FROM ops_observation_runs WHERE tenant_id=:t AND project_id=:p "
                "AND idempotency_key=:k"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "k": key},
        ),
        "uq_ops_observation_runs_idempotency",
        reconciles=True,
    )
    print("A2-OBS-MUT")


async def test_a2_issue_bindings_green(rls_engine, admin_engine):
    world = await seed_binding_world(rls_engine, admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=binding_writer(world),
        count_sql=(
            "SELECT count(*) FROM release_candidate_issue_bindings "
            "WHERE tenant_id=:t AND release_candidate_id=:c AND release_issue_id=:i"
        ),
        count_params={
            "t": world["tenant"],
            "c": world["candidate_id"],
            "i": world["issue_id"],
        },
    )
    assert_a2_green(result, "uq_release_candidate_issue_binding")
    print("A2-BIND-GREEN", result.unique_row_count)


async def test_a2_issue_bindings_mutation(rls_engine, admin_engine):
    world = await seed_binding_world(rls_engine, admin_engine)
    await commit_writer(rls_engine, world["tenant"], binding_writer(world))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=binding_writer(world),
            count_sql=(
                "SELECT count(*) FROM release_candidate_issue_bindings "
                "WHERE tenant_id=:t AND release_candidate_id=:c AND release_issue_id=:i"
            ),
            count_params={
                "t": world["tenant"],
                "c": world["candidate_id"],
                "i": world["issue_id"],
            },
        ),
        "uq_release_candidate_issue_binding",
    )
    print("A2-BIND-MUT")
