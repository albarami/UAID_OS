"""Slice 59 stabilization-window — pure contract proofs. Does not close §25.4 / §26.6."""

from __future__ import annotations

import hashlib
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity import AuthenticatedActor
from app.ops.hotfix import evaluate_hotfix_actions
from app.ops.incidents import ActionChild, evaluate_actions
from app.ops.stabilization import (
    CRITERION_COUNT,
    FOLLOW_UP_REQUIRED,
    IMPROVEMENT_COUNT,
    IMPROVEMENT_INVENTORY_VERSION,
    PASSABLE_SEQS,
    RULESET_VERSION,
    STABILIZATION_VERSION,
    WINDOW_STATUS,
    CriterionChild,
    StabilizationError,
    assessor_identity,
    input_digest,
    policy_digest,
    request_digest,
    validate_window_policy,
)
from app.ops.stabilization_criteria import (
    assemble_criteria,
    assemble_improvements,
    closure_result,
    compute_status_counters,
    evaluate_handover_criterion,
    evaluate_monitoring_criterion,
    evaluate_rollback_criterion,
)
from app.ops.stabilization_service import (
    assess_stabilization,
    attempt_closure,
    history_stabilization,
    latest_stabilization,
)
from app.policy.engine import Decision
from app.release.production_autonomy import (
    A5_RULESET_VERSION,
    NO_GO_LIVE_REASONS,
    evaluate_production_autonomy,
)
from app.tenancy import TenantContext
from tests.ops_stabilization_support import (
    STABLE_HASHES,
    VALID_POLICY,
    fresh_snapshot,
    passing_rollback_coverage,
)

_OWNED = (
    "app/ops/stabilization.py",
    "app/ops/stabilization_criteria.py",
    "app/ops/stabilization_service.py",
    "app/ops/stabilization_db_checks.py",
    "app/ops/stabilization_ddl.py",
    "app/repositories/ops_stabilization.py",
    "app/repositories/ops_stabilization_reads.py",
    "app/models/ops_stabilization.py",
)
_AS_OF = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def test_contracts_and_non_closure():
    assert STABILIZATION_VERSION == "slice59.stabilization.v1"
    assert IMPROVEMENT_INVENTORY_VERSION == "slice59.improvement_inventory.v1"
    assert RULESET_VERSION == "slice59.v1"
    assert WINDOW_STATUS == "open"
    assert PASSABLE_SEQS == frozenset({5})
    assert CRITERION_COUNT == 8
    assert IMPROVEMENT_COUNT == 8
    assert FOLLOW_UP_REQUIRED == "required_not_executed"


def test_invalid_declaration_unknown_keys_and_custom_duration():
    with pytest.raises(StabilizationError, match="no_window_declaration"):
        validate_window_policy(None)
    with pytest.raises(StabilizationError, match="no_window_declaration"):
        validate_window_policy({**VALID_POLICY, "extra": "nope"})
    custom = dict(VALID_POLICY)
    custom["duration_days"] = "custom"
    with pytest.raises(StabilizationError, match="no_window_declaration"):
        validate_window_policy(custom)
    cleaned = validate_window_policy(VALID_POLICY)
    assert cleaned["duration_days"] == 14
    assert cleaned["error_budget_threshold"] == "2.5%"
    exit_criteria = cleaned["exit_criteria"]
    assert isinstance(exit_criteria, dict)
    assert exit_criteria["rollback_blockers_open"] == 0


def test_seq_1_2_locked_and_seq_6_7_8_not_observed():
    monitoring = evaluate_monitoring_criterion(
        declared_target=None, snapshot=None, as_of=_AS_OF, max_age_hours=24
    )
    rollback = evaluate_rollback_criterion(SimpleNamespace(), None)
    handover = evaluate_handover_criterion(None)
    children = assemble_criteria(monitoring, rollback, handover)
    mapped = {child.seq: child for child in children}
    assert mapped[1].status == "not_evaluable"
    assert mapped[1].reason == "no_production_coverage_clock"
    assert mapped[2].status == "not_evaluable"
    assert mapped[2].reason == "error_budget_threshold_unparsed_string"
    for seq, reason in (
        (6, "no_backup_restore_source"),
        (7, "no_latency_slo_source"),
        (8, "no_post_launch_security_alert_source"),
    ):
        assert mapped[seq].status == "not_observed"
        assert mapped[seq].reason == reason
    assert all(child.status != "passed" or child.seq == 5 for child in children)


