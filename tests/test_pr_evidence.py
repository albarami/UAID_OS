"""Pull-request evidence connector tests (Slice 29, App. B #7 feed / §12.3-12.4).

Immutable, append-only ``pull_request_evidence_snapshots`` with a two-tier provenance: the caller path
writes ``caller_supplied_unverified``; the connector path writes ``connector_verified``. PR + reviews
endpoints are fail-closed; requested-reviewers is observed (``requested_reviewers_observed``); checks are
optional observed-only (``check_status_summary`` nullable). Identity facts are normalized
(latest-review-per-principal) and separation-of-duties flags are structural-only (provider-principal
equality — NOT a verified UAID-actor separation). Store-only: no A5 gate flip, no ``production_autonomy``
edit (the PR-evidence store does not touch ``production_autonomy``; the ruleset has since advanced to
``slice43.v1`` via later slices — the invariant here is that PR evidence leaves the report unchanged,
``before == after``).

Docker-free for the pure validators / approval normalization / separation flags / connector mapping;
``db`` for the store, traceability + merged-protected validation, DB guard, broker-gated connector,
and the no-A5-regression check.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.pr_evidence import (
    CHECK_STATES,
    PR_STATES,
    PRESENCE_ITEMS,
    PRESENCE_SOURCES,
    PROVENANCES,
    PROVIDERS,
    WRITABLE_PROVENANCES,
    InvalidPullRequestSnapshot,
    derive_separation_flags,
    normalize_approvals,
    validate_check_status_summary,
    validate_connector_pull_request,
    validate_new_pull_request,
    validate_presence_flags,
    validate_traceability_refs_shape,
)

_NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _valid(**over) -> dict:
    rec = {
        "provider": "github",
        "repo_ref": "owner/repo",
        "pr_number": 7,
        "pr_state": "merged",
        "merged": True,
    }
    rec.update(over)
    return rec


def _connector(**over) -> dict:
    rec = _valid(provenance="connector_verified", observed_at=_NOW)
    rec.update(over)
    return rec


# --- Docker-free: constants + shape validators --------------------------------


def test_constants():
    assert PROVIDERS == ("github",)
    assert PROVENANCES == ("caller_supplied_unverified", "connector_verified")
    assert WRITABLE_PROVENANCES == ("caller_supplied_unverified",)
    assert PR_STATES == ("open", "closed", "merged")
    assert PRESENCE_SOURCES == ("caller_declared", "connector_observed_template")
    assert len(PRESENCE_ITEMS) == 10  # the 10 §12.4 required-contents keys
    assert "acceptance_criteria_coverage" in PRESENCE_ITEMS
    assert set(CHECK_STATES) == {"success", "failure", "pending", "neutral", "error", "unknown"}


def test_valid_caller_and_connector_snapshots():
    validate_new_pull_request(_valid())
    validate_new_pull_request(_valid(pr_state="open", merged=False))
    validate_connector_pull_request(_connector())


@pytest.mark.parametrize(
    "over",
    [
        {"provider": "gitlab"},
        {"repo_ref": "https://github.com/org/repo"},
        {"repo_ref": "git@github.com:org/repo.git"},
        {"repo_ref": "org/repo/extra"},
        {"repo_ref": "owner/ghp_abcdefghijklmnopqrstuvwxyz123456"},
        {"pr_number": 0},
        {"pr_number": -1},
        {"pr_number": "7"},
        {"pr_number": True},  # bool is not an int pr_number
        {"pr_state": "draft"},
        {"merged": "true"},  # must be a real bool
        {"provider": None},
    ],
)
def test_invalid_pr_shape_rejected(over):
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_new_pull_request(_valid(**over))


def test_caller_path_rejects_connector_verified():
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_new_pull_request(_valid(provenance="connector_verified"))


def test_connector_path_requires_verified_and_observed_at():
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_connector_pull_request(_valid(provenance="caller_supplied_unverified"))
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_connector_pull_request(_valid(provenance="connector_verified"))  # no observed_at


# --- Docker-free: §12.4 presence flags (Q2) -----------------------------------


def test_presence_flags_valid():
    validate_presence_flags({})
    validate_presence_flags(
        {
            "tests_added": {"present": True, "source": "caller_declared"},
            "rollback_notes": {
                "present": False,
                "source": "connector_observed_template",
                "observed_marker": "checklist:rollback",
            },
        }
    )


@pytest.mark.parametrize(
    "obj",
    [
        {"not_a_real_item": {"present": True, "source": "caller_declared"}},  # bad key
        {"tests_added": {"present": True, "source": "made_up"}},  # bad source
        {"tests_added": {"present": "yes", "source": "caller_declared"}},  # present not bool
        {"tests_added": {"source": "caller_declared"}},  # missing present
        {"tests_added": "some prose about tests"},  # value not an object (no prose)
        {"tests_added": {"present": True}},  # missing source label
    ],
)
def test_presence_flags_invalid(obj):
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_presence_flags(obj)


# --- Docker-free: observed check-status summary (B-29-1) ----------------------


def test_check_status_summary_nullable_and_valid():
    validate_check_status_summary(None)  # not observed
    validate_check_status_summary({"success": 3, "failure": 0, "pending": 1})
    validate_check_status_summary({"success": 2, "combined_state": "success"})


@pytest.mark.parametrize(
    "obj",
    [
        "not-an-object",
        {"made_up_state": 1},  # bad state key
        {"success": -1},  # negative count
        {"success": 1.5},  # non-integer count
        {"success": True},  # bool is not a count
        {"combined_state": "flaky"},  # bad combined_state
    ],
)
def test_check_status_summary_invalid(obj):
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_check_status_summary(obj)


# --- Docker-free: traceability refs SHAPE (existence/kind is the repo's job) ---


def test_traceability_refs_shape_valid():
    validate_traceability_refs_shape({})
    validate_traceability_refs_shape(
        {
            "release_issue_ids": [str(uuid.uuid4())],
            "acceptance_criterion_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "provider_refs": {"pr_number": 7, "commit_sha": "abc1234"},
        }
    )


@pytest.mark.parametrize(
    "obj",
    [
        "not-an-object",
        {"release_issue_ids": "not-a-list"},
        {"release_issue_ids": ["not-a-uuid"]},
        {"acceptance_criterion_ids": [123]},
    ],
)
def test_traceability_refs_shape_invalid(obj):
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_traceability_refs_shape(obj)


# --- Docker-free: approval normalization (B-29-5/6) ---------------------------


def _rev(principal, state, submitted_at):
    return {"principal": principal, "state": state, "submitted_at": submitted_at}


def test_normalize_approvals_latest_wins_per_principal():
    # alice: APPROVED then CHANGES_REQUESTED later -> not approving (latest wins)
    reviews = [
        _rev("alice", "APPROVED", "2026-06-01T00:00:00Z"),
        _rev("alice", "CHANGES_REQUESTED", "2026-06-02T00:00:00Z"),
        _rev("bob", "APPROVED", "2026-06-01T00:00:00Z"),
    ]
    approvers, reviewers, count = normalize_approvals(reviews)
    assert approvers == ["bob"]
    assert count == 1
    assert {r["principal"]: r["latest_state"] for r in reviewers} == {
        "alice": "CHANGES_REQUESTED",
        "bob": "APPROVED",
    }


def test_normalize_approvals_dismissed_and_commented_not_approving():
    reviews = [
        _rev("carol", "APPROVED", "2026-06-01T00:00:00Z"),
        _rev("carol", "DISMISSED", "2026-06-03T00:00:00Z"),  # latest dismissed
        _rev("dave", "COMMENTED", "2026-06-01T00:00:00Z"),  # never approving
    ]
    approvers, _, count = normalize_approvals(reviews)
    assert approvers == []
    assert count == 0


def test_normalize_approvals_dedup_and_count_invariant():
    reviews = [
        _rev("ann", "APPROVED", "2026-06-01T00:00:00Z"),
        _rev("ann", "APPROVED", "2026-06-02T00:00:00Z"),  # same principal, still one approver
    ]
    approvers, _, count = normalize_approvals(reviews)
    assert approvers == ["ann"]
    assert count == len(approvers) == 1


def test_normalize_approvals_empty():
    assert normalize_approvals([]) == ([], [], 0)


# --- Docker-free: separation-of-duties flags (Q3) -----------------------------


def test_derive_separation_flags_truth_table():
    # self-approval + self-merge
    f = derive_separation_flags(
        author_principal="alice", approver_principals=["alice"], merger_principal="alice"
    )
    assert f == {
        "self_approval_observed": True,
        "self_merge_observed": True,
        "review_separation_observed": False,
    }
    # clean separation: bob authored, alice approved, carol merged
    f = derive_separation_flags(
        author_principal="bob", approver_principals=["alice"], merger_principal="carol"
    )
    assert f == {
        "self_approval_observed": False,
        "self_merge_observed": False,
        "review_separation_observed": True,
    }
    # author approved among others -> self_approval true, but separation also true
    f = derive_separation_flags(
        author_principal="bob", approver_principals=["bob", "alice"], merger_principal="carol"
    )
    assert f["self_approval_observed"] is True
    assert f["review_separation_observed"] is True


def test_derive_separation_flags_unknown_author_is_conservative():
    f = derive_separation_flags(
        author_principal=None, approver_principals=["alice"], merger_principal="bob"
    )
    assert f["self_approval_observed"] is False
    assert f["self_merge_observed"] is False
    assert f["review_separation_observed"] is False  # cannot assert separation w/o a known author


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def pr_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('PrOrg',:s) RETURNING id",
            s=f"pr-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"pr-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p2", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"pr-{proj}-{sfx}",
            )
    return out


# --- DB-backed: guard (direct SQL refusals) -----------------------------------

_RAW_INSERT = (
    "INSERT INTO pull_request_evidence_snapshots "
    "(tenant_id, project_id, provider, repo_ref, pr_number, pr_state, merged, "
    " approver_principals, approval_count, check_status_summary, presence_flags, "
    " traceability_refs, provenance) "
    "VALUES (:t,:p,:provider,:repo_ref,:pr_number,:pr_state,:merged,"
    " (:approvers)::jsonb,:approval_count,(:checks)::jsonb,(:presence)::jsonb,"
    " (:trace)::jsonb,:prov)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    params = {
        "t": str(t1),
        "p": str(p1),
        "provider": "github",
        "repo_ref": "owner/repo",
        "pr_number": 7,
        "pr_state": "merged",
        "merged": True,
        "approvers": "[]",
        "approval_count": 0,
        "checks": None,
        "presence": "{}",
        "trace": "{}",
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
        {"repo_ref": "https://github.com/org/repo"},  # repo_ref URL
        {"repo_ref": "org/repo/extra"},  # multi-slash
        {"repo_ref": "owner/ghp_abcdefghijklmnopqrstuvwxyz123456"},  # token denylist
        {"pr_number": 0},  # pr_number CHECK
        {"pr_number": -1},
        {"pr_state": "draft"},  # pr_state CHECK
        # B-29-8 derived invariants (guard):
        {"approvers": '["a"]', "approval_count": 0},  # count mismatch
        {"approvers": '{"a":1}'},  # non-array approver_principals
        {"checks": '"x"'},  # non-object check_status_summary
        {"checks": '{"made_up":1}'},  # invalid check-state key
        {"checks": '{"success":-1}'},  # negative count
        {"checks": '{"success":1.5}'},  # non-integer count
        {"checks": '{"combined_state":"flaky"}'},  # invalid combined_state
        {"presence": '"prose"'},  # non-object presence_flags
        {"trace": "[]"},  # non-object traceability_refs
    ],
)
async def test_guard_rejects_bad_inserts(pr_ctx, rls_engine, over):
    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, **over)


@pytest.mark.db
async def test_guard_accepts_null_check_summary_and_consistent_count(pr_ctx, rls_engine):
    # B-29-8: NULL check_status_summary accepted; approval_count matching array length accepted.
    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1, checks=None)
    await _raw_insert(
        rls_engine, t1, p1, approvers='["alice","bob"]', approval_count=2, checks='{"success":3}'
    )


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(pr_ctx, rls_engine):
    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            sid = (
                await conn.execute(text("SELECT id FROM pull_request_evidence_snapshots LIMIT 1"))
            ).scalar_one()
    for verb in (
        "UPDATE pull_request_evidence_snapshots SET pr_state='open' WHERE id=:i",
        "DELETE FROM pull_request_evidence_snapshots WHERE id=:i",
        "TRUNCATE pull_request_evidence_snapshots",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb), {"i": str(sid)})


@pytest.mark.db
async def test_fk_cross_project_tenant_rejected(pr_ctx, rls_engine):
    # px belongs to t2, not t1 -> the composite FK has no matching project row.
    t1, px = pr_ctx["t1"], pr_ctx["px"]
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
                        "WHERE table_name='pull_request_evidence_snapshots' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}  # append-only: no UPDATE/DELETE
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='pull_request_evidence_snapshots'"
                )
            )
        ).one()
        assert rls == (True, True)


# --- DB-backed: repository (record / latest / counts / flags) -----------------


def _pr_repo(session, ctx):
    from app.repositories.pr_evidence import PullRequestEvidenceRepository

    return PullRequestEvidenceRepository(session, ctx)


def _conn_payload(**over) -> dict:
    rec = {
        "provider": "github",
        "repo_ref": "owner/repo",
        "pr_number": 7,
        "pr_state": "merged",
        "merged": True,
        "base_branch": "main",
        "head_branch": "feature/x",
        "author_principal": "alice",
        "approver_principals": ["bob"],
        "reviewer_principals": [{"principal": "bob", "latest_state": "APPROVED"}],
        "requested_reviewer_principals": [],
        "requested_reviewers_observed": True,
        "merger_principal": "carol",
        "presence_flags": {},
        "traceability_refs": {},
        "provenance": "connector_verified",
        "observed_at": _NOW,
    }
    rec.update(over)
    return rec


@pytest.mark.db
async def test_record_connector_latest_counts_and_flags(pr_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        # author approves + merges own PR -> self-approval + self-merge observed
        row = await repo.record_connector_verified_pull_request(
            project_id=p1,
            payload=_conn_payload(
                author_principal="alice", approver_principals=["alice"], merger_principal="alice"
            ),
            actor="conn",
        )
        assert row.provenance == "connector_verified"
        assert row.approval_count == 1  # == len(approver_principals), DB-enforced
        assert row.self_approval_observed is True
        assert row.self_merge_observed is True
        assert row.review_separation_observed is False
        # newer snapshot for the same PR wins
        row2 = await repo.record_connector_verified_pull_request(
            project_id=p1, payload=_conn_payload(approver_principals=["bob"]), actor="conn"
        )
        latest = await repo.latest_pull_request_for_pr(p1, "github", "owner/repo", 7)
        assert latest.id == row2.id
        assert await repo.count_pull_request_snapshots(p1) == 2
        assert await repo.count_connector_verified_pull_requests(p1) == 2


@pytest.mark.db
async def test_caller_path_unverified(pr_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        row = await repo.record_pull_request(
            project_id=p1,
            payload={
                "provider": "github",
                "repo_ref": "owner/repo",
                "pr_number": 3,
                "pr_state": "open",
                "merged": False,
            },
            actor="caller",
        )
        assert row.provenance == "caller_supplied_unverified"


@pytest.mark.db
async def test_caller_declared_presence_label_preserved(pr_ctx):
    # B-29-4: a connector_verified snapshot must NOT promote caller_declared flags.
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        row = await repo.record_connector_verified_pull_request(
            project_id=p1,
            payload=_conn_payload(
                presence_flags={"tests_added": {"present": True, "source": "caller_declared"}}
            ),
            actor="conn",
        )
        assert row.presence_flags["tests_added"]["source"] == "caller_declared"


# --- DB-backed: traceability validation (B-29-3) ------------------------------


def _issue_payload() -> dict:
    return {
        "issue_category": "security",
        "severity": "high",
        "blocking": True,
        "summary": "an open blocker",
        "source": "manual",
    }


async def _seed_issue(session, ctx, project_id) -> uuid.UUID:
    from app.repositories.release_issues import ReleaseIssueRepository

    row = await ReleaseIssueRepository(session, ctx).create(
        project_id=project_id, payload=_issue_payload(), actor="t"
    )
    return row.id


async def _seed_artifact(session, ctx, project_id, kind, ref) -> uuid.UUID:
    from app.intake.compiler import SourceInput
    from app.repositories.intake import IntakeRepository

    art = await IntakeRepository(session, ctx).add_artifact(
        project_id=project_id,
        kind=kind,
        ref=ref,
        title="x",
        sources=[SourceInput(origin="human_decision", document_id=None)],
        actor="t",
    )
    return art.id


@pytest.mark.db
async def test_traceability_valid_same_project_accepted(pr_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        issue_id = await _seed_issue(session, ctx, p1)
        ac_id = await _seed_artifact(session, ctx, p1, "acceptance_criterion", "AC-1")
        row = await _pr_repo(session, ctx).record_connector_verified_pull_request(
            project_id=p1,
            payload=_conn_payload(
                traceability_refs={
                    "release_issue_ids": [str(issue_id)],
                    "acceptance_criterion_ids": [str(ac_id)],
                }
            ),
            actor="conn",
        )
        assert str(issue_id) in row.traceability_refs["release_issue_ids"]


@pytest.mark.db
async def test_traceability_rejections(pr_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1, p2 = pr_ctx["t1"], pr_ctx["p1"], pr_ctx["p2"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        ac_p2 = await _seed_artifact(session, ctx, p2, "acceptance_criterion", "AC-P2")  # other proj
        req_p1 = await _seed_artifact(session, ctx, p1, "requirement", "REQ-1")  # wrong kind
        issue_p1 = await _seed_issue(session, ctx, p1)
        cases = [
            {"acceptance_criterion_ids": [str(ac_p2)]},  # wrong project
            {"acceptance_criterion_ids": [str(req_p1)]},  # wrong kind (requirement)
            {"acceptance_criterion_ids": [str(uuid.uuid4())]},  # unknown
            {"release_issue_ids": [str(uuid.uuid4())]},  # unknown issue
            {"release_issue_ids": [str(issue_p1), str(issue_p1)]},  # duplicate
        ]
        for refs in cases:
            with pytest.raises(InvalidPullRequestSnapshot):
                await repo.record_connector_verified_pull_request(
                    project_id=p1, payload=_conn_payload(traceability_refs=refs), actor="conn"
                )


# --- DB-backed: merged-to-protected cross-ref (B-29-2) ------------------------


async def _seed_verified_bp(session, ctx, project_id, repo_ref, branch, observed_at):
    from app.repositories.ci_evidence import CIEvidenceRepository

    await CIEvidenceRepository(session, ctx).record_connector_verified_branch_protection(
        project_id=project_id,
        payload={
            "provider": "github",
            "repo_ref": repo_ref,
            "branch": branch,
            "protection_enabled": True,
            "required_pull_request_reviews": True,
            "required_status_checks": ["ci/build"],
            "enforce_admins": True,
            "observed_at": observed_at,
        },
        actor="bp",
    )


def _now():
    return datetime.now(timezone.utc)


@pytest.mark.db
async def test_merged_protected_true_only_when_verified_fresh(pr_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        await _declare_repo(session, ctx, p1, "owner/repo", branch="main")
        await _seed_verified_bp(session, ctx, p1, "owner/repo", "main", _now())
        row = await repo.record_connector_verified_pull_request(
            project_id=p1,
            payload=_conn_payload(merged=True, base_branch="main"),
            actor="conn",
        )
        assert row.merged_to_declared_protected_branch_observed is True


@pytest.mark.db
@pytest.mark.parametrize(
    "scenario",
    ["not_merged", "branch_mismatch", "no_bp", "stale_bp", "unverified_bp"],
)
async def test_merged_protected_false_paths(pr_ctx, scenario):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        await _declare_repo(session, ctx, p1, "owner/repo", branch="main")
        payload = _conn_payload(merged=True, base_branch="main")
        if scenario == "not_merged":
            await _seed_verified_bp(session, ctx, p1, "owner/repo", "main", _now())
            payload = _conn_payload(merged=False, pr_state="closed", base_branch="main")
        elif scenario == "branch_mismatch":
            await _seed_verified_bp(session, ctx, p1, "owner/repo", "main", _now())
            payload = _conn_payload(merged=True, base_branch="dev")
        elif scenario == "no_bp":
            pass  # no branch-protection evidence at all
        elif scenario == "stale_bp":
            await _seed_verified_bp(
                session, ctx, p1, "owner/repo", "main", _now() - timedelta(hours=48)
            )
        elif scenario == "unverified_bp":
            from app.repositories.ci_evidence import CIEvidenceRepository

            await CIEvidenceRepository(session, ctx).record_branch_protection(
                project_id=p1,
                payload={
                    "provider": "github",
                    "repo_ref": "owner/repo",
                    "branch": "main",
                    "protection_enabled": True,
                    "required_pull_request_reviews": True,
                    "required_status_checks": ["ci/build"],
                    "enforce_admins": True,
                },
                actor="caller",
            )
        row = await repo.record_connector_verified_pull_request(
            project_id=p1, payload=payload, actor="conn"
        )
        assert row.merged_to_declared_protected_branch_observed is False


# --- DB-backed: RLS + audit safety --------------------------------------------


@pytest.mark.db
async def test_rls_cross_tenant(pr_ctx, rls_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = pr_ctx["t1"], pr_ctx["t2"], pr_ctx["p1"]
    async with tenant_scope(TenantContext(t1)) as session:
        await _pr_repo(session, TenantContext(t1)).record_connector_verified_pull_request(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            n = (
                await conn.execute(text("SELECT count(*) FROM pull_request_evidence_snapshots"))
            ).scalar_one()
            assert n == 0  # deny-by-default: no GUC set
    async with tenant_scope(TenantContext(t2)) as session:
        assert (
            await _pr_repo(session, TenantContext(t2)).latest_pull_request_for_pr(
                p1, "github", "owner/repo", 7
            )
            is None
        )


@pytest.mark.db
async def test_audit_is_safe_metadata_only(pr_ctx, admin_engine):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    secret_repo = "private-org/secret-repo"
    async with tenant_scope(ctx) as session:
        issue_id = await _seed_issue(session, ctx, p1)
        row = await _pr_repo(session, ctx).record_connector_verified_pull_request(
            project_id=p1,
            payload=_conn_payload(
                repo_ref=secret_repo,
                author_principal="secret-author",
                traceability_refs={"release_issue_ids": [str(issue_id)]},
            ),
            actor="conn",
        )
        sid = row.id
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM audit_logs WHERE target=:tg AND tenant_id=:t "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"tg": f"pull_request_evidence_snapshot:{sid}", "t": t1},
            )
        ).scalar_one()
    blob = str(payload)
    assert secret_repo not in blob  # repo_ref never audited
    assert "secret-author" not in blob  # principals never audited
    assert str(issue_id) not in blob  # traceability UUIDs never audited
    assert "repo_ref" not in payload and "author_principal" not in payload


# --- Docker-free: GitHub PR mapping (B-29-1) ----------------------------------


def _gh_pull(**over) -> dict:
    p = {
        "number": 7,
        "state": "closed",
        "merged": True,
        "merge_commit_sha": "a1b2c3d4e5f6",
        "merged_at": "2026-06-20T00:00:00Z",
        "base": {"ref": "main", "sha": "basesha1"},
        "head": {"ref": "feature/x", "sha": "headsha1"},
        "user": {"login": "alice"},
        "merged_by": {"login": "carol"},
    }
    p.update(over)
    return p


def _gh_reviews() -> list:
    return [{"user": {"login": "bob"}, "state": "APPROVED", "submitted_at": "2026-06-19T00:00:00Z"}]


def test_map_github_pull_merged_facts():
    from app.release.scm_connector import map_github_pull_request

    m = map_github_pull_request(_gh_pull(), _gh_reviews())
    assert m["pr_state"] == "merged"
    assert m["merged"] is True
    assert m["merge_commit_sha"] == "a1b2c3d4e5f6"
    assert m["base_branch"] == "main" and m["head_branch"] == "feature/x"
    assert m["author_principal"] == "alice"
    assert m["merger_principal"] == "carol"
    assert m["approver_principals"] == ["bob"]
    assert m["approval_count"] == 1
    assert m["check_status_summary"] is None  # no checks provided -> not observed


@pytest.mark.parametrize(
    "state,merged,expected",
    [("open", False, "open"), ("closed", False, "closed"), ("closed", True, "merged")],
)
def test_map_pr_state_derivation(state, merged, expected):
    from app.release.scm_connector import map_github_pull_request

    m = map_github_pull_request(_gh_pull(state=state, merged=merged), [])
    assert m["pr_state"] == expected


def test_map_requires_pull_and_reviews():
    from app.release.scm_connector import SCMConnectorError, map_github_pull_request

    with pytest.raises(SCMConnectorError):
        map_github_pull_request("not-a-dict", [])
    with pytest.raises(SCMConnectorError):
        map_github_pull_request(_gh_pull(), "not-a-list")


def test_map_checks_summary_states():
    from app.release.scm_connector import map_github_pull_request

    checks = {
        "check_runs": [
            {"status": "completed", "conclusion": "success"},
            {"status": "completed", "conclusion": "failure"},
            {"status": "in_progress", "conclusion": None},
            {"status": "completed", "conclusion": "neutral"},
        ]
    }
    m = map_github_pull_request(
        _gh_pull(), _gh_reviews(), checks=checks, combined_status={"state": "failure"}
    )
    css = m["check_status_summary"]
    assert css["success"] == 1 and css["failure"] == 1
    assert css["pending"] == 1 and css["neutral"] == 1
    assert css["combined_state"] == "failure"


def test_map_requested_reviewers_observed_flag():
    from app.release.scm_connector import map_github_pull_request

    rr = {"users": [{"login": "dan"}], "teams": [{"slug": "team-a"}]}
    m = map_github_pull_request(
        _gh_pull(), _gh_reviews(), requested_reviewers=rr, requested_reviewers_observed=True
    )
    assert m["requested_reviewers_observed"] is True
    assert "dan" in m["requested_reviewer_principals"]
    # not observed -> empty list + false (no silent empty)
    m2 = map_github_pull_request(
        _gh_pull(), _gh_reviews(), requested_reviewers=rr, requested_reviewers_observed=False
    )
    assert m2["requested_reviewers_observed"] is False
    assert m2["requested_reviewer_principals"] == []


async def test_fake_connector_fetch_pull_request():
    from app.release.scm_connector import FakeSCMConnector, SCMConnectorError

    ok = FakeSCMConnector(result={"pr_state": "open"})
    assert (await ok.fetch_pull_request(repo_ref="o/r", pr_number=1)) == {"pr_state": "open"}
    boom = FakeSCMConnector(error=SCMConnectorError("x"))
    with pytest.raises(SCMConnectorError):
        await boom.fetch_pull_request(repo_ref="o/r", pr_number=1)


# --- DB-backed: broker-gated service (B-29-4/7) -------------------------------


async def _declare_repo(session, ctx, project_id, repo_ref, branch="main"):
    from app.repositories.intake_categories import IntakeCategoryRepository

    repo = IntakeCategoryRepository(session, ctx)
    data = {"primary_repository": repo_ref, "protected_branch": branch}
    await repo.declare(
        project_id=project_id,
        category="existing_assets_and_repositories",
        actor="a",
        data=data,
        origin="test",
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


def _mapped_pr(**over) -> dict:
    rec = {
        "pr_state": "merged",
        "merged": True,
        "base_branch": "main",
        "head_branch": "feature/x",
        "merge_commit_sha": "a1b2c3d4",
        "author_principal": "alice",
        "approver_principals": ["bob"],
        "reviewer_principals": [{"principal": "bob", "latest_state": "APPROVED"}],
        "approval_count": 1,
        "requested_reviewer_principals": [],
        "requested_reviewers_observed": True,
        "merger_principal": "carol",
        "check_status_summary": None,
    }
    rec.update(over)
    return rec


async def _allow_setup(session, ctx, project_id, agent_id="conn"):
    from app.policy.levels import AutonomyLevel
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.tools import ToolAllowlistRepository

    await _declare_repo(session, ctx, project_id, "owner/repo")
    await _declare_secrets(session, ctx, project_id)
    await AutonomyPolicyRepository(session, ctx).upsert(
        project_id=project_id, autonomy_level=int(AutonomyLevel.A5), actor="a"
    )
    await ToolAllowlistRepository(session, ctx).grant(
        agent_id=agent_id, tool_name="source_control.read_pull_request", actor="admin"
    )


@pytest.mark.db
async def test_refresh_broker_allow_writes_safe_params(pr_ctx, admin_engine):
    from app.release.pr_evidence_service import refresh_pull_request_evidence
    from app.release.scm_connector import FakeSCMConnector
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await _allow_setup(session, ctx, p1)
        result = await refresh_pull_request_evidence(
            session,
            ctx,
            project_id=p1,
            pr_number=7,
            agent_id="conn",
            actor="conn",
            connector=FakeSCMConnector(_mapped_pr()),
            presence_flags={"tests_added": {"present": True, "source": "caller_declared"}},
        )
        assert result.wrote is True
        row = await _pr_repo(session, ctx).latest_pull_request_for_pr(p1, "github", "owner/repo", 7)
        assert row.provenance == "connector_verified"
        assert row.presence_flags["tests_added"]["source"] == "caller_declared"
    # broker recorded the tool call with SAFE params only — never the raw repo_ref.
    async with admin_engine.connect() as c:
        params_rows = (
            await c.execute(
                text(
                    "SELECT params FROM tool_calls WHERE tenant_id=:t "
                    "AND tool_name='source_control.read_pull_request'"
                ),
                {"t": str(t1)},
            )
        ).all()
    assert params_rows
    for (params,) in params_rows:
        assert "repo_ref" not in (params or {})
        assert params.get("repo_ref_present") is True
        assert params.get("pr_number") == 7  # pr_number is a safe param (not a secret)


@pytest.mark.db
@pytest.mark.parametrize("scenario", ["repo_unbound", "broker_denied", "connector_error", "no_pr"])
async def test_refresh_no_write_paths(pr_ctx, scenario):
    from app.release.pr_evidence_service import refresh_pull_request_evidence
    from app.release.scm_connector import FakeSCMConnector, SCMConnectorError
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        connector = FakeSCMConnector(_mapped_pr())
        if scenario == "repo_unbound":
            pass  # no declared repo
        elif scenario == "broker_denied":
            await _declare_repo(session, ctx, p1, "owner/repo")
            await _declare_secrets(session, ctx, p1)  # declared, but agent not allowlisted
        elif scenario == "connector_error":
            await _allow_setup(session, ctx, p1)
            connector = FakeSCMConnector(error=SCMConnectorError("reviews endpoint 500"))
        elif scenario == "no_pr":
            await _allow_setup(session, ctx, p1)
            connector = FakeSCMConnector(result=None)
        result = await refresh_pull_request_evidence(
            session, ctx, project_id=p1, pr_number=7, agent_id="conn", actor="conn",
            connector=connector,
        )
        assert result.wrote is False
        assert await repo.count_connector_verified_pull_requests(p1) == 0


# --- DB-backed: no A5 regression (Q6 store-only) ------------------------------


@pytest.mark.db
async def test_pr_evidence_does_not_change_a5_report(pr_ctx):
    # Q6: store-only. PR evidence must NOT alter the production_autonomy report in any way.
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        before = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
        await _pr_repo(session, ctx).record_connector_verified_pull_request(
            project_id=p1,
            payload=_conn_payload(
                author_principal="alice", approver_principals=["alice"], merger_principal="alice"
            ),
            actor="conn",
        )
        after = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
    assert before == after  # byte-identical: PR evidence feeds no gate (the Slice-29 invariant)
    # The ruleset reflects the latest slice that touched the A5 engine (Slice 31 bumped it to
    # slice43.v1); PR evidence still changes nothing — proven by ``before == after`` above.
    assert after["ruleset_version"] == "slice54.v1"
    assert after["a5_satisfied"] is False
    assert after["can_go_live_autonomously"] is False


# ============================================================================
# Code-review fixes (Slice 29 review round) — RED-first regression tests
# ============================================================================


# --- A: merged_at ISO string must be parsed to a datetime (asyncpg crash) -----


def test_parse_iso_timestamp_and_mapper_merged_at_is_datetime():
    from app.release.pr_evidence import parse_iso_timestamp
    from app.release.scm_connector import map_github_pull_request

    assert parse_iso_timestamp(None) is None
    dt = parse_iso_timestamp("2026-06-20T00:00:00Z")
    assert isinstance(dt, datetime) and dt.tzinfo is not None
    # passthrough an existing datetime unchanged
    assert parse_iso_timestamp(dt) == dt
    # the mapper must emit a datetime (not the raw provider string)
    m = map_github_pull_request(_gh_pull(merged_at="2026-06-20T00:00:00Z"), _gh_reviews())
    assert isinstance(m["merged_at"], datetime)


@pytest.mark.db
async def test_connector_record_accepts_string_merged_at(pr_ctx):
    # Defense-in-depth: repo coerces a string merged_at so a merged PR never crashes on flush.
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        row = await _pr_repo(session, ctx).record_connector_verified_pull_request(
            project_id=p1, payload=_conn_payload(merged_at="2026-06-20T00:00:00Z"), actor="conn"
        )
        assert isinstance(row.merged_at, datetime)


# --- C: a null-timestamp review must not supersede a real one -----------------


def test_normalize_approvals_null_timestamp_does_not_drop_approval():
    reviews = [
        _rev("bob", "APPROVED", "2026-06-01T00:00:00Z"),
        _rev("bob", "PENDING", None),  # own pending review, null submitted_at
    ]
    approvers, _, count = normalize_approvals(reviews)
    assert approvers == ["bob"] and count == 1  # approval retained


# --- D: combined-status 'error' must be recorded, not dropped -----------------


def test_summarize_checks_maps_combined_error_to_failure():
    from app.release.scm_connector import map_github_pull_request

    m = map_github_pull_request(_gh_pull(), _gh_reviews(), combined_status={"state": "error"})
    assert m["check_status_summary"] is not None
    assert m["check_status_summary"]["combined_state"] == "failure"


# --- F: principal lists must be validated (no list()-coercion corruption) -----


@pytest.mark.parametrize(
    "over",
    [
        {"approver_principals": "bob"},  # non-list string
        {"approver_principals": [{"principal": "alice"}]},  # dict elements
        {"approver_principals": [1, 2]},  # non-string elements
        {"author_principal": 123},  # non-string scalar
        {"requested_reviewer_principals": "dan"},  # non-list
    ],
)
def test_principal_lists_rejected(over):
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_new_pull_request(_valid(**over))


# --- G: merged <-> pr_state consistency ---------------------------------------


@pytest.mark.parametrize(
    "over",
    [{"pr_state": "merged", "merged": False}, {"pr_state": "open", "merged": True}],
)
def test_merged_pr_state_consistency_enforced(over):
    with pytest.raises(InvalidPullRequestSnapshot):
        validate_new_pull_request(_valid(**over))


# --- H: self_merge_observed requires merged=True ------------------------------


def test_self_merge_requires_merged():
    f = derive_separation_flags(
        author_principal="alice",
        approver_principals=["alice"],
        merger_principal="alice",
        merged=False,
    )
    assert f["self_merge_observed"] is False  # not merged -> cannot be a self-merge


# --- E: merged-protected binds to the DECLARED protected branch ---------------


@pytest.mark.db
async def test_merged_protected_requires_declared_branch_match(pr_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        repo = _pr_repo(session, ctx)
        # Declared protected branch = main. A verified+fresh BP snapshot exists for a NON-declared
        # branch 'develop'. A PR merged to 'develop' must NOT be 'merged_to_declared_protected_branch'.
        await _declare_repo(session, ctx, p1, "owner/repo", branch="main")
        await _seed_verified_bp(session, ctx, p1, "owner/repo", "develop", _now())
        row = await repo.record_connector_verified_pull_request(
            project_id=p1, payload=_conn_payload(merged=True, base_branch="develop"), actor="conn"
        )
        assert row.merged_to_declared_protected_branch_observed is False
        # base matches the declared protected branch + verified+fresh BP -> True
        await _seed_verified_bp(session, ctx, p1, "owner/repo", "main", _now())
        row2 = await repo.record_connector_verified_pull_request(
            project_id=p1, payload=_conn_payload(merged=True, base_branch="main"), actor="conn"
        )
        assert row2.merged_to_declared_protected_branch_observed is True


# --- J: DB guard must reject integer-valued floats in check_status_summary ----


@pytest.mark.db
async def test_db_guard_rejects_integer_valued_float_count(pr_ctx, rls_engine):
    # J: counts must be TRUE JSON integers. A float like 1.0 must be rejected so the DB guard is an
    # authoritative backstop matching the Python validator (which rejects floats via _is_int).
    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, checks='{"success":1.0}')


@pytest.mark.db
async def test_db_guard_still_accepts_integer_count(pr_ctx, rls_engine):
    # Legitimate integer counts continue to pass after the J tightening.
    t1, p1 = pr_ctx["t1"], pr_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1, checks='{"success":3,"failure":0}')


# --- Docker-free: GitHubSCMConnector malformed-200-JSON fail-closed (live path) -


def _gh_client(malformed_kind):
    """Build a monkeypatch httpx.AsyncClient whose endpoints return 200 but one chosen endpoint's
    .json() raises (malformed body). No network."""
    bodies = {
        "pr": _gh_pull(),
        "reviews": _gh_reviews(),
        "requested": {"users": [{"login": "dan"}], "teams": []},
        "checks": {"check_runs": [{"status": "completed", "conclusion": "success"}]},
        "status": {"state": "success"},
    }

    class _Resp:
        def __init__(self, kind):
            self.kind = kind
            self.status_code = 200

        def json(self):
            if self.kind == malformed_kind:
                raise ValueError("not json")
            return bodies[self.kind]

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            if "requested_reviewers" in url:
                kind = "requested"
            elif "/reviews" in url:
                kind = "reviews"
            elif "check-runs" in url:
                kind = "checks"
            elif url.endswith("/status"):
                kind = "status"
            else:
                kind = "pr"
            return _Resp(kind)

    return _Client


@pytest.mark.parametrize("malformed", ["pr", "reviews"])
async def test_github_fetch_pr_mandatory_malformed_json_fails_closed(monkeypatch, malformed):
    import httpx

    from app.release.scm_connector import GitHubSCMConnector, SCMConnectorError

    monkeypatch.setattr(httpx, "AsyncClient", _gh_client(malformed))
    with pytest.raises(SCMConnectorError):
        await GitHubSCMConnector("tok").fetch_pull_request(repo_ref="owner/repo", pr_number=7)


async def test_github_fetch_pr_optional_requested_malformed_degrades(monkeypatch):
    import httpx

    from app.release.scm_connector import GitHubSCMConnector

    monkeypatch.setattr(httpx, "AsyncClient", _gh_client("requested"))
    mapped = await GitHubSCMConnector("tok").fetch_pull_request(repo_ref="owner/repo", pr_number=7)
    assert mapped["requested_reviewers_observed"] is False
    assert mapped["requested_reviewer_principals"] == []
    assert mapped["pr_state"] == "merged"  # mandatory evidence still mapped


@pytest.mark.parametrize("malformed", ["checks", "status"])
async def test_github_fetch_pr_optional_checks_malformed_degrades(monkeypatch, malformed):
    import httpx

    from app.release.scm_connector import GitHubSCMConnector

    monkeypatch.setattr(httpx, "AsyncClient", _gh_client(malformed))
    mapped = await GitHubSCMConnector("tok").fetch_pull_request(repo_ref="owner/repo", pr_number=7)
    assert mapped["check_status_summary"] is None  # malformed check evidence ⇒ not observed
    assert mapped["pr_state"] == "merged"  # mandatory evidence still mapped
