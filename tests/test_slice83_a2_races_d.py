"""Slice 83 commit-10: A2 barriers for remaining platform leaves (batch 2)."""

from __future__ import annotations

import uuid

import pytest

from app.release.production_approval import idempotency_digest
from app.tenancy import TenantContext
from tests.export_bundle_support import committed_exportable, configure_signing
from tests.slice83_a2_c_support import (
    race_pair,
    reviewer_writer,
    seed_staffed_contract,
    without_uniques,
)
from tests.slice83_a2_d_support import (
    append_request_writer,
    approve_writer,
    export_writer,
    finding_writer,
    request_writer,
    seed_preapproval_pending,
    seed_preapproval_ready,
    seed_shared_approval_request,
    seed_trusted_finding,
)
from tests.slice83_a2_e_support import era_writer, seed_era_world
from tests.slice83_a2_support import (
    assert_a2_green,
    assert_preseed_breaks_green,
    commit_writer,
    race_runtime,
)

pytestmark = pytest.mark.db


async def test_a2_reviewers_triple_green(rls_engine, admin_engine):
    world = await seed_staffed_contract(admin_engine)
    writer = reviewer_writer(world["ctx"], world["contract_id"], world["reviewer_id"])
    async with without_uniques(admin_engine, ("uq_tc_reviewers_registration",)):
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
    assert_a2_green(result, "uq_tc_reviewers_triple")
    print("A2-REV-TRIPLE-GREEN", result.unique_row_count)


async def test_a2_reviewers_triple_mutation(rls_engine, admin_engine):
    world = await seed_staffed_contract(admin_engine)
    writer = reviewer_writer(world["ctx"], world["contract_id"], world["reviewer_id"])
    await commit_writer(rls_engine, world["tenant"], writer)
    async with without_uniques(admin_engine, ("uq_tc_reviewers_registration",)):
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
            "uq_tc_reviewers_triple",
        )
    print("A2-REV-TRIPLE-MUT")


async def test_a2_era_idempotency_green(rls_engine, admin_engine):
    world = await seed_era_world(admin_engine)
    key = idempotency_digest("s83-era")
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=era_writer(world, key),
        count_sql=(
            "SELECT count(*) FROM emergency_rollback_authorizations "
            "WHERE tenant_id=:t AND project_id=:p AND idempotency_key_hash=:k"
        ),
        count_params={"t": world["tenant"], "p": world["project"], "k": key},
    )
    assert_a2_green(result, "uq_era_idempotency")
    print("A2-ERA-GREEN", result.unique_row_count)


async def test_a2_era_idempotency_mutation(rls_engine, admin_engine):
    world = await seed_era_world(admin_engine)
    key = idempotency_digest("s83-era-m")
    await commit_writer(rls_engine, world["tenant"], era_writer(world, key))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=era_writer(world, key),
            count_sql=(
                "SELECT count(*) FROM emergency_rollback_authorizations "
                "WHERE tenant_id=:t AND project_id=:p AND idempotency_key_hash=:k"
            ),
            count_params={"t": world["tenant"], "p": world["project"], "k": key},
        ),
        "uq_era_idempotency",
    )
    print("A2-ERA-MUT")


async def test_a2_epr_idempotency_green(rls_engine, admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    key = f"epr-{uuid.uuid4().hex[:10]}"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=seeded["tenant"],
        writer=export_writer(ctx, seeded["pack_id"], key),
        count_sql=(
            "SELECT count(*) FROM evidence_pack_export_records "
            "WHERE tenant_id=:t AND evidence_pack_id=:p AND idempotency_key=:k"
        ),
        count_params={"t": seeded["tenant"], "p": seeded["pack_id"], "k": key},
    )
    assert_a2_green(result, "uq_epr_idempotency", reconciles=True)
    print("A2-EPR-GREEN", result.unique_row_count)


