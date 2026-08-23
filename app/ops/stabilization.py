"""Pure Slice-59 stabilization-window contract. No DB, no broker, no go-live.

Records a tenant-owned assessment against an immutable §27.13 policy snapshot.
Does not close §25.4 or §26.6. ``all_criteria_passed`` is unreachable.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from app.identity import CALLER_SUPPLIED_UNVERIFIED, REQUEST_AUTHENTICATED, AuthenticatedActor

STABILIZATION_VERSION = "slice59.stabilization.v1"
IMPROVEMENT_INVENTORY_VERSION = "slice59.improvement_inventory.v1"
RULESET_VERSION = "slice59.v1"

WINDOW_STATUS = "open"
CLOCK_BASIS = "transaction_timestamp_not_production_uptime"
FOLLOW_UP_NONE = "none"
FOLLOW_UP_REQUIRED = "required_not_executed"
FOLLOW_UP_POSTURES = (FOLLOW_UP_NONE, FOLLOW_UP_REQUIRED)
ASSESSOR_PROVENANCES = (CALLER_SUPPLIED_UNVERIFIED, REQUEST_AUTHENTICATED)
REFRESH_POSTURE = "recorded_not_refreshed"

CRITERION_STATUSES = ("passed", "failed", "not_observed", "not_evaluable")
IMPROVEMENT_STATUSES = ("observed", "not_observed")
CLOSURE_RESULTS = (
    "refused_latch_active",
    "refused_unauthenticated",
    "refused_same_actor",
    "refused_incomplete_criteria",
)

DURATION_DAYS = (7, 14, 30)
WINDOW_POLICY_KEYS = (
    "duration_days",
    "owner",
    "support_owner",
    "monitored_journeys",
    "error_budget_threshold",
    "exit_criteria",
    "closure_approver",
)
EXIT_CRITERIA_KEYS = (
    "zero_open_critical_incidents_for_days",
    "error_budget_under_threshold",
    "monitoring_confirmed_active",
    "rollback_blockers_open",
    "support_handover_complete",
)
CRITERION_KEYS: tuple[tuple[int, str], ...] = (
    (1, "zero_open_critical_incidents_for_days"),
    (2, "error_budget_under_threshold"),
    (3, "monitoring_confirmed_active"),
    (4, "rollback_blockers_open"),
    (5, "support_handover_complete"),
    (6, "backup_restore_validated"),
    (7, "p95_latency_within_slo"),
    (8, "no_unresolved_security_alerts"),
)
IMPROVEMENT_CLASSES: tuple[tuple[int, str], ...] = (
    (1, "lessons_learned"),
    (2, "recurring_failure_patterns"),
    (3, "agent_evals"),
    (4, "prompt_templates"),
    (5, "domain_pack_gaps"),
    (6, "test_oracle_gaps"),
    (7, "cost_forecasts"),
    (8, "connector_reliability_scores"),
)
PASSABLE_SEQS = frozenset({5})
CRITERION_COUNT = 8
IMPROVEMENT_COUNT = 8
MAX_STRING = 200
MAX_JOURNEYS = 16
MAX_ACTOR = 200
MAX_IDEMPOTENCY = 200
MIN_AGE_HOURS = 1
MAX_AGE_HOURS = 168
HISTORY_LIMIT_DEFAULT = 50
HISTORY_LIMIT_MAX = 100
DIGEST_RE = r"^sha256:[0-9a-f]{64}$"
MONITORING_PROVIDER = "generic_monitoring_api"


class StabilizationError(ValueError):
    """Fail-closed stabilization-window contract error."""


class StabilizationIdempotencyConflict(StabilizationError):
    """Idempotency key reused with a different request digest."""


class StabilizationIdempotencyRace(StabilizationError):
    """Winner stayed invisible after bounded REPEATABLE READ retries."""


@dataclass(frozen=True)
class CriterionChild:
    """One frozen seq 1–8 criterion result. Seq 5 is the only passable row."""

    seq: int
    criterion_key: str
    status: str
    reason: str
    monitoring_snapshot_id: uuid.UUID | None = None
    rollback_verification_run_id: uuid.UUID | None = None
    handover_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ImprovementChild:
    """One frozen seq 1–8 improvement inventory row. Descriptive only."""

    seq: int
    improvement_class: str
    status: str
    reason: str
    findings_report_id: uuid.UUID | None = None
    cost_forecast_run_id: uuid.UUID | None = None
    metric_int: int | None = None
    refresh_posture: str | None = None


@dataclass(frozen=True)
class AssessorIdentity:
    """Assessor bound to TenantContext.actor when present."""

    subject: str
    actor_type: str | None
    provenance: str


@dataclass(frozen=True)
class StabilizationSnapshot:
    """Safe stabilization-window surface. Omits owner, journeys, and URLs."""

    id: uuid.UUID
    project_id: uuid.UUID
    ruleset_version: str
    status: str
    as_of: datetime
    clock_basis: str
    policy_digest: str
    monitoring_target_bound: bool
    extension_required: bool
    follow_up_posture: str
    extends_window_id: uuid.UUID | None
    passed_count: int
    failed_count: int
    not_observed_count: int
    not_evaluable_count: int
    request_digest: str
    input_digest: str
    assessor_provenance: str
    criteria: tuple[CriterionChild, ...]
    improvements: tuple[ImprovementChild, ...]


@dataclass(frozen=True)
class ClosureAttemptRecord:
    """Persisted closure refusal. Window status never changes."""

    id: uuid.UUID
    window_id: uuid.UUID
    project_id: uuid.UUID
    result_code: str


def _require_bounded(name: str, value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        raise StabilizationError(f"{name} must be a non-blank string of at most {max_chars} chars")
    stripped = value.strip()
    if not stripped or len(stripped) > max_chars:
        raise StabilizationError(f"{name} must be a non-blank string of at most {max_chars} chars")
    return stripped


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


def policy_digest(policy: Mapping[str, object]) -> str:
    """Digest of the validated policy snapshot. Copied verbatim, never a pointer."""
    return canonical_digest(dict(policy))


def request_digest(
    *,
    project_id: uuid.UUID,
    extends_window_id: uuid.UUID | None,
    assessor_subject: str,
    assessor_actor_type: str | None,
    assessor_provenance: str,
) -> str:
    """Idempotency identity. Excludes ``as_of`` and live observations."""
    return canonical_digest(
        {
            "assessor_actor_type": assessor_actor_type,
            "assessor_provenance": assessor_provenance,
            "assessor_subject": assessor_subject,
            "extends_window_id": str(extends_window_id) if extends_window_id else None,
            "project_id": str(project_id),
            "ruleset_version": RULESET_VERSION,
        }
    )


def _criterion_tuple(child: CriterionChild) -> dict[str, object]:
    return {
        "criterion_key": child.criterion_key,
        "handover_id": str(child.handover_id) if child.handover_id else None,
        "monitoring_snapshot_id": (
            str(child.monitoring_snapshot_id) if child.monitoring_snapshot_id else None
        ),
        "reason": child.reason,
        "rollback_verification_run_id": (
            str(child.rollback_verification_run_id) if child.rollback_verification_run_id else None
        ),
        "seq": child.seq,
        "status": child.status,
    }


def _improvement_tuple(child: ImprovementChild) -> dict[str, object]:
    return {
        "cost_forecast_run_id": (
            str(child.cost_forecast_run_id) if child.cost_forecast_run_id else None
        ),
        "findings_report_id": str(child.findings_report_id) if child.findings_report_id else None,
        "improvement_class": child.improvement_class,
        "metric_int": child.metric_int,
        "reason": child.reason,
        "refresh_posture": child.refresh_posture,
        "seq": child.seq,
        "status": child.status,
    }


def input_digest(
    *,
    as_of: datetime,
    policy_digest_value: str,
    monitoring_max_age_hours: int,
    deployment_max_age_hours: int,
    criteria: Sequence[CriterionChild],
    improvements: Sequence[ImprovementChild],
) -> str:
    """Snapshot identity over the DB clock, policy, ages, and both child sets."""
    return canonical_digest(
        {
            "as_of": as_of.isoformat(),
            "criteria": [_criterion_tuple(child) for child in criteria],
            "deployment_max_age_hours": deployment_max_age_hours,
            "improvements": [_improvement_tuple(child) for child in improvements],
            "monitoring_max_age_hours": monitoring_max_age_hours,
            "policy_digest": policy_digest_value,
        }
    )


def validate_actor_label(value: str) -> str:
    """Return a stripped actor label or raise."""
    return _require_bounded("actor", value, MAX_ACTOR)


def validate_idempotency_key(value: str) -> str:
    """Return a stripped idempotency key or raise."""
    if not isinstance(value, str):
        raise StabilizationError("idempotency_key must be a string")
    key = value.strip()
    if not key or len(key) > MAX_IDEMPOTENCY:
        raise StabilizationError("idempotency_key must be non-blank and <=200 characters")
    return key


def validate_history_limit(limit: int) -> int:
    """Return a history limit in ``1..100`` or raise."""
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise StabilizationError("history limit must be an int")
    if not 1 <= limit <= HISTORY_LIMIT_MAX:
        raise StabilizationError("history limit must be between 1 and 100")
    return limit


def validate_age_hours(value: object, *, name: str) -> int:
    """Return a recorded freshness limit in ``1..168`` or raise."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise StabilizationError(f"{name} must be an int between 1 and 168")
    if not MIN_AGE_HOURS <= value <= MAX_AGE_HOURS:
        raise StabilizationError(f"{name} must be an int between 1 and 168")
    return value


