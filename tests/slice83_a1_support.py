"""Slice 83 commit-7 A1 helpers: privilege, lock skip, unique isolation, seeds."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity import AuthenticatedActor
from app.tenancy import TenantContext
from tests.slice83_support import bind_tenant, seed_approved_requirement, seed_org_tenant_project

DIGEST = "sha256:" + "c" * 64
SKIP_PROJECT_LOCK = AsyncMock(return_value=None)

_DROP: dict[str, str] = {
    "uq_acar_criterion_sequence": (
        "ALTER TABLE public.acceptance_criterion_authorship_records "
        "DROP CONSTRAINT uq_acar_criterion_sequence"
    ),
    "uq_acar_supersedes_once": (
        "ALTER TABLE public.acceptance_criterion_authorship_records "
        "DROP CONSTRAINT uq_acar_supersedes_once"
    ),
    "uq_cle_run_ordinal": (
        "ALTER TABLE public.control_loop_events DROP CONSTRAINT uq_cle_run_ordinal"
    ),
    "uq_cle_previous": ("ALTER TABLE public.control_loop_events DROP CONSTRAINT uq_cle_previous"),
    "uq_cle_loop_root": "DROP INDEX public.uq_cle_loop_root",
    "uq_pple_previous": (
        "ALTER TABLE public.production_preapproval_lifecycle_events "
        "DROP CONSTRAINT uq_pple_previous"
    ),
    "uq_pple_attestation_event": (
        "ALTER TABLE public.production_preapproval_lifecycle_events "
        "DROP CONSTRAINT uq_pple_attestation_event"
    ),
    "uq_pple_idempotency": (
        "ALTER TABLE public.production_preapproval_lifecycle_events "
        "DROP CONSTRAINT uq_pple_idempotency"
    ),
}
_RESTORE: dict[str, str] = {
    "uq_acar_criterion_sequence": (
        "ALTER TABLE public.acceptance_criterion_authorship_records "
        "ADD CONSTRAINT uq_acar_criterion_sequence "
        "UNIQUE (acceptance_criterion_id, sequence)"
    ),
    "uq_acar_supersedes_once": (
        "ALTER TABLE public.acceptance_criterion_authorship_records "
        "ADD CONSTRAINT uq_acar_supersedes_once UNIQUE (supersedes_record_id)"
    ),
    "uq_cle_run_ordinal": (
        "ALTER TABLE public.control_loop_events "
        "ADD CONSTRAINT uq_cle_run_ordinal UNIQUE (control_loop_run_id, ordinal)"
    ),
    "uq_cle_previous": (
        "ALTER TABLE public.control_loop_events "
        "ADD CONSTRAINT uq_cle_previous UNIQUE (previous_event_id)"
    ),
    "uq_cle_loop_root": (
        "CREATE UNIQUE INDEX uq_cle_loop_root ON public.control_loop_events "
        "(control_loop_run_id) WHERE previous_event_id IS NULL"
    ),
    "uq_pple_previous": (
        "ALTER TABLE public.production_preapproval_lifecycle_events "
        "ADD CONSTRAINT uq_pple_previous UNIQUE (previous_event_id)"
    ),
    "uq_pple_attestation_event": (
        "ALTER TABLE public.production_preapproval_lifecycle_events "
        "ADD CONSTRAINT uq_pple_attestation_event UNIQUE (attestation_id, event_type)"
    ),
    "uq_pple_idempotency": (
        "ALTER TABLE public.production_preapproval_lifecycle_events "
        "ADD CONSTRAINT uq_pple_idempotency "
        "UNIQUE (tenant_id, project_id, idempotency_key_hash)"
    ),
}


@asynccontextmanager
async def without_uniques(admin_engine: AsyncEngine, names: Sequence[str]) -> AsyncIterator[None]:
    """Drop named unique indexes for one mutation, then restore them."""
    async with admin_engine.begin() as conn:
        for name in names:
            await conn.execute(text(_DROP[name]))
    try:
        yield
    finally:
        async with admin_engine.begin() as conn:
            for name in names:
                await conn.execute(text(_RESTORE[name]))


async def seed_ac_bridge(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Requirement + AC + a promotion the unapproved authorship path can cite."""
    world = await seed_approved_requirement(admin_engine)
    async with admin_engine.begin() as conn:
        requirement = (
            await conn.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,data) "
                    "VALUES (:t,:p,'requirement','REQ-S83','R','{}') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO intake_provenance "
                "(tenant_id,project_id,artifact_id,origin) VALUES (:t,:p,:a,'s83')"
            ),
            {"t": world["tenant"], "p": world["project"], "a": requirement},
        )
        ac = (
            await conn.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,data,parent_id) "
                    "VALUES (:t,:p,'acceptance_criterion','AC-S83','AC','{}',:r) "
                    "RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "r": requirement},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO intake_provenance "
                "(tenant_id,project_id,artifact_id,origin) VALUES (:t,:p,:a,'s83')"
            ),
            {"t": world["tenant"], "p": world["project"], "a": ac},
        )
        await conn.execute(
            text(
                "INSERT INTO extraction_promotions "
                "(tenant_id,project_id,extraction_proposal_id,artifact_id,promoted_by) "
                "VALUES (:t,:p,:prop,:a,'s83')"
            ),
            {
                "t": world["tenant"],
                "p": world["project"],
                "prop": world["proposal"],
                "a": ac,
            },
        )
    world["ac"] = ac
    world["requirement"] = requirement
    return world


async def seed_control_loop(rls_engine: AsyncEngine, admin_engine: AsyncEngine) -> dict[str, Any]:
    """Committed cycle so two sessions can race ``append_event``."""
    from app.repositories.go_live_decisions import GoLiveDecisionRepository

    world = await seed_org_tenant_project(admin_engine)
    async with admin_engine.begin() as conn:
        run = (
            await conn.execute(
                text(
                    "INSERT INTO project_runs (tenant_id,project_id,status) "
                    "VALUES (:t,:p,'created') RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(rls_engine) as session:
        await bind_tenant(session, world["tenant"])
        cycle = await GoLiveDecisionRepository(session, ctx).start_cycle(
            project_id=world["project"],
            project_run_id=run,
            idempotency_key=f"s83-loop-{world['sfx']}",
        )
        world["cycle"] = cycle.id
        await session.commit()
    world["run"] = run
    world["ctx"] = ctx
    return world


async def seed_emergency_project(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Committed policy + checklist + autonomy so ``append_binding`` can run."""
    from tests.test_emergency_controls import _checklist, _policy

    world = await seed_org_tenant_project(admin_engine)
    async with admin_engine.begin() as conn:
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
                "policy": json.dumps(_policy()),
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
    world["ctx"] = TenantContext(
        world["tenant"], actor=AuthenticatedActor("stop-a@example.test", "human")
    )
    return world