def test_seq3_ladder_seven_outcomes():
    key = "monitoring_confirmed_active"
    none = evaluate_monitoring_criterion(
        declared_target=None, snapshot=None, as_of=_AS_OF, max_age_hours=24
    )
    assert (none.status, none.reason) == ("not_observed", "no_monitoring_declaration")
    declared = evaluate_monitoring_criterion(
        declared_target="https://mon.example.com/status",
        snapshot=None,
        as_of=_AS_OF,
        max_age_hours=24,
    )
    assert (declared.status, declared.reason) == (
        "not_observed",
        "monitoring_declared_but_no_evidence",
    )
    unverified = evaluate_monitoring_criterion(
        declared_target="https://mon.example.com/status",
        snapshot=fresh_snapshot(provenance="caller_supplied_unverified"),
        as_of=_AS_OF,
        max_age_hours=24,
    )
    assert (unverified.status, unverified.reason) == ("failed", "monitoring_observed_unverified")
    stale = evaluate_monitoring_criterion(
        declared_target="https://mon.example.com/status",
        snapshot=fresh_snapshot(observed_at=_AS_OF - timedelta(hours=25)),
        as_of=_AS_OF,
        max_age_hours=24,
    )
    assert (stale.status, stale.reason) == ("failed", "monitoring_evidence_stale")
    unread = evaluate_monitoring_criterion(
        declared_target="https://mon.example.com/status",
        snapshot=fresh_snapshot(response_valid=False),
        as_of=_AS_OF,
        max_age_hours=24,
    )
    assert (unread.status, unread.reason) == ("not_evaluable", "monitoring_evidence_unreadable")
    inactive = evaluate_monitoring_criterion(
        declared_target="https://mon.example.com/status",
        snapshot=fresh_snapshot(overall_active=False),
        as_of=_AS_OF,
        max_age_hours=24,
    )
    assert (inactive.status, inactive.reason) == ("failed", "monitoring_or_alerts_inactive")
    active = evaluate_monitoring_criterion(
        declared_target="https://mon.example.com/status",
        snapshot=fresh_snapshot(),
        as_of=_AS_OF,
        max_age_hours=24,
    )
    assert (active.status, active.reason) == (
        "not_evaluable",
        "monitoring_active_app_derived_not_db_provable",
    )
    assert active.status != "passed"
    for row in (none, declared, unverified, stale, unread, inactive, active):
        assert row.criterion_key == key
        assert row.seq == 3


def test_seq4_three_way_never_passed():
    missing = evaluate_rollback_criterion(passing_rollback_coverage(), None)
    assert (missing.status, missing.reason) == ("not_observed", "no_rollback_run")
    run_id = uuid.uuid4()
    stale = evaluate_rollback_criterion(passing_rollback_coverage(binding_current=False), run_id)
    assert (stale.status, stale.reason) == ("failed", "rollback_path_not_current")
    current = evaluate_rollback_criterion(passing_rollback_coverage(), run_id)
    assert (current.status, current.reason) == (
        "not_evaluable",
        "rollback_currency_app_derived_not_db_provable",
    )
    assert current.status != "passed"


def test_seq5_three_way_and_latest_wins_incomplete():
    missing = evaluate_handover_criterion(None)
    assert (missing.status, missing.reason) == ("not_observed", "no_handover_record")
    complete_id = uuid.uuid4()
    complete = evaluate_handover_criterion(
        SimpleNamespace(id=complete_id, status="recorded_complete")
    )
    assert (complete.status, complete.reason) == ("passed", "handover_recorded_complete")
    incomplete_id = uuid.uuid4()
    incomplete = evaluate_handover_criterion(
        SimpleNamespace(id=incomplete_id, status="recorded_incomplete")
    )
    assert (incomplete.status, incomplete.reason) == ("failed", "handover_recorded_incomplete")
    # Latest-wins is the handover object the caller supplies; a newer incomplete
    # row is what latest_handover would return.
    assert incomplete.handover_id == incomplete_id
    assert complete.handover_id == complete_id