async def test_a2_epr_idempotency_mutation(rls_engine, admin_engine, monkeypatch):
    configure_signing(monkeypatch)
    seeded = await committed_exportable(admin_engine)
    ctx = TenantContext(seeded["tenant"])
    key = f"epr-{uuid.uuid4().hex[:10]}"
    await commit_writer(rls_engine, seeded["tenant"], export_writer(ctx, seeded["pack_id"], key))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=seeded["tenant"],
            writer=export_writer(ctx, seeded["pack_id"], key),
            count_sql=(
                "SELECT count(*) FROM evidence_pack_export_records "
                "WHERE tenant_id=:t AND evidence_pack_id=:p AND idempotency_key=:k"
            ),
            count_params={"t": seeded["tenant"], "p": seeded["pack_id"], "k": key},
        ),
        "uq_epr_idempotency",
        reconciles=True,
    )
    print("A2-EPR-MUT")


async def test_a2_ppa_idempotency_green(rls_engine, admin_engine):
    world = await seed_preapproval_pending(admin_engine)
    key = "s83-approve"
    async with without_uniques(admin_engine, ("uq_ppa_request",)):
        result = await race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=approve_writer(world, key),
            count_sql=(
                "SELECT count(*) FROM production_preapproval_attestations WHERE request_id=:r"
            ),
            count_params={"r": world["request_id"]},
        )
    assert_a2_green(result, "uq_ppa_idempotency")
    print("A2-PPA-IDEM-GREEN", result.unique_row_count)


async def test_a2_ppa_idempotency_mutation(rls_engine, admin_engine):
    world = await seed_preapproval_pending(admin_engine)
    key = "s83-approve-m"
    await commit_writer(rls_engine, world["tenant"], approve_writer(world, key))
    async with without_uniques(admin_engine, ("uq_ppa_request",)):
        await assert_preseed_breaks_green(
            lambda: race_runtime(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=approve_writer(world, key),
                count_sql=(
                    "SELECT count(*) FROM production_preapproval_attestations WHERE request_id=:r"
                ),
                count_params={"r": world["request_id"]},
            ),
            "uq_ppa_idempotency",
        )
    print("A2-PPA-IDEM-MUT")


async def test_a2_ppa_request_green(rls_engine, admin_engine):
    world = await seed_preapproval_pending(admin_engine)
    async with without_uniques(admin_engine, ("uq_ppa_idempotency",)):
        result = await race_pair(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=approve_writer(world, "s83-appr-a"),
            writer_w2=approve_writer(world, "s83-appr-b"),
            count_sql=(
                "SELECT count(*) FROM production_preapproval_attestations WHERE request_id=:r"
            ),
            count_params={"r": world["request_id"]},
        )
    assert_a2_green(result, "uq_ppa_request")
    print("A2-PPA-REQ-GREEN", result.unique_row_count)


async def test_a2_ppa_request_mutation(rls_engine, admin_engine):
    world = await seed_preapproval_pending(admin_engine)
    await commit_writer(rls_engine, world["tenant"], approve_writer(world, "s83-appr-seed"))
    async with without_uniques(admin_engine, ("uq_ppa_idempotency",)):
        await assert_preseed_breaks_green(
            lambda: race_pair(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=approve_writer(world, "s83-appr-a"),
                writer_w2=approve_writer(world, "s83-appr-b"),
                count_sql=(
                    "SELECT count(*) FROM production_preapproval_attestations WHERE request_id=:r"
                ),
                count_params={"r": world["request_id"]},
            ),
            "uq_ppa_request",
        )
    print("A2-PPA-REQ-MUT")


async def test_a2_ppr_idempotency_green(rls_engine, admin_engine):
    world = await seed_preapproval_ready(admin_engine)
    key = "s83-ppr"
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=request_writer(world, key),
        count_sql=(
            "SELECT count(*) FROM production_preapproval_requests "
            "WHERE tenant_id=:t AND project_id=:p AND request_idempotency_key_hash=:k"
        ),
        count_params={
            "t": world["tenant"],
            "p": world["project"],
            "k": idempotency_digest(key),
        },
    )
    assert_a2_green(result, "uq_ppr_idempotency")
    print("A2-PPR-IDEM-GREEN", result.unique_row_count)