def assessor_identity(actor: AuthenticatedActor | None, caller_label: str) -> AssessorIdentity:
    """Derive assessor fields from TenantContext.actor, else the caller label."""
    label = validate_actor_label(caller_label)
    if actor is not None:
        return AssessorIdentity(
            subject=actor.subject,
            actor_type=actor.actor_type,
            provenance=REQUEST_AUTHENTICATED,
        )
    return AssessorIdentity(subject=label, actor_type=None, provenance=CALLER_SUPPLIED_UNVERIFIED)


def _policy_string(value: object) -> str:
    if not isinstance(value, str):
        raise StabilizationError("no_window_declaration")
    stripped = value.strip()
    if not stripped or len(stripped) > MAX_STRING:
        raise StabilizationError("no_window_declaration")
    return stripped


def validate_window_policy(window: object) -> dict[str, object]:
    """Return a cleaned §27.13 snapshot or raise ``no_window_declaration``.

    Template YAML is never parsed. Unknown keys fail closed. The error-budget
    string is copied verbatim and never parsed numerically.
    """
    if not isinstance(window, dict):
        raise StabilizationError("no_window_declaration")
    if set(window) != set(WINDOW_POLICY_KEYS):
        raise StabilizationError("no_window_declaration")
    duration = window["duration_days"]
    if not isinstance(duration, int) or isinstance(duration, bool) or duration not in DURATION_DAYS:
        raise StabilizationError("no_window_declaration")
    journeys = window["monitored_journeys"]
    if not isinstance(journeys, list) or len(journeys) > MAX_JOURNEYS:
        raise StabilizationError("no_window_declaration")
    cleaned_journeys = [_policy_string(item) for item in journeys]
    exit_criteria = window["exit_criteria"]
    if not isinstance(exit_criteria, dict) or set(exit_criteria) != set(EXIT_CRITERIA_KEYS):
        raise StabilizationError("no_window_declaration")
    streak = exit_criteria["zero_open_critical_incidents_for_days"]
    if not isinstance(streak, int) or isinstance(streak, bool) or not 1 <= streak <= 30:
        raise StabilizationError("no_window_declaration")
    rollback_open = exit_criteria["rollback_blockers_open"]
    if not isinstance(rollback_open, int) or isinstance(rollback_open, bool) or rollback_open != 0:
        raise StabilizationError("no_window_declaration")
    for flag_key in (
        "error_budget_under_threshold",
        "monitoring_confirmed_active",
        "support_handover_complete",
    ):
        if not isinstance(exit_criteria[flag_key], bool):
            raise StabilizationError("no_window_declaration")
    return {
        "closure_approver": _policy_string(window["closure_approver"]),
        "duration_days": duration,
        "error_budget_threshold": _policy_string(window["error_budget_threshold"]),
        "exit_criteria": {
            "error_budget_under_threshold": exit_criteria["error_budget_under_threshold"],
            "monitoring_confirmed_active": exit_criteria["monitoring_confirmed_active"],
            "rollback_blockers_open": 0,
            "support_handover_complete": exit_criteria["support_handover_complete"],
            "zero_open_critical_incidents_for_days": streak,
        },
        "monitored_journeys": cleaned_journeys,
        "owner": _policy_string(window["owner"]),
        "support_owner": _policy_string(window["support_owner"]),
    }
