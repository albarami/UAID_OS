"""Pure Slice-53 production pre-approval contracts.

This module validates and hashes *recorded* policy plus application-authenticated key-custody
evidence.  It never upgrades either source into a human signature or production authority and it
never performs a deployment.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from app.identity import AuthenticatedActor, REQUEST_AUTHENTICATED

POLICY_CONTRACT_VERSION = "slice53.production_approval_policy.v1"
CONDITIONS_CONTRACT_VERSION = "slice53.production_preapproval_conditions.v1"
PREAPPROVAL_CONTRACT_VERSION = "slice53.production_preapproval.v1"
POLICY_SOURCE_PROVENANCE = "caller_supplied_unverified_structured_approval_policy"

MAX_APPROVERS = 100
MAX_SUBJECT_BYTES = 255
MAX_VALIDITY_HOURS = 24

_POLICY_KEYS = {
    "approval_channel",
    "daily_digest_time",
    "batch_low_risk_questions",
    "realtime_for",
    "non_response_policy",
    "approvers",
}
_REALTIME_FOR = (
    "production_deployment",
    "security_exception",
    "cost_overrun",
    "data_access",
    "legal_or_regulatory_decision",
)
_NON_RESPONSE = {
    "low_risk": "proceed_with_safe_assumption_after_24h",
    "medium_risk": "pause_affected_work_after_24h",
    "high_risk": "block_until_approval",
    "production": "block_until_approval",
}
_CHECKLIST_KEYS = {"product", "engineering", "ai_and_data", "security", "operations", "governance"}
_GOVERNANCE = {
    "evidence_pack_complete": "required",
    "approval_events_recorded": "required",
    "separation_of_duties_confirmed": "required",
    "open_issues_have_risk_acceptance": "required_if_any_open_issues",
}
_TRUTH_KEYS = {
    "approved",
    "verified",
    "trusted",
    "eligible",
    "current",
    "passed",
    "gate",
    "authority",
    "human_signed",
}
_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")


class ProductionApprovalContractError(ValueError):
    """A recorded policy, identity, binding, or timestamp is outside the ruled contract."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProductionApprovalContractError("value is not canonical JSON") from exc


def canonical_digest(value: object) -> str:
    """SHA-256 over sorted-key UTF-8 canonical JSON, prefixed with the algorithm name."""
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def ordered_value_digest(values: Sequence[str]) -> str:
    """DB-reproducible SHA-256 over an ordered, bounded set of already-normalized values."""
    if any(not isinstance(value, str) or not value for value in values):
        raise ProductionApprovalContractError("ordered digest values must be non-blank strings")
    return "sha256:" + hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def subject_digest(subject: str) -> str:
    """One-way exact principal-subject digest; the source principal is never persisted here."""
    if not isinstance(subject, str) or not subject.strip():
        raise ProductionApprovalContractError("principal subject must be non-blank")
    if len(subject.encode("utf-8")) > MAX_SUBJECT_BYTES:
        raise ProductionApprovalContractError("principal subject exceeds 255 bytes")
    return canonical_digest({"principal_subject": subject})


def idempotency_digest(key: str) -> str:
    if not isinstance(key, str) or not key.strip() or len(key.encode("utf-8")) > 128:
        raise ProductionApprovalContractError("idempotency key must be 1..128 bytes")
    return canonical_digest({"idempotency_key": key})


def autonomy_policy_digest(
    *, policy_id: object, autonomy_level: int, overrides: Mapping[str, object], updated_at: datetime
) -> str:
    timestamp = _require_aware_utc(updated_at, "autonomy policy updated_at")
    return canonical_digest(
        {
            "policy_id": str(policy_id),
            "autonomy_level": autonomy_level,
            "overrides": dict(overrides),
            "updated_at": timestamp.isoformat().replace("+00:00", "Z"),
        }
    )


def _reject_truth_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ProductionApprovalContractError("policy keys must be strings")
            if key.lower() in _TRUTH_KEYS:
                raise ProductionApprovalContractError("caller truth fields are forbidden")
            _reject_truth_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_truth_fields(child)


