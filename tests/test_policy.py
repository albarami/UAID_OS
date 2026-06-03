"""Slice 3 — autonomy policy engine (§5, §2.6) tests.

Docker-free: the pure authority-matrix decision logic and tighten-only override
rules. DB-backed (`db`): tenant-owned `autonomy_policies` RLS, repository,
`decision_for`, audit-on-upsert, and catalog/privilege proofs.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.policy.engine import Decision, PolicyOverrideError, check_authority
from app.policy.levels import AutonomyLevel as L
from app.policy.matrix import validate_overrides
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.tenancy import TenantContext, tenant_scope

# --- Docker-free: pure engine -------------------------------------------------

_A1_MANUAL = [
    "delete_resources",
    "change_secrets",
    "modify_billing_or_paid_resources",
    "send_external_communications",
    "access_sensitive_data",
    "accept_risk",
    "override_failed_gate",
    "weaken_test_or_review_standards",
]
_A4_APPROVAL = ["merge_to_protected", "deploy_production"]


def test_unknown_action_is_denied():
    assert check_authority("nope_not_an_action", L.A5) is Decision.DENY


def test_a0_allows_only_read_docs():
    assert check_authority("read_docs", L.A0) is Decision.ALLOW
    for action in ("create_draft_prd", "create_branches", "run_tests", "deploy_staging"):
        assert check_authority(action, L.A0) is Decision.DENY


def test_a2_allows_build_actions_denies_higher():
    for action in (
        "create_repository",
        "create_branches",
        "commit_code",
        "open_pull_requests",
        "run_tests",
    ):
        assert check_authority(action, L.A2) is Decision.ALLOW
    assert check_authority("deploy_staging", L.A2) is Decision.DENY
    assert check_authority("deploy_production", L.A2) is Decision.DENY


def test_a3_allows_staging():
    assert check_authority("deploy_staging", L.A3) is Decision.ALLOW
    assert check_authority("deploy_staging", L.A2) is Decision.DENY


def test_a4_actions_deny_below_a4_needs_approval_at_a4_plus():
    for action in _A4_APPROVAL:
        for level in (L.A0, L.A1, L.A2, L.A3):
            assert check_authority(action, level) is Decision.DENY
        for level in (L.A4, L.A5):
            assert check_authority(action, level) is Decision.NEEDS_APPROVAL


def test_a1_manual_actions_deny_at_a0_needs_approval_a1_plus():
    for action in _A1_MANUAL:
        assert check_authority(action, L.A0) is Decision.DENY
        for level in (L.A1, L.A2, L.A3, L.A4, L.A5):
            assert check_authority(action, level) is Decision.NEEDS_APPROVAL


def test_override_can_tighten_min_level():
    # run_tests is A2 by default; raise it to A4.
    overrides = {"run_tests": {"min_level": int(L.A4)}}
    assert check_authority("run_tests", L.A2, overrides) is Decision.DENY
    assert check_authority("run_tests", L.A4, overrides) is Decision.ALLOW


def test_override_can_add_approval_requirement():
    overrides = {"run_tests": {"requires_approval": True}}
    assert check_authority("run_tests", L.A2, overrides) is Decision.NEEDS_APPROVAL


def test_override_can_disable_action():
    overrides = {"run_tests": {"allow": False}}
    assert check_authority("run_tests", L.A5, overrides) is Decision.DENY


@pytest.mark.parametrize(
    "action,override",
    [
        ("run_tests", {"min_level": int(L.A0)}),  # lowering min_level
        ("deploy_production", {"requires_approval": False}),  # clearing §2.6 approval
        ("deploy_production", {"allow": True}),  # enabling a §2.6 action
        ("run_tests", {"allow": True}),  # allow may only be False
        ("run_tests", {"bogus_key": 1}),  # unknown override key
    ],
)
def test_relaxing_or_invalid_overrides_raise_in_check_authority(action, override):
    with pytest.raises(PolicyOverrideError):
        check_authority(action, L.A5, {action: override})


def test_validate_overrides_rejects_unknown_action_and_relaxing():
    validate_overrides({"run_tests": {"min_level": int(L.A4)}})  # valid tighten: no raise
    with pytest.raises(PolicyOverrideError):
        validate_overrides({"not_a_real_action": {"min_level": 2}})  # unknown action key
    with pytest.raises(PolicyOverrideError):
        validate_overrides({"run_tests": {"min_level": int(L.A0)}})  # relaxing


@pytest.mark.parametrize(
    "bad_min_level",
    ["abc", None, True, 6, 1.5, [3]],  # non-int, None, bool, > A5, float, list
)
def test_malformed_min_level_raises_policy_override_error(bad_min_level):
    with pytest.raises(PolicyOverrideError):
        validate_overrides({"run_tests": {"min_level": bad_min_level}})


def test_bool_min_level_rejected_even_on_a0_action():
    # read_docs is A0; without an explicit bool guard, True would coerce to 1
    # and be silently accepted as a "tighten" — it must be rejected instead.
    with pytest.raises(PolicyOverrideError):
        validate_overrides({"read_docs": {"min_level": True}})


def test_section_2_6_actions_cannot_be_made_allow():
    for action in _A1_MANUAL + _A4_APPROVAL:
        # Even with an aggressive override, the best a tighten-only system yields
        # for a mandatory-approval action is NEEDS_APPROVAL or DENY — never ALLOW.
        with pytest.raises(PolicyOverrideError):
            check_authority(action, L.A5, {action: {"requires_approval": False}})
        assert check_authority(action, L.A5) is not Decision.ALLOW


def test_monotonicity_non_approval_actions():
    non_approval = [
        "read_docs",
        "create_draft_prd",
        "create_branches",
        "run_tests",
        "deploy_staging",
    ]
    for action in non_approval:
        allowed = [lvl for lvl in L if check_authority(action, lvl) is Decision.ALLOW]
        # allowed levels form a contiguous top range (monotonic).
        if allowed:
            assert allowed == [lvl for lvl in L if lvl >= min(allowed)]


# --- DB-backed: storage, decision_for, RLS, audit, catalog --------------------


@pytest_asyncio.fixture
async def policy_project(admin_engine):
    """Idempotent org/tenant + a UNIQUE project per test (admin-seeded)."""
    suffix = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org_id = (
            await c.execute(
                text(
                    "INSERT INTO organizations (name, slug) VALUES ('PolOrg','pol-org') "
                    "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id"
                )
            )
        ).scalar_one()
        tenant_id = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'PolT','pol-t') "
                    "ON CONFLICT (organization_id, slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id"
                ),
                {"o": org_id},
            )
        ).scalar_one()
        project_id = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PolProj',:s) RETURNING id"
                ),
                {"t": tenant_id, "s": f"pol-proj-{suffix}"},
            )
        ).scalar_one()
    return tenant_id, project_id


@pytest.mark.db
async def test_missing_policy_denies_all(policy_project):
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        assert await repo.decision_for(project_id, "read_docs") is Decision.DENY
        assert await repo.decision_for(project_id, "create_branches") is Decision.DENY


@pytest.mark.db
async def test_upsert_then_decision_reflects_level(policy_project):
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        await repo.upsert(project_id=project_id, autonomy_level=int(L.A2), actor="test:setup")
        assert await repo.decision_for(project_id, "create_branches") is Decision.ALLOW
        assert await repo.decision_for(project_id, "deploy_staging") is Decision.DENY
        assert await repo.decision_for(project_id, "deploy_production") is Decision.DENY


@pytest.mark.db
async def test_upsert_tighten_override_takes_effect(policy_project):
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        await repo.upsert(
            project_id=project_id,
            autonomy_level=int(L.A3),
            overrides={"run_tests": {"requires_approval": True}},
            actor="test:setup",
        )
        assert await repo.decision_for(project_id, "run_tests") is Decision.NEEDS_APPROVAL


@pytest.mark.db
async def test_upsert_rejects_relaxing_override(policy_project):
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        with pytest.raises(PolicyOverrideError):
            await repo.upsert(
                project_id=project_id,
                autonomy_level=int(L.A5),
                overrides={"deploy_production": {"requires_approval": False}},
                actor="test:setup",
            )


@pytest.mark.db
async def test_decision_for_fail_closed_on_invalid_persisted_override(policy_project, admin_engine):
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        await repo.upsert(project_id=project_id, autonomy_level=int(L.A5), actor="test:setup")
    # Inject an invalid/relaxing override directly (admin bypasses validation).
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                'UPDATE autonomy_policies SET overrides = \'{"deploy_production": {"requires_approval": false}}\'::jsonb '
                "WHERE project_id = :p"
            ),
            {"p": project_id},
        )
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        assert await repo.decision_for(project_id, "deploy_production") is Decision.DENY


@pytest.mark.db
async def test_decision_for_fail_closed_on_invalid_UNRELATED_override(policy_project, admin_engine):
    # An invalid/relaxing persisted override for a DIFFERENT action must fail the
    # whole map closed — even when querying an unrelated action.
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        await repo.upsert(project_id=project_id, autonomy_level=int(L.A5), actor="test:setup")
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "UPDATE autonomy_policies SET overrides = "
                "'{\"deploy_production\": {\"requires_approval\": false}}'::jsonb "
                "WHERE project_id = :p"
            ),
            {"p": project_id},
        )
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        # read_docs would normally be ALLOW at A5; the invalid map must force DENY.
        assert await repo.decision_for(project_id, "read_docs") is Decision.DENY


@pytest.mark.db
async def test_decision_for_fail_closed_on_malformed_persisted_min_level(policy_project, admin_engine):
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        await repo.upsert(project_id=project_id, autonomy_level=int(L.A5), actor="test:setup")
    # Admin-inject a malformed (non-integer) min_level (bypasses write validation).
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "UPDATE autonomy_policies SET overrides = "
                "'{\"run_tests\": {\"min_level\": \"abc\"}}'::jsonb WHERE project_id = :p"
            ),
            {"p": project_id},
        )
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        # Must fail closed (not raise a raw ValueError through the repository).
        assert await repo.decision_for(project_id, "read_docs") is Decision.DENY


@pytest.mark.db
async def test_upsert_writes_audit_event(policy_project, admin_engine):
    tenant_id, project_id = policy_project
    async with tenant_scope(TenantContext(tenant_id)) as session:
        repo = AutonomyPolicyRepository(session, TenantContext(tenant_id))
        await repo.upsert(
            project_id=project_id,
            autonomy_level=int(L.A2),
            overrides={"run_tests": {"requires_approval": True}},
            actor="test:setup",
        )
    async with admin_engine.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT tenant_id, action, payload FROM audit_logs "
                    "WHERE action='autonomy_policy.upserted' AND payload->>'project_id' = :p"
                ),
                {"p": str(project_id)},
            )
        ).one()
    assert row[0] == tenant_id
    assert row[1] == "autonomy_policy.upserted"
    assert row[2]["new_level"] == int(L.A2)
    assert row[2]["changed_override_keys"] == ["run_tests"]
    # safe metadata only: no secret/value leakage of override internals
    assert set(row[2].keys()) == {
        "project_id",
        "previous_level",
        "new_level",
        "changed_override_keys",
    }


@pytest_asyncio.fixture
async def two_policy_tenants(admin_engine):
    """Two distinct tenants, each with a project + an autonomy policy (admin-seeded)."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org_id = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('PolRLS',:s) RETURNING id"),
                {"s": f"pol-rls-{sfx}"},
            )
        ).scalar_one()
        out = {}
        for label in ("a", "b"):
            t = (
                await c.execute(
                    text(
                        "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id"
                    ),
                    {"o": org_id, "n": label, "s": f"pol-{label}-{sfx}"},
                )
            ).scalar_one()
            p = (
                await c.execute(
                    text(
                        "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id"
                    ),
                    {"t": t, "s": f"pol-{label}-proj-{sfx}"},
                )
            ).scalar_one()
            await c.execute(
                text(
                    "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level) VALUES (:t,:p,2)"
                ),
                {"t": t, "p": p},
            )
            out[label] = (t, p)
    return out


