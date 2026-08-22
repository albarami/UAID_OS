"""Pure §25.1 ops-signal contract (Slice 56). No DB, no I/O, no network.

Assesses eleven named classes with source-bound thresholds only. Does not claim
production is live, that monitoring is adequate, or that incidents were opened.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Sequence

from app.cost import BudgetCeilings, CostStopDecision, to_decimal

OPS_CONTRACT_VERSION = "slice56.ops_signals.v1"
THRESHOLD_EVAL_VERSION = "slice56.threshold_eval.v1"
RULESET_VERSION = "slice56.v1"

SIGNAL_CLASSES: tuple[str, ...] = (
    "uptime",
    "error_rates",
    "latency",
    "job_failures",
    "security_alerts",
    "user_journey_failures",
    "data_quality_issues",
    "cost_anomalies",
    "model_output_drift",
    "support_tickets",
    "incident_reports",
)
CLASS_SEQ: dict[str, int] = {name: index for index, name in enumerate(SIGNAL_CLASSES, start=1)}

REASON_CODES: tuple[str, ...] = (
    "no_uptime_source",
    "no_error_rate_source",
    "no_latency_source",
    "no_post_launch_security_alert_source",
    "no_journey_failure_source",
    "no_data_quality_source",
    "no_model_drift_source",
    "no_support_ticket_source",
    "no_incident_store",
    "no_job_slo_threshold",
    "cost_ledger_recorded",
    "cost_no_budget",
    "cost_budget_exceeded",
    "cost_daily_budget_exceeded",
    "cost_within_budget",
    "uaid_runtime_failed_run_count",
    "caller_sample_accepted",
    "caller_threshold_ok",
    "caller_threshold_breached",
)

OBSERVATION_STATUSES = ("observed", "caller_supplied_unverified", "not_observed")
TRUTH_TIERS = ("none", "system_derived_ledger", "caller_supplied_unverified")
SOURCE_KINDS = ("none", "cost_ledger", "uaid_runtime", "caller_supplied")
SOURCE_TABLES = ("none", "cost_events_and_budgets", "run_steps", "caller_sample")
WINDOW_KINDS = ("none", "cumulative_project", "caller_declared")
THRESHOLD_PROVENANCES = ("none", "recorded_budget", "caller_supplied_unverified")
THRESHOLD_KINDS = ("none", "cost_stop", "caller_count", "caller_ratio", "caller_ms")
METRIC_KINDS = ("none", "count", "ratio", "milliseconds", "money")
THRESHOLD_STATES = ("not_evaluable", "ok", "breached")

ALLOWED_SAMPLE_CLASSES = frozenset(
    {
        "error_rates",
        "latency",
        "user_journey_failures",
        "data_quality_issues",
        "model_output_drift",
    }
)
FORBIDDEN_SAMPLE_CLASSES = frozenset(SIGNAL_CLASSES) - ALLOWED_SAMPLE_CLASSES
RATIO_SAMPLE_CLASSES = frozenset({"error_rates", "model_output_drift"})
COUNT_SAMPLE_CLASSES = frozenset({"user_journey_failures", "data_quality_issues"})
MS_SAMPLE_CLASSES = frozenset({"latency"})
LEDGER_CLASSES = frozenset({"job_failures", "cost_anomalies"})
STRUCTURALLY_UNOBSERVED = frozenset(
    {"uptime", "security_alerts", "support_tickets", "incident_reports"}
)

NOT_OBSERVED_REASONS: dict[str, str] = {
    "uptime": "no_uptime_source",
    "error_rates": "no_error_rate_source",
    "latency": "no_latency_source",
    "security_alerts": "no_post_launch_security_alert_source",
    "user_journey_failures": "no_journey_failure_source",
    "data_quality_issues": "no_data_quality_source",
    "model_output_drift": "no_model_drift_source",
    "support_tickets": "no_support_ticket_source",
    "incident_reports": "no_incident_store",
}

INTEGER_MAX = 2_147_483_647
IDEMPOTENCY_KEY_MAX = 200
HISTORY_LIMIT_DEFAULT = 50
HISTORY_LIMIT_MAX = 100
DIGEST_RE = r"^sha256:[0-9a-f]{64}$"

_RATIO_KEYS = frozenset(
    {"signal_class", "metric_ratio", "threshold_ratio", "window_start", "window_end"}
)
_INT_KEYS = frozenset({"signal_class", "metric_int", "threshold_int", "window_start", "window_end"})


class OpsSignalError(ValueError):
    """Fail-closed ops-signal contract error."""


class OpsSignalIdempotencyConflict(OpsSignalError):
    """Idempotency key reused with a different request digest."""


class OpsSignalIdempotencyRace(OpsSignalError):
    """REPEATABLE READ winner stayed invisible after bounded retries."""


@dataclass(frozen=True)
class CallerSample:
    """Caller-supplied unverified fixture sample. Not live telemetry."""

    signal_class: str
    window_start: datetime
    window_end: datetime
    metric_int: int | None = None
    metric_ratio: Decimal | None = None
    threshold_int: int | None = None
    threshold_ratio: Decimal | None = None


@dataclass(frozen=True)
class SignalRow:
    """One assessed §25.1 class. Persistence shape; not an adequacy claim."""

    seq: int
    signal_class: str
    observation_status: str
    truth_tier: str
    source_kind: str
    source_table: str
    source_ref: uuid.UUID | None
    source_digest: str | None
    window_kind: str
    window_start: datetime | None
    window_end: datetime | None
    reason_code: str
    threshold_provenance: str
    threshold_kind: str
    threshold_int: int | None
    threshold_ratio: Decimal | None
    threshold_money: Decimal | None
    threshold_money_daily: Decimal | None
    metric_kind: str
    metric_int: int | None
    metric_ratio: Decimal | None
    metric_money: Decimal | None
    metric_money_daily: Decimal | None
    threshold_state: str


@dataclass(frozen=True)
class Counters:
    observed_count: int
    caller_supplied_count: int
    not_observed_count: int
    breached_count: int


@dataclass(frozen=True)
class CostObservation:
    """Bounded ledger snapshot plus the pure stop decision over that snapshot."""

    total_spent: Decimal
    daily_spent: Decimal
    utc_midnight: datetime
    budget: BudgetCeilings | None
    decision: CostStopDecision


@dataclass(frozen=True)
class OpsObservationSnapshot:
    """Immutable collect result copied out of the transaction."""

    id: uuid.UUID
    project_id: uuid.UUID
    as_of: datetime
    ruleset_version: str
    idempotency_key: str
    request_digest: str
    input_digest: str
    observed_count: int
    caller_supplied_count: int
    not_observed_count: int
    breached_count: int
    signals: tuple[SignalRow, ...]


def format_utc(value: datetime) -> str:
    """Format an aware datetime as ``YYYY-MM-DDTHH:MM:SS.ffffffZ``."""
    if value.tzinfo is None:
        raise OpsSignalError("datetime must be timezone-aware")
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc_midnight(as_of: datetime) -> datetime:
    """UTC midnight of the ``as_of`` calendar day."""
    if as_of.tzinfo is None:
        raise OpsSignalError("as_of must be timezone-aware")
    utc = as_of.astimezone(timezone.utc)
    return datetime(utc.year, utc.month, utc.day, tzinfo=timezone.utc)


def cost_event_in_total(occurred_at: datetime, as_of: datetime) -> bool:
    """Whether a cost event is inside the total window ``occurred_at < as_of``."""
    return occurred_at < as_of


def cost_event_in_daily(occurred_at: datetime, as_of: datetime) -> bool:
    """Whether a cost event is inside ``[utc_midnight, as_of)``."""
    return utc_midnight(as_of) <= occurred_at < as_of


def canonical_digest(payload: Mapping[str, object]) -> str:
    """Return ``sha256:`` of canonical JSON with sorted keys."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_idempotency_key(value: str) -> str:
    """Return a stripped idempotency key or raise."""
    if not isinstance(value, str):
        raise OpsSignalError("idempotency_key must be a string")
    key = value.strip()
    if not key or len(key) > IDEMPOTENCY_KEY_MAX:
        raise OpsSignalError("idempotency_key must be non-blank and <=200 characters")
    return key


