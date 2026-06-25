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
        out["key_a"], _ = await repo.issue(
            tenant_id=out["ta"], label="A key", principal_subject="svc-a", actor_type="service"
        )
        out["key_b"], _ = await repo.issue(
            tenant_id=out["tb"], label="B key", principal_subject="svc-b", actor_type="service"
        )
        revoked_raw, revoked_row = await repo.issue(
            tenant_id=out["ta"], label="revoked", principal_subject="svc-r", actor_type="service"
        )
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
        # D4 hardening: resolver function is SECURITY DEFINER owned by api_key_resolver,
        # and uaid_app has EXECUTE on it.
        secdef, owner = (
            await c.execute(
                text(
                    "SELECT prosecdef, pg_get_userbyid(proowner) FROM pg_proc "
                    "WHERE proname='resolve_tenant_api_key'"
                )
            )
        ).one()
        can_exec = (
            await c.execute(
                text(
                    "SELECT has_function_privilege('uaid_app', "
                    "'public.resolve_tenant_api_key(text)', 'EXECUTE')"
                )
            )
        ).scalar_one()
    # hash-only: no raw-key column
    assert cols == {
        "id", "tenant_id", "key_hash", "label", "status", "created_at", "updated_at",
        "principal_subject", "actor_type",  # Slice 27: verified principal binding
    }
    assert not any("raw" in col or "secret" in col or col == "key" for col in cols)
    assert grants == set()  # uaid_app has NO direct key-table read (D4 hardening)
    assert rls is False  # global auth-lookup, intentionally not RLS
    assert secdef is True and owner == "api_key_resolver"  # SECURITY DEFINER, least-priv owner
    assert can_exec is True  # uaid_app may EXECUTE the resolver


@pytest.mark.db
async def test_uaid_app_resolver_execute_not_table_read(api_ctx, rls_engine):
    # uaid_app cannot read the key table directly...
    with pytest.raises(Exception) as ei:
        async with rls_engine.connect() as conn:
            await conn.execute(text("SELECT count(*) FROM tenant_api_keys"))
    assert "permission denied" in str(ei.value).lower()
    # ...but it can EXECUTE the resolver: active hash -> tenant; unknown/revoked -> NULL.
    async with rls_engine.connect() as conn:

        async def _resolve(raw: str):
            # Slice 27: the resolver now returns a (tenant_id, principal_subject, actor_type) row.
            return (
                await conn.execute(
                    text("SELECT tenant_id FROM public.resolve_tenant_api_key(:h)"),
                    {"h": hash_key(raw)},
                )
            ).scalar_one_or_none()

        active = await _resolve(api_ctx["key_a"])
        unknown = await _resolve("uaidk_does_not_exist")
        revoked = await _resolve(api_ctx["key_revoked"])
    assert str(active) == str(api_ctx["ta"])  # active key resolves to its tenant
    assert unknown is None  # uniform NULL — no key-exists oracle
    assert revoked is None


# --- DB-backed: Slice 17 — readiness + findings read endpoints ----------------


async def _record_readiness(project_id, tenant_id):
    """Persist one readiness snapshot via the repo (R0 over an empty spine is fine)."""
    from app.repositories.readiness import ReadinessRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(tenant_id)
    async with tenant_scope(ctx) as session:
        _, row = await ReadinessRepository(session, ctx).evaluate_and_record(
            project_id=project_id, actor="t"
        )
        return row.id


async def _record_findings(project_id, tenant_id):
    """Persist one findings snapshot via the repo (empty spine ⇒ G_NO_REQUIREMENTS gap)."""
    from app.repositories.findings import FindingsRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(tenant_id)
    async with tenant_scope(ctx) as session:
        _, row = await FindingsRepository(session, ctx).evaluate_and_record(
            project_id=project_id, actor="t"
        )
        return row.id


@pytest.mark.db
async def test_readiness_endpoint_returns_latest_snapshot(api_ctx):
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    report_id = await _record_readiness(pa, ta)
    async with _client() as client:
        r = await client.get(f"/api/projects/{pa}/readiness", headers=_auth(api_ctx["key_a"]))
    assert r.status_code == 200
    body = r.json()["readiness"]
    assert body is not None
    assert body["report_id"] == str(report_id)
    assert set(body) >= {
        "report_id",
        "evaluated_at",
        "readiness_level",
        "can_build_to_staging",
        "can_go_live_autonomously",
        "report",
    }
    assert "evaluated_by" not in body  # D-17-1: internal label omitted
    assert body["readiness_level"] == "R0"  # empty spine
    assert body["can_go_live_autonomously"] is False
    assert body["report"]["ruleset_version"]  # full §4.5 doc carried through


