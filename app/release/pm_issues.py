"""PM / issue-tracker mapping validation (Slice 34, §12.3 / §26.3) — pure, no I/O.

A ``pm_issue_mappings`` row reflects an external PM (Jira) issue's **observed** state — **mapping-only**
(this slice creates no ``release_issues``). Records observed facts only: ``external_ref`` / ``external_status``
(raw, bounded) / ``board_column`` (a §12.3 column, or ``unmapped``) / ``title_present`` (presence, **not** the
title text). **No title/description/credential.** ``connector_verified`` means the connector verified it
**observed** the external state — **NOT** that the issue is provenance-complete/authoritative (gate #7
adequacy is not provided here). ``map_board_column`` is fail-closed: an unknown Jira status ⇒ ``unmapped``.
"""

from __future__ import annotations

import re

from app.release.deploy_evidence import TOKENISH_RE

EXTERNAL_SYSTEMS = ("jira",)
PROVENANCES = ("caller_supplied_unverified", "connector_verified")
WRITABLE_PROVENANCES = ("caller_supplied_unverified",)
CONNECTOR_WRITABLE = ("connector_verified",)

# The 16 §12.3 project-board columns (snake_case) + the honest fail-closed sentinel.
_SPEC_COLUMNS = (
    "backlog",
    "analysis",
    "requirements_review",
    "ready_for_development",
    "in_progress",
    "developer_self_check",
    "specialist_review",
    "changes_requested",
    "qa_testing",
    "security_review",
    "shortcut_detection",
    "acceptance_verification",
    "evidence_audit",
    "ready_for_release",
    "released",
    "done",
)
BOARD_COLUMNS = (*_SPEC_COLUMNS, "unmapped")

# Default Jira-status → §12.3-column map (lowercased exact match). Anything not here ⇒ ``unmapped`` (B2):
# we never GUESS a column. (Operator-tunable maps are a future refinement.)
JIRA_STATUS_MAP = {
    "backlog": "backlog",
    "to do": "ready_for_development",
    "selected for development": "ready_for_development",
    "ready for development": "ready_for_development",
    "in progress": "in_progress",
    "in review": "specialist_review",
    "code review": "specialist_review",
    "in qa": "qa_testing",
    "qa": "qa_testing",
    "testing": "qa_testing",
    "in testing": "qa_testing",
    "security review": "security_review",
    "ready for release": "ready_for_release",
    "released": "released",
    "done": "done",
    "closed": "done",
    "resolved": "done",
}

EXTERNAL_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
INSTANCE_KEY_RE = re.compile(r"^[a-z0-9_.:-]{1,64}$")
# Jira project key (uppercase), e.g. ``PROJ`` (B4 declared shape).
PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_MAX_STATUS_LEN = 256

REQUIRED_FIELDS = (
    "external_system",
    "instance_key",
    "external_ref",
    "external_status",
    "board_column",
    "title_present",
)


class InvalidPMMapping(ValueError):
    """Raised when a PM-mapping payload is invalid (fail-closed)."""


def is_valid_external_ref(ref) -> bool:
    return (
        isinstance(ref, str)
        and EXTERNAL_REF_RE.fullmatch(ref) is not None
        and TOKENISH_RE.search(ref) is None
    )


def is_valid_instance_key(key) -> bool:
    return isinstance(key, str) and INSTANCE_KEY_RE.fullmatch(key) is not None


def is_valid_project_key(key) -> bool:
    return isinstance(key, str) and PROJECT_KEY_RE.fullmatch(key) is not None


def map_board_column(jira_status) -> str:
    """Map a raw Jira status to a §12.3 board column; unknown/blank/non-str ⇒ ``unmapped`` (B2)."""
    if not isinstance(jira_status, str):
        return "unmapped"
    return JIRA_STATUS_MAP.get(jira_status.strip().lower(), "unmapped")


def _validate_shape(record: dict) -> None:
    for field in REQUIRED_FIELDS:
        if field not in record:
            raise InvalidPMMapping(f"missing required field: {field}")
    if record["external_system"] not in EXTERNAL_SYSTEMS:
        raise InvalidPMMapping(f"invalid external_system: {record['external_system']!r}")
    if not is_valid_instance_key(record["instance_key"]):
        raise InvalidPMMapping(f"invalid instance_key: {record['instance_key']!r}")
    if not is_valid_external_ref(record["external_ref"]):
        raise InvalidPMMapping(f"invalid external_ref: {record['external_ref']!r}")
    status = record["external_status"]
    if (
        not isinstance(status, str)
        or not (1 <= len(status) <= _MAX_STATUS_LEN)
        or any(ord(c) < 32 for c in status)
    ):
        raise InvalidPMMapping("external_status must be a bounded non-control string")
    if record["board_column"] not in BOARD_COLUMNS:
        raise InvalidPMMapping(f"invalid board_column: {record['board_column']!r}")
    if not isinstance(record["title_present"], bool):
        raise InvalidPMMapping("title_present must be a bool")


def validate_new_mapping(record: dict) -> None:
    """Fail-closed validation of a CALLER (unverified) mapping."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in WRITABLE_PROVENANCES:
        raise InvalidPMMapping(
            f"provenance {prov!r} is not writable on the caller path (only caller_supplied_unverified)"
        )


def validate_connector_mapping(record: dict) -> None:
    """Fail-closed validation of a CONNECTOR (observation-verified) mapping — provenance
    ``connector_verified`` (if present) and ``observed_at`` required."""
    _validate_shape(record)
    prov = record.get("provenance")
    if prov is not None and prov not in CONNECTOR_WRITABLE:
        raise InvalidPMMapping(f"connector provenance must be connector_verified, got {prov!r}")
    if record.get("observed_at") is None:
        raise InvalidPMMapping("connector mapping requires observed_at")
