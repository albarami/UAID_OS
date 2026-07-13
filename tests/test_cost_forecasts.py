"""Slice 51 cost-forecast contracts and persistence.

The Docker-free half proves deterministic policy parsing, Decimal arithmetic, truth-tier
boundaries, the non-vacuous six-dimension decision, and the gate-#9 ladder. DB-backed tests
below prove tenant isolation and database ownership of the stored evidence.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.cost import COST_COMPONENTS
from app.cost_forecast import (
    COST_FORECAST_CONTRACT_VERSION,
    COST_FORECAST_INPUT_CONTRACT_VERSION,
    COST_POLICY_CONTRACT_VERSION,
    ComponentAssumption,
    CostForecastError,
    ForecastInput,
    LedgerCostLine,
    ModelForecastLine,
    derive_forecast,
    parse_structured_policy,
)
from app.llm.pricing import ModelPrice
from app.release.production_autonomy import NO_GO_LIVE_REASONS, evaluate_production_autonomy
from app.release.evidence_pack import (
    INVENTORY_SECTIONS,
    SectionInventory,
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
)


_AS_OF = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)


def _policy_payload(*, approval_percentage=90, model_total=100, model_daily=50):
    return {
        "cost_and_resource_policy": {
            "max_total_model_cost_usd": model_total,
            "max_daily_model_cost_usd": model_daily,
            "max_cloud_spend_usd": 100,
            "max_ci_minutes_per_day": 100,
            "require_approval_above_forecast_percentage": approval_percentage,
            "model_routing": {
                "cheap_first_for_low_risk": True,
                "frontier_for_high_risk": True,
                "use_cached_context_when_possible": True,
            },
            "stop_conditions": [
                "budget_exceeded",
                "repeated_failure_without_new_strategy",
                "tool_loop_detected",
                "model_provider_outage_extended",
            ],
        }
    }


def _forecast_input(*, approval_percentage=90, model_total=100, stop_reason="ok"):
    policy = parse_structured_policy(
        _policy_payload(approval_percentage=approval_percentage, model_total=model_total)
    )
    assumptions = tuple(
        ComponentAssumption(
            component=component,
            remaining_total_usd=Decimal("0") if component == "model_inference" else Decimal("1"),
            remaining_today_usd=Decimal("0") if component == "model_inference" else Decimal("1"),
        )
        for component in COST_COMPONENTS
    )
    ledger = tuple(
        LedgerCostLine(
            event_id=f"event-{index}",
            component=component,
            amount_usd=Decimal("1"),
            occurred_at=_AS_OF - timedelta(hours=1),
            material_digest=f"sha256:{index:064x}",
        )
        for index, component in enumerate(COST_COMPONENTS, start=1)
    )
    model_lines = (
        ModelForecastLine(
            model_route_hash="sha256:" + "a" * 64,
            remaining_input_tokens=1000,
            remaining_output_tokens=1000,
            remaining_today_input_tokens=1000,
            remaining_today_output_tokens=1000,
            price=ModelPrice(Decimal("2"), Decimal("3")),
        ),
    )
    return ForecastInput(
        policy=policy,
        budget_total_usd=Decimal("500"),
        budget_daily_usd=Decimal("200"),
        ledger_lines=ledger,
        assumptions=assumptions,
        model_lines=model_lines,
        forecast_ci_minutes_today=10,
        stop_reason=stop_reason,
        as_of=_AS_OF,
    )


def test_contract_versions_and_policy_truth_tier_are_exact():
    assert COST_POLICY_CONTRACT_VERSION == "slice51.cost_policy.v1"
    assert COST_FORECAST_INPUT_CONTRACT_VERSION == "slice51.cost_forecast_input.v1"
    assert COST_FORECAST_CONTRACT_VERSION == "slice51.cost_forecast.v1"
    policy = parse_structured_policy(_policy_payload())
    assert policy.source_provenance == "caller_supplied_unverified_structured_cost_policy"
    assert policy.max_total_model_cost_usd == Decimal("100")
    assert policy.require_approval_above_forecast_percentage == Decimal("90")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["cost_and_resource_policy"].update(extra=True),
        lambda p: p["cost_and_resource_policy"].pop("max_cloud_spend_usd"),
        lambda p: p["cost_and_resource_policy"].update(max_total_model_cost_usd=0),
        lambda p: p["cost_and_resource_policy"].update(max_ci_minutes_per_day=True),
        lambda p: p["cost_and_resource_policy"]["model_routing"].update(extra=True),
        lambda p: p["cost_and_resource_policy"].update(stop_conditions=["budget_exceeded"]),
    ],
)
def test_policy_parser_rejects_noncanonical_or_non_gate_bearing_payload(mutation):
    payload = _policy_payload()
    mutation(payload)
    with pytest.raises(CostForecastError):
        parse_structured_policy(payload)


def test_forecast_derives_all_six_dimensions_from_exact_inputs():
    decision = derive_forecast(_forecast_input())
    assert decision.outcome == "succeeded"
    assert decision.reason_code == "within_recorded_policy"
    assert decision.execution_provenance == "system_derived_cost_forecast"
    assert decision.gate_eligible is True
    assert decision.all_dimensions_within is True
    assert decision.approval_required is False
    dimensions = {row.dimension_code: row for row in decision.dimensions}
    assert set(dimensions) == {
        "all_cost_total_usd",
        "all_cost_daily_usd",
        "model_cost_total_usd",
        "model_cost_daily_usd",
        "cloud_spend_total_usd",
        "ci_minutes_daily",
    }
    assert dimensions["all_cost_total_usd"].forecast_value == Decimal("20")
    assert dimensions["model_cost_total_usd"].forecast_value == Decimal("6")
    assert dimensions["cloud_spend_total_usd"].forecast_value == Decimal("2")
    assert dimensions["ci_minutes_daily"].forecast_value == Decimal("10")


def test_explicit_zero_is_valid_but_omission_is_not_zero():
    complete = _forecast_input()
    assert derive_forecast(complete).gate_eligible is True
    with pytest.raises(CostForecastError, match="exactly once"):
        derive_forecast(replace(complete, assumptions=complete.assumptions[:-1]))


def test_model_remaining_cost_requires_tokens_and_exact_price():
    valid = _forecast_input()
    direct_model_usd = tuple(
        replace(line, remaining_total_usd=Decimal("1"), remaining_today_usd=Decimal("1"))
        if line.component == "model_inference"
        else line
        for line in valid.assumptions
    )
    with pytest.raises(CostForecastError, match="model_inference"):
        derive_forecast(replace(valid, assumptions=direct_model_usd))
    bad_line = replace(valid.model_lines[0], price=ModelPrice(Decimal("0"), Decimal("0")))
    with pytest.raises(CostForecastError, match="price"):
        derive_forecast(replace(valid, model_lines=(bad_line,)))


def test_numeric_and_integer_storage_bounds_fail_closed():
    valid = _forecast_input()
    oversized_money = tuple(
        replace(line, remaining_total_usd=Decimal("1000000000000"))
        if line.component == "tool_execution"
        else line
        for line in valid.assumptions
    )
    with pytest.raises(CostForecastError, match="NUMERIC"):
        derive_forecast(replace(valid, assumptions=oversized_money))
    oversized_tokens = replace(valid.model_lines[0], remaining_input_tokens=2_147_483_648)
    with pytest.raises(CostForecastError, match="permitted range"):
        derive_forecast(replace(valid, model_lines=(oversized_tokens,)))


def test_more_than_128_model_routes_fail_closed():
    valid = _forecast_input()
    model_lines = tuple(
        replace(
            valid.model_lines[0],
            model_route_hash="sha256:" + format(index, "064x"),
            remaining_input_tokens=0,
            remaining_output_tokens=0,
            remaining_today_input_tokens=0,
            remaining_today_output_tokens=0,
        )
        for index in range(129)
    )
    with pytest.raises(CostForecastError, match="128"):
        derive_forecast(replace(valid, model_lines=model_lines))


def test_approval_trigger_is_strict_and_never_gate_eligible():
    at_threshold = derive_forecast(_forecast_input(approval_percentage=12))
    assert at_threshold.approval_required is False
    assert at_threshold.gate_eligible is True
    above_threshold = derive_forecast(_forecast_input(approval_percentage=11))
    assert above_threshold.reason_code == "approval_required"
    assert above_threshold.approval_required is True
    assert above_threshold.gate_eligible is False


def test_hard_cap_equality_and_active_stop_both_block():
    at_cap = derive_forecast(_forecast_input(model_total=6))
    assert at_cap.reason_code == "limit_reached_or_exceeded"
    assert at_cap.gate_eligible is False
    stopped = derive_forecast(_forecast_input(stop_reason="budget_exceeded"))
    assert stopped.reason_code == "cost_stop_active"
    assert stopped.gate_eligible is False


def test_future_dated_incurred_event_refuses():
    valid = _forecast_input()
    future = replace(valid.ledger_lines[0], occurred_at=_AS_OF + timedelta(microseconds=1))
    with pytest.raises(CostForecastError, match="future"):
        derive_forecast(replace(valid, ledger_lines=(future, *valid.ledger_lines[1:])))


def _gate9(**changes):
    kwargs = {
        "cost_forecast_scope_resolved": True,
        "cost_forecast_policy_present": True,
        "cost_forecast_policy_valid": True,
        "cost_forecast_budget_present": True,
        "cost_forecast_budget_valid": True,
        "cost_forecast_history_count": 8,
        "cost_forecast_run_present": True,
        "cost_forecast_attempt_failed": False,
        "cost_forecast_binding_current": True,
        "cost_forecast_input_coverage_complete": True,
        "cost_forecast_price_coverage_complete": True,
        "cost_forecast_evidence_consistent": True,
        "cost_forecast_stop_active": False,
        "cost_forecast_all_dimensions_within": True,
        "cost_forecast_approval_required": False,
        "cost_forecast_gate_eligible": True,
        "cost_forecast_dimension_count": 6,
        "cost_forecast_utc_date": "2026-07-13",
        "cost_forecast_execution_provenance": "system_derived_cost_forecast",
    }
    kwargs.update(changes)
    report = evaluate_production_autonomy("p", readiness_level="R5", **kwargs)
    return next(g for g in report.gates if g.number == 9), report


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"cost_forecast_scope_resolved": False}, "no_current_release_scope"),
        ({"cost_forecast_policy_present": False}, "no_current_structured_cost_policy"),
        ({"cost_forecast_policy_valid": False}, "cost_policy_invalid"),
        ({"cost_forecast_budget_present": False}, "no_current_cost_budget"),
        ({"cost_forecast_budget_valid": False}, "cost_budget_invalid"),
        ({"cost_forecast_history_count": 0}, "no_cost_history"),
        ({"cost_forecast_run_present": False}, "cost_forecast_not_run"),
        ({"cost_forecast_attempt_failed": True}, "cost_forecast_latest_attempt_failed_or_refused"),
        ({"cost_forecast_binding_current": False}, "cost_forecast_binding_stale"),
        (
            {"cost_forecast_input_coverage_complete": False},
            "cost_forecast_input_or_price_coverage_incomplete",
        ),
        (
            {"cost_forecast_evidence_consistent": False},
            "cost_forecast_evidence_inconsistent",
        ),
        ({"cost_forecast_stop_active": True, "cost_forecast_gate_eligible": False}, "cost_stop_active"),
        (
            {
                "cost_forecast_all_dimensions_within": False,
                "cost_forecast_gate_eligible": False,
            },
            "cost_forecast_limit_reached_or_exceeded",
        ),
        (
            {"cost_forecast_approval_required": True, "cost_forecast_gate_eligible": False},
            "cost_forecast_requires_approval",
        ),
    ],
)
def test_gate9_fail_closed_ladder(changes, reason):
    gate, _report = _gate9(**changes)
    assert gate.status == "insufficient_evidence"
    assert gate.reason == reason


def test_gate9_pass_is_bounded_safe_context_and_non_authorizing():
    gate, report = _gate9()
    assert gate.status == "passed"
    assert gate.reason == "passed:system_derived_cost_forecast_within_recorded_policy"
    assert gate.context == {
        "scope_resolved": True,
        "structured_policy_present": True,
        "structured_policy_valid": True,
        "budget_present": True,
        "budget_valid": True,
        "ledger_event_count": 8,
        "run_present": True,
        "latest_attempt_failed_or_refused": False,
        "binding_current": True,
        "input_coverage_complete": True,
        "price_coverage_complete": True,
        "evidence_consistent": True,
        "stop_active": False,
        "all_dimensions_within": True,
        "approval_required": False,
        "gate_eligible": True,
        "dimension_count": 6,
        "forecast_utc_date": "2026-07-13",
        "execution_provenance": "system_derived_cost_forecast",
    }
    result = report.to_dict()
    assert result["ruleset_version"] == "slice51.v1"
    assert result["a5_satisfied"] is False
    assert result["can_go_live_autonomously"] is False
    assert tuple(result["can_go_live_reasons"]) == NO_GO_LIVE_REASONS


def test_gate9_caller_truth_flag_cannot_rescue_missing_or_inconsistent_evidence():
    missing, _ = _gate9(cost_forecast_policy_present=False, cost_forecast_gate_eligible=True)
    assert missing.reason == "no_current_structured_cost_policy"
    forged, _ = _gate9(cost_forecast_dimension_count=5, cost_forecast_gate_eligible=True)
    assert forged.reason == "cost_forecast_evidence_inconsistent"


def test_slice51_golden_matrix_changes_only_gate9():
    before = evaluate_production_autonomy("p", readiness_level="R5")
    _gate, after = _gate9()
    baseline = {gate.number: gate for gate in before.gates}
    advanced = {gate.number: gate for gate in after.gates}
    assert {number for number in baseline if baseline[number] != advanced[number]} == {9}


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


def _zero_inventories():
    empty_digest = digest_bytes(canonical_json_bytes([]))
    return tuple(
        SectionInventory(
            section_code=section,
            presence_code="present_zero_rows",
            item_count=0,
            section_digest=empty_digest,
            required=True,
            failure_code=None,
        )
        for section in INVENTORY_SECTIONS
    )


@pytest_asyncio.fixture
async def cost_forecast_ctx(db_session):
    from app.repositories.cost import BudgetRepository, CostEventRepository
    from app.repositories.cost_forecasts import CostForecastRepository
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.tenancy import TenantContext

    suffix = uuid.uuid4().hex[:10]
    org = await _scalar(
        db_session,
        "INSERT INTO organizations (name,slug) VALUES ('ForecastOrg',:s) RETURNING id",
        s=f"forecast-org-{suffix}",
    )
    tenant = await _scalar(
        db_session,
        "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'ForecastTenant',:s) RETURNING id",
        o=org,
        s=f"forecast-tenant-{suffix}",
    )
    project = await _scalar(
        db_session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'ForecastProject',:s) RETURNING id",
        t=tenant,
        s=f"forecast-project-{suffix}",
    )
    candidate = await _scalar(
        db_session,
        "INSERT INTO release_candidates (tenant_id,project_id,release_ref,status) "
        "VALUES (:t,:p,:r,'draft') RETURNING id",
        t=tenant,
        p=project,
        r=f"release-{suffix}",
    )
    await db_session.execute(
        text("UPDATE release_candidates SET status='frozen',frozen_at=:f WHERE id=:c"),
        {"c": candidate, "f": _AS_OF - timedelta(days=1)},
    )
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(tenant)}
    )
    await db_session.execute(text("SELECT * FROM audit_append('slice51-test','seed',NULL,'{}')"))
    context = TenantContext(tenant)
    packs = EvidencePackRepository(db_session, context)
    checkpoint = await packs.record_audit_checkpoint()
    inventories = _zero_inventories()
    core = assemble_core(
        project_id=project,
        release_candidate_id=candidate,
        release_ref_digest="sha256:" + "a" * 64,
        generated_at=checkpoint.created_at,
        frozen_at=_AS_OF - timedelta(days=1),
        artifact_scope_digest="sha256:" + "b" * 64,
        issue_binding_digest=digest_bytes(canonical_json_bytes([])),
        source_refs=(),
        inventories=inventories,
        traceability=(),
        audit_checkpoint=checkpoint,
        repo_commit_binding=derive_repo_commit_binding([]),
    )
    pack = await packs._persist_core(
        project_id=project,
        release_candidate_id=candidate,
        core=core,
        source_refs=(),
        inventories=inventories,
        traceability_edge_count=0,
        actor="slice51-test",
    )
    budget = await BudgetRepository(db_session, context).upsert(
        project_id=project,
        max_total_cost_usd="500",
        max_daily_cost_usd="200",
        actor="slice51-test",
    )
    costs = CostEventRepository(db_session, context)
    events = []
    for component in sorted(COST_COMPONENTS):
        events.append(
            await costs.record(
                project_id=project,
                component=component,
                amount_usd="1",
                actor="slice51-test",
                occurred_at=_AS_OF - timedelta(hours=1),
            )
        )
    forecasts = CostForecastRepository(db_session, context)
    policy = await forecasts.record_policy_version(
        project_id=project,
        payload=_policy_payload(),
        source_label="SENTINEL_POLICY_SOURCE",
        evidence_ref="SENTINEL_POLICY_EVIDENCE",
        actor="slice51-test",
    )
    await db_session.flush()
    return {
        "tenant": tenant,
        "project": project,
        "candidate": candidate,
        "pack": pack,
        "budget": budget,
        "events": events,
        "policy": policy,
        "repo": forecasts,
        "session": db_session,
    }


def _repo_assumptions():
    return tuple(
        ComponentAssumption(
            component=component,
            remaining_total_usd=Decimal("0") if component == "model_inference" else Decimal("1"),
            remaining_today_usd=Decimal("0") if component == "model_inference" else Decimal("1"),
        )
        for component in COST_COMPONENTS
    )


@pytest.mark.db
async def test_cost_forecast_catalog_rls_grants_and_findings_guard_pin(admin_engine):
    tables = {
        "cost_forecast_policy_versions",
        "cost_forecast_runs",
        "cost_forecast_ledger_event_refs",
        "cost_forecast_input_lines",
        "cost_forecast_dimension_results",
    }
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                    "WHERE relname = ANY(:names) ORDER BY relname"
                ),
                {"names": list(tables)},
            )
        ).all()
        assert {row[0] for row in rows} == tables
        assert all(row[1:] == (True, True) for row in rows)
        for table in tables:
            assert await _scalar(
                conn, f"SELECT has_table_privilege('uaid_app','{table}','SELECT')"
            ) is True
            assert await _scalar(
                conn, f"SELECT has_table_privilege('uaid_app','{table}','INSERT')"
            ) is True
            assert await _scalar(
                conn, f"SELECT has_table_privilege('uaid_app','{table}','UPDATE')"
            ) is False
        assert await _scalar(
            conn,
            "SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))",
        ) == "808036faf2660d6810aeca4342e6f1ac"


@pytest.mark.db
async def test_repository_records_exact_forecast_and_gate9_passes(cost_forecast_ctx):
    from app.repositories.cost_forecasts import ReportedModelPlan

    ctx = cost_forecast_ctx
    run = await ctx["repo"].generate_forecast(
        project_id=ctx["project"],
        assumptions=_repo_assumptions(),
        model_plans=(
            ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),
        ),
        price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
        forecast_ci_minutes_today=10,
        as_of=_AS_OF,
        actor="slice51-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert run.outcome == "succeeded"
    assert run.gate_eligible is True
    assert run.event_ref_count == 8
    assert run.input_line_count == 10
    assert run.dimension_count == 6
    coverage = await ctx["repo"].coverage_for_project(ctx["project"], as_of=_AS_OF)
    gate = next(
        item
        for item in evaluate_production_autonomy(
            ctx["project"], readiness_level="R5", **coverage.gate_kwargs()
        ).gates
        if item.number == 9
    )
    assert gate.status == "passed"
    assert gate.reason == "passed:system_derived_cost_forecast_within_recorded_policy"


@pytest.mark.db
async def test_production_autonomy_repository_uses_current_forecast_coverage(cost_forecast_ctx):
    from app.repositories.cost_forecasts import ReportedModelPlan
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.tenancy import TenantContext

    ctx = cost_forecast_ctx
    await ctx["repo"].generate_forecast(
        project_id=ctx["project"],
        assumptions=_repo_assumptions(),
        model_plans=(ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),),
        price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
        forecast_ci_minutes_today=10,
        as_of=_AS_OF,
        actor="slice51-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    report = await ProductionAutonomyRepository(
        ctx["session"], TenantContext(ctx["tenant"])
    ).evaluate(ctx["project"])
    gate9 = next(gate for gate in report.gates if gate.number == 9)
    assert gate9.status == "passed"


@pytest.mark.db
async def test_utc_day_rollover_decurrents_prior_forecast(cost_forecast_ctx):
    from app.repositories.cost_forecasts import ReportedModelPlan

    ctx = cost_forecast_ctx
    await ctx["repo"].generate_forecast(
        project_id=ctx["project"],
        assumptions=_repo_assumptions(),
        model_plans=(ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),),
        price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
        forecast_ci_minutes_today=10,
        as_of=_AS_OF,
        actor="slice51-test",
    )
    coverage = await ctx["repo"].coverage_for_project(
        ctx["project"], as_of=_AS_OF + timedelta(days=1)
    )
    assert coverage.binding_current is False
    report = evaluate_production_autonomy(
        ctx["project"], readiness_level="R5", **coverage.gate_kwargs()
    )
    gate9 = next(item for item in report.gates if item.number == 9)
    assert gate9.reason == "cost_forecast_binding_stale"


@pytest.mark.db
async def test_future_event_refuses_without_result_children(cost_forecast_ctx):
    from app.repositories.cost import CostEventRepository
    from app.repositories.cost_forecasts import ReportedModelPlan
    from app.tenancy import TenantContext

    ctx = cost_forecast_ctx
    costs = CostEventRepository(ctx["session"], TenantContext(ctx["tenant"]))
    await costs.record(
        project_id=ctx["project"],
        component="tool_execution",
        amount_usd="1",
        occurred_at=_AS_OF + timedelta(seconds=1),
        actor="slice51-test",
    )
    run = await ctx["repo"].generate_forecast(
        project_id=ctx["project"],
        assumptions=_repo_assumptions(),
        model_plans=(ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),),
        price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
        forecast_ci_minutes_today=10,
        as_of=_AS_OF,
        actor="slice51-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert run.outcome == "refused"
    assert run.reason_code == "cost_forecast_input_or_price_invalid"
    assert await _scalar(
        ctx["session"], "SELECT count(*) FROM cost_forecast_dimension_results WHERE run_id=:r", r=run.id
    ) == 0


@pytest.mark.db
async def test_active_stop_precedes_forecast_limit_and_blocks_gate(cost_forecast_ctx):
    from app.repositories.cost import BudgetRepository
    from app.repositories.cost_forecasts import ReportedModelPlan
    from app.tenancy import TenantContext

    ctx = cost_forecast_ctx
    await BudgetRepository(ctx["session"], TenantContext(ctx["tenant"])).upsert(
        project_id=ctx["project"],
        max_total_cost_usd="8",
        max_daily_cost_usd="200",
        actor="slice51-test",
    )
    run = await ctx["repo"].generate_forecast(
        project_id=ctx["project"],
        assumptions=_repo_assumptions(),
        model_plans=(ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),),
        price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
        forecast_ci_minutes_today=10,
        as_of=_AS_OF,
        actor="slice51-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert run.stop_reason == "budget_exceeded"
    assert run.reason_code == "cost_stop_active"
    assert run.gate_eligible is False


@pytest.mark.db
async def test_db_reverification_rejects_an_omitted_source_event(cost_forecast_ctx):
    from app.repositories.cost import CostEventRepository
    from app.repositories.cost_forecasts import ReportedModelPlan
    from app.tenancy import TenantContext

    ctx = cost_forecast_ctx
    run = await ctx["repo"].generate_forecast(
        project_id=ctx["project"],
        assumptions=_repo_assumptions(),
        model_plans=(ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),),
        price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
        forecast_ci_minutes_today=10,
        as_of=_AS_OF,
        actor="slice51-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await CostEventRepository(ctx["session"], TenantContext(ctx["tenant"])).record(
        project_id=ctx["project"],
        component="tool_execution",
        amount_usd="1",
        occurred_at=_AS_OF - timedelta(seconds=1),
        actor="slice51-test",
    )
    with pytest.raises(DBAPIError, match="source event inventory"):
        await ctx["session"].execute(
            text("SELECT verify_cost_forecast_run(:run_id)"), {"run_id": run.id}
        )


@pytest.mark.db
@pytest.mark.parametrize(
    ("table", "assignment"),
    (
        ("cost_forecast_dimension_results", "forecast_value=0"),
        ("cost_forecast_dimension_results", "policy_limit=999999"),
        ("cost_forecast_dimension_results", "within_limit=true"),
        ("cost_forecast_dimension_results", "approval_triggered=false"),
        ("cost_forecast_runs", "all_dimensions_within=true"),
        ("cost_forecast_runs", "approval_required=false"),
        ("cost_forecast_runs", "evidence_consistent=true"),
        ("cost_forecast_runs", "gate_eligible=true"),
    ),
)
async def test_direct_sql_cannot_forge_dimension_or_gate_eligibility(
    cost_forecast_ctx, table, assignment
):
    from app.repositories.cost_forecasts import ReportedModelPlan

    ctx = cost_forecast_ctx
    run = await ctx["repo"].generate_forecast(
        project_id=ctx["project"],
        assumptions=_repo_assumptions(),
        model_plans=(ReportedModelPlan("model-a", 1000, 1000, 1000, 1000),),
        price_card={"model-a": ModelPrice(Decimal("2"), Decimal("3"))},
        forecast_ci_minutes_today=10,
        as_of=_AS_OF,
        actor="slice51-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pytest.raises(DBAPIError):
        async with ctx["session"].begin_nested():
            await ctx["session"].execute(
                text(
                    f"UPDATE {table} SET {assignment} WHERE "
                    + ("run_id=:r" if table.endswith("results") else "id=:r")
                ),
                {"r": run.id},
            )


@pytest.mark.db
async def test_forecast_audit_is_safe_metadata_only(cost_forecast_ctx):
    ctx = cost_forecast_ctx
    payloads = (
        await ctx["session"].execute(
            text(
                "SELECT payload::text FROM audit_logs WHERE tenant_id=:t "
                "AND action LIKE 'cost_forecast.%'"
            ),
            {"t": ctx["tenant"]},
        )
    ).scalars().all()
    encoded = json.dumps(payloads)
    assert "SENTINEL_POLICY_SOURCE" not in encoded
    assert "SENTINEL_POLICY_EVIDENCE" not in encoded