@pytest.mark.db
async def test_findings_endpoint_returns_latest_snapshot(api_ctx):
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    report_id = await _record_findings(pa, ta)
    async with _client() as client:
        r = await client.get(f"/api/projects/{pa}/findings", headers=_auth(api_ctx["key_a"]))
    assert r.status_code == 200
    body = r.json()["findings"]
    assert body is not None
    assert body["report_id"] == str(report_id)
    assert set(body) >= {
        "report_id",
        "evaluated_at",
        "gap_count",
        "contradiction_count",
        "report",
    }
    assert "evaluated_by" not in body  # D-17-1
    assert body["gap_count"] >= 1  # empty spine ⇒ G_NO_REQUIREMENTS
    assert "gaps" in body["report"] and "contradictions" in body["report"]


@pytest.mark.db
async def test_readiness_findings_empty_state_returns_null(api_ctx):
    # pa has no snapshot recorded ⇒ honest 200 + null, not 404.
    pa = api_ctx["pa"]
    async with _client() as client:
        rd = await client.get(f"/api/projects/{pa}/readiness", headers=_auth(api_ctx["key_a"]))
        fn = await client.get(f"/api/projects/{pa}/findings", headers=_auth(api_ctx["key_a"]))
    assert rd.status_code == 200 and rd.json() == {"readiness": None}
    assert fn.status_code == 200 and fn.json() == {"findings": None}


@pytest.mark.db
async def test_readiness_findings_cross_tenant_denied(api_ctx):
    # Record snapshots for tenant B's project; key A must not see them (200 + null),
    # while key B sees its own — no cross-tenant leak, no existence oracle.
    tb, pb = api_ctx["tb"], api_ctx["pb"]
    await _record_readiness(pb, tb)
    await _record_findings(pb, tb)
    async with _client() as client:
        rd_cross = await client.get(
            f"/api/projects/{pb}/readiness", headers=_auth(api_ctx["key_a"])
        )
        fn_cross = await client.get(f"/api/projects/{pb}/findings", headers=_auth(api_ctx["key_a"]))
        rd_own = await client.get(f"/api/projects/{pb}/readiness", headers=_auth(api_ctx["key_b"]))
        fn_own = await client.get(f"/api/projects/{pb}/findings", headers=_auth(api_ctx["key_b"]))
    assert rd_cross.status_code == 200 and rd_cross.json() == {"readiness": None}
    assert fn_cross.status_code == 200 and fn_cross.json() == {"findings": None}
    assert rd_own.status_code == 200 and rd_own.json()["readiness"] is not None
    assert fn_own.status_code == 200 and fn_own.json()["findings"] is not None


@pytest.mark.db
async def test_readiness_findings_auth_deny_by_default(api_ctx):
    for kind in ("readiness", "findings"):
        path = f"/api/projects/{api_ctx['pa']}/{kind}"
        async with _client() as client:
            assert (await client.get(path)).status_code == 401  # missing
            assert (await client.get(path, headers={"Authorization": "Basic x"})).status_code == 401
            assert (await client.get(path, headers=_auth("uaidk_bogus"))).status_code == 401
            assert (
                await client.get(path, headers=_auth(api_ctx["key_revoked"]))
            ).status_code == 401
            # authorized request to the same path succeeds — proves auth, not path
            assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200


@pytest.mark.db
async def test_readiness_findings_are_read_only(api_ctx, admin_engine):
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    await _record_readiness(pa, ta)
    await _record_findings(pa, ta)

    async def _count(table: str) -> int:
        async with admin_engine.connect() as c:
            return (
                await c.execute(
                    text(f"SELECT count(*) FROM {table} WHERE tenant_id=:t"),
                    {"t": ta},
                )
            ).scalar_one()

    before = {t: await _count(t) for t in ("readiness_reports", "intake_findings_reports")}
    async with _client() as client:
        for kind in ("readiness", "findings"):
            path = f"/api/projects/{pa}/{kind}"
            assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200
            # write verb to a read-only path is rejected (405), no mutation
            assert (await client.post(path, headers=_auth(api_ctx["key_a"]))).status_code == 405
    # neither GET persists a new snapshot (no evaluate_and_record side effect, either table)
    assert {t: await _count(t) for t in before} == before


