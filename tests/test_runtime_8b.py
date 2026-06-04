"""Slice 8b — durable runtime integration (§23.2 + §18 + §19) tests.

Docker-free: explicit-approval gate matrix, no-lapse, event-type set.
DB-backed (`db`): subject-scoped approval gate, gate-before-protected-work, the
PENDING/APPROVED/terminal-denial resume matrix, cross-tenant isolation, node
retry/backoff (retried only for attempts > 1), and cost STOP→pause.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.approvals.states import RiskTier, Status, auto_transition
from app.approvals.states import is_blocked as gate_is_blocked
from app.models.run_step import _EVENT_TYPES
from app.repositories.approvals import ApprovalRepository
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.runtime.engine import (
    PROTECTED_NODE,
    WORKFLOW_RESUME_ACTION,
    PermanentNodeError,
    TransientNodeError,
    resume_approval_run,
    resume_costguard_run,
    run_failing_demo,
    run_retry_demo,
    start_approval_run,
    start_costguard_run,
    workflow_subject,
)
from app.tenancy import TenantContext, tenant_scope


# --- Docker-free --------------------------------------------------------------


def test_explicit_gate_matrix():
    # With requires_explicit=True only APPROVED unblocks; everything else blocks.
    for status in Status:
        expected_blocked = status is not Status.APPROVED
        assert gate_is_blocked(status, requires_explicit=True) is expected_blocked, status


def test_explicit_waits_never_auto_lapse():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    overdue = t0 + timedelta(hours=25)
    for tier in (RiskTier.LOW, RiskTier.MEDIUM, RiskTier.HIGH):
        assert auto_transition(tier, True, t0, overdue) is None


def test_event_types_include_8b():
    assert {"blocked_on_approval", "retried", "cost_paused"} <= set(_EVENT_TYPES)


def test_node_error_types_distinct():
    assert issubclass(TransientNodeError, Exception)
    assert issubclass(PermanentNodeError, Exception)
    assert TransientNodeError is not PermanentNodeError


# --- DB-backed fixtures -------------------------------------------------------


async def _scalar(c, sql, **p):
    return (await c.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def b_ctx(admin_engine):
    """Two tenants; tenant1 P1 with runs ra..rh; tenant2 PX with run rx. status='created'."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('B8Org',:s) RETURNING id",
            s=f"b8-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"b8-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"b8-{proj}-{sfx}",
            )
        for run in ("ra", "rb", "rc", "rd", "re", "rf", "rg", "rh"):
            out[run] = await _scalar(
                c,
                "INSERT INTO project_runs (tenant_id, project_id, status) "
                "VALUES (:t,:p,'created') RETURNING id",
                t=out["t1"],
                p=out["p1"],
            )
        out["rx"] = await _scalar(
            c,
            "INSERT INTO project_runs (tenant_id, project_id, status) "
            "VALUES (:t,:p,'created') RETURNING id",
            t=out["t2"],
            p=out["px"],
        )
    return out


async def _status(admin_engine, run_id) -> str:
    async with admin_engine.connect() as c:
        return (
            await c.execute(text("SELECT status FROM project_runs WHERE id=:r"), {"r": run_id})
        ).scalar_one()


async def _count_steps(admin_engine, run_id, *, node=None, event_type=None) -> int:
    sql = "SELECT count(*) FROM run_steps WHERE run_id=:r"
    params = {"r": run_id}
    if node is not None:
        sql += " AND node=:n"
        params["n"] = node
    if event_type is not None:
        sql += " AND event_type=:e"
        params["e"] = event_type
    async with admin_engine.connect() as c:
        return (await c.execute(text(sql), params)).scalar_one()


# --- DB-backed: subject-scoped approval gate ----------------------------------


@pytest.mark.db
async def test_subject_scoped_gate(b_ctx):
    t1, p1, ra, rb = b_ctx["t1"], b_ctx["p1"], b_ctx["ra"], b_ctx["rb"]
    ctx = TenantContext(t1)
    subj_a = workflow_subject(ra, PROTECTED_NODE)
    async with tenant_scope(ctx) as session:
        approvals = ApprovalRepository(session, ctx)
        appr = await approvals.request(
            project_id=p1,
            action=WORKFLOW_RESUME_ACTION,
            risk_tier="high",
            requested_by="u",
            requires_explicit_approval=True,
            subject_ref=subj_a,
        )
        await approvals.approve(approval_id=appr.id, actor="boss")
        # unblocks ONLY subject_a
        assert await approvals.is_blocked(p1, WORKFLOW_RESUME_ACTION, subject_ref=subj_a) is False
        assert (
            await approvals.is_blocked(
                p1, WORKFLOW_RESUME_ACTION, subject_ref=workflow_subject(rb, PROTECTED_NODE)
            )
            is True
        )
        assert (
            await approvals.is_blocked(
                p1, WORKFLOW_RESUME_ACTION, subject_ref=workflow_subject(ra, "other_node")
            )
            is True
        )


