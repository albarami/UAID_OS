"""evidence-pack assembly, audit checkpoint, and internal export storage

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-13

Slice 49. Additive-only: one restricted global checkpoint table and four
tenant-owned immutable evidence-pack tables. Existing functions, including
``release_findings_guard()``, are not replaced or altered.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_HASH = r"^sha256:[0-9a-f]{64}$"
_SOURCE_KINDS = (
    "intake_artifact",
    "intake_provenance",
    "release_candidate_issue_binding",
    "risk_acceptance_record",
    "release_finding",
    "release_issue",
    "review_report",
    "test_oracle_run",
    "security_scan_run",
    "shortcut_detector_run",
    "acceptance_verification_run",
    "reviewer_quality_record",
)
_SECTIONS = (
    "scope",
    "traceability",
    "candidate_issues",
    "risk_acceptances",
    "review_reports",
    "test_oracles",
    "security_scans",
    "shortcut_detectors",
    "acceptance_verification",
    "reviewer_quality",
    "sanad_provenance",
    "audit_checkpoint",
)


def _append_only(table: str) -> None:
    op.execute(
        f"""
        CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN
          RAISE EXCEPTION '{table} is append-only';
        END $fn$
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
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def _global_table(table: str) -> None:
    _append_only(table)
    op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
    op.execute(f"GRANT SELECT ON {table} TO uaid_app")


