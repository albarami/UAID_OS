"""Slice 39 — agent realization + factory + broker↔instance wiring (§9/§26.4) tests.

Docker-free: the pure factory validators + qualification-status constants. DB-backed (`db`): the
`agent_realizations` + `agent_realization_reviewers` store + migration 0038 (SELECT/INSERT-only,
unqualified-locked B4, FK-backed reviewers with the actual-blueprint self-review guard B3, RLS, the
agent_instances UNIQUE + tool_calls decision CHECK B2/B6), the factory `realize`, the broker↔instance
wiring (same-project resolution B7 + the always-firing qualification gate), and the bit-stable
no-A5/readiness guard. No qualification (Slice 40), no execution unlocked, no LLM.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.agents.factory import (
    MAX_REVIEWERS_PER_REALIZATION,
    MAX_TOOLS_PER_REALIZATION,
    QUALIFICATION_STATUSES,
    REALIZE_INSERT_STATUS,
    validate_realization_request,
)


def test_qualification_status_constants():
    assert QUALIFICATION_STATUSES == ("unqualified", "qualified")
    assert REALIZE_INSERT_STATUS == "unqualified"  # the only value writable in Slice 39 (B4)
    assert (MAX_TOOLS_PER_REALIZATION, MAX_REVIEWERS_PER_REALIZATION) == (64, 16)


def test_validate_realization_request_ok():
    validate_realization_request(
        instance_key="backend_api_v2",
        tool_allowlist=["read_project_docs", "run_unit_tests"],
        reviewer_blueprint_ids=["11111111-1111-1111-1111-111111111111"],
    )  # no raise


def test_validate_realization_request_rejects_bad_inputs():
    bad = [
        dict(instance_key="", tool_allowlist=[], reviewer_blueprint_ids=[]),  # empty key
        dict(instance_key="bad key!", tool_allowlist=[], reviewer_blueprint_ids=[]),  # key shape
        dict(
            instance_key="k", tool_allowlist=["x"] * 65, reviewer_blueprint_ids=[]
        ),  # too many tools
        dict(instance_key="k", tool_allowlist=[""], reviewer_blueprint_ids=[]),  # empty tool name
        dict(
            instance_key="k", tool_allowlist=[], reviewer_blueprint_ids=["a"] * 17
        ),  # too many reviewers
        dict(
            instance_key="k", tool_allowlist=[], reviewer_blueprint_ids=["not-a-uuid"]
        ),  # bad uuid
    ]
    for kwargs in bad:
        with pytest.raises(ValueError):
            validate_realization_request(**kwargs)


# --- DB-backed: store + migration 0038 guards (B2/B3/B4/RLS/FK) ------------------

_H = "sha256:" + "a" * 64


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def ar_ctx(admin_engine):
    """A global builder blueprint+version + a tenant instance (t1/p1); a distinct reviewer blueprint;
    and a second instance under t2/px (for the cross-project composite-FK test)."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('ArOrg',:s) RETURNING id",
            s=f"ar-org-{sfx}",
        )
        t1 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t1',:s) RETURNING id",
            o=org,
            s=f"ar-t1-{sfx}",
        )
        t2 = await _scalar(
            c,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t2',:s) RETURNING id",
            o=org,
            s=f"ar-t2-{sfx}",
        )
        p1 = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
            t=t1,
            s=f"ar-p1-{sfx}",
        )
        px = await _scalar(
            c,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"ar-px-{sfx}",
        )
        bp_builder = await _scalar(
            c,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) VALUES (:k,'Builder','build','builder') RETURNING id",
            k=f"builder-{sfx}",
        )
        bp_reviewer = await _scalar(
            c,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) VALUES (:k,'Reviewer','review','reviewer') RETURNING id",
            k=f"reviewer-{sfx}",
        )
        ver1 = await _scalar(
            c,
            "INSERT INTO agent_versions (blueprint_id, version_label, model_route, prompt_hash, tool_policy_hash, "
            "context_policy_hash, eval_suite_hash, critical_dependencies_hash, output_schema_hash, content_hash) "
            "VALUES (:b,'v1','m',:h,:h,:h,:h,:h,:h,:ch) RETURNING id",
            b=bp_builder,
            h=_H,
            ch="sha256:" + sfx + "0" * (64 - len(sfx)),
        )
        inst1 = await _scalar(
            c,
            "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) VALUES (:t,:p,:v,:k) RETURNING id",
            t=t1,
            p=p1,
            v=ver1,
            k=f"k1{sfx}",
        )
        inst_px = await _scalar(
            c,
            "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) VALUES (:t,:p,:v,:k) RETURNING id",
            t=t2,
            p=px,
            v=ver1,
            k=f"kx{sfx}",
        )
    return {
        "t1": t1,
        "t2": t2,
        "p1": p1,
        "px": px,
        "bp_builder": bp_builder,
        "bp_reviewer": bp_reviewer,
        "ver1": ver1,
        "inst1": inst1,
        "inst_px": inst_px,
        "sfx": sfx,
    }


