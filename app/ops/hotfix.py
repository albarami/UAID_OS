"""Pure Slice-58 hotfix-intent contract. No DB, no git, no deploy, no rollback.

Records intent under one policy snapshot. Does not close §26.6.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from app.ops.incidents import TERMINAL_STATUSES
from app.policy.engine import Decision

HOTFIX_INTENT_VERSION = "slice58.hotfix_intent.v1"
HOTFIX_PLAN_VERSION = "slice58.hotfix_plan.v1"
RULESET_VERSION = "slice58.v1"

ACTIONS: tuple[tuple[int, str, str], ...] = (
    (3, "create_patch_branch", "create_branches"),
    (4, "open_hotfix_pr", "open_pull_requests"),
    (5, "deploy_staging_hotfix", "deploy_staging"),
    (6, "deploy_production_hotfix", "deploy_production"),
    (7, "rollback_production", "deploy_production"),
)
ACTION_COUNT = 5
MATRIX_ACTIONS: tuple[str, ...] = tuple(dict.fromkeys(matrix for _seq, _action, matrix in ACTIONS))
PLAN_KINDS = ("patch_branch", "hotfix_pr")
POLICY_DECISIONS = ("allow", "deny", "needs_approval")
EXECUTION_POSTURES = (
    "local_branch_plan_written",
    "local_pr_plan_written",
    "recorded_not_executed",
    "staging_not_executed",
    "production_not_executed",
)
REASON_CODES = (
    "plan_written",
    "plan_denied_by_policy",
    "plan_needs_approval",
    "branch_plan_required",
    "no_deploy_actuator",
    "production_not_executed",
)
GATE10_CONTEXT_KEYS = (
    "scope_resolved",
    "core_present",
    "core_reaudited",
    "repo_binding_agreed",
    "staging_target_valid",
    "staging_snapshot_present",
    "staging_snapshot_available",
    "staging_snapshot_fresh",
    "run_present",
    "attempt_failed",
    "artifact_trusted",
    "binding_current",
    "phase_coverage_complete",
    "evidence_consistent",
    "drill_passed",
    "gate_eligible",
    "phase_count",
    "execution_observation",
)
DIGEST_RE = r"^sha256:[0-9a-f]{64}$"
MAX_ACTOR = 200
MAX_IDEMPOTENCY = 200
MAX_INTENDED_REF = 200
HISTORY_LIMIT_DEFAULT = 50
HISTORY_LIMIT_MAX = 100


class HotfixError(ValueError):
    """Fail-closed hotfix-intent contract error."""


class HotfixIdempotencyConflict(HotfixError):
    """Idempotency key reused with a different request digest."""


class HotfixIdempotencyRace(HotfixError):
    """Winner stayed invisible after bounded READ COMMITTED retries."""


@dataclass(frozen=True)
class HotfixChild:
    """One frozen seq 3–7 result. Not an actuator."""

    seq: int
    action: str
    matrix_action: str
    policy_decision: str
    execution_posture: str
    reason_code: str
    plan_id: uuid.UUID | None = None
    plan_kind: str | None = None


@dataclass(frozen=True)
class HotfixIntentSnapshot:
    """Safe hotfix-intent surface. Omits intended_ref."""

    id: uuid.UUID
    project_id: uuid.UUID
    incident_id: uuid.UUID
    ruleset_version: str
    request_digest: str
    policy_present: bool
    policy_id: uuid.UUID | None
    autonomy_level: int | None
    policy_input_digest: str
    rollback_verification_run_id: uuid.UUID | None
    emergency_control_binding_id: uuid.UUID | None
    emergency_rollback_authorization_id: uuid.UUID | None
    rollback_run_present: bool
    standing_binding_present: bool
    rollback_authorization_present: bool
    actions: tuple[HotfixChild, ...]


def _require_bounded(name: str, value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        raise HotfixError(f"{name} must be a non-blank string of at most {max_chars} chars")
    stripped = value.strip()
    if not stripped or len(stripped) > max_chars:
        raise HotfixError(f"{name} must be a non-blank string of at most {max_chars} chars")
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


def policy_input_digest(
    *,
    policy_present: bool,
    policy_id: uuid.UUID | None,
    autonomy_level: int | None,
    overrides: Mapping[str, object],
) -> str:
    """Hash the full policy snapshot, including override values."""
    return canonical_digest(
        {
            "autonomy_level": autonomy_level,
            "overrides": dict(overrides),
            "policy_id": str(policy_id) if policy_id is not None else None,
            "policy_present": policy_present,
            "ruleset_version": RULESET_VERSION,
        }
    )


def request_digest(incident_id: uuid.UUID) -> str:
    """Idempotency digest. Excludes clocks."""
    return canonical_digest({"incident_id": str(incident_id), "ruleset_version": RULESET_VERSION})


def decision_snapshot_payload(decisions: Mapping[str, Decision]) -> dict[str, str]:
    """Persist the four unique matrix actions from one snapshot."""
    missing = [action for action in MATRIX_ACTIONS if action not in decisions]
    if missing:
        raise HotfixError(f"missing policy decision for {missing[0]!r}")
    payload: dict[str, str] = {}
    for action in MATRIX_ACTIONS:
        decision = decisions[action]
        if not isinstance(decision, Decision):
            raise HotfixError(f"invalid policy decision for {action!r}")
        payload[action] = decision.value
    return payload


def rollback_coverage_digest(coverage: object) -> str:
    """Canonical digest of the gate-#10 context keys."""
    payload: dict[str, object] = {key: getattr(coverage, key) for key in GATE10_CONTEXT_KEYS}
    return canonical_digest(payload)


