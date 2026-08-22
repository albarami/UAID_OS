"""Slice 56 §25.1 ops-signal assessment — pure contract proofs."""

from __future__ import annotations

import ast
import hashlib
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.cost import BudgetCeilings, evaluate_stop
from app.ops.assessment import build_assessment
from app.ops.collect import collect_ops_signals
from app.ops.signals import (
    FORBIDDEN_SAMPLE_CLASSES,
    HISTORY_LIMIT_DEFAULT,
    HISTORY_LIMIT_MAX,
    OPS_CONTRACT_VERSION,
    REASON_CODES,
    RULESET_VERSION,
    SIGNAL_CLASSES,
    THRESHOLD_EVAL_VERSION,
    CallerSample,
    CostObservation,
    OpsSignalError,
    OpsSignalIdempotencyRace,
    compute_counters,
    cost_event_in_daily,
    cost_event_in_total,
    evaluate_caller_threshold,
    input_digest,
    parse_samples,
    request_digest,
    utc_midnight,
)
from app.release.production_autonomy import (
    A5_RULESET_VERSION,
    NO_GO_LIVE_REASONS,
    evaluate_production_autonomy,
)
from app.tenancy import TenantContext

_AS_OF = datetime(2026, 8, 22, 15, 0, 0, tzinfo=timezone.utc)
_PROJECT = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_STABLE = {
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": ("7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26"),
    "app/runtime/control_loop.py": (
        "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180"
    ),
}


def _cost(*, total="0", daily="0", budget: BudgetCeilings | None = None) -> CostObservation:
    total_spent = Decimal(total)
    daily_spent = Decimal(daily)
    return CostObservation(
        total_spent=total_spent,
        daily_spent=daily_spent,
        utc_midnight=utc_midnight(_AS_OF),
        budget=budget,
        decision=evaluate_stop(total_spent=total_spent, daily_spent=daily_spent, budget=budget),
    )


def _assess(*, failed_run_ids=(), cost=None, samples=()):
    return build_assessment(
        project_id=_PROJECT,
        as_of=_AS_OF,
        failed_run_ids=failed_run_ids,
        cost=cost if cost is not None else _cost(),
        samples=samples,
    )


def _by_class(rows):
    return {row.signal_class: row for row in rows}


def _window(*, hours=1):
    return {
        "window_start": _AS_OF - timedelta(hours=hours),
        "window_end": _AS_OF,
    }


def test_contracts_and_default_empty_matrix():
    assert OPS_CONTRACT_VERSION == "slice56.ops_signals.v1"
    assert THRESHOLD_EVAL_VERSION == "slice56.threshold_eval.v1"
    assert RULESET_VERSION == "slice56.v1"
    assert len(SIGNAL_CLASSES) == 11 and "unknown" not in SIGNAL_CLASSES
    assert "no_uptime_source" in REASON_CODES
    rows = _assess()
    counters = compute_counters(rows)
    assert (
        counters.observed_count,
        counters.caller_supplied_count,
        counters.not_observed_count,
    ) == (2, 0, 9)
    assert counters.breached_count == 0
    mapped = _by_class(rows)
    assert mapped["job_failures"].observation_status == "observed"
    assert mapped["job_failures"].metric_int == 0
    assert mapped["job_failures"].threshold_state == "not_evaluable"
    assert mapped["cost_anomalies"].reason_code == "cost_no_budget"
    assert mapped["cost_anomalies"].threshold_state == "not_evaluable"
    assert mapped["uptime"].reason_code == "no_uptime_source"


def test_samples_fill_ratio_and_count_and_refuse_locked_or_partial():
    samples = parse_samples(
        [
            {
                "signal_class": "model_output_drift",
                "metric_ratio": "0.20",
                "threshold_ratio": "0.10",
                **_window(),
            },
            {
                "signal_class": "data_quality_issues",
                "metric_int": 1,
                "threshold_int": 3,
                **_window(),
            },
        ]
    )
    mapped = _by_class(_assess(samples=samples))
    assert mapped["model_output_drift"].observation_status == "caller_supplied_unverified"
    assert mapped["model_output_drift"].threshold_state == "breached"
    assert mapped["data_quality_issues"].threshold_state == "ok"
    assert compute_counters(_assess(samples=samples)).caller_supplied_count == 2
    with pytest.raises(OpsSignalError):
        parse_samples([{"signal_class": "error_rates", "metric_ratio": "0.01", **_window()}])
    for locked in FORBIDDEN_SAMPLE_CLASSES:
        payload = {"signal_class": locked, "metric_int": 1, "threshold_int": 2, **_window()}
        with pytest.raises(OpsSignalError):
            parse_samples([payload])
    with pytest.raises(OpsSignalError):
        parse_samples(
            [
                {
                    "signal_class": "latency",
                    "metric_ratio": "0.1",
                    "threshold_ratio": "0.2",
                    **_window(),
                }
            ]
        )
    with pytest.raises(OpsSignalError):
        parse_samples(
            [{"signal_class": "cpu_temp", "metric_int": 1, "threshold_int": 2, **_window()}]
        )
    with pytest.raises(OpsSignalError):
        parse_samples(
            [
                {
                    "signal_class": "error_rates",
                    "metric_ratio": "1.01",
                    "threshold_ratio": "1",
                    **_window(),
                }
            ]
        )


