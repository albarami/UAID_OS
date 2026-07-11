"""Bounded, versioned CI observation artifact contract for Slice 43.

The connector verifies that it fetched this data for an exact repository commit;
this module validates shape only. It never accepts or carries a pass/fail verdict.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Mapping

RESULTS_SCHEMA_VERSION = "slice43.results.v1"
MAX_RESULT_ARTIFACT_BYTES = 2_000_000
MAX_ORACLES_PER_ARTIFACT = 1_000
MAX_OBSERVATIONS_PER_ORACLE = 1_000
MAX_CASE_REF = 128

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOP_FIELDS = {"schema_version", "commit_sha", "oracles"}
_ORACLE_FIELDS = {"oracle_artifact_id", "definition_hash", "observations"}
_OBSERVATION_FIELDS = {"case_ref", "observed", "input", "sample_class"}
_SAMPLE_CLASSES = {"representative", "adversarial", "calibration", "other"}


def _bounded_json(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("result artifact must contain canonical JSON data") from exc
    if len(encoded) > MAX_RESULT_ARTIFACT_BYTES:
        raise ValueError("result artifact exceeds the byte limit")
    return encoded


def _ref(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_CASE_REF:
        raise ValueError("case_ref must be a bounded non-blank string")
    return value.strip()


def validate_result_artifact(
    payload: Mapping[str, Any], *, expected_commit_sha: str
) -> dict[str, Any]:
    """Return a canonical copy after strict exact-commit and shape validation."""
    if not isinstance(payload, Mapping):
        raise ValueError("result artifact must be an object")
    if set(payload) != _TOP_FIELDS:
        raise ValueError("unknown or missing result artifact fields")
    if payload.get("schema_version") != RESULTS_SCHEMA_VERSION:
        raise ValueError("unsupported result artifact schema")
    commit_sha = payload.get("commit_sha")
    if not isinstance(expected_commit_sha, str) or _SHA_RE.fullmatch(expected_commit_sha) is None:
        raise ValueError("expected_commit_sha must be 40 lowercase hexadecimal characters")
    if commit_sha != expected_commit_sha:
        raise ValueError("result artifact commit_sha does not match the requested commit")
    oracles = payload.get("oracles")
    if not isinstance(oracles, list) or not (1 <= len(oracles) <= MAX_ORACLES_PER_ARTIFACT):
        raise ValueError("oracles must be a bounded non-empty list")

    seen_oracles: set[str] = set()
    for oracle in oracles:
        if not isinstance(oracle, dict) or set(oracle) != _ORACLE_FIELDS:
            raise ValueError("unknown or missing oracle result fields")
        try:
            oracle_id = str(uuid.UUID(str(oracle.get("oracle_artifact_id"))))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("oracle_artifact_id must be a UUID") from exc
        if oracle_id in seen_oracles:
            raise ValueError("duplicate oracle_artifact_id")
        seen_oracles.add(oracle_id)
        definition_hash = oracle.get("definition_hash")
        if not isinstance(definition_hash, str) or _HASH_RE.fullmatch(definition_hash) is None:
            raise ValueError("definition_hash must be a sha256 digest")
        observations = oracle.get("observations")
        if not isinstance(observations, list) or not (
            1 <= len(observations) <= MAX_OBSERVATIONS_PER_ORACLE
        ):
            raise ValueError("observations must be a bounded non-empty list")
        seen_cases: set[str] = set()
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError("each observation must be an object")
            unknown = set(observation) - _OBSERVATION_FIELDS
            if unknown or "case_ref" not in observation or "observed" not in observation:
                raise ValueError("unknown observation fields or missing required fields")
            case_ref = _ref(observation["case_ref"])
            if case_ref in seen_cases:
                raise ValueError("duplicate observation case_ref")
            seen_cases.add(case_ref)
            sample_class = observation.get("sample_class")
            if sample_class is not None and sample_class not in _SAMPLE_CLASSES:
                raise ValueError("invalid observation sample_class")
    encoded = _bounded_json(dict(payload))
    return json.loads(encoded)