def gate10_conjunction_passed(coverage: object) -> bool:
    """True only when the complete gate-#10 ladder would pass.

    Mirrors ``production_autonomy.py:1188-1285``. Does not trust
    ``coverage.gate_eligible`` alone.
    """
    scope_resolved = bool(getattr(coverage, "scope_resolved"))
    core_present = bool(getattr(coverage, "core_present"))
    core_reaudited = bool(getattr(coverage, "core_reaudited"))
    repo_binding_agreed = bool(getattr(coverage, "repo_binding_agreed"))
    staging_target_valid = bool(getattr(coverage, "staging_target_valid"))
    staging_snapshot_present = bool(getattr(coverage, "staging_snapshot_present"))
    staging_snapshot_available = bool(getattr(coverage, "staging_snapshot_available"))
    staging_snapshot_fresh = bool(getattr(coverage, "staging_snapshot_fresh"))
    run_present = bool(getattr(coverage, "run_present"))
    attempt_failed = bool(getattr(coverage, "attempt_failed"))
    artifact_trusted = bool(getattr(coverage, "artifact_trusted"))
    binding_current = bool(getattr(coverage, "binding_current"))
    phase_coverage_complete = bool(getattr(coverage, "phase_coverage_complete"))
    evidence_consistent = bool(getattr(coverage, "evidence_consistent"))
    drill_passed = bool(getattr(coverage, "drill_passed"))
    gate_eligible = bool(getattr(coverage, "gate_eligible"))
    phase_count = int(getattr(coverage, "phase_count"))
    execution_observation = getattr(coverage, "execution_observation")
    if not scope_resolved:
        return False
    if not core_present:
        return False
    if not core_reaudited:
        return False
    if not repo_binding_agreed:
        return False
    if not staging_target_valid:
        return False
    if not staging_snapshot_present:
        return False
    if not staging_snapshot_available or not staging_snapshot_fresh:
        return False
    if not run_present:
        return False
    if attempt_failed:
        return False
    if not artifact_trusted or execution_observation != "connector_observed_ci":
        return False
    if not binding_current:
        return False
    if not phase_coverage_complete or phase_count != 5:
        return False
    if not evidence_consistent:
        return False
    if not drill_passed or not gate_eligible:
        return False
    return True


def authorization_matches(
    *,
    binding_id: uuid.UUID,
    candidate_id: uuid.UUID,
    evidence_pack_id: uuid.UUID,
    rollback_run_id: uuid.UUID,
    binding_digest: str,
    authorization_binding_id: uuid.UUID,
    authorization_candidate_id: uuid.UUID,
    authorization_pack_id: uuid.UUID,
    authorization_run_id: uuid.UUID,
    authorization_digest: str,
    result_code: str,
) -> bool:
    """True only when the authorization row is the selected current-release graph."""
    return (
        result_code == "authorized_not_executed"
        and authorization_binding_id == binding_id
        and authorization_candidate_id == candidate_id
        and authorization_pack_id == evidence_pack_id
        and authorization_run_id == rollback_run_id
        and authorization_digest == binding_digest
    )


def incident_is_evaluable(status: str) -> bool:
    """Non-terminal incidents only."""
    return status not in TERMINAL_STATUSES


def validate_actor_label(value: str) -> str:
    """Return a stripped actor label or raise."""
    return _require_bounded("actor", value, MAX_ACTOR)


