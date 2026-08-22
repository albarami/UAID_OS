"""Slice 57 action-result CHECK, count-match, and composite-FK proofs."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.ops_incidents_support import (
    INC_DIGEST,
    denied_children,
    insert_child,
    insert_evaluation,
    insert_incident,
    insert_seven_denied,
    insert_ticket,
)


async def _probe_children(db_session, t1, p1, key, rows):
    incident_id = await insert_incident(db_session, t1, p1, key)
    evaluation_id = await insert_evaluation(db_session, t1, p1, incident_id)
    for row in rows:
        await insert_child(db_session, t1, p1, incident_id, evaluation_id, row)
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.db
async def test_frozen_pairs_posture_count_and_cross_ticket_fk(inc_ctx, db_session):
    t1, p1 = inc_ctx["t1"], inc_ctx["p1"]
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_incident(
                db_session, t1, p1, f"bad-status-{inc_ctx['suffix']}", status="investigating"
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            incident_id = await insert_incident(db_session, t1, p1, f"zero-{inc_ctx['suffix']}")
            await insert_evaluation(db_session, t1, p1, incident_id)
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    allow_no_ticket = list(denied_children())
    allow_no_ticket[0] = (
        1,
        "create_bug_ticket",
        "create_project_tasks",
        "allow",
        "local_ticket_written",
        "ticket_written",
        None,
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await _probe_children(db_session, t1, p1, f"allow-{inc_ctx['suffix']}", allow_no_ticket)
    seq2_allow = list(denied_children())
    seq2_allow[1] = (
        2,
        "diagnose_log_error",
        "none",
        "allow",
        "recorded_not_executed",
        "no_log_source",
        None,
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await _probe_children(db_session, t1, p1, f"seq2-{inc_ctx['suffix']}", seq2_allow)
    prod_written = list(denied_children())
    prod_written[5] = (
        6,
        "deploy_production_hotfix",
        "deploy_production",
        "deny",
        "local_ticket_written",
        "production_not_executed",
        None,
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await _probe_children(db_session, t1, p1, f"prod-{inc_ctx['suffix']}", prod_written)
    wrong_pair = list(denied_children())
    wrong_pair[0] = (
        1,
        "diagnose_log_error",
        "none",
        "not_evaluated",
        "recorded_not_executed",
        "no_log_source",
        None,
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await _probe_children(db_session, t1, p1, f"pair-{inc_ctx['suffix']}", wrong_pair)
    await insert_seven_denied(
        db_session, t1, p1, await insert_incident(db_session, t1, p1, f"ok-{inc_ctx['suffix']}")
    )
    first = await insert_incident(db_session, t1, p1, f"t1-{inc_ctx['suffix']}")
    second = await insert_incident(db_session, t1, p1, f"t2-{inc_ctx['suffix']}")
    await insert_ticket(db_session, t1, p1, first)
    other_ticket = await insert_ticket(db_session, t1, p1, second)
    stolen = list(denied_children())
    stolen[0] = (
        1,
        "create_bug_ticket",
        "create_project_tasks",
        "allow",
        "local_ticket_written",
        "ticket_written",
        other_ticket,
    )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await _probe_children(db_session, t1, p1, f"steal-{inc_ctx['suffix']}", stolen)
    own = await insert_incident(db_session, t1, p1, f"own-{inc_ctx['suffix']}")
    own_ticket = await insert_ticket(db_session, t1, p1, own)
    own_eval = await insert_evaluation(db_session, t1, p1, own)
    allowed = list(denied_children())
    allowed[0] = (
        1,
        "create_bug_ticket",
        "create_project_tasks",
        "allow",
        "local_ticket_written",
        "ticket_written",
        own_ticket,
    )
    for row in allowed:
        await insert_child(db_session, t1, p1, own, own_eval, row)


@pytest.mark.db
async def test_signal_and_mapping_composite_fk_reject_wrong_project(inc_ctx, db_session):
    t1, p1, p1b = inc_ctx["t1"], inc_ctx["p1"], inc_ctx["p1b"]
    mapping = (
        await db_session.execute(
            text(
                "INSERT INTO pm_issue_mappings ("
                "tenant_id, project_id, external_system, instance_key, external_ref, "
                "external_status, board_column, title_present, provenance) VALUES ("
                ":t,:p,'jira','acme-jira','PROJ-x','Open','backlog',true,"
                "'caller_supplied_unverified') RETURNING id"
            ),
            {"t": t1, "p": p1b},
        )
    ).scalar_one()
    incident_id = await insert_incident(db_session, t1, p1, f"mapfk-{inc_ctx['suffix']}")
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await insert_ticket(db_session, t1, p1, incident_id, mapping_id=mapping)
    fake_signal = uuid.uuid4()
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ops_incidents ("
                    "tenant_id, project_id, ruleset_version, category, severity, status, "
                    "summary, source_provenance, source_signal_id, idempotency_key, "
                    "request_digest) VALUES ("
                    ":t,:p,'slice57.v1','error','low','open','x',"
                    "'caller_supplied_unverified',:s,:k,:d)"
                ),
                {
                    "t": t1,
                    "p": p1,
                    "s": fake_signal,
                    "k": f"sigfk-{inc_ctx['suffix']}",
                    "d": INC_DIGEST,
                },
            )
