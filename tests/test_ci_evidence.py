"""Source-control / CI branch-protection evidence store tests (Slice 26, Appendix B #3 / §26.3).

Fail-closed and non-authorizing: an immutable, append-only ``branch_protection_snapshots`` store whose
only writable provenance is ``caller_supplied_unverified`` (the ``connector_verified`` tier is
schema-reserved but unwritable this slice). ``repo_ref`` is a GitHub-first ``owner/repo`` slug with a
token-prefix denylist; ``required_status_checks`` is a bounded-string JSON array with server-derived
count. Docker-free for the pure validators; ``db`` for the store (RLS, append-only, DB guard + CHECKs,
audit safe-metadata). Gate #3 never PASSes this slice.
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
        assert await repo.count_connector_verified_branch_protection(p1) == 0  # tier unwritable


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
        {"prov": "connector_verified"},  # verified tier unwritable
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
