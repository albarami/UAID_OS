"""Source-control / CI branch-protection evidence + connector tests (Slice 26 + 28, App. B #3 / §26.3).

Immutable, append-only ``branch_protection_snapshots`` with a two-tier provenance: the caller path
writes ``caller_supplied_unverified``; the **Slice-28 connector path** writes ``connector_verified``
(the tier unlocked by migration ``0027``). ``repo_ref`` is a GitHub-first ``owner/repo`` slug with a
token-prefix denylist; ``required_status_checks`` is a bounded-string JSON array with server-derived
count. Docker-free for the pure validators + connector mapping/gate predicate; ``db`` for the store, the
broker-gated repo-bound connector, and gate #3 (which PASSes only on repo-bound + latest verified +
fresh + sufficient evidence).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.ci_evidence import (
    MAX_CHECK_NAME_LEN,
    PROVENANCES,
    PROVIDERS,
    WRITABLE_PROVENANCES,
    InvalidBranchProtectionSnapshot,
    derived_check_count,
    validate_new_snapshot,
)


def _valid(**over) -> dict:
    rec = {
        "provider": "github",
        "repo_ref": "owner/repo",
        "branch": "main",
        "protection_enabled": True,
        "required_pull_request_reviews": True,
        "required_status_checks": ["ci/build", "ci/test"],
        "enforce_admins": False,
    }
    rec.update(over)
    return rec


# --- Docker-free: pure validators ---------------------------------------------


def test_valid_snapshot_and_constants():
    validate_new_snapshot(_valid())
    validate_new_snapshot(_valid(required_status_checks=[]))
    assert PROVIDERS == ("github",)
    assert PROVENANCES == ("caller_supplied_unverified", "connector_verified")
    assert WRITABLE_PROVENANCES == ("caller_supplied_unverified",)
    assert derived_check_count(["a", "b"]) == 2 and derived_check_count(None) == 0


@pytest.mark.parametrize(
    "field",
    (
        "provider",
        "repo_ref",
        "branch",
        "protection_enabled",
        "required_pull_request_reviews",
        "enforce_admins",
    ),
)
def test_required_fields_enforced(field):
    rec = _valid()
    del rec[field]
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(rec)


def test_bad_provider_rejected():
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(_valid(provider="gitlab"))


@pytest.mark.parametrize(
    "bad",
    [
        "https://github.com/org/repo",
        "https://token@github.com/org/repo",
        "git@github.com:org/repo.git",
        "https://github.com/org/repo?token=x",
        "org/repo#frag",
        "org/repo/extra",
        " org/repo",
        "org/repo ",
        "org/repo\n",
        "",
    ],
)
def test_repo_ref_shape_rejections(bad):
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(_valid(repo_ref=bad))


@pytest.mark.parametrize(
    "bad",
    [
        "owner/ghp_abcdefghijklmnopqrstuvwxyz123456",
        "owner/github_pat_11ABCDEFG0abcdefghij_ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "owner/gho_16C7e42F292c6912E7710c838347Ae178B4a",
        "owner/ghu_16C7e42F292c6912E7710c838347Ae178B4a",
        "owner/ghs_16C7e42F292c6912E7710c838347Ae178B4a",
        "owner/ghr_1B4a0d1f8e2c",
    ],
)
def test_repo_ref_token_rejections(bad):
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(_valid(repo_ref=bad))


@pytest.mark.parametrize(
    "ok",
    [
        "owner/repo",
        "Org-1/repo.name_2",
        "owner/my_repo",
        "owner/github-actions",
        "owner/ghost",
        "owner/repo-ghp",
    ],
)
def test_repo_ref_accepts_no_false_positive(ok):
    validate_new_snapshot(_valid(repo_ref=ok))


@pytest.mark.parametrize(
    "field", ("protection_enabled", "required_pull_request_reviews", "enforce_admins")
)
@pytest.mark.parametrize("bad", [1, 0, "true", "false", None])
def test_bool_fields_must_be_real_bools(field, bad):
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(_valid(**{field: bad}))


@pytest.mark.parametrize(
    "bad",
    [{"a": 1}, "x", None, ["ci", 1], [""], ["x" * (MAX_CHECK_NAME_LEN + 1)]],
)
def test_required_status_checks_rejections(bad):
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(_valid(required_status_checks=bad))


def test_caller_cannot_assert_connector_verified():
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(_valid(provenance="connector_verified"))


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def bp_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('BpOrg',:s) RETURNING id",
            s=f"bp-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"bp-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"bp-{proj}-{sfx}",
            )
    return out


def _repo(session, ctx):
    from app.repositories.ci_evidence import CIEvidenceRepository

    return CIEvidenceRepository(session, ctx)


# --- DB-backed: repository ----------------------------------------------------


@pytest.mark.db
async def test_record_and_latest_and_audit_safe(bp_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    secret_repo = "private-org/secret-repo"
    async with tenant_scope(ctx) as session:
        row = await _repo(session, ctx).record_branch_protection(
            project_id=p1, payload=_valid(repo_ref=secret_repo), actor="rev"
        )
        assert row.provenance == "caller_supplied_unverified"
        assert row.required_status_check_count == 2  # derived from ["ci/build","ci/test"]
        latest = await _repo(session, ctx).latest_branch_protection(p1)
        assert latest.id == row.id
        sid = row.id
    async with admin_engine.connect() as c:
        actor, payload = (
            await c.execute(
                text(
                    "SELECT actor, payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"branch_protection_snapshot:{sid}", "t": t1},
            )
        ).one()
    assert actor == "rev"
    blob = str(payload)
    assert secret_repo not in blob  # repo_ref never in the audit log
    assert "repo_ref" not in payload and "required_status_checks" not in payload


@pytest.mark.db
async def test_counts_and_verified_tier_empty(bp_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        await repo.record_branch_protection(project_id=p1, payload=_valid(), actor="a")
        await repo.record_branch_protection(
            project_id=p1, payload=_valid(required_status_checks=[]), actor="a"
        )
        assert await repo.count_branch_protection_snapshots(p1) == 2
        assert await repo.count_connector_verified_branch_protection(p1) == 0  # no connector write here


@pytest.mark.db
async def test_rls_cross_tenant(bp_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = bp_ctx["t1"], bp_ctx["t2"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _repo(session, ctx).record_branch_protection(
            project_id=p1, payload=_valid(), actor="a"
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM branch_protection_snapshots"))
            ).scalar_one()
            assert n == 0  # deny-by-default: no GUC set
    async with tenant_scope(TenantContext(t2)) as session:
        assert await _repo(session, TenantContext(t2)).latest_branch_protection(p1) is None


# --- DB-backed: guard (direct SQL refusals) -----------------------------------

_RAW_INSERT = (
    "INSERT INTO branch_protection_snapshots "
    "(tenant_id, project_id, provider, repo_ref, branch, protection_enabled, "
    " required_pull_request_reviews, required_status_checks, required_status_check_count, "
    " enforce_admins, provenance) "
    "VALUES (:t,:p,:provider,:repo_ref,'main',true,true,(:checks)::jsonb,:cnt,false,:prov)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    params = {
        "t": str(t1),
        "p": str(p1),
        "provider": "github",
        "repo_ref": "owner/repo",
        "checks": "[]",
        "cnt": 0,
        "prov": "caller_supplied_unverified",
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(_RAW_INSERT), params)


@pytest.mark.db
@pytest.mark.parametrize(
    "over",
    [
        {"provider": "gitlab"},  # provider CHECK
        {"repo_ref": "https://github.com/org/repo"},  # repo_ref shape (URL)
        {"repo_ref": "https://token@github.com/org/repo"},  # repo_ref shape (credentialed URL)
        {"repo_ref": "git@github.com:org/repo.git"},  # repo_ref shape (SSH)
        {"repo_ref": "org/repo?token=x"},  # repo_ref shape (query)
        {"repo_ref": "org/repo/extra"},  # repo_ref shape (multi-slash)
        {"repo_ref": "owner/ghp_abcdefghijklmnopqrstuvwxyz123456"},  # token denylist (ghp_)
        {"repo_ref": "owner/gho_16C7e42F292c6912E7710c838347Ae178B4a"},  # token denylist (gho_)
        {"repo_ref": "owner/github_pat_11ABCDEF"},  # token denylist
        {"checks": '"x"'},  # non-array JSON
        {"checks": '{"a":1}'},  # non-array JSON
        {"checks": "[1]"},  # non-string element
        {"checks": '[""]'},  # empty element
        {"checks": '["' + "x" * 201 + '"]'},  # oversized element
        {"checks": '["a"]', "cnt": 2},  # count mismatch
    ],
)
async def test_guard_rejects_bad_inserts(bp_ctx, rls_engine, over):
    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, **over)


@pytest.mark.db
async def test_guard_accepts_legit_token_lookalike(bp_ctx, rls_engine):
    # 'owner/github-actions' must NOT be a false positive of the token denylist.
    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1, repo_ref="owner/github-actions")


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(bp_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        row = await _repo(session, ctx).record_branch_protection(
            project_id=p1, payload=_valid(), actor="a"
        )
        sid = row.id
    for verb in (
        "UPDATE branch_protection_snapshots SET branch='dev' WHERE id=:i",
        "DELETE FROM branch_protection_snapshots WHERE id=:i",
        "TRUNCATE branch_protection_snapshots",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb), {"i": str(sid)})


@pytest.mark.db
async def test_fk_cross_project_tenant_rejected(bp_ctx, rls_engine):
    # An insert pinning (project_id, tenant_id) that has no matching project row is rejected.
    t1, px = bp_ctx["t1"], bp_ctx["px"]  # px belongs to t2, not t1
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, px)


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='branch_protection_snapshots' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}  # append-only: no UPDATE/DELETE
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='branch_protection_snapshots'"
                )
            )
        ).one()
        assert rls == (True, True)
        checks = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid='branch_protection_snapshots'::regclass AND contype='c'"
                    )
                )
            ).all()
        }
        assert {
            "ck_bps_repo_ref_slug",
            "ck_bps_repo_ref_not_tokenish",
            "ck_bps_checks_array",
        } <= checks


# --- Slice 28: connector pure functions (Docker-free) -------------------------

from app.release.ci_evidence import (  # noqa: E402
    CONNECTOR_WRITABLE,
    gate3_protection_sufficient,
    validate_connector_snapshot,
)


def _connector_valid(**over) -> dict:
    rec = _valid()
    rec["provenance"] = "connector_verified"
    rec["observed_at"] = "2026-06-23T00:00:00Z"  # required for the connector path
    rec.update(over)
    return rec


def test_connector_writable_tuple():
    assert CONNECTOR_WRITABLE == ("connector_verified",)


def test_validate_connector_snapshot_accepts_verified():
    validate_connector_snapshot(_connector_valid())  # no raise


def test_validate_connector_snapshot_requires_observed_at():
    rec = _connector_valid()
    del rec["observed_at"]
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_connector_snapshot(rec)


def test_validate_connector_snapshot_rejects_caller_tier():
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_connector_snapshot(_connector_valid(provenance="caller_supplied_unverified"))


def test_caller_validator_still_rejects_connector_tier():
    # The unverified caller path must NEVER accept connector_verified (Slice 26 invariant holds).
    with pytest.raises(InvalidBranchProtectionSnapshot):
        validate_new_snapshot(_valid(provenance="connector_verified"))


@pytest.mark.parametrize(
    "enabled,pr,count,expected",
    [
        (True, True, 1, True),
        (True, True, 3, True),
        (False, True, 1, False),  # protection off
        (True, False, 1, False),  # no PR reviews
        (True, True, 0, False),  # no required checks
        (None, True, 1, False),  # fail-closed on None
        (True, None, 1, False),
    ],
)
def test_gate3_protection_sufficient(enabled, pr, count, expected):
    assert (
        gate3_protection_sufficient(
            protection_enabled=enabled,
            required_pull_request_reviews=pr,
            required_status_check_count=count,
        )
        is expected
    )


# --- Slice 28: GitHub response mapping (pure) ---------------------------------

from app.release.scm_connector import (  # noqa: E402
    SCMConnectorError,
    map_github_branch_protection,
)


def test_map_github_happy():
    m = map_github_branch_protection(
        {
            "required_pull_request_reviews": {"dismiss_stale_reviews": True},
            "required_status_checks": {"contexts": ["ci/build", "ci/test"]},
            "enforce_admins": {"enabled": True},
        }
    )
    assert m["protection_enabled"] is True  # a 200 means protection is on
    assert m["required_pull_request_reviews"] is True
    assert m["required_status_checks"] == ["ci/build", "ci/test"]
    assert m["enforce_admins"] is True


def test_map_github_no_pr_reviews_no_checks():
    m = map_github_branch_protection({"enforce_admins": {"enabled": False}})
    assert m["required_pull_request_reviews"] is False
    assert m["required_status_checks"] == []
    assert m["enforce_admins"] is False


@pytest.mark.parametrize(
    "bad",
    [
        "x",
        None,
        123,
        {},
        {"enforce_admins": "no"},  # not an object
        {"enforce_admins": {}},  # missing enabled
        {"enforce_admins": {"enabled": "yes"}},  # enabled not a bool
        {"enforce_admins": {"enabled": 1}},  # int is not bool (no truthy coercion)
        {"enforce_admins": {"enabled": True}, "required_status_checks": "x"},  # rsc non-object
        {  # non-string context — must NOT be silently dropped
            "enforce_admins": {"enabled": True},
            "required_status_checks": {"contexts": ["a", 1]},
        },
        {  # malformed check object
            "enforce_admins": {"enabled": True},
            "required_status_checks": {"checks": [{"context": 1}]},
        },
    ],
)
def test_map_github_malformed_raises(bad):
    with pytest.raises(SCMConnectorError):
        map_github_branch_protection(bad)


async def test_github_adapter_wraps_malformed_200_json(monkeypatch):
    # GitHubSCMConnector is never run against the real network; here we monkeypatch httpx so a 200
    # with non-JSON body fails closed as SCMConnectorError (no verified write). No network.
    import httpx

    from app.release.scm_connector import GitHubSCMConnector

    class _Resp:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(SCMConnectorError):
        await GitHubSCMConnector("tok").fetch_branch_protection(repo_ref="owner/repo", branch="main")


# --- Slice 28 DB: connector verified write + gate-time repo binding -----------

from datetime import datetime, timezone  # noqa: E402


def _gate3(rep) -> dict:
    return next(g for g in rep.to_dict()["gates"] if g["number"] == 3)


def _connector_payload(repo_ref="owner/repo-a", branch="main", **over) -> dict:
    rec = {
        "provider": "github",
        "repo_ref": repo_ref,
        "branch": branch,
        "protection_enabled": True,
        "required_pull_request_reviews": True,
        "required_status_checks": ["ci/build"],
        "enforce_admins": True,
        "observed_at": datetime.now(timezone.utc),
    }
    rec.update(over)
    return rec


async def _declare_repo(session, ctx, project_id, repo_ref, branch="main"):
    from app.repositories.intake_categories import IntakeCategoryRepository

    repo = IntakeCategoryRepository(session, ctx)
    data = {"primary_repository": repo_ref, "protected_branch": branch}
    if await repo.get_category(project_id, "existing_assets_and_repositories") is None:
        await repo.declare(
            project_id=project_id,
            category="existing_assets_and_repositories",
            actor="a",
            data=data,
            origin="test",
        )
    else:
        await repo.revise(
            project_id=project_id,
            category="existing_assets_and_repositories",
            actor="a",
            data=data,
        )


async def _declare_secrets(session, ctx, project_id):
    from app.repositories.intake_categories import IntakeCategoryRepository

    await IntakeCategoryRepository(session, ctx).declare(
        project_id=project_id,
        category="secrets_and_credentials_manifest",
        actor="a",
        data={"references": [{"manager": "env", "reference_name": "GITHUB_CONNECTOR_TOKEN"}]},
        origin="test",
    )


@pytest.mark.db
async def test_connector_verified_write_and_counts(bp_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _repo(session, ctx)
        row = await repo.record_connector_verified_branch_protection(
            project_id=p1, payload=_connector_payload(), actor="conn"
        )
        assert row.provenance == "connector_verified"
        assert await repo.count_connector_verified_branch_protection(p1) == 1
        got = await repo.latest_branch_protection_for_repo(p1, "owner/repo-a", "main")
        assert got is not None and got.id == row.id
        # a different repo/branch has no snapshot
        assert await repo.latest_branch_protection_for_repo(p1, "owner/other", "main") is None


@pytest.mark.db
async def test_db_guard_now_allows_connector_verified_only(bp_ctx, rls_engine):
    # 0027 relaxed the guard: connector_verified now inserts; bad provider still rejected.
    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1, prov="connector_verified")  # no raise now
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, prov="connector_verified", provider="gitlab")


@pytest.mark.db
async def test_gate3_passes_for_declared_repo_and_invalidated_on_revision(bp_ctx):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _declare_repo(session, ctx, p1, "owner/repo-a")
        await _repo(session, ctx).record_connector_verified_branch_protection(
            project_id=p1, payload=_connector_payload("owner/repo-a"), actor="conn"
        )
        rep = await ProductionAutonomyRepository(session, ctx).evaluate(p1)
        g3 = _gate3(rep)
        assert g3["status"] == "passed"
        assert g3["context"]["branch_protection_repo_bound"] is True
        assert "repo_ref" not in g3["context"]  # never the raw repo_ref
    # Revise the declaration to repo B — the old verified A snapshot must NOT satisfy gate #3.
    async with tenant_scope(ctx) as session:
        await _declare_repo(session, ctx, p1, "owner/repo-b")
        g3 = _gate3(await ProductionAutonomyRepository(session, ctx).evaluate(p1))
        assert g3["status"] == "insufficient_evidence"
        assert g3["reason"] == "no_branch_protection_evidence"
    # A verified snapshot for B then passes.
    async with tenant_scope(ctx) as session:
        await _repo(session, ctx).record_connector_verified_branch_protection(
            project_id=p1, payload=_connector_payload("owner/repo-b"), actor="conn"
        )
        g3 = _gate3(await ProductionAutonomyRepository(session, ctx).evaluate(p1))
        assert g3["status"] == "passed"


@pytest.mark.db
async def test_gate3_unbound_fails_closed_even_with_old_snapshot(bp_ctx):
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        # a verified snapshot exists, but the project declares NO repo ⇒ fail-closed unbound.
        await _repo(session, ctx).record_connector_verified_branch_protection(
            project_id=p1, payload=_connector_payload("owner/repo-a"), actor="conn"
        )
        g3 = _gate3(await ProductionAutonomyRepository(session, ctx).evaluate(p1))
        assert g3["status"] == "insufficient_evidence"
        assert g3["reason"] == "branch_protection_repo_unbound"


@pytest.mark.db
async def test_refresh_broker_allow_writes_safe_params(bp_ctx, admin_engine):
    from app.policy.levels import AutonomyLevel
    from app.release.ci_evidence_service import refresh_branch_protection
    from app.release.scm_connector import FakeSCMConnector
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.tools import ToolAllowlistRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    mapped = {
        "provider": "github",
        "protection_enabled": True,
        "required_pull_request_reviews": True,
        "required_status_checks": ["ci/build"],
        "enforce_admins": True,
    }
    async with tenant_scope(ctx) as session:
        await _declare_repo(session, ctx, p1, "owner/repo-a")
        await _declare_secrets(session, ctx, p1)
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=p1, autonomy_level=int(AutonomyLevel.A5), actor="a"
        )
        await ToolAllowlistRepository(session, ctx).grant(
            agent_id="conn", tool_name="source_control.read_branch_protection", actor="admin"
        )
        result = await refresh_branch_protection(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeSCMConnector(mapped),
        )
        assert result.wrote is True
        g3 = _gate3(await ProductionAutonomyRepository(session, ctx).evaluate(p1))
        assert g3["status"] == "passed"
    # the broker recorded the tool call with SAFE params only — never the raw repo_ref.
    async with admin_engine.connect() as c:
        params_rows = (
            await c.execute(
                text(
                    "SELECT params FROM tool_calls WHERE tenant_id=:t "
                    "AND tool_name='source_control.read_branch_protection'"
                ),
                {"t": str(t1)},
            )
        ).all()
    assert params_rows
    for (params,) in params_rows:
        assert "repo_ref" not in (params or {})
        assert params.get("repo_ref_present") is True


@pytest.mark.db
async def test_refresh_no_write_paths(bp_ctx):
    from app.release.ci_evidence_service import refresh_branch_protection
    from app.release.scm_connector import FakeSCMConnector
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    # (a) undeclared repo ⇒ fail-closed, no broker call, no write.
    async with tenant_scope(ctx) as session:
        r = await refresh_branch_protection(
            session, ctx, project_id=p1, agent_id="conn", actor="conn",
            connector=FakeSCMConnector({"provider": "github"}),
        )
        assert r.wrote is False and r.reason == "repo_unbound"
    # (b) declared + not-allowlisted agent ⇒ broker denies, no write.
    async with tenant_scope(ctx) as session:
        await _declare_repo(session, ctx, p1, "owner/repo-a")
        await _declare_secrets(session, ctx, p1)
        r = await refresh_branch_protection(
            session, ctx, project_id=p1, agent_id="nope", actor="conn",
            connector=FakeSCMConnector({"provider": "github"}),
        )
        assert r.wrote is False  # broker_denied (not allowlisted / no policy)
        assert await _repo(session, ctx).count_connector_verified_branch_protection(p1) == 0


@pytest.mark.db
async def test_connector_audit_has_no_secret(bp_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    secret_repo = "private-org/secret-repo-x"
    async with tenant_scope(ctx) as session:
        row = await _repo(session, ctx).record_connector_verified_branch_protection(
            project_id=p1, payload=_connector_payload(secret_repo), actor="conn"
        )
        sid = row.id
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"branch_protection_snapshot:{sid}", "t": t1},
            )
        ).scalar_one()
    assert secret_repo not in str(payload)
    assert "repo_ref" not in payload and "required_status_checks" not in payload


@pytest.mark.db
async def test_credential_reference_binding(bp_ctx):
    # D-28-3/11: the credential SOURCE must name a usable {env, GITHUB_CONNECTOR_TOKEN} reference.
    from app.release.project_repo import has_declared_credential
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as s:
        cats = IntakeCategoryRepository(s, ctx)
        # (a) no declaration ⇒ False
        assert await has_declared_credential(s, ctx, p1) is False
        # (b) empty declaration ⇒ False
        await cats.declare(
            project_id=p1, category="secrets_and_credentials_manifest",
            actor="a", data={}, origin="test",
        )
        assert await has_declared_credential(s, ctx, p1) is False
        # (c) unrelated reference ⇒ False
        await cats.revise(
            project_id=p1, category="secrets_and_credentials_manifest",
            actor="a", data={"references": [{"manager": "vault", "reference_name": "OTHER"}]},
        )
        assert await has_declared_credential(s, ctx, p1) is False
        # (d) valid env reference ⇒ True
        await cats.revise(
            project_id=p1, category="secrets_and_credentials_manifest",
            actor="a",
            data={"references": [{"manager": "env", "reference_name": "GITHUB_CONNECTOR_TOKEN"}]},
        )
        assert await has_declared_credential(s, ctx, p1) is True


@pytest.mark.db
async def test_refresh_credential_unbound_no_broker_no_write(bp_ctx):
    from app.release.ci_evidence_service import refresh_branch_protection
    from app.release.scm_connector import FakeSCMConnector
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as s:
        await _declare_repo(s, ctx, p1, "owner/repo-a")  # repo declared, but NO usable credential
        r = await refresh_branch_protection(
            s, ctx, project_id=p1, agent_id="conn", actor="conn",
            connector=FakeSCMConnector({"provider": "github"}),
        )
        assert r.wrote is False and r.reason == "credential_unbound"
        assert r.decision is None  # fail-closed BEFORE the broker call
        assert await _repo(s, ctx).count_connector_verified_branch_protection(p1) == 0


@pytest.mark.db
async def test_gate3_latest_wins_newer_unverified_b_never_passes_from_a(bp_ctx):
    # Older VERIFIED snapshot for A + newer UNVERIFIED snapshot for the now-declared B ⇒ the gate
    # (bound to B) sees an unverified latest ⇒ observed_unverified; A's verified evidence never passes.
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = bp_ctx["t1"], bp_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as s:
        await _declare_repo(s, ctx, p1, "owner/repo-a")
        await _repo(s, ctx).record_connector_verified_branch_protection(
            project_id=p1, payload=_connector_payload("owner/repo-a"), actor="conn"
        )
    async with tenant_scope(ctx) as s:
        await _declare_repo(s, ctx, p1, "owner/repo-b")  # revise declaration to B
        await _repo(s, ctx).record_branch_protection(
            project_id=p1, payload=_valid(repo_ref="owner/repo-b"), actor="caller"
        )  # newer UNVERIFIED snapshot for B
        g3 = _gate3(await ProductionAutonomyRepository(s, ctx).evaluate(p1))
        assert g3["status"] == "insufficient_evidence"
        assert g3["reason"] == "branch_protection_observed_unverified"