async def test_a2_ppr_idempotency_mutation(rls_engine, admin_engine):
    world = await seed_preapproval_ready(admin_engine)
    key = "s83-ppr-m"
    await commit_writer(rls_engine, world["tenant"], request_writer(world, key))
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=request_writer(world, key),
            count_sql=(
                "SELECT count(*) FROM production_preapproval_requests "
                "WHERE tenant_id=:t AND project_id=:p AND request_idempotency_key_hash=:k"
            ),
            count_params={
                "t": world["tenant"],
                "p": world["project"],
                "k": idempotency_digest(key),
            },
        ),
        "uq_ppr_idempotency",
    )
    print("A2-PPR-IDEM-MUT")


async def test_a2_ppr_generic_approval_green(rls_engine, admin_engine):
    world = await seed_shared_approval_request(admin_engine)
    async with without_uniques(admin_engine, ("uq_ppr_idempotency",)):
        result = await race_pair(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=append_request_writer(
                world, world["notification_id"], idempotency_digest("ga-a"), world["request_id"]
            ),
            writer_w2=append_request_writer(
                world, world["notification_b_id"], idempotency_digest("ga-b"), uuid.uuid4()
            ),
            count_sql=(
                "SELECT count(*) FROM production_preapproval_requests WHERE generic_approval_id=:a"
            ),
            count_params={"a": world["approval_id"]},
        )
    assert_a2_green(result, "uq_ppr_generic_approval")
    print("A2-PPR-GA-GREEN", result.unique_row_count)


async def test_a2_ppr_generic_approval_mutation(rls_engine, admin_engine):
    world = await seed_shared_approval_request(admin_engine)
    await commit_writer(
        rls_engine,
        world["tenant"],
        append_request_writer(
            world, world["notification_id"], idempotency_digest("ga-seed"), world["request_id"]
        ),
    )
    async with without_uniques(admin_engine, ("uq_ppr_idempotency",)):
        await assert_preseed_breaks_green(
            lambda: race_pair(
                rls_engine=rls_engine,
                admin_engine=admin_engine,
                tenant_id=world["tenant"],
                writer=append_request_writer(
                    world, world["notification_id"], idempotency_digest("ga-a"), world["request_id"]
                ),
                writer_w2=append_request_writer(
                    world, world["notification_b_id"], idempotency_digest("ga-b"), uuid.uuid4()
                ),
                count_sql=(
                    "SELECT count(*) FROM production_preapproval_requests "
                    "WHERE generic_approval_id=:a"
                ),
                count_params={"a": world["approval_id"]},
            ),
            "uq_ppr_generic_approval",
        )
    print("A2-PPR-GA-MUT")


async def test_a2_source_finding_green(rls_engine, admin_engine):
    world = await seed_trusted_finding(admin_engine)
    result = await race_runtime(
        rls_engine=rls_engine,
        admin_engine=admin_engine,
        tenant_id=world["tenant"],
        writer=finding_writer(world["ctx"], world["project"], world["finding_id"]),
        count_sql="SELECT count(*) FROM release_issues WHERE source_finding_id=:f",
        count_params={"f": world["finding_id"]},
    )
    assert_a2_green(result, "uq_release_issues_source_finding", reconciles=True)
    print("A2-FINDING-GREEN", result.unique_row_count)


async def test_a2_source_finding_mutation(rls_engine, admin_engine):
    world = await seed_trusted_finding(admin_engine)
    await commit_writer(
        rls_engine,
        world["tenant"],
        finding_writer(world["ctx"], world["project"], world["finding_id"]),
    )
    await assert_preseed_breaks_green(
        lambda: race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=world["tenant"],
            writer=finding_writer(world["ctx"], world["project"], world["finding_id"]),
            count_sql="SELECT count(*) FROM release_issues WHERE source_finding_id=:f",
            count_params={"f": world["finding_id"]},
        ),
        "uq_release_issues_source_finding",
        reconciles=True,
    )
    print("A2-FINDING-MUT")
