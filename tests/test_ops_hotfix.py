"""Slice 58 hotfix-intent — pure contract proofs. Does not close §26.6."""

from __future__ import annotations

import hashlib
import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.ops.hotfix import (
    ACTION_COUNT,
    ACTIONS,
    GATE10_CONTEXT_KEYS,
    HOTFIX_INTENT_VERSION,
    HOTFIX_PLAN_VERSION,
    MATRIX_ACTIONS,
    RULESET_VERSION,
    HotfixError,
    HotfixIdempotencyRace,
    authorization_matches,
    bind_plans,
    evaluate_hotfix_actions,
    gate10_conjunction_passed,
    incident_is_evaluable,
    local_intended_ref,
    policy_input_digest,
    request_digest,
)
from app.ops.hotfix_service import (
    evaluate_hotfix_intent,
    history_hotfix_intent,
    latest_hotfix_intent,
)
from app.ops.incidents import ActionChild, evaluate_actions
from app.policy.engine import Decision, check_authority
from app.policy.levels import AutonomyLevel
from app.policy.matrix import validate_overrides
from app.release.production_autonomy import (
    A5_RULESET_VERSION,
    NO_GO_LIVE_REASONS,
    evaluate_production_autonomy,
)
from app.tenancy import TenantContext
from tests.ops_hotfix_support import DB_CHECKS_SHA, INCIDENTS_SHA

_STABLE = {
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": ("7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26"),
    "app/runtime/control_loop.py": (
        "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180"
    ),
    "app/ops/incidents.py": INCIDENTS_SHA,
}
_OWNED = (
    "app/ops/hotfix.py",
    "app/ops/hotfix_service.py",
    "app/ops/hotfix_db_checks.py",
    "app/ops/hotfix_ddl.py",
    "app/repositories/ops_hotfix.py",
    "app/models/ops_hotfix.py",
)


def _by_seq(children):
    return {child.seq: child for child in children}


def _decisions(level: int, overrides: dict | None = None) -> dict[str, Decision]:
    payload = overrides or {}
    validate_overrides(payload)
    return {
        action: check_authority(action, AutonomyLevel(level), payload) for action in MATRIX_ACTIONS
    }


def _passing_coverage(**overrides) -> SimpleNamespace:
    flags: dict[str, object] = {key: True for key in GATE10_CONTEXT_KEYS}
    flags["attempt_failed"] = False
    flags["phase_count"] = 5
    flags["execution_observation"] = "connector_observed_ci"
    flags.update(overrides)
    return SimpleNamespace(**flags)


def test_contracts_and_non_closure():
    assert HOTFIX_INTENT_VERSION == "slice58.hotfix_intent.v1"
    assert HOTFIX_PLAN_VERSION == "slice58.hotfix_plan.v1"
    assert RULESET_VERSION == "slice58.v1"
    assert ACTION_COUNT == 5
    assert ACTIONS[0] == (3, "create_patch_branch", "create_branches")
    assert not incident_is_evaluable("resolved")
    assert incident_is_evaluable("open")
    ref = local_intended_ref("patch_branch", uuid.UUID(int=1))
    assert ref.startswith("local:patch_branch:")
    with pytest.raises(HotfixError):
        local_intended_ref("git_branch", uuid.uuid4())


def test_missing_policy_and_a0_write_no_plans():
    missing = evaluate_hotfix_actions({action: Decision.DENY for action in MATRIX_ACTIONS})
    a0 = evaluate_hotfix_actions(_decisions(0))
    for children in (missing, a0):
        mapped = _by_seq(children)
        assert mapped[3].reason_code == "plan_denied_by_policy"
        assert mapped[4].reason_code == "plan_denied_by_policy"
        assert mapped[5].reason_code == "plan_denied_by_policy"
        assert mapped[6].reason_code == "plan_denied_by_policy"
        assert mapped[3].plan_id is None
    with pytest.raises(HotfixError, match="missing policy decision"):
        evaluate_hotfix_actions({})