@pytest.mark.db
async def test_autonomy_policies_rls_isolation(rls_engine, two_policy_tenants):
    ta, pa = two_policy_tenants["a"]
    async with rls_engine.connect() as conn:
        async with conn.begin():  # no GUC -> deny by default
            assert (
                await conn.execute(text("SELECT count(*) FROM autonomy_policies"))
            ).scalar_one() == 0
        async with conn.begin():  # GUC = A -> only A's policy visible
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(ta)}
            )
            ids = (
                (await conn.execute(text("SELECT project_id FROM autonomy_policies")))
                .scalars()
                .all()
            )
            assert ids == [pa]


@pytest.mark.db
async def test_autonomy_policies_cross_tenant_write_blocked(rls_engine, two_policy_tenants):
    ta, _ = two_policy_tenants["a"]
    tb, pb = two_policy_tenants["b"]

    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(ta)}
                )
                # GUC=A; write a policy for tenant B (valid composite FK) -> WITH CHECK violation.
                await conn.execute(
                    text(
                        "INSERT INTO autonomy_policies (tenant_id, project_id, autonomy_level) VALUES (:t,:p,3)"
                    ),
                    {"t": str(tb), "p": str(pb)},
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "row-level security" in str(ei.value).lower() or "policy" in str(ei.value).lower()


@pytest.mark.db
async def test_autonomy_policies_catalog_and_grants(admin_engine):
    async with admin_engine.connect() as c:
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='autonomy_policies'"
                )
            )
        ).one()
        assert rls == (True, True)
        pol = (
            (
                await c.execute(
                    text("SELECT policyname FROM pg_policies WHERE tablename='autonomy_policies'")
                )
            )
            .scalars()
            .all()
        )
        assert "tenant_isolation" in pol
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='autonomy_policies' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
    assert grants == {"SELECT", "INSERT", "UPDATE"}
    assert "DELETE" not in grants
