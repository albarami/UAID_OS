"""Slice 57 §25.2 incident workflow — pure contract proofs."""

from __future__ import annotations

import hashlib
import inspect
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.ops.incident_service import (
    evaluate_post_launch_actions,
    history,
    latest_handover,
    latest_incident,
    list_open,
    open_incident,
    record_log_diagnosis_unavailable,
    record_support_handover,
    transition_incident,
)
from app.ops.incidents import (
    ACTION_EVAL_VERSION,
    ACTIONS,
    GATED_MATRIX_ACTIONS,
    INCIDENT_CONTRACT_VERSION,
    RULESET_VERSION,
    STATUSES,
    ActionChild,
    IncidentError,
    IncidentIdempotencyRace,
    IncidentPayload,
    IncidentSnapshot,
    PolicySnapshot,
    bind_seq1_ticket,
    evaluate_actions,
    policy_input_digest,
    ticket_should_exist,
    validate_handover,
    validate_new_incident,
    validate_transition,
)
from app.policy.engine import Decision, check_authority
from app.policy.levels import AutonomyLevel
from app.policy.matrix import validate_overrides
from app.release.production_autonomy import (
    A5_RULESET_VERSION,
    NO_GO_LIVE_REASONS,
    evaluate_production_autonomy,
)
from app.tenancy import TenantContext
from tests.ops_incidents_support import DB_CHECKS_SHA

_STABLE = {
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": ("7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26"),
    "app/runtime/control_loop.py": (
        "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180"
    ),
}
_POLICY = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_OWNED = (
    "app/ops/incidents.py",
    "app/ops/incident_service.py",
    "app/ops/incident_db_checks.py",
    "app/ops/incident_ddl.py",
    "app/repositories/ops_incidents.py",
    "app/repositories/ops_incident_reads.py",
    "app/models/ops_incident.py",
)


def _by_seq(children):
    return {child.seq: child for child in children}


def _denied() -> dict[str, Decision]:
    return {action: Decision.DENY for action in GATED_MATRIX_ACTIONS}


def _decisions(level: int, overrides: dict | None = None) -> dict[str, Decision]:
    payload = overrides or {}
    validate_overrides(payload)
    return {
        action: check_authority(action, AutonomyLevel(level), payload)
        for action in GATED_MATRIX_ACTIONS
    }


def test_contracts_and_accepted_absent():
    assert INCIDENT_CONTRACT_VERSION == "slice57.incidents.v1"
    assert ACTION_EVAL_VERSION == "slice57.action_eval.v1"
    assert RULESET_VERSION == "slice57.v1"
    assert "accepted" not in STATUSES
    assert len(ACTIONS) == 7
    assert ACTIONS[1] == (2, "diagnose_log_error", "none")
    with pytest.raises(IncidentError):
        validate_new_incident(IncidentPayload(category="nope", severity="low", summary="x"))
    with pytest.raises(IncidentError):
        validate_new_incident(IncidentPayload(category="other", severity="low", summary="x"))
    with pytest.raises(IncidentError):
        validate_transition("open", "mitigated")
    with pytest.raises(IncidentError):
        validate_transition("open", "accepted")
    parsed = validate_new_incident(
        IncidentPayload(category="error", severity="high", summary="  disk  ")
    )
    assert parsed.summary == "disk"
    with pytest.raises(IncidentError):
        validate_new_incident(
            IncidentPayload(
                category="error",
                severity="low",
                summary="x",
                source_signal_id="not-a-uuid",  # type: ignore[arg-type]
            )
        )
    with pytest.raises(IncidentError):
        validate_new_incident(
            IncidentPayload(
                category="error",
                severity="low",
                summary="x",
                pm_issue_mapping_id="not-a-uuid",  # type: ignore[arg-type]
            )
        )


def test_missing_policy_and_a0_write_no_ticket():
    missing = evaluate_actions(_denied())
    a0 = evaluate_actions(_decisions(0))
    for children in (missing, a0):
        mapped = _by_seq(children)
        assert mapped[1].policy_decision == "deny"
        assert mapped[1].execution_posture == "recorded_not_executed"
        assert mapped[1].reason_code == "ticket_denied_by_policy"
        assert mapped[1].ticket_id is None
        assert not ticket_should_exist(children)
        assert mapped[2].policy_decision == "not_evaluated"
        assert mapped[2].matrix_action == "none"
        assert mapped[2].reason_code == "no_log_source"
    with pytest.raises(IncidentError, match="missing policy decision"):
        evaluate_actions({})


def test_a1_allow_and_tightened_deny():
    allowed = evaluate_actions(_decisions(1))
    mapped = _by_seq(allowed)
    assert mapped[1].policy_decision == "allow"
    assert mapped[1].execution_posture == "local_ticket_written"
    assert ticket_should_exist(allowed)
    tightened = evaluate_actions(_decisions(1, {"create_project_tasks": {"allow": False}}))
    first = _by_seq(tightened)[1]
    assert first.policy_decision == "deny"
    assert not ticket_should_exist(tightened)


def test_a2_and_a5_not_executed_production():
    a2 = _by_seq(evaluate_actions(_decisions(2)))
    assert a2[3].policy_decision == "allow"
    assert a2[4].policy_decision == "allow"
    assert a2[3].execution_posture == "recorded_not_executed"
    assert a2[5].policy_decision == "deny"
    assert a2[6].policy_decision == "deny"
    assert a2[6].reason_code == "production_not_executed"
    assert a2[7].reason_code == "production_not_executed"
    a5 = _by_seq(evaluate_actions(_decisions(5)))
    assert a5[6].policy_decision == "needs_approval"
    assert a5[7].policy_decision == "needs_approval"
    assert a5[6].execution_posture == "recorded_not_executed"
    assert a5[5].policy_decision == "allow"