def _exact_keys(value: object, required: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != required:
        raise ProductionApprovalContractError(f"{label} field set does not match the contract")
    return value


@dataclass(frozen=True)
class RecordedProductionApprovalPolicy:
    policy_contract_version: str
    source_provenance: str
    policy_digest: str
    checklist_digest: str
    approval_channel: str
    production_realtime: bool
    production_nonresponse_code: str
    governance_requirements_digest: str
    approver_subject_hashes: tuple[str, ...]

    @property
    def approver_count(self) -> int:
        return len(self.approver_subject_hashes)


def parse_recorded_policy(
    policy: Mapping[str, object], checklist: Mapping[str, object]
) -> RecordedProductionApprovalPolicy:
    """Validate the exact ruled template-20/template-23 projection.

    The result remains explicitly caller-supplied structured policy; validation is not an authority
    upgrade.  The checked-in pipe placeholder is intentionally not a live channel.
    """
    _reject_truth_fields(policy)
    _reject_truth_fields(checklist)
    p = _exact_keys(policy, _POLICY_KEYS, "human_approval_policy")
    c = _exact_keys(checklist, _CHECKLIST_KEYS, "go_live_checklist")

    if p["approval_channel"] != "dashboard":
        raise ProductionApprovalContractError("production approval channel must be dashboard")
    if not isinstance(p["daily_digest_time"], str) or not _TIME.fullmatch(p["daily_digest_time"]):
        raise ProductionApprovalContractError("daily_digest_time must be HH:MM")
    if p["batch_low_risk_questions"] is not True:
        raise ProductionApprovalContractError("batch_low_risk_questions must match the canonical policy")
    realtime = p["realtime_for"]
    if not isinstance(realtime, list) or tuple(realtime) != _REALTIME_FOR:
        raise ProductionApprovalContractError("realtime_for must match the canonical ordered codes")
    if p["non_response_policy"] != _NON_RESPONSE:
        raise ProductionApprovalContractError("non_response_policy must match canonical codes")

    approvers = p["approvers"]
    if not isinstance(approvers, list) or not 1 <= len(approvers) <= MAX_APPROVERS:
        raise ProductionApprovalContractError("approvers must contain 1..100 exact principals")
    subject_hashes: list[str] = []
    for subject in approvers:
        if not isinstance(subject, str):
            raise ProductionApprovalContractError("approver subjects must be strings")
        lowered = subject.strip().lower()
        if (
            lowered in {"*", "all", "any", "any admin"}
            or lowered.startswith(("role:", "group:"))
            or "|" in subject
            or "*" in subject
        ):
            raise ProductionApprovalContractError("wildcard, role, and group approvers are unsupported")
        subject_hashes.append(subject_digest(subject))
    if len(set(subject_hashes)) != len(subject_hashes):
        raise ProductionApprovalContractError("approvers must be unique exact principals")

    for section in ("product", "engineering", "ai_and_data", "security", "operations"):
        if c[section] != {}:
            raise ProductionApprovalContractError(f"{section} must match the canonical empty object")
    governance = _exact_keys(c["governance"], set(_GOVERNANCE), "governance")
    if dict(governance) != _GOVERNANCE:
        raise ProductionApprovalContractError("governance codes must match the canonical checklist")

    return RecordedProductionApprovalPolicy(
        policy_contract_version=POLICY_CONTRACT_VERSION,
        source_provenance=POLICY_SOURCE_PROVENANCE,
        policy_digest=canonical_digest(dict(p)),
        checklist_digest=canonical_digest(dict(c)),
        approval_channel="dashboard",
        production_realtime=True,
        production_nonresponse_code="block_until_approval",
        governance_requirements_digest=canonical_digest(_GOVERNANCE),
        approver_subject_hashes=tuple(subject_hashes),
    )


_FIXED_CONDITIONS = {
    "binding_must_be_current_at_use": True,
    "all_thirteen_a5_gates_must_pass_at_use": True,
    "preapproval_must_be_current_at_use": True,
    "autonomy_policy_must_permit_at_use": True,
    "slice55_must_authorize_transition": True,
    "production_forbidden_by_this_contract": True,
}


def fixed_conditions_digest() -> str:
    return canonical_digest(
        {"contract_version": CONDITIONS_CONTRACT_VERSION, "conditions": _FIXED_CONDITIONS}
    )


def release_binding_digest(**components: str) -> str:
    required = {
        "release_candidate_id",
        "evidence_pack_id",
        "release_verdict_id",
        "core_content_hash",
        "issue_binding_digest",
        "source_set_digest",
        "traceability_digest",
        "verdict_input_digest",
        "verdict_contract_hash",
        "autonomy_policy_digest",
        "policy_digest",
        "checklist_digest",
        "condition_contract_hash",
    }
    if set(components) != required:
        raise ProductionApprovalContractError("release binding component set is incomplete")
    if any(not isinstance(value, str) or not value.strip() for value in components.values()):
        raise ProductionApprovalContractError("release binding components must be non-blank strings")
    ordered_keys = (
        "release_candidate_id",
        "evidence_pack_id",
        "release_verdict_id",
        "core_content_hash",
        "issue_binding_digest",
        "source_set_digest",
        "traceability_digest",
        "verdict_input_digest",
        "verdict_contract_hash",
        "autonomy_policy_digest",
        "policy_digest",
        "checklist_digest",
        "condition_contract_hash",
    )
    return ordered_value_digest(
        (PREAPPROVAL_CONTRACT_VERSION, *(components[key] for key in ordered_keys))
    )


@dataclass(frozen=True)
class ActorEvidence:
    requester_authenticated: bool
    approver_authenticated: bool
    approver_in_policy: bool
    separation_ok: bool
    requester_actor_type: str | None
    approver_actor_type: str | None

    @property
    def gate_eligible(self) -> bool:
        return (
            self.requester_authenticated
            and self.approver_authenticated
            and self.approver_in_policy
            and self.separation_ok
            and self.requester_actor_type in {"human", "service"}
            and self.approver_actor_type == "human"
        )


def actor_evidence(
    *,
    requester: AuthenticatedActor | None,
    approver: AuthenticatedActor | None,
    member_subject_hashes: Sequence[str],
) -> ActorEvidence:
    requester_hash = subject_digest(requester.subject) if requester is not None else None
    approver_hash = subject_digest(approver.subject) if approver is not None else None
    return ActorEvidence(
        requester_authenticated=bool(
            requester is not None and requester.provenance == REQUEST_AUTHENTICATED
        ),
        approver_authenticated=bool(
            approver is not None and approver.provenance == REQUEST_AUTHENTICATED
        ),
        approver_in_policy=bool(approver_hash and approver_hash in member_subject_hashes),
        separation_ok=bool(requester_hash and approver_hash and requester_hash != approver_hash),
        requester_actor_type=requester.actor_type if requester is not None else None,
        approver_actor_type=approver.actor_type if approver is not None else None,
    )


def _require_aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProductionApprovalContractError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def preapproval_is_expired(expires_at: datetime, now: datetime) -> bool:
    return _require_aware_utc(now, "now") >= _require_aware_utc(expires_at, "expires_at")


__all__ = [
    "ActorEvidence",
    "CONDITIONS_CONTRACT_VERSION",
    "MAX_VALIDITY_HOURS",
    "POLICY_CONTRACT_VERSION",
    "POLICY_SOURCE_PROVENANCE",
    "PREAPPROVAL_CONTRACT_VERSION",
    "ProductionApprovalContractError",
    "RecordedProductionApprovalPolicy",
    "actor_evidence",
    "autonomy_policy_digest",
    "canonical_digest",
    "fixed_conditions_digest",
    "idempotency_digest",
    "ordered_value_digest",
    "parse_recorded_policy",
    "preapproval_is_expired",
    "release_binding_digest",
    "subject_digest",
]