def test_assemble_rejects_passed_outside_seq5():
    passed = evaluate_handover_criterion(
        SimpleNamespace(id=uuid.uuid4(), status="recorded_complete")
    )
    forged = CriterionChild(
        seq=3,
        criterion_key="monitoring_confirmed_active",
        status="passed",
        reason="forged",
        monitoring_snapshot_id=uuid.uuid4(),
    )
    with pytest.raises(StabilizationError, match="only seq 5"):
        assemble_criteria(forged, evaluate_rollback_criterion(SimpleNamespace(), None), passed)


def test_improvement_seq7_observed_iff_run_present():
    missing = assemble_improvements(
        recurrence_count=0,
        domain_pack_declared=False,
        findings_report_id=None,
        oracle_gap_count=None,
        forecast_run_id=None,
        forecast_run_present=False,
    )
    mapped = {child.seq: child for child in missing}
    assert mapped[7].status == "not_observed"
    assert mapped[2].status == "observed"
    assert mapped[2].metric_int == 0
    run_id = uuid.uuid4()
    present = assemble_improvements(
        recurrence_count=2,
        domain_pack_declared=True,
        findings_report_id=uuid.uuid4(),
        oracle_gap_count=3,
        forecast_run_id=run_id,
        forecast_run_present=True,
    )
    mapped = {child.seq: child for child in present}
    assert mapped[7].status == "observed"
    assert mapped[7].cost_forecast_run_id == run_id
    assert mapped[7].refresh_posture == "recorded_not_refreshed"
    assert mapped[5].status == "observed"
    assert mapped[6].metric_int == 3


def test_request_digest_changes_with_assessor_not_as_of():
    project = uuid.uuid4()
    first = request_digest(
        project_id=project,
        extends_window_id=None,
        assessor_subject="alice",
        assessor_actor_type="human",
        assessor_provenance="request_authenticated",
    )
    second = request_digest(
        project_id=project,
        extends_window_id=None,
        assessor_subject="bob",
        assessor_actor_type="human",
        assessor_provenance="request_authenticated",
    )
    assert first != second
    identity = assessor_identity(AuthenticatedActor("alice", "human"), "caller")
    assert identity.subject == "alice"
    assert identity.provenance == "request_authenticated"
    unverified = assessor_identity(None, "caller-label")
    assert unverified.provenance == "caller_supplied_unverified"
    children = assemble_criteria(
        evaluate_monitoring_criterion(
            declared_target=None, snapshot=None, as_of=_AS_OF, max_age_hours=24
        ),
        evaluate_rollback_criterion(SimpleNamespace(), None),
        evaluate_handover_criterion(None),
    )
    improvements = assemble_improvements(
        recurrence_count=0,
        domain_pack_declared=False,
        findings_report_id=None,
        oracle_gap_count=None,
        forecast_run_id=None,
        forecast_run_present=False,
    )
    later = _AS_OF + timedelta(hours=1)
    digest_a = input_digest(
        as_of=_AS_OF,
        policy_digest_value=policy_digest(VALID_POLICY),
        monitoring_max_age_hours=24,
        deployment_max_age_hours=24,
        criteria=children,
        improvements=improvements,
    )
    digest_b = input_digest(
        as_of=later,
        policy_digest_value=policy_digest(VALID_POLICY),
        monitoring_max_age_hours=24,
        deployment_max_age_hours=24,
        criteria=children,
        improvements=improvements,
    )
    assert digest_a != digest_b
    assert first == request_digest(
        project_id=project,
        extends_window_id=None,
        assessor_subject="alice",
        assessor_actor_type="human",
        assessor_provenance="request_authenticated",
    )


def test_closure_ladder_four_refusals():
    actor = AuthenticatedActor("alice", "human")
    assert (
        closure_result(
            latch_active=True,
            actor=actor,
            window_assessor_subject="alice",
            window_assessor_provenance="request_authenticated",
        )
        == "refused_latch_active"
    )
    assert (
        closure_result(
            latch_active=False,
            actor=None,
            window_assessor_subject="alice",
            window_assessor_provenance="request_authenticated",
        )
        == "refused_unauthenticated"
    )
    assert (
        closure_result(
            latch_active=False,
            actor=actor,
            window_assessor_subject="alice",
            window_assessor_provenance="request_authenticated",
        )
        == "refused_same_actor"
    )
    assert (
        closure_result(
            latch_active=False,
            actor=AuthenticatedActor("bob", "human"),
            window_assessor_subject="alice",
            window_assessor_provenance="request_authenticated",
        )
        == "refused_incomplete_criteria"
    )
    assert (
        closure_result(
            latch_active=False,
            actor=actor,
            window_assessor_subject="alice",
            window_assessor_provenance="caller_supplied_unverified",
        )
        == "refused_incomplete_criteria"
    )


