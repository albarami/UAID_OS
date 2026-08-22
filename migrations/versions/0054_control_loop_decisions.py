"""bounded control loop and non-executing go-live decisions

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-14

Slice 55 stops at a hash-chained ``decided_not_executed`` record.  It adds no
production action and does not alter the A5 evaluator or hard-false output.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_HASH = r"^sha256:[0-9a-f]{64}$"
_OLD_RUN_STEP_CHECK = (
    "event_type IN ('run_started', 'step_completed', 'run_resumed', 'run_completed', "
    "'run_failed', 'blocked_on_approval', 'retried', 'cost_paused', 'emergency_paused')"
)
_NEW_RUN_STEP_CHECK = _OLD_RUN_STEP_CHECK[:-1] + ", 'control_loop_waiting')"


def _append_only(table: str) -> None:
    op.execute(
        f"""CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$"""
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON public.{table} "
        f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
    )


def _tenant_table(table: str, *, decision: bool = False) -> None:
    _append_only(table)
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    privileges = "SELECT" if decision else "SELECT, INSERT"
    op.execute(f"GRANT {privileges} ON public.{table} TO uaid_app")


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
    ]


def _common_fks() -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
        ),
    ]


def _create_tables() -> None:
    op.create_table(
        "control_loop_runs",
        *_common_columns(),
        sa.Column("project_run_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_digest", sa.Text(), nullable=False),
        sa.Column("control_loop_contract_version", sa.Text(), nullable=False),
        sa.Column("control_loop_contract_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "control_loop_contract_version='slice55.control_loop.v1'", name="contract"
        ),
        sa.CheckConstraint(
            f"idempotency_digest ~ '{_HASH}' AND control_loop_contract_hash ~ '{_HASH}'",
            name="digests",
        ),
        *_common_fks(),
        sa.ForeignKeyConstraint(
            ["project_run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_clr_id_project_tenant"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_digest", name="uq_clr_idempotency"
        ),
    )
    op.create_index(
        "ix_clr_tenant_project_created",
        "control_loop_runs",
        ["tenant_id", "project_id", "created_at"],
    )

    op.create_table(
        "control_loop_events",
        *_common_columns(),
        sa.Column("control_loop_run_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("previous_event_id", sa.UUID(), nullable=True),
        sa.Column("stage_code", sa.Text(), nullable=False),
        sa.Column("outcome_code", sa.Text(), nullable=False),
        sa.Column("evidence_reference_digest", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 64", name="ordinal"),
        sa.CheckConstraint(
            "char_length(stage_code) BETWEEN 1 AND 128 AND btrim(stage_code)<>'' AND "
            "char_length(outcome_code) BETWEEN 1 AND 128 AND btrim(outcome_code)<>''",
            name="codes",
        ),
        sa.CheckConstraint(
            "("
            "(stage_code='read_project_state' AND outcome_code IN "
            "('capability_unavailable_not_executed','paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='inspect_existing_work_evidence' AND outcome_code IN "
            "('capability_unavailable_not_executed','paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='observe_existing_review_and_verification_evidence' AND outcome_code IN "
            "('capability_unavailable_not_executed','paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='assemble_or_reaudit_evidence_pack' AND outcome_code IN "
            "('evidence_pack_reaudited','evidence_pack_unavailable_not_executed',"
            "'paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='check_cost_and_authority_limits' AND outcome_code IN "
            "('cost_and_authority_limits_checked','paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='observe_staging_evidence' AND outcome_code IN "
            "('staging_evidence_observed_not_deployed','staging_evidence_not_observed',"
            "'paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='evaluate_a5_gate' AND outcome_code IN "
            "('a5_evaluation_completed','paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='finalize_go_live_decision' AND outcome_code IN "
            "('decision_recorded','blocked_evidence_or_authority',"
            "'paused_emergency_stop','paused_cost_stop')) OR "
            "(stage_code='control_loop_runtime' AND outcome_code='failed_infrastructure')"
            ")",
            name="stage_outcome",
        ),
        sa.CheckConstraint(
            f"evidence_reference_digest IS NULL OR evidence_reference_digest ~ '{_HASH}'",
            name="digest",
        ),
        *_common_fks(),
        sa.ForeignKeyConstraint(
            ["control_loop_run_id", "project_id", "tenant_id"],
            ["control_loop_runs.id", "control_loop_runs.project_id", "control_loop_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_event_id", "project_id", "tenant_id"],
            ["control_loop_events.id", "control_loop_events.project_id", "control_loop_events.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_cle_id_project_tenant"),
        sa.UniqueConstraint("control_loop_run_id", "ordinal", name="uq_cle_run_ordinal"),
        sa.UniqueConstraint("previous_event_id", name="uq_cle_previous"),
    )
    op.create_index(
        "ix_cle_tenant_loop_ordinal",
        "control_loop_events",
        ["tenant_id", "control_loop_run_id", "ordinal"],
    )
    op.create_index(
        "uq_cle_loop_root",
        "control_loop_events",
        ["control_loop_run_id"],
        unique=True,
        postgresql_where=sa.text("previous_event_id IS NULL"),
    )

    op.create_table(
        "go_live_evaluations",
        *_common_columns(),
        sa.Column("control_loop_run_id", sa.UUID(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("evaluation_contract_version", sa.Text(), nullable=False),
        sa.Column("evaluation_contract_hash", sa.Text(), nullable=False),
        sa.Column("gate_result_digest", sa.Text(), nullable=False),
        sa.Column("passed_gate_count", sa.SmallInteger(), nullable=False),
        sa.Column("all_gates_passed", sa.Boolean(), nullable=False),
        sa.Column("preapproval_gate_eligible", sa.Boolean(), nullable=False),
        sa.Column("policy_decision", sa.Text(), nullable=False),
        sa.Column("emergency_latch_active", sa.Boolean(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=True),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=True),
        sa.Column("release_verdict_id", sa.UUID(), nullable=True),
        sa.Column("preapproval_request_id", sa.UUID(), nullable=True),
        sa.Column("preapproval_attestation_id", sa.UUID(), nullable=True),
        sa.Column("preapproval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("autonomy_policy_id", sa.UUID(), nullable=True),
        sa.Column("autonomy_policy_digest", sa.Text(), nullable=True),
        sa.Column("autonomy_policy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("emergency_control_binding_id", sa.UUID(), nullable=True),
        sa.Column("emergency_stop_event_id", sa.UUID(), nullable=True),
        sa.Column("decision_binding_digest", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ruleset_version='slice54.v1' AND evaluation_contract_version='slice55.go_live_evaluation.v1'",
            name="contracts",
        ),
        sa.CheckConstraint(
            f"evaluation_contract_hash ~ '{_HASH}' AND gate_result_digest ~ '{_HASH}' "
            f"AND decision_binding_digest ~ '{_HASH}' AND "
            f"(autonomy_policy_digest IS NULL OR autonomy_policy_digest ~ '{_HASH}')",
            name="digests",
        ),
        sa.CheckConstraint("passed_gate_count BETWEEN 0 AND 13", name="passed_count"),
        sa.CheckConstraint("policy_decision IN ('needs_approval','deny','allow')", name="policy"),
        *_common_fks(),
        sa.ForeignKeyConstraint(
            ["control_loop_run_id", "project_id", "tenant_id"],
            ["control_loop_runs.id", "control_loop_runs.project_id", "control_loop_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["preapproval_request_id", "project_id", "tenant_id"],
            ["production_preapproval_requests.id", "production_preapproval_requests.project_id", "production_preapproval_requests.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["preapproval_attestation_id", "project_id", "tenant_id"],
            ["production_preapproval_attestations.id", "production_preapproval_attestations.project_id", "production_preapproval_attestations.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            ["autonomy_policies.id", "autonomy_policies.project_id", "autonomy_policies.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["emergency_control_binding_id", "project_id", "tenant_id"],
            ["emergency_control_bindings.id", "emergency_control_bindings.project_id", "emergency_control_bindings.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["emergency_stop_event_id", "project_id", "tenant_id"],
            ["emergency_stop_events.id", "emergency_stop_events.project_id", "emergency_stop_events.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_gle_id_project_tenant"),
        sa.UniqueConstraint("control_loop_run_id", name="uq_gle_loop"),
    )
    op.create_index(
        "ix_gle_tenant_project_created",
        "go_live_evaluations",
        ["tenant_id", "project_id", "created_at"],
    )

    op.create_table(
        "go_live_evaluation_gate_results",
        *_common_columns(),
        sa.Column("evaluation_id", sa.UUID(), nullable=False),
        sa.Column("gate_number", sa.SmallInteger(), nullable=False),
        sa.Column("gate_name_code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("safe_context_digest", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("gate_number BETWEEN 1 AND 13 AND ordinal BETWEEN 1 AND 13", name="numbers"),
        sa.CheckConstraint(
            "status IN ('passed','insufficient_evidence','no_evidence_source')",
            name="status",
        ),
        sa.CheckConstraint(
            "char_length(gate_name_code) BETWEEN 1 AND 128 AND btrim(gate_name_code)<>'' AND "
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''",
            name="codes",
        ),
        sa.CheckConstraint(f"safe_context_digest ~ '{_HASH}'", name="digest"),
        *_common_fks(),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "project_id", "tenant_id"],
            ["go_live_evaluations.id", "go_live_evaluations.project_id", "go_live_evaluations.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_glegr_id_project_tenant"),
        sa.UniqueConstraint("evaluation_id", "gate_number", name="uq_glegr_gate"),
        sa.UniqueConstraint("evaluation_id", "ordinal", name="uq_glegr_ordinal"),
    )
    op.create_index(
        "ix_glegr_tenant_evaluation_gate",
        "go_live_evaluation_gate_results",
        ["tenant_id", "evaluation_id", "gate_number"],
    )

    op.create_table(
        "go_live_decisions",
        *_common_columns(),
        sa.Column("decision_seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("control_loop_run_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_id", sa.UUID(), nullable=False),
        sa.Column("preapproval_request_id", sa.UUID(), nullable=False),
        sa.Column("preapproval_attestation_id", sa.UUID(), nullable=False),
        sa.Column("autonomy_policy_id", sa.UUID(), nullable=False),
        sa.Column("autonomy_policy_digest", sa.Text(), nullable=False),
        sa.Column("emergency_control_binding_id", sa.UUID(), nullable=False),
        sa.Column("emergency_stop_event_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("release_verdict_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_digest", sa.Text(), nullable=False),
        sa.Column("decision_binding_digest", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("authority_truth_tier", sa.Text(), nullable=False),
        sa.Column("production_action_executed", sa.Boolean(), nullable=False),
        sa.Column("can_go_live_autonomously_snapshot", sa.Boolean(), nullable=False),
        sa.Column("scope_limitation_digest", sa.Text(), nullable=False),
        sa.Column("previous_decision_id", sa.UUID(), nullable=True),
        sa.Column("prev_entry_hash", sa.Text(), nullable=True),
        sa.Column("entry_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("status='decided_not_executed'", name="status"),
        sa.CheckConstraint(
            "authority_truth_tier='request_authenticated_key_custody_under_recorded_policy_not_human_signature'",
            name="authority",
        ),
        sa.CheckConstraint(
            "production_action_executed=false AND can_go_live_autonomously_snapshot=false",
            name="hard_false",
        ),
        sa.CheckConstraint(
            f"evaluation_digest ~ '{_HASH}' AND decision_binding_digest ~ '{_HASH}' AND "
            f"autonomy_policy_digest ~ '{_HASH}' AND scope_limitation_digest ~ '{_HASH}' AND "
            f"(prev_entry_hash IS NULL OR prev_entry_hash ~ '{_HASH}') AND entry_hash ~ '{_HASH}'",
            name="digests",
        ),
        *_common_fks(),
        sa.ForeignKeyConstraint(
            ["control_loop_run_id", "project_id", "tenant_id"],
            ["control_loop_runs.id", "control_loop_runs.project_id", "control_loop_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "project_id", "tenant_id"],
            ["go_live_evaluations.id", "go_live_evaluations.project_id", "go_live_evaluations.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_decision_id", "project_id", "tenant_id"],
            ["go_live_decisions.id", "go_live_decisions.project_id", "go_live_decisions.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["preapproval_request_id", "project_id", "tenant_id"],
            ["production_preapproval_requests.id", "production_preapproval_requests.project_id", "production_preapproval_requests.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["preapproval_attestation_id", "project_id", "tenant_id"],
            ["production_preapproval_attestations.id", "production_preapproval_attestations.project_id", "production_preapproval_attestations.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            ["autonomy_policies.id", "autonomy_policies.project_id", "autonomy_policies.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["emergency_control_binding_id", "project_id", "tenant_id"],
            ["emergency_control_bindings.id", "emergency_control_bindings.project_id", "emergency_control_bindings.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["emergency_stop_event_id", "project_id", "tenant_id"],
            ["emergency_stop_events.id", "emergency_stop_events.project_id", "emergency_stop_events.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_gld_id_project_tenant"),
        sa.UniqueConstraint("evaluation_id", name="uq_gld_evaluation"),
        sa.UniqueConstraint("previous_decision_id", name="uq_gld_previous"),
        sa.UniqueConstraint("entry_hash", name="uq_gld_entry_hash"),
    )
    op.create_index(
        "ix_gld_tenant_project_seq",
        "go_live_decisions",
        ["tenant_id", "project_id", "decision_seq"],
    )
    op.create_index(
        "uq_gld_project_root",
        "go_live_decisions",
        ["tenant_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("previous_decision_id IS NULL"),
    )


def _create_functions() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.slice55_gate_digest(p_evaluation uuid) RETURNS text
        LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $fn$
          SELECT 'sha256:' || encode(sha256(convert_to(COALESCE(string_agg(
            gate_number::text || ':' || octet_length(gate_name_code)::text || ':' || gate_name_code || ':' ||
            octet_length(status)::text || ':' || status || ':' || octet_length(reason_code)::text || ':' || reason_code || ':' || safe_context_digest,
            E'\n' ORDER BY gate_number), ''), 'UTF8')), 'hex')
          FROM public.go_live_evaluation_gate_results WHERE evaluation_id=p_evaluation
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_evaluation_binding_digest(p_evaluation uuid) RETURNS text
        LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $fn$
          SELECT 'sha256:' || encode(sha256(convert_to(concat_ws('|',
            COALESCE(release_candidate_id::text,''), COALESCE(evidence_pack_id::text,''),
            COALESCE(release_verdict_id::text,''), COALESCE(preapproval_request_id::text,''),
            COALESCE(preapproval_attestation_id::text,''), COALESCE(autonomy_policy_id::text,''),
            COALESCE(autonomy_policy_digest,''),
            COALESCE(to_char(autonomy_policy_updated_at AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),''),
            COALESCE(emergency_control_binding_id::text,''), COALESCE(emergency_stop_event_id::text,''),
            preapproval_gate_eligible::text, policy_decision, emergency_latch_active::text,
            ruleset_version, evaluation_contract_version), 'UTF8')), 'hex')
          FROM public.go_live_evaluations WHERE id=p_evaluation
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_policy_permits(p_policy uuid) RETURNS boolean
        LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $fn$
          SELECT COALESCE((
            SELECT a.autonomy_level>=4
              AND jsonb_typeof(a.overrides)='object'
              AND NOT EXISTS (
                SELECT 1 FROM jsonb_each(a.overrides) item
                WHERE item.key NOT IN (
                  'read_docs','read_source_control_config','read_pull_requests',
                  'read_deployment_target','read_monitoring_status','verify_secret_reference',
                  'read_project_management_issues','create_draft_prd','create_project_tasks',
                  'create_repository','create_branches','commit_code','open_pull_requests',
                  'run_tests','deploy_staging','merge_to_protected','deploy_production',
                  'delete_resources','change_secrets','modify_billing_or_paid_resources',
                  'send_external_communications','access_sensitive_data','accept_risk',
                  'override_failed_gate','weaken_test_or_review_standards'
                )
                OR jsonb_typeof(item.value)<>'object'
                OR EXISTS (
                  SELECT 1 FROM jsonb_object_keys(item.value) k
                  WHERE k NOT IN ('min_level','requires_approval','allow')
                )
                OR (
                  item.value ? 'min_level' AND (
                    jsonb_typeof(item.value->'min_level')<>'number'
                    OR item.value->>'min_level' !~ '^[0-5]$'
                    OR (item.value->>'min_level')::integer < CASE item.key
                      WHEN 'read_docs' THEN 0
                      WHEN 'create_repository' THEN 2 WHEN 'create_branches' THEN 2
                      WHEN 'commit_code' THEN 2 WHEN 'open_pull_requests' THEN 2
                      WHEN 'run_tests' THEN 2 WHEN 'deploy_staging' THEN 3
                      WHEN 'merge_to_protected' THEN 4 WHEN 'deploy_production' THEN 4
                      ELSE 1 END
                  )
                )
                OR (item.value ? 'requires_approval'
                    AND item.value->'requires_approval'<>'true'::jsonb)
                OR (item.value ? 'allow' AND item.value->'allow'<>'false'::jsonb)
              )
              AND COALESCE(a.overrides#>>'{deploy_production,allow}','true')<>'false'
              AND a.autonomy_level>=COALESCE(
                    (a.overrides#>>'{deploy_production,min_level}')::integer,4)
            FROM public.autonomy_policies a WHERE a.id=p_policy
          ),false)
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_validate_evaluation(p_id uuid) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE e public.go_live_evaluations%ROWTYPE; n integer; p integer;
        BEGIN
          SELECT * INTO e FROM public.go_live_evaluations WHERE id=p_id;
          IF NOT FOUND THEN RETURN; END IF;
          SELECT count(*),count(*) FILTER (WHERE status='passed') INTO n,p
          FROM public.go_live_evaluation_gate_results WHERE evaluation_id=e.id;
          IF n<>13 OR EXISTS (
            SELECT 1 FROM generate_series(1,13) g
            LEFT JOIN public.go_live_evaluation_gate_results r
              ON r.evaluation_id=e.id AND r.gate_number=g AND r.ordinal=g
            WHERE r.id IS NULL
          ) THEN RAISE EXCEPTION 'go-live evaluation exact gate set incomplete'; END IF;
          IF e.passed_gate_count<>p OR e.all_gates_passed<>(p=13) THEN
            RAISE EXCEPTION 'go-live evaluation aggregate mismatch'; END IF;
          IF e.gate_result_digest<>public.slice55_gate_digest(e.id) THEN
            RAISE EXCEPTION 'go-live evaluation gate digest mismatch'; END IF;
          IF e.decision_binding_digest<>public.slice55_evaluation_binding_digest(e.id) THEN
            RAISE EXCEPTION 'go-live evaluation binding digest mismatch'; END IF;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_validate_event(p_id uuid) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE e public.control_loop_events%ROWTYPE; p public.control_loop_events%ROWTYPE;
        BEGIN
          SELECT * INTO e FROM public.control_loop_events WHERE id=p_id;
          IF NOT FOUND THEN RETURN; END IF;
          IF e.previous_event_id IS NULL THEN
            IF e.ordinal<>1 THEN RAISE EXCEPTION 'control-loop event chain is not linear'; END IF;
            IF e.stage_code NOT IN ('read_project_state','control_loop_runtime') THEN
              RAISE EXCEPTION 'control-loop event transition is not allowed'; END IF;
          ELSE
            SELECT * INTO p FROM public.control_loop_events WHERE id=e.previous_event_id;
            IF NOT FOUND OR p.control_loop_run_id<>e.control_loop_run_id OR p.ordinal+1<>e.ordinal THEN
              RAISE EXCEPTION 'control-loop event chain is not linear'; END IF;
            IF p.outcome_code IN (
                 'failed_infrastructure','decision_recorded','blocked_evidence_or_authority'
               ) THEN
              RAISE EXCEPTION 'control-loop event transition is not allowed'; END IF;
            IF p.outcome_code IN ('paused_emergency_stop','paused_cost_stop') THEN
              IF e.stage_code<>p.stage_code THEN
                RAISE EXCEPTION 'control-loop event transition is not allowed'; END IF;
              RETURN;
            END IF;
            IF NOT (
              (p.stage_code='read_project_state' AND e.stage_code='inspect_existing_work_evidence') OR
              (p.stage_code='inspect_existing_work_evidence'
                 AND e.stage_code='observe_existing_review_and_verification_evidence') OR
              (p.stage_code='observe_existing_review_and_verification_evidence'
                 AND e.stage_code='assemble_or_reaudit_evidence_pack') OR
              (p.stage_code='assemble_or_reaudit_evidence_pack'
                 AND e.stage_code='check_cost_and_authority_limits') OR
              (p.stage_code='check_cost_and_authority_limits'
                 AND e.stage_code='observe_staging_evidence') OR
              (p.stage_code='observe_staging_evidence' AND e.stage_code='evaluate_a5_gate') OR
              (p.stage_code='evaluate_a5_gate' AND e.stage_code='finalize_go_live_decision') OR
              e.stage_code='control_loop_runtime'
            ) THEN
              RAISE EXCEPTION 'control-loop event transition is not allowed'; END IF;
          END IF;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_scope_digest() RETURNS text
        LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $fn$
          SELECT 'sha256:' || encode(sha256(convert_to(
            'production_not_executed|key_custody_not_human_signature|bounded_current_evidence_only|staging_evidence_observed_not_deployed|future_execution_requires_new_plan',
            'UTF8')), 'hex')
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_entry_hash(
          p_seq bigint,p_tenant uuid,p_project uuid,p_evaluation uuid,p_evaluation_digest text,
          p_binding_digest text,p_status text,p_truth text,p_scope text,p_created timestamptz,
          p_prev text
        ) RETURNS text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $fn$
          SELECT 'sha256:' || encode(sha256(convert_to(concat_ws('|',p_seq::text,p_tenant::text,
            p_project::text,p_evaluation::text,p_evaluation_digest,p_binding_digest,p_status,
            p_truth,p_scope,to_char(p_created AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
            COALESCE(p_prev,'')), 'UTF8')), 'hex')
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_finalize_decision(p_evaluation uuid) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE
          e public.go_live_evaluations%ROWTYPE; prior public.go_live_decisions%ROWTYPE;
          new_id uuid:=gen_random_uuid(); new_seq bigint; now_at timestamptz:=clock_timestamp();
          scope_hash text:=public.slice55_scope_digest(); new_hash text; tenant uuid;
        BEGIN
          tenant:=NULLIF(current_setting('app.current_tenant',true),'')::uuid;
          IF tenant IS NULL THEN RAISE EXCEPTION 'tenant context required'; END IF;
          SELECT * INTO e FROM public.go_live_evaluations WHERE id=p_evaluation AND tenant_id=tenant;
          IF NOT FOUND THEN RAISE EXCEPTION 'go-live evaluation unavailable'; END IF;
          PERFORM 1 FROM public.projects WHERE id=e.project_id AND tenant_id=e.tenant_id FOR UPDATE;
          PERFORM 1 FROM public.autonomy_policies
            WHERE id=e.autonomy_policy_id AND project_id=e.project_id AND tenant_id=e.tenant_id
            FOR UPDATE;
          PERFORM 1 FROM public.production_preapproval_requests
            WHERE id=e.preapproval_request_id AND project_id=e.project_id AND tenant_id=e.tenant_id
            FOR UPDATE;
          PERFORM 1 FROM public.emergency_control_bindings
            WHERE id=e.emergency_control_binding_id AND project_id=e.project_id
              AND tenant_id=e.tenant_id
            FOR UPDATE;
          PERFORM public.slice55_validate_evaluation(e.id);
          IF NOT e.all_gates_passed OR NOT e.preapproval_gate_eligible
             OR e.policy_decision<>'needs_approval' OR e.emergency_latch_active THEN
            RAISE EXCEPTION 'go-live decision predicate not satisfied'; END IF;
          IF e.release_candidate_id IS NULL OR e.evidence_pack_id IS NULL OR e.release_verdict_id IS NULL
             OR e.preapproval_request_id IS NULL OR e.preapproval_attestation_id IS NULL
             OR e.autonomy_policy_id IS NULL OR e.autonomy_policy_digest IS NULL
             OR e.autonomy_policy_updated_at IS NULL OR e.emergency_control_binding_id IS NULL
             OR e.emergency_stop_event_id IS NULL OR e.preapproval_expires_at IS NULL THEN
            RAISE EXCEPTION 'go-live decision binding incomplete'; END IF;
          IF e.preapproval_expires_at<=now_at OR NOT EXISTS (
            SELECT 1 FROM public.production_preapproval_requests r
            JOIN public.production_preapproval_attestations a ON a.id=e.preapproval_attestation_id
              AND a.request_id=r.id AND a.project_id=r.project_id AND a.tenant_id=r.tenant_id
            WHERE r.id=e.preapproval_request_id AND r.project_id=e.project_id AND r.tenant_id=e.tenant_id
              AND r.release_candidate_id=e.release_candidate_id AND r.evidence_pack_id=e.evidence_pack_id
              AND r.release_verdict_id=e.release_verdict_id AND r.autonomy_policy_id=e.autonomy_policy_id
              AND r.autonomy_policy_digest=e.autonomy_policy_digest
              AND r.id=(SELECT lr.id FROM public.production_preapproval_requests lr
                WHERE lr.project_id=e.project_id AND lr.tenant_id=e.tenant_id
                ORDER BY lr.created_at DESC,lr.id DESC LIMIT 1)
              AND a.gate_eligible_at_creation AND a.expires_at=e.preapproval_expires_at
              AND a.expires_at>now_at
              AND NOT EXISTS (
                SELECT 1 FROM public.production_preapproval_lifecycle_events l
                WHERE l.attestation_id=a.id AND l.event_type IN ('revoked','superseded')
              )
          ) THEN RAISE EXCEPTION 'go-live preapproval is not current'; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.autonomy_policies a
            WHERE a.id=e.autonomy_policy_id AND a.project_id=e.project_id AND a.tenant_id=e.tenant_id
              AND a.updated_at=e.autonomy_policy_updated_at
              AND public.slice55_policy_permits(a.id)
          ) THEN RAISE EXCEPTION 'go-live autonomy policy binding invalid'; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.emergency_control_bindings b
            JOIN public.emergency_stop_events s ON s.id=e.emergency_stop_event_id
              AND s.binding_id=b.id AND s.project_id=b.project_id AND s.tenant_id=b.tenant_id
            WHERE b.id=e.emergency_control_binding_id AND b.project_id=e.project_id
              AND b.tenant_id=e.tenant_id
              AND s.state_after='armed' AND s.id=(
                SELECT x.id FROM public.emergency_stop_events x
                WHERE x.project_id=e.project_id AND x.tenant_id=e.tenant_id
                ORDER BY x.created_at DESC,x.id DESC LIMIT 1)
          ) THEN RAISE EXCEPTION 'go-live emergency binding is not current'; END IF;
          SELECT * INTO prior FROM public.go_live_decisions
          WHERE tenant_id=e.tenant_id AND project_id=e.project_id
          ORDER BY decision_seq DESC LIMIT 1;
          new_seq:=nextval(pg_get_serial_sequence('public.go_live_decisions','decision_seq'));
          new_hash:=public.slice55_entry_hash(new_seq,e.tenant_id,e.project_id,e.id,
            e.gate_result_digest,e.decision_binding_digest,'decided_not_executed',
            'request_authenticated_key_custody_under_recorded_policy_not_human_signature',
            scope_hash,now_at,prior.entry_hash);
          INSERT INTO public.go_live_decisions (
            id,decision_seq,tenant_id,project_id,control_loop_run_id,evaluation_id,
            preapproval_request_id,preapproval_attestation_id,autonomy_policy_id,
            autonomy_policy_digest,
            emergency_control_binding_id,emergency_stop_event_id,release_candidate_id,
            evidence_pack_id,release_verdict_id,evaluation_digest,decision_binding_digest,
            status,authority_truth_tier,production_action_executed,
            can_go_live_autonomously_snapshot,scope_limitation_digest,previous_decision_id,
            prev_entry_hash,entry_hash,created_at
          ) OVERRIDING SYSTEM VALUE VALUES (
            new_id,new_seq,e.tenant_id,e.project_id,e.control_loop_run_id,e.id,
            e.preapproval_request_id,e.preapproval_attestation_id,e.autonomy_policy_id,
            e.autonomy_policy_digest,
            e.emergency_control_binding_id,e.emergency_stop_event_id,e.release_candidate_id,
            e.evidence_pack_id,e.release_verdict_id,e.gate_result_digest,e.decision_binding_digest,
            'decided_not_executed',
            'request_authenticated_key_custody_under_recorded_policy_not_human_signature',
            false,false,scope_hash,prior.id,prior.entry_hash,new_hash,now_at);
          PERFORM public.audit_append(
            'control_loop_runtime',
            'control_loop.decision_recorded',
            'go_live_decision',
            jsonb_build_object(
              'project_id', e.project_id,
              'control_loop_run_id', e.control_loop_run_id,
              'evaluation_id', e.id,
              'decision_id', new_id,
              'status', 'decided_not_executed',
              'production_action_executed', false
            )
          );
          RETURN new_id;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_verify_decision_chain(p_project uuid) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE d public.go_live_decisions%ROWTYPE; prior_id uuid:=NULL; prior_hash text:=NULL;
        BEGIN
          FOR d IN SELECT * FROM public.go_live_decisions WHERE project_id=p_project
                   ORDER BY decision_seq LOOP
            IF d.previous_decision_id IS DISTINCT FROM prior_id OR d.prev_entry_hash IS DISTINCT FROM prior_hash
               OR d.entry_hash<>public.slice55_entry_hash(d.decision_seq,d.tenant_id,d.project_id,
                 d.evaluation_id,d.evaluation_digest,d.decision_binding_digest,d.status,
                 d.authority_truth_tier,d.scope_limitation_digest,d.created_at,d.prev_entry_hash) THEN
              RETURN false; END IF;
            prior_id:=d.id; prior_hash:=d.entry_hash;
          END LOOP;
          RETURN true;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice55_graph_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        BEGIN
          IF TG_TABLE_NAME='control_loop_events' THEN
            PERFORM public.slice55_validate_event(NEW.id);
          ELSIF TG_TABLE_NAME='go_live_evaluations' THEN
            PERFORM public.slice55_validate_evaluation(NEW.id);
          ELSIF TG_TABLE_NAME='go_live_evaluation_gate_results' THEN
            PERFORM public.slice55_validate_evaluation(NEW.evaluation_id);
          ELSIF TG_TABLE_NAME='go_live_decisions' THEN
            PERFORM public.slice55_validate_evaluation(NEW.evaluation_id);
            IF NOT NEW.status='decided_not_executed' OR NEW.production_action_executed
               OR NEW.can_go_live_autonomously_snapshot THEN
              RAISE EXCEPTION 'go-live decision truth fields invalid'; END IF;
          END IF;
          RETURN NULL;
        END $fn$
        """
    )
    for table in (
        "control_loop_events",
        "go_live_evaluations",
        "go_live_evaluation_gate_results",
        "go_live_decisions",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_graph_guard AFTER INSERT ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.slice55_graph_guard()"
        )
    for signature in (
        "slice55_gate_digest(uuid)",
        "slice55_evaluation_binding_digest(uuid)",
        "slice55_policy_permits(uuid)",
        "slice55_validate_evaluation(uuid)",
        "slice55_validate_event(uuid)",
        "slice55_scope_digest()",
        "slice55_entry_hash(bigint,uuid,uuid,uuid,text,text,text,text,text,timestamptz,text)",
        "slice55_finalize_decision(uuid)",
        "slice55_verify_decision_chain(uuid)",
        "slice55_graph_guard()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.slice55_finalize_decision(uuid) TO uaid_app")
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.audit_append(text,text,text,jsonb) TO CURRENT_USER"
    )


