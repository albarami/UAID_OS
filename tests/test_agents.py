"""Slice 6 — agent registry (§9.7 / §17.4 / §22.2) tests.

Docker-free: deterministic ``content_hash``, archetype + sha256 validation.
DB-backed (`db`): version immutability (UPDATE/DELETE/TRUNCATE), idempotency,
global readability, tenant scoping + RLS, FK pinning (run→project→tenant),
binding immutability, instance-key uniqueness, lifecycle + audit, the structural
tenant-content boundary, and catalog/grant proofs.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import (
    ARCHETYPES,
    AgentInstanceRepository,
    InstanceRebindRejected,
    InvalidArchetype,
    InvalidHash,
    compute_content_hash,
    register_blueprint,
    register_version,
)
from app.models.agent_version import COMPONENT_HASH_FIELDS
from app.tenancy import TenantContext, tenant_scope


def _hashes(prompt: str = "a" * 64) -> dict:
    return {
        "prompt_hash": f"sha256:{prompt}",
        "tool_policy_hash": "sha256:" + "1" * 64,
        "context_policy_hash": "sha256:" + "2" * 64,
        "eval_suite_hash": "sha256:" + "3" * 64,
        "critical_dependencies_hash": "sha256:" + "4" * 64,
        "output_schema_hash": "sha256:" + "5" * 64,
    }


# --- Docker-free --------------------------------------------------------------


def test_archetypes_cover_the_canonical_library():
    # §9.5.1 archetype set is present and reviewer/security are distinct entries.
    assert "reviewer" in ARCHETYPES
    assert "security_reviewer" in ARCHETYPES
    assert len(ARCHETYPES) == 11


def test_content_hash_deterministic_and_sensitive_to_every_field():
    bp = uuid.uuid4()
    base = compute_content_hash(
        blueprint_id=bp, version_label="v1", model_route="mr", component_hashes=_hashes()
    )
    # deterministic
    assert base == compute_content_hash(
        blueprint_id=bp, version_label="v1", model_route="mr", component_hashes=_hashes()
    )
    assert base.startswith("sha256:")
    # sensitive to label, model_route, and EACH of the six component hashes
    assert base != compute_content_hash(
        blueprint_id=bp, version_label="v2", model_route="mr", component_hashes=_hashes()
    )
    assert base != compute_content_hash(
        blueprint_id=bp, version_label="v1", model_route="other", component_hashes=_hashes()
    )
    for field in COMPONENT_HASH_FIELDS:
        changed = _hashes()
        changed[field] = "sha256:" + "f" * 64
        assert base != compute_content_hash(
            blueprint_id=bp, version_label="v1", model_route="mr", component_hashes=changed
        ), f"content_hash must change when {field} changes"


async def test_unknown_archetype_rejected():
    with pytest.raises(InvalidArchetype):
        await register_blueprint(
            None, key="k", role="r", mission="m", archetype="wizard", actor="admin"
        )


async def test_non_sha256_component_hash_rejected():
    bad = _hashes()
    bad["tool_policy_hash"] = "not-a-hash"
    with pytest.raises(InvalidHash):
        await register_version(
            None,
            blueprint_id=uuid.uuid4(),
            version_label="v1",
            model_route="mr",
            actor="admin",
            **bad,
        )


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(c, sql, **params):
    return (await c.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def reg(admin_engine):
    """Org + two tenants; tenant1 has projects P1/P2 (+runs R1/R2); tenant2 has PX/RX.
    Plus a global blueprint and one version (V1)."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('AgOrg',:s) RETURNING id",
            s=f"ag-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"ag-{label}-{sfx}",
            )
        # tenant1: P1/R1, P2/R2 ; tenant2: PX/RX
        for proj, tn, run in (("p1", "t1", "r1"), ("p2", "t1", "r2"), ("px", "t2", "rx")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"ag-{proj}-{sfx}",
            )
            out[run] = await _scalar(
                c,
                "INSERT INTO project_runs (tenant_id, project_id, status) "
                "VALUES (:t,:p,'running') RETURNING id",
                t=out[tn],
                p=out[proj],
            )
        # A SECOND run in P1/T1 (valid triple-FK target) for the rebind proof.
        out["r1b"] = await _scalar(
            c,
            "INSERT INTO project_runs (tenant_id, project_id, status) "
            "VALUES (:t,:p,'running') RETURNING id",
            t=out["t1"],
            p=out["p1"],
        )
    async with AsyncSession(admin_engine, expire_on_commit=False) as s:
        bp = await register_blueprint(
            s, key=f"bp-{sfx}", role="Reviewer", mission="m", archetype="reviewer", actor="admin"
        )
        v1 = await register_version(
            s,
            blueprint_id=bp.id,
            version_label="v1",
            model_route="mr",
            actor="admin",
            **_hashes(),
        )
        await s.commit()
        out["blueprint_id"] = bp.id
        out["v1_id"] = v1.id
    return out