def test_caller_sample_dataclass_uses_the_same_bounds_as_mappings():
    window = _window()
    with pytest.raises(OpsSignalError):
        parse_samples(
            [
                CallerSample(
                    signal_class="error_rates",
                    window_start=window["window_start"],
                    window_end=window["window_end"],
                    metric_ratio=Decimal("2"),
                    threshold_ratio=Decimal("1.5"),
                )
            ]
        )
    with pytest.raises(OpsSignalError):
        parse_samples(
            [
                CallerSample(
                    signal_class="error_rates",
                    window_start=window["window_start"],
                    window_end=window["window_end"],
                    metric_ratio=Decimal("0.1"),
                    threshold_ratio=Decimal("0.2"),
                    metric_int=3,
                )
            ]
        )
    with pytest.raises(OpsSignalError):
        evaluate_caller_threshold(
            CallerSample(
                signal_class="error_rates",
                window_start=window["window_start"],
                window_end=window["window_end"],
                metric_ratio=Decimal("2"),
                threshold_ratio=Decimal("1.5"),
            ),
            _AS_OF,
        )


def test_cost_snapshot_rules_and_as_of_window():
    none = _by_class(_assess(cost=_cost()))["cost_anomalies"]
    assert none.metric_money == Decimal("0") and none.threshold_money is None
    budget = BudgetCeilings(max_total_cost_usd=Decimal("10"), max_daily_cost_usd=Decimal("4"))
    exceeded = _by_class(_assess(cost=_cost(total="10", budget=budget)))["cost_anomalies"]
    assert exceeded.threshold_state == "breached" and exceeded.reason_code == "cost_budget_exceeded"
    assert exceeded.threshold_money == Decimal("10")
    daily = _by_class(_assess(cost=_cost(total="1", daily="4", budget=budget)))["cost_anomalies"]
    assert daily.reason_code == "cost_daily_budget_exceeded"
    ok = _by_class(_assess(cost=_cost(total="1", daily="1", budget=budget)))["cost_anomalies"]
    assert ok.threshold_state == "ok" and ok.threshold_money_daily == Decimal("4")
    uncapped = BudgetCeilings(max_total_cost_usd=Decimal("10"), max_daily_cost_usd=None)
    within = _by_class(_assess(cost=_cost(total="1", daily="9", budget=uncapped)))["cost_anomalies"]
    assert within.reason_code == "cost_within_budget" and within.threshold_money_daily is None
    later = _AS_OF + timedelta(minutes=1)
    assert cost_event_in_total(later, _AS_OF) is False
    assert cost_event_in_daily(_AS_OF - timedelta(hours=1), _AS_OF) is True
    assert cost_event_in_daily(_AS_OF - timedelta(days=1), _AS_OF) is False


