"""local-runtime emergency stop and release-bound rollback authority

Revision ID: 0053
Revises: 0052
Create Date: 2026-07-14

Slice 54. Additive tenant-owned evidence plus the two ruled runtime extensions.
No production deployment or rollback action is introduced.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_HASH = r"^sha256:[0-9a-f]{64}$"
_OLD_RUN_STEP_CHECK = (
    "event_type IN ('run_started', 'step_completed', 'run_resumed', 'run_completed', "
    "'run_failed', 'blocked_on_approval', 'retried', 'cost_paused')"
)
_NEW_RUN_STEP_CHECK = _OLD_RUN_STEP_CHECK[:-1] + ", 'emergency_paused')"


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


def _tenant_table(table: str) -> None:
    _append_only(table)
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON public.{table} TO uaid_app")


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
    ]


def _create_tables() -> None:
    op.create_table(
        "emergency_control_bindings",
        *_common_columns(),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column("autonomy_policy_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=True),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=True),
        sa.Column("rollback_verification_run_id", sa.UUID(), nullable=True),
        sa.Column("emergency_control_contract_version", sa.Text(), nullable=False),
        sa.Column("emergency_stop_contract_version", sa.Text(), nullable=False),
        sa.Column("rollback_authority_contract_version", sa.Text(), nullable=False),
        sa.Column("source_provenance", sa.Text(), nullable=False),
        sa.Column("binding_attempt_status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("policy_digest", sa.Text(), nullable=False),
        sa.Column("checklist_digest", sa.Text(), nullable=False),
        sa.Column("approver_set_digest", sa.Text(), nullable=False),
        sa.Column("autonomy_policy_digest", sa.Text(), nullable=False),
        sa.Column("release_rollback_binding_digest", sa.Text(), nullable=True),
        sa.Column("authority_member_count", sa.SmallInteger(), nullable=False),
        sa.Column(
            "stop_authority_bound",
            sa.Boolean(),
            sa.Computed(
                "binding_attempt_status='succeeded' AND authority_member_count>=2", persisted=True
            ),
            nullable=False,
        ),
        sa.Column(
            "rollback_authority_bound",
            sa.Boolean(),
            sa.Computed(
                "binding_attempt_status='succeeded' AND authority_member_count>=2 AND release_candidate_id IS NOT NULL AND evidence_pack_id IS NOT NULL AND rollback_verification_run_id IS NOT NULL",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_consistent",
            sa.Boolean(),
            sa.Computed("binding_attempt_status='succeeded'", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "gate_eligible_at_creation",
            sa.Boolean(),
            sa.Computed(
                "binding_attempt_status='succeeded' AND authority_member_count>=2 AND release_candidate_id IS NOT NULL AND evidence_pack_id IS NOT NULL AND rollback_verification_run_id IS NOT NULL",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("configured_by_subject_hash", sa.Text(), nullable=False),
        sa.Column("configured_by_actor_type", sa.Text(), nullable=False),
        sa.Column("configured_by_provenance", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "emergency_control_contract_version='slice54.emergency_control.v1' AND emergency_stop_contract_version='slice54.emergency_stop.v1' AND rollback_authority_contract_version='slice54.rollback_authority.v1'",
            name="contracts",
        ),
        sa.CheckConstraint(
            "source_provenance='caller_supplied_unverified_structured_approval_policy' AND configured_by_provenance='request_authenticated' AND configured_by_actor_type='human'",
            name="provenance",
        ),
        sa.CheckConstraint(
            "binding_attempt_status IN ('succeeded','failed','refused')", name="attempt"
        ),
        sa.CheckConstraint(
            f"policy_digest ~ '{_HASH}' AND checklist_digest ~ '{_HASH}' AND approver_set_digest ~ '{_HASH}' AND autonomy_policy_digest ~ '{_HASH}' AND configured_by_subject_hash ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}' AND (release_rollback_binding_digest IS NULL OR release_rollback_binding_digest ~ '{_HASH}')",
            name="digests",
        ),
        sa.CheckConstraint("authority_member_count BETWEEN 1 AND 100", name="member_count"),
        sa.CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''", name="reason"
        ),
        sa.CheckConstraint(
            "(release_candidate_id IS NULL AND evidence_pack_id IS NULL AND rollback_verification_run_id IS NULL AND release_rollback_binding_digest IS NULL) OR (release_candidate_id IS NOT NULL AND evidence_pack_id IS NOT NULL AND rollback_verification_run_id IS NOT NULL AND release_rollback_binding_digest IS NOT NULL)",
            name="release_binding_shape",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "production_approval_policy_versions.id",
                "production_approval_policy_versions.project_id",
                "production_approval_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["autonomy_policy_id", "project_id", "tenant_id"],
            ["autonomy_policies.id", "autonomy_policies.project_id", "autonomy_policies.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_verification_run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_ecb_id_project_tenant"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_ecb_idempotency"
        ),
    )
    op.create_index(
        "ix_ecb_tenant_project_created",
        "emergency_control_bindings",
        ["tenant_id", "project_id", "created_at"],
    )

    op.create_table(
        "emergency_control_authority_members",
        *_common_columns(),
        sa.Column("binding_id", sa.UUID(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column("policy_approver_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("principal_subject_hash", sa.Text(), nullable=False),
        sa.Column(
            "may_activate_stop", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("may_clear_stop", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "may_authorize_rollback", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 100", name="ordinal"),
        sa.CheckConstraint(f"principal_subject_hash ~ '{_HASH}'", name="subject_hash"),
        sa.CheckConstraint(
            "may_activate_stop AND may_clear_stop AND may_authorize_rollback", name="capabilities"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "production_approval_policy_versions.id",
                "production_approval_policy_versions.project_id",
                "production_approval_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_approver_id"], ["production_approval_policy_approvers.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_ecam_id_project_tenant"),
        sa.UniqueConstraint("binding_id", "ordinal", name="uq_ecam_binding_ordinal"),
        sa.UniqueConstraint("binding_id", "principal_subject_hash", name="uq_ecam_binding_subject"),
    )

    op.create_table(
        "emergency_stop_events",
        *_common_columns(),
        sa.Column("binding_id", sa.UUID(), nullable=False),
        sa.Column("previous_event_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "state_after",
            sa.Text(),
            sa.Computed(
                "CASE WHEN event_type='activated' THEN 'active' ELSE 'armed' END", persisted=True
            ),
            nullable=False,
        ),
        sa.Column("actor_member_id", sa.UUID(), nullable=False),
        sa.Column("actor_subject_hash", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_provenance", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('armed_anchor','activated','cleared')", name="event_type"
        ),
        sa.CheckConstraint(
            "actor_type='human' AND actor_provenance='request_authenticated'", name="actor"
        ),
        sa.CheckConstraint(
            f"actor_subject_hash ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}'", name="digests"
        ),
        sa.CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''", name="reason"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_member_id", "project_id", "tenant_id"],
            [
                "emergency_control_authority_members.id",
                "emergency_control_authority_members.project_id",
                "emergency_control_authority_members.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_event_id", "project_id", "tenant_id"],
            [
                "emergency_stop_events.id",
                "emergency_stop_events.project_id",
                "emergency_stop_events.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_ese_id_project_tenant"),
        sa.UniqueConstraint("previous_event_id", name="uq_ese_previous"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_ese_idempotency"
        ),
    )
    op.create_index(
        "ix_ese_tenant_project_created",
        "emergency_stop_events",
        ["tenant_id", "project_id", "created_at"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_ese_project_root ON public.emergency_stop_events(tenant_id,project_id) WHERE previous_event_id IS NULL"
    )

    op.create_table(
        "emergency_stop_run_effects",
        *_common_columns(),
        sa.Column("activation_event_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("emergency_run_step_id", sa.UUID(), nullable=True),
        sa.Column("status_before", sa.Text(), nullable=False),
        sa.Column("status_after", sa.Text(), nullable=False),
        sa.Column("effect_code", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status_before IN ('created','running','paused','blocked') AND status_after IN ('created','paused','blocked')",
            name="statuses",
        ),
        sa.CheckConstraint(
            "effect_code IN ('paused','already_paused','already_blocked','not_started')",
            name="effect",
        ),
        sa.CheckConstraint(
            "(effect_code='paused' AND status_before='running' AND status_after='paused' AND emergency_run_step_id IS NOT NULL) OR (effect_code<>'paused' AND status_before=status_after AND emergency_run_step_id IS NULL)",
            name="shape",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["activation_event_id", "project_id", "tenant_id"],
            [
                "emergency_stop_events.id",
                "emergency_stop_events.project_id",
                "emergency_stop_events.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            ["project_runs.id", "project_runs.project_id", "project_runs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activation_event_id", "run_id", name="uq_esre_event_run"),
    )

    op.create_table(
        "emergency_rollback_authorizations",
        *_common_columns(),
        sa.Column("binding_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("rollback_verification_run_id", sa.UUID(), nullable=False),
        sa.Column("actor_member_id", sa.UUID(), nullable=False),
        sa.Column("actor_subject_hash", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_provenance", sa.Text(), nullable=False),
        sa.Column("release_rollback_binding_digest", sa.Text(), nullable=False),
        sa.Column("authorization_contract_version", sa.Text(), nullable=False),
        sa.Column("result_code", sa.Text(), nullable=False),
        sa.Column("scope_limitation_code", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_type='human' AND actor_provenance='request_authenticated'", name="actor"
        ),
        sa.CheckConstraint(
            "authorization_contract_version='slice54.rollback_authority.v1' AND result_code='authorized_not_executed' AND scope_limitation_code='production_rollback_not_executed'",
            name="result",
        ),
        sa.CheckConstraint(
            f"actor_subject_hash ~ '{_HASH}' AND release_rollback_binding_digest ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}'",
            name="digests",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_verification_run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_member_id", "project_id", "tenant_id"],
            [
                "emergency_control_authority_members.id",
                "emergency_control_authority_members.project_id",
                "emergency_control_authority_members.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_era_idempotency"
        ),
    )


def _create_graph_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.slice54_validate_binding(p_id uuid) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE b public.emergency_control_bindings%ROWTYPE; n integer;
        BEGIN
          SELECT * INTO b FROM public.emergency_control_bindings WHERE id=p_id;
          IF NOT FOUND THEN RETURN; END IF;
          SELECT count(*) INTO n FROM public.emergency_control_authority_members WHERE binding_id=b.id;
          IF n<>b.authority_member_count THEN RAISE EXCEPTION 'emergency authority member set incomplete'; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.production_approval_policy_versions p
            WHERE p.id=b.policy_version_id AND p.project_id=b.project_id AND p.tenant_id=b.tenant_id
              AND p.policy_digest=b.policy_digest AND p.checklist_digest=b.checklist_digest
              AND p.approver_set_digest=b.approver_set_digest AND p.approver_count=b.authority_member_count
          ) THEN RAISE EXCEPTION 'emergency binding does not match policy snapshot'; END IF;
          IF EXISTS (
            SELECT 1 FROM public.emergency_control_authority_members m
            LEFT JOIN public.production_approval_policy_approvers p
              ON p.id=m.policy_approver_id AND p.policy_version_id=m.policy_version_id
             AND p.project_id=m.project_id AND p.tenant_id=m.tenant_id
             AND p.ordinal=m.ordinal AND p.principal_subject_hash=m.principal_subject_hash
            WHERE m.binding_id=b.id AND (p.id IS NULL OR m.policy_version_id<>b.policy_version_id)
          ) THEN RAISE EXCEPTION 'emergency authority membership does not match policy'; END IF;
          IF b.binding_attempt_status='succeeded' AND n<2 THEN
            RAISE EXCEPTION 'gate-bearing emergency authority requires two members';
          END IF;
          IF b.rollback_verification_run_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.rollback_verification_runs r
            WHERE r.id=b.rollback_verification_run_id AND r.project_id=b.project_id AND r.tenant_id=b.tenant_id
              AND r.release_candidate_id=b.release_candidate_id AND r.evidence_pack_id=b.evidence_pack_id
              AND r.gate_eligible AND r.attempt_status='succeeded'
          ) THEN RAISE EXCEPTION 'rollback authority is not bound to gate-eligible evidence'; END IF;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice54_validate_event(p_id uuid) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE e public.emergency_stop_events%ROWTYPE; p public.emergency_stop_events%ROWTYPE;
        BEGIN
          SELECT * INTO e FROM public.emergency_stop_events WHERE id=p_id;
          IF NOT FOUND THEN RETURN; END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.emergency_control_authority_members m
            WHERE m.id=e.actor_member_id AND m.binding_id=e.binding_id
              AND m.project_id=e.project_id AND m.tenant_id=e.tenant_id
              AND m.principal_subject_hash=e.actor_subject_hash
          ) THEN RAISE EXCEPTION 'emergency event actor is not an exact binding member'; END IF;
          IF e.previous_event_id IS NULL THEN
            IF e.event_type<>'armed_anchor' THEN RAISE EXCEPTION 'emergency latch root must be armed anchor'; END IF;
          ELSE
            SELECT * INTO p FROM public.emergency_stop_events WHERE id=e.previous_event_id;
            IF NOT FOUND OR (p.state_after='armed' AND e.event_type<>'activated')
               OR (p.state_after='active' AND e.event_type<>'cleared') THEN
              RAISE EXCEPTION 'emergency latch chain transition invalid';
            END IF;
            IF e.event_type='cleared' AND e.actor_subject_hash=p.actor_subject_hash THEN
              RAISE EXCEPTION 'emergency latch clear requires distinct authority member';
            END IF;
          END IF;
          IF e.event_type='activated' THEN
            IF EXISTS (SELECT 1 FROM public.project_runs r WHERE r.tenant_id=e.tenant_id AND r.project_id=e.project_id AND r.status='running') THEN
              RAISE EXCEPTION 'emergency activation left a running project run';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.project_runs r
              WHERE r.tenant_id=e.tenant_id AND r.project_id=e.project_id
                AND r.status IN ('created','paused','blocked')
                AND NOT EXISTS (SELECT 1 FROM public.emergency_stop_run_effects x WHERE x.activation_event_id=e.id AND x.run_id=r.id)
            ) THEN RAISE EXCEPTION 'emergency activation effect inventory incomplete'; END IF;
            IF EXISTS (
              SELECT 1 FROM public.emergency_stop_run_effects x
              LEFT JOIN public.run_steps s ON s.id=x.emergency_run_step_id
              LEFT JOIN public.project_runs r ON r.id=x.run_id AND r.project_id=x.project_id AND r.tenant_id=x.tenant_id
              WHERE x.activation_event_id=e.id AND (
                r.id IS NULL OR r.status<>x.status_after
                OR
                (x.effect_code='paused' AND (s.id IS NULL OR s.run_id<>x.run_id OR s.project_id<>x.project_id OR s.tenant_id<>x.tenant_id OR s.event_type<>'emergency_paused' OR s.status_from<>'running' OR s.status_to<>'paused'))
                OR (x.effect_code='not_started' AND x.status_after<>'created')
                OR (x.effect_code='already_paused' AND x.status_after<>'paused')
                OR (x.effect_code='already_blocked' AND x.status_after<>'blocked')
              )
            ) THEN RAISE EXCEPTION 'emergency activation effect graph invalid'; END IF;
          END IF;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice54_graph_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE target uuid;
        BEGIN
          IF TG_TABLE_NAME='emergency_control_bindings' THEN target=NEW.id;
          ELSIF TG_TABLE_NAME='emergency_control_authority_members' THEN target=NEW.binding_id;
          ELSIF TG_TABLE_NAME='emergency_stop_events' THEN PERFORM public.slice54_validate_binding(NEW.binding_id); PERFORM public.slice54_validate_event(NEW.id); RETURN NULL;
          ELSIF TG_TABLE_NAME='emergency_stop_run_effects' THEN PERFORM public.slice54_validate_event(NEW.activation_event_id); RETURN NULL;
          ELSIF TG_TABLE_NAME='emergency_rollback_authorizations' THEN
            PERFORM public.slice54_validate_binding(NEW.binding_id);
            IF NOT EXISTS (
              SELECT 1 FROM public.emergency_control_bindings b
              JOIN public.emergency_control_authority_members m ON m.id=NEW.actor_member_id AND m.binding_id=b.id
              WHERE b.id=NEW.binding_id AND b.rollback_authority_bound
                AND b.release_candidate_id=NEW.release_candidate_id AND b.evidence_pack_id=NEW.evidence_pack_id
                AND b.rollback_verification_run_id=NEW.rollback_verification_run_id
                AND b.release_rollback_binding_digest=NEW.release_rollback_binding_digest
                AND m.principal_subject_hash=NEW.actor_subject_hash
            ) THEN RAISE EXCEPTION 'emergency rollback authorization graph invalid'; END IF;
            RETURN NULL;
          END IF;
          PERFORM public.slice54_validate_binding(target); RETURN NULL;
        END $fn$
        """
    )
    for table in (
        "emergency_control_bindings",
        "emergency_control_authority_members",
        "emergency_stop_events",
        "emergency_stop_run_effects",
        "emergency_rollback_authorizations",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_graph_guard AFTER INSERT ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.slice54_graph_guard()"
        )
    op.execute(
        """
        CREATE FUNCTION public.project_runs_emergency_latch_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $fn$
        DECLARE active boolean;
        BEGIN
          IF NEW.status<>'running' THEN RETURN NEW; END IF;
          SELECT e.state_after='active' INTO active FROM public.emergency_stop_events e
          WHERE e.tenant_id=NEW.tenant_id AND e.project_id=NEW.project_id
          ORDER BY e.created_at DESC,e.id DESC LIMIT 1;
          IF COALESCE(active,false) THEN RAISE EXCEPTION 'project emergency stop is active'; END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER project_runs_emergency_latch_guard BEFORE INSERT OR UPDATE OF status "
        "ON public.project_runs FOR EACH ROW EXECUTE FUNCTION public.project_runs_emergency_latch_guard()"
    )


def upgrade() -> None:
    op.drop_constraint("event_type_valid", "run_steps", type_="check")
    op.create_check_constraint("event_type_valid", "run_steps", _NEW_RUN_STEP_CHECK)
    _create_tables()
    for table in (
        "emergency_control_bindings",
        "emergency_control_authority_members",
        "emergency_stop_events",
        "emergency_stop_run_effects",
        "emergency_rollback_authorizations",
    ):
        _tenant_table(table)
    _create_graph_guards()


def downgrade() -> None:
    op.execute(
        """DO $fn$ BEGIN
        IF EXISTS (SELECT 1 FROM public.emergency_control_bindings)
           OR EXISTS (SELECT 1 FROM public.emergency_control_authority_members)
           OR EXISTS (SELECT 1 FROM public.emergency_stop_events)
           OR EXISTS (SELECT 1 FROM public.emergency_stop_run_effects)
           OR EXISTS (SELECT 1 FROM public.emergency_rollback_authorizations) THEN
          RAISE EXCEPTION 'cannot downgrade Slice 54 while emergency-control rows exist';
        END IF; END $fn$"""
    )
    op.execute("DROP TRIGGER project_runs_emergency_latch_guard ON public.project_runs")
    op.execute("DROP FUNCTION public.project_runs_emergency_latch_guard()")
    for table in (
        "emergency_control_bindings",
        "emergency_control_authority_members",
        "emergency_stop_events",
        "emergency_stop_run_effects",
        "emergency_rollback_authorizations",
    ):
        op.execute(f"DROP TRIGGER {table}_graph_guard ON public.{table}")
    op.execute("DROP FUNCTION public.slice54_graph_guard()")
    op.execute("DROP FUNCTION public.slice54_validate_event(uuid)")
    op.execute("DROP FUNCTION public.slice54_validate_binding(uuid)")
    op.execute("DROP INDEX public.uq_ese_project_root")
    for table in (
        "emergency_rollback_authorizations",
        "emergency_stop_run_effects",
        "emergency_stop_events",
        "emergency_control_authority_members",
        "emergency_control_bindings",
    ):
        op.drop_table(table)
        op.execute(f"DROP FUNCTION public.{table}_block_dml()")
    op.drop_constraint("event_type_valid", "run_steps", type_="check")
    op.create_check_constraint("event_type_valid", "run_steps", _OLD_RUN_STEP_CHECK)