@pytest.mark.db
async def test_readiness_returns_most_recent_snapshot(api_ctx):
    # Two snapshots; the endpoint returns the most recent (created_at DESC, id DESC).
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    await _record_readiness(pa, ta)
    second_id = await _record_readiness(pa, ta)
    async with _client() as client:
        r = await client.get(f"/api/projects/{pa}/readiness", headers=_auth(api_ctx["key_a"]))
    assert r.status_code == 200
    assert r.json()["readiness"]["report_id"] == str(second_id)


# --- DB-backed: Slice 19 — readiness + findings history endpoints -------------


@pytest.mark.db
async def test_readiness_history_returns_ordered_snapshots(api_ctx):
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    first = await _record_readiness(pa, ta)
    second = await _record_readiness(pa, ta)
    async with _client() as client:
        r = await client.get(
            f"/api/projects/{pa}/readiness/history", headers=_auth(api_ctx["key_a"])
        )
    assert r.status_code == 200
    hist = r.json()["readiness_history"]
    assert [h["report_id"] for h in hist] == [str(second), str(first)]  # newest-first
    assert set(hist[0]) >= {
        "report_id",
        "evaluated_at",
        "readiness_level",
        "can_build_to_staging",
        "can_go_live_autonomously",
        "report",
    }
    assert "evaluated_by" not in hist[0]  # D-17-1


@pytest.mark.db
async def test_findings_history_returns_ordered_snapshots(api_ctx):
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    first = await _record_findings(pa, ta)
    second = await _record_findings(pa, ta)
    async with _client() as client:
        r = await client.get(
            f"/api/projects/{pa}/findings/history", headers=_auth(api_ctx["key_a"])
        )
    assert r.status_code == 200
    hist = r.json()["findings_history"]
    assert [h["report_id"] for h in hist] == [str(second), str(first)]  # newest-first
    assert set(hist[0]) >= {
        "report_id",
        "evaluated_at",
        "gap_count",
        "contradiction_count",
        "report",
    }
    assert "evaluated_by" not in hist[0]


@pytest.mark.db
async def test_history_empty_state_returns_empty_list(api_ctx):
    pa = api_ctx["pa"]  # no snapshots recorded
    async with _client() as client:
        rd = await client.get(
            f"/api/projects/{pa}/readiness/history", headers=_auth(api_ctx["key_a"])
        )
        fn = await client.get(
            f"/api/projects/{pa}/findings/history", headers=_auth(api_ctx["key_a"])
        )
    assert rd.status_code == 200 and rd.json() == {"readiness_history": []}
    assert fn.status_code == 200 and fn.json() == {"findings_history": []}


@pytest.mark.db
async def test_history_cross_tenant_returns_empty_list(api_ctx):
    # Record snapshots for tenant B's project; key A must see none (empty list, no leak).
    tb, pb = api_ctx["tb"], api_ctx["pb"]
    await _record_readiness(pb, tb)
    await _record_findings(pb, tb)
    async with _client() as client:
        rd_cross = await client.get(
            f"/api/projects/{pb}/readiness/history", headers=_auth(api_ctx["key_a"])
        )
        fn_cross = await client.get(
            f"/api/projects/{pb}/findings/history", headers=_auth(api_ctx["key_a"])
        )
        rd_own = await client.get(
            f"/api/projects/{pb}/readiness/history", headers=_auth(api_ctx["key_b"])
        )
        fn_own = await client.get(
            f"/api/projects/{pb}/findings/history", headers=_auth(api_ctx["key_b"])
        )
    assert rd_cross.status_code == 200 and rd_cross.json() == {"readiness_history": []}
    assert fn_cross.status_code == 200 and fn_cross.json() == {"findings_history": []}
    assert rd_own.status_code == 200 and len(rd_own.json()["readiness_history"]) == 1
    assert fn_own.status_code == 200 and len(fn_own.json()["findings_history"]) == 1


@pytest.mark.db
async def test_history_auth_deny_by_default(api_ctx):
    for kind in ("readiness", "findings"):
        path = f"/api/projects/{api_ctx['pa']}/{kind}/history"
        async with _client() as client:
            assert (await client.get(path)).status_code == 401  # missing
            assert (await client.get(path, headers={"Authorization": "Basic x"})).status_code == 401
            assert (await client.get(path, headers=_auth("uaidk_bogus"))).status_code == 401
            assert (
                await client.get(path, headers=_auth(api_ctx["key_revoked"]))
            ).status_code == 401
            # authorized request to the same path succeeds — proves auth, not path
            assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200


