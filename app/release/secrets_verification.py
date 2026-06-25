"""Secrets-reference verification (Slice 32, R5 App. A l.2968 / §26.3 / spec:1094) — pure, no I/O.

A ``secret_reference_checks`` row records whether a declared ``secrets_and_credentials_manifest`` reference
**resolves in its approved manager** — the A5 "secrets available" evidence class. Fail-closed,
non-authorizing, and **store-only** (no gate flip this slice).

ZERO secret-value leakage (B4/B6): a secret **value** is never stored, logged, audited, persisted,
returned, or bound into any DB/broker/audit payload. The only allowed value contact is a transient
in-process ``env`` non-emptiness check (the connector, not here).

- ``SUPPORTED_MANAGERS=("env",)`` is the **verifiable** set this slice; ``manager`` is persisted as
  bounded safe **text** (any declared identifier), so a non-``env`` reference is representable — but
  honesty (B1) requires ``manager not in SUPPORTED_MANAGERS ⟹ outcome='unsupported_manager' and not
  resolved``.
- ``reference_name`` is a bounded safe **shape only** (B2) — it ACCEPTS legitimate names such as
  ``prod/db_password`` / ``app/api_key``; no token/value-substring denylist is applied to the name.
- Honesty model: ``outcome ∈ {resolved, not_found, unsupported_manager, probe_error}`` with
  ``resolved == (outcome == 'resolved')``. A check that could not be performed is never ``not_found``.
"""

from __future__ import annotations

import re

SUPPORTED_MANAGERS = ("env",)
OUTCOMES = ("resolved", "not_found", "unsupported_manager", "probe_error")
PROVENANCES = ("caller_supplied_unverified", "connector_verified")
WRITABLE_PROVENANCES = ("caller_supplied_unverified",)
CONNECTOR_WRITABLE = ("connector_verified",)

MANAGER_RE = re.compile(r"^[a-z0-9_.:-]{1,64}$")
REFERENCE_NAME_RE = re.compile(r"^[A-Za-z0-9_./:-]{1,256}$")

REQUIRED_FIELDS = ("manager", "reference_name", "outcome", "resolved")


class InvalidSecretCheck(ValueError):
    """Raised when a secret-reference-check payload is invalid (fail-closed)."""


def is_valid_manager(manager) -> bool:
    return isinstance(manager, str) and MANAGER_RE.fullmatch(manager) is not None


def is_valid_reference_name(reference_name) -> bool:
    return (
        isinstance(reference_name, str) and REFERENCE_NAME_RE.fullmatch(reference_name) is not None
    )


def build_env_outcome(*, present: bool) -> dict:
    """Map an ``env`` non-emptiness **boolean** (never a value) to an outcome (B4)."""
    return (
        {"outcome": "resolved", "resolved": True}
        if present
        else {"outcome": "not_found", "resolved": False}
    )


def observation_unsupported_manager() -> dict:
    return {"outcome": "unsupported_manager", "resolved": False}


def observation_probe_error() -> dict:
    return {"outcome": "probe_error", "resolved": False}


def _validate_shape(record: dict) -> None:
    for field in REQUIRED_FIELDS:
        if field not in record:
            raise InvalidSecretCheck(f"missing required field: {field}")
    if not is_valid_manager(record["manager"]):
        raise InvalidSecretCheck(f"invalid manager: {record['manager']!r}")
    if not is_valid_reference_name(record["reference_name"]):
        raise InvalidSecretCheck(f"invalid reference_name shape: {record['reference_name']!r}")
    if record["outcome"] not in OUTCOMES:
        raise InvalidSecretCheck(f"invalid outcome: {record['outcome']!r}")
    if not isinstance(record["resolved"], bool):
        raise InvalidSecretCheck("resolved must be a bool")
    # Honesty invariant: resolved iff outcome is 'resolved'.
    if record["resolved"] != (record["outcome"] == "resolved"):
        raise InvalidSecretCheck("resolved must equal (outcome == 'resolved')")
    # B1: an unsupported (non-env) manager must be recorded as unsupported_manager + not resolved.
    if record["manager"] not in SUPPORTED_MANAGERS and not (
        record["outcome"] == "unsupported_manager" and record["resolved"] is False
    ):
        raise InvalidSecretCheck(
            f"manager {record['manager']!r} is not verifiable this slice; "
            "must be recorded as unsupported_manager + not resolved"
        )


def validate_new_secret_check(record: dict) -> None:
    """Fail-closed validation of a CALLER (unverified) check."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in WRITABLE_PROVENANCES:
        raise InvalidSecretCheck(
            f"provenance {prov!r} is not writable on the caller path (only caller_supplied_unverified)"
        )


def validate_connector_secret_check(record: dict) -> None:
    """Fail-closed validation of a CONNECTOR (verified) check — provenance ``connector_verified`` (if
    present) and ``checked_at`` required."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in CONNECTOR_WRITABLE:
        raise InvalidSecretCheck(f"connector provenance must be connector_verified, got {prov!r}")
    if record.get("checked_at") is None:
        raise InvalidSecretCheck("connector check requires checked_at")
