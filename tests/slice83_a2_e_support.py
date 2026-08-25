"""Slice 83 commit-10 helpers: emergency rollback-authorization A2 seed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity import AuthenticatedActor
from app.policy.levels import AutonomyLevel
from app.release.deploy_connector import FakeDeployTargetConnector
from app.release.evidence_pack import (
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
)
from app.release.production_approval import idempotency_digest, subject_digest
from app.release.scm_connector import FakeSCMConnector
from app.repositories.emergency_controls import EmergencyControlRepository
from app.repositories.evidence_packs import EvidencePackRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.rollback_verifications import RollbackVerificationRepository
from app.repositories.tools import ToolAllowlistRepository
from app.tenancy import TenantContext
from app.verify.security_scan import canonical_digest
from tests.admin_support import seed_gated_policy
from tests.slice83_support import Writer, bind_tenant, seed_org_tenant_project
from tests.test_emergency_controls import _checklist as _emergency_checklist
from tests.test_emergency_controls import _policy as _emergency_policy
from tests.test_rollback_verifications import (
    COMMIT_SHA as ROLLBACK_SHA,
    _bound_payload,
    _zero_inventories as _rollback_inventories,
)


def era_writer(world: dict[str, Any], key_hash: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        repo = EmergencyControlRepository(session, world["ctx"])
        binding = await repo.latest_binding(world["project"])
        assert binding is not None
        member = await repo.member_for_actor(binding, world["actor_hash"])
        assert member is not None
        return await repo.authorize_rollback(
            binding=binding, member=member, idempotency_key_hash=key_hash
        )

    return writer


async def seed_era_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Rollback-bound emergency binding so ``authorize_rollback`` can collide."""
    world = await seed_org_tenant_project(admin_engine)
    suffix = world["sfx"]
    tenant = world["tenant"]
    project = world["project"]
    ctx = TenantContext(tenant, actor=AuthenticatedActor("stop-a@example.test", "human"))
    frozen_at = datetime.now(timezone.utc) - timedelta(days=1)
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, tenant)
        candidate = (
            await session.execute(
                text(
                    "INSERT INTO release_candidates "
                    "(tenant_id,project_id,release_ref,status) "
                    "VALUES (:t,:p,:r,'draft') RETURNING id"
                ),
                {"t": tenant, "p": project, "r": f"era-{suffix}"},
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE release_candidates SET status='frozen',frozen_at=:f WHERE id=:c"),
            {"c": candidate, "f": frozen_at},
        )
        await session.execute(text("SELECT * FROM audit_append('s83','seed',NULL,'{}'::jsonb)"))
        intake = IntakeCategoryRepository(session, ctx)
        await intake.declare(
            project_id=project,
            category="existing_assets_and_repositories",
            actor="s83-a2",
            origin="s83",
            data={"primary_repository": "owner/repo", "protected_branch": "main"},
        )
        await intake.declare(
            project_id=project,
            category="environments_and_deployment_targets",
            actor="s83-a2",
            origin="s83",
            data={
                "environments": {
                    "staging": {"provider": "generic_https", "domain": "staging.example.com"}
                }
            },
        )
        await intake.declare(
            project_id=project,
            category="human_approval_policy",
            actor="s83-a2",
            origin="s83",
            data=_emergency_policy(),
        )
        await intake.declare(
            project_id=project,
            category="go_live_checklist",
            actor="s83-a2",
            origin="s83",
            data=_emergency_checklist(),
        )
        await seed_gated_policy(
            session=session,
            ctx=ctx,
            project_id=project,
            autonomy_level=int(AutonomyLevel.A5),
            session_is_admin=True,
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id="rollback-connector",
            tool_name="deployment.read_target_status",
            actor="s83-a2",
        )
        packs = EvidencePackRepository(session, ctx)
        checkpoint = await packs.record_audit_checkpoint()
        inventories = _rollback_inventories()
        core = assemble_core(
            project_id=project,
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
                        "repo_binding_hash": canonical_digest("owner/repo"),
                        "commit_sha": ROLLBACK_SHA,
                    }
                ]
            ),
        )
        pack = await packs._persist_core(
            project_id=project,
            release_candidate_id=candidate,
            core=core,
            source_refs=(),
            inventories=inventories,
            traceability_edge_count=0,
            actor="s83-a2",
        )
        run = await RollbackVerificationRepository(session, ctx).observe_ci_drill(
            project_id=project,
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
            actor="s83-a2",
        )
        actor_hash = subject_digest("stop-a@example.test")
        binding = await EmergencyControlRepository(session, ctx).append_binding(
            project_id=project,
            actor_subject_hash=actor_hash,
            actor_type="human",
            idempotency_key_hash=idempotency_digest(f"era-bind-{suffix}"),
        )
        world["ctx"] = ctx
        world["actor_hash"] = actor_hash
        world["binding_id"] = binding.id
        world["rollback_run"] = run.id
        world["pack_id"] = pack.id
        await session.commit()
    return world
