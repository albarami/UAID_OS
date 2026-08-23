"""Postgres CHECK fragments for Slice-59 stabilization-window results.

Consumed by the ORM and migration ``0058`` only.
"""

from __future__ import annotations

CRITERION_SEQ_KEY_SQL = (
    "(seq=1 AND criterion_key='zero_open_critical_incidents_for_days') OR "
    "(seq=2 AND criterion_key='error_budget_under_threshold') OR "
    "(seq=3 AND criterion_key='monitoring_confirmed_active') OR "
    "(seq=4 AND criterion_key='rollback_blockers_open') OR "
    "(seq=5 AND criterion_key='support_handover_complete') OR "
    "(seq=6 AND criterion_key='backup_restore_validated') OR "
    "(seq=7 AND criterion_key='p95_latency_within_slo') OR "
    "(seq=8 AND criterion_key='no_unresolved_security_alerts')"
)

CRITERION_STATUS_SQL = (
    "("
    "seq=1 AND status='not_evaluable' AND reason='no_production_coverage_clock' "
    "AND monitoring_snapshot_id IS NULL AND rollback_verification_run_id IS NULL "
    "AND handover_id IS NULL"
    ") OR ("
    "seq=2 AND status='not_evaluable' AND reason='error_budget_threshold_unparsed_string' "
    "AND monitoring_snapshot_id IS NULL AND rollback_verification_run_id IS NULL "
    "AND handover_id IS NULL"
    ") OR ("
    "seq=3 AND status IN ('not_observed','failed','not_evaluable') "
    "AND rollback_verification_run_id IS NULL AND handover_id IS NULL AND ("
    "(reason IN ('no_monitoring_declaration','monitoring_declared_but_no_evidence') "
    "AND monitoring_snapshot_id IS NULL) OR "
    "(reason IN ('monitoring_observed_unverified','monitoring_evidence_stale',"
    "'monitoring_evidence_unreadable','monitoring_or_alerts_inactive',"
    "'monitoring_active_app_derived_not_db_provable') "
    "AND monitoring_snapshot_id IS NOT NULL)"
    ")"
    ") OR ("
    "seq=4 AND status IN ('not_observed','failed','not_evaluable') "
    "AND monitoring_snapshot_id IS NULL AND handover_id IS NULL AND ("
    "(reason='no_rollback_run' AND rollback_verification_run_id IS NULL) OR "
    "(reason IN ('rollback_path_not_current',"
    "'rollback_currency_app_derived_not_db_provable') "
    "AND rollback_verification_run_id IS NOT NULL)"
    ")"
    ") OR ("
    "seq=5 AND monitoring_snapshot_id IS NULL AND rollback_verification_run_id IS NULL AND ("
    "(status='not_observed' AND reason='no_handover_record' AND handover_id IS NULL) OR "
    "(status='passed' AND reason='handover_recorded_complete' AND handover_id IS NOT NULL) OR "
    "(status='failed' AND reason='handover_recorded_incomplete' AND handover_id IS NOT NULL)"
    ")"
    ") OR ("
    "seq=6 AND status='not_observed' AND reason='no_backup_restore_source' "
    "AND monitoring_snapshot_id IS NULL AND rollback_verification_run_id IS NULL "
    "AND handover_id IS NULL"
    ") OR ("
    "seq=7 AND status='not_observed' AND reason='no_latency_slo_source' "
    "AND monitoring_snapshot_id IS NULL AND rollback_verification_run_id IS NULL "
    "AND handover_id IS NULL"
    ") OR ("
    "seq=8 AND status='not_observed' AND reason='no_post_launch_security_alert_source' "
    "AND monitoring_snapshot_id IS NULL AND rollback_verification_run_id IS NULL "
    "AND handover_id IS NULL"
    ")"
)

PASSED_ONLY_SEQ5_SQL = "(status<>'passed' OR seq=5)"

