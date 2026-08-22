"""Slice 57 incident workflow — DB, RLS, policy, and abort proofs."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.identity import AuthenticatedActor
from app.ops.collect import collect_ops_signals
from app.ops.incident_service import (
    evaluate_post_launch_actions,
    history,
    latest_handover,
    latest_incident,
    list_open,
    open_incident,
    record_log_diagnosis_unavailable,
    record_support_handover,
    transition_incident,
)
from app.ops.incidents import (
    GATED_MATRIX_ACTIONS,
    HandoverPayload,
    IncidentError,
    IncidentIdempotencyConflict,
    IncidentPayload,
)
from app.release.production_autonomy import evaluate_production_autonomy
from app.repositories.autonomy_policies import AutonomyPolicyRepository
from app.tenancy import TenantContext, tenant_scope
from tests.ops_incidents_support import FINDINGS_GUARD_MD5


def _payload(
    *,
    category: str = "error",
    severity: str = "high",
    summary: str = "api 5xx burst",
    detail: str | None = None,
    source_signal_id: uuid.UUID | None = None,
    pm_issue_mapping_id: uuid.UUID | None = None,
) -> IncidentPayload:
    return IncidentPayload(
        category=category,
        severity=severity,
        summary=summary,
        detail=detail,
        source_signal_id=source_signal_id,
        pm_issue_mapping_id=pm_issue_mapping_id,
    )


async def _set_policy(ctx, project_id, level, overrides=None):
    async with tenant_scope(ctx) as session:
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=project_id,
            autonomy_level=level,
            overrides=overrides or {},
            actor="inc-test",
        )


def _by_seq(actions):
    return {child.seq: child for child in actions}


@pytest.mark.db
async def test_missing_policy_and_a0_persist_zero_tickets(inc_ctx, admin_engine):
    ctx = TenantContext(inc_ctx["t1"])
    p1 = inc_ctx["p1"]
    missing = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"miss-{inc_ctx['suffix']}"
    )
    assert missing.ticket_id is None
    assert _by_seq(missing.actions)[1].policy_decision == "deny"
    await _set_policy(ctx, p1, 0)
    a0 = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"a0-{inc_ctx['suffix']}"
    )
    assert a0.ticket_id is None
    async with admin_engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM ops_incident_tickets WHERE project_id=:p"),
                {"p": p1},
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.db
async def test_a1_writes_one_ticket_and_tightened_override_denies(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    p1 = inc_ctx["p1"]
    await _set_policy(ctx, p1, 1)
    first = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"a1-{inc_ctx['suffix']}"
    )
    assert first.ticket_id is not None
    assert _by_seq(first.actions)[1].execution_posture == "local_ticket_written"
    await _set_policy(ctx, p1, 1, {"create_project_tasks": {"allow": False}})
    denied = await open_incident(
        ctx,
        p1,
        actor="inc-test",
        payload=_payload(summary="other incident"),
        idempotency_key=f"deny-{inc_ctx['suffix']}",
    )
    assert denied.ticket_id is None
    assert _by_seq(denied.actions)[1].policy_decision == "deny"


@pytest.mark.db
async def test_open_and_reeval_route_through_decision_for(inc_ctx, monkeypatch):
    ctx = TenantContext(inc_ctx["t1"])
    p1 = inc_ctx["p1"]
    await _set_policy(ctx, p1, 1)
    seen: list[str] = []
    original = AutonomyPolicyRepository.decision_for

    async def wrapped(self, project_id, action):
        seen.append(action)
        return await original(self, project_id, action)

    monkeypatch.setattr(AutonomyPolicyRepository, "decision_for", wrapped)
    opened = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"gate-{inc_ctx['suffix']}"
    )
    assert opened.ticket_id is not None
    assert seen == list(GATED_MATRIX_ACTIONS)
    seen.clear()
    await evaluate_post_launch_actions(ctx, p1, opened.id)
    assert seen == list(GATED_MATRIX_ACTIONS)
    assert "none" not in seen


@pytest.mark.db
async def test_a2_a5_transitions_diagnosis_and_idempotency(inc_ctx, admin_engine):
    ctx = TenantContext(inc_ctx["t1"])
    p1 = inc_ctx["p1"]
    await _set_policy(ctx, p1, 2)
    a2 = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"a2-{inc_ctx['suffix']}"
    )
    mapped = _by_seq(a2.actions)
    assert mapped[3].policy_decision == "allow"
    assert mapped[5].policy_decision == "deny"
    assert mapped[6].execution_posture == "recorded_not_executed"
    same = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"a2-{inc_ctx['suffix']}"
    )
    assert same.id == a2.id
    with pytest.raises(IncidentIdempotencyConflict):
        await open_incident(
            ctx,
            p1,
            actor="inc-test",
            payload=_payload(summary="changed"),
            idempotency_key=f"a2-{inc_ctx['suffix']}",
        )
    investigating = await transition_incident(
        ctx, p1, a2.id, actor="inc-test", to_status="investigating"
    )
    assert investigating.status == "investigating"
    with pytest.raises(IncidentError):
        await transition_incident(ctx, p1, a2.id, actor="inc-test", to_status="resolved")
    diagnosed = await record_log_diagnosis_unavailable(ctx, p1, a2.id, actor="inc-test")
    assert not hasattr(diagnosed, "diagnosed")
    assert diagnosed.latest_evaluation_id == a2.latest_evaluation_id
    await _set_policy(ctx, p1, 5)
    a5 = await open_incident(
        ctx,
        p1,
        actor="inc-test",
        payload=_payload(summary="a5 path"),
        idempotency_key=f"a5-{inc_ctx['suffix']}",
    )
    prod = _by_seq(a5.actions)[6]
    assert prod.policy_decision == "needs_approval"
    assert prod.execution_posture == "recorded_not_executed"
    async with admin_engine.connect() as conn:
        event_types = {
            row[0]
            for row in (
                await conn.execute(
                    text("SELECT event_type FROM ops_incident_events WHERE incident_id=:i"),
                    {"i": a2.id},
                )
            ).all()
        }
    assert "log_diagnosis_unavailable" in event_types
    assert "diagnosed" not in event_types


@pytest.mark.db
async def test_deny_then_allow_creates_ticket_repeated_allow_reuses(inc_ctx):
    ctx = TenantContext(inc_ctx["t1"])
    p1 = inc_ctx["p1"]
    opened = await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"flip-{inc_ctx['suffix']}"
    )
    assert opened.ticket_id is None
    await _set_policy(ctx, p1, 1)
    allowed = await evaluate_post_launch_actions(ctx, p1, opened.id)
    assert _by_seq(allowed.actions)[1].ticket_id is not None
    latest = await latest_incident(ctx, p1)
    assert latest is not None and latest.ticket_id == _by_seq(allowed.actions)[1].ticket_id
    again = await evaluate_post_launch_actions(ctx, p1, opened.id)
    assert _by_seq(again.actions)[1].ticket_id == latest.ticket_id
    await _set_policy(ctx, p1, 0)
    denied = await evaluate_post_launch_actions(ctx, p1, opened.id)
    assert _by_seq(denied.actions)[1].ticket_id is None
    still = await latest_incident(ctx, p1)
    assert still is not None and still.ticket_id == latest.ticket_id


@pytest.mark.db
async def test_invalid_binds_abort_and_valid_mapping_is_local(inc_ctx, admin_engine):
    ctx = TenantContext(inc_ctx["t1"])
    p1, p1b = inc_ctx["p1"], inc_ctx["p1b"]
    await _set_policy(ctx, p1, 1)
    with pytest.raises(IncidentError):
        await open_incident(
            ctx,
            p1,
            actor="inc-test",
            payload=_payload(pm_issue_mapping_id=uuid.uuid4()),
            idempotency_key=f"badmap-{inc_ctx['suffix']}",
        )
    with pytest.raises(IncidentError):
        await open_incident(
            ctx,
            p1,
            actor="inc-test",
            payload=_payload(source_signal_id=uuid.uuid4()),
            idempotency_key=f"badsig-{inc_ctx['suffix']}",
        )
    async with admin_engine.begin() as conn:
        mapping_id = (
            await conn.execute(
                text(
                    "INSERT INTO pm_issue_mappings ("
                    "tenant_id, project_id, external_system, instance_key, external_ref, "
                    "external_status, board_column, title_present, provenance) VALUES ("
                    ":t,:p,'jira','acme-jira','PROJ-9','Open','backlog',true,"
                    "'caller_supplied_unverified') RETURNING id"
                ),
                {"t": inc_ctx["t1"], "p": p1b},
            )
        ).scalar_one()
        good_mapping = (
            await conn.execute(
                text(
                    "INSERT INTO pm_issue_mappings ("
                    "tenant_id, project_id, external_system, instance_key, external_ref, "
                    "external_status, board_column, title_present, provenance) VALUES ("
                    ":t,:p,'jira','acme-jira','PROJ-1','Open','backlog',true,"
                    "'caller_supplied_unverified') RETURNING id"
                ),
                {"t": inc_ctx["t1"], "p": p1},
            )
        ).scalar_one()
    with pytest.raises(IncidentError):
        await open_incident(
            ctx,
            p1,
            actor="inc-test",
            payload=_payload(pm_issue_mapping_id=mapping_id),
            idempotency_key=f"wrongproj-{inc_ctx['suffix']}",
        )
    ok = await open_incident(
        ctx,
        p1,
        actor="inc-test",
        payload=_payload(pm_issue_mapping_id=good_mapping),
        idempotency_key=f"goodmap-{inc_ctx['suffix']}",
    )
    assert ok.ticket_id is not None
    async with admin_engine.connect() as conn:
        stored = (
            await conn.execute(
                text("SELECT pm_issue_mapping_id FROM ops_incident_tickets WHERE id=:i"),
                {"i": ok.ticket_id},
            )
        ).scalar_one()
        incidents = (
            await conn.execute(
                text("SELECT count(*) FROM ops_incidents WHERE project_id=:p"), {"p": p1}
            )
        ).scalar_one()
        tool_calls = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM tool_calls WHERE tenant_id=:t "
                    "AND tool_name='pm.create_issue'"
                ),
                {"t": inc_ctx["t1"]},
            )
        ).scalar_one()
    assert stored == good_mapping
    assert incidents == 1
    assert tool_calls == 0


@pytest.mark.db
async def test_handover_reads_collect_and_a5_unchanged(inc_ctx, admin_engine):
    ctx = TenantContext(inc_ctx["t1"])
    p1 = inc_ctx["p1"]
    before = evaluate_production_autonomy(p1, readiness_level="R2")
    await open_incident(
        ctx, p1, actor="inc-test", payload=_payload(), idempotency_key=f"obs-{inc_ctx['suffix']}"
    )
    signals = await collect_ops_signals(
        ctx, p1, actor="inc-test", idempotency_key=f"sig-{inc_ctx['suffix']}"
    )
    assert (signals.observed_count, signals.caller_supplied_count, signals.not_observed_count) == (
        2,
        0,
        9,
    )
    assert {row.signal_class: row.observation_status for row in signals.signals}[
        "incident_reports"
    ] == "not_observed"
    async with admin_engine.connect() as conn:
        signal_id = (
            await conn.execute(
                text("SELECT id FROM ops_signal_results WHERE project_id=:p LIMIT 1"),
                {"p": p1},
            )
        ).scalar_one()
    bound = await open_incident(
        ctx,
        p1,
        actor="inc-test",
        payload=_payload(summary="bound-signal", source_signal_id=signal_id),
        idempotency_key=f"bindsig-{inc_ctx['suffix']}",
    )
    assert bound.source_signal_id == signal_id
    after = evaluate_production_autonomy(p1, readiness_level="R2")
    assert before.to_dict() == after.to_dict()
    assert after.to_dict()["can_go_live_autonomously"] is False
    complete = await record_support_handover(
        ctx,
        p1,
        actor="inc-test",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_complete"
        ),
    )
    assert complete.recorded_by_provenance == "caller_supplied_unverified"
    auth_ctx = TenantContext(
        inc_ctx["t1"], actor=AuthenticatedActor(subject="alice", actor_type="human")
    )
    with pytest.raises(IncidentError):
        await record_support_handover(
            auth_ctx,
            p1,
            actor="alice",
            payload=HandoverPayload(
                handed_over_by="bob", received_by="ops-queue", status="recorded_complete"
            ),
        )
    matched = await record_support_handover(
        auth_ctx,
        p1,
        actor="alice",
        payload=HandoverPayload(
            handed_over_by="alice", received_by="ops-queue", status="recorded_incomplete"
        ),
    )
    assert matched.recorded_by_provenance == "request_authenticated"
    handover = await latest_handover(ctx, p1)
    assert handover is not None
    assert handover.id == matched.id
    assert await latest_incident(ctx, p1) is not None
    assert len(await list_open(ctx, p1)) >= 1
    assert len(await history(ctx, p1)) >= 2
    other = TenantContext(inc_ctx["t2"])
    assert await latest_incident(other, p1) is None
    async with admin_engine.connect() as conn:
        payload = json.dumps(
            (
                await conn.execute(
                    text(
                        "SELECT actor, action, target, payload FROM audit_logs "
                        "WHERE tenant_id=:t AND action LIKE 'ops_incidents.%'"
                    ),
                    {"t": inc_ctx["t1"]},
                )
            )
            .mappings()
            .all(),
            default=str,
        )
        guard = (
            await conn.execute(
                text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
            )
        ).scalar_one()
    assert "api 5xx" not in payload
    assert "disk" not in payload
    assert guard == FINDINGS_GUARD_MD5
