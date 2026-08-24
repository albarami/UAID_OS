"""Shared Slice-58 DB test helpers. Not a collected test module."""

from __future__ import annotations

import uuid

from app.ops.incidents import IncidentPayload
from app.tenancy import tenant_scope
from tests.admin_support import seed_gated_policy

HOTFIX_TABLES = (
    "ops_self_healing_runs",
    "ops_hotfix_plans",
    "ops_self_healing_results",
)
FINDINGS_GUARD_MD5 = "808036faf2660d6810aeca4342e6f1ac"
DB_CHECKS_SHA = "468837a3afe452239fa392a16cdf1ab90c10938fecb0854478f32606eabb49fc"
INCIDENTS_SHA = "0b5e996c410169b41d3aacd12659d680e3147354cfd23e2dad568a4221eb76c7"


def incident_payload() -> IncidentPayload:
    return IncidentPayload(category="error", severity="high", summary="api 5xx burst")


async def set_policy(ctx, project_id, level, overrides=None, *, admin_engine):
    async with tenant_scope(ctx) as session:
        await seed_gated_policy(
            session=session,
            ctx=ctx,
            project_id=project_id,
            autonomy_level=level,
            overrides=overrides or {},
            admin_engine=admin_engine,
        )


def unique_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
