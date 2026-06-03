"""Slice 5 — tool broker skeleton (§11) tests.

Docker-free: the code tool registry and deterministic param validation/redaction.
DB-backed (`db`): the broker decision pipeline composing the Slice 3 policy engine
and Slice 4 approval engine, the append-only allowlist ledger, tenant-owned
`tool_calls`, RLS, audit, and catalog/privilege proofs.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.policy.levels import AutonomyLevel as L
from app.repositories.approvals import ApprovalRepository
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.repositories.tools import ToolAllowlistRepository
from app.tenancy import TenantContext, tenant_scope
from app.tools.broker import BrokerDecision, broker_call
from app.tools.registry import TOOL_REGISTRY, InvalidParams, get_contract, sanitize_params

_AGENT = "agent:1"

# --- Docker-free: registry ----------------------------------------------------


def test_unknown_tool_has_no_contract():
    assert get_contract("nope.not_a_tool") is None


def test_known_tool_contract_shape():
    c = get_contract("ci.deploy_production")
    assert c is not None
    assert c.required_action == "deploy_production"
    assert c.requires_approval is True  # §2.6 mandatory


def test_registry_actions_are_strings():
    for name, c in TOOL_REGISTRY.items():
        assert c.tool_name == name
        assert isinstance(c.required_action, str)
        assert isinstance(c.requires_approval, bool)


# --- Docker-free: sanitize_params ---------------------------------------------


def test_non_mapping_params_raise_invalid():
    for bad in (["a"], "x", 5, None):
        with pytest.raises(InvalidParams) as ei:
            sanitize_params(bad)
        assert ei.value.kind == "non_mapping"


def test_secret_like_keys_are_redacted():
    out = sanitize_params(
        {"repo": "r", "api_key": "AKIA123", "password": "p", "nested_token": "t", "ok": 1}
    )
    assert out["repo"] == "r"
    assert out["ok"] == 1
    assert out["api_key"] == "[REDACTED]"
    assert out["password"] == "[REDACTED]"
    assert out["nested_token"] == "[REDACTED]"  # substring match on key


def test_nested_secret_keys_are_redacted_at_any_depth():
    out = sanitize_params(
        {
            "outer": {"api_key": "SECRET", "ok": 1},
            "items": [{"token": "t"}, {"safe": "v"}],
        }
    )
    assert out["outer"]["api_key"] == "[REDACTED]"
    assert out["outer"]["ok"] == 1
    assert out["items"][0]["token"] == "[REDACTED]"  # nested in a list
    assert out["items"][1]["safe"] == "v"


def test_non_finite_floats_rejected():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(InvalidParams) as ei:
            sanitize_params({"x": bad})
        assert ei.value.kind == "invalid_json"
    # also rejected when nested
    with pytest.raises(InvalidParams) as ei:
        sanitize_params({"a": [{"b": float("nan")}]})
    assert ei.value.kind == "invalid_json"


def test_oversized_params_raise_invalid():
    big = {"blob": "x" * 20000}
    with pytest.raises(InvalidParams) as ei:
        sanitize_params(big)
    assert ei.value.kind == "oversized"


def test_non_json_values_are_made_json_safe():
    # A non-JSON-native value (datetime) must come back as its JSON string form, so
    # the result is guaranteed storable in the JSONB `params` column (never errors
    # mid-pipeline). The returned object must round-trip through json cleanly.
    import json

    out = sanitize_params({"when": datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc), "n": 1})
    assert isinstance(out["when"], str) and "2026-06-03" in out["when"]
    assert out["n"] == 1
    assert json.loads(json.dumps(out)) == out  # already JSON-native


def test_broker_decision_has_expected_members():
    names = {d.name for d in BrokerDecision}
    assert names == {
        "ALLOWED_UNVERIFIED_IDENTITY",
        "NEEDS_APPROVAL",
        "NEEDS_AUTHENTICATED_APPROVAL",
        "DENIED_UNKNOWN_TOOL",
        "DENIED_INVALID_PARAMS",
        "DENIED_NOT_ALLOWLISTED",
        "DENIED_POLICY",
    }


# --- DB-backed: broker pipeline, allowlist ledger, RLS, audit, catalog -------


@pytest_asyncio.fixture
async def tool_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org_id = (
            await c.execute(
                text(
                    "INSERT INTO organizations (name, slug) VALUES ('TbOrg','tb-org') "
                    "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id"
                )
            )
        ).scalar_one()
        # Unique tenant per test: the allowlist is keyed by (tenant, agent, tool),
        # so a shared tenant would leak grants across tests.
        tenant_id = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'TbT',:s) RETURNING id"
                ),
                {"o": org_id, "s": f"tb-t-{sfx}"},
            )
        ).scalar_one()
        project_id = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'TbP',:s) RETURNING id"
                ),
                {"t": tenant_id, "s": f"tb-proj-{sfx}"},
            )
        ).scalar_one()
    return tenant_id, project_id


@pytest.mark.db
async def test_unknown_tool_denied_and_recorded_redacted(tool_ctx, admin_engine):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        d = await broker_call(
            session,
            TenantContext(tid),
            project_id=pid,
            agent_id=_AGENT,
            tool_name="nope.tool",
            params={"api_key": "AKIA-SECRET"},
        )
    assert d is BrokerDecision.DENIED_UNKNOWN_TOOL
    async with admin_engine.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT decision, params FROM tool_calls WHERE tenant_id=:t ORDER BY created_at DESC LIMIT 1"
                ),
                {"t": tid},
            )
        ).one()
        assert row[0] == "denied_unknown_tool"
        assert row[1]["api_key"] == "[REDACTED]"  # stored params redacted
        # audit recorded, never with params
        audit = (
            await c.execute(
                text(
                    "SELECT action, payload FROM audit_logs WHERE target='tool:nope.tool' AND tenant_id=:t ORDER BY seq DESC LIMIT 1"
                ),
                {"t": tid},
            )
        ).one()
        assert audit[0] == "tool_call.denied_unknown_tool"
        assert "params" not in audit[1]


@pytest.mark.db
async def test_invalid_params_denied_and_stored_empty(tool_ctx, admin_engine):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        d1 = await broker_call(
            session,
            TenantContext(tid),
            project_id=pid,
            agent_id=_AGENT,
            tool_name="ci.run_tests",
            params=["not", "a", "mapping"],
        )
        d2 = await broker_call(
            session,
            TenantContext(tid),
            project_id=pid,
            agent_id=_AGENT,
            tool_name="ci.run_tests",
            params={"blob": "x" * 20000},
        )
    assert d1 is BrokerDecision.DENIED_INVALID_PARAMS
    assert d2 is BrokerDecision.DENIED_INVALID_PARAMS
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT params FROM tool_calls WHERE tenant_id=:t AND decision='denied_invalid_params'"
                ),
                {"t": tid},
            )
        ).all()
    assert all(r[0] == {} for r in rows)  # invalid-params store {}


@pytest.mark.db
async def test_non_finite_float_param_denied_and_stored_empty(tool_ctx, admin_engine):
    # A non-portable JSON value (NaN) must deterministically deny + store {} — never
    # reach the JSONB column as NaN.
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        d = await broker_call(
            session,
            TenantContext(tid),
            project_id=pid,
            agent_id=_AGENT,
            tool_name="ci.run_tests",
            params={"x": float("nan")},
        )
    assert d is BrokerDecision.DENIED_INVALID_PARAMS
    async with admin_engine.connect() as c:
        params = (
            await c.execute(
                text(
                    "SELECT params FROM tool_calls WHERE tenant_id=:t "
                    "AND decision='denied_invalid_params' ORDER BY created_at DESC LIMIT 1"
                ),
                {"t": tid},
            )
        ).scalar_one()
    assert params == {}


@pytest.mark.db
async def test_not_allowlisted_denied(tool_ctx):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        await AutonomyPolicyRepository(session, TenantContext(tid)).upsert(
            project_id=pid, autonomy_level=int(L.A2), actor="test"
        )
        d = await broker_call(
            session, TenantContext(tid), project_id=pid, agent_id=_AGENT, tool_name="ci.run_tests"
        )
    assert d is BrokerDecision.DENIED_NOT_ALLOWLISTED


@pytest.mark.db
async def test_allowlisted_policy_allow_yields_unverified_identity(tool_ctx):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A2), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="ci.run_tests", actor="admin"
        )
        d = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="ci.run_tests"
        )
    assert d is BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY  # never bare ALLOWED


@pytest.mark.db
async def test_policy_deny(tool_ctx):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A0), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="ci.run_tests", actor="admin"
        )
        d = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="ci.run_tests"
        )
    assert d is BrokerDecision.DENIED_POLICY


@pytest.mark.db
async def test_mandatory_tool_needs_approval_then_unverified(tool_ctx):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A5), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="ci.deploy_production", actor="admin"
        )
        # no approval yet
        d1 = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="ci.deploy_production"
        )
        assert d1 is BrokerDecision.NEEDS_APPROVAL
        # tool-scoped, approved (but unverified provenance)
        a = await ApprovalRepository(session, ctx).request(
            project_id=pid,
            action="deploy_production",
            risk_tier="production",
            requested_by="u",
            subject_ref="tool:ci.deploy_production",
        )
        await ApprovalRepository(session, ctx).approve(approval_id=a.id, actor="boss")
        d2 = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="ci.deploy_production"
        )
    assert d2 is BrokerDecision.NEEDS_AUTHENTICATED_APPROVAL  # unverified approval never authorizes


@pytest.mark.db
async def test_action_level_or_other_tool_approval_does_not_satisfy(tool_ctx):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A5), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="ci.deploy_production", actor="admin"
        )
        # action-level approval (subject_ref NULL) — must NOT satisfy the tool
        a1 = await ApprovalRepository(session, ctx).request(
            project_id=pid,
            action="deploy_production",
            risk_tier="production",
            requested_by="u",
        )
        await ApprovalRepository(session, ctx).approve(approval_id=a1.id, actor="boss")
        d = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="ci.deploy_production"
        )
    assert d is BrokerDecision.NEEDS_APPROVAL


@pytest.mark.db
async def test_contract_requires_approval_over_policy_allow(tool_ctx):
    # pm.create_issue: policy ALLOW at A2, but contract.requires_approval=True.
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A2), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="pm.create_issue", actor="admin"
        )
        d = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="pm.create_issue"
        )
    assert d is BrokerDecision.NEEDS_APPROVAL


@pytest.mark.db
async def test_contract_unverified_approval_yields_authenticated(tool_ctx):
    # pm.create_issue: policy ALLOW at A2 + contract.requires_approval=True. A
    # tool-scoped APPROVED approval whose provenance is unverified must NOT execute
    # — it yields NEEDS_AUTHENTICATED_APPROVAL (the contract gate, not the policy gate).
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A2), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="pm.create_issue", actor="admin"
        )
        a = await ApprovalRepository(session, ctx).request(
            project_id=pid,
            action="create_project_tasks",
            risk_tier="medium",
            requested_by="u",
            subject_ref="tool:pm.create_issue",
        )
        await ApprovalRepository(session, ctx).approve(approval_id=a.id, actor="boss")
        d = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="pm.create_issue"
        )
    assert d is BrokerDecision.NEEDS_AUTHENTICATED_APPROVAL


@pytest.mark.db
async def test_bogus_provenance_still_needs_authenticated_approval(tool_ctx):
    # Fail-closed: ANY provenance not on the (empty) authenticated allowlist — even
    # an arbitrary/forged string like 'bogus' — must NOT authorize. Proves the gate
    # is allowlist-based, not "anything except the unverified default".
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A5), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="ci.deploy_production", actor="admin"
        )
        a = await ApprovalRepository(session, ctx).request(
            project_id=pid,
            action="deploy_production",
            risk_tier="production",
            requested_by="u",
            subject_ref="tool:ci.deploy_production",
        )
        await ApprovalRepository(session, ctx).approve(approval_id=a.id, actor="boss")
        # Forge a non-default provenance value directly on the row.
        await session.execute(
            text("UPDATE approvals SET approver_provenance='bogus' WHERE id=:id"),
            {"id": str(a.id)},
        )
        d = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="ci.deploy_production"
        )
    assert d is BrokerDecision.NEEDS_AUTHENTICATED_APPROVAL


@pytest.mark.db
async def test_other_tool_approval_does_not_satisfy(tool_ctx):
    # An APPROVED approval scoped to a DIFFERENT tool (subject_ref='tool:other') must
    # NOT authorize ci.deploy_production — no cross-tool approval reuse.
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A5), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="ci.deploy_production", actor="admin"
        )
        a = await ApprovalRepository(session, ctx).request(
            project_id=pid,
            action="deploy_production",
            risk_tier="production",
            requested_by="u",
            subject_ref="tool:other",
        )
        await ApprovalRepository(session, ctx).approve(approval_id=a.id, actor="boss")
        d = await broker_call(
            session, ctx, project_id=pid, agent_id=_AGENT, tool_name="ci.deploy_production"
        )
    assert d is BrokerDecision.NEEDS_APPROVAL


@pytest.mark.db
async def test_non_json_param_value_stored_json_safe(tool_ctx, admin_engine):
    # End-to-end: a non-JSON-native param value reaches the JSONB column as its
    # string form — the brokered call records deterministically, never errors.
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=pid, autonomy_level=int(L.A2), actor="t"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id=_AGENT, tool_name="ci.run_tests", actor="admin"
        )
        d = await broker_call(
            session,
            ctx,
            project_id=pid,
            agent_id=_AGENT,
            tool_name="ci.run_tests",
            params={"when": datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)},
        )
    assert d is BrokerDecision.ALLOWED_UNVERIFIED_IDENTITY
    async with admin_engine.connect() as c:
        params = (
            await c.execute(
                text(
                    "SELECT params FROM tool_calls WHERE tenant_id=:t "
                    "AND decision='allowed_unverified_identity' ORDER BY created_at DESC LIMIT 1"
                ),
                {"t": tid},
            )
        ).scalar_one()
    assert isinstance(params["when"], str) and "2026-06-03" in params["when"]


@pytest.mark.db
async def test_allowlist_grant_revoke_regrant(tool_ctx):
    tid, pid = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        repo = ToolAllowlistRepository(session, ctx)
        assert await repo.is_allowed(_AGENT, "ci.run_tests") is False  # deny-by-default
        await repo.grant(agent_id=_AGENT, tool_name="ci.run_tests", actor="admin")
        assert await repo.is_allowed(_AGENT, "ci.run_tests") is True
        await repo.revoke(agent_id=_AGENT, tool_name="ci.run_tests", actor="admin", reason="rotate")
        assert await repo.is_allowed(_AGENT, "ci.run_tests") is False
        await repo.grant(agent_id=_AGENT, tool_name="ci.run_tests", actor="admin")
        assert await repo.is_allowed(_AGENT, "ci.run_tests") is True


@pytest.mark.db
async def test_allowlist_grant_and_revoke_are_audited(tool_ctx, admin_engine):
    # Both grant and revoke must leave audit-log entries with safe metadata (no secrets).
    tid, _ = tool_ctx
    async with tenant_scope(TenantContext(tid)) as session:
        ctx = TenantContext(tid)
        repo = ToolAllowlistRepository(session, ctx)
        await repo.grant(agent_id=_AGENT, tool_name="ci.run_tests", actor="admin")
        await repo.revoke(agent_id=_AGENT, tool_name="ci.run_tests", actor="admin", reason="rotate")
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT action, payload FROM audit_logs WHERE tenant_id=:t "
                    "AND action LIKE 'tool_allowlist.%' ORDER BY seq"
                ),
                {"t": tid},
            )
        ).all()
    actions = [r[0] for r in rows]
    assert "tool_allowlist.grant" in actions
    assert "tool_allowlist.revoke" in actions
    for _action, payload in rows:
        assert payload["tool_name"] == "ci.run_tests"
        assert payload["agent_id"] == _AGENT
        assert "reason" not in payload  # safe metadata only — no free-text reason


@pytest.mark.db
async def test_rls_deny_by_default_both_tables(rls_engine, admin_engine, tool_ctx):
    tid, pid = tool_ctx
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO tool_calls (tenant_id, project_id, agent_id, tool_name, decision) "
                "VALUES (:t,:p,'a','ci.run_tests','denied_policy')"
            ),
            {"t": tid, "p": pid},
        )
        await c.execute(
            text(
                "INSERT INTO agent_tool_allowlist (tenant_id, agent_id, tool_name, event_type, actor) "
                "VALUES (:t,'a','ci.run_tests','grant','admin')"
            ),
            {"t": tid},
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            assert (await conn.execute(text("SELECT count(*) FROM tool_calls"))).scalar_one() == 0
            assert (
                await conn.execute(text("SELECT count(*) FROM agent_tool_allowlist"))
            ).scalar_one() == 0


@pytest.mark.db
async def test_catalog_and_grants(admin_engine):
    async with admin_engine.connect() as c:
        for tbl in ("tool_calls", "agent_tool_allowlist"):
            rls = (
                await c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=:t"
                    ),
                    {"t": tbl},
                )
            ).one()
            assert rls == (True, True)
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
            assert grants == {"SELECT", "INSERT"}  # append-only: no UPDATE/DELETE


@pytest_asyncio.fixture
async def two_tool_tenants(admin_engine):
    """Two tenants, each with a project (so tool_calls' composite FK is valid)."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org_id = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('TbRLS',:s) RETURNING id"),
                {"s": f"tb-rls-{sfx}"},
            )
        ).scalar_one()
        out = {}
        for label in ("a", "b"):
            t = (
                await c.execute(
                    text(
                        "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id"
                    ),
                    {"o": org_id, "n": label, "s": f"tb-{label}-{sfx}"},
                )
            ).scalar_one()
            p = (
                await c.execute(
                    text(
                        "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id"
                    ),
                    {"t": t, "s": f"tb-{label}-proj-{sfx}"},
                )
            ).scalar_one()
            out[label] = {"tenant": t, "project": p}
    return out


@pytest.mark.db
async def test_tool_calls_cross_tenant_write_blocked(rls_engine, two_tool_tenants):
    a, b = two_tool_tenants["a"], two_tool_tenants["b"]

    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(a["tenant"])},
                )
                # GUC=A; write a tool_call for tenant B (valid composite FK) -> WITH CHECK.
                await conn.execute(
                    text(
                        "INSERT INTO tool_calls (tenant_id, project_id, agent_id, tool_name, decision) "
                        "VALUES (:t,:p,'a','ci.run_tests','denied_policy')"
                    ),
                    {"t": str(b["tenant"]), "p": str(b["project"])},
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


@pytest.mark.db
async def test_allowlist_cross_tenant_write_blocked(rls_engine, two_tool_tenants):
    a, b = two_tool_tenants["a"], two_tool_tenants["b"]

    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": str(a["tenant"])},
                )
                # GUC=A; write an allowlist event for tenant B -> WITH CHECK violation.
                await conn.execute(
                    text(
                        "INSERT INTO agent_tool_allowlist (tenant_id, agent_id, tool_name, event_type, actor) "
                        "VALUES (:t,'a','ci.run_tests','grant','admin')"
                    ),
                    {"t": str(b["tenant"])},
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()
