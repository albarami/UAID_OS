"""Slice 83 commit-13 helpers: rollback and verdict A3 writers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.policy.levels import AutonomyLevel
from app.release.deploy_connector import FakeDeployTargetConnector
from app.release.evidence_pack import (
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
    project_source_record,
)
from app.release.scm_connector import FakeSCMConnector
from app.repositories.evidence_packs import EvidencePackRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.release_verdicts import ReleaseVerdictRepository
from app.repositories.rollback_verifications import RollbackVerificationRepository
from app.repositories.tools import ToolAllowlistRepository
from app.tenancy import TenantContext
from app.verify.security_scan import canonical_digest
from tests.admin_support import seed_gated_policy
from tests.slice83_a3_release_support import declare_repo
from tests.slice83_support import Writer, bind_tenant, seed_org_tenant_project
from tests.test_release_verdicts import _binding_digest, _issue_inventories
from tests.test_rollback_verifications import COMMIT_SHA as ROLLBACK_SHA
from tests.test_rollback_verifications import _bound_payload, _zero_inventories

_AS_OF = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)


async def seed_rollback_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    frozen_at = _AS_OF - timedelta(days=1)
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        candidate = (
            await session.execute(
                text(
                    "INSERT INTO release_candidates "
                    "(tenant_id,project_id,release_ref,status) "
                    "VALUES (:t,:p,:r,'draft') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "r": f"rb-{world['sfx']}"},
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE release_candidates SET status='frozen',frozen_at=:f WHERE id=:c"),
            {"c": candidate, "f": frozen_at},
        )
        await session.execute(text("SELECT * FROM audit_append('s83','seed',NULL,'{}'::jsonb)"))
        await declare_repo(session, ctx, world["project"], "owner/repo")
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=world["project"],
            category="environments_and_deployment_targets",
            actor="s83-a3",
            origin="s83",
            data={
                "environments": {
                    "staging": {"provider": "generic_https", "domain": "staging.example.com"}
                }
            },
        )
        await seed_gated_policy(
            session=session,
            ctx=ctx,
            project_id=world["project"],
            autonomy_level=int(AutonomyLevel.A5),
            session_is_admin=True,
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id="rollback-connector",
            tool_name="deployment.read_target_status",
            actor="s83-a3",
        )
        packs = EvidencePackRepository(session, ctx)
        checkpoint = await packs.record_audit_checkpoint()
        repo_hash = canonical_digest("owner/repo")
        inventories = _zero_inventories()
        core = assemble_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            release_ref_digest="sha256:" + "1" * 64,
            generated_at=checkpoint.created_at,
            frozen_at=frozen_at,
            artifact_scope_digest="sha256:" + "2" * 64,
            issue_binding_digest=digest_bytes(canonical_json_bytes([])),
            source_refs=(),
            inventories=inventories,
            traceability=(),
            audit_checkpoint=checkpoint,
            repo_commit_binding=derive_repo_commit_binding(
                [
                    {
                        "truth_tier": "connector_verified_ci",
                        "repo_binding_hash": repo_hash,
                        "commit_sha": ROLLBACK_SHA,
                    }
                ]
            ),
        )
        pack = await packs._persist_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            core=core,
            source_refs=(),
            inventories=inventories,
            traceability_edge_count=0,
            actor="s83-a3",
        )
        world["ctx"] = ctx
        world["candidate"] = candidate
        world["pack_id"] = pack.id
        await session.commit()
    return world


def rollback_writer(world: dict[str, Any]) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await RollbackVerificationRepository(session, world["ctx"]).observe_ci_drill(
            project_id=world["project"],
            scm_connector=FakeSCMConnector(rollback_drill_artifact=_bound_payload()),
            deploy_connector=FakeDeployTargetConnector(
                result={
                    "reachable": True,
                    "provisioned": True,
                    "target_available": True,
                    "observed_http_status": 200,
                }
            ),
            service_id="rollback-connector",
            actor="s83-a3",
        )

    return writer


async def seed_verdict_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    from app.models.release_candidate_issue_binding import ReleaseCandidateIssueBinding
    from app.models.release_issue import ReleaseIssue

    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        issue_id = (
            await session.execute(
                text(
                    "INSERT INTO release_issues "
                    "(tenant_id,project_id,issue_category,severity,blocking,summary,detail,source,"
                    "source_provenance,status) VALUES "
                    "(:t,:p,'security','critical',true,'s83-a3','s83-a3-detail','s83',"
                    "'caller_supplied_unverified','open') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
        candidate = (
            await session.execute(
                text(
                    "INSERT INTO release_candidates "
                    "(tenant_id,project_id,release_ref,status) "
                    "VALUES (:t,:p,:r,'draft') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "r": f"vd-{world['sfx']}"},
            )
        ).scalar_one()
        binding_id = (
            await session.execute(
                text(
                    "INSERT INTO release_candidate_issue_bindings "
                    "(tenant_id,project_id,release_candidate_id,release_issue_id) "
                    "VALUES (:t,:p,:c,:i) RETURNING id"
                ),
                {
                    "t": world["tenant"],
                    "p": world["project"],
                    "c": candidate,
                    "i": issue_id,
                },
            )
        ).scalar_one()
        await session.execute(
            text(
                "UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() "
                "WHERE id=:c"
            ),
            {"c": candidate},
        )
        frozen_at = (
            await session.execute(
                text("SELECT frozen_at FROM release_candidates WHERE id=:c"),
                {"c": candidate},
            )
        ).scalar_one()
        await session.execute(text("SELECT * FROM audit_append('s83','seed',NULL,'{}'::jsonb)"))
        issue = await session.get(ReleaseIssue, issue_id)
        binding = await session.get(ReleaseCandidateIssueBinding, binding_id)
        assert issue is not None and binding is not None
        issue_ref = project_source_record("release_issue", issue)
        binding_ref = project_source_record("release_candidate_issue_binding", binding)
        refs = (binding_ref, issue_ref)
        packs = EvidencePackRepository(session, ctx)
        checkpoint = await packs.record_audit_checkpoint()
        inventories = _issue_inventories(*refs)
        core = assemble_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            release_ref_digest="sha256:" + "d" * 64,
            generated_at=checkpoint.created_at,
            frozen_at=frozen_at,
            artifact_scope_digest="sha256:" + "e" * 64,
            issue_binding_digest=_binding_digest(binding_ref),
            source_refs=refs,
            inventories=inventories,
            traceability=(),
            audit_checkpoint=checkpoint,
            repo_commit_binding=derive_repo_commit_binding([]),
        )
        pack = await packs._persist_core(
            project_id=world["project"],
            release_candidate_id=candidate,
            core=core,
            source_refs=refs,
            inventories=inventories,
            traceability_edge_count=0,
            actor="s83-a3",
        )
        world["ctx"] = ctx
        world["candidate"] = candidate
        world["pack_id"] = pack.id
        await session.commit()
    return world


def verdict_writer(world: dict[str, Any]) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        await bind_tenant(session, world["tenant"])
        return await ReleaseVerdictRepository(session, world["ctx"]).evaluate_and_record(
            project_id=world["project"],
            release_candidate_id=world["candidate"],
            evidence_pack_id=world["pack_id"],
            actor="s83-a3",
        )

    return writer
