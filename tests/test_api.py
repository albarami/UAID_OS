"""Slice 10 — read-only dashboard API + bearer-key tenant auth (§18.6) tests.

Docker-free: bearer parsing, key hashing/generation.
DB-backed (`db`): real HTTP via httpx AsyncClient + ASGITransport through the actual
auth dependency → tenant_scope/RLS path — happy reads, deny-by-default 401s,
cross-tenant denial, read-only, and the tenant_api_keys catalog (hash-only, SELECT).
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import parse_bearer
from app.main import app
from app.repositories.api_keys import TenantApiKeyRepository, generate_raw_key, hash_key

# --- Docker-free --------------------------------------------------------------


def test_parse_bearer():
    assert parse_bearer("Bearer abc123") == "abc123"
    assert parse_bearer("bearer abc123") == "abc123"  # scheme case-insensitive
    assert parse_bearer("Bearer    ") is None  # empty token
    assert parse_bearer("Basic abc") is None
    assert parse_bearer("abc") is None
    assert parse_bearer("") is None
    assert parse_bearer(None) is None


def test_key_hash_and_generation():
    raw = generate_raw_key()
    assert raw.startswith("uaidk_") and len(raw) > 30
    assert generate_raw_key() != generate_raw_key()  # high-entropy, distinct
    h = hash_key(raw)
    assert h.startswith("sha256:") and len(h) == len("sha256:") + 64
    assert hash_key(raw) == h  # deterministic
    assert hash_key("other") != h


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(c, sql, **p):
    return (await c.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def api_ctx(admin_engine):
    """Two tenants (A, B) each with a project + a run; A also has a blocked run.
    Issues active keys for A and B, plus a revoked key for A."""
    sfx = uuid.uuid4().hex[:8]
    out = {"sfx": sfx}
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('ApiOrg',:s) RETURNING id",
            s=f"api-org-{sfx}",
        )
        for label in ("ta", "tb"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"api-{label}-{sfx}",
            )
        for proj, tn in (("pa", "ta"), ("pb", "tb")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"api-{proj}-{sfx}",
            )
        out["run_a"] = await _scalar(
            c,
            "INSERT INTO project_runs (tenant_id, project_id, status) VALUES (:t,:p,'running') RETURNING id",
            t=out["ta"],
            p=out["pa"],
        )
        out["run_a_blocked"] = await _scalar(
            c,
            "INSERT INTO project_runs (tenant_id, project_id, status) VALUES (:t,:p,'blocked') RETURNING id",
            t=out["ta"],
            p=out["pa"],
        )
        out["run_b"] = await _scalar(
            c,
            "INSERT INTO project_runs (tenant_id, project_id, status) VALUES (:t,:p,'running') RETURNING id",
            t=out["tb"],
            p=out["pb"],
        )
    async with AsyncSession(admin_engine, expire_on_commit=False) as s:
        repo = TenantApiKeyRepository(s)
        out["key_a"], _ = await repo.issue(tenant_id=out["ta"], label="A key")
        out["key_b"], _ = await repo.issue(tenant_id=out["tb"], label="B key")
        revoked_raw, revoked_row = await repo.issue(tenant_id=out["ta"], label="revoked")
        await repo.revoke(key_id=revoked_row.id)
        out["key_revoked"] = revoked_raw
        await s.commit()
    return out


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(raw: str) -> dict:
    return {"Authorization": f"Bearer {raw}"}


# --- DB-backed: happy path ----------------------------------------------------


@pytest.mark.db
async def test_runs_endpoint_returns_tenant_runs(api_ctx):
    async with _client() as client:
        r = await client.get(f"/api/projects/{api_ctx['pa']}/runs", headers=_auth(api_ctx["key_a"]))
    assert r.status_code == 200
    statuses = {row["status"] for row in r.json()["runs"]}
    assert statuses == {"running", "blocked"}  # both A runs, scoped to A


@pytest.mark.db
async def test_blockers_and_cost_endpoints(api_ctx):
    from app.repositories.cost import BudgetRepository, CostEventRepository
    from app.tenancy import TenantContext, tenant_scope

    ta, pa = api_ctx["ta"], api_ctx["pa"]
    ctx = TenantContext(ta)
    async with tenant_scope(ctx) as session:
        await BudgetRepository(session, ctx).upsert(
            project_id=pa, max_total_cost_usd="10", actor="t"
        )
        await CostEventRepository(session, ctx).record(
            project_id=pa, component="model_inference", amount_usd="25", actor="t"
        )
    async with _client() as client:
        b = await client.get(f"/api/projects/{pa}/blockers", headers=_auth(api_ctx["key_a"]))
        c = await client.get(f"/api/projects/{pa}/cost", headers=_auth(api_ctx["key_a"]))
    assert b.status_code == 200
    assert any(run["status"] == "blocked" for run in b.json()["blocked_runs"])
    assert c.status_code == 200
    body = c.json()
    assert body["total_spent"] == "25.000000"
    assert body["budget"]["max_total_cost_usd"] == "10.000000"
    assert body["decision"]["stop"] is True and body["decision"]["reason"] == "budget_exceeded"


@pytest.mark.db
async def test_approvals_endpoint(api_ctx):
    from app.repositories.approvals import ApprovalRepository
    from app.tenancy import TenantContext, tenant_scope

    ta, pa, tb, pb = api_ctx["ta"], api_ctx["pa"], api_ctx["tb"], api_ctx["pb"]
    # tenant A: one PENDING + one resolved (approved); tenant B: one PENDING
    async with tenant_scope(TenantContext(ta)) as session:
        ar = ApprovalRepository(session, TenantContext(ta))
        pending = await ar.request(
            project_id=pa,
            action="deploy_staging",
            risk_tier="medium",
            requested_by="u",
            subject_ref="run:x:node:y",
        )
        resolved = await ar.request(
            project_id=pa, action="run_tests", risk_tier="low", requested_by="u"
        )
        await ar.approve(approval_id=resolved.id, actor="boss")
        pending_id, resolved_id = str(pending.id), str(resolved.id)
    async with tenant_scope(TenantContext(tb)) as session:
        await ApprovalRepository(session, TenantContext(tb)).request(
            project_id=pb, action="deploy_staging", risk_tier="medium", requested_by="u"
        )
    async with _client() as client:
        own = await client.get(f"/api/projects/{pa}/approvals", headers=_auth(api_ctx["key_a"]))
        cross = await client.get(f"/api/projects/{pb}/approvals", headers=_auth(api_ctx["key_a"]))
        blockers = await client.get(f"/api/projects/{pa}/blockers", headers=_auth(api_ctx["key_a"]))
    assert own.status_code == 200
    open_ids = {a["id"] for a in own.json()["open_approvals"]}
    assert pending_id in open_ids  # PENDING surfaced
    assert resolved_id not in open_ids  # resolved excluded
    entry = next(a for a in own.json()["open_approvals"] if a["id"] == pending_id)
    assert set(entry) >= {"id", "action", "subject_ref", "risk_tier", "requested_at"}
    assert entry["action"] == "deploy_staging" and entry["subject_ref"] == "run:x:node:y"
    # cross-tenant: B's pending approval is hidden from key A
    assert cross.status_code == 200 and cross.json()["open_approvals"] == []
    # blockers surfaces the same open approvals
    assert pending_id in {a["id"] for a in blockers.json()["open_approvals"]}


# --- DB-backed: deny-by-default 401 -------------------------------------------


@pytest.mark.db
async def test_auth_deny_by_default(api_ctx):
    path = f"/api/projects/{api_ctx['pa']}/runs"
    async with _client() as client:
        assert (await client.get(path)).status_code == 401  # missing
        assert (await client.get(path, headers={"Authorization": "Basic x"})).status_code == 401
        assert (await client.get(path, headers=_auth("uaidk_bogus"))).status_code == 401  # unknown
        assert (await client.get(path, headers=_auth(api_ctx["key_revoked"]))).status_code == 401
        # an authorized request to the same path succeeds — proves it's auth, not the path
        assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200


# --- DB-backed: cross-tenant denial through HTTP -> auth -> tenant_scope/RLS ---


@pytest.mark.db
async def test_cross_tenant_reads_denied(api_ctx):
    async with _client() as client:
        # key A asking for tenant B's project => no B data (empty), never B's run
        cross = await client.get(
            f"/api/projects/{api_ctx['pb']}/runs", headers=_auth(api_ctx["key_a"])
        )
        own = await client.get(
            f"/api/projects/{api_ctx['pa']}/runs", headers=_auth(api_ctx["key_a"])
        )
    assert cross.status_code == 200 and cross.json()["runs"] == []  # B hidden from A
    assert own.status_code == 200 and len(own.json()["runs"]) == 2  # A sees its own


# --- DB-backed: read-only -----------------------------------------------------


@pytest.mark.db
async def test_endpoints_are_read_only(api_ctx, admin_engine):
    path = f"/api/projects/{api_ctx['pa']}/runs"

    async def _run_count() -> int:
        async with admin_engine.connect() as c:
            return (
                await c.execute(
                    text("SELECT count(*) FROM project_runs WHERE tenant_id=:t"),
                    {"t": api_ctx["ta"]},
                )
            ).scalar_one()

    before = await _run_count()
    async with _client() as client:
        assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200
        # a write method to a read-only path is rejected (405), no mutation
        assert (await client.post(path, headers=_auth(api_ctx["key_a"]))).status_code == 405
    assert await _run_count() == before


# --- DB-backed: catalog -------------------------------------------------------


@pytest.mark.db
async def test_tenant_api_keys_catalog(admin_engine):
    async with admin_engine.connect() as c:
        cols = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='tenant_api_keys'"
                    )
                )
            ).all()
        }
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='tenant_api_keys' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        rls = (
            await c.execute(
                text("SELECT relrowsecurity FROM pg_class WHERE relname='tenant_api_keys'")
            )
        ).scalar_one()
    # hash-only: no raw-key column
    assert cols == {"id", "tenant_id", "key_hash", "label", "status", "created_at", "updated_at"}
    assert not any("raw" in col or "secret" in col or col == "key" for col in cols)
    assert grants == {"SELECT"}  # runtime resolve only
    assert rls is False  # global auth-lookup, intentionally not RLS
