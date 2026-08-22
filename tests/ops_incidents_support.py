"""Shared Slice-57 DB test helpers. Not a collected test module."""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text

INC_DIGEST = "sha256:" + "ab" * 32
INCIDENT_TABLES = (
    "ops_incidents",
    "ops_incident_events",
    "ops_incident_tickets",
    "ops_support_handovers",
    "ops_incident_action_evaluations",
    "ops_incident_action_results",
)
FINDINGS_GUARD_MD5 = "808036faf2660d6810aeca4342e6f1ac"
DB_CHECKS_SHA = "468837a3afe452239fa392a16cdf1ab90c10938fecb0854478f32606eabb49fc"


async def scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def inc_ctx(admin_engine):
    suffix = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as conn:
        org = await scalar(
            conn,
            "INSERT INTO organizations (name, slug) VALUES ('IncOrg',:s) RETURNING id",
            s=f"inc-org-{suffix}",
        )
        t1 = await scalar(
            conn,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t1',:s) RETURNING id",
            o=org,
            s=f"inc-t1-{suffix}",
        )
        t2 = await scalar(
            conn,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t2',:s) RETURNING id",
            o=org,
            s=f"inc-t2-{suffix}",
        )
        p1 = await scalar(
            conn,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P1',:s) RETURNING id",
            t=t1,
            s=f"inc-p1-{suffix}",
        )
        p2 = await scalar(
            conn,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"inc-px-{suffix}",
        )
        p1b = await scalar(
            conn,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P1B',:s) RETURNING id",
            t=t1,
            s=f"inc-p1b-{suffix}",
        )
    return {"t1": t1, "t2": t2, "p1": p1, "p2": p2, "p1b": p1b, "suffix": suffix}


async def insert_incident(session, tenant_id, project_id, key, *, status="open"):
    return (
        await session.execute(
            text(
                "INSERT INTO ops_incidents ("
                "tenant_id, project_id, ruleset_version, category, severity, status, "
                "summary, source_provenance, idempotency_key, request_digest) VALUES ("
                ":t,:p,'slice57.v1','error','low',:st,'disk full',"
                "'caller_supplied_unverified',:k,:d) RETURNING id"
            ),
            {"t": tenant_id, "p": project_id, "st": status, "k": key, "d": INC_DIGEST},
        )
    ).scalar_one()


async def insert_ticket(session, tenant_id, project_id, incident_id, *, mapping_id=None):
    return (
        await session.execute(
            text(
                "INSERT INTO ops_incident_tickets ("
                "tenant_id, project_id, incident_id, ticket_kind, delivery, status, "
                "pm_issue_mapping_id) VALUES ("
                ":t,:p,:i,'bug','local_record','open',:m) RETURNING id"
            ),
            {"t": tenant_id, "p": project_id, "i": incident_id, "m": mapping_id},
        )
    ).scalar_one()


async def insert_evaluation(session, tenant_id, project_id, incident_id):
    return (
        await session.execute(
            text(
                "INSERT INTO ops_incident_action_evaluations ("
                "tenant_id, project_id, incident_id, ruleset_version, action_count, "
                "policy_present, policy_id, autonomy_level_snapshot, policy_input_digest) "
                "VALUES (:t,:p,:i,'slice57.v1',7, false, NULL, NULL, :d) RETURNING id"
            ),
            {"t": tenant_id, "p": project_id, "i": incident_id, "d": INC_DIGEST},
        )
    ).scalar_one()


def denied_children():
    return (
        (
            1,
            "create_bug_ticket",
            "create_project_tasks",
            "deny",
            "recorded_not_executed",
            "ticket_denied_by_policy",
            None,
        ),
        (
            2,
            "diagnose_log_error",
            "none",
            "not_evaluated",
            "recorded_not_executed",
            "no_log_source",
            None,
        ),
        (
            3,
            "create_patch_branch",
            "create_branches",
            "deny",
            "recorded_not_executed",
            "deferred_slice58",
            None,
        ),
        (
            4,
            "open_hotfix_pr",
            "open_pull_requests",
            "deny",
            "recorded_not_executed",
            "deferred_slice58",
            None,
        ),
        (
            5,
            "deploy_staging_hotfix",
            "deploy_staging",
            "deny",
            "recorded_not_executed",
            "deferred_slice58",
            None,
        ),
        (
            6,
            "deploy_production_hotfix",
            "deploy_production",
            "deny",
            "recorded_not_executed",
            "production_not_executed",
            None,
        ),
        (
            7,
            "rollback_production",
            "deploy_production",
            "deny",
            "recorded_not_executed",
            "production_not_executed",
            None,
        ),
    )


async def insert_child(session, tenant_id, project_id, incident_id, evaluation_id, row):
    seq, action, matrix, decision, posture, reason, ticket_id = row
    await session.execute(
        text(
            "INSERT INTO ops_incident_action_results ("
            "tenant_id, project_id, incident_id, evaluation_id, seq, action, "
            "matrix_action, policy_decision, execution_posture, reason_code, ticket_id) "
            "VALUES (:t,:p,:i,:e,:seq,:a,:m,:d,:po,:r,:tid)"
        ),
        {
            "t": tenant_id,
            "p": project_id,
            "i": incident_id,
            "e": evaluation_id,
            "seq": seq,
            "a": action,
            "m": matrix,
            "d": decision,
            "po": posture,
            "r": reason,
            "tid": ticket_id,
        },
    )


async def insert_seven_denied(session, tenant_id, project_id, incident_id):
    evaluation_id = await insert_evaluation(session, tenant_id, project_id, incident_id)
    for row in denied_children():
        await insert_child(session, tenant_id, project_id, incident_id, evaluation_id, row)
    return evaluation_id