@pytest.mark.db
async def test_history_is_read_only(api_ctx, admin_engine):
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    await _record_readiness(pa, ta)
    await _record_findings(pa, ta)

    async def _count(table: str) -> int:
        async with admin_engine.connect() as c:
            return (
                await c.execute(
                    text(f"SELECT count(*) FROM {table} WHERE tenant_id=:t"),
                    {"t": ta},
                )
            ).scalar_one()

    before = {t: await _count(t) for t in ("readiness_reports", "intake_findings_reports")}
    async with _client() as client:
        for kind in ("readiness", "findings"):
            path = f"/api/projects/{pa}/{kind}/history"
            assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200
            assert (await client.post(path, headers=_auth(api_ctx["key_a"]))).status_code == 405
    # no GET persists a new snapshot (either table)
    assert {t: await _count(t) for t in before} == before


@pytest.mark.db
async def test_latest_and_history_coexist(api_ctx):
    # Both the Slice 17 latest route and the Slice 19 history route resolve (no shadowing).
    ta, pa = api_ctx["ta"], api_ctx["pa"]
    await _record_readiness(pa, ta)
    async with _client() as client:
        latest = await client.get(f"/api/projects/{pa}/readiness", headers=_auth(api_ctx["key_a"]))
        history = await client.get(
            f"/api/projects/{pa}/readiness/history", headers=_auth(api_ctx["key_a"])
        )
    assert latest.status_code == 200 and latest.json()["readiness"] is not None
    assert history.status_code == 200 and len(history.json()["readiness_history"]) == 1


# --- DB-backed: Slice 21 — A5 production-autonomy endpoint ---------------------


@pytest.mark.db
async def test_production_autonomy_endpoint_returns_report(api_ctx):
    pa = api_ctx["pa"]  # empty project ⇒ readiness R0 ⇒ generic not-satisfied report (never null)
    async with _client() as client:
        r = await client.get(
            f"/api/projects/{pa}/production_autonomy", headers=_auth(api_ctx["key_a"])
        )
    assert r.status_code == 200
    body = r.json()["production_autonomy"]
    assert body is not None
    assert body["a5_satisfied"] is False
    assert body["can_go_live_autonomously"] is False
    assert len(body["gates"]) == 13
    assert body["ruleset_version"] == "slice30.v1"


@pytest.mark.db
async def test_production_autonomy_endpoint_returns_slice25_context_shape(api_ctx):
    pa = api_ctx["pa"]
    async with _client() as client:
        r = await client.get(
            f"/api/projects/{pa}/production_autonomy", headers=_auth(api_ctx["key_a"])
        )
    assert r.status_code == 200
    body = r.json()["production_autonomy"]
    assert body["ruleset_version"] == "slice30.v1"
    assert all("context" in g and isinstance(g["context"], dict) for g in body["gates"])
    by_num = {g["number"]: g for g in body["gates"]}
    g7 = by_num[7]
    assert g7["status"] == "insufficient_evidence"
    # no frozen release candidate seeded in the API fixture ⇒ full reason
    assert g7["reason"] == "no_issue_provenance_or_release_binding"
    # Slice 24/25: gate #7 carries risk-acceptance + open-issue + release-binding context
    for k in (
        "active_risk_acceptance_count",
        "open_issue_count",
        "open_blocking_issue_count",
        "open_unaccepted_blocking_issue_count",
        "frozen_release_candidate_count",
        "latest_frozen_release_candidate_id",
        "latest_frozen_release_ref",
        "bound_open_issue_count",
        "bound_open_blocking_issue_count",
        "bound_open_unaccepted_blocking_issue_count",
    ):
        assert k in g7["context"]
    # Slice 23: gates #5/#6 now carry finding-count context (still insufficient_evidence)
    for n in (5, 6):
        assert by_num[n]["status"] == "insufficient_evidence"
        assert by_num[n]["reason"] == "no_finding_provenance_or_scan_source"
    assert "open_security_finding_count" in by_num[5]["context"]
    assert "open_unaccepted_critical_security_finding_count" in by_num[5]["context"]
    assert "open_shortcut_finding_count" in by_num[6]["context"]
    assert "open_unaccepted_critical_shortcut_finding_count" in by_num[6]["context"]
    # Slice 28: gate #3 binds to the project's declared repo; the API fixture declares none ⇒
    # fail-closed branch_protection_repo_unbound (insufficient_evidence, never passes here).
    g3 = by_num[3]
    assert g3["status"] == "insufficient_evidence"
    assert g3["reason"] == "branch_protection_repo_unbound"
    assert g3["context"]["branch_protection_repo_bound"] is False
    assert "repo_ref" not in g3["context"]
    for k in (
        "branch_protection_snapshot_count",
        "connector_verified_branch_protection_count",
        "latest_branch_protection_provenance",
        "latest_branch_protection_enabled",
        "latest_required_status_check_count",
    ):
        assert k in g3["context"]