def test_a2_writes_branch_and_pr_plans():
    mapped = _by_seq(evaluate_hotfix_actions(_decisions(2)))
    assert mapped[3].policy_decision == "allow"
    assert mapped[3].execution_posture == "local_branch_plan_written"
    assert mapped[4].execution_posture == "local_pr_plan_written"
    assert mapped[5].reason_code == "plan_denied_by_policy"
    assert mapped[6].reason_code == "plan_denied_by_policy"
    branch = uuid.uuid4()
    pr = uuid.uuid4()
    bound = bind_plans(evaluate_hotfix_actions(_decisions(2)), branch_plan_id=branch, pr_plan_id=pr)
    assert _by_seq(bound)[3].plan_id == branch
    assert _by_seq(bound)[3].plan_kind == "patch_branch"
    assert _by_seq(bound)[4].plan_kind == "hotfix_pr"


def test_a2_requires_approval_writes_zero_plans():
    mapped = _by_seq(
        evaluate_hotfix_actions(
            _decisions(
                2,
                {
                    "create_branches": {"requires_approval": True},
                    "open_pull_requests": {"requires_approval": True},
                },
            )
        )
    )
    assert mapped[3].reason_code == "plan_needs_approval"
    assert mapped[4].reason_code == "plan_needs_approval"
    assert mapped[3].execution_posture == "recorded_not_executed"


def test_branch_denied_pr_allowed_requires_branch_plan():
    mapped = _by_seq(evaluate_hotfix_actions(_decisions(2, {"create_branches": {"allow": False}})))
    assert mapped[3].reason_code == "plan_denied_by_policy"
    assert mapped[4].policy_decision == "allow"
    assert mapped[4].reason_code == "branch_plan_required"
    assert mapped[4].plan_id is None


def test_staging_deny_outranks_actuator_absence():
    mapped = _by_seq(evaluate_hotfix_actions(_decisions(2)))
    assert mapped[5].policy_decision == "deny"
    assert mapped[5].reason_code == "plan_denied_by_policy"
    assert mapped[5].reason_code != "no_deploy_actuator"


def test_staging_needs_approval_outranks_actuator_absence():
    mapped = _by_seq(
        evaluate_hotfix_actions(_decisions(3, {"deploy_staging": {"requires_approval": True}}))
    )
    assert mapped[5].policy_decision == "needs_approval"
    assert mapped[5].reason_code == "plan_needs_approval"
    assert mapped[3].reason_code == "plan_written"


def test_a3_staging_allow_is_not_executed():
    mapped = _by_seq(evaluate_hotfix_actions(_decisions(3)))
    assert mapped[5].policy_decision == "allow"
    assert mapped[5].execution_posture == "staging_not_executed"
    assert mapped[5].reason_code == "no_deploy_actuator"
    assert mapped[6].reason_code == "plan_denied_by_policy"


def test_a5_production_needs_approval_never_a_plan():
    mapped = _by_seq(evaluate_hotfix_actions(_decisions(5)))
    assert mapped[6].policy_decision == "needs_approval"
    assert mapped[6].reason_code == "plan_needs_approval"
    assert mapped[7].reason_code == "plan_needs_approval"
    assert mapped[6].plan_id is None
    assert mapped[5].reason_code == "no_deploy_actuator"


def test_gate10_conjunction_rejects_stored_eligible_when_stale():
    passing = _passing_coverage()
    assert gate10_conjunction_passed(passing) is True
    stale_binding = _passing_coverage(binding_current=False)
    assert stale_binding.gate_eligible is True
    assert gate10_conjunction_passed(stale_binding) is False
    stale_snapshot = _passing_coverage(staging_snapshot_fresh=False)
    assert stale_snapshot.gate_eligible is True
    assert gate10_conjunction_passed(stale_snapshot) is False


def test_old_authorization_does_not_match_current_graph():
    current = uuid.uuid4()
    old = uuid.uuid4()
    digest = "sha256:" + "ab" * 32
    other = "sha256:" + "cd" * 32
    assert (
        authorization_matches(
            binding_id=current,
            candidate_id=current,
            evidence_pack_id=current,
            rollback_run_id=current,
            binding_digest=digest,
            authorization_binding_id=current,
            authorization_candidate_id=current,
            authorization_pack_id=current,
            authorization_run_id=current,
            authorization_digest=digest,
            result_code="authorized_not_executed",
        )
        is True
    )
    assert (
        authorization_matches(
            binding_id=current,
            candidate_id=current,
            evidence_pack_id=current,
            rollback_run_id=current,
            binding_digest=digest,
            authorization_binding_id=old,
            authorization_candidate_id=current,
            authorization_pack_id=current,
            authorization_run_id=current,
            authorization_digest=digest,
            result_code="authorized_not_executed",
        )
        is False
    )
    assert (
        authorization_matches(
            binding_id=current,
            candidate_id=current,
            evidence_pack_id=current,
            rollback_run_id=current,
            binding_digest=digest,
            authorization_binding_id=current,
            authorization_candidate_id=current,
            authorization_pack_id=current,
            authorization_run_id=current,
            authorization_digest=other,
            result_code="authorized_not_executed",
        )
        is False
    )


