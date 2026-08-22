"""Pure §25.2 incident workflow contract (Slice 57). No DB, no I/O.

Records a tenant-owned incident ledger, authorized local tickets, and
prescriptions. Does not diagnose logs, write Jira, or execute hotfixes.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from app.policy.engine import Decision

INCIDENT_CONTRACT_VERSION = "slice57.incidents.v1"
ACTION_EVAL_VERSION = "slice57.action_eval.v1"
RULESET_VERSION = "slice57.v1"

SEVERITIES = ("low", "medium", "high", "critical")
CATEGORIES = (
    "availability",
    "security",
    "error",
    "cost",
    "data_quality",
    "other",
)
STATUSES = ("open", "investigating", "mitigated", "resolved", "superseded")
TERMINAL_STATUSES = ("resolved", "superseded")
OPEN_WORKFLOW_STATUSES = tuple(status for status in STATUSES if status not in TERMINAL_STATUSES)
_TRANSITIONS = {
    ("open", "investigating"),
    ("investigating", "mitigated"),
    ("mitigated", "resolved"),
    ("mitigated", "superseded"),
}

PROVENANCES = ("caller_supplied_unverified", "request_authenticated")
HANDOVER_STATUSES = ("recorded_complete", "recorded_incomplete")
TICKET_KINDS = ("bug",)
TICKET_DELIVERIES = ("local_record",)
POLICY_DECISIONS = ("allow", "deny", "needs_approval", "not_evaluated")
EXECUTION_POSTURES = ("local_ticket_written", "recorded_not_executed")

ACTIONS: tuple[tuple[int, str, str], ...] = (
    (1, "create_bug_ticket", "create_project_tasks"),
    (2, "diagnose_log_error", "none"),
    (3, "create_patch_branch", "create_branches"),
    (4, "open_hotfix_pr", "open_pull_requests"),
    (5, "deploy_staging_hotfix", "deploy_staging"),
    (6, "deploy_production_hotfix", "deploy_production"),
    (7, "rollback_production", "deploy_production"),
)
ACTION_COUNT = 7
GATED_MATRIX_ACTIONS: tuple[str, ...] = tuple(
    dict.fromkeys(matrix for seq, _action, matrix in ACTIONS if seq != 2)
)

REASON_CODES = (
    "ticket_written",
    "ticket_denied_by_policy",
    "no_log_source",
    "deferred_slice58",
    "production_not_executed",
)

MAX_SUMMARY = 2000
MAX_DETAIL = 8000
MAX_ACTOR = 200
MAX_IDEMPOTENCY = 200
HISTORY_LIMIT_DEFAULT = 50
HISTORY_LIMIT_MAX = 100
DIGEST_RE = r"^sha256:[0-9a-f]{64}$"


class IncidentError(ValueError):
    """Fail-closed incident contract error."""


class IncidentIdempotencyConflict(IncidentError):
    """Idempotency key reused with a different request digest."""


class IncidentIdempotencyRace(IncidentError):
    """REPEATABLE READ winner stayed invisible after bounded retries."""


@dataclass(frozen=True)
class IncidentPayload:
    """Caller-supplied unverified incident facts. Not a production incident."""

    category: str
    severity: str
    summary: str
    detail: str | None = None
    source_signal_id: uuid.UUID | None = None
    pm_issue_mapping_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ActionChild:
    """One frozen §25.2 prescription row. Not an actuator."""

    seq: int
    action: str
    matrix_action: str
    policy_decision: str
    execution_posture: str
    reason_code: str
    ticket_id: uuid.UUID | None = None


@dataclass(frozen=True)
class PolicySnapshot:
    """Exact policy inputs hashed into ``policy_input_digest``."""

    policy_present: bool
    policy_id: uuid.UUID | None
    autonomy_level: int | None
    overrides: Mapping[str, object]


@dataclass(frozen=True)
class HandoverPayload:
    """Presence-only support handover. Not Slice 59 closure or a human signature."""

    handed_over_by: str
    received_by: str
    status: str


@dataclass(frozen=True)
class IncidentSnapshot:
    """Safe incident surface. Omits summary/detail; not a diagnosed-complete flag."""

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    category: str
    severity: str
    ruleset_version: str
    request_digest: str
    source_signal_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    latest_evaluation_id: uuid.UUID | None
    actions: tuple[ActionChild, ...]


@dataclass(frozen=True)
class ActionPrescriptionSet:
    """One seven-row §25.2 evaluation. Prescriptions are not actuators."""

    evaluation_id: uuid.UUID
    incident_id: uuid.UUID
    policy_present: bool
    policy_id: uuid.UUID | None
    autonomy_level: int | None
    policy_input_digest: str
    actions: tuple[ActionChild, ...]


@dataclass(frozen=True)
class HandoverRecord:
    """Recorded handover presence. Request-authenticated is key custody only."""

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    recorded_by_provenance: str
    handed_over_by: str
    received_by: str


def _require_bounded(name: str, value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        raise IncidentError(f"{name} must be a non-blank string of at most {max_chars} chars")
    stripped = value.strip()
    if not stripped or len(stripped) > max_chars:
        raise IncidentError(f"{name} must be a non-blank string of at most {max_chars} chars")
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


def policy_input_digest(snapshot: PolicySnapshot) -> str:
    """Hash the full policy snapshot, including override values."""
    return canonical_digest(
        {
            "autonomy_level": snapshot.autonomy_level,
            "overrides": dict(snapshot.overrides),
            "policy_id": str(snapshot.policy_id) if snapshot.policy_id is not None else None,
            "policy_present": snapshot.policy_present,
            "ruleset_version": RULESET_VERSION,
        }
    )


def request_digest(payload: IncidentPayload) -> str:
    """Idempotency digest. Excludes clocks."""
    return canonical_digest(
        {
            "category": payload.category,
            "detail": payload.detail,
            "pm_issue_mapping_id": (
                str(payload.pm_issue_mapping_id) if payload.pm_issue_mapping_id else None
            ),
            "severity": payload.severity,
            "source_signal_id": (
                str(payload.source_signal_id) if payload.source_signal_id else None
            ),
            "summary": payload.summary,
        }
    )


def validate_idempotency_key(value: str) -> str:
    """Return a stripped idempotency key or raise."""
    if not isinstance(value, str):
        raise IncidentError("idempotency_key must be a string")
    key = value.strip()
    if not key or len(key) > MAX_IDEMPOTENCY:
        raise IncidentError("idempotency_key must be non-blank and <=200 characters")
    return key


def validate_history_limit(limit: int) -> int:
    """Return a history limit in ``1..100`` or raise."""
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise IncidentError("history limit must be an int")
    if not 1 <= limit <= HISTORY_LIMIT_MAX:
        raise IncidentError("history limit must be between 1 and 100")
    return limit


def validate_new_incident(payload: IncidentPayload) -> IncidentPayload:
    """Fail-closed create validator. ``accepted`` is not a status."""
    if payload.category not in CATEGORIES:
        raise IncidentError(f"unknown category: {payload.category!r}")
    if payload.severity not in SEVERITIES:
        raise IncidentError(f"unknown severity: {payload.severity!r}")
    summary = _require_bounded("summary", payload.summary, MAX_SUMMARY)
    detail = payload.detail
    if payload.category == "other":
        detail = _require_bounded("detail", detail, MAX_DETAIL)
    elif detail is not None:
        detail = _require_bounded("detail", detail, MAX_DETAIL)
    if payload.source_signal_id is not None and not isinstance(payload.source_signal_id, uuid.UUID):
        raise IncidentError("source_signal_id must be a UUID")
    if payload.pm_issue_mapping_id is not None and not isinstance(
        payload.pm_issue_mapping_id, uuid.UUID
    ):
        raise IncidentError("pm_issue_mapping_id must be a UUID")
    return IncidentPayload(
        category=payload.category,
        severity=payload.severity,
        summary=summary,
        detail=detail,
        source_signal_id=payload.source_signal_id,
        pm_issue_mapping_id=payload.pm_issue_mapping_id,
    )


def validate_transition(current: str, target: str) -> None:
    """Refuse skips, ``accepted``, and reverse transitions."""
    if current not in STATUSES or target not in STATUSES:
        raise IncidentError("unknown incident status")
    if current == target:
        raise IncidentError("same-status updates are not a transition")
    if (current, target) not in _TRANSITIONS:
        raise IncidentError(f"illegal transition {current!r} -> {target!r}")


def validate_handover(
    *,
    handed_over_by: str,
    received_by: str,
    status: str,
    provenance: str,
    actor_subject: str | None,
) -> None:
    """Fail-closed handover validator. Key custody is not a human signature."""
    _require_bounded("handed_over_by", handed_over_by, MAX_ACTOR)
    _require_bounded("received_by", received_by, MAX_ACTOR)
    if status not in HANDOVER_STATUSES:
        raise IncidentError(f"unknown handover status: {status!r}")
    if provenance not in PROVENANCES:
        raise IncidentError(f"unknown provenance: {provenance!r}")
    if provenance == "request_authenticated":
        if actor_subject is None or handed_over_by != actor_subject:
            raise IncidentError("request_authenticated handover requires matching principal")


def _decision_value(decision: Decision) -> str:
    return {
        Decision.ALLOW: "allow",
        Decision.DENY: "deny",
        Decision.NEEDS_APPROVAL: "needs_approval",
    }[decision]


def evaluate_actions(decisions: Mapping[str, Decision]) -> tuple[ActionChild, ...]:
    """Map real ``decision_for`` results onto seven frozen prescriptions.

    Authorization is not computed here. Seq 2 stays unevaluated.
    """
    for matrix in GATED_MATRIX_ACTIONS:
        if matrix not in decisions:
            raise IncidentError(f"missing policy decision for {matrix!r}")
        if not isinstance(decisions[matrix], Decision):
            raise IncidentError(f"invalid policy decision for {matrix!r}")
    children: list[ActionChild] = []
    for seq, action, matrix_action in ACTIONS:
        if seq == 2:
            children.append(
                ActionChild(
                    seq=2,
                    action=action,
                    matrix_action="none",
                    policy_decision="not_evaluated",
                    execution_posture="recorded_not_executed",
                    reason_code="no_log_source",
                )
            )
            continue
        value = _decision_value(decisions[matrix_action])
        if seq == 1:
            allowed = value == "allow"
            children.append(
                ActionChild(
                    seq=1,
                    action=action,
                    matrix_action=matrix_action,
                    policy_decision=value,
                    execution_posture=(
                        "local_ticket_written" if allowed else "recorded_not_executed"
                    ),
                    reason_code="ticket_written" if allowed else "ticket_denied_by_policy",
                )
            )
            continue
        reason = "production_not_executed" if seq in {6, 7} else "deferred_slice58"
        children.append(
            ActionChild(
                seq=seq,
                action=action,
                matrix_action=matrix_action,
                policy_decision=value,
                execution_posture="recorded_not_executed",
                reason_code=reason,
            )
        )
    return tuple(children)


def ticket_should_exist(children: Sequence[ActionChild]) -> bool:
    """True when seq-1 is ALLOW and a local ticket must be written first."""
    first = next(child for child in children if child.seq == 1)
    return first.policy_decision == "allow"


def validate_actor_label(value: str) -> str:
    """Return a stripped actor label or raise."""
    return _require_bounded("actor", value, MAX_ACTOR)


def bind_seq1_ticket(
    children: Sequence[ActionChild], ticket_id: uuid.UUID | None
) -> tuple[ActionChild, ...]:
    """Attach the already-inserted ticket to seq-1 ALLOW, else leave NULL."""
    bound: list[ActionChild] = []
    for child in children:
        if child.seq == 1 and child.policy_decision == "allow":
            if ticket_id is None:
                raise IncidentError("seq-1 ALLOW requires a ticket id")
            bound.append(replace(child, ticket_id=ticket_id))
        else:
            bound.append(child)
    return tuple(bound)