def validate_history_limit(limit: int) -> int:
    """Return a history limit in ``1..100`` or raise."""
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise OpsSignalError("history limit must be an int")
    if limit < 1 or limit > HISTORY_LIMIT_MAX:
        raise OpsSignalError("history limit must be between 1 and 100")
    return limit


def _require_aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise OpsSignalError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpsSignalError(f"{field} must be an int")
    if value < 0 or value > INTEGER_MAX:
        raise OpsSignalError(f"{field} must be between 0 and {INTEGER_MAX}")
    return value


def _require_ratio(value: object, field: str) -> Decimal:
    ratio = to_decimal(value, field)
    if ratio < 0 or ratio > 1:
        raise OpsSignalError(f"{field} must be between 0 and 1 inclusive")
    return ratio


def money_str(value: Decimal | None) -> str | None:
    """Render a Decimal as ``str(Decimal)`` for canonical digests, or None."""
    return None if value is None else str(value)


def _sample_as_mapping(sample: CallerSample) -> dict[str, object]:
    """Project a dataclass sample into the same key set a mapping sample uses."""
    payload: dict[str, object] = {
        "signal_class": sample.signal_class,
        "window_start": sample.window_start,
        "window_end": sample.window_end,
    }
    if sample.metric_ratio is not None:
        payload["metric_ratio"] = sample.metric_ratio
    if sample.threshold_ratio is not None:
        payload["threshold_ratio"] = sample.threshold_ratio
    if sample.metric_int is not None:
        payload["metric_int"] = sample.metric_int
    if sample.threshold_int is not None:
        payload["threshold_int"] = sample.threshold_int
    return payload