@pytest.mark.db
async def test_production_autonomy_auth_deny_by_default(api_ctx):
    path = f"/api/projects/{api_ctx['pa']}/production_autonomy"
    async with _client() as client:
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers={"Authorization": "Basic x"})).status_code == 401
        assert (await client.get(path, headers=_auth("uaidk_bogus"))).status_code == 401
        assert (await client.get(path, headers=_auth(api_ctx["key_revoked"]))).status_code == 401
        assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200


@pytest.mark.db
async def test_production_autonomy_cross_tenant_no_leak(api_ctx):
    # key A on tenant B's project ⇒ 200 with a generic not-satisfied report (no B data, gate #1 not passed).
    pb = api_ctx["pb"]
    async with _client() as client:
        r = await client.get(
            f"/api/projects/{pb}/production_autonomy", headers=_auth(api_ctx["key_a"])
        )
    assert r.status_code == 200
    body = r.json()["production_autonomy"]
    assert body["a5_satisfied"] is False
    gate1 = next(g for g in body["gates"] if g["number"] == 1)
    assert gate1["status"] != "passed"


@pytest.mark.db
async def test_production_autonomy_read_only(api_ctx):
    path = f"/api/projects/{api_ctx['pa']}/production_autonomy"
    async with _client() as client:
        assert (await client.get(path, headers=_auth(api_ctx["key_a"]))).status_code == 200
        assert (await client.post(path, headers=_auth(api_ctx["key_a"]))).status_code == 405


# --- DB-backed: Slice 26 — CI evidence (branch protection) read endpoint -------


async def _record_branch_protection(project_id, tenant_id):
    from app.repositories.ci_evidence import CIEvidenceRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(tenant_id)
    async with tenant_scope(ctx) as session:
        row = await CIEvidenceRepository(session, ctx).record_branch_protection(
            project_id=project_id,
            payload={
                "provider": "github",
                "repo_ref": "owner/repo",
                "branch": "main",
                "protection_enabled": True,
                "required_pull_request_reviews": True,
                "required_status_checks": ["ci/build"],
                "enforce_admins": False,
            },
            actor="rev",
        )
        return row.id


@pytest.mark.db
async def test_ci_evidence_endpoint_returns_latest_or_null(api_ctx):
    pa, ta = api_ctx["pa"], api_ctx["ta"]
    async with _client() as client:
        empty = await client.get(f"/api/projects/{pa}/ci_evidence", headers=_auth(api_ctx["key_a"]))
        assert empty.status_code == 200 and empty.json() == {"ci_evidence": None}
    await _record_branch_protection(pa, ta)
    async with _client() as client:
        r = await client.get(f"/api/projects/{pa}/ci_evidence", headers=_auth(api_ctx["key_a"]))
    assert r.status_code == 200
    body = r.json()["ci_evidence"]
    assert body is not None
    assert body["provider"] == "github"
    assert body["protection_enabled"] is True
    assert body["required_status_checks"] == ["ci/build"]
    assert body["required_status_check_count"] == 1
    assert body["provenance"] == "caller_supplied_unverified"


@pytest.mark.db
async def test_ci_evidence_cross_tenant_and_auth_and_read_only(api_ctx):
    pa, pb, tb = api_ctx["pa"], api_ctx["pb"], api_ctx["tb"]
    await _record_branch_protection(pb, tb)  # tenant B's project
    path_a = f"/api/projects/{pa}/ci_evidence"
    async with _client() as client:
        # key A on tenant B's project ⇒ 200 + null (no leak)
        cross = await client.get(f"/api/projects/{pb}/ci_evidence", headers=_auth(api_ctx["key_a"]))
        assert cross.status_code == 200 and cross.json() == {"ci_evidence": None}
        # auth deny-by-default + read-only
        assert (await client.get(path_a)).status_code == 401
        assert (await client.get(path_a, headers=_auth(api_ctx["key_revoked"]))).status_code == 401
        assert (await client.post(path_a, headers=_auth(api_ctx["key_a"]))).status_code == 405
