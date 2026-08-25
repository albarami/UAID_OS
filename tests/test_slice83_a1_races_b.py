"""Slice 83 commit-7: A1 emergency-root and preapproval-lifecycle barriers."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity import AuthenticatedActor
from app.release.production_approval import idempotency_digest, subject_digest
from app.release.production_approval_service import ProductionApprovalService
from app.repositories.emergency_controls import EmergencyControlRepository
from app.tenancy import TenantContext
from tests.slice83_a1_support import (
    SKIP_PROJECT_LOCK,
    seed_emergency_project,
    without_uniques,
)
from tests.slice83_support import (
    READ_COMMITTED,
    assert_integrity_error_on,
    assert_no_integrity_error,
    bind_tenant,
    reported_constraint,
    run_two_writers,
    seed_org_tenant_project,
)
from tests.test_production_preapprovals import _checklist, _policy, _zero_inventories

pytestmark = pytest.mark.db


async def test_a1_emergency_project_root_green(rls_engine, admin_engine):
    """Leaf 13 GREEN: concurrent first binds share one armed-anchor root."""
    world = await seed_emergency_project(admin_engine)
    actor_hash = subject_digest("stop-a@example.test")
    keys = [idempotency_digest("s83-bind-a"), idempotency_digest("s83-bind-b")]

    async def writer_a(session: AsyncSession):
        return await EmergencyControlRepository(session, world["ctx"]).append_binding(
            project_id=world["project"],
            actor_subject_hash=actor_hash,
            actor_type="human",
            idempotency_key_hash=keys[0],
        )

    async def writer_b(session: AsyncSession):
        return await EmergencyControlRepository(session, world["ctx"]).append_binding(
            project_id=world["project"],
            actor_subject_hash=actor_hash,
            actor_type="human",
            idempotency_key_hash=keys[1],
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
            "WHERE tenant_id=:t AND project_id=:p AND previous_event_id IS NULL"
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None and result.w2_error is None
    print("A1-ESE-ROOT-GREEN", result.w1_value.id, result.w2_value.id)


async def test_a1_emergency_project_root_mutation(rls_engine, admin_engine):
    """Leaf 13 mutation: no project lock → 23505 on ``uq_ese_project_root``."""
    world = await seed_emergency_project(admin_engine)
    actor_hash = subject_digest("stop-a@example.test")
    keys = [idempotency_digest("s83-mut-a"), idempotency_digest("s83-mut-b")]

    async def writer_a(session: AsyncSession):
        return await EmergencyControlRepository(session, world["ctx"]).append_binding(
            project_id=world["project"],
            actor_subject_hash=actor_hash,
            actor_type="human",
            idempotency_key_hash=keys[0],
        )

    async def writer_b(session: AsyncSession):
        return await EmergencyControlRepository(session, world["ctx"]).append_binding(
            project_id=world["project"],
            actor_subject_hash=actor_hash,
            actor_type="human",
            idempotency_key_hash=keys[1],
        )

    with patch(
        "app.repositories.emergency_controls.lock_project_row",
        SKIP_PROJECT_LOCK,
    ):
        result = await run_two_writers(
            engine=rls_engine,
            admin_engine=admin_engine,
            isolation_level=READ_COMMITTED,
            tenant_id=world["tenant"],
            writer=writer_a,
            writer_w2=writer_b,
            count_sql=(
                "SELECT count(*) FROM emergency_stop_events "
                "WHERE tenant_id=:t AND project_id=:p AND previous_event_id IS NULL"
            ),
            count_params={"t": world["tenant"], "p": world["project"]},
        )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_ese_project_root")
    print("A1-ESE-ROOT-MUT", reported_constraint(result.w2_error))


async def _seed_revocable_attestation(admin_engine) -> dict:
    """Committed approved attestation the revoke path can race."""
    from app.release.evidence_pack import (
        assemble_core,
        canonical_json_bytes,
        derive_repo_commit_binding,
        digest_bytes,
    )
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.repositories.release_verdicts import ReleaseVerdictRepository

    world = await seed_org_tenant_project(admin_engine)
    suffix = world["sfx"]
    async with admin_engine.begin() as conn:
        candidate = (
            await conn.execute(
                text(
                    "INSERT INTO release_candidates "
                    "(tenant_id,project_id,release_ref,status) "
                    "VALUES (:t,:p,:ref,'draft') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "ref": f"s83-{suffix}"},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() "
                "WHERE id=:id"
            ),
            {"id": candidate},
        )
        await conn.execute(
            text(
                "INSERT INTO intake_categories "
                "(tenant_id,project_id,category,status,data,origin) VALUES "
                "(:t,:p,'human_approval_policy','declared',CAST(:policy AS jsonb),'s83'),"
                "(:t,:p,'go_live_checklist','declared',CAST(:checklist AS jsonb),'s83')"
            ),
            {
                "t": world["tenant"],
                "p": world["project"],
                "policy": json.dumps(
                    _policy(
                        approvers=[
                            "requester@example.test",
                            "approver@example.test",
                        ]
                    )
                ),
                "checklist": json.dumps(_checklist()),
            },
        )
        await conn.execute(
            text(
                "INSERT INTO autonomy_policies "
                "(tenant_id,project_id,autonomy_level,overrides) "
                "VALUES (:t,:p,5,'{}'::jsonb)"
            ),
            {"t": world["tenant"], "p": world["project"]},
        )
    requester = TenantContext(
        world["tenant"], actor=AuthenticatedActor("requester@example.test", "service")
    )
    approver = TenantContext(
        world["tenant"], actor=AuthenticatedActor("approver@example.test", "human")
    )
    system = TenantContext(world["tenant"])
    async with AsyncSession(admin_engine) as session:
        await bind_tenant(session, world["tenant"])
        await session.execute(text("SELECT * FROM audit_append('s83','seed',NULL,'{}'::jsonb)"))
        frozen_at = (
            await session.execute(
                text("SELECT frozen_at FROM release_candidates WHERE id=:id"),
                {"id": candidate},
            )
        ).scalar_one()
        packs = EvidencePackRepository(session, system)
        checkpoint = await packs.record_audit_checkpoint()
        inventories = _zero_inventories()
        empty = digest_bytes(canonical_json_bytes([]))
        core = assemble_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            release_ref_digest="sha256:" + "a" * 64,
            generated_at=checkpoint.created_at,
            frozen_at=frozen_at,
            artifact_scope_digest="sha256:" + "b" * 64,
            issue_binding_digest=empty,
            source_refs=(),
            inventories=inventories,
            traceability=(),
            audit_checkpoint=checkpoint,
            repo_commit_binding=derive_repo_commit_binding([]),
        )
        pack = await packs._persist_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            core=core,
            source_refs=(),
            inventories=inventories,
            traceability_edge_count=0,
            actor="s83-seed",
        )
        verdict = await ReleaseVerdictRepository(session, system).evaluate_and_record(
            project_id=world["project"],
            release_candidate_id=candidate,
            evidence_pack_id=pack.id,
            actor="s83-seed",
        )
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        requested = await ProductionApprovalService(session, requester).request(
            project_id=world["project"], idempotency_key="s83-request"
        )
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        approved = await ProductionApprovalService(session, approver).approve(
            project_id=world["project"],
            request_id=requested.request_id,
            idempotency_key="s83-approve",
        )
        world["attestation"] = approved.attestation_id
        world["verdict"] = verdict.id
        await session.commit()
    world["approver"] = approver
    return world


async def test_a1_preapproval_revoke_green(rls_engine, admin_engine):
    """Leaves 15–17 GREEN: concurrent revoke; loser is idempotent_replay."""
    world = await _seed_revocable_attestation(admin_engine)

    async def writer(session: AsyncSession):
        return await ProductionApprovalService(session, world["approver"]).revoke(
            project_id=world["project"],
            attestation_id=world["attestation"],
            idempotency_key="s83-revoke",
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM production_preapproval_lifecycle_events "
            "WHERE attestation_id=:a AND event_type='revoked'"
        ),
        count_params={"a": world["attestation"]},
    )
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert_no_integrity_error(result)
    assert result.unique_row_count == 1
    assert result.w1_error is None and result.w2_error is None
    assert result.w2_value.reason_code == "idempotent_replay"
    print("A1-PPLE-GREEN", result.w1_value.status, result.w2_value.reason_code)


async def test_a1_preapproval_previous_mutation(rls_engine, admin_engine):
    """Leaf 15 mutation: drop sibling axes so only ``uq_pple_previous`` fires."""
    world = await _seed_revocable_attestation(admin_engine)

    async def writer_a(session: AsyncSession):
        return await ProductionApprovalService(session, world["approver"]).revoke(
            project_id=world["project"],
            attestation_id=world["attestation"],
            idempotency_key="s83-rev-a",
        )

    async def writer_b(session: AsyncSession):
        return await ProductionApprovalService(session, world["approver"]).revoke(
            project_id=world["project"],
            attestation_id=world["attestation"],
            idempotency_key="s83-rev-b",
        )

    async with without_uniques(admin_engine, ("uq_pple_attestation_event", "uq_pple_idempotency")):
        with patch(
            "app.release.production_approval_service.lock_project_row",
            SKIP_PROJECT_LOCK,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer_a,
                writer_w2=writer_b,
                count_sql=(
                    "SELECT count(*) FROM production_preapproval_lifecycle_events "
                    "WHERE attestation_id=:a AND event_type='revoked'"
                ),
                count_params={"a": world["attestation"]},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_pple_previous")
    print("A1-PPLE-PREV-MUT", reported_constraint(result.w2_error))


async def test_a1_preapproval_attestation_event_mutation(rls_engine, admin_engine):
    """Leaf 16 mutation: drop sibling axes so only ``uq_pple_attestation_event`` fires."""
    world = await _seed_revocable_attestation(admin_engine)

    async def writer_a(session: AsyncSession):
        return await ProductionApprovalService(session, world["approver"]).revoke(
            project_id=world["project"],
            attestation_id=world["attestation"],
            idempotency_key="s83-evt-a",
        )

    async def writer_b(session: AsyncSession):
        return await ProductionApprovalService(session, world["approver"]).revoke(
            project_id=world["project"],
            attestation_id=world["attestation"],
            idempotency_key="s83-evt-b",
        )

    async with without_uniques(admin_engine, ("uq_pple_previous", "uq_pple_idempotency")):
        with patch(
            "app.release.production_approval_service.lock_project_row",
            SKIP_PROJECT_LOCK,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer_a,
                writer_w2=writer_b,
                count_sql=(
                    "SELECT count(*) FROM production_preapproval_lifecycle_events "
                    "WHERE attestation_id=:a AND event_type='revoked'"
                ),
                count_params={"a": world["attestation"]},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_pple_attestation_event")
    print("A1-PPLE-EVT-MUT", reported_constraint(result.w2_error))


async def test_a1_preapproval_idempotency_mutation(rls_engine, admin_engine):
    """Leaf 17 mutation: drop sibling axes so only ``uq_pple_idempotency`` fires."""
    world = await _seed_revocable_attestation(admin_engine)

    async def writer(session: AsyncSession):
        return await ProductionApprovalService(session, world["approver"]).revoke(
            project_id=world["project"],
            attestation_id=world["attestation"],
            idempotency_key="s83-same-key",
        )

    async with without_uniques(admin_engine, ("uq_pple_previous", "uq_pple_attestation_event")):
        with patch(
            "app.release.production_approval_service.lock_project_row",
            SKIP_PROJECT_LOCK,
        ):
            result = await run_two_writers(
                engine=rls_engine,
                admin_engine=admin_engine,
                isolation_level=READ_COMMITTED,
                tenant_id=world["tenant"],
                writer=writer,
                count_sql=(
                    "SELECT count(*) FROM production_preapproval_lifecycle_events "
                    "WHERE attestation_id=:a AND event_type='revoked'"
                ),
                count_params={"a": world["attestation"]},
            )
    assert result.w1_error is None
    assert_integrity_error_on(result.w2_error, "uq_pple_idempotency")
    print("A1-PPLE-IDEM-MUT", reported_constraint(result.w2_error))