async def _realize(conn, ctx, *, status="unqualified", instance=None, project=None, tenant=None):
    return await _scalar(
        conn,
        "INSERT INTO agent_realizations (tenant_id, project_id, instance_id, qualification_status, realized_by) "
        "VALUES (:t,:p,:i,:q,'planner') RETURNING id",
        t=str(tenant or ctx["t1"]),
        p=str(project or ctx["p1"]),
        i=str(instance or ctx["inst1"]),
        q=status,
    )


@pytest.mark.db
async def test_db_realization_insert_unqualified_ok(admin_engine, ar_ctx):
    async with admin_engine.begin() as c:
        rid = await _realize(c, ar_ctx)
    assert rid is not None


@pytest.mark.db
async def test_db_realization_insert_qualified_rejected(admin_engine, ar_ctx):
    # B4 — 'qualified' cannot be INSERT-ed this slice (Slice 40 owns the transition).
    with pytest.raises(Exception, match="must be unqualified|qualified transition is Slice 40"):
        async with admin_engine.begin() as c:
            await _realize(c, ar_ctx, status="qualified")


@pytest.mark.db
async def test_db_realization_no_update_or_delete(admin_engine, ar_ctx):
    # B4 — SELECT/INSERT only.
    async with admin_engine.begin() as c:
        rid = await _realize(c, ar_ctx)
    for sql in (
        "UPDATE agent_realizations SET qualification_status='qualified' WHERE id=:i",
        "DELETE FROM agent_realizations WHERE id=:i",
    ):
        with pytest.raises(Exception, match="append-only"):
            async with admin_engine.begin() as c:
                await c.execute(text(sql), {"i": str(rid)})


@pytest.mark.db
async def test_db_reviewer_self_review_rejected(admin_engine, ar_ctx):
    # B3 — reviewer == the realized agent's ACTUAL blueprint (via instance->version) is refused (§2.2).
    async with admin_engine.begin() as c:
        rid = await _realize(c, ar_ctx)
    with pytest.raises(Exception, match="self-review|cannot be the realized"):
        async with admin_engine.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO agent_realization_reviewers (tenant_id, project_id, realization_id, reviewer_blueprint_id) "
                    "VALUES (:t,:p,:r,:b)"
                ),
                {
                    "t": str(ar_ctx["t1"]),
                    "p": str(ar_ctx["p1"]),
                    "r": str(rid),
                    "b": str(ar_ctx["bp_builder"]),
                },
            )


@pytest.mark.db
async def test_db_reviewer_distinct_blueprint_ok(admin_engine, ar_ctx):
    async with admin_engine.begin() as c:
        rid = await _realize(c, ar_ctx)
        await c.execute(
            text(
                "INSERT INTO agent_realization_reviewers (tenant_id, project_id, realization_id, reviewer_blueprint_id) "
                "VALUES (:t,:p,:r,:b)"
            ),
            {
                "t": str(ar_ctx["t1"]),
                "p": str(ar_ctx["p1"]),
                "r": str(rid),
                "b": str(ar_ctx["bp_reviewer"]),
            },
        )


@pytest.mark.db
async def test_db_realization_cross_project_instance_fk_rejected(admin_engine, ar_ctx):
    # the composite FK (instance_id, project_id, tenant_id) -> agent_instances rejects a px instance under p1.
    with pytest.raises(Exception, match="foreign key|instance_project_tenant"):
        async with admin_engine.begin() as c:
            await _realize(c, ar_ctx, instance=ar_ctx["inst_px"])


@pytest.mark.db
async def test_db_realization_rls_cross_tenant(rls_engine, ar_ctx):
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(ar_ctx["t1"])}
        )
        rid = await _realize(conn, ar_ctx)
        await conn.commit()
    async with rls_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(ar_ctx["t2"])}
        )
        n = (
            await conn.execute(
                text("SELECT count(*) FROM agent_realizations WHERE id=:i"), {"i": str(rid)}
            )
        ).scalar_one()
        assert n == 0


@pytest.mark.db
async def test_db_tool_call_new_decisions_persist(admin_engine, ar_ctx):
    # B2 — ck_tool_calls_decision_valid now admits the two Slice-39 decisions.
    async with admin_engine.begin() as c:
        for decision in ("denied_unknown_agent", "denied_unqualified_agent"):
            await c.execute(
                text(
                    "INSERT INTO tool_calls (tenant_id, project_id, agent_id, tool_name, decision) "
                    "VALUES (:t,:p,'some-agent','some.tool',:d)"
                ),
                {"t": str(ar_ctx["t1"]), "p": str(ar_ctx["p1"]), "d": decision},
            )