def _create_checkpoint_table() -> None:
    op.create_table(
        "audit_chain_verifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("verifier_contract_version", sa.Text(), nullable=False),
        sa.Column("verifier_contract_hash", sa.Text(), nullable=False),
        sa.Column("verification_ok", sa.Boolean(), nullable=False),
        sa.Column("first_bad_seq", sa.BigInteger(), nullable=True),
        sa.Column("verified_through_seq", sa.BigInteger(), nullable=True),
        sa.Column("verified_through_entry_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "verifier_contract_version='slice49.evidence_audit.v1'",
            name="ck_audit_chain_verifications_contract_version",
        ),
        sa.CheckConstraint(
            f"verifier_contract_hash ~ '{_HASH}'",
            name="ck_audit_chain_verifications_contract_hash",
        ),
        sa.CheckConstraint(
            "(verification_ok AND first_bad_seq IS NULL "
            "AND verified_through_seq IS NOT NULL AND verified_through_seq>0 "
            "AND verified_through_entry_hash ~ '^[0-9a-f]{64}$') OR "
            "(NOT verification_ok AND first_bad_seq IS NOT NULL "
            "AND verified_through_seq IS NULL AND verified_through_entry_hash IS NULL)",
            name="ck_audit_chain_verifications_result_shape",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_chain_verifications"),
    )


def _create_runs_table() -> None:
    op.create_table(
        "evidence_pack_generation_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("audit_checkpoint_id", sa.UUID(), nullable=True),
        sa.Column("release_ref_digest", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("semantic_contract_version", sa.Text(), nullable=False),
        sa.Column("semantic_contract_hash", sa.Text(), nullable=False),
        sa.Column("projection_contract_version", sa.Text(), nullable=False),
        sa.Column("projection_contract_hash", sa.Text(), nullable=False),
        sa.Column("audit_contract_version", sa.Text(), nullable=False),
        sa.Column("audit_contract_hash", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("execution_provenance", sa.Text(), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("missing_required_section_count", sa.Integer(), nullable=False),
        sa.Column("inconsistent_section_count", sa.Integer(), nullable=False),
        sa.Column("source_ref_count", sa.Integer(), nullable=False),
        sa.Column("section_count", sa.Integer(), nullable=False),
        sa.Column("traceability_edge_count", sa.Integer(), nullable=False),
        sa.Column("canonical_byte_count", sa.Integer(), nullable=False),
        sa.Column("source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "schema_version='uaid.evidence_pack.v1.2'",
            name="ck_evidence_pack_generation_runs_schema_version",
        ),
        sa.CheckConstraint(
            "semantic_contract_version='slice49.evidence_pack.v1'",
            name="ck_evidence_pack_generation_runs_semantic_version",
        ),
        sa.CheckConstraint(
            "projection_contract_version='slice49.evidence_projection.v1'",
            name="ck_evidence_pack_generation_runs_projection_version",
        ),
        sa.CheckConstraint(
            "audit_contract_version='slice49.evidence_audit.v1'",
            name="ck_evidence_pack_generation_runs_audit_version",
        ),
        sa.CheckConstraint(
            f"semantic_contract_hash ~ '{_HASH}' AND projection_contract_hash ~ '{_HASH}' "
            f"AND audit_contract_hash ~ '{_HASH}' AND release_ref_digest ~ '{_HASH}'",
            name="ck_evidence_pack_generation_runs_hashes",
        ),
        sa.CheckConstraint(
            "execution_status IN ('succeeded','incomplete','failed','refused')",
            name="ck_evidence_pack_generation_runs_status",
        ),
        sa.CheckConstraint(
            "execution_provenance='system_assembled_evidence_pack'",
            name="ck_evidence_pack_generation_runs_provenance",
        ),
        sa.CheckConstraint(
            "(execution_status='succeeded' AND failure_code IS NULL "
            "AND missing_required_section_count=0 AND inconsistent_section_count=0) OR "
            "(execution_status='incomplete' AND failure_code IS NOT NULL "
            "AND (missing_required_section_count>0 OR inconsistent_section_count>0)) OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL)",
            name="ck_evidence_pack_generation_runs_result_shape",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (char_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code)<>'')",
            name="ck_evidence_pack_generation_runs_failure_code",
        ),
        sa.CheckConstraint(
            "missing_required_section_count BETWEEN 0 AND 12 "
            "AND inconsistent_section_count BETWEEN 0 AND 12 "
            "AND source_ref_count BETWEEN 0 AND 50000 "
            "AND traceability_edge_count BETWEEN 0 AND 50000 "
            "AND ((execution_status IN ('succeeded','incomplete') "
            "AND section_count=12 AND canonical_byte_count BETWEEN 2 AND 8388608) "
            "OR (execution_status IN ('failed','refused') "
            "AND section_count=0 AND canonical_byte_count=0))",
            name="ck_evidence_pack_generation_runs_counts",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
            name="audit_checkpoint",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_pack_generation_runs"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_epgr_id_project_tenant"
        ),
    )


def _create_packs_table() -> None:
    op.create_table(
        "evidence_packs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("generation_run_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("audit_checkpoint_id", sa.UUID(), nullable=False),
        sa.Column("assembly_status", sa.Text(), nullable=False),
        sa.Column("artifact_scope_digest", sa.Text(), nullable=False),
        sa.Column("issue_binding_digest", sa.Text(), nullable=False),
        sa.Column("source_set_digest", sa.Text(), nullable=False),
        sa.Column("traceability_digest", sa.Text(), nullable=False),
        sa.Column("repo_binding_state", sa.Text(), nullable=False),
        sa.Column("repo_binding_hash", sa.Text(), nullable=True),
        sa.Column("commit_sha", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("semantic_contract_version", sa.Text(), nullable=False),
        sa.Column("projection_contract_version", sa.Text(), nullable=False),
        sa.Column("audit_contract_version", sa.Text(), nullable=False),
        sa.Column("canonical_core_text", sa.Text(), nullable=False),
        sa.Column("core_content_hash", sa.Text(), nullable=False),
        sa.Column("verdict_status", sa.Text(), nullable=False),
        sa.Column("signature_status", sa.Text(), nullable=False),
        sa.Column("source_ref_count", sa.Integer(), nullable=False),
        sa.Column("section_count", sa.Integer(), nullable=False),
        sa.Column("traceability_edge_count", sa.Integer(), nullable=False),
        sa.Column("source_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assembly_status IN ('complete','incomplete')",
            name="ck_evidence_packs_status",
        ),
        sa.CheckConstraint(
            "repo_binding_state IN ('agreed','missing_trusted_binding','trusted_binding_disagreement')",
            name="ck_evidence_packs_repo_state",
        ),
        sa.CheckConstraint(
            f"(repo_binding_state='agreed' AND repo_binding_hash ~ '{_HASH}' "
            "AND commit_sha ~ '^[0-9a-f]{40}$') OR "
            "(repo_binding_state<>'agreed' AND repo_binding_hash IS NULL AND commit_sha IS NULL)",
            name="ck_evidence_packs_repo_shape",
        ),
        sa.CheckConstraint(
            f"artifact_scope_digest ~ '{_HASH}' AND issue_binding_digest ~ '{_HASH}' "
            f"AND source_set_digest ~ '{_HASH}' AND traceability_digest ~ '{_HASH}' "
            f"AND core_content_hash ~ '{_HASH}'",
            name="ck_evidence_packs_digests",
        ),
        sa.CheckConstraint(
            "verdict_status='absent_deferred_slice50' "
            "AND signature_status='unsigned_signer_tier_not_implemented'",
            name="ck_evidence_packs_attestations_deferred",
        ),
        sa.CheckConstraint(
            "source_ref_count BETWEEN 0 AND 50000 AND section_count=12 "
            "AND traceability_edge_count BETWEEN 0 AND 50000 "
            "AND octet_length(canonical_core_text) BETWEEN 2 AND 8388608",
            name="ck_evidence_packs_bounds",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["generation_run_id", "project_id", "tenant_id"],
            ["evidence_pack_generation_runs.id", "evidence_pack_generation_runs.project_id", "evidence_pack_generation_runs.tenant_id"],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            ["release_candidates.id", "release_candidates.project_id", "release_candidates.tenant_id"],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
            name="audit_checkpoint",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_packs"),
        sa.UniqueConstraint("generation_run_id", name="uq_evidence_packs_generation_run"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_ep_id_project_tenant"),
    )


def _create_children() -> None:
    op.create_table(
        "evidence_pack_source_refs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("truth_tier", sa.Text(), nullable=False),
        sa.Column("projection_digest", sa.Text(), nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_kind IN (" + ",".join(repr(value) for value in _SOURCE_KINDS) + ")",
            name="ck_evidence_pack_source_refs_source_kind",
        ),
        sa.CheckConstraint(
            "char_length(truth_tier) BETWEEN 1 AND 128 AND btrim(truth_tier)<>''",
            name="ck_evidence_pack_source_refs_truth_tier",
        ),
        sa.CheckConstraint(
            f"projection_digest ~ '{_HASH}'",
            name="ck_evidence_pack_source_refs_projection_digest",
        ),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 50000",
            name="ck_evidence_pack_source_refs_ordinal",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_pack_source_refs"),
        sa.UniqueConstraint(
            "evidence_pack_id", "ordinal", name="uq_epsr_pack_ordinal"
        ),
        sa.UniqueConstraint(
            "evidence_pack_id", "source_kind", "source_id", name="uq_epsr_pack_source"
        ),
    )
    op.create_table(
        "evidence_pack_section_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("section_code", sa.Text(), nullable=False),
        sa.Column("presence_code", sa.Text(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("section_digest", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "section_code IN (" + ",".join(repr(value) for value in _SECTIONS) + ")",
            name="ck_evidence_pack_section_results_section_code",
        ),
        sa.CheckConstraint(
            "presence_code IN ('present','present_zero_rows','missing_required_source',"
            "'inconsistent_source','unsupported_this_slice','deferred_to_slice_50',"
            "'deferred_to_slice_60')",
            name="ck_evidence_pack_section_results_presence_code",
        ),
        sa.CheckConstraint(
            "item_count BETWEEN 0 AND 10000",
            name="ck_evidence_pack_section_results_item_count",
        ),
        sa.CheckConstraint(
            f"section_digest ~ '{_HASH}'",
            name="ck_evidence_pack_section_results_section_digest",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (char_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code)<>'')",
            name="ck_evidence_pack_section_results_failure_code",
        ),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 12",
            name="ck_evidence_pack_section_results_ordinal",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_pack_section_results"),
        sa.UniqueConstraint(
            "evidence_pack_id", "section_code", name="uq_eps_pack_section"
        ),
        sa.UniqueConstraint(
            "evidence_pack_id", "ordinal", name="uq_eps_pack_ordinal"
        ),
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.evidence_pack_source_ref_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE ok boolean := false;
        BEGIN
          CASE NEW.source_kind
            WHEN 'intake_artifact' THEN
              SELECT EXISTS(SELECT 1 FROM public.intake_artifacts x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'intake_provenance' THEN
              SELECT EXISTS(SELECT 1 FROM public.intake_provenance x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'release_candidate_issue_binding' THEN
              SELECT EXISTS(SELECT 1 FROM public.release_candidate_issue_bindings x
                WHERE x.id=NEW.source_id AND x.tenant_id=NEW.tenant_id
                AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'risk_acceptance_record' THEN
              SELECT EXISTS(SELECT 1 FROM public.risk_acceptance_records x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'release_finding' THEN
              SELECT EXISTS(SELECT 1 FROM public.release_findings x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'release_issue' THEN
              SELECT EXISTS(SELECT 1 FROM public.release_issues x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'review_report' THEN
              SELECT EXISTS(SELECT 1 FROM public.review_reports x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'test_oracle_run' THEN
              SELECT EXISTS(SELECT 1 FROM public.test_oracle_runs x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'security_scan_run' THEN
              SELECT EXISTS(SELECT 1 FROM public.security_scan_runs x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'shortcut_detector_run' THEN
              SELECT EXISTS(SELECT 1 FROM public.shortcut_detector_runs x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'acceptance_verification_run' THEN
              SELECT EXISTS(SELECT 1 FROM public.acceptance_verification_runs x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            WHEN 'reviewer_quality_record' THEN
              SELECT EXISTS(SELECT 1 FROM public.reviewer_quality_records x WHERE x.id=NEW.source_id
                AND x.tenant_id=NEW.tenant_id AND x.project_id=NEW.project_id) INTO ok;
            ELSE ok := false;
          END CASE;
          IF NOT ok THEN RAISE EXCEPTION 'source kind does not resolve in the same tenant/project'; END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER evidence_pack_source_ref_guard BEFORE INSERT ON evidence_pack_source_refs "
        "FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_source_ref_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.evidence_pack_core_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE r record; c record; a record; payload jsonb;
        BEGIN
          SELECT * INTO r FROM public.evidence_pack_generation_runs WHERE id=NEW.generation_run_id;
          SELECT * INTO c FROM public.release_candidates WHERE id=NEW.release_candidate_id;
          SELECT * INTO a FROM public.audit_chain_verifications WHERE id=NEW.audit_checkpoint_id;
          IF r.id IS NULL OR r.tenant_id<>NEW.tenant_id OR r.project_id<>NEW.project_id
             OR r.release_candidate_id<>NEW.release_candidate_id
             OR r.audit_checkpoint_id<>NEW.audit_checkpoint_id THEN
            RAISE EXCEPTION 'core does not match its generation run';
          END IF;
          IF c.id IS NULL OR c.tenant_id<>NEW.tenant_id OR c.project_id<>NEW.project_id
             OR c.status<>'frozen' OR c.frozen_at IS NULL OR c.frozen_at<>NEW.source_cutoff THEN
            RAISE EXCEPTION 'new evidence core requires the exact currently frozen candidate';
          END IF;
          IF a.id IS NULL OR NOT a.verification_ok OR a.verified_through_seq IS NULL THEN
            RAISE EXCEPTION 'successful audit checkpoint required';
          END IF;
          IF (NEW.assembly_status='complete') IS DISTINCT FROM (r.execution_status='succeeded')
             OR (NEW.assembly_status='incomplete') IS DISTINCT FROM (r.execution_status='incomplete')
             OR r.source_ref_count<>NEW.source_ref_count OR r.section_count<>NEW.section_count
             OR r.traceability_edge_count<>NEW.traceability_edge_count
             OR r.canonical_byte_count<>octet_length(NEW.canonical_core_text)
             OR r.generated_at<>NEW.generated_at OR r.source_cutoff<>NEW.source_cutoff THEN
            RAISE EXCEPTION 'core/run generated properties mismatch';
          END IF;
          BEGIN payload := NEW.canonical_core_text::jsonb;
          EXCEPTION WHEN others THEN RAISE EXCEPTION 'canonical core text is not JSON'; END;
          IF payload ? 'verdict' OR payload ? 'signatures' OR payload ? 'signature'
             OR payload ? 'complete' OR payload ? 'verified' OR payload ? 'passed'
             OR payload ? 'trusted' OR payload ? 'signed' OR payload ? 'gate'
             OR payload ? 'ready' THEN
            RAISE EXCEPTION 'core contains forbidden truth or attestation fields';
          END IF;
          IF payload->>'schema_version'<>'uaid.evidence_pack.v1.2'
             OR payload->>'semantic_contract_version'<>'slice49.evidence_pack.v1'
             OR payload->>'projection_contract_version'<>'slice49.evidence_projection.v1'
             OR payload->>'project_id'<>NEW.project_id::text
             OR payload->>'release_id'<>NEW.release_candidate_id::text
             OR payload#>>'{integrity,audit_checkpoint,id}'<>NEW.audit_checkpoint_id::text
             OR payload#>>'{integrity,source_set_digest}'<>NEW.source_set_digest
             OR payload#>>'{integrity,traceability_digest}'<>NEW.traceability_digest
             OR NEW.core_content_hash<>'sha256:'||encode(
                sha256(convert_to(NEW.canonical_core_text,'UTF8')),'hex')
             OR payload#>>'{repo_commit_binding,state}'<>NEW.repo_binding_state
             OR payload#>>'{repo_commit_binding,repo_binding_hash}' IS DISTINCT FROM NEW.repo_binding_hash
             OR payload#>>'{repo_commit_binding,commit_sha}' IS DISTINCT FROM NEW.commit_sha THEN
            RAISE EXCEPTION 'canonical core metadata mismatch';
          END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER evidence_pack_core_guard BEFORE INSERT ON evidence_packs "
        "FOR EACH ROW EXECUTE FUNCTION public.evidence_pack_core_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_evidence_pack_children(pack_id uuid) RETURNS boolean
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE p record; payload jsonb; section_rows bigint; ref_rows bigint;
        DECLARE min_ref int; max_ref int; min_section int; max_section int;
        BEGIN
          SELECT * INTO p FROM public.evidence_packs WHERE id=pack_id;
          IF p.id IS NULL THEN RETURN true; END IF;
          payload := p.canonical_core_text::jsonb;
          SELECT count(*),min(ordinal),max(ordinal) INTO ref_rows,min_ref,max_ref
            FROM public.evidence_pack_source_refs WHERE evidence_pack_id=pack_id;
          IF ref_rows<>p.source_ref_count
             OR (ref_rows>0 AND (min_ref<>1 OR max_ref<>ref_rows)) THEN
            RAISE EXCEPTION 'declared source-ref count/ordinals mismatch';
          END IF;
          IF jsonb_array_length(payload->'source_refs')<>ref_rows THEN
            RAISE EXCEPTION 'canonical source-ref count mismatch';
          END IF;
          IF EXISTS (
            SELECT 1 FROM public.evidence_pack_source_refs s
            LEFT JOIN LATERAL (
              SELECT value,ordinality FROM jsonb_array_elements(payload->'source_refs')
                WITH ORDINALITY AS source(value,ordinality)
              WHERE value->>'source_kind'=s.source_kind
                AND value->>'source_id'=s.source_id::text
            ) j ON true
            WHERE s.evidence_pack_id=pack_id AND (
              j.value IS NULL OR j.ordinality<>s.ordinal
              OR j.value->>'truth_tier'<>s.truth_tier
              OR j.value->>'projection_digest'<>s.projection_digest
              OR (j.value->>'source_created_at')::timestamptz<>s.source_created_at)
          ) THEN RAISE EXCEPTION 'source reference projection mismatch'; END IF;
          SELECT count(*),min(ordinal),max(ordinal) INTO section_rows,min_section,max_section
            FROM public.evidence_pack_section_results WHERE evidence_pack_id=pack_id;
          IF section_rows<>p.section_count OR min_section<>1 OR max_section<>section_rows THEN
            RAISE EXCEPTION 'declared section count/ordinals mismatch';
          END IF;
          IF jsonb_array_length(payload->'source_inventory')<>section_rows
             OR jsonb_array_length(payload->'traceability')<>p.traceability_edge_count THEN
            RAISE EXCEPTION 'canonical inventory/traceability counts mismatch';
          END IF;
          IF EXISTS (
            SELECT 1 FROM public.evidence_pack_section_results s
            LEFT JOIN LATERAL (
              SELECT value FROM jsonb_array_elements(payload->'source_inventory') value
              WHERE value->>'section_code'=s.section_code
            ) j ON true
            WHERE s.evidence_pack_id=pack_id AND (
              j.value IS NULL OR j.value->>'presence_code'<>s.presence_code
              OR (j.value->>'item_count')::int<>s.item_count
              OR j.value->>'section_digest'<>s.section_digest
              OR (j.value->>'required')::boolean<>s.required
              OR j.value->>'failure_code' IS DISTINCT FROM s.failure_code)
          ) THEN RAISE EXCEPTION 'section inventory mismatch'; END IF;
          RETURN true;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_evidence_pack_children_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE row_new jsonb := to_jsonb(NEW); row_old jsonb := to_jsonb(OLD);
        BEGIN
          PERFORM public.verify_evidence_pack_children(
            CASE WHEN TG_TABLE_NAME='evidence_packs'
                 THEN COALESCE((row_new->>'id')::uuid,(row_old->>'id')::uuid)
                 ELSE COALESCE((row_new->>'evidence_pack_id')::uuid,
                               (row_old->>'evidence_pack_id')::uuid) END);
          RETURN NULL;
        END $fn$
        """
    )
    for table in ("evidence_packs", "evidence_pack_source_refs", "evidence_pack_section_results"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_verify AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.verify_evidence_pack_children_trigger()"
        )


def upgrade() -> None:
    _create_checkpoint_table()
    _create_runs_table()
    _create_packs_table()
    _create_children()
    _create_guards()
    _global_table("audit_chain_verifications")
    for table in (
        "evidence_pack_generation_runs",
        "evidence_packs",
        "evidence_pack_source_refs",
        "evidence_pack_section_results",
    ):
        _tenant_table(table)


def downgrade() -> None:
    op.execute(
        """
        DO $fn$ BEGIN
          IF EXISTS(SELECT 1 FROM public.audit_chain_verifications)
             OR EXISTS(SELECT 1 FROM public.evidence_pack_generation_runs)
             OR EXISTS(SELECT 1 FROM public.evidence_packs)
             OR EXISTS(SELECT 1 FROM public.evidence_pack_source_refs)
             OR EXISTS(SELECT 1 FROM public.evidence_pack_section_results) THEN
            RAISE EXCEPTION 'Slice-49 rows exist; downgrade refuses to erase evidence history';
          END IF;
        END $fn$
        """
    )
    for table in ("evidence_packs", "evidence_pack_source_refs", "evidence_pack_section_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_verify ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS public.verify_evidence_pack_children_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_evidence_pack_children(uuid)")
    op.execute("DROP TRIGGER IF EXISTS evidence_pack_core_guard ON public.evidence_packs")
    op.execute("DROP FUNCTION IF EXISTS public.evidence_pack_core_guard()")
    op.execute(
        "DROP TRIGGER IF EXISTS evidence_pack_source_ref_guard ON public.evidence_pack_source_refs"
    )
    op.execute("DROP FUNCTION IF EXISTS public.evidence_pack_source_ref_guard()")
    for table in (
        "evidence_pack_section_results",
        "evidence_pack_source_refs",
        "evidence_packs",
        "evidence_pack_generation_runs",
        "audit_chain_verifications",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
        op.drop_table(table)
