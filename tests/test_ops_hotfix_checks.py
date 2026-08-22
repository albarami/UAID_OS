"""Slice 58 CHECK contract fragments. Docker-free."""

from __future__ import annotations

from app.ops.hotfix_db_checks import DECISION_SNAPSHOT_SQL, POSTURE_SQL, SEQ_ACTION_SQL


def test_posture_sql_is_policy_first():
    assert "plan_denied_by_policy" in POSTURE_SQL
    assert "plan_needs_approval" in POSTURE_SQL
    assert "branch_plan_required" in POSTURE_SQL
    assert "no_deploy_actuator" in POSTURE_SQL
    assert "plan_kind='patch_branch'" in POSTURE_SQL
    assert "plan_kind='hotfix_pr'" in POSTURE_SQL
    assert "seq IN (6,7)" in POSTURE_SQL
    assert "create_patch_branch" in SEQ_ACTION_SQL
    assert "'{}'::jsonb" in DECISION_SNAPSHOT_SQL
