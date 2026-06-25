"""PM / issue-tracker connector tests (Slice 34, §12.3 / §26.3).

A broker-gated **Jira** connector reflects external PM issues into an immutable, append-only
``pm_issue_mappings`` store — **mapping-only** (creates no ``release_issues``). Records observed facts only
``(external_ref, external_status, §12.3 board_column, title_present)`` — **no title/description/credential**;
``connector_verified`` = OBSERVATION-verified (not issue-provenance-complete). Jira-status → §12.3 column via
``map_board_column`` with an **``unmapped``** fail-closed sentinel for unknown statuses. Idempotent
latest-wins keyed by ``(tenant, project, external_system, instance_key, external_ref)``. **Store/infra-only —
no release_issues/production_autonomy/readiness change; ruleset stays slice31.v1.**

Docker-free for the pure validators / board-column map; ``db`` for the store, DB guard, resolver, broker-
gated service, idempotent sync, and the ``before==after`` no-A5-impact guard.
"""

import pytest

from app.release.pm_issues import (
    BOARD_COLUMNS,
    EXTERNAL_SYSTEMS,
    PROVENANCES,
    WRITABLE_PROVENANCES,
    InvalidPMMapping,
    is_valid_external_ref,
    is_valid_instance_key,
    map_board_column,
    validate_connector_mapping,
    validate_new_mapping,
)

_NOW = "2026-06-25T12:00:00+00:00"  # opaque marker; the model uses a real datetime

# The 16 §12.3 board columns (snake_case) + the unmapped fail-closed sentinel.
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


def _rec(**over) -> dict:
    rec = {
        "external_system": "jira",
        "instance_key": "acme-jira",
        "external_ref": "PROJ-123",
        "external_status": "In Progress",
        "board_column": "in_progress",
        "title_present": True,
    }
    rec.update(over)
    return rec


# --- pure: constants + board-column mapping (B2) ------------------------------


def test_constants():
    assert EXTERNAL_SYSTEMS == ("jira",)
    assert PROVENANCES == ("caller_supplied_unverified", "connector_verified")
    assert WRITABLE_PROVENANCES == ("caller_supplied_unverified",)
    # the §12.3 columns are all present, plus the unmapped sentinel
    for col in _SPEC_COLUMNS:
        assert col in BOARD_COLUMNS
    assert "unmapped" in BOARD_COLUMNS


@pytest.mark.parametrize(
    "status,column",
    [
        ("Backlog", "backlog"),
        ("In Progress", "in_progress"),
        ("in progress", "in_progress"),  # case-insensitive
        ("Done", "done"),
        ("Released", "released"),
    ],
)
def test_map_board_column_known(status, column):
    assert map_board_column(status) == column


@pytest.mark.parametrize("status", ["Frobnicating", "", None, "   ", 123])
def test_map_board_column_unknown_is_unmapped(status):
    # B2: any unknown/unmapped/blank Jira status maps to 'unmapped' (honest fail-closed, never guessed).
    assert map_board_column(status) == "unmapped"


# --- pure: shapes -------------------------------------------------------------


@pytest.mark.parametrize("ref", ["PROJ-123", "ABC-1", "x", "a.b_c-1"])
def test_valid_external_refs(ref):
    assert is_valid_external_ref(ref)


@pytest.mark.parametrize("ref", ["", "has space", "ghp_secrettoken", "x" * 129, "bad/ref"])
def test_invalid_external_refs(ref):
    assert not is_valid_external_ref(ref)


@pytest.mark.parametrize("key", ["acme-jira", "jira_1", "a"])
def test_valid_instance_keys(key):
    assert is_valid_instance_key(key)


@pytest.mark.parametrize("key", ["", "ACME", "has space", "x" * 65])
def test_invalid_instance_keys(key):
    assert not is_valid_instance_key(key)


# --- pure: validators ---------------------------------------------------------


def test_valid_records_pass():
    validate_new_mapping(_rec())
    validate_new_mapping(_rec(external_status="Frobnicating", board_column="unmapped"))
    validate_connector_mapping(_rec(provenance="connector_verified", observed_at=_NOW))


@pytest.mark.parametrize(
    "over",
    [
        {"external_system": "trello"},  # not jira
        {"instance_key": "BAD KEY"},  # bad shape
        {"external_ref": "has space"},  # bad shape
        {"external_ref": "ghp_token"},  # token denylist
        {"board_column": "in_review"},  # not a §12.3 column
        {"title_present": "yes"},  # not a bool
        {"external_status": ""},  # blank status
    ],
)
def test_invalid_records_rejected(over):
    with pytest.raises(InvalidPMMapping):
        validate_new_mapping(_rec(**over))


def test_caller_path_rejects_connector_verified():
    with pytest.raises(InvalidPMMapping):
        validate_new_mapping(_rec(provenance="connector_verified"))


def test_connector_path_requires_verified_and_observed_at():
    with pytest.raises(InvalidPMMapping):
        validate_connector_mapping(_rec(provenance="caller_supplied_unverified"))
    with pytest.raises(InvalidPMMapping):
        validate_connector_mapping(_rec(provenance="connector_verified"))  # no observed_at