# --- DB-backed: global catalog (versions immutable, idempotent, readable) ------


@pytest.mark.db
async def test_register_version_idempotent_changes_make_new_version(reg, admin_engine):
    async with AsyncSession(admin_engine, expire_on_commit=False) as s:
        # identical content => same row
        again = await register_version(
            s,
            blueprint_id=reg["blueprint_id"],
            version_label="v1",
            model_route="mr",
            actor="admin",
            **_hashes(),
        )
        assert again.id == reg["v1_id"]
        # changed content (+ new label) => new row, distinct content_hash
        v2 = await register_version(
            s,
            blueprint_id=reg["blueprint_id"],
            version_label="v2",
            model_route="mr",
            actor="admin",
            **_hashes(prompt="b" * 64),
        )
        await s.commit()
        assert v2.id != reg["v1_id"]
        assert v2.content_hash != (await s.get(type(v2), reg["v1_id"])).content_hash


@pytest.mark.db
async def test_agent_versions_immutable_even_for_admin(reg, admin_engine):
    vid = reg["v1_id"]
    # CASCADE so the TRUNCATE actually reaches the BEFORE TRUNCATE trigger (a plain
    # TRUNCATE is already refused by the agent_instances FK reference — also a raise,
    # but we want to prove the immutability trigger itself fires).
    for stmt, params in (
        ("UPDATE agent_versions SET model_route='x' WHERE id=:v", {"v": vid}),
        ("DELETE FROM agent_versions WHERE id=:v", {"v": vid}),
        ("TRUNCATE agent_versions CASCADE", {}),
    ):
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(text(stmt), params)
        assert "immutable" in str(ei.value).lower()


@pytest.mark.db
async def test_global_catalog_readable_by_runtime(reg, rls_engine):
    # No GUC set: global tables are not RLS'd, uaid_app has SELECT.
    async with rls_engine.connect() as conn:
        bp = (
            await conn.execute(
                text("SELECT count(*) FROM agent_blueprints WHERE id=:b"),
                {"b": reg["blueprint_id"]},
            )
        ).scalar_one()
        ver = (
            await conn.execute(
                text("SELECT count(*) FROM agent_versions WHERE id=:v"), {"v": reg["v1_id"]}
            )
        ).scalar_one()
    assert bp == 1 and ver == 1


# --- DB-backed: tenant-scoped instances ---------------------------------------


@pytest.mark.db
async def test_instance_lifecycle_is_audited(reg, admin_engine):
    t1 = reg["t1"]
    async with tenant_scope(TenantContext(t1)) as session:
        repo = AgentInstanceRepository(session, TenantContext(t1))
        inst = await repo.instantiate(
            project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="admin"
        )
        await repo.bind_to_run(instance_id=inst.id, run_id=reg["r1"], actor="cmdr")
        await repo.suspend(instance_id=inst.id, reason="violation", actor="sec")
        await repo.retire(instance_id=inst.id, actor="cmdr")
        iid = inst.id
    async with admin_engine.connect() as c:
        actions = [
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT action FROM audit_logs WHERE target=:tg AND tenant_id=:t ORDER BY seq"
                    ),
                    {"tg": f"agent_instance:{iid}", "t": t1},
                )
            ).all()
        ]
    assert actions == [
        "agent_instance.registered",
        "agent_instance.bound",
        "agent_instance.suspended",
        "agent_instance.retired",
    ]


