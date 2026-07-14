"""request-authenticated production pre-approval evidence graph

Revision ID: 0052
Revises: 0051
Create Date: 2026-07-14

Slice 53. Additive-only: five tenant-owned RLS ENABLE+FORCE append-only tables, two
composite identity targets, and deferred graph guards.  It does not authorize production;
``can_go_live_autonomously`` remains a literal false in application code.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_HASH = r"^sha256:[0-9a-f]{64}$"
_CONDITION_HASH = "sha256:770c4b591c7e3a7b0070eb4e14aa817aeb2cc43bbcf426f96256a85ddd1a6022"
_GOVERNANCE_HASH = "sha256:0ca9c7483e406697e5f871481a584c0bddafa5b94829493d1d8b6c6e7963aeb3"


def _append_only(table: str) -> None:
    op.execute(
        f"""
        CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$
        """
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


def _create_policy_versions() -> None:
    op.create_table(
        "production_approval_policy_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("human_approval_category_id", sa.UUID(), nullable=False),
        sa.Column("go_live_checklist_category_id", sa.UUID(), nullable=False),
        sa.Column("policy_contract_version", sa.Text(), nullable=False),
        sa.Column("source_provenance", sa.Text(), nullable=False),
        sa.Column("policy_digest", sa.Text(), nullable=False),
        sa.Column("checklist_digest", sa.Text(), nullable=False),
        sa.Column("approval_channel", sa.Text(), nullable=False),
        sa.Column("production_realtime", sa.Boolean(), nullable=False),
        sa.Column("production_nonresponse_code", sa.Text(), nullable=False),
        sa.Column("governance_requirements_digest", sa.Text(), nullable=False),
        sa.Column("approver_count", sa.SmallInteger(), nullable=False),
        sa.Column("approver_set_digest", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.CheckConstraint(
            "policy_contract_version='slice53.production_approval_policy.v1' AND "
            "source_provenance='caller_supplied_unverified_structured_approval_policy'",
            name="ck_papv_contracts",
        ),
        sa.CheckConstraint(
            f"policy_digest ~ '{_HASH}' AND checklist_digest ~ '{_HASH}' AND "
            f"governance_requirements_digest='{_GOVERNANCE_HASH}' AND approver_set_digest ~ '{_HASH}'",
            name="ck_papv_digests",
        ),
        sa.CheckConstraint(
            "approval_channel='dashboard' AND production_realtime AND "
            "production_nonresponse_code='block_until_approval'",
            name="ck_papv_production_policy",
        ),
        sa.CheckConstraint("approver_count BETWEEN 1 AND 100", name="ck_papv_approver_count"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["human_approval_category_id", "project_id", "tenant_id"],
            ["intake_categories.id", "intake_categories.project_id", "intake_categories.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["go_live_checklist_category_id", "project_id", "tenant_id"],
            ["intake_categories.id", "intake_categories.project_id", "intake_categories.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_papv_id_project_tenant"),
    )
    op.create_index(
        "ix_papv_tenant_project_created",
        "production_approval_policy_versions",
        ["tenant_id", "project_id", "created_at"],
    )


def _create_policy_approvers() -> None:
    op.create_table(
        "production_approval_policy_approvers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("principal_subject_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 100", name="ck_papa_ordinal"),
        sa.CheckConstraint(f"principal_subject_hash ~ '{_HASH}'", name="ck_papa_subject_hash"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["policy_version_id", "project_id", "tenant_id"],
            [
                "production_approval_policy_versions.id",
                "production_approval_policy_versions.project_id",
                "production_approval_policy_versions.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_version_id", "ordinal", name="uq_papa_policy_ordinal"),
        sa.UniqueConstraint(
            "policy_version_id", "principal_subject_hash", name="uq_papa_policy_subject"
        ),
    )


def _create_requests() -> None:
    op.create_table(
        "production_preapproval_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("release_verdict_id", sa.UUID(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column("autonomy_policy_id", sa.UUID(), nullable=False),
        sa.Column("generic_approval_id", sa.UUID(), nullable=False),
        sa.Column("approval_notification_id", sa.UUID(), nullable=False),
        sa.Column("preapproval_contract_version", sa.Text(), nullable=False),
        sa.Column("condition_contract_version", sa.Text(), nullable=False),
        sa.Column("condition_contract_hash", sa.Text(), nullable=False),
        sa.Column("release_binding_digest", sa.Text(), nullable=False),
        sa.Column("core_content_hash", sa.Text(), nullable=False),
        sa.Column("issue_binding_digest", sa.Text(), nullable=False),
        sa.Column("source_set_digest", sa.Text(), nullable=False),
        sa.Column("traceability_digest", sa.Text(), nullable=False),
        sa.Column("verdict_input_digest", sa.Text(), nullable=False),
        sa.Column("verdict_contract_hash", sa.Text(), nullable=False),
        sa.Column("autonomy_policy_digest", sa.Text(), nullable=False),
        sa.Column("requester_subject_hash", sa.Text(), nullable=False),
        sa.Column("requester_actor_type", sa.Text(), nullable=False),
        sa.Column("requester_provenance", sa.Text(), nullable=False),
        sa.Column("request_idempotency_key_hash", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.CheckConstraint(
            "preapproval_contract_version='slice53.production_preapproval.v1' AND "
            "condition_contract_version='slice53.production_preapproval_conditions.v1'",
            name="ck_ppr_contracts",
        ),
        sa.CheckConstraint(
            f"condition_contract_hash='{_CONDITION_HASH}' AND release_binding_digest ~ '{_HASH}' AND "
            f"core_content_hash ~ '{_HASH}' AND issue_binding_digest ~ '{_HASH}' AND "
            f"source_set_digest ~ '{_HASH}' AND traceability_digest ~ '{_HASH}' AND "
            f"verdict_input_digest ~ '{_HASH}' AND verdict_contract_hash ~ '{_HASH}' AND "
            f"autonomy_policy_digest ~ '{_HASH}' AND requester_subject_hash ~ '{_HASH}' AND "
            f"request_idempotency_key_hash ~ '{_HASH}'",
            name="ck_ppr_digests",
        ),
        sa.CheckConstraint(
            "requester_actor_type IN ('human','service') AND requester_provenance='request_authenticated'",
            name="ck_ppr_requester",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
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
            ["generic_approval_id", "project_id", "tenant_id"],
            ["approvals.id", "approvals.project_id", "approvals.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approval_notification_id"], ["approval_notifications.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_ppr_id_project_tenant"),
        sa.UniqueConstraint("generic_approval_id", name="uq_ppr_generic_approval"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "request_idempotency_key_hash", name="uq_ppr_idempotency"
        ),
    )
    op.create_index(
        "ix_ppr_tenant_project_created",
        "production_preapproval_requests",
        ["tenant_id", "project_id", "created_at"],
    )


def _create_attestations() -> None:
    op.create_table(
        "production_preapproval_attestations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("generic_approval_id", sa.UUID(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("release_verdict_id", sa.UUID(), nullable=False),
        sa.Column("requester_subject_hash", sa.Text(), nullable=False),
        sa.Column("requester_actor_type", sa.Text(), nullable=False),
        sa.Column("requester_provenance", sa.Text(), nullable=False),
        sa.Column("approver_subject_hash", sa.Text(), nullable=False),
        sa.Column("approver_actor_type", sa.Text(), nullable=False),
        sa.Column("approver_provenance", sa.Text(), nullable=False),
        sa.Column("resolution_idempotency_key_hash", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attestation_result", sa.Text(), sa.Computed("'approved'::text"), nullable=False),
        sa.Column(
            "identity_separation_ok",
            sa.Boolean(),
            sa.Computed("requester_subject_hash<>approver_subject_hash"),
            nullable=False,
        ),
        sa.Column("policy_membership_ok", sa.Boolean(), nullable=False),
        sa.Column(
            "gate_eligible_at_creation",
            sa.Boolean(),
            sa.Computed(
                "requester_subject_hash<>approver_subject_hash AND "
                "requester_provenance='request_authenticated' AND "
                "approver_provenance='request_authenticated' AND approver_actor_type='human' AND "
                "policy_membership_ok AND expires_at>approved_at"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.CheckConstraint(
            f"requester_subject_hash ~ '{_HASH}' AND approver_subject_hash ~ '{_HASH}' AND "
            f"resolution_idempotency_key_hash ~ '{_HASH}'",
            name="ck_ppa_digests",
        ),
        sa.CheckConstraint(
            "requester_actor_type IN ('human','service') AND approver_actor_type='human' AND "
            "requester_provenance='request_authenticated' AND approver_provenance='request_authenticated'",
            name="ck_ppa_identity",
        ),
        sa.CheckConstraint(
            "valid_from=approved_at AND expires_at>approved_at AND "
            "expires_at<=approved_at + interval '24 hours'",
            name="ck_ppa_validity",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["request_id", "project_id", "tenant_id"],
            [
                "production_preapproval_requests.id",
                "production_preapproval_requests.project_id",
                "production_preapproval_requests.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["generic_approval_id", "project_id", "tenant_id"],
            ["approvals.id", "approvals.project_id", "approvals.tenant_id"],
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
        sa.UniqueConstraint("request_id", name="uq_ppa_request"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_ppa_id_project_tenant"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "resolution_idempotency_key_hash", name="uq_ppa_idempotency"
        ),
    )


def _create_lifecycle() -> None:
    op.create_table(
        "production_preapproval_lifecycle_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("attestation_id", sa.UUID(), nullable=False),
        sa.Column("previous_event_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor_subject_hash", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_provenance", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("idempotency_key_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('approved_anchor','revoked','superseded')", name="ck_pple_event_type"
        ),
        sa.CheckConstraint(
            f"actor_subject_hash ~ '{_HASH}' AND idempotency_key_hash ~ '{_HASH}'",
            name="ck_pple_digests",
        ),
        sa.CheckConstraint(
            "actor_type IN ('human','service') AND actor_provenance='request_authenticated'",
            name="ck_pple_actor",
        ),
        sa.CheckConstraint(
            "char_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code)<>''",
            name="ck_pple_reason",
        ),
        sa.CheckConstraint(
            "(event_type='approved_anchor' AND previous_event_id IS NULL) OR "
            "(event_type IN ('revoked','superseded') AND previous_event_id IS NOT NULL)",
            name="ck_pple_chain",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["attestation_id", "project_id", "tenant_id"],
            [
                "production_preapproval_attestations.id",
                "production_preapproval_attestations.project_id",
                "production_preapproval_attestations.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_event_id", "project_id", "tenant_id"],
            [
                "production_preapproval_lifecycle_events.id",
                "production_preapproval_lifecycle_events.project_id",
                "production_preapproval_lifecycle_events.tenant_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_pple_id_project_tenant"),
        sa.UniqueConstraint("attestation_id", "event_type", name="uq_pple_attestation_event"),
        sa.UniqueConstraint("previous_event_id", name="uq_pple_previous"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "idempotency_key_hash", name="uq_pple_idempotency"
        ),
    )
    op.create_index(
        "ix_pple_tenant_project_attestation_created",
        "production_preapproval_lifecycle_events",
        ["tenant_id", "project_id", "attestation_id", "created_at"],
    )


def _create_graph_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.slice53_validate_policy(policy_uuid uuid) RETURNS void
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE p record; pc integer; pd text; bad integer; hp jsonb; gc jsonb;
        BEGIN
          SELECT * INTO p FROM public.production_approval_policy_versions WHERE id=policy_uuid;
          IF NOT FOUND THEN RETURN; END IF;
          SELECT count(*), 'sha256:'||encode(sha256(convert_to(
                   string_agg(principal_subject_hash, chr(31) ORDER BY ordinal), 'UTF8')), 'hex')
            INTO pc,pd FROM public.production_approval_policy_approvers WHERE policy_version_id=p.id;
          IF pc<>p.approver_count OR pd<>p.approver_set_digest THEN
            RAISE EXCEPTION 'production approval policy member set mismatch';
          END IF;
          SELECT data INTO hp FROM public.intake_categories
           WHERE id=p.human_approval_category_id AND project_id=p.project_id AND tenant_id=p.tenant_id
             AND category='human_approval_policy' AND status='declared';
          SELECT data INTO gc FROM public.intake_categories
           WHERE id=p.go_live_checklist_category_id AND project_id=p.project_id AND tenant_id=p.tenant_id
             AND category='go_live_checklist' AND status='declared';
          IF hp IS NULL OR gc IS NULL OR hp->>'approval_channel'<>'dashboard'
             OR hp->'realtime_for' IS NULL OR NOT (hp->'realtime_for' ? 'production_deployment')
             OR hp#>>'{non_response_policy,production}'<>'block_until_approval'
             OR gc->'governance' <> '{"evidence_pack_complete":"required","approval_events_recorded":"required","separation_of_duties_confirmed":"required","open_issues_have_risk_acceptance":"required_if_any_open_issues"}'::jsonb THEN
            RAISE EXCEPTION 'production approval policy source projection mismatch';
          END IF;
          SELECT count(*) INTO bad FROM (
            SELECT COALESCE(a.ordinal,x.ordinal::smallint) ordinal
              FROM jsonb_array_elements_text(hp->'approvers') WITH ORDINALITY x(subject,ordinal)
              FULL JOIN (
                SELECT * FROM public.production_approval_policy_approvers
                 WHERE policy_version_id=p.id
              ) a ON a.ordinal=x.ordinal
             WHERE a.id IS NULL OR x.subject IS NULL OR
                   a.principal_subject_hash <> 'sha256:'||encode(sha256(convert_to(
                     '{"principal_subject":'||to_json(x.subject)::text||'}','UTF8')),'hex')
          ) mismatch;
          IF bad<>0 OR jsonb_array_length(hp->'approvers')<>p.approver_count THEN
            RAISE EXCEPTION 'production approval policy exact principals mismatch';
          END IF;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice53_validate_request(request_uuid uuid) RETURNS void
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE r record; a record; n record; p record; c record; e record; v record; au record;
                att record; ac integer; anchor_count integer; event_count integer; chain_count integer;
                expected_binding text;
        BEGIN
          SELECT * INTO r FROM public.production_preapproval_requests WHERE id=request_uuid;
          IF NOT FOUND THEN RETURN; END IF;
          PERFORM public.slice53_validate_policy(r.policy_version_id);
          SELECT * INTO p FROM public.production_approval_policy_versions WHERE id=r.policy_version_id;
          SELECT * INTO c FROM public.release_candidates WHERE id=r.release_candidate_id;
          SELECT * INTO e FROM public.evidence_packs WHERE id=r.evidence_pack_id;
          SELECT * INTO v FROM public.release_verdicts WHERE id=r.release_verdict_id;
          SELECT * INTO au FROM public.autonomy_policies WHERE id=r.autonomy_policy_id;
          SELECT * INTO a FROM public.approvals WHERE id=r.generic_approval_id;
          SELECT * INTO n FROM public.approval_notifications WHERE id=r.approval_notification_id;
          IF c.status<>'frozen' OR e.assembly_status<>'complete' OR e.release_candidate_id<>c.id
             OR v.release_candidate_id<>c.id OR v.evidence_pack_id<>e.id OR NOT v.gate_eligible
             OR p.project_id<>r.project_id OR au.project_id<>r.project_id THEN
            RAISE EXCEPTION 'production preapproval release graph mismatch';
          END IF;
          IF r.core_content_hash<>e.core_content_hash OR r.issue_binding_digest<>e.issue_binding_digest
             OR r.source_set_digest<>e.source_set_digest OR r.traceability_digest<>e.traceability_digest
             OR r.verdict_input_digest<>v.input_digest OR r.verdict_contract_hash<>v.verdict_contract_hash
             OR r.condition_contract_hash<>'sha256:770c4b591c7e3a7b0070eb4e14aa817aeb2cc43bbcf426f96256a85ddd1a6022' THEN
            RAISE EXCEPTION 'production preapproval bound digest mismatch';
          END IF;
          expected_binding := 'sha256:'||encode(sha256(convert_to(array_to_string(ARRAY[
             r.preapproval_contract_version,c.id::text,e.id::text,v.id::text,e.core_content_hash,
             e.issue_binding_digest,e.source_set_digest,e.traceability_digest,v.input_digest,
             v.verdict_contract_hash,r.autonomy_policy_digest,p.policy_digest,p.checklist_digest,
             r.condition_contract_hash],chr(31)),'UTF8')),'hex');
          IF r.release_binding_digest<>expected_binding THEN
            RAISE EXCEPTION 'production preapproval release binding digest mismatch';
          END IF;
          IF a.project_id<>r.project_id OR a.tenant_id<>r.tenant_id OR a.action<>'deploy_production'
             OR a.subject_ref<>'production_preapproval:'||r.id::text OR a.risk_tier<>'production'
             OR NOT a.requires_explicit_approval OR a.requested_by<>r.requester_subject_hash
             OR a.requested_by_provenance<>'request_authenticated' OR a.payload<>'{}'::jsonb
             OR a.status NOT IN ('pending','approved','rejected','cancelled') THEN
            RAISE EXCEPTION 'production-specific generic approval shape mismatch';
          END IF;
          IF n.approval_id<>a.id OR n.project_id<>r.project_id OR n.tenant_id<>r.tenant_id
             OR n.risk_tier<>'production' OR n.routing_mode<>'realtime' OR n.channel<>'dashboard' THEN
            RAISE EXCEPTION 'production approval notification graph mismatch';
          END IF;
          SELECT count(*) INTO ac FROM public.production_preapproval_attestations WHERE request_id=r.id;
          IF a.status='approved' AND ac<>1 THEN
            RAISE EXCEPTION 'approved production request requires exactly one attestation';
          ELSIF a.status<>'approved' AND ac<>0 THEN
            RAISE EXCEPTION 'non-approved production request cannot have an attestation';
          END IF;
          IF ac=1 THEN
            SELECT * INTO att FROM public.production_preapproval_attestations WHERE request_id=r.id;
            IF att.generic_approval_id<>a.id OR att.policy_version_id<>p.id
               OR att.release_candidate_id<>c.id OR att.evidence_pack_id<>e.id
               OR att.release_verdict_id<>v.id OR att.requester_subject_hash<>r.requester_subject_hash
               OR att.requester_actor_type<>r.requester_actor_type
               OR att.requester_provenance<>r.requester_provenance
               OR att.approver_subject_hash<>a.resolved_by OR a.approver_provenance<>'request_authenticated'
               OR a.resolved_at IS NULL OR att.approved_at<>a.resolved_at
               OR NOT att.identity_separation_ok OR NOT att.policy_membership_ok
               OR NOT att.gate_eligible_at_creation OR NOT EXISTS (
                    SELECT 1 FROM public.production_approval_policy_approvers m
                     WHERE m.policy_version_id=p.id
                       AND m.principal_subject_hash=att.approver_subject_hash) THEN
              RAISE EXCEPTION 'production preapproval attestation graph mismatch';
            END IF;
            SELECT count(*) INTO anchor_count FROM public.production_preapproval_lifecycle_events
             WHERE attestation_id=att.id AND event_type='approved_anchor';
            SELECT count(*) INTO event_count FROM public.production_preapproval_lifecycle_events
             WHERE attestation_id=att.id;
            WITH RECURSIVE chain AS (
              SELECT id FROM public.production_preapproval_lifecycle_events
               WHERE attestation_id=att.id AND event_type='approved_anchor' AND previous_event_id IS NULL
              UNION ALL
              SELECT x.id FROM public.production_preapproval_lifecycle_events x
                JOIN chain q ON x.previous_event_id=q.id WHERE x.attestation_id=att.id
            ) SELECT count(*) INTO chain_count FROM chain;
            IF anchor_count<>1 OR event_count<>chain_count THEN
              RAISE EXCEPTION 'production preapproval lifecycle is not one linear chain';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.production_preapproval_lifecycle_events x
                JOIN public.production_preapproval_lifecycle_events prev
                  ON prev.id=x.previous_event_id
               WHERE x.attestation_id=att.id AND x.created_at<=prev.created_at
            ) THEN RAISE EXCEPTION 'production preapproval lifecycle time order mismatch'; END IF;
            IF EXISTS (
              SELECT 1 FROM public.production_preapproval_lifecycle_events x
               WHERE x.attestation_id=att.id AND x.event_type<>'approved_anchor'
                 AND NOT EXISTS (SELECT 1 FROM public.production_approval_policy_approvers m
                   WHERE m.policy_version_id=p.id AND m.principal_subject_hash=x.actor_subject_hash)
            ) THEN RAISE EXCEPTION 'production preapproval lifecycle actor not in recorded policy'; END IF;
          END IF;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice53_graph_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE rid uuid; pid uuid;
        BEGIN
          IF TG_TABLE_NAME='production_approval_policy_versions' THEN pid:=NEW.id;
          ELSIF TG_TABLE_NAME='production_approval_policy_approvers' THEN pid:=NEW.policy_version_id;
          ELSIF TG_TABLE_NAME='production_preapproval_requests' THEN rid:=NEW.id;
          ELSIF TG_TABLE_NAME='production_preapproval_attestations' THEN rid:=NEW.request_id;
          ELSIF TG_TABLE_NAME='production_preapproval_lifecycle_events' THEN
            SELECT request_id INTO rid FROM public.production_preapproval_attestations WHERE id=NEW.attestation_id;
          ELSIF TG_TABLE_NAME='approvals' THEN
            SELECT id INTO rid FROM public.production_preapproval_requests WHERE generic_approval_id=NEW.id;
          END IF;
          IF pid IS NOT NULL THEN PERFORM public.slice53_validate_policy(pid); END IF;
          IF rid IS NOT NULL THEN PERFORM public.slice53_validate_request(rid); END IF;
          RETURN NEW;
        END $fn$
        """
    )
    for table in (
        "production_approval_policy_versions",
        "production_approval_policy_approvers",
        "production_preapproval_requests",
        "production_preapproval_attestations",
        "production_preapproval_lifecycle_events",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_graph_guard AFTER INSERT ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.slice53_graph_guard()"
        )
    op.execute(
        "CREATE CONSTRAINT TRIGGER approvals_production_preapproval_guard "
        "AFTER UPDATE OF status,resolved_by,resolved_at,approver_provenance ON public.approvals "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.slice53_graph_guard()"
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_intake_categories_id_proj_tenant", "intake_categories", ["id", "project_id", "tenant_id"]
    )
    op.create_unique_constraint(
        "uq_autonomy_policies_id_proj_tenant", "autonomy_policies", ["id", "project_id", "tenant_id"]
    )
    _create_policy_versions()
    _create_policy_approvers()
    _create_requests()
    _create_attestations()
    _create_lifecycle()
    for table in (
        "production_approval_policy_versions",
        "production_approval_policy_approvers",
        "production_preapproval_requests",
        "production_preapproval_attestations",
        "production_preapproval_lifecycle_events",
    ):
        _tenant_table(table)
    _create_graph_guards()