IMPROVEMENT_SEQ_CLASS_SQL = (
    "(seq=1 AND improvement_class='lessons_learned') OR "
    "(seq=2 AND improvement_class='recurring_failure_patterns') OR "
    "(seq=3 AND improvement_class='agent_evals') OR "
    "(seq=4 AND improvement_class='prompt_templates') OR "
    "(seq=5 AND improvement_class='domain_pack_gaps') OR "
    "(seq=6 AND improvement_class='test_oracle_gaps') OR "
    "(seq=7 AND improvement_class='cost_forecasts') OR "
    "(seq=8 AND improvement_class='connector_reliability_scores')"
)

IMPROVEMENT_STATUS_SQL = (
    "("
    "seq=1 AND status='not_observed' AND reason='no_lessons_store' "
    "AND findings_report_id IS NULL AND cost_forecast_run_id IS NULL "
    "AND metric_int IS NULL AND refresh_posture IS NULL"
    ") OR ("
    "seq=2 AND status='observed' AND reason='incident_category_recurrence' "
    "AND findings_report_id IS NULL AND cost_forecast_run_id IS NULL "
    "AND metric_int IS NOT NULL AND metric_int >= 0 AND refresh_posture IS NULL"
    ") OR ("
    "seq=3 AND status='not_observed' AND reason='no_live_eval_update' "
    "AND findings_report_id IS NULL AND cost_forecast_run_id IS NULL "
    "AND metric_int IS NULL AND refresh_posture IS NULL"
    ") OR ("
    "seq=4 AND status='not_observed' AND reason='no_prompt_store' "
    "AND findings_report_id IS NULL AND cost_forecast_run_id IS NULL "
    "AND metric_int IS NULL AND refresh_posture IS NULL"
    ") OR ("
    "seq=5 AND cost_forecast_run_id IS NULL AND findings_report_id IS NULL "
    "AND metric_int IS NULL AND refresh_posture IS NULL AND ("
    "(status='observed' AND reason='domain_pack_declared') OR "
    "(status='not_observed' AND reason='no_domain_pack_declaration')"
    ")"
    ") OR ("
    "seq=6 AND cost_forecast_run_id IS NULL AND refresh_posture IS NULL AND ("
    "(status='observed' AND reason='acceptance_without_oracle_count' "
    "AND findings_report_id IS NOT NULL AND metric_int IS NOT NULL AND metric_int >= 0) OR "
    "(status='not_observed' AND reason='no_findings_report' "
    "AND findings_report_id IS NULL AND metric_int IS NULL)"
    ")"
    ") OR ("
    "seq=7 AND findings_report_id IS NULL AND metric_int IS NULL AND ("
    "(status='observed' AND reason='forecast_cited_not_refreshed' "
    "AND cost_forecast_run_id IS NOT NULL AND refresh_posture='recorded_not_refreshed') OR "
    "(status='not_observed' AND reason='no_cost_forecast_run' "
    "AND cost_forecast_run_id IS NULL AND refresh_posture IS NULL)"
    ")"
    ") OR ("
    "seq=8 AND status='not_observed' AND reason='no_connector_score_store' "
    "AND findings_report_id IS NULL AND cost_forecast_run_id IS NULL "
    "AND metric_int IS NULL AND refresh_posture IS NULL"
    ")"
)

WINDOW_COUNTER_SQL = (
    "passed_count >= 0 AND failed_count >= 0 AND not_observed_count >= 0 "
    "AND not_evaluable_count >= 0 "
    "AND passed_count + failed_count + not_observed_count + not_evaluable_count = 8"
)

ASSESSOR_SHAPE_SQL = (
    "(assessor_provenance='request_authenticated' "
    "AND assessor_actor_type IN ('human','service')) OR "
    "(assessor_provenance='caller_supplied_unverified' AND assessor_actor_type IS NULL)"
)

CRITERION_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("seq_bounded", "seq BETWEEN 1 AND 8"),
    ("seq_key_pair", CRITERION_SEQ_KEY_SQL),
    ("status_by_seq", CRITERION_STATUS_SQL),
    ("passed_only_seq5", PASSED_ONLY_SEQ5_SQL),
)

IMPROVEMENT_CHECK_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("seq_bounded", "seq BETWEEN 1 AND 8"),
    ("seq_class_pair", IMPROVEMENT_SEQ_CLASS_SQL),
    ("status_by_seq", IMPROVEMENT_STATUS_SQL),
)
