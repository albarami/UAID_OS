"""Shared Slice-56 DB test helpers. Not a collected test module."""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text

OPS_DIGEST = "sha256:" + "ab" * 32
OPS_MISSING = (
    (1, "uptime", "no_uptime_source"),
    (2, "error_rates", "no_error_rate_source"),
    (3, "latency", "no_latency_source"),
    (5, "security_alerts", "no_post_launch_security_alert_source"),
    (6, "user_journey_failures", "no_journey_failure_source"),
    (7, "data_quality_issues", "no_data_quality_source"),
    (9, "model_output_drift", "no_model_drift_source"),
    (10, "support_tickets", "no_support_ticket_source"),
    (11, "incident_reports", "no_incident_store"),
)


async def scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def ops_ctx(admin_engine):
    suffix = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as conn:
        org = await scalar(
            conn,
            "INSERT INTO organizations (name, slug) VALUES ('OpsOrg',:s) RETURNING id",
            s=f"ops-org-{suffix}",
        )
        t1 = await scalar(
            conn,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t1',:s) RETURNING id",
            o=org,
            s=f"ops-t1-{suffix}",
        )
        t2 = await scalar(
            conn,
            "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,'t2',:s) RETURNING id",
            o=org,
            s=f"ops-t2-{suffix}",
        )
        p1 = await scalar(
            conn,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P1',:s) RETURNING id",
            t=t1,
            s=f"ops-p1-{suffix}",
        )
        p2 = await scalar(
            conn,
            "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"ops-px-{suffix}",
        )
        run = await scalar(
            conn,
            "INSERT INTO project_runs (tenant_id, project_id, status) "
            "VALUES (:t,:p,'failed') RETURNING id",
            t=t1,
            p=p1,
        )
    return {"t1": t1, "t2": t2, "p1": p1, "p2": p2, "run": run, "suffix": suffix}


async def new_parent(session, tenant_id, project_id, key, *, observed=2, caller=0, missing=9):
    return (
        await session.execute(
            text(
                "INSERT INTO ops_observation_runs ("
                "tenant_id, project_id, ruleset_version, idempotency_key, request_digest, "
                "input_digest, as_of, signal_count, observed_count, caller_supplied_count, "
                "not_observed_count, breached_count) VALUES ("
                ":t,:p,'slice56.v1',:k,:d,:d, now(), 11, :o, :c, :m, 0) RETURNING id, as_of"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "k": key,
                "d": OPS_DIGEST,
                "o": observed,
                "c": caller,
                "m": missing,
            },
        )
    ).one()
