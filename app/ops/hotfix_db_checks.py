"""Postgres CHECK fragments for Slice-58 hotfix-intent results.

Consumed by the ORM and migration ``0057`` only.
"""

from __future__ import annotations

SEQ_ACTION_SQL = (
    "(seq=3 AND action='create_patch_branch' AND matrix_action='create_branches' "
    "AND policy_decision IN ('allow','deny','needs_approval')) OR "
    "(seq=4 AND action='open_hotfix_pr' AND matrix_action='open_pull_requests' "
    "AND policy_decision IN ('allow','deny','needs_approval')) OR "
    "(seq=5 AND action='deploy_staging_hotfix' AND matrix_action='deploy_staging' "
    "AND policy_decision IN ('allow','deny','needs_approval')) OR "
    "(seq=6 AND action='deploy_production_hotfix' AND matrix_action='deploy_production' "
    "AND policy_decision IN ('allow','deny','needs_approval')) OR "
    "(seq=7 AND action='rollback_production' AND matrix_action='deploy_production' "
    "AND policy_decision IN ('allow','deny','needs_approval'))"
)

POSTURE_SQL = (
    "("
    "seq=3 AND ("
    "(policy_decision='allow' AND execution_posture='local_branch_plan_written' "
    "AND plan_id IS NOT NULL AND plan_kind='patch_branch' AND reason_code='plan_written') OR "
    "(policy_decision='deny' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_denied_by_policy') OR "
    "(policy_decision='needs_approval' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_needs_approval')"
    ")"
    ") OR ("
    "seq=4 AND ("
    "(policy_decision='allow' AND execution_posture='local_pr_plan_written' "
    "AND plan_id IS NOT NULL AND plan_kind='hotfix_pr' AND reason_code='plan_written') OR "
    "(policy_decision='allow' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='branch_plan_required') OR "
    "(policy_decision='deny' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_denied_by_policy') OR "
    "(policy_decision='needs_approval' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_needs_approval')"
    ")"
    ") OR ("
    "seq=5 AND ("
    "(policy_decision='allow' AND execution_posture='staging_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='no_deploy_actuator') OR "
    "(policy_decision='deny' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_denied_by_policy') OR "
    "(policy_decision='needs_approval' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_needs_approval')"
    ")"
    ") OR ("
    "seq IN (6,7) AND ("
    "(policy_decision='allow' AND execution_posture='production_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='production_not_executed') OR "
    "(policy_decision='deny' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_denied_by_policy') OR "
    "(policy_decision='needs_approval' AND execution_posture='recorded_not_executed' "
    "AND plan_id IS NULL AND plan_kind IS NULL AND reason_code='plan_needs_approval')"
    ")"
    ")"
)

CHILD_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("seq_bounded", "seq BETWEEN 3 AND 7"),
    ("seq_action_pair", SEQ_ACTION_SQL),
    ("posture_by_action", POSTURE_SQL),
)

DECISION_SNAPSHOT_SQL = (
    "jsonb_typeof(decision_snapshot)='object' "
    "AND (decision_snapshot - 'create_branches' - 'open_pull_requests' "
    "- 'deploy_staging' - 'deploy_production') = '{}'::jsonb "
    "AND decision_snapshot ? 'create_branches' "
    "AND decision_snapshot ? 'open_pull_requests' "
    "AND decision_snapshot ? 'deploy_staging' "
    "AND decision_snapshot ? 'deploy_production' "
    "AND decision_snapshot->>'create_branches' IN ('allow','deny','needs_approval') "
    "AND decision_snapshot->>'open_pull_requests' IN ('allow','deny','needs_approval') "
    "AND decision_snapshot->>'deploy_staging' IN ('allow','deny','needs_approval') "
    "AND decision_snapshot->>'deploy_production' IN ('allow','deny','needs_approval')"
)