def downgrade() -> None:
    op.execute(
        """
        DO $fn$ BEGIN
          IF EXISTS (SELECT 1 FROM public.production_approval_policy_versions)
             OR EXISTS (SELECT 1 FROM public.production_approval_policy_approvers)
             OR EXISTS (SELECT 1 FROM public.production_preapproval_requests)
             OR EXISTS (SELECT 1 FROM public.production_preapproval_attestations)
             OR EXISTS (SELECT 1 FROM public.production_preapproval_lifecycle_events) THEN
            RAISE EXCEPTION 'cannot downgrade Slice 53 while production preapproval rows exist';
          END IF;
        END $fn$
        """
    )
    op.execute("DROP TRIGGER approvals_production_preapproval_guard ON public.approvals")
    for table in (
        "production_approval_policy_versions",
        "production_approval_policy_approvers",
        "production_preapproval_requests",
        "production_preapproval_attestations",
        "production_preapproval_lifecycle_events",
    ):
        op.execute(f"DROP TRIGGER {table}_graph_guard ON public.{table}")
    op.execute("DROP FUNCTION public.slice53_graph_guard()")
    op.execute("DROP FUNCTION public.slice53_validate_request(uuid)")
    op.execute("DROP FUNCTION public.slice53_validate_policy(uuid)")
    for table in (
        "production_preapproval_lifecycle_events",
        "production_preapproval_attestations",
        "production_preapproval_requests",
        "production_approval_policy_approvers",
        "production_approval_policy_versions",
    ):
        op.drop_table(table)
        op.execute(f"DROP FUNCTION public.{table}_block_dml()")
    op.drop_constraint("uq_autonomy_policies_id_proj_tenant", "autonomy_policies", type_="unique")
    op.drop_constraint("uq_intake_categories_id_proj_tenant", "intake_categories", type_="unique")
