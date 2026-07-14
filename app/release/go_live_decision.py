"""Pure Slice-55 go-live decision contracts.

This module derives only a bounded ``decided_not_executed`` decision.  It has no
deployment capability and deliberately keeps request-authenticated authority at
the key-custody truth tier defined by Slice 53.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

CONTROL_LOOP_CONTRACT_VERSION = "slice55.control_loop.v1"
GO_LIVE_EVALUATION_CONTRACT_VERSION = "slice55.go_live_evaluation.v1"
GO_LIVE_DECISION_CONTRACT_VERSION = "slice55.go_live_decision.v1"
GO_LIVE_CHAIN_CONTRACT_VERSION = "slice55.go_live_decision_chain.v1"

DECISION_STATUS = "decided_not_executed"
AUTHORITY_TRUTH_TIER = (
    "request_authenticated_key_custody_under_recorded_policy_not_human_signature"
)
SCOPE_LIMITATION_CODES = (
    "production_not_executed",
    "key_custody_not_human_signature",
    "bounded_current_evidence_only",
    "staging_evidence_observed_not_deployed",
    "future_execution_requires_new_plan",
)

_HASH_PREFIX = "sha256:"
_ALLOWED_GATE_STATUSES = frozenset(
    {"passed", "failed", "insufficient_evidence", "no_evidence_source"}
)
_FORBIDDEN_CALLER_TRUTH_FIELDS = frozenset(
    {
        "passed",
        "eligible",
        "current",
        "approved",
        "policy_permits",
        "latch_active",
        "decision_status",
        "executed",
        "can_go_live",
        "prev_hash",
        "entry_hash",
        "chain_seq",
    }
)


def _bounded_code(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > 128:
        raise ValueError(f"{field}_invalid")
    return value


def _sha256_text(value: bytes) -> str:
    return _HASH_PREFIX + hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class GateSnapshot:
    gate_number: int
    gate_name: str
    status: str
    reason: str
    safe_context_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.gate_number, bool) or not isinstance(self.gate_number, int):
            raise ValueError("gate_number_invalid")
        _bounded_code(self.gate_name, "gate_name")
        if self.status not in _ALLOWED_GATE_STATUSES:
            raise ValueError("gate_status_invalid")
        _bounded_code(self.reason, "gate_reason")
        if not (
            isinstance(self.safe_context_digest, str)
            and len(self.safe_context_digest) == 71
            and self.safe_context_digest.startswith(_HASH_PREFIX)
            and all(c in "0123456789abcdef" for c in self.safe_context_digest[7:])
        ):
            raise ValueError("safe_context_digest_invalid")


@dataclass(frozen=True, slots=True)
class DecisionInputs:
    gates: tuple[GateSnapshot, ...]
    preapproval_gate_eligible: bool
    policy_decision: str
    emergency_latch_active: bool
    binding_ids: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "gates", tuple(self.gates))
        if type(self.preapproval_gate_eligible) is not bool:  # noqa: E721
            raise ValueError("preapproval_gate_eligible_invalid")
        if self.policy_decision not in {"needs_approval", "deny", "allow"}:
            raise ValueError("policy_decision_invalid")
        if type(self.emergency_latch_active) is not bool:  # noqa: E721
            raise ValueError("emergency_latch_active_invalid")
        normalized: dict[str, str] = {}
        for key, value in self.binding_ids.items():
            normalized[_bounded_code(key, "binding_key")] = _bounded_code(
                value, "binding_value"
            )
        object.__setattr__(self, "binding_ids", normalized)


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    eligible: bool
    status: str | None
    production_action_executed: bool = False
    can_go_live_autonomously: bool = False
    authority_truth_tier: str = AUTHORITY_TRUTH_TIER
    scope_limitation_codes: tuple[str, ...] = SCOPE_LIMITATION_CODES


def validate_exact_gate_set(gates: Sequence[GateSnapshot]) -> tuple[GateSnapshot, ...]:
    normalized = tuple(gates)
    if tuple(gate.gate_number for gate in normalized) != tuple(range(1, 14)):
        raise ValueError("exact_gate_set_required")
    return normalized


def canonical_gate_digest(gates: Sequence[GateSnapshot]) -> str:
    normalized = validate_exact_gate_set(gates)
    rows = []
    for gate in normalized:
        name = gate.gate_name.encode("utf-8")
        status = gate.status.encode("utf-8")
        reason = gate.reason.encode("utf-8")
        rows.append(
            b":".join(
                (
                    str(gate.gate_number).encode(),
                    str(len(name)).encode(),
                    name,
                    str(len(status)).encode(),
                    status,
                    str(len(reason)).encode(),
                    reason,
                    gate.safe_context_digest.encode(),
                )
            )
        )
    return _sha256_text(b"\n".join(rows))


def canonical_binding_digest(inputs: DecisionInputs) -> str:
    payload = {
        "gate_result_digest": canonical_gate_digest(inputs.gates),
        "preapproval_gate_eligible": inputs.preapproval_gate_eligible,
        "policy_decision": inputs.policy_decision,
        "emergency_latch_active": inputs.emergency_latch_active,
        "binding_ids": dict(inputs.binding_ids),
        "decision_contract": GO_LIVE_DECISION_CONTRACT_VERSION,
    }
    return _sha256_text(_canonical_json(payload))


def decision_eligible(inputs: DecisionInputs) -> bool:
    gates = validate_exact_gate_set(inputs.gates)
    return (
        all(gate.status == "passed" for gate in gates)
        and inputs.preapproval_gate_eligible
        and inputs.policy_decision == "needs_approval"
        and not inputs.emergency_latch_active
    )


def derive_decision(inputs: DecisionInputs) -> DecisionOutcome:
    eligible = decision_eligible(inputs)
    return DecisionOutcome(eligible=eligible, status=DECISION_STATUS if eligible else None)


def reject_caller_truth_fields(payload: object) -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in _FORBIDDEN_CALLER_TRUTH_FIELDS:
                raise ValueError(f"caller_truth_field_forbidden:{key}")
            reject_caller_truth_fields(value)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            reject_caller_truth_fields(value)
