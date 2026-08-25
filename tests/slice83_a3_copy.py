"""Slice 83 A3 mutation helper: duplicate one existing child row onto its parent."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.slice83_a2_support import commit_writer
from tests.slice83_a3_support import (
    assert_a3_mutation,
    minted_id,
    race_admin,
    race_runtime,
)
from tests.slice83_support import Writer

# table -> (parent_column, insertable columns excluding id / generated)
_COPY: dict[str, tuple[str, str]] = {
    "acceptance_verification_results": (
        "acceptance_verification_run_id",
        "tenant_id, project_id, acceptance_verification_run_id, acceptance_criterion_id, "
        "authorship_record_id, authorship_status, authorship_provenance, source_kind, "
        "eligibility_status, reason_code, created_at",
    ),
    "agent_provided_skills": (
        "capability_id",
        "capability_id, skill_id, can_review, created_at",
    ),
    "agent_realizations": (
        "instance_id",
        "tenant_id, project_id, instance_id, qualification_status, realized_by, "
        "created_at, updated_at, qualified_via_run_id",
    ),
    "catalog_vetting_check_results": (
        "vetting_record_id",
        "vetting_record_id, check_name, passed, created_at",
    ),
    "cost_forecast_dimension_results": (
        "run_id",
        "tenant_id, project_id, run_id, ordinal, dimension_code, forecast_value, "
        "policy_limit, approval_threshold, dimension_digest, created_at",
    ),
    "cost_forecast_input_lines": (
        "run_id",
        "tenant_id, project_id, run_id, ordinal, line_kind, component, remaining_total_usd, "
        "remaining_today_usd, model_route_hash, remaining_input_tokens, remaining_output_tokens, "
        "remaining_today_input_tokens, remaining_today_output_tokens, input_rate_usd_per_1k, "
        "output_rate_usd_per_1k, ci_minutes, source_provenance, line_digest, created_at",
    ),
    "cost_forecast_ledger_event_refs": (
        "run_id",
        "tenant_id, project_id, run_id, cost_event_id, ordinal, component, amount_usd, "
        "occurred_at, material_digest, source_provenance, created_at",
    ),
    "cost_optimizer_citations": (
        "run_id",
        "tenant_id, project_id, run_id, bucket_id, created_at",
    ),
    "cross_project_aggregate_buckets": (
        "run_id",
        "run_id, signal_class, bucket_key, n_events, n_projects, n_tenants, metric_sum, metric_unit",
    ),
    "emergency_control_authority_members": (
        "binding_id",
        "tenant_id, project_id, binding_id, policy_version_id, policy_approver_id, ordinal, "
        "principal_subject_hash, may_activate_stop, may_clear_stop, may_authorize_rollback, "
        "created_at",
    ),
    "emergency_stop_run_effects": (
        "activation_event_id",
        "tenant_id, project_id, activation_event_id, run_id, emergency_run_step_id, "
        "status_before, status_after, effect_code, created_at",
    ),
    "evidence_pack_export_files": (
        "export_record_id",
        "tenant_id, project_id, export_record_id, ordinal, file_name, media_type, content, "
        "byte_count, content_sha256, created_at",
    ),
    "evidence_pack_manifest_signatures": (
        "export_record_id",
        "tenant_id, project_id, export_record_id, signature_algorithm, signing_key_id, "
        "signature_b64, signed_bytes_digest, created_at",
    ),
    "evidence_pack_section_results": (
        "evidence_pack_id",
        "tenant_id, project_id, evidence_pack_id, section_code, presence_code, item_count, "
        "section_digest, required, failure_code, ordinal, created_at",
    ),
    "evidence_pack_source_refs": (
        "evidence_pack_id",
        "tenant_id, project_id, evidence_pack_id, source_kind, source_id, truth_tier, "
        "projection_digest, source_created_at, ordinal, created_at",
    ),
    "evidence_packs": (
        "generation_run_id",
        "tenant_id, project_id, generation_run_id, release_candidate_id, audit_checkpoint_id, "
        "assembly_status, artifact_scope_digest, issue_binding_digest, source_set_digest, "
        "traceability_digest, repo_binding_state, repo_binding_hash, commit_sha, schema_version, "
        "semantic_contract_version, projection_contract_version, audit_contract_version, "
        "canonical_core_text, core_content_hash, verdict_status, signature_status, "
        "source_ref_count, section_count, traceability_edge_count, source_cutoff, generated_at, "
        "created_at",
    ),
    "ops_hotfix_plans": (
        "run_id",
        "tenant_id, project_id, incident_id, run_id, plan_kind, intended_ref, created_at",
    ),
    "ops_improvement_results": (
        "window_id",
        "tenant_id, project_id, window_id, seq, improvement_class, status, reason, "
        "findings_report_id, cost_forecast_run_id, metric_int, refresh_posture, created_at",
    ),
    "ops_incident_action_results": (
        "evaluation_id",
        "tenant_id, project_id, incident_id, evaluation_id, seq, action, matrix_action, "
        "policy_decision, execution_posture, reason_code, ticket_id, created_at",
    ),
    "ops_self_healing_results": (
        "run_id",
        "tenant_id, project_id, incident_id, run_id, seq, action, matrix_action, "
        "policy_decision, execution_posture, reason_code, plan_id, plan_kind, created_at",
    ),
    "ops_signal_results": (
        "run_id",
        "tenant_id, project_id, run_id, seq, signal_class, observation_status, truth_tier, "
        "source_kind, source_table, source_ref, source_digest, window_kind, window_start, "
        "window_end, reason_code, threshold_provenance, threshold_kind, threshold_int, "
        "threshold_ratio, threshold_money, threshold_money_daily, metric_kind, metric_int, "
        "metric_ratio, metric_money, metric_money_daily, threshold_state, created_at",
    ),
    "ops_stabilization_criterion_results": (
        "window_id",
        "tenant_id, project_id, window_id, seq, criterion_key, status, reason, "
        "monitoring_snapshot_id, rollback_verification_run_id, handover_id, created_at",
    ),
    "production_approval_policy_approvers": (
        "policy_version_id",
        "tenant_id, project_id, policy_version_id, ordinal, principal_subject_hash, created_at",
    ),
    "release_verdict_issue_results": (
        "verdict_id",
        "tenant_id, project_id, verdict_id, release_candidate_id, binding_id, issue_id, "
        "risk_acceptance_record_id, ordinal, issue_category, severity, blocking_category, "
        "source_finding_id, issue_status, source_provenance, trusted_provenance, blocking, "
        "hard_blocker, exact_risk_acceptance, risk_authority_verified, issue_projection_digest, "
        "risk_projection_digest, created_at",
    ),
    "reviewer_quality_case_results": (
        "reviewer_quality_record_id",
        "tenant_id, project_id, reviewer_quality_record_id, fixture_suite_id, fixture_case_id, "
        "execution_status, reviewer_decision, response_digest, reported_finding_count, "
        "matched_evidence_count, specific_required_change_count, input_tokens, output_tokens, "
        "latency_ms, created_at",
    ),
    "rollback_verification_phase_results": (
        "run_id",
        "tenant_id, project_id, run_id, ordinal, phase_code, phase_status, result_code, "
        "target_binding_hash, expected_version_digest, observed_version_digest, health_ok, "
        "operation_ok, started_at, completed_at, created_at",
    ),
    "security_scan_category_results": (
        "security_scan_run_id",
        "tenant_id, project_id, security_scan_run_id, category, scanner_key, scanner_version, "
        "rule_pack_hash, coverage_status, reported_finding_count, evidence_digest, created_at",
    ),
    "shortcut_detector_category_results": (
        "shortcut_detector_run_id",
        "tenant_id, project_id, shortcut_detector_run_id, category, deterministic_status, "
        "review_status, coverage_status, deterministic_fingerprints, "
        "reported_reviewer_result_count, reported_finding_count, detector_evidence_digest, "
        "created_at",
    ),
    "test_results": (
        "test_oracle_run_id",
        "tenant_id, project_id, test_oracle_run_id, case_ref, sample_class, result_kind, "
        "expected_digest, observed_digest, reference_digest, observed_numeric, reference_numeric, "
        "tolerance_numeric, evaluator_instance_id, evaluator_version_hash, llm_provider, "
        "llm_model, input_tokens, output_tokens, cost_external_ref, criterion_scores, "
        "judgment_label, created_at",
    ),
}


def copy_child_writer(table: str, parent_id: Any) -> Writer:
    """Insert a copy of one existing child row for ``parent_id`` (new primary key)."""
    parent_column, columns = _COPY[table]
    sql = text(
        f"INSERT INTO {table} ({columns}) "
        f"SELECT {columns} FROM {table} WHERE {parent_column}=:parent LIMIT 1 "
        "RETURNING 1"
    )

    async def writer(session: AsyncSession) -> Any:
        copied = (await session.execute(sql, {"parent": parent_id})).first()
        if copied is None:
            raise AssertionError(f"{table} copy missed parent {parent_id}")
        await session.flush()
        return parent_id

    return writer


async def mutate_copied_child(
    *,
    table: str,
    constraint: str | tuple[str, ...],
    parent_writer: Writer,
    parent_id_of,
    admin_engine: AsyncEngine,
    count_sql: str,
    count_params: dict[str, Any],
    rls_engine: AsyncEngine | None = None,
    tenant_id: Any = None,
    admin: bool = False,
) -> None:
    """Commit one parent, then race two copies of one child onto that parent."""
    parent = await commit_writer(
        admin_engine if admin else rls_engine,
        None if admin else tenant_id,
        parent_writer,
    )
    child = copy_child_writer(table, parent_id_of(parent))

    async def race_admin_path():
        return await race_admin(
            admin_engine=admin_engine,
            writer=child,
            count_sql=count_sql,
            count_params=count_params,
        )

    async def race_runtime_path():
        return await race_runtime(
            rls_engine=rls_engine,
            admin_engine=admin_engine,
            tenant_id=tenant_id,
            writer=child,
            count_sql=count_sql,
            count_params=count_params,
        )

    await assert_a3_mutation(
        race_admin_path if admin else race_runtime_path,
        parent_of=minted_id,
        constraint=constraint,
    )