@pytest.mark.db
async def test_instances_rls_deny_by_default_and_cross_tenant_write_blocked(reg, rls_engine):
    t1, t2 = reg["t1"], reg["t2"]
    # Seed one instance for tenant1 (committed) via the runtime path.
    async with tenant_scope(TenantContext(t1)) as session:
        await AgentInstanceRepository(session, TenantContext(t1)).instantiate(
            project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
        )
    # No GUC => deny-by-default (0 rows visible).
    async with rls_engine.connect() as conn:
        async with conn.begin():
            assert (
                await conn.execute(text("SELECT count(*) FROM agent_instances"))
            ).scalar_one() == 0
    # GUC=t1, INSERT a row for tenant2 (valid FK target PX) => WITH CHECK violation.
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(
                        "INSERT INTO agent_instances (tenant_id, project_id, version_id, instance_key) "
                        "VALUES (:t,:p,:v,'x')"
                    ),
                    {"t": str(t2), "p": str(reg["px"]), "v": str(reg["v1_id"])},
                )
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


@pytest.mark.db
async def test_run_fk_pins_to_same_project_and_tenant(reg, admin_engine):
    # active_run_id must belong to the SAME project (and tenant) as the instance.
    cases = [
        # same tenant, DIFFERENT project: instance in P1, run R2 (belongs to P2)
        {"t": reg["t1"], "p": reg["p1"], "run": reg["r2"]},
        # cross tenant: instance in P1/T1, run RX (belongs to PX/T2)
        {"t": reg["t1"], "p": reg["p1"], "run": reg["rx"]},
        # project from a different tenant than tenant_id
        {"t": reg["t2"], "p": reg["p1"], "run": None},
    ]
    for case in cases:
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as c:
                await c.execute(
                    text(
                        "INSERT INTO agent_instances "
                        "(tenant_id, project_id, version_id, instance_key, active_run_id) "
                        "VALUES (:t,:p,:v,'k',:r)"
                    ),
                    {
                        "t": str(case["t"]),
                        "p": str(case["p"]),
                        "v": str(reg["v1_id"]),
                        "r": str(case["run"]) if case["run"] else None,
                    },
                )
        assert "foreign key" in str(ei.value).lower() or "violates" in str(ei.value).lower()


@pytest.mark.db
async def test_binding_columns_immutable_under_raw_sql(reg, rls_engine):
    t1 = reg["t1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        inst = await AgentInstanceRepository(session, ctx).instantiate(
            project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
        )
        iid = inst.id
    # Each failing UPDATE aborts its transaction, so isolate each in its own
    # rls_engine (uaid_app) transaction with the GUC set.
    for col, val in (
        ("version_id", str(uuid.uuid4())),
        ("project_id", str(reg["p2"])),
        ("instance_key", "renamed"),
        ("tenant_id", str(reg["t2"])),
    ):
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(
                        text(f"UPDATE agent_instances SET {col}=:val WHERE id=:i"),
                        {"val": val, "i": str(iid)},
                    )
        assert "immutable" in str(ei.value).lower(), f"{col}: {ei.value}"

    # created_at is also frozen (separate stmt: it needs a timestamptz cast).
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text(
                        "UPDATE agent_instances SET created_at = created_at + interval '1 day' "
                        "WHERE id=:i"
                    ),
                    {"i": str(iid)},
                )
    assert "immutable" in str(ei.value).lower(), f"created_at: {ei.value}"


@pytest.mark.db
async def test_active_run_id_is_set_once(reg):
    t1 = reg["t1"]
    async with tenant_scope(TenantContext(t1)) as session:
        ctx = TenantContext(t1)
        repo = AgentInstanceRepository(session, ctx)
        inst = await repo.instantiate(
            project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
        )
        await repo.bind_to_run(instance_id=inst.id, run_id=reg["r1"], actor="a")
        # rebinding to a different run is rejected by the repository guard...
        with pytest.raises(InstanceRebindRejected):
            await repo.bind_to_run(instance_id=inst.id, run_id=reg["r2"], actor="a")


@pytest.mark.db
async def test_active_run_id_rebind_blocked_by_trigger(reg, rls_engine):
    # The DB trigger (not just the repo guard) rejects rebinding a non-NULL
    # active_run_id, even to a run in the SAME project/tenant (so the triple FK
    # passes and the rebind trigger is what fires).
    t1 = reg["t1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = AgentInstanceRepository(session, ctx)
        inst = await repo.instantiate(
            project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
        )
        await repo.bind_to_run(instance_id=inst.id, run_id=reg["r1"], actor="a")
        iid = inst.id
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                )
                await conn.execute(
                    text("UPDATE agent_instances SET active_run_id=:r WHERE id=:i"),
                    {"r": str(reg["r1b"]), "i": str(iid)},
                )
    msg = str(ei.value).lower()
    assert "set-once" in msg or "rebinding" in msg, ei.value