def test_request_digest_ignores_as_of_and_allowlist_skips_adjacent_stores():
    samples = parse_samples(
        [{"signal_class": "latency", "metric_int": 100, "threshold_int": 200, **_window()}]
    )
    first = request_digest(_PROJECT, samples)
    later_as_of = _AS_OF + timedelta(seconds=5)
    later_rows = build_assessment(
        project_id=_PROJECT,
        as_of=later_as_of,
        failed_run_ids=(),
        cost=_cost(),
        samples=samples,
    )
    assert request_digest(_PROJECT, samples) == first
    assert input_digest(_PROJECT, later_as_of, later_rows) != input_digest(
        _PROJECT, _AS_OF, _assess(samples=samples)
    )
    changed = parse_samples(
        [{"signal_class": "latency", "metric_int": 101, "threshold_int": 200, **_window()}]
    )
    assert request_digest(_PROJECT, changed) != first
    owned = (
        Path("app/ops/collect.py").read_text()
        + Path("app/repositories/ops_signals.py").read_text()
        + Path("app/ops/assessment.py").read_text()
    )
    for forbidden in (
        "latest_monitoring",
        "monitoring_status_snapshots",
        "deployment_target_snapshots",
        "release_findings",
        "pm_issue",
    ):
        assert forbidden not in owned
    assert "from app.repositories.cost import evaluate" not in owned
    assert "CostEventRepository(" not in owned
    tree = ast.parse(Path("app/ops/collect.py").read_text())
    params = {
        arg.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "collect_ops_signals"
        for arg in node.args.args + node.args.kwonlyargs
    }
    assert "session" not in params and "as_of" not in params
    assert "session" not in inspect.signature(collect_ops_signals).parameters
    assert "as_of" not in inspect.signature(collect_ops_signals).parameters
    assert HISTORY_LIMIT_DEFAULT == 50
    assert HISTORY_LIMIT_MAX == 100
    from app.ops.db_checks import CHILD_CHECK_CONSTRAINTS

    shared = {name for name, _sql in CHILD_CHECK_CONSTRAINTS}
    for required in (
        "sampleable_not_ledger",
        "metric_money_daily_nonneg",
        "metric_ratio_bounds",
        "metric_int_bounds",
        "metric_money_nonneg",
    ):
        assert required in shared
    model_src = Path("app/models/ops_signal.py").read_text()
    migration_src = Path("migrations/versions/0055_ops_signals.py").read_text()
    assert "CHILD_CHECK_CONSTRAINTS" in model_src
    assert "CHILD_CHECK_CONSTRAINTS" in migration_src


def test_a5_readiness_and_go_live_remain_hard_false():
    for path, digest in _STABLE.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    project_id = uuid.uuid4()
    before = evaluate_production_autonomy(project_id, readiness_level="R2")
    after = evaluate_production_autonomy(project_id, readiness_level="R2")
    assert before.to_dict() == after.to_dict()
    assert after.to_dict()["can_go_live_autonomously"] is False
    assert A5_RULESET_VERSION == "slice54.v1"
    assert NO_GO_LIVE_REASONS == ("a5_gates_not_all_satisfied",)
    from app.intake.readiness import RULESET_VERSION as readiness_ruleset

    assert readiness_ruleset == "slice20.v1"
    assert (
        "cannot downgrade Slice 56 while ops-signal rows exist"
        in Path("migrations/versions/0055_ops_signals.py").read_text()
    )
    assert (
        'down_revision: str | None = "0054"'
        in Path("migrations/versions/0055_ops_signals.py").read_text()
    )


def _dbapi_error(sqlstate: str) -> DBAPIError:
    original = type("OriginalDatabaseError", (Exception,), {"sqlstate": sqlstate})()
    return DBAPIError("ops_retry_probe", {}, original)


async def _patched_collect(monkeypatch, fake_once):
    from app.ops import collect as collect_mod

    monkeypatch.setattr(collect_mod, "_collect_once", fake_once)
    monkeypatch.setattr(collect_mod.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(collect_mod.random, "uniform", lambda _a, _b: 0.0)
    return await collect_ops_signals(
        TenantContext(uuid.uuid4()),
        uuid.uuid4(),
        actor="ops-test",
        idempotency_key="retry-key",
    )


async def test_collect_retries_empty_reselect_then_succeeds(monkeypatch):
    from app.ops import collect as collect_mod

    winner = MagicMock(name="snapshot")
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise collect_mod._IdempotencyWinnerNotVisible()
        return winner

    assert await _patched_collect(monkeypatch, fake_once) is winner
    assert calls["n"] == 2


async def test_collect_retries_serialization_sqlstates_then_succeeds(monkeypatch):
    winner = MagicMock(name="snapshot")
    seen: list[str] = []

    async def fake_once(*_args, **_kwargs):
        if len(seen) < 2:
            code = "40001" if not seen else "40P01"
            seen.append(code)
            raise _dbapi_error(code)
        return winner

    assert await _patched_collect(monkeypatch, fake_once) is winner
    assert seen == ["40001", "40P01"]


async def test_collect_exhausts_five_race_retries(monkeypatch):
    from app.ops import collect as collect_mod

    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        raise collect_mod._IdempotencyWinnerNotVisible()

    with pytest.raises(OpsSignalIdempotencyRace):
        await _patched_collect(monkeypatch, fake_once)
    assert calls["n"] == collect_mod.MAX_IDEMPOTENCY_RACE_RETRIES


async def test_collect_does_not_retry_non_serialization_errors(monkeypatch):
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        raise _dbapi_error("23505")

    with pytest.raises(DBAPIError):
        await _patched_collect(monkeypatch, fake_once)
    assert calls["n"] == 1
