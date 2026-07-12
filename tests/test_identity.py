"""Verified actor identity (Slice 27, §2.2/§5.2/§7.x/§23.4).

The ``request_authenticated`` provenance tier is **key-custody-based, not a human signature**.
Docker-free tests cover the pure identity model. DB-backed (``db``) tests cover: resolver → principal,
``require_tenant`` building ``TenantContext.actor``, approval **dual** provenance (requester vs
resolver) + the §2.2 verified self-approval refusal, risk-acceptance **actor-bound** signer semantics,
tenant isolation of the principal, and that the A5 report is **unchanged** (no gate flips).
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.identity import (
    ACTOR_TYPES,
    APP_WRITABLE,
    IDENTITY_PROVENANCES,
    AuthenticatedActor,
    InvalidActor,
    actor_fields,
    validate_actor,
)

# --- Docker-free: pure model --------------------------------------------------


def test_constants():
    assert ACTOR_TYPES == ("human", "service")
    assert IDENTITY_PROVENANCES == ("caller_supplied_unverified", "request_authenticated")
    assert APP_WRITABLE == ("request_authenticated",)


def test_validate_actor_good():
    a = validate_actor("alice", "human")
    assert isinstance(a, AuthenticatedActor)
    assert (a.subject, a.actor_type, a.provenance) == ("alice", "human", "request_authenticated")
    assert validate_actor("ci-bot", "service").actor_type == "service"


@pytest.mark.parametrize(
    "subject,actor_type",
    [
        ("", "human"),
        ("   ", "human"),
        ("x" * 256, "human"),
        ("alice", "robot"),
        ("alice", ""),
        (None, "human"),
        ("alice", None),
    ],
)
def test_validate_actor_bad(subject, actor_type):
    with pytest.raises(InvalidActor):
        validate_actor(subject, actor_type)


def test_actor_fields_verified_stamps_request_authenticated():
    a = validate_actor("alice", "human")
    assert actor_fields(a, "ignored-fallback") == ("alice", "request_authenticated")


def test_actor_fields_unverified_falls_back():
    assert actor_fields(None, "caller-typed-name") == (
        "caller-typed-name",
        "caller_supplied_unverified",
    )


def test_a5_report_unchanged_no_gate_flip():
    # Slice 27 adds no gate-flipping input: at R5 only gate #1 passes, go-live false.
    from app.release.production_autonomy import evaluate_production_autonomy

    d = evaluate_production_autonomy("p", readiness_level="R5").to_dict()
    assert d["passed_gate_count"] == 1
    assert d["can_go_live_autonomously"] is False


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(c, sql, **p):
    return (await c.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def id_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('IdOrg',:s) RETURNING id",
            s=f"id-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"id-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"id-{proj}-{sfx}",
            )
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.tenancy import TenantContext, tenant_scope

    context = TenantContext(out["t1"])
    async with tenant_scope(context) as session:
        issue = await ReleaseIssueRepository(session, context).create(
            project_id=out["p1"],
            payload={
                "issue_category": "approval",
                "severity": "low",
                "blocking": False,
                "summary": "identity fixture",
                "detail": "fixture",
                "source": "test",
            },
            actor="fixture",
        )
        candidates = ReleaseCandidateRepository(session, context)
        candidate = await candidates.create(
            project_id=out["p1"], payload={"release_ref": f"ID-{sfx}"}, actor="fixture"
        )
        await candidates.bind_issue(
            candidate_id=candidate.id, release_issue_id=issue.id, actor="fixture"
        )
        await candidates.freeze(candidate_id=candidate.id, actor="fixture")
        out["issue_id"] = issue.id
        out["release_ref"] = candidate.release_ref
    return out


async def _issue_raw_key(admin_engine, tenant_id, subject, actor_type, status="active"):
    from app.repositories.api_keys import generate_raw_key, hash_key

    raw = generate_raw_key()
    async with admin_engine.begin() as c:
        await c.execute(
            text(
                "INSERT INTO tenant_api_keys "
                "(tenant_id, key_hash, label, status, principal_subject, actor_type) "
                "VALUES (:t,:h,'k',:st,:ps,:at)"
            ),
            {"t": str(tenant_id), "h": hash_key(raw), "st": status, "ps": subject, "at": actor_type},
        )
    return raw


def _ra_payload(ctx, **over):
    p = {
        "release_id": ctx["release_ref"],
        "issue_id": str(ctx["issue_id"]),
        "subject_type": "release_issue",
        "severity": "low",
        "reason_for_acceptance": "x",
        "business_impact": "x",
        "rollback_or_mitigation_plan": "x",
        "required_follow_up_ticket": "T-1",
        "expiry_date": date(2099, 1, 1),
        "owner": "alice",
        "approver": "alice",
        "accepted_by": ["alice", "bob"],
        "approval_authority_source": "approval_matrix",
    }
    p.update(over)
    return p


# --- DB-backed: resolver + require_tenant -> verified principal ----------------


@pytest.mark.db
async def test_resolve_and_require_tenant_builds_actor(id_ctx, admin_engine):
    from app.api.auth import require_tenant

    raw = await _issue_raw_key(admin_engine, id_ctx["t1"], "alice", "human")
    ctx = await require_tenant(authorization=f"Bearer {raw}")
    assert ctx.tenant_id == id_ctx["t1"]
    assert ctx.actor is not None
    assert (ctx.actor.subject, ctx.actor.actor_type, ctx.actor.provenance) == (
        "alice",
        "human",
        "request_authenticated",
    )


@pytest.mark.db
async def test_unknown_and_revoked_key_401(id_ctx, admin_engine):
    from fastapi import HTTPException

    from app.api.auth import require_tenant

    revoked = await _issue_raw_key(admin_engine, id_ctx["t1"], "alice", "human", status="revoked")
    with pytest.raises(HTTPException):
        await require_tenant(authorization=f"Bearer {revoked}")
    with pytest.raises(HTTPException):
        await require_tenant(authorization="Bearer uaidk_definitely-not-a-key")


@pytest.mark.db
async def test_resolver_grants_least_privilege(admin_engine):
    async with admin_engine.connect() as c:
        owner = (
            await c.execute(
                text(
                    "SELECT r.rolname FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner "
                    "WHERE p.proname='resolve_tenant_api_key'"
                )
            )
        ).scalar_one()
        assert owner == "api_key_resolver"
        has_exec = (
            await c.execute(
                text(
                    "SELECT has_function_privilege('uaid_app',"
                    "'public.resolve_tenant_api_key(text)','EXECUTE')"
                )
            )
        ).scalar_one()
        assert has_exec is True
        # uaid_app must NOT read the global key table directly (D4 invariant preserved).
        has_select = (
            await c.execute(
                text("SELECT has_table_privilege('uaid_app','tenant_api_keys','SELECT')")
            )
        ).scalar_one()
        assert has_select is False


# --- DB-backed: approvals dual provenance + §2.2 separation -------------------


@pytest.mark.db
async def test_approval_verified_dual_provenance(id_ctx):
    from app.repositories.approvals import ApprovalRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx_a = TenantContext(id_ctx["t1"], actor=validate_actor("alice", "human"))
    async with tenant_scope(ctx_a) as s:
        ap = await ApprovalRepository(s, ctx_a).request(
            project_id=id_ctx["p1"], action="run_tests", risk_tier="low", requested_by="ignored"
        )
        ap_id = ap.id
        assert ap.requested_by == "alice"
        assert ap.requested_by_provenance == "request_authenticated"
    ctx_b = TenantContext(id_ctx["t1"], actor=validate_actor("bob", "human"))
    async with tenant_scope(ctx_b) as s:
        ap2 = await ApprovalRepository(s, ctx_b).approve(approval_id=ap_id, actor="ignored")
        assert ap2.resolved_by == "bob"
        assert ap2.approver_provenance == "request_authenticated"


@pytest.mark.db
async def test_approval_verified_self_approval_refused(id_ctx):
    from app.approvals.states import InvalidApprovalRequest
    from app.repositories.approvals import ApprovalRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(id_ctx["t1"], actor=validate_actor("alice", "human"))
    async with tenant_scope(ctx) as s:
        repo = ApprovalRepository(s, ctx)
        ap = await repo.request(
            project_id=id_ctx["p1"], action="run_tests", risk_tier="low", requested_by="x"
        )
        with pytest.raises(InvalidApprovalRequest):
            await repo.approve(approval_id=ap.id, actor="x")


@pytest.mark.db
async def test_approval_unverified_fallback(id_ctx):
    from app.repositories.approvals import ApprovalRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(id_ctx["t1"])  # no actor
    async with tenant_scope(ctx) as s:
        ap = await ApprovalRepository(s, ctx).request(
            project_id=id_ctx["p1"], action="run_tests", risk_tier="low", requested_by="caller-name"
        )
        assert ap.requested_by == "caller-name"
        assert ap.requested_by_provenance == "caller_supplied_unverified"


# --- DB-backed: risk-acceptance actor-bound signer ----------------------------


@pytest.mark.db
async def test_risk_acceptance_verified_actor_bound(id_ctx):
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(id_ctx["t1"], actor=validate_actor("alice", "human"))
    async with tenant_scope(ctx) as s:
        row = await RiskAcceptanceRepository(s, ctx).create(
            project_id=id_ctx["p1"], payload=_ra_payload(id_ctx), actor="ignored"
        )
        assert row.approver_provenance == "request_authenticated"


@pytest.mark.db
async def test_risk_acceptance_verified_signer_mismatch_refused(id_ctx):
    from app.release.risk_acceptance import InvalidRiskAcceptance
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(id_ctx["t1"], actor=validate_actor("alice", "human"))
    async with tenant_scope(ctx) as s:
        repo = RiskAcceptanceRepository(s, ctx)
        with pytest.raises(InvalidRiskAcceptance):  # approver != verified subject
            await repo.create(
                project_id=id_ctx["p1"],
                payload=_ra_payload(id_ctx, approver="carol"),
                actor="x",
            )
    async with tenant_scope(ctx) as s:
        repo = RiskAcceptanceRepository(s, ctx)
        with pytest.raises(InvalidRiskAcceptance):  # verified subject not among accepted_by
            await repo.create(
                project_id=id_ctx["p1"],
                payload=_ra_payload(id_ctx, accepted_by=["bob"]),
                actor="x",
            )


@pytest.mark.db
async def test_risk_acceptance_unverified_default(id_ctx):
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(id_ctx["t1"])  # no actor
    async with tenant_scope(ctx) as s:
        row = await RiskAcceptanceRepository(s, ctx).create(
            project_id=id_ctx["p1"], payload=_ra_payload(id_ctx), actor="x"
        )
        assert row.approver_provenance == "caller_supplied_unverified"


# --- DB-backed: tenant isolation of the principal -----------------------------


@pytest.mark.db
async def test_principal_resolves_only_to_its_own_tenant(id_ctx, admin_engine):
    from app.api.auth import require_tenant

    raw = await _issue_raw_key(admin_engine, id_ctx["t1"], "alice", "human")
    ctx = await require_tenant(authorization=f"Bearer {raw}")
    # Bound to t1 only; nothing maps this key's principal to t2.
    assert ctx.tenant_id == id_ctx["t1"]
    assert ctx.tenant_id != id_ctx["t2"]
