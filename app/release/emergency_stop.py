"""Pure Slice-54 emergency-stop and rollback-authority contract.

The executable stop is deliberately limited to the current UAID workflow runtime.
Rollback authority is an immutable, release-bound authorization record and never a
deployment or rollback execution claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


EMERGENCY_CONTROL_CONTRACT_VERSION = "slice54.emergency_control.v1"
EMERGENCY_STOP_CONTRACT_VERSION = "slice54.emergency_stop.v1"
ROLLBACK_AUTHORITY_CONTRACT_VERSION = "slice54.rollback_authority.v1"

AUTHORITY_PROVENANCE = "request_authenticated"
POLICY_PROVENANCE = "caller_supplied_unverified_structured_approval_policy"

SCOPE_LIMITATION_CODES = (
    "local_uaid_runtime_step_boundary_only",
    "in_flight_node_not_preempted",
    "production_rollback_not_executed",
    "rollback_path_connector_observed_staging_only",
    "authority_is_request_authenticated_key_custody_under_recorded_policy",
)

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_OPERATIONS = frozenset({"activate", "clear", "authorize_rollback"})


class EmergencyControlContractError(ValueError):
    """Raised when emergency-control input cannot satisfy the ruled contract."""


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def authority_set_digest(subject_hashes: Sequence[str]) -> str:
    """Digest the exact ordered policy membership without exposing principals."""

    values = tuple(subject_hashes)
    if not values or len(values) > 100:
        raise EmergencyControlContractError("authority membership count is invalid")
    if len(values) != len(set(values)):
        raise EmergencyControlContractError("authority membership must be unique")
    if any(not isinstance(value, str) or not _DIGEST_RE.fullmatch(value) for value in values):
        raise EmergencyControlContractError("authority membership digest is invalid")
    return f"sha256:{hashlib.sha256(chr(31).join(values).encode('utf-8')).hexdigest()}"


def validate_latch_transition(before: str, after: str) -> None:
    """Accept only a real change between the two stable latch states."""

    if (before, after) not in {("armed", "active"), ("active", "armed")}:
        raise EmergencyControlContractError("emergency latch transition is invalid")


def validate_actor_authority(
    *,
    actor_provenance: str,
    actor_type: str,
    actor_is_member: bool,
    operation: str,
    activating_subject_hash: str | None = None,
    actor_subject_hash: str | None = None,
) -> None:
    """Validate the narrow DB-provable key-custody authority boundary."""

    if operation not in _OPERATIONS:
        raise EmergencyControlContractError("emergency operation is unsupported")
    if actor_provenance != AUTHORITY_PROVENANCE:
        raise EmergencyControlContractError("actor provenance is not request-authenticated")
    if actor_type != "human":
        raise EmergencyControlContractError("actor type is not eligible")
    if actor_is_member is not True:
        raise EmergencyControlContractError("actor is not a current policy member")
    if operation == "clear":
        if not (
            isinstance(activating_subject_hash, str)
            and _DIGEST_RE.fullmatch(activating_subject_hash)
            and isinstance(actor_subject_hash, str)
            and _DIGEST_RE.fullmatch(actor_subject_hash)
        ):
            raise EmergencyControlContractError("clear actors are not DB-bindable")
        if activating_subject_hash == actor_subject_hash:
            raise EmergencyControlContractError("clear requires a distinct second member")


def validate_empty_operation_payload(payload: Mapping[str, object]) -> None:
    """The bearer boundary derives every material input server-side."""

    if not isinstance(payload, Mapping) or payload:
        raise EmergencyControlContractError("emergency operation bodies must be empty")


def release_rollback_binding_digest(**components: str) -> str:
    """Bind the exact candidate, immutable core, and current rollback drill."""

    required = {
        "release_candidate_id",
        "evidence_pack_id",
        "rollback_verification_run_id",
        "core_content_hash",
        "rollback_artifact_scope_digest",
        "rollback_phase_digest",
    }
    if set(components) != required or any(
        not isinstance(value, str) or not value for value in components.values()
    ):
        raise EmergencyControlContractError("release rollback binding is incomplete")
    return _canonical_digest(components)


@dataclass(frozen=True)
class EmergencyControlCoverage:
    """Safe scalar/code-only projection consumed by A5 gate #13."""

    policy_present: bool = False
    policy_valid: bool = False
    binding_present: bool = False
    latest_binding_failed_or_refused: bool = False
    contracts_current: bool = False
    authority_membership_complete: bool = False
    authority_member_count: int = 0
    mechanism_initialized: bool = False
    stop_state_consistent: bool = False
    stop_active: bool = False
    rollback_authority_bound: bool = False
    rollback_binding_current: bool = False
    rollback_verification_current: bool = False
    evidence_consistent: bool = False
    control_contract_version: str | None = None
    stop_contract_version: str | None = None
    rollback_authority_contract_version: str | None = None

    def gate_kwargs(self) -> dict[str, object]:
        values = {
            key: value
            for key, value in self.__dict__.items()
            if key
            not in {
                "control_contract_version",
                "stop_contract_version",
                "rollback_authority_contract_version",
            }
        }
        return {
            **{f"emergency_{key}": value for key, value in values.items()},
            "emergency_control_contract_version": self.control_contract_version,
            "emergency_stop_contract_version": self.stop_contract_version,
            "emergency_rollback_authority_contract_version": (
                self.rollback_authority_contract_version
            ),
        }