def coerce_caller_sample(item: Mapping[str, object] | CallerSample) -> CallerSample:
    """Validate mapping and dataclass samples through the same shape checks."""
    if isinstance(item, CallerSample):
        return _parse_sample_mapping(_sample_as_mapping(item))
    return _parse_sample_mapping(item)


def parse_samples(
    raw: Sequence[Mapping[str, object] | CallerSample] | None,
) -> tuple[CallerSample, ...]:
    """Parse caller samples. Extra fields, OOV classes, and partial shapes fail closed."""
    if raw is None:
        return ()
    parsed: list[CallerSample] = []
    seen: set[str] = set()
    for item in raw:
        sample = coerce_caller_sample(item)
        if sample.signal_class in seen:
            raise OpsSignalError(f"duplicate sample class {sample.signal_class}")
        seen.add(sample.signal_class)
        parsed.append(sample)
    return tuple(sorted(parsed, key=lambda row: CLASS_SEQ[row.signal_class]))


def _parse_sample_mapping(item: Mapping[str, object]) -> CallerSample:
    if type(item) is not dict:
        raise OpsSignalError("sample must be a mapping")
    keys = frozenset(item)
    signal_class = item.get("signal_class")
    if not isinstance(signal_class, str):
        raise OpsSignalError("sample signal_class must be a string")
    if signal_class not in SIGNAL_CLASSES:
        raise OpsSignalError(f"unknown signal class {signal_class}")
    if signal_class in FORBIDDEN_SAMPLE_CLASSES:
        raise OpsSignalError(f"sample class {signal_class} cannot overwrite structural observation")
    if signal_class in RATIO_SAMPLE_CLASSES:
        if keys != _RATIO_KEYS:
            raise OpsSignalError(
                f"{signal_class} sample requires metric_ratio and threshold_ratio only"
            )
        return CallerSample(
            signal_class=signal_class,
            window_start=_require_aware_utc(item["window_start"], "window_start"),  # type: ignore[arg-type]
            window_end=_require_aware_utc(item["window_end"], "window_end"),  # type: ignore[arg-type]
            metric_ratio=_require_ratio(item["metric_ratio"], "metric_ratio"),
            threshold_ratio=_require_ratio(item["threshold_ratio"], "threshold_ratio"),
        )
    expected = _INT_KEYS
    kind = "metric_int and threshold_int"
    if keys != expected:
        raise OpsSignalError(f"{signal_class} sample requires {kind} only")
    if signal_class not in COUNT_SAMPLE_CLASSES and signal_class not in MS_SAMPLE_CLASSES:
        raise OpsSignalError(f"sample class {signal_class} is not allowed")
    return CallerSample(
        signal_class=signal_class,
        window_start=_require_aware_utc(item["window_start"], "window_start"),  # type: ignore[arg-type]
        window_end=_require_aware_utc(item["window_end"], "window_end"),  # type: ignore[arg-type]
        metric_int=_require_int(item["metric_int"], "metric_int"),
        threshold_int=_require_int(item["threshold_int"], "threshold_int"),
    )


def sample_digest_payload(sample: CallerSample) -> dict[str, object]:
    """Canonical sample payload including window bounds (source_digest material)."""
    payload: dict[str, object] = {
        "signal_class": sample.signal_class,
        "window_end": format_utc(sample.window_end),
        "window_start": format_utc(sample.window_start),
    }
    if sample.metric_ratio is not None:
        payload["metric_ratio"] = str(sample.metric_ratio)
        payload["threshold_ratio"] = str(sample.threshold_ratio)
    else:
        payload["metric_int"] = sample.metric_int
        payload["threshold_int"] = sample.threshold_int
    return payload


def request_digest(project_id: uuid.UUID, samples: Sequence[CallerSample]) -> str:
    """Idempotency identity: ruleset + project + canonical samples. Excludes as_of."""
    return canonical_digest(
        {
            "project_id": str(project_id),
            "ruleset_version": RULESET_VERSION,
            "samples": [sample_digest_payload(sample) for sample in samples],
        }
    )


