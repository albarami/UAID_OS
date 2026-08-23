"""Slice 59 Alembic 0058 reversibility proofs (empty roundtrip + populated refusal)."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from tests.conftest import TEST_ADMIN_URL
from tests.ops_stabilization_support import DIGEST, VALID_POLICY


@contextmanager
def _alembic_url(url: str) -> Iterator[Config]:
    prior = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield Config("alembic.ini")
    finally:
        if prior is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = prior


async def _admin_connect(database: str = "postgres"):
    import asyncpg

    url = make_url(TEST_ADMIN_URL)
    return await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=database,
    )


async def _create_database(name: str) -> None:
    conn = await _admin_connect()
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(name: str) -> None:
    conn = await _admin_connect()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


async def _regclass(database: str, table: str) -> str | None:
    conn = await _admin_connect(database)
    try:
        return await conn.fetchval("SELECT to_regclass($1)::text", f"public.{table}")
    finally:
        await conn.close()


async def _constraint_exists(database: str, name: str) -> bool:
    conn = await _admin_connect(database)
    try:
        found = await conn.fetchval("SELECT 1 FROM pg_constraint WHERE conname=$1", name)
        return found is not None
    finally:
        await conn.close()


_CRITERIA = (
    (1, "zero_open_critical_incidents_for_days", "not_evaluable", "no_production_coverage_clock"),
    (2, "error_budget_under_threshold", "not_evaluable", "error_budget_threshold_unparsed_string"),
    (3, "monitoring_confirmed_active", "not_observed", "no_monitoring_declaration"),
    (4, "rollback_blockers_open", "not_observed", "no_rollback_run"),
    (5, "support_handover_complete", "not_observed", "no_handover_record"),
    (6, "backup_restore_validated", "not_observed", "no_backup_restore_source"),
    (7, "p95_latency_within_slo", "not_observed", "no_latency_slo_source"),
    (8, "no_unresolved_security_alerts", "not_observed", "no_post_launch_security_alert_source"),
)
_IMPROVEMENTS = (
    (1, "lessons_learned", "not_observed", "no_lessons_store", None),
    (2, "recurring_failure_patterns", "observed", "incident_category_recurrence", 0),
    (3, "agent_evals", "not_observed", "no_live_eval_update", None),
    (4, "prompt_templates", "not_observed", "no_prompt_store", None),
    (5, "domain_pack_gaps", "not_observed", "no_domain_pack_declaration", None),
    (6, "test_oracle_gaps", "not_observed", "no_findings_report", None),
    (7, "cost_forecasts", "not_observed", "no_cost_forecast_run", None),
    (8, "connector_reliability_scores", "not_observed", "no_connector_score_store", None),
)


async def _seed_window(database: str) -> None:
    conn = await _admin_connect(database)
    try:
        async with conn.transaction():
            org = await conn.fetchval(
                "INSERT INTO organizations (name, slug) VALUES ('StabMig', $1) RETURNING id",
                f"st-mig-{uuid.uuid4().hex[:8]}",
            )
            tenant = await conn.fetchval(
                "INSERT INTO tenants (organization_id, name, slug) "
                "VALUES ($1,'t1',$2) RETURNING id",
                org,
                f"st-mig-t-{uuid.uuid4().hex[:8]}",
            )
            project = await conn.fetchval(
                "INSERT INTO projects (tenant_id, name, slug) VALUES ($1,'P',$2) RETURNING id",
                tenant,
                f"st-mig-p-{uuid.uuid4().hex[:8]}",
            )
            category = await conn.fetchval(
                "INSERT INTO intake_categories ("
                "tenant_id, project_id, category, status, data, origin) VALUES ("
                "$1,$2,'operations_observability_support','declared','{}'::jsonb,'migrate') "
                "RETURNING id",
                tenant,
                project,
            )
            policy = json.dumps(VALID_POLICY)
            window_id = await conn.fetchval(
                "INSERT INTO ops_stabilization_windows ("
                "tenant_id, project_id, ruleset_version, status, as_of, clock_basis, "
                "category_id, policy_snapshot, policy_digest, "
                "monitoring_max_age_hours, deployment_max_age_hours, "
                "assessor_subject, assessor_provenance, follow_up_posture, extension_required, "
                "criterion_count, improvement_count, passed_count, failed_count, "
                "not_observed_count, not_evaluable_count, request_digest, input_digest, "
                "idempotency_key) VALUES ("
                "$1,$2,'slice59.v1','open', transaction_timestamp(), "
                "'transaction_timestamp_not_production_uptime', $3, $4::jsonb, "
                "public.stabilization_policy_digest($4::jsonb), 24, 24, 'seed', "
                "'caller_supplied_unverified', 'required_not_executed', true, "
                "8, 8, 0, 0, 6, 2, $5, $5, 'migrate-seed') RETURNING id",
                tenant,
                project,
                category,
                policy,
                DIGEST,
            )
            for seq, key, status, reason in _CRITERIA:
                await conn.execute(
                    "INSERT INTO ops_stabilization_criterion_results ("
                    "tenant_id, project_id, window_id, seq, criterion_key, status, reason) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                    tenant,
                    project,
                    window_id,
                    seq,
                    key,
                    status,
                    reason,
                )
            for seq, klass, status, reason, metric in _IMPROVEMENTS:
                await conn.execute(
                    "INSERT INTO ops_improvement_results ("
                    "tenant_id, project_id, window_id, seq, improvement_class, status, "
                    "reason, metric_int) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                    tenant,
                    project,
                    window_id,
                    seq,
                    klass,
                    status,
                    reason,
                    metric,
                )
    finally:
        await conn.close()


def _fresh_db() -> tuple[str, str]:
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_st59_{uuid.uuid4().hex[:8]}"
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    return dbname, alembic_url


@pytest.mark.db
def test_alembic_0058_empty_roundtrip_and_populated_refusal(_schema) -> None:
    dbname, alembic_url = _fresh_db()
    asyncio.run(_create_database(dbname))
    try:
        with _alembic_url(alembic_url) as cfg:
            command.upgrade(cfg, "0058")
            assert asyncio.run(_regclass(dbname, "ops_stabilization_windows")) == (
                "ops_stabilization_windows"
            )
            assert asyncio.run(_constraint_exists(dbname, "uq_mss_id_project_tenant"))
            assert asyncio.run(_constraint_exists(dbname, "uq_osh_id_project_tenant"))
            assert asyncio.run(_constraint_exists(dbname, "uq_ifr_id_project_tenant"))
            command.downgrade(cfg, "0057")
            assert asyncio.run(_regclass(dbname, "ops_stabilization_windows")) is None
            assert not asyncio.run(_constraint_exists(dbname, "uq_mss_id_project_tenant"))
            command.upgrade(cfg, "0058")
            asyncio.run(_seed_window(dbname))
            with pytest.raises(DBAPIError, match="cannot downgrade Slice 59"):
                command.downgrade(cfg, "0057")
    finally:
        asyncio.run(_drop_database(dbname))
