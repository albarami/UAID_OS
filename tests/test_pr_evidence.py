"""Pull-request evidence connector tests (Slice 29, App. B #7 feed / §12.3-12.4).

Immutable, append-only ``pull_request_evidence_snapshots`` with a two-tier provenance: the caller path
writes ``caller_supplied_unverified``; the connector path writes ``connector_verified``. PR + reviews
endpoints are fail-closed; requested-reviewers is observed (``requested_reviewers_observed``); checks are
optional observed-only (``check_status_summary`` nullable). Identity facts are normalized
(latest-review-per-principal) and separation-of-duties flags are structural-only (provider-principal
equality — NOT a verified UAID-actor separation). Store-only: no A5 gate flip, no ``production_autonomy``
edit, ruleset stays ``slice28.v1``.

Docker-free for the pure validators / approval normalization / separation flags / connector mapping;
``db`` for the store, traceability + merged-protected validation, DB guard, broker-gated connector,
and the no-A5-regression check.
"""

import uuid
from datetime import datetime, timezone

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
        for proj, tn in (("p1", "t1"), ("px", "t2")):
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