@pytest.mark.db
async def test_repository_cannot_see_other_tenants_instances(reg):
    # App-layer TenantScopedRepository isolation (INV-4), distinct from DB RLS.
    async with tenant_scope(TenantContext(reg["t2"])) as session:
        t2_inst = await AgentInstanceRepository(session, TenantContext(reg["t2"])).instantiate(
            project_id=reg["px"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
        )
        t2_id = t2_inst.id
    async with tenant_scope(TenantContext(reg["t1"])) as session:
        repo = AgentInstanceRepository(session, TenantContext(reg["t1"]))
        assert await repo.get(t2_id) is None
        assert t2_id not in {i.id for i in await repo.list()}


@pytest.mark.db
async def test_live_instance_key_unique_but_retired_frees_it(reg):
    ctx = TenantContext(reg["t1"])
    async with tenant_scope(ctx) as session:
        first = await AgentInstanceRepository(session, ctx).instantiate(
            project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
        )
        first_id = first.id
    # A second LIVE instance with the same (tenant, project, key) => rejected
    # (own transaction — the unique violation aborts it).
    with pytest.raises(Exception) as ei:
        async with tenant_scope(ctx) as session:
            await AgentInstanceRepository(session, ctx).instantiate(
                project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
            )
    assert "unique" in str(ei.value).lower() or "duplicate" in str(ei.value).lower()
    # Retiring the first frees the key (retired rows are outside the partial index).
    async with tenant_scope(ctx) as session:
        repo = AgentInstanceRepository(session, ctx)
        await repo.retire(instance_id=first_id, actor="a")
        reborn = await repo.instantiate(
            project_id=reg["p1"], version_id=reg["v1_id"], instance_key="reviewer", actor="a"
        )
        assert reborn.id != first_id


# --- DB-backed: tenant-content boundary + catalog/grants ----------------------


@pytest.mark.db
async def test_global_catalog_has_no_tenant_content_columns(admin_engine):
    # Structural boundary (Blocker 6): global tables expose ONLY reusable metadata
    # and hashes — no prompt/body/document/content bodies. (The DB cannot detect
    # tenant prose inside role/mission; that is a curation responsibility.)
    async with admin_engine.connect() as c:
        bp_cols = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='agent_blueprints'"
                    )
                )
            ).all()
        }
        ver_cols = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='agent_versions'"
                    )
                )
            ).all()
        }
    assert bp_cols == {
        "id",
        "key",
        "role",
        "mission",
        "archetype",
        "status",
        "created_at",
        "updated_at",
    }
    assert ver_cols == {
        "id",
        "blueprint_id",
        "version_label",
        "model_route",
        "prompt_hash",
        "tool_policy_hash",
        "context_policy_hash",
        "eval_suite_hash",
        "critical_dependencies_hash",
        "output_schema_hash",
        "content_hash",
        "created_at",
    }


@pytest.mark.db
async def test_catalog_rls_grants_and_triggers(admin_engine):
    async with admin_engine.connect() as c:
        # global catalog: uaid_app SELECT-only
        for tbl in ("agent_blueprints", "agent_versions"):
            grants = {
                r[0]
                for r in (
                    await c.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:t AND grantee='uaid_app'"
                        ),
                        {"t": tbl},
                    )
                ).all()
            }
            assert grants == {"SELECT"}, f"{tbl}: {grants}"
        # tenant-owned instances: SELECT/INSERT/UPDATE (no DELETE) + RLS forced
        inst_grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='agent_instances' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert inst_grants == {"SELECT", "INSERT", "UPDATE"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='agent_instances'"
                )
            )
        ).one()
        assert rls == (True, True)
        # immutability/binding triggers present
        trigs = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN "
                        "('agent_versions'::regclass, 'agent_instances'::regclass)"
                    )
                )
            ).all()
        }
    assert {
        "agent_versions_no_update_delete",
        "agent_versions_no_truncate",
        "agent_instances_block_rebind",
    } <= trigs
