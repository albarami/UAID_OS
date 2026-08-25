"""Slice 83 commit-10 helpers: platform A2 seeds (preapproval, export, finding)."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.approvals.channels.adapter import DashboardChannel
from app.approvals.channels.service import request_and_notify_approval
from app.identity import AuthenticatedActor
from app.models.approval_notification import ApprovalNotification
from app.release.evidence_pack import (
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
)
from app.release.production_approval import canonical_digest, idempotency_digest, subject_digest
from app.release.production_approval_service import ProductionApprovalService
from app.repositories.evidence_packs import EvidencePackRepository
from app.repositories.export_bundles import ExportBundleRepository, snapshot_of
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.production_preapprovals import ProductionPreapprovalRepository
from app.repositories.release_issues import ReleaseIssueRepository
from app.repositories.release_verdicts import ReleaseVerdictRepository
from app.repositories.security_scans import SecurityScanRepository
from app.tenancy import TenantContext
from tests.slice83_a2_support import reload_conflict_winner
from tests.slice83_support import Writer, bind_tenant, seed_org_tenant_project
from tests.test_issue_provenance import COMMIT_SHA as SCAN_SHA
from tests.test_issue_provenance import _security_payload
from tests.test_production_preapprovals import _checklist, _policy, _zero_inventories


async def seed_preapproval_ready(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Frozen candidate + pack + verdict + policy. No request yet."""
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
                    _policy(approvers=["requester@example.test", "approver@example.test"])
                ),
                "checklist": json.dumps(_checklist()),
            },
        )
        await conn.execute(
            text(
                "INSERT INTO autonomy_policies "
                "(tenant_id,project_id,autonomy_level,overrides) VALUES (:t,:p,5,'{}'::jsonb)"
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
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        await session.execute(text("SELECT * FROM audit_append('s83','seed',NULL,'{}'::jsonb)"))
        frozen_at = (
            await session.execute(
                text("SELECT frozen_at FROM release_candidates WHERE id=:id"), {"id": candidate}
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
        world["candidate"] = candidate
        world["pack_id"] = pack.id
        world["verdict_id"] = verdict.id
        await session.commit()
    world["requester"] = requester
    world["approver"] = approver
    world["system"] = system
    return world


async def seed_preapproval_pending(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Approved request with its attestation stripped so ``append_attestation`` can race."""
    world = await seed_preapproval_ready(admin_engine)
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        requested = await ProductionApprovalService(session, world["requester"]).request(
            project_id=world["project"], idempotency_key=f"s83-req-{world['sfx']}"
        )
        await ProductionApprovalService(session, world["approver"]).approve(
            project_id=world["project"],
            request_id=requested.request_id,
            idempotency_key="s83-seed-appr",
        )
        request = await ProductionPreapprovalRepository(session, world["requester"]).get_request(
            world["project"], requested.request_id
        )
        assert request is not None
        world["request_id"] = requested.request_id
        world["approval_id"] = request.generic_approval_id
        await session.commit()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE public.production_preapproval_lifecycle_events DISABLE TRIGGER ALL")
        )
        await conn.execute(
            text("ALTER TABLE public.production_preapproval_attestations DISABLE TRIGGER ALL")
        )
        await conn.execute(
            text(
                "DELETE FROM production_preapproval_lifecycle_events WHERE attestation_id IN "
                "(SELECT id FROM production_preapproval_attestations WHERE request_id=:r)"
            ),
            {"r": world["request_id"]},
        )
        await conn.execute(
            text("DELETE FROM production_preapproval_attestations WHERE request_id=:r"),
            {"r": world["request_id"]},
        )
        await conn.execute(
            text("ALTER TABLE public.production_preapproval_attestations ENABLE TRIGGER ALL")
        )
        await conn.execute(
            text("ALTER TABLE public.production_preapproval_lifecycle_events ENABLE TRIGGER ALL")
        )
    return world


async def seed_shared_approval_request(admin_engine: AsyncEngine) -> dict[str, Any]:
    """One generic approval whose subject_ref matches W1's request id."""
    world = await seed_preapproval_ready(admin_engine)
    request_id = uuid.uuid4()
    requester_hash = subject_digest("requester@example.test")
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        repo = ProductionPreapprovalRepository(session, world["requester"])
        sources = await repo.require_current_sources(world["project"])
        await repo.append_policy_snapshot(project_id=world["project"], sources=sources)
        approval, notification = await request_and_notify_approval(
            session,
            world["requester"],
            project_id=world["project"],
            action="deploy_production",
            risk_tier="production",
            requested_by="request_authenticated_requester",
            actor="request_authenticated_requester",
            channel=DashboardChannel(),
            requires_explicit_approval=True,
            subject_ref=f"production_preapproval:{request_id}",
            payload={},
            identity_storage_subject=requester_hash,
            audit_actor="request_authenticated_requester",
        )
        extra = ApprovalNotification(
            tenant_id=world["tenant"],
            project_id=world["project"],
            approval_id=approval.id,
            risk_tier="production",
            routing_mode="realtime",
            channel="dashboard",
            status="delivered",
        )
        session.add(extra)
        await session.flush()
        world["request_id"] = request_id
        world["approval_id"] = approval.id
        world["notification_id"] = notification.id
        world["notification_b_id"] = extra.id
        await session.commit()
    return world


def request_writer(world: dict[str, Any], key: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await ProductionApprovalService(session, world["requester"]).request(
            project_id=world["project"], idempotency_key=key
        )

    return writer


def approve_writer(world: dict[str, Any], key: str) -> Writer:
    from app.models.approval import Approval

    async def writer(session: AsyncSession) -> Any:
        repo = ProductionPreapprovalRepository(session, world["approver"])
        request = await repo.get_request(world["project"], world["request_id"])
        approval = await session.get(Approval, world["approval_id"])
        assert request is not None and approval is not None and approval.resolved_at is not None
        resolution_hash = idempotency_digest(key)
        attestation = await repo.append_attestation(
            request=request,
            approval=approval,
            approver_subject_hash=subject_digest("approver@example.test"),
            approver_actor_type="human",
            resolution_idempotency_key_hash=resolution_hash,
            expires_at=approval.resolved_at + timedelta(hours=24),
        )
        await repo.append_lifecycle_event(
            attestation=attestation,
            previous_event_id=None,
            event_type="approved_anchor",
            actor_subject_hash=subject_digest("approver@example.test"),
            actor_type="human",
            reason_code="request_authenticated_preapproval_recorded",
            idempotency_key_hash=canonical_digest(
                {"event": "approved_anchor", "resolution_key_hash": resolution_hash}
            ),
        )
        return attestation

    return writer


def append_request_writer(
    world: dict[str, Any], notification_id: uuid.UUID, key_hash: str, request_id: uuid.UUID
) -> Writer:
    from app.models.approval import Approval

    async def writer(session: AsyncSession) -> Any:
        repo = ProductionPreapprovalRepository(session, world["requester"])
        sources = await repo.require_current_sources(world["project"])
        policy = await repo.append_policy_snapshot(project_id=world["project"], sources=sources)
        approval = await session.get(Approval, world["approval_id"])
        notification = await session.get(ApprovalNotification, notification_id)
        assert approval is not None and notification is not None
        return await repo.append_request(
            project_id=world["project"],
            request_id=request_id,
            sources=sources,
            policy_version=policy,
            generic_approval=approval,
            notification=notification,
            requester_subject_hash=subject_digest("requester@example.test"),
            requester_actor_type="service",
            request_idempotency_key_hash=key_hash,
        )

    return writer


def export_writer(ctx: TenantContext, pack_id: uuid.UUID, key: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        repo = ExportBundleRepository(session, ctx)

        async def fetch() -> Any:
            existing = await repo.get_by_idempotency(pack_id, key)
            return None if existing is None else snapshot_of(existing)

        return await reload_conflict_winner(
            await repo.generate(pack_id, actor="s83-a2", idempotency_key=key),
            fetch,
        )

    return writer


def finding_writer(ctx: TenantContext, project_id: uuid.UUID, finding_id: uuid.UUID) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await ReleaseIssueRepository(session, ctx).create_from_trusted_finding(
            project_id=project_id, finding_id=finding_id, actor="s83-a2"
        )

    return writer


async def seed_trusted_finding(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Trusted security finding with the bridged issue removed so the unique can race."""
    from app.release.scm_connector import FakeSCMConnector

    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=world["project"],
            category="existing_assets_and_repositories",
            actor="s83-a2",
            data={"primary_repository": "owner/s83-a2", "protected_branch": "main"},
            origin="s83",
        )
        await SecurityScanRepository(session, ctx).execute_ci(
            project_id=world["project"],
            commit_sha=SCAN_SHA,
            connector=FakeSCMConnector(security_scan_artifact=_security_payload()),
            actor="s83-a2",
        )
        finding_id = (
            await session.execute(
                text("SELECT id FROM release_findings WHERE project_id=:p LIMIT 1"),
                {"p": world["project"]},
            )
        ).scalar_one()
        await session.commit()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE public.release_candidate_issue_bindings DISABLE TRIGGER ALL")
        )
        await conn.execute(text("ALTER TABLE public.release_issue_events DISABLE TRIGGER ALL"))
        await conn.execute(text("ALTER TABLE public.release_issues DISABLE TRIGGER ALL"))
        await conn.execute(
            text(
                "DELETE FROM release_candidate_issue_bindings WHERE release_issue_id IN "
                "(SELECT id FROM release_issues WHERE source_finding_id=:f)"
            ),
            {"f": finding_id},
        )
        await conn.execute(
            text(
                "DELETE FROM release_issue_events WHERE issue_id IN "
                "(SELECT id FROM release_issues WHERE source_finding_id=:f)"
            ),
            {"f": finding_id},
        )
        await conn.execute(
            text("DELETE FROM release_issues WHERE source_finding_id=:f"), {"f": finding_id}
        )
        await conn.execute(text("ALTER TABLE public.release_issues ENABLE TRIGGER ALL"))
        await conn.execute(text("ALTER TABLE public.release_issue_events ENABLE TRIGGER ALL"))
        await conn.execute(
            text("ALTER TABLE public.release_candidate_issue_bindings ENABLE TRIGGER ALL")
        )
    world["ctx"] = ctx
    world["finding_id"] = finding_id
    return world