def test_policy_digest_hashes_override_values():
    same_keys_low = policy_input_digest(
        PolicySnapshot(True, _POLICY, 2, {"create_branches": {"min_level": 3}})
    )
    same_keys_high = policy_input_digest(
        PolicySnapshot(True, _POLICY, 2, {"create_branches": {"min_level": 4}})
    )
    assert same_keys_low != same_keys_high
    ticket = uuid.uuid4()
    bound = bind_seq1_ticket(
        (
            ActionChild(
                seq=1,
                action="create_bug_ticket",
                matrix_action="create_project_tasks",
                policy_decision="allow",
                execution_posture="local_ticket_written",
                reason_code="ticket_written",
            ),
        ),
        ticket,
    )
    assert bound[0].ticket_id == ticket


def test_handover_request_authenticated_requires_principal():
    validate_handover(
        handed_over_by="alice",
        received_by="ops",
        status="recorded_complete",
        provenance="caller_supplied_unverified",
        actor_subject=None,
    )
    with pytest.raises(IncidentError):
        validate_handover(
            handed_over_by="alice",
            received_by="ops",
            status="recorded_complete",
            provenance="request_authenticated",
            actor_subject="bob",
        )


def test_public_wrappers_have_no_session_and_no_broker():
    for fn in (
        open_incident,
        transition_incident,
        record_log_diagnosis_unavailable,
        evaluate_post_launch_actions,
        record_support_handover,
        latest_incident,
        list_open,
        history,
        latest_handover,
    ):
        assert "session" not in inspect.signature(fn).parameters
    for path in _OWNED:
        text = Path(path).read_text()
        assert "broker_call" not in text
        assert "pm.create_issue" not in text
    incident_contract = Path("app/ops/incidents.py").read_text()
    assert "check_authority(" not in incident_contract
    assert "decision_for(" not in incident_contract
    repo = Path("app/repositories/ops_incidents.py").read_text()
    assert "decision_for(" in repo
    assert "check_authority(" not in repo
    assert not hasattr(IncidentSnapshot, "diagnosed")
    assert "diagnosed" not in IncidentSnapshot.__dataclass_fields__
    assert "log_diagnosis_complete" not in IncidentSnapshot.__dataclass_fields__


def test_a5_readiness_go_live_and_frozen_db_checks():
    for path, digest in _STABLE.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    assert hashlib.sha256(Path("app/ops/db_checks.py").read_bytes()).hexdigest() == DB_CHECKS_SHA
    project_id = uuid.uuid4()
    before = evaluate_production_autonomy(project_id, readiness_level="R2")
    after = evaluate_production_autonomy(project_id, readiness_level="R2")
    assert before.to_dict() == after.to_dict()
    assert after.to_dict()["can_go_live_autonomously"] is False
    assert A5_RULESET_VERSION == "slice54.v1"
    assert NO_GO_LIVE_REASONS == ("a5_gates_not_all_satisfied",)
    from app.intake.readiness import RULESET_VERSION as readiness_ruleset

    assert readiness_ruleset == "slice20.v1"
    migration = Path("migrations/versions/0056_ops_incidents.py").read_text()
    assert 'down_revision: str | None = "0055"' in migration
    assert (
        "cannot downgrade Slice 57 while incident rows exist"
        in Path("app/ops/incident_ddl.py").read_text()
    )


def _dbapi_error(sqlstate: str) -> DBAPIError:
    original = type("OriginalDatabaseError", (Exception,), {"sqlstate": sqlstate})()
    return DBAPIError("inc_retry_probe", {}, original)


async def _patched_open(monkeypatch, fake_once):
    from app.ops import incident_service as service

    monkeypatch.setattr(service, "_open_once", fake_once)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    return await open_incident(
        TenantContext(uuid.uuid4()),
        uuid.uuid4(),
        actor="inc-test",
        payload=IncidentPayload(category="error", severity="low", summary="x"),
        idempotency_key="retry-key",
    )


async def test_open_retries_empty_reselect_then_succeeds(monkeypatch):
    from app.ops import incident_service as service

    winner = MagicMock(name="snapshot")
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise service._IdempotencyWinnerNotVisible()
        return winner

    assert await _patched_open(monkeypatch, fake_once) is winner
    assert calls["n"] == 2


async def test_open_retries_serialization_then_succeeds(monkeypatch):
    winner = MagicMock(name="snapshot")
    seen: list[str] = []

    async def fake_once(*_args, **_kwargs):
        if len(seen) < 2:
            code = "40001" if not seen else "40P01"
            seen.append(code)
            raise _dbapi_error(code)
        return winner

    assert await _patched_open(monkeypatch, fake_once) is winner
    assert seen == ["40001", "40P01"]


async def test_open_exhausts_five_race_retries(monkeypatch):
    from app.ops import incident_service as service

    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        raise service._IdempotencyWinnerNotVisible()

    with pytest.raises(IncidentIdempotencyRace):
        await _patched_open(monkeypatch, fake_once)
    assert calls["n"] == service.MAX_IDEMPOTENCY_RACE_RETRIES


async def test_open_does_not_retry_unique_violation(monkeypatch):
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        raise _dbapi_error("23505")

    with pytest.raises(DBAPIError):
        await _patched_open(monkeypatch, fake_once)
    assert calls["n"] == 1