def signal_digest_material(row: SignalRow) -> dict[str, object]:
    """Canonical child payload hashed into the parent input digest."""
    return {
        "metric_int": row.metric_int,
        "metric_kind": row.metric_kind,
        "metric_money": money_str(row.metric_money),
        "metric_money_daily": money_str(row.metric_money_daily),
        "metric_ratio": None if row.metric_ratio is None else str(row.metric_ratio),
        "observation_status": row.observation_status,
        "reason_code": row.reason_code,
        "signal_class": row.signal_class,
        "source_digest": row.source_digest,
        "source_kind": row.source_kind,
        "source_ref": None if row.source_ref is None else str(row.source_ref),
        "source_table": row.source_table,
        "threshold_int": row.threshold_int,
        "threshold_kind": row.threshold_kind,
        "threshold_money": money_str(row.threshold_money),
        "threshold_money_daily": money_str(row.threshold_money_daily),
        "threshold_provenance": row.threshold_provenance,
        "threshold_ratio": None if row.threshold_ratio is None else str(row.threshold_ratio),
        "threshold_state": row.threshold_state,
        "truth_tier": row.truth_tier,
        "window_end": None if row.window_end is None else format_utc(row.window_end),
        "window_kind": row.window_kind,
        "window_start": None if row.window_start is None else format_utc(row.window_start),
    }


def input_digest(project_id: uuid.UUID, as_of: datetime, rows: Sequence[SignalRow]) -> str:
    """Snapshot identity including as_of and live ledger facts."""
    ordered = sorted(rows, key=lambda row: row.seq)
    return canonical_digest(
        {
            "as_of": format_utc(as_of),
            "project_id": str(project_id),
            "ruleset_version": RULESET_VERSION,
            "signals": [signal_digest_material(row) for row in ordered],
        }
    )


def compute_counters(rows: Sequence[SignalRow]) -> Counters:
    """Count disjoint observation statuses plus independent breached rows."""
    if len(rows) != 11:
        raise OpsSignalError("assessment must contain exactly 11 classes")
    observed = sum(row.observation_status == "observed" for row in rows)
    caller = sum(row.observation_status == "caller_supplied_unverified" for row in rows)
    missing = sum(row.observation_status == "not_observed" for row in rows)
    if observed + caller + missing != 11:
        raise OpsSignalError("observation statuses must be disjoint and sum to 11")
    breached = sum(row.threshold_state == "breached" for row in rows)
    return Counters(observed, caller, missing, breached)


def evaluate_caller_threshold(sample: CallerSample, as_of: datetime) -> SignalRow:
    """Accept a complete metric+threshold sample against the transaction as_of."""
    sample = coerce_caller_sample(sample)
    start = _require_aware_utc(sample.window_start, "window_start")
    end = _require_aware_utc(sample.window_end, "window_end")
    as_of_utc = _require_aware_utc(as_of, "as_of")
    if not (start < end <= as_of_utc):
        raise OpsSignalError("sample window must satisfy window_start < window_end <= as_of")
    if sample.signal_class in RATIO_SAMPLE_CLASSES:
        if sample.metric_ratio is None or sample.threshold_ratio is None:
            raise OpsSignalError("ratio sample requires metric and threshold")
        metric_kind, threshold_kind = "ratio", "caller_ratio"
        metric_int = threshold_int = None
        metric_ratio, threshold_ratio = sample.metric_ratio, sample.threshold_ratio
        breached = metric_ratio > threshold_ratio
    else:
        if sample.metric_int is None or sample.threshold_int is None:
            raise OpsSignalError("integer sample requires metric and threshold")
        metric_kind = "milliseconds" if sample.signal_class in MS_SAMPLE_CLASSES else "count"
        threshold_kind = "caller_ms" if sample.signal_class in MS_SAMPLE_CLASSES else "caller_count"
        metric_int, threshold_int = sample.metric_int, sample.threshold_int
        metric_ratio = threshold_ratio = None
        breached = metric_int > threshold_int
    return SignalRow(
        seq=CLASS_SEQ[sample.signal_class],
        signal_class=sample.signal_class,
        observation_status="caller_supplied_unverified",
        truth_tier="caller_supplied_unverified",
        source_kind="caller_supplied",
        source_table="caller_sample",
        source_ref=None,
        source_digest=canonical_digest(sample_digest_payload(sample)),
        window_kind="caller_declared",
        window_start=start,
        window_end=end,
        reason_code="caller_threshold_breached" if breached else "caller_threshold_ok",
        threshold_provenance="caller_supplied_unverified",
        threshold_kind=threshold_kind,
        threshold_int=threshold_int,
        threshold_ratio=threshold_ratio,
        threshold_money=None,
        threshold_money_daily=None,
        metric_kind=metric_kind,
        metric_int=metric_int,
        metric_ratio=metric_ratio,
        metric_money=None,
        metric_money_daily=None,
        threshold_state="breached" if breached else "ok",
    )
