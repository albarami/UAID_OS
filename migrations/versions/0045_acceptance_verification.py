"""acceptance authorship verification

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "acceptance_criterion_authorship_records",
    "acceptance_verification_runs",
    "acceptance_verification_results",
)
_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_CONTRACT_HASH = "sha256:2451a65871b26a8f7cbe1d5adaa80af5917df336ed8ad1dcc1ae0c0a54f5e893"


def upgrade() -> None:
    op.create_table(
        "acceptance_criterion_authorship_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("acceptance_criterion_id", sa.UUID(), nullable=False),
        sa.Column("supersedes_record_id", sa.UUID(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("authorship_status", sa.Text(), nullable=False),
        sa.Column("authorship_provenance", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("extraction_proposal_id", sa.UUID(), nullable=True),
        sa.Column("generator_instance_id", sa.UUID(), nullable=True),
        sa.Column("reviewer_instance_id", sa.UUID(), nullable=True),
        sa.Column("approval_id", sa.UUID(), nullable=True),
        sa.Column("approval_basis", sa.Text(), nullable=True),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_acar_sequence_positive"),
        sa.CheckConstraint("authorship_status IN ('user_authored','user_authored_system_normalized','system_authored_unapproved','system_authored_human_approved','system_authored_independent_approved','disputed')", name="ck_acar_status_valid"),
        sa.CheckConstraint("authorship_provenance IN ('caller_supplied_unverified','db_verified_independent_agent_lineage')", name="ck_acar_provenance_valid"),
        sa.CheckConstraint("source_kind IN ('agent_generated','extraction_promoted')", name="ck_acar_source_kind_valid"),
        sa.CheckConstraint("approval_basis IS NULL OR approval_basis IN ('human_owner','independent_agent_lineage')", name="ck_acar_approval_basis_valid"),
        sa.CheckConstraint("evidence_reference ~ '^sha256:[0-9a-f]{64}$'", name="ck_acar_evidence_digest"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name="fk_acar_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT", name="project_tenant"),
        sa.ForeignKeyConstraint(["acceptance_criterion_id", "project_id", "tenant_id"], ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"], ondelete="RESTRICT", name="criterion_project_tenant"),
        sa.ForeignKeyConstraint(["supersedes_record_id", "acceptance_criterion_id", "project_id", "tenant_id"], ["acceptance_criterion_authorship_records.id", "acceptance_criterion_authorship_records.acceptance_criterion_id", "acceptance_criterion_authorship_records.project_id", "acceptance_criterion_authorship_records.tenant_id"], ondelete="RESTRICT", name="supersedes_chain"),
        sa.ForeignKeyConstraint(["generator_instance_id", "project_id", "tenant_id"], ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"], ondelete="RESTRICT", name="generator_project_tenant"),
        sa.ForeignKeyConstraint(["reviewer_instance_id", "project_id", "tenant_id"], ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"], ondelete="RESTRICT", name="reviewer_project_tenant"),
        sa.ForeignKeyConstraint(["approval_id", "project_id", "tenant_id"], ["approvals.id", "approvals.project_id", "approvals.tenant_id"], ondelete="RESTRICT", name="approval_project_tenant"),
        sa.ForeignKeyConstraint(["extraction_proposal_id", "project_id", "tenant_id"], ["extraction_proposals.id", "extraction_proposals.project_id", "extraction_proposals.tenant_id"], ondelete="RESTRICT", name="extraction_proposal_project_tenant"),
        sa.PrimaryKeyConstraint("id", name="pk_acceptance_criterion_authorship_records"),
        sa.UniqueConstraint("id", "acceptance_criterion_id", "project_id", "tenant_id", name="uq_acar_chain_target"),
        sa.UniqueConstraint("acceptance_criterion_id", "sequence", name="uq_acar_criterion_sequence"),
        sa.UniqueConstraint("supersedes_record_id", name="uq_acar_supersedes_once"),
    )
    op.create_index("ix_acar_current", "acceptance_criterion_authorship_records", ["tenant_id", "project_id", "acceptance_criterion_id", "sequence", "id"])
    op.create_table(
        "acceptance_verification_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False), sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("scope_digest", sa.Text(), nullable=False), sa.Column("authorship_digest", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False), sa.Column("verifier_contract_hash", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False), sa.Column("execution_provenance", sa.Text(), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True), sa.Column("reported_scope_count", sa.Integer(), nullable=False),
        sa.Column("reported_eligible_count", sa.Integer(), nullable=False), sa.Column("reported_unapproved_count", sa.Integer(), nullable=False),
        sa.Column("reported_disputed_count", sa.Integer(), nullable=False), sa.Column("reported_missing_or_untrusted_count", sa.Integer(), nullable=False),
        sa.Column("reported_controls_failed_count", sa.Integer(), nullable=False), sa.Column("evidence_consistent", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint("scope_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_avr_scope_digest"),
        sa.CheckConstraint("authorship_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_avr_authorship_digest"),
        sa.CheckConstraint(f"verifier_contract_hash = '{_CONTRACT_HASH}'", name="ck_avr_contract_hash"),
        sa.CheckConstraint("schema_version = 'slice46.acceptance_verification.v1'", name="ck_avr_schema_version"),
        sa.CheckConstraint("execution_status IN ('succeeded','failed','refused')", name="ck_avr_execution_status"),
        sa.CheckConstraint("execution_provenance = 'system_executed_structural'", name="ck_avr_execution_provenance"),
        sa.CheckConstraint("verdict IN ('eligible','blocked')", name="ck_avr_verdict"),
        sa.CheckConstraint("reported_scope_count BETWEEN 0 AND 10000 AND reported_eligible_count BETWEEN 0 AND 10000 AND reported_unapproved_count BETWEEN 0 AND 10000 AND reported_disputed_count BETWEEN 0 AND 10000 AND reported_missing_or_untrusted_count BETWEEN 0 AND 10000 AND reported_controls_failed_count BETWEEN 0 AND 10000", name="ck_avr_counts_bounded"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name="fk_avr_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT", name="project_tenant"),
        sa.PrimaryKeyConstraint("id", name="pk_acceptance_verification_runs"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_avr_id_project_tenant"),
    )
    op.create_index("ix_acceptance_verification_latest", "acceptance_verification_runs", ["tenant_id", "project_id", "scope_digest", "authorship_digest", "verifier_contract_hash", "created_at", "id"])
    op.create_table(
        "acceptance_verification_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False), sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("acceptance_verification_run_id", sa.UUID(), nullable=False), sa.Column("acceptance_criterion_id", sa.UUID(), nullable=False),
        sa.Column("authorship_record_id", sa.UUID(), nullable=True), sa.Column("authorship_status", sa.Text(), nullable=True),
        sa.Column("authorship_provenance", sa.Text(), nullable=True), sa.Column("source_kind", sa.Text(), nullable=True),
        sa.Column("eligibility_status", sa.Text(), nullable=False), sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint("eligibility_status IN ('eligible','missing','untrusted','unapproved','disputed','controls_failed')", name="ck_avres_eligibility_status"),
        sa.CheckConstraint("octet_length(reason_code) BETWEEN 1 AND 128 AND btrim(reason_code) <> ''", name="ck_avres_reason_code_bounded"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name="fk_avres_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT", name="project_tenant"),
        sa.ForeignKeyConstraint(["acceptance_verification_run_id", "project_id", "tenant_id"], ["acceptance_verification_runs.id", "acceptance_verification_runs.project_id", "acceptance_verification_runs.tenant_id"], ondelete="RESTRICT", name="run_project_tenant"),
        sa.ForeignKeyConstraint(["acceptance_criterion_id", "project_id", "tenant_id"], ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"], ondelete="RESTRICT", name="criterion_project_tenant"),
        sa.ForeignKeyConstraint(["authorship_record_id", "acceptance_criterion_id", "project_id", "tenant_id"], ["acceptance_criterion_authorship_records.id", "acceptance_criterion_authorship_records.acceptance_criterion_id", "acceptance_criterion_authorship_records.project_id", "acceptance_criterion_authorship_records.tenant_id"], ondelete="RESTRICT", name="authorship_project_tenant"),
        sa.PrimaryKeyConstraint("id", name="pk_acceptance_verification_results"),
        sa.UniqueConstraint("acceptance_verification_run_id", "acceptance_criterion_id", name="uq_avres_run_criterion"),
    )
    _install_guards()
    _apply_security()


def _install_guards() -> None:
    op.execute("""
    CREATE FUNCTION public.acceptance_authorship_guard() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
    DECLARE a record; prior record; g record; r record; ok int;
    BEGIN
      SELECT c.kind, p.kind parent_kind INTO a FROM public.intake_artifacts c
      LEFT JOIN public.intake_artifacts p ON p.id=c.parent_id AND p.project_id=c.project_id AND p.tenant_id=c.tenant_id
      WHERE c.id=NEW.acceptance_criterion_id AND c.project_id=NEW.project_id AND c.tenant_id=NEW.tenant_id;
      IF a.kind IS DISTINCT FROM 'acceptance_criterion' OR a.parent_kind IS DISTINCT FROM 'requirement' THEN
        RAISE EXCEPTION 'acceptance authorship requires a canonical acceptance criterion with requirement parent';
      END IF;
      SELECT * INTO prior FROM public.acceptance_criterion_authorship_records
      WHERE acceptance_criterion_id=NEW.acceptance_criterion_id AND project_id=NEW.project_id AND tenant_id=NEW.tenant_id
      ORDER BY sequence DESC,id DESC LIMIT 1;
      IF prior.id IS NULL THEN
        IF NEW.sequence<>1 OR NEW.supersedes_record_id IS NOT NULL THEN RAISE EXCEPTION 'acceptance authorship chain must start at sequence 1'; END IF;
      ELSE
        IF NEW.supersedes_record_id IS DISTINCT FROM prior.id OR NEW.sequence<>prior.sequence+1 OR NEW.authorship_status=prior.authorship_status THEN
          RAISE EXCEPTION 'acceptance authorship chain must linearly supersede the current record';
        END IF;
      END IF;
      IF NEW.authorship_status='system_authored_independent_approved' THEN
        IF NEW.authorship_provenance<>'db_verified_independent_agent_lineage' OR NEW.source_kind<>'agent_generated'
           OR NEW.generator_instance_id IS NULL OR NEW.reviewer_instance_id IS NULL OR NEW.approval_id IS NULL
           OR NEW.approval_basis<>'independent_agent_lineage' OR NEW.extraction_proposal_id IS NOT NULL THEN
          RAISE EXCEPTION 'verified independent-agent evidence is required';
        END IF;
        SELECT i.id,v.id version_id,v.blueprint_id,v.content_hash,v.model_route,b.archetype,b.status,i.status instance_status
          INTO g FROM public.agent_instances i JOIN public.agent_versions v ON v.id=i.version_id JOIN public.agent_blueprints b ON b.id=v.blueprint_id
          WHERE i.id=NEW.generator_instance_id AND i.project_id=NEW.project_id AND i.tenant_id=NEW.tenant_id;
        SELECT i.id,v.id version_id,v.blueprint_id,v.content_hash,v.model_route,b.archetype,b.status,i.status instance_status
          INTO r FROM public.agent_instances i JOIN public.agent_versions v ON v.id=i.version_id JOIN public.agent_blueprints b ON b.id=v.blueprint_id
          WHERE i.id=NEW.reviewer_instance_id AND i.project_id=NEW.project_id AND i.tenant_id=NEW.tenant_id;
        SELECT count(*) INTO ok FROM public.agent_realizations ar WHERE ar.instance_id=NEW.reviewer_instance_id
          AND ar.project_id=NEW.project_id AND ar.tenant_id=NEW.tenant_id AND ar.qualification_status='qualified';
        IF g.id IS NULL OR r.id IS NULL OR g.instance_status<>'active' OR r.instance_status<>'active'
           OR g.status<>'active' OR r.status<>'active' OR g.archetype<>'builder' OR r.archetype<>'reviewer' OR ok<>1
           OR g.blueprint_id=r.blueprint_id OR g.content_hash=r.content_hash OR g.model_route=r.model_route THEN
          RAISE EXCEPTION 'verified independent-agent evidence fails lineage separation';
        END IF;
        SELECT count(*) INTO ok FROM public.approvals ap WHERE ap.id=NEW.approval_id AND ap.project_id=NEW.project_id
          AND ap.tenant_id=NEW.tenant_id AND ap.action='approve_acceptance_authorship'
          AND ap.subject_ref='acceptance_criterion:'||NEW.acceptance_criterion_id::text AND ap.status='approved'
          AND ap.requested_by=NEW.generator_instance_id::text AND ap.resolved_by=NEW.reviewer_instance_id::text
          AND ap.requested_by_provenance='request_authenticated' AND ap.approver_provenance='request_authenticated'
          AND NOT EXISTS (SELECT 1 FROM public.acceptance_criterion_authorship_records used
            WHERE used.acceptance_criterion_id=NEW.acceptance_criterion_id AND used.project_id=NEW.project_id
              AND used.tenant_id=NEW.tenant_id AND used.approval_id=NEW.approval_id);
        IF ok<>1 THEN RAISE EXCEPTION 'verified independent-agent evidence requires a bound approval decision'; END IF;
      ELSIF NEW.authorship_status='system_authored_unapproved' THEN
        IF NEW.authorship_provenance<>'caller_supplied_unverified' OR NEW.source_kind<>'extraction_promoted'
           OR NEW.extraction_proposal_id IS NULL OR NEW.generator_instance_id IS NOT NULL OR NEW.reviewer_instance_id IS NOT NULL
           OR NEW.approval_id IS NOT NULL OR NEW.approval_basis IS NOT NULL THEN
          RAISE EXCEPTION 'system-authored unapproved evidence requires the exact extraction bridge';
        END IF;
        SELECT count(*) INTO ok FROM public.extraction_promotions ep WHERE ep.extraction_proposal_id=NEW.extraction_proposal_id
          AND ep.artifact_id=NEW.acceptance_criterion_id AND ep.project_id=NEW.project_id AND ep.tenant_id=NEW.tenant_id;
        IF ok<>1 THEN RAISE EXCEPTION 'system-authored unapproved evidence requires the exact extraction bridge'; END IF;
      ELSIF NEW.authorship_status='disputed' THEN
        IF prior.id IS NULL OR NEW.authorship_provenance<>'caller_supplied_unverified' THEN RAISE EXCEPTION 'dispute must supersede an existing record'; END IF;
      ELSE
        IF NEW.authorship_provenance<>'caller_supplied_unverified' THEN RAISE EXCEPTION 'unsupported authorship trust upgrade'; END IF;
      END IF;
      RETURN NEW;
    END $fn$;
    """)
    op.execute("CREATE TRIGGER acceptance_authorship_guard BEFORE INSERT ON acceptance_criterion_authorship_records FOR EACH ROW EXECUTE FUNCTION public.acceptance_authorship_guard()")
    op.execute("""
    CREATE FUNCTION public.acceptance_result_guard() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
    DECLARE current_record record; expected text; expected_reason text;
    BEGIN
      SELECT * INTO current_record FROM public.acceptance_criterion_authorship_records
      WHERE acceptance_criterion_id=NEW.acceptance_criterion_id AND project_id=NEW.project_id AND tenant_id=NEW.tenant_id
      ORDER BY sequence DESC,id DESC LIMIT 1;
      IF current_record.id IS NULL THEN
        IF NEW.authorship_record_id IS NOT NULL OR NEW.authorship_status IS NOT NULL OR NEW.authorship_provenance IS NOT NULL OR NEW.source_kind IS NOT NULL THEN
          RAISE EXCEPTION 'acceptance verification result must use the current authorship record';
        END IF;
        expected:='missing'; expected_reason:='authorship_missing';
      ELSE
        IF NEW.authorship_record_id IS DISTINCT FROM current_record.id OR NEW.authorship_status IS DISTINCT FROM current_record.authorship_status
           OR NEW.authorship_provenance IS DISTINCT FROM current_record.authorship_provenance OR NEW.source_kind IS DISTINCT FROM current_record.source_kind THEN
          RAISE EXCEPTION 'acceptance verification result must use the current authorship record';
        END IF;
        IF current_record.authorship_status='system_authored_independent_approved' AND current_record.authorship_provenance='db_verified_independent_agent_lineage' THEN
          expected:='eligible'; expected_reason:='verified_independent_agent_approval';
        ELSIF current_record.authorship_status='system_authored_unapproved' THEN expected:='unapproved'; expected_reason:='generated_unapproved';
        ELSIF current_record.authorship_status='disputed' THEN expected:='disputed'; expected_reason:='unresolved_dispute';
        ELSE expected:='untrusted'; expected_reason:='approval_unverified'; END IF;
      END IF;
      IF NEW.eligibility_status<>expected OR NEW.reason_code<>expected_reason THEN RAISE EXCEPTION 'acceptance verification result eligibility is DB-derived'; END IF;
      RETURN NEW;
    END $fn$;
    """)
    op.execute("CREATE TRIGGER acceptance_result_guard BEFORE INSERT ON acceptance_verification_results FOR EACH ROW EXECUTE FUNCTION public.acceptance_result_guard()")
    op.execute("""
    CREATE FUNCTION public.verify_acceptance_run(target uuid) RETURNS void
    LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
    DECLARE r record; total int; eligible int; unapproved int; disputed int; missing_untrusted int; controls int; sd text; ad text;
    BEGIN
      SELECT * INTO r FROM public.acceptance_verification_runs WHERE id=target;
      IF r.id IS NULL THEN RETURN; END IF;
      SELECT count(*),count(*) FILTER (WHERE eligibility_status='eligible'),count(*) FILTER (WHERE eligibility_status='unapproved'),
        count(*) FILTER (WHERE eligibility_status='disputed'),count(*) FILTER (WHERE eligibility_status IN ('missing','untrusted')),
        count(*) FILTER (WHERE eligibility_status='controls_failed')
        INTO total,eligible,unapproved,disputed,missing_untrusted,controls
        FROM public.acceptance_verification_results WHERE acceptance_verification_run_id=target;
      IF r.execution_status IN ('failed','refused') THEN
        IF total<>0 OR r.reported_scope_count<>0 OR r.reported_eligible_count<>0 OR r.reported_unapproved_count<>0 OR r.reported_disputed_count<>0
           OR r.reported_missing_or_untrusted_count<>0 OR r.reported_controls_failed_count<>0 OR r.evidence_consistent OR r.verdict<>'blocked' OR r.failure_code IS NULL THEN
          RAISE EXCEPTION 'acceptance_verification_runs: aggregate mismatch'; END IF; RETURN;
      END IF;
      SELECT 'sha256:'||encode(sha256(convert_to(string_agg(acceptance_criterion_id::text,',' ORDER BY acceptance_criterion_id::text),'UTF8')),'hex') INTO sd
        FROM public.acceptance_verification_results WHERE acceptance_verification_run_id=target;
      SELECT 'sha256:'||encode(sha256(convert_to(string_agg(acceptance_criterion_id::text||':'||COALESCE(authorship_record_id::text,'missing'),',' ORDER BY acceptance_criterion_id::text),'UTF8')),'hex') INTO ad
        FROM public.acceptance_verification_results WHERE acceptance_verification_run_id=target;
      IF total=0 OR total<>r.reported_scope_count OR eligible<>r.reported_eligible_count OR unapproved<>r.reported_unapproved_count
         OR disputed<>r.reported_disputed_count OR missing_untrusted<>r.reported_missing_or_untrusted_count OR controls<>r.reported_controls_failed_count
         OR sd<>r.scope_digest OR ad<>r.authorship_digest OR NOT r.evidence_consistent
         OR (r.verdict='eligible') IS DISTINCT FROM (eligible=total AND unapproved=0 AND disputed=0 AND missing_untrusted=0 AND controls=0)
         OR r.failure_code IS NOT NULL THEN RAISE EXCEPTION 'acceptance_verification_runs: aggregate mismatch'; END IF;
    END $fn$;
    """)
    op.execute("""
    CREATE FUNCTION public.acceptance_run_trigger() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
      BEGIN PERFORM public.verify_acceptance_run(NEW.id); RETURN NULL; END $fn$
    """)
    op.execute("""
    CREATE FUNCTION public.acceptance_result_verify_trigger() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
      BEGIN PERFORM public.verify_acceptance_run(NEW.acceptance_verification_run_id); RETURN NULL; END $fn$
    """)
    op.execute("CREATE CONSTRAINT TRIGGER acceptance_runs_verify AFTER INSERT ON acceptance_verification_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.acceptance_run_trigger()")
    op.execute("CREATE CONSTRAINT TRIGGER acceptance_results_verify AFTER INSERT ON acceptance_verification_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.acceptance_result_verify_trigger()")


def _apply_security() -> None:
    op.execute("""
    CREATE FUNCTION public.acceptance_evidence_append_only() RETURNS trigger LANGUAGE plpgsql AS $fn$
    BEGIN RAISE EXCEPTION 'acceptance verification evidence is append-only'; END $fn$;
    """)
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})")
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"REVOKE ALL ON {table} FROM uaid_app")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")
        op.execute(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION public.acceptance_evidence_append_only()")
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION public.acceptance_evidence_append_only()")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.acceptance_result_verify_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.acceptance_run_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_acceptance_run(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.acceptance_result_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.acceptance_authorship_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.acceptance_evidence_append_only()")