def validate_idempotency_key(value: str) -> str:
    """Return a stripped idempotency key or raise."""
    if not isinstance(value, str):
        raise HotfixError("idempotency_key must be a string")
    key = value.strip()
    if not key or len(key) > MAX_IDEMPOTENCY:
        raise HotfixError("idempotency_key must be non-blank and <=200 characters")
    return key


def validate_history_limit(limit: int) -> int:
    """Return a history limit in ``1..100`` or raise."""
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise HotfixError("history limit must be an int")
    if not 1 <= limit <= HISTORY_LIMIT_MAX:
        raise HotfixError("history limit must be between 1 and 100")
    return limit


def local_intended_ref(plan_kind: str, incident_id: uuid.UUID) -> str:
    """Local plan label. Not a created git branch or GitHub PR."""
    if plan_kind not in PLAN_KINDS:
        raise HotfixError(f"unknown plan_kind: {plan_kind!r}")
    return f"local:{plan_kind}:{incident_id.hex[:8]}"


def _decision_value(decision: Decision) -> str:
    return decision.value


def _policy_first(decision: Decision, *, allow_posture: str, allow_reason: str) -> tuple[str, str]:
    if decision is Decision.DENY:
        return "recorded_not_executed", "plan_denied_by_policy"
    if decision is Decision.NEEDS_APPROVAL:
        return "recorded_not_executed", "plan_needs_approval"
    return allow_posture, allow_reason


def evaluate_hotfix_actions(decisions: Mapping[str, Decision]) -> tuple[HotfixChild, ...]:
    """Map one locked snapshot onto five frozen seq 3–7 results.

    Policy precedence is applied before actuator-absence residuals.
    """
    snapshot = decision_snapshot_payload(decisions)
    branch_allowed = snapshot["create_branches"] == "allow"
    children: list[HotfixChild] = []
    for seq, action, matrix_action in ACTIONS:
        decision = decisions[matrix_action]
        value = _decision_value(decision)
        if seq == 3:
            posture, reason = _policy_first(
                decision,
                allow_posture="local_branch_plan_written",
                allow_reason="plan_written",
            )
            children.append(
                HotfixChild(
                    seq=seq,
                    action=action,
                    matrix_action=matrix_action,
                    policy_decision=value,
                    execution_posture=posture,
                    reason_code=reason,
                )
            )
            continue
        if seq == 4:
            if decision is Decision.DENY:
                posture, reason = "recorded_not_executed", "plan_denied_by_policy"
            elif decision is Decision.NEEDS_APPROVAL:
                posture, reason = "recorded_not_executed", "plan_needs_approval"
            elif not branch_allowed:
                posture, reason = "recorded_not_executed", "branch_plan_required"
            else:
                posture, reason = "local_pr_plan_written", "plan_written"
            children.append(
                HotfixChild(
                    seq=seq,
                    action=action,
                    matrix_action=matrix_action,
                    policy_decision=value,
                    execution_posture=posture,
                    reason_code=reason,
                )
            )
            continue
        if seq == 5:
            posture, reason = _policy_first(
                decision,
                allow_posture="staging_not_executed",
                allow_reason="no_deploy_actuator",
            )
        else:
            posture, reason = _policy_first(
                decision,
                allow_posture="production_not_executed",
                allow_reason="production_not_executed",
            )
        children.append(
            HotfixChild(
                seq=seq,
                action=action,
                matrix_action=matrix_action,
                policy_decision=value,
                execution_posture=posture,
                reason_code=reason,
            )
        )
    return tuple(children)


def bind_plans(
    children: Sequence[HotfixChild],
    *,
    branch_plan_id: uuid.UUID | None,
    pr_plan_id: uuid.UUID | None,
) -> tuple[HotfixChild, ...]:
    """Attach already-inserted local plans. Seq 5–7 stay plan-less."""
    bound: list[HotfixChild] = []
    for child in children:
        if child.seq == 3 and child.reason_code == "plan_written":
            if branch_plan_id is None:
                raise HotfixError("seq-3 ALLOW requires a patch_branch plan")
            bound.append(replace(child, plan_id=branch_plan_id, plan_kind="patch_branch"))
        elif child.seq == 4 and child.reason_code == "plan_written":
            if pr_plan_id is None:
                raise HotfixError("seq-4 ALLOW with a branch plan requires a hotfix_pr plan")
            bound.append(replace(child, plan_id=pr_plan_id, plan_kind="hotfix_pr"))
        else:
            bound.append(child)
    return tuple(bound)
