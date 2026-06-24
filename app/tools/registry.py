"""Code-defined tool catalog + deterministic parameter validation (§11.4 / §16.4).

The registry is version-controlled and deny-by-default: a tool not present here is
rejected by the broker. Each contract maps a tool to a Slice 3 policy action and a
tool-level approval requirement (§11.4).
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_MAX_PARAMS_BYTES = 16 * 1024  # 16 KiB
_SECRET_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "api_key",
    "access_key",
    "private_key",
    "credential",
)


class InvalidParams(Exception):
    """Raised when tool params fail deterministic validation."""

    def __init__(self, kind: str):
        super().__init__(f"invalid_params:{kind}")
        self.kind = kind  # 'non_mapping' | 'oversized' | 'invalid_json'


@dataclass(frozen=True)
class ToolContract:
    tool_name: str
    category: str
    required_action: str  # maps to the Slice 3 authority matrix action
    requires_approval: bool
    audit_level: str


def _c(tool_name, category, required_action, *, requires_approval=False, audit_level="standard"):
    return ToolContract(tool_name, category, required_action, requires_approval, audit_level)


# Skeleton catalog (no real execution). Actions map to app.policy.matrix entries.
TOOL_REGISTRY: dict[str, ToolContract] = {
    # Policy-allowed at A1+, but the org gates this tool behind approval anyway
    # (tool-level requires_approval, independent of the policy decision).
    "pm.create_issue": _c(
        "pm.create_issue", "project_management", "create_project_tasks", requires_approval=True
    ),
    "source_control.create_branch": _c(
        "source_control.create_branch", "source_control", "create_branches"
    ),
    # Slice 28: broker-gated read; maps to the read-only read_source_control_config action.
    "source_control.read_branch_protection": _c(
        "source_control.read_branch_protection", "source_control", "read_source_control_config"
    ),
    # Slice 29: broker-gated read; maps to the read-only read_pull_requests action.
    "source_control.read_pull_request": _c(
        "source_control.read_pull_request", "source_control", "read_pull_requests"
    ),
    # Slice 30: broker-gated read; maps to the read-only read_deployment_target action.
    "deployment.read_target_status": _c(
        "deployment.read_target_status", "deployment", "read_deployment_target"
    ),
    "source_control.open_pull_request": _c(
        "source_control.open_pull_request",
        "source_control",
        "open_pull_requests",
        audit_level="high",
    ),
    "ci.run_tests": _c("ci.run_tests", "ci_cd", "run_tests"),
    "ci.deploy_staging": _c("ci.deploy_staging", "ci_cd", "deploy_staging"),
    "ci.deploy_production": _c(
        "ci.deploy_production",
        "ci_cd",
        "deploy_production",
        requires_approval=True,
        audit_level="high",
    ),
    "source_control.merge_to_protected": _c(
        "source_control.merge_to_protected",
        "source_control",
        "merge_to_protected",
        requires_approval=True,
        audit_level="high",
    ),
}


def get_contract(tool_name: str) -> ToolContract | None:
    return TOOL_REGISTRY.get(tool_name)


def sanitize_params(params: Any) -> dict:
    """Validate + redact tool params (deterministic). Raise InvalidParams on failure.

    - params MUST be a mapping (else kind='non_mapping');
    - secret-ish keys are redacted to '[REDACTED]' at ANY depth (nested in maps/lists);
    - non-finite floats (NaN/Infinity) are rejected (kind='invalid_json') — they are
      not portable JSON and must not cross the persistence boundary;
    - serialized size must be <= 16 KiB (else kind='oversized');
    - the result is round-tripped through JSON (default=str, allow_nan=False) so it is
      guaranteed JSONB-storable: what we validated for size is exactly what gets stored,
      and the store can never fail or persist a non-portable value mid-pipeline.
    """
    if not isinstance(params, Mapping):
        raise InvalidParams("non_mapping")
    normalized = _normalize(params)
    try:
        serialized = json.dumps(normalized, default=str, allow_nan=False)
    except ValueError as exc:  # belt-and-suspenders; _normalize already rejects non-finite
        raise InvalidParams("invalid_json") from exc
    if len(serialized.encode("utf-8")) > _MAX_PARAMS_BYTES:
        raise InvalidParams("oversized")
    return json.loads(serialized)


def _normalize(value: Any) -> Any:
    """Recursively normalize to JSON-portable, secret-redacted data (deterministic).

    Mappings → str keys with secret-ish keys redacted (whole subtree dropped);
    lists/tuples → element-wise normalized lists; non-finite floats → InvalidParams.
    Other scalars (str/int/bool/None) pass through; anything else is stringified by
    ``json.dumps(default=str)`` downstream.
    """
    if isinstance(value, Mapping):
        return {
            str(k): ("[REDACTED]" if _is_secret_key(str(k)) else _normalize(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidParams("invalid_json")
    return value


def _is_secret_key(key: str) -> bool:
    low = key.lower()
    return any(marker in low for marker in _SECRET_KEY_MARKERS)