def test_slice57_seq_3_to_5_still_deferred():
    children = evaluate_actions(
        {
            action: Decision.ALLOW
            for action in (
                "create_project_tasks",
                "create_branches",
                "open_pull_requests",
                "deploy_staging",
                "deploy_production",
            )
        }
    )
    mapped = {child.seq: child for child in children}
    assert mapped[3].reason_code == "deferred_slice58"
    assert mapped[4].reason_code == "deferred_slice58"
    assert mapped[5].reason_code == "deferred_slice58"
    assert isinstance(mapped[3], ActionChild)


def test_public_wrappers_have_no_session_and_no_broker():
    for fn in (evaluate_hotfix_intent, latest_hotfix_intent, history_hotfix_intent):
        assert "session" not in inspect.signature(fn).parameters
    for path in _OWNED:
        text = Path(path).read_text()
        assert "broker_call" not in text
        assert "subprocess" not in text
    assert "decision_for(" not in Path("app/ops/hotfix.py").read_text()
    assert "decision_for(" not in Path("app/repositories/ops_hotfix.py").read_text()
    assert "snapshot_decisions(" in Path("app/repositories/ops_hotfix.py").read_text()
    owned = Path("app/repositories/ops_hotfix.py").read_text()
    assert "_latest_gate10_run" not in owned
    assert "coverage_with_run(" in owned
    assert "authorization_matches(" in owned


def test_a5_readiness_go_live_and_frozen_files():
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
    migration = Path("migrations/versions/0057_self_healing.py").read_text()
    assert 'down_revision: str | None = "0056"' in migration
    assert "cannot downgrade Slice 58" in Path("app/ops/hotfix_ddl.py").read_text()
    first = policy_input_digest(
        policy_present=True,
        policy_id=uuid.UUID(int=1),
        autonomy_level=2,
        overrides={"create_branches": {"min_level": 3}},
    )
    second = policy_input_digest(
        policy_present=True,
        policy_id=uuid.UUID(int=1),
        autonomy_level=2,
        overrides={"create_branches": {"min_level": 4}},
    )
    assert first != second
    assert request_digest(uuid.UUID(int=1)) != request_digest(uuid.UUID(int=2))


def _dbapi_error(sqlstate: str) -> DBAPIError:
    original = type("OriginalDatabaseError", (Exception,), {"sqlstate": sqlstate})()
    return DBAPIError("hotfix_retry_probe", {}, original)


async def test_evaluate_retries_then_succeeds(monkeypatch):
    from app.ops import hotfix_service as service

    winner = MagicMock(name="snapshot")
    calls = {"n": 0}

    async def fake_once(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise service._IdempotencyWinnerNotVisible()
        return winner

    monkeypatch.setattr(service, "_evaluate_once", fake_once)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    assert (
        await evaluate_hotfix_intent(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            uuid.uuid4(),
            actor="hotfix-test",
            idempotency_key="retry-key",
        )
        is winner
    )
    assert calls["n"] == 2


async def test_evaluate_exhausts_five_race_retries(monkeypatch):
    from app.ops import hotfix_service as service

    async def fake_once(*_args, **_kwargs):
        raise service._IdempotencyWinnerNotVisible()

    monkeypatch.setattr(service, "_evaluate_once", fake_once)
    monkeypatch.setattr(service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(service.random, "uniform", lambda _a, _b: 0.0)
    with pytest.raises(HotfixIdempotencyRace):
        await evaluate_hotfix_intent(
            TenantContext(uuid.uuid4()),
            uuid.uuid4(),
            uuid.uuid4(),
            actor="hotfix-test",
            idempotency_key="retry-key",
        )
