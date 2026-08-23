"""Shared Slice-59 test helpers. Not a collected test module."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import text

from app.release.emergency_control_service import EmergencyControlResult
from app.release.monitoring_evidence import observation_valid
from app.tenancy import TenantContext, tenant_scope

FINDINGS_GUARD_MD5 = "808036faf2660d6810aeca4342e6f1ac"
DB_CHECKS_SHA = "468837a3afe452239fa392a16cdf1ab90c10938fecb0854478f32606eabb49fc"
INCIDENTS_SHA = "0b5e996c410169b41d3aacd12659d680e3147354cfd23e2dad568a4221eb76c7"
HOTFIX_SHA = "ac6a26cee28ae37b872bcac0e8daef2709d9a69be35d4c31822328309aeb8599"
INCIDENT_CHECKS_SHA = "c529a280f8758eefa6d5e82d616ff39580327caf2bdd307c7461b6c7295692b8"
HOTFIX_CHECKS_SHA = "f7b282f5eef92234777ec0055c3e4efa5d9d3cc40e2d7852d29f3e0f7da8def4"

STABLE_HASHES = {
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26",
    "app/runtime/control_loop.py": (
        "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180"
    ),
    "app/ops/db_checks.py": DB_CHECKS_SHA,
    "app/ops/incidents.py": INCIDENTS_SHA,
    "app/ops/hotfix.py": HOTFIX_SHA,
    "app/ops/incident_db_checks.py": INCIDENT_CHECKS_SHA,
    "app/ops/hotfix_db_checks.py": HOTFIX_CHECKS_SHA,
}

STABILIZATION_TABLES = (
    "ops_stabilization_windows",
    "ops_stabilization_criterion_results",
    "ops_improvement_results",
    "ops_stabilization_closure_attempts",
)

MONITORING_URL = "https://mon.example.com/status"
DIGEST = "sha256:" + "ab" * 32

VALID_POLICY: dict[str, object] = {
    "duration_days": 14,
    "owner": "sre-owner",
    "support_owner": "support-owner",
    "monitored_journeys": ["checkout"],
    "error_budget_threshold": "2.5%",
    "exit_criteria": {
        "zero_open_critical_incidents_for_days": 7,
        "error_budget_under_threshold": True,
        "monitoring_confirmed_active": True,
        "rollback_blockers_open": 0,
        "support_handover_complete": True,
    },
    "closure_approver": "sre-lead",
}


def unique_key(prefix: str) -> str:
    """Return a unique idempotency key."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def window_data(
    *,
    status_url: str | None = MONITORING_URL,
    provider: str | None = "generic_monitoring_api",
    policy: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build ``operations_observability_support.data`` for a declaration."""
    monitoring: dict[str, object] = {}
    if provider is not None:
        monitoring["provider"] = provider
    if status_url is not None:
        monitoring["status_url"] = status_url
    return {
        "monitoring": monitoring,
        "stabilization_window": policy if policy is not None else dict(VALID_POLICY),
    }


async def declare_window(ctx, project_id, *, data: dict[str, object] | None = None):
    """Declare file 22 with a valid §27.13 window snapshot."""
    from app.repositories.intake_categories import IntakeCategoryRepository

    async with tenant_scope(ctx) as session:
        return await IntakeCategoryRepository(session, ctx).declare(
            project_id=project_id,
            category="operations_observability_support",
            actor="stab-test",
            data=data if data is not None else window_data(),
            origin="test",
        )


def passing_rollback_coverage(**overrides) -> SimpleNamespace:
    """Coverage object that satisfies ``gate10_conjunction_passed``."""
    from app.ops.hotfix import GATE10_CONTEXT_KEYS

    flags: dict[str, object] = {key: True for key in GATE10_CONTEXT_KEYS}
    flags["attempt_failed"] = False
    flags["phase_count"] = 5
    flags["execution_observation"] = "connector_observed_ci"
    flags.update(overrides)
    return SimpleNamespace(**flags)


def fresh_snapshot(**overrides) -> SimpleNamespace:
    """Connector-verified, valid, active, fresh monitoring snapshot."""
    payload = {
        "id": uuid.uuid4(),
        "provenance": "connector_verified",
        "response_valid": True,
        "overall_active": True,
        "observed_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


CRITERIA_ROWS = (
    (1, "zero_open_critical_incidents_for_days", "not_evaluable", "no_production_coverage_clock"),
    (2, "error_budget_under_threshold", "not_evaluable", "error_budget_threshold_unparsed_string"),
    (3, "monitoring_confirmed_active", "not_observed", "no_monitoring_declaration"),
    (4, "rollback_blockers_open", "not_observed", "no_rollback_run"),
    (5, "support_handover_complete", "not_observed", "no_handover_record"),
    (6, "backup_restore_validated", "not_observed", "no_backup_restore_source"),
    (7, "p95_latency_within_slo", "not_observed", "no_latency_slo_source"),
    (8, "no_unresolved_security_alerts", "not_observed", "no_post_launch_security_alert_source"),
)
IMPROVEMENT_ROWS = (
    (1, "lessons_learned", "not_observed", "no_lessons_store", None),
    (2, "recurring_failure_patterns", "observed", "incident_category_recurrence", 0),
    (3, "agent_evals", "not_observed", "no_live_eval_update", None),
    (4, "prompt_templates", "not_observed", "no_prompt_store", None),
    (5, "domain_pack_gaps", "not_observed", "no_domain_pack_declaration", None),
    (6, "test_oracle_gaps", "not_observed", "no_findings_report", None),
    (7, "cost_forecasts", "not_observed", "no_cost_forecast_run", None),
    (8, "connector_reliability_scores", "not_observed", "no_connector_score_store", None),
)


def by_seq(rows):
    """Index children by seq."""
    return {row.seq: row for row in rows}


async def insert_sql_window(
    session,
    tenant_id,
    project_id,
    category_id,
    *,
    target_ref=None,
    passed=0,
    failed=0,
    missing=6,
    unevaluable=2,
    extension_required=True,
    as_of_sql="transaction_timestamp()",
    policy_digest_sql="public.stabilization_policy_digest(CAST(:policy AS jsonb))",
    age_mon=24,
    age_dep=24,
    extends_window_id=None,
    key=None,
    assessor_subject="seed",
    assessor_provenance="caller_supplied_unverified",
    assessor_actor_type=None,
):
    """Insert a window row via SQL. Caller supplies ``as_of`` SQL for forgery tests."""
    return (
        await session.execute(
            text(
                "INSERT INTO ops_stabilization_windows ("
                "tenant_id, project_id, ruleset_version, status, as_of, clock_basis, "
                "category_id, policy_snapshot, policy_digest, monitoring_target_ref, "
                "monitoring_max_age_hours, deployment_max_age_hours, assessor_subject, "
                "assessor_actor_type, assessor_provenance, follow_up_posture, "
                "extension_required, extends_window_id, criterion_count, improvement_count, "
                "passed_count, failed_count, not_observed_count, not_evaluable_count, "
                "request_digest, input_digest, idempotency_key) VALUES ("
                ":t,:p,'slice59.v1','open', "
                f"{as_of_sql}, "
                "'transaction_timestamp_not_production_uptime', :c, CAST(:policy AS jsonb), "
                f"{policy_digest_sql}, "
                ":ref, :mon, :dep, :subj, :atype, :prov, 'required_not_executed', "
                ":ext, :prior, 8, 8, :passed, :failed, :missing, :uneval, "
                ":d, :d, :k) RETURNING id"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "c": category_id,
                "policy": json.dumps(VALID_POLICY),
                "ref": target_ref,
                "mon": age_mon,
                "dep": age_dep,
                "subj": assessor_subject,
                "atype": assessor_actor_type,
                "prov": assessor_provenance,
                "ext": extension_required,
                "prior": extends_window_id,
                "passed": passed,
                "failed": failed,
                "missing": missing,
                "uneval": unevaluable,
                "d": DIGEST,
                "k": key or unique_key("sql"),
            },
        )
    ).scalar_one()


async def insert_default_children(
    session, tenant_id, project_id, window_id, *, seq3=None, seq5=None
):
    """Insert the honest locked 8+8 children, optionally overriding seq 3 or 5."""
    for seq, key, status, reason in CRITERIA_ROWS:
        snap = None
        handover_id = None
        if seq == 3 and seq3 is not None:
            status, reason = seq3[0], seq3[1]
            snap = seq3[2] if len(seq3) > 2 else None
        if seq == 5 and seq5 is not None:
            status, reason = seq5[0], seq5[1]
            handover_id = seq5[2] if len(seq5) > 2 else None
        await session.execute(
            text(
                "INSERT INTO ops_stabilization_criterion_results ("
                "tenant_id, project_id, window_id, seq, criterion_key, status, reason, "
                "monitoring_snapshot_id, rollback_verification_run_id, handover_id) VALUES ("
                ":t,:p,:w,:seq,:key,:st,:reason,:snap,:run,:ho)"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "w": window_id,
                "seq": seq,
                "key": key,
                "st": status,
                "reason": reason,
                "snap": snap,
                "run": None,
                "ho": handover_id,
            },
        )
    for seq, klass, status, reason, metric in IMPROVEMENT_ROWS:
        await session.execute(
            text(
                "INSERT INTO ops_improvement_results ("
                "tenant_id, project_id, window_id, seq, improvement_class, status, "
                "reason, metric_int) VALUES (:t,:p,:w,:seq,:klass,:st,:reason,:metric)"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "w": window_id,
                "seq": seq,
                "klass": klass,
                "st": status,
                "reason": reason,
                "metric": metric,
            },
        )


async def insert_raw_snapshot(
    session, tenant_id, project_id, target_ref, *, provenance="connector_verified"
):
    """Insert a monitoring snapshot by SQL, bypassing the URL validator."""
    obs = observation_valid(3, 2)
    return (
        await session.execute(
            text(
                "INSERT INTO monitoring_status_snapshots ("
                "tenant_id, project_id, provider, target_ref, provider_reachable, "
                "response_valid, observed_http_status, failure_kind, active_monitor_count, "
                "active_alert_rule_count, monitoring_active, alerts_active, overall_active, "
                "provenance, observed_at) VALUES ("
                ":t,:p,'generic_monitoring_api',:ref,:reachable,:valid,200,NULL,:mc,:ac,"
                "true,true,true,:prov,:obs) RETURNING id"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "ref": target_ref,
                "reachable": obs["provider_reachable"],
                "valid": obs["response_valid"],
                "mc": obs["active_monitor_count"],
                "ac": obs["active_alert_rule_count"],
                "prov": provenance,
                "obs": datetime.now(timezone.utc),
            },
        )
    ).scalar_one()


async def create_project(ctx: TenantContext, *, name: str, slug: str) -> uuid.UUID:
    """Create a committed same-tenant project for isolated Slice-59 DB proofs."""
    from app.repositories.projects import ProjectRepository

    async with tenant_scope(ctx) as session:
        project = await ProjectRepository(session, ctx).create(name=name, slug=slug)
        await session.flush()
        return project.id


async def seed_emergency_authority(ctx: TenantContext, project_id: uuid.UUID) -> None:
    """Declare the Slice-54 recorded policy + checklist and a valid autonomy row.

    Bind/activate need this graph. ``emergency_controls.py`` stays unmodified.
    """
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.intake_categories import IntakeCategoryRepository
    from tests.test_emergency_controls import _checklist, _policy

    async with tenant_scope(ctx) as session:
        cats = IntakeCategoryRepository(session, ctx)
        await cats.declare(
            project_id=project_id,
            category="human_approval_policy",
            actor="stab-test",
            data=_policy(),
            origin="test",
        )
        await cats.declare(
            project_id=project_id,
            category="go_live_checklist",
            actor="stab-test",
            data=_checklist(),
            origin="test",
        )
        await AutonomyPolicyRepository(session, ctx).upsert(
            project_id=project_id,
            autonomy_level=5,
            overrides={},
            actor="stab-test",
        )


async def bind_and_activate_emergency_stop(
    ctx: TenantContext, project_id: uuid.UUID, *, bind_key: str, activate_key: str
) -> tuple[EmergencyControlResult, EmergencyControlResult]:
    """Drive the real ``EmergencyControlService`` bind + activate path."""
    from app.release.emergency_control_service import EmergencyControlService

    async with tenant_scope(ctx) as session:
        service = EmergencyControlService(session, ctx)
        bound = await service.bind(project_id=project_id, idempotency_key=bind_key)
        activated = await service.activate(project_id=project_id, idempotency_key=activate_key)
        return bound, activated