def upgrade() -> None:
    op.drop_constraint("event_type_valid", "run_steps", type_="check")
    op.create_check_constraint("event_type_valid", "run_steps", _NEW_RUN_STEP_CHECK)
    _create_tables()
    for table in (
        "control_loop_runs",
        "control_loop_events",
        "go_live_evaluations",
        "go_live_evaluation_gate_results",
    ):
        _tenant_table(table)
    _tenant_table("go_live_decisions", decision=True)
    _create_functions()


def downgrade() -> None:
    op.execute(
        """DO $fn$ BEGIN
        IF EXISTS (SELECT 1 FROM public.control_loop_runs)
           OR EXISTS (SELECT 1 FROM public.control_loop_events)
           OR EXISTS (SELECT 1 FROM public.go_live_evaluations)
           OR EXISTS (SELECT 1 FROM public.go_live_evaluation_gate_results)
           OR EXISTS (SELECT 1 FROM public.go_live_decisions) THEN
          RAISE EXCEPTION 'cannot downgrade Slice 55 while control-loop rows exist';
        END IF; END $fn$"""
    )
    for table in (
        "control_loop_events",
        "go_live_evaluations",
        "go_live_evaluation_gate_results",
        "go_live_decisions",
    ):
        op.execute(f"DROP TRIGGER {table}_graph_guard ON public.{table}")
    op.execute("DROP FUNCTION public.slice55_graph_guard()")
    op.execute("DROP FUNCTION public.slice55_verify_decision_chain(uuid)")
    op.execute("DROP FUNCTION public.slice55_finalize_decision(uuid)")
    op.execute("DROP FUNCTION public.slice55_entry_hash(bigint,uuid,uuid,uuid,text,text,text,text,text,timestamptz,text)")
    op.execute("DROP FUNCTION public.slice55_scope_digest()")
    op.execute("DROP FUNCTION public.slice55_validate_event(uuid)")
    op.execute("DROP FUNCTION public.slice55_validate_evaluation(uuid)")
    op.execute("DROP FUNCTION public.slice55_policy_permits(uuid)")
    op.execute("DROP FUNCTION public.slice55_evaluation_binding_digest(uuid)")
    op.execute("DROP FUNCTION public.slice55_gate_digest(uuid)")
    op.execute("DROP INDEX public.uq_gld_project_root")
    op.execute("DROP INDEX public.uq_cle_loop_root")
    for table in (
        "go_live_decisions",
        "go_live_evaluation_gate_results",
        "go_live_evaluations",
        "control_loop_events",
        "control_loop_runs",
    ):
        op.drop_table(table)
        op.execute(f"DROP FUNCTION public.{table}_block_dml()")
    op.drop_constraint("event_type_valid", "run_steps", type_="check")
    op.create_check_constraint("event_type_valid", "run_steps", _OLD_RUN_STEP_CHECK)