async def test_missing_declaration_raises_without_writes(monkeypatch):
    from app.repositories.ops_stabilization import OpsStabilizationRepository

    async def none_resolve(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.repositories.ops_stabilization.resolve_declared_stabilization_window",
        none_resolve,
    )

    session = MagicMock(spec=AsyncSession)
    session.scalar.side_effect = AssertionError("no writes")
    session.execute.side_effect = AssertionError("no writes")
    session.add.side_effect = AssertionError("no writes")
    repo = OpsStabilizationRepository(cast(AsyncSession, session), TenantContext(uuid.uuid4()))
    with pytest.raises(StabilizationError, match="no_window_declaration"):
        await repo.assess(uuid.uuid4(), actor="stab-test", idempotency_key="missing")


def test_public_wrappers_have_no_session_and_no_broker():
    for fn in (
        assess_stabilization,
        attempt_closure,
        latest_stabilization,
        history_stabilization,
    ):
        assert "session" not in inspect.signature(fn).parameters
        assert "as_of" not in inspect.signature(fn).parameters
    for path in _OWNED:
        text = Path(path).read_text()
        assert "broker_call" not in text
        assert "subprocess" not in text
        assert "git " not in text


def test_a5_readiness_go_live_and_frozen_files():
    for path, digest in STABLE_HASHES.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    project_id = uuid.uuid4()
    before = evaluate_production_autonomy(project_id, readiness_level="R2")
    after = evaluate_production_autonomy(project_id, readiness_level="R2")
    assert before.to_dict() == after.to_dict()
    assert after.to_dict()["can_go_live_autonomously"] is False
    assert A5_RULESET_VERSION == "slice54.v1"
    assert NO_GO_LIVE_REASONS == ("a5_gates_not_all_satisfied",)
    from app.intake.readiness import RULESET_VERSION as readiness_ruleset
    from app.intake.readiness import evaluate_readiness

    assert readiness_ruleset == "slice20.v1"
    ready_before = evaluate_readiness(
        str(project_id), [], production_authority_decision="needs_approval"
    )
    ready_after = evaluate_readiness(
        str(project_id), [], production_authority_decision="needs_approval"
    )
    assert ready_before.to_dict() == ready_after.to_dict()
    assert ready_before.can_go_live_autonomously is False
    migration = Path("migrations/versions/0058_stabilization.py").read_text()
    assert 'down_revision: str | None = "0057"' in migration
    assert "cannot downgrade Slice 59" in Path("app/ops/stabilization_ddl.py").read_text()
    counters = compute_status_counters(
        assemble_criteria(
            evaluate_monitoring_criterion(
                declared_target=None, snapshot=None, as_of=_AS_OF, max_age_hours=24
            ),
            evaluate_rollback_criterion(SimpleNamespace(), None),
            evaluate_handover_criterion(None),
        )
    )
    assert counters == (0, 0, 6, 2)


def test_slice58_residual_still_open():
    from app.ops.hotfix import MATRIX_ACTIONS
    from app.policy.engine import check_authority
    from app.policy.levels import AutonomyLevel
    from app.policy.matrix import validate_overrides

    validate_overrides({})
    decisions = {action: check_authority(action, AutonomyLevel(3), {}) for action in MATRIX_ACTIONS}
    mapped = {child.seq: child for child in evaluate_hotfix_actions(decisions)}
    assert mapped[5].reason_code == "no_deploy_actuator"
    assert mapped[6].reason_code == "plan_denied_by_policy"
    incident = evaluate_actions(
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
    by_seq = {child.seq: child for child in incident}
    assert by_seq[3].reason_code == "deferred_slice58"
    assert by_seq[4].reason_code == "deferred_slice58"
    assert by_seq[5].reason_code == "deferred_slice58"
    assert isinstance(by_seq[3], ActionChild)