@pytest.mark.db
async def test_action_level_approval_does_not_satisfy_subject_gate(b_ctx):
    t1, p1, ra = b_ctx["t1"], b_ctx["p1"], b_ctx["ra"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        approvals = ApprovalRepository(session, ctx)
        # action-level (subject_ref=NULL) APPROVED
        appr = await approvals.request(
            project_id=p1,
            action=WORKFLOW_RESUME_ACTION,
            risk_tier="high",
            requested_by="u",
            requires_explicit_approval=True,
            subject_ref=None,
        )
        await approvals.approve(approval_id=appr.id, actor="boss")
        # does NOT satisfy a subject-scoped wait
        assert (
            await approvals.is_blocked(
                p1, WORKFLOW_RESUME_ACTION, subject_ref=workflow_subject(ra, PROTECTED_NODE)
            )
            is True
        )


# --- DB-backed: gate-before-protected-work + resume matrix --------------------


@pytest.mark.db
async def test_start_blocks_and_protected_node_does_not_run(b_ctx, admin_engine):
    t1, p1, ra = b_ctx["t1"], b_ctx["p1"], b_ctx["ra"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        status = await start_approval_run(session, ctx, project_id=p1, run_id=ra)
    assert status == "blocked"
    assert await _status(admin_engine, ra) == "blocked"
    assert await _count_steps(admin_engine, ra, event_type="blocked_on_approval") == 1
    # protected node MUST NOT have run while pending
    assert await _count_steps(admin_engine, ra, node=PROTECTED_NODE) == 0


@pytest.mark.db
async def test_resume_pending_stays_blocked(b_ctx, admin_engine):
    t1, p1, ra = b_ctx["t1"], b_ctx["p1"], b_ctx["ra"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await start_approval_run(session, ctx, project_id=p1, run_id=ra)
    async with tenant_scope(ctx) as session:
        status = await resume_approval_run(session, ctx, project_id=p1, run_id=ra)
    assert status == "blocked"
    assert await _status(admin_engine, ra) == "blocked"
    assert await _count_steps(admin_engine, ra, node=PROTECTED_NODE) == 0


@pytest.mark.db
async def test_approved_resumes_and_completes(b_ctx, admin_engine):
    t1, p1, ra = b_ctx["t1"], b_ctx["p1"], b_ctx["ra"]
    ctx = TenantContext(t1)
    subject = workflow_subject(ra, PROTECTED_NODE)
    async with tenant_scope(ctx) as session:
        await start_approval_run(session, ctx, project_id=p1, run_id=ra)
    async with tenant_scope(ctx) as session:
        approvals = ApprovalRepository(session, ctx)
        appr = await approvals.latest_for(p1, WORKFLOW_RESUME_ACTION, subject_ref=subject)
        await approvals.approve(approval_id=appr.id, actor="boss")
    async with tenant_scope(ctx) as session:
        status = await resume_approval_run(session, ctx, project_id=p1, run_id=ra)
    assert status == "completed"
    assert await _status(admin_engine, ra) == "completed"
    assert (
        await _count_steps(admin_engine, ra, node=PROTECTED_NODE, event_type="step_completed") == 1
    )


@pytest.mark.db
@pytest.mark.parametrize(
    "resolve,reason",
    [("reject", "approval_rejected"), ("cancel", "approval_cancelled")],
)
async def test_terminal_human_denial_fails_run(b_ctx, admin_engine, resolve, reason):
    t1, p1, ra = b_ctx["t1"], b_ctx["p1"], b_ctx["ra"]
    ctx = TenantContext(t1)
    subject = workflow_subject(ra, PROTECTED_NODE)
    async with tenant_scope(ctx) as session:
        await start_approval_run(session, ctx, project_id=p1, run_id=ra)
    async with tenant_scope(ctx) as session:
        approvals = ApprovalRepository(session, ctx)
        appr = await approvals.latest_for(p1, WORKFLOW_RESUME_ACTION, subject_ref=subject)
        await getattr(approvals, resolve)(approval_id=appr.id, actor="boss")
    async with tenant_scope(ctx) as session:
        status = await resume_approval_run(session, ctx, project_id=p1, run_id=ra)
    assert status == "failed"
    assert await _status(admin_engine, ra) == "failed"
    assert await _count_steps(admin_engine, ra, node=PROTECTED_NODE) == 0
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM run_steps WHERE run_id=:r AND event_type='run_failed' "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"r": ra},
            )
        ).scalar_one()
    assert payload["reason"] == reason


@pytest.mark.db
@pytest.mark.parametrize(
    "forced,reason",
    [("expired", "approval_expired"), ("proceeded_by_policy", "approval_proceeded_by_policy")],
)
async def test_forced_terminal_status_fails_run(b_ctx, admin_engine, forced, reason):
    # EXPIRED / PROCEEDED_BY_POLICY are unreachable via auto_transition for explicit
    # waits; force the status (admin) to prove the resume fail path.
    t1, p1, ra = b_ctx["t1"], b_ctx["p1"], b_ctx["ra"]
    ctx = TenantContext(t1)
    subject = workflow_subject(ra, PROTECTED_NODE)
    async with tenant_scope(ctx) as session:
        await start_approval_run(session, ctx, project_id=p1, run_id=ra)
    async with admin_engine.begin() as c:
        await c.execute(
            text("UPDATE approvals SET status=:s WHERE subject_ref=:sr AND tenant_id=:t"),
            {"s": forced, "sr": subject, "t": t1},
        )
    async with tenant_scope(ctx) as session:
        status = await resume_approval_run(session, ctx, project_id=p1, run_id=ra)
    assert status == "failed"
    assert await _count_steps(admin_engine, ra, node=PROTECTED_NODE) == 0
    async with admin_engine.connect() as c:
        payload = (
            await c.execute(
                text(
                    "SELECT payload FROM run_steps WHERE run_id=:r AND event_type='run_failed' "
                    "ORDER BY seq DESC LIMIT 1"
                ),
                {"r": ra},
            )
        ).scalar_one()
    assert payload["reason"] == reason


@pytest.mark.db
async def test_cross_tenant_approval_does_not_unblock(b_ctx, admin_engine):
    t1, t2, p1, px, ra = b_ctx["t1"], b_ctx["t2"], b_ctx["p1"], b_ctx["px"], b_ctx["ra"]
    subject = workflow_subject(ra, PROTECTED_NODE)  # names tenant-1's run
    async with tenant_scope(TenantContext(t1)) as session:
        await start_approval_run(session, TenantContext(t1), project_id=p1, run_id=ra)
    # tenant 2 approves an approval with the SAME subject string (its own project)
    async with tenant_scope(TenantContext(t2)) as session:
        approvals = ApprovalRepository(session, TenantContext(t2))
        appr = await approvals.request(
            project_id=px,
            action=WORKFLOW_RESUME_ACTION,
            risk_tier="high",
            requested_by="u",
            requires_explicit_approval=True,
            subject_ref=subject,
        )
        await approvals.approve(approval_id=appr.id, actor="boss")
    # tenant 1's run stays blocked (tenant 2's approval is invisible)
    async with tenant_scope(TenantContext(t1)) as session:
        status = await resume_approval_run(session, TenantContext(t1), project_id=p1, run_id=ra)
    assert status == "blocked"
    assert await _status(admin_engine, ra) == "blocked"


# --- DB-backed: retry / failure -----------------------------------------------


@pytest.mark.db
async def test_retry_succeeds_records_only_real_retries(b_ctx, admin_engine):
    t1, p1, rb = b_ctx["t1"], b_ctx["p1"], b_ctx["rb"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        status = await run_retry_demo(
            session, ctx, project_id=p1, run_id=rb, fail_times=2, max_attempts=3
        )
    assert status == "completed"
    # retried rows only for attempts > 1 => attempts 2 and 3 => 2 rows
    assert await _count_steps(admin_engine, rb, event_type="retried") == 2
    assert await _count_steps(admin_engine, rb, node="flaky", event_type="step_completed") == 1
    async with admin_engine.connect() as c:
        attempts = [
            r[0]["attempt"]
            for r in (
                await c.execute(
                    text(
                        "SELECT payload FROM run_steps WHERE run_id=:r AND event_type='retried' "
                        "ORDER BY seq"
                    ),
                    {"r": rb},
                )
            ).all()
        ]
    assert attempts == [2, 3]


@pytest.mark.db
async def test_retry_exhausted_fails(b_ctx, admin_engine):
    t1, p1, rc = b_ctx["t1"], b_ctx["p1"], b_ctx["rc"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        status = await run_retry_demo(
            session, ctx, project_id=p1, run_id=rc, fail_times=99, max_attempts=3
        )
    assert status == "failed"
    assert await _status(admin_engine, rc) == "failed"
    # bounded: attempts 2 and 3 recorded (attempt 1 has no row); never exceeds max_attempts
    assert await _count_steps(admin_engine, rc, event_type="retried") == 2
    async with admin_engine.connect() as c:
        reason = (
            await c.execute(
                text(
                    "SELECT payload->>'reason' FROM run_steps WHERE run_id=:r "
                    "AND event_type='run_failed' LIMIT 1"
                ),
                {"r": rc},
            )
        ).scalar_one()
    assert reason == "retry_exhausted"


@pytest.mark.db
async def test_non_retryable_failure_fails_without_retry(b_ctx, admin_engine):
    t1, p1, rd = b_ctx["t1"], b_ctx["p1"], b_ctx["rd"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        status = await run_failing_demo(session, ctx, project_id=p1, run_id=rd)
    assert status == "failed"
    assert await _status(admin_engine, rd) == "failed"
    assert await _count_steps(admin_engine, rd, event_type="retried") == 0
    async with admin_engine.connect() as c:
        reason = (
            await c.execute(
                text(
                    "SELECT payload->>'reason' FROM run_steps WHERE run_id=:r "
                    "AND event_type='run_failed' LIMIT 1"
                ),
                {"r": rd},
            )
        ).scalar_one()
    assert reason == "node_error"


# --- DB-backed: cost STOP → pause ---------------------------------------------


@pytest.mark.db
async def test_cost_stop_pauses_before_node(b_ctx, admin_engine):
    t1, p1, re_ = b_ctx["t1"], b_ctx["p1"], b_ctx["re"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await BudgetRepository(session, ctx).upsert(
            project_id=p1, max_total_cost_usd="10", actor="t"
        )
        await CostEventRepository(session, ctx).record(
            project_id=p1, component="model_inference", amount_usd="25", actor="t"
        )
    async with tenant_scope(ctx) as session:
        status = await start_costguard_run(session, ctx, project_id=p1, run_id=re_)
    assert status == "paused"
    assert await _status(admin_engine, re_) == "paused"
    assert await _count_steps(admin_engine, re_, node="work", event_type="step_completed") == 0
    async with admin_engine.connect() as c:
        reason = (
            await c.execute(
                text(
                    "SELECT payload->>'reason' FROM run_steps WHERE run_id=:r "
                    "AND event_type='cost_paused' LIMIT 1"
                ),
                {"r": re_},
            )
        ).scalar_one()
    assert reason == "budget_exceeded"


@pytest.mark.db
async def test_cost_resume_after_budget_raise_completes(b_ctx, admin_engine):
    t1, p1, rf = b_ctx["t1"], b_ctx["p1"], b_ctx["rf"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        await BudgetRepository(session, ctx).upsert(
            project_id=p1, max_total_cost_usd="10", actor="t"
        )
        await CostEventRepository(session, ctx).record(
            project_id=p1, component="model_inference", amount_usd="25", actor="t"
        )
    async with tenant_scope(ctx) as session:
        assert await start_costguard_run(session, ctx, project_id=p1, run_id=rf) == "paused"
    # raise the ceiling, then resume
    async with tenant_scope(ctx) as session:
        await BudgetRepository(session, ctx).upsert(
            project_id=p1, max_total_cost_usd="1000", actor="t"
        )
    async with tenant_scope(ctx) as session:
        status = await resume_costguard_run(session, ctx, project_id=p1, run_id=rf)
    assert status == "completed"
    assert await _status(admin_engine, rf) == "completed"
    assert await _count_steps(admin_engine, rf, node="work", event_type="step_completed") == 1
