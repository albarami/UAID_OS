"""Postgres CHECK fragments for Slice-57 incident action results.

Consumed by the ORM and migration ``0056`` only. Do not import from
``app.ops.db_checks`` (frozen Slice-56 0055 importer).
"""

from __future__ import annotations

SEQ_ACTION_SQL = (
    "(seq=1 AND action='create_bug_ticket' AND matrix_action='create_project_tasks' "
    "AND policy_decision IN ('allow','deny','needs_approval')) OR "
    "(seq=2 AND action='diagnose_log_error' AND matrix_action='none' "
    "AND policy_decision='not_evaluated') OR "
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
    "seq=1 AND ("
    "(policy_decision='allow' AND execution_posture='local_ticket_written' "
    "AND ticket_id IS NOT NULL AND reason_code='ticket_written') OR "
    "(policy_decision<>'allow' AND execution_posture='recorded_not_executed' "
    "AND ticket_id IS NULL AND reason_code='ticket_denied_by_policy')"
    ")"
    ") OR ("
    "seq=2 AND execution_posture='recorded_not_executed' AND ticket_id IS NULL "
    "AND reason_code='no_log_source'"
    ") OR ("
    "seq BETWEEN 3 AND 5 AND execution_posture='recorded_not_executed' "
    "AND ticket_id IS NULL AND reason_code='deferred_slice58'"
    ") OR ("
    "seq IN (6,7) AND execution_posture='recorded_not_executed' "
    "AND ticket_id IS NULL AND reason_code='production_not_executed'"
    ")"
)

CHILD_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("seq_bounded", "seq BETWEEN 1 AND 7"),
    ("seq_action_pair", SEQ_ACTION_SQL),
    ("posture_by_action", POSTURE_SQL),
)
