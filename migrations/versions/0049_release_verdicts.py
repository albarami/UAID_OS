"""release-manager verdict attempts, attestations, and exact issue results

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-13

Slice 50. Additive-only: three tenant-owned, RLS ENABLE+FORCE, append-only tables.
Existing release, evidence-pack, findings, audit, and readiness objects are not replaced.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_HASH = r"^sha256:[0-9a-f]{64}$"
_VERDICT_CONTRACT_HASH = "sha256:793fd7d8aa26908192912a80ec39a6a0d6dddb397027fe3784996ae3b1d928e2"


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


def _create_runs() -> None:
    op.create_table(
        "release_verdict_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=True),
        sa.Column("input_contract_version", sa.Text(), nullable=False),
        sa.Column("verdict_contract_version", sa.Text(), nullable=False),
        sa.Column("projection_contract_version", sa.Text(), nullable=False),
        sa.Column("input_digest", sa.Text(), nullable=False),
        sa.Column("core_content_hash", sa.Text(), nullable=True),
        sa.Column("verdict_contract_hash", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("execution_provenance", sa.Text(), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "input_contract_version='slice50.release_verdict_input.v1' "
            "AND verdict_contract_version='slice50.release_verdict.v1' "
            "AND projection_contract_version='slice50.verdict_projection.v1'",
            name="ck_release_verdict_runs_contracts",
        ),
        sa.CheckConstraint(
            f"input_digest ~ '{_HASH}' AND verdict_contract_hash='{_VERDICT_CONTRACT_HASH}' "
            f"AND (core_content_hash IS NULL OR core_content_hash ~ '{_HASH}')",
            name="ck_release_verdict_runs_hashes",
        ),
        sa.CheckConstraint(
            "execution_status IN ('succeeded','failed','refused')",
            name="ck_release_verdict_runs_status",
        ),
        sa.CheckConstraint(
            "execution_provenance='system_derived_release_verdict'",
            name="ck_release_verdict_runs_provenance",
        ),
        sa.CheckConstraint(
            "(execution_status='succeeded' AND evidence_pack_id IS NOT NULL "
            "AND core_content_hash IS NOT NULL AND failure_code IS NULL) OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL)",
            name="ck_release_verdict_runs_result_shape",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (char_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code)<>'')",
            name="ck_release_verdict_runs_failure_code",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_release_verdict_runs"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_rvr_id_project_tenant"),
    )


def _create_verdicts() -> None:
    spec_expression = (
        "CASE WHEN missing_evidence_count>0 THEN 'failed_missing_evidence' "
        "WHEN blocking_issue_count>0 THEN 'failed_blocking_issue' "
        "WHEN unverified_authority_count>0 THEN 'requires_human_decision' "
        "WHEN limitation_count>0 THEN 'passed_with_limitations' ELSE 'passed' END"
    )
    canonical_expression = (
        "CASE WHEN missing_evidence_count>0 OR blocking_issue_count>0 THEN 'failed' "
        "WHEN unverified_authority_count>0 THEN 'blocked' "
        "WHEN limitation_count>0 THEN 'passed_with_accepted_risk' ELSE 'passed' END"
    )
    reason_expression = (
        "CASE WHEN missing_evidence_count>0 THEN 'bound_issue_provenance_incomplete' "
        "WHEN blocking_issue_count>0 THEN 'open_blocking_or_hard_refusal_issue' "
        "WHEN unverified_authority_count>0 THEN 'risk_acceptance_authority_unverified' "
        "WHEN limitation_count>0 THEN 'bound_release_limitations_authoritatively_accepted' "
        "ELSE 'bound_release_issue_disposition_clean' END"
    )
    op.create_table(
        "release_verdicts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("evidence_pack_id", sa.UUID(), nullable=False),
        sa.Column("audit_checkpoint_id", sa.UUID(), nullable=False),
        sa.Column("input_digest", sa.Text(), nullable=False),
        sa.Column("core_content_hash", sa.Text(), nullable=False),
        sa.Column("issue_binding_digest", sa.Text(), nullable=False),
        sa.Column("source_set_digest", sa.Text(), nullable=False),
        sa.Column("traceability_digest", sa.Text(), nullable=False),
        sa.Column("verdict_contract_hash", sa.Text(), nullable=False),
        sa.Column("input_contract_version", sa.Text(), nullable=False),
        sa.Column("verdict_contract_version", sa.Text(), nullable=False),
        sa.Column("projection_contract_version", sa.Text(), nullable=False),
        sa.Column("decision_scope", sa.Text(), nullable=False),
        sa.Column("execution_provenance", sa.Text(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("missing_evidence_count", sa.Integer(), nullable=False),
        sa.Column("blocking_issue_count", sa.Integer(), nullable=False),
        sa.Column("limitation_count", sa.Integer(), nullable=False),
        sa.Column("unverified_authority_count", sa.Integer(), nullable=False),
        sa.Column(
            "spec_verdict", sa.Text(), sa.Computed(spec_expression, persisted=True), nullable=False
        ),
        sa.Column(
            "canonical_verdict",
            sa.Text(),
            sa.Computed(canonical_expression, persisted=True),
            nullable=False,
        ),
        sa.Column(
            "reason_code", sa.Text(), sa.Computed(reason_expression, persisted=True), nullable=False
        ),
        sa.Column(
            "gate_eligible",
            sa.Boolean(),
            sa.Computed(
                "missing_evidence_count=0 AND blocking_issue_count=0 "
                "AND unverified_authority_count=0",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "input_contract_version='slice50.release_verdict_input.v1' "
            "AND verdict_contract_version='slice50.release_verdict.v1' "
            "AND projection_contract_version='slice50.verdict_projection.v1' "
            "AND decision_scope='known_bound_issue_disposition' "
            "AND execution_provenance='system_derived_release_verdict'",
            name="ck_release_verdicts_contracts",
        ),
        sa.CheckConstraint(
            f"input_digest ~ '{_HASH}' AND core_content_hash ~ '{_HASH}' "
            f"AND issue_binding_digest ~ '{_HASH}' AND source_set_digest ~ '{_HASH}' "
            f"AND traceability_digest ~ '{_HASH}' "
            f"AND verdict_contract_hash='{_VERDICT_CONTRACT_HASH}'",
            name="ck_release_verdicts_hashes",
        ),
        sa.CheckConstraint(
            "issue_count BETWEEN 0 AND 10000 AND missing_evidence_count BETWEEN 0 AND issue_count "
            "AND blocking_issue_count BETWEEN 0 AND issue_count "
            "AND limitation_count BETWEEN 0 AND issue_count "
            "AND unverified_authority_count BETWEEN 0 AND limitation_count",
            name="ck_release_verdicts_counts",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id", "tenant_id"],
            [
                "release_verdict_runs.id",
                "release_verdict_runs.project_id",
                "release_verdict_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id", "project_id", "tenant_id"],
            ["evidence_packs.id", "evidence_packs.project_id", "evidence_packs.tenant_id"],
            ondelete="RESTRICT",
            name="pack_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["audit_checkpoint_id"],
            ["audit_chain_verifications.id"],
            ondelete="RESTRICT",
            name="audit_checkpoint",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_release_verdicts"),
        sa.UniqueConstraint("run_id", name="uq_release_verdicts_run"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_rv_id_project_tenant"),
    )


def _create_issue_results() -> None:
    op.create_table(
        "release_verdict_issue_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("verdict_id", sa.UUID(), nullable=False),
        sa.Column("release_candidate_id", sa.UUID(), nullable=False),
        sa.Column("binding_id", sa.UUID(), nullable=False),
        sa.Column("issue_id", sa.UUID(), nullable=False),
        sa.Column("risk_acceptance_record_id", sa.UUID(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("issue_category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("blocking_category", sa.Text(), nullable=True),
        sa.Column("source_finding_id", sa.UUID(), nullable=True),
        sa.Column("issue_status", sa.Text(), nullable=False),
        sa.Column("source_provenance", sa.Text(), nullable=False),
        sa.Column("trusted_provenance", sa.Boolean(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("hard_blocker", sa.Boolean(), nullable=False),
        sa.Column("exact_risk_acceptance", sa.Boolean(), nullable=False),
        sa.Column("risk_authority_verified", sa.Boolean(), nullable=False),
        sa.Column("issue_projection_digest", sa.Text(), nullable=False),
        sa.Column("risk_projection_digest", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "issue_status IN ('open','resolved','accepted','superseded')",
            name="ck_release_verdict_issue_results_status",
        ),
        sa.CheckConstraint(
            "issue_category IN ('security','shortcut','test_or_acceptance','cost',"
            "'deployment','rollback','monitoring','evidence','approval','other') "
            "AND severity IN ('low','medium','high','critical')",
            name="ck_release_verdict_issue_results_taxonomy",
        ),
        sa.CheckConstraint(
            "char_length(source_provenance) BETWEEN 1 AND 128 AND btrim(source_provenance)<>''",
            name="ck_release_verdict_issue_results_provenance",
        ),
        sa.CheckConstraint(
            f"issue_projection_digest ~ '{_HASH}' AND "
            f"(risk_projection_digest IS NULL OR risk_projection_digest ~ '{_HASH}')",
            name="ck_release_verdict_issue_results_digests",
        ),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 10000 AND "
            "(exact_risk_acceptance OR (risk_acceptance_record_id IS NULL "
            "AND risk_projection_digest IS NULL AND NOT risk_authority_verified))",
            name="ck_release_verdict_issue_results_shape",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["verdict_id", "project_id", "tenant_id"],
            ["release_verdicts.id", "release_verdicts.project_id", "release_verdicts.tenant_id"],
            ondelete="RESTRICT",
            name="verdict_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["release_candidate_id", "project_id", "tenant_id"],
            [
                "release_candidates.id",
                "release_candidates.project_id",
                "release_candidates.tenant_id",
            ],
            ondelete="RESTRICT",
            name="candidate_project_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["release_candidate_issue_bindings.id"],
            ondelete="RESTRICT",
            name="binding",
        ),
        sa.ForeignKeyConstraint(
            ["issue_id", "tenant_id"],
            ["release_issues.id", "release_issues.tenant_id"],
            ondelete="RESTRICT",
            name="issue_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["risk_acceptance_record_id", "tenant_id"],
            ["risk_acceptance_records.id", "risk_acceptance_records.tenant_id"],
            ondelete="RESTRICT",
            name="risk_tenant",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_release_verdict_issue_results"),
        sa.UniqueConstraint("verdict_id", "binding_id", name="uq_rvir_verdict_binding"),
        sa.UniqueConstraint("verdict_id", "ordinal", name="uq_rvir_verdict_ordinal"),
    )


def _create_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.slice50_release_issue_projection_digest(issue_uuid uuid)
        RETURNS text LANGUAGE sql STABLE SET search_path=pg_catalog AS $fn$
          SELECT 'sha256:' || encode(sha256(convert_to(
            '{"blocking":' || CASE WHEN i.blocking THEN 'true' ELSE 'false' END ||
            ',"blocking_category":' || COALESCE(to_json(i.blocking_category)::text,'null') ||
            ',"id":' || to_json(i.id::text)::text ||
            ',"issue_category":' || to_json(i.issue_category)::text ||
            ',"severity":' || to_json(i.severity)::text ||
            ',"source_finding_id":' || COALESCE(to_json(i.source_finding_id::text)::text,'null') ||
            ',"source_provenance":' || to_json(i.source_provenance)::text ||
            ',"status":' || to_json(i.status)::text || '}', 'UTF8')), 'hex')
          FROM public.release_issues i WHERE i.id=issue_uuid
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.slice50_risk_projection_digest(risk_uuid uuid)
        RETURNS text LANGUAGE sql STABLE SET search_path=pg_catalog AS $fn$
          SELECT 'sha256:' || encode(sha256(convert_to(
            '{"approver_provenance":' || to_json(r.approver_provenance)::text ||
            ',"blocking_category":' || COALESCE(to_json(r.blocking_category)::text,'null') ||
            ',"expires_at":' || to_json(r.expiry_date::text)::text ||
            ',"id":' || to_json(r.id::text)::text ||
            ',"release_ref_digest":' || to_json('sha256:' || encode(sha256(
              convert_to(r.release_id,'UTF8')), 'hex'))::text ||
            ',"severity":' || to_json(r.severity)::text ||
            ',"status":' || to_json(r.status)::text ||
            ',"subject_id":' || to_json(r.issue_id)::text ||
            ',"subject_type":' || COALESCE(to_json(r.subject_type)::text,'null') || '}',
            'UTF8')), 'hex')
          FROM public.risk_acceptance_records r WHERE r.id=risk_uuid
        $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.release_verdict_run_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE p record; c record;
        BEGIN
          SELECT * INTO c FROM public.release_candidates WHERE id=NEW.release_candidate_id;
          IF c.id IS NULL OR c.tenant_id<>NEW.tenant_id OR c.project_id<>NEW.project_id
             OR c.status<>'frozen' THEN
            RAISE EXCEPTION 'release verdict run requires exact frozen candidate';
          END IF;
          IF NEW.evidence_pack_id IS NOT NULL THEN
            SELECT * INTO p FROM public.evidence_packs WHERE id=NEW.evidence_pack_id;
            IF p.id IS NULL OR p.tenant_id<>NEW.tenant_id OR p.project_id<>NEW.project_id
               OR p.release_candidate_id<>NEW.release_candidate_id
               OR p.core_content_hash IS DISTINCT FROM NEW.core_content_hash THEN
              RAISE EXCEPTION 'release verdict run pack binding mismatch';
            END IF;
            IF NEW.execution_status='succeeded' AND p.assembly_status<>'complete' THEN
              RAISE EXCEPTION 'successful release verdict requires complete evidence core';
            END IF;
          END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER release_verdict_run_guard BEFORE INSERT ON release_verdict_runs "
        "FOR EACH ROW EXECUTE FUNCTION public.release_verdict_run_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.release_verdict_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE r record; p record; c record;
        BEGIN
          SELECT * INTO r FROM public.release_verdict_runs WHERE id=NEW.run_id;
          SELECT * INTO p FROM public.evidence_packs WHERE id=NEW.evidence_pack_id;
          SELECT * INTO c FROM public.release_candidates WHERE id=NEW.release_candidate_id;
          IF r.id IS NULL OR r.execution_status<>'succeeded'
             OR r.tenant_id<>NEW.tenant_id OR r.project_id<>NEW.project_id
             OR r.release_candidate_id<>NEW.release_candidate_id
             OR r.evidence_pack_id<>NEW.evidence_pack_id
             OR r.input_digest<>NEW.input_digest
             OR r.core_content_hash<>NEW.core_content_hash
             OR r.verdict_contract_hash<>NEW.verdict_contract_hash THEN
            RAISE EXCEPTION 'release verdict does not match successful run';
          END IF;
          IF p.id IS NULL OR p.assembly_status<>'complete' OR p.tenant_id<>NEW.tenant_id
             OR p.project_id<>NEW.project_id OR p.release_candidate_id<>NEW.release_candidate_id
             OR p.audit_checkpoint_id<>NEW.audit_checkpoint_id
             OR p.core_content_hash<>NEW.core_content_hash
             OR p.issue_binding_digest<>NEW.issue_binding_digest
             OR p.source_set_digest<>NEW.source_set_digest
             OR p.traceability_digest<>NEW.traceability_digest THEN
            RAISE EXCEPTION 'release verdict evidence-pack binding mismatch';
          END IF;
          IF c.id IS NULL OR c.status<>'frozen' OR c.tenant_id<>NEW.tenant_id
             OR c.project_id<>NEW.project_id THEN
            RAISE EXCEPTION 'release verdict candidate is not frozen';
          END IF;
          RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER release_verdict_guard BEFORE INSERT ON release_verdicts "
        "FOR EACH ROW EXECUTE FUNCTION public.release_verdict_guard()"
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_release_verdict(verdict_uuid uuid) RETURNS boolean
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE v record; child_count bigint; binding_count bigint; input_rows text; binding_rows text;
        DECLARE missing_count bigint; blocker_count bigint; limit_count bigint; authority_count bigint;
        BEGIN
          SELECT * INTO v FROM public.release_verdicts WHERE id=verdict_uuid;
          IF v.id IS NULL THEN RETURN true; END IF;
          SELECT count(*) INTO binding_count FROM public.release_candidate_issue_bindings
            WHERE release_candidate_id=v.release_candidate_id;
          SELECT count(*),
                 count(*) FILTER (WHERE NOT trusted_provenance),
                 count(*) FILTER (WHERE issue_status NOT IN ('resolved','superseded')
                   AND (blocking OR hard_blocker)),
                 count(*) FILTER (WHERE issue_status NOT IN ('resolved','superseded')
                   AND NOT blocking AND NOT hard_blocker),
                 count(*) FILTER (WHERE issue_status NOT IN ('resolved','superseded')
                   AND NOT blocking AND NOT hard_blocker
                   AND (NOT exact_risk_acceptance OR NOT risk_authority_verified))
            INTO child_count,missing_count,blocker_count,limit_count,authority_count
            FROM public.release_verdict_issue_results WHERE verdict_id=verdict_uuid;
          IF child_count<>binding_count OR child_count<>v.issue_count
             OR missing_count<>v.missing_evidence_count
             OR blocker_count<>v.blocking_issue_count
             OR limit_count<>v.limitation_count
             OR authority_count<>v.unverified_authority_count THEN
            RAISE EXCEPTION 'release verdict child counts do not match generated inputs';
          END IF;
          SELECT COALESCE(string_agg(to_json(s.projection_digest)::text, ','
                   ORDER BY b.created_at,b.id), '') INTO binding_rows
          FROM public.release_candidate_issue_bindings b
          JOIN public.evidence_pack_source_refs s
            ON s.evidence_pack_id=v.evidence_pack_id
           AND s.source_kind='release_candidate_issue_binding' AND s.source_id=b.id
          WHERE b.release_candidate_id=v.release_candidate_id;
          IF v.issue_binding_digest <> 'sha256:' || encode(sha256(convert_to(
            '[' || binding_rows || ']', 'UTF8')), 'hex') THEN
            RAISE EXCEPTION 'release verdict binding digest does not match frozen core';
          END IF;
          SELECT COALESCE(string_agg(
            '{"binding_id":' || to_json(binding_id::text)::text ||
            ',"blocking":' || CASE WHEN blocking THEN 'true' ELSE 'false' END ||
            ',"exact_risk_acceptance":' ||
              CASE WHEN exact_risk_acceptance THEN 'true' ELSE 'false' END ||
            ',"hard_blocker":' || CASE WHEN hard_blocker THEN 'true' ELSE 'false' END ||
            ',"issue_id":' || to_json(issue_id::text)::text ||
            ',"risk_authority_verified":' ||
              CASE WHEN risk_authority_verified THEN 'true' ELSE 'false' END ||
            ',"status":' || to_json(issue_status)::text ||
            ',"trusted_provenance":' ||
              CASE WHEN trusted_provenance THEN 'true' ELSE 'false' END || '}',
            ',' ORDER BY binding_id::text,issue_id::text), '') INTO input_rows
          FROM public.release_verdict_issue_results WHERE verdict_id=verdict_uuid;
          IF v.input_digest <> 'sha256:' || encode(sha256(convert_to(
            '{"assembly_complete":' || 'true,' ||
            '"contract_version":"slice50.release_verdict_input.v1",' ||
            '"input_current":' || 'true,"inventory_complete":' || 'true,' ||
            '"issue_binding_exact":' || 'true,"issues":[' || input_rows || ']}',
            'UTF8')), 'hex') THEN
            RAISE EXCEPTION 'release verdict input digest does not match generated child input';
          END IF;
          IF EXISTS (
            SELECT 1 FROM public.release_candidate_issue_bindings b
            FULL JOIN public.release_verdict_issue_results x
              ON x.verdict_id=verdict_uuid AND x.binding_id=b.id
            LEFT JOIN public.release_issues i ON i.id=b.release_issue_id
            LEFT JOIN public.risk_acceptance_records r ON r.id=i.risk_acceptance_record_id
            WHERE (b.release_candidate_id=v.release_candidate_id OR x.verdict_id=verdict_uuid)
              AND (
                b.id IS NULL OR x.id IS NULL OR x.release_candidate_id<>v.release_candidate_id
                OR x.project_id<>v.project_id OR x.tenant_id<>v.tenant_id
                OR b.project_id<>v.project_id OR b.tenant_id<>v.tenant_id
                OR x.issue_id<>b.release_issue_id OR i.id IS NULL
                OR x.issue_category<>i.issue_category OR x.severity<>i.severity
                OR x.blocking_category IS DISTINCT FROM i.blocking_category
                OR x.source_finding_id IS DISTINCT FROM i.source_finding_id
                OR x.issue_status<>i.status OR x.source_provenance<>i.source_provenance
                OR x.trusted_provenance IS DISTINCT FROM
                   (i.source_provenance='db_verified_trusted_release_finding'
                    AND i.source_finding_id IS NOT NULL)
                OR x.blocking IS DISTINCT FROM i.blocking
                OR x.hard_blocker IS DISTINCT FROM
                   (i.severity='critical' OR i.blocking_category IN
                    ('critical_security_blocker','fake_done_finding',
                     'missing_production_rollback','missing_regulated_or_safety_authority'))
                OR x.risk_acceptance_record_id IS DISTINCT FROM i.risk_acceptance_record_id
                OR x.exact_risk_acceptance IS DISTINCT FROM (
                   r.id IS NOT NULL AND r.tenant_id=v.tenant_id AND r.project_id=v.project_id
                   AND r.release_id=(SELECT release_ref FROM public.release_candidates
                     WHERE id=v.release_candidate_id)
                   AND r.subject_type='release_issue' AND r.issue_id=i.id::text
                   AND r.status='active' AND r.expiry_date>=CURRENT_DATE
                   AND r.blocking_category IS NULL)
                OR x.risk_authority_verified
                OR (x.risk_projection_digest IS NOT NULL) IS DISTINCT FROM
                   (x.risk_acceptance_record_id IS NOT NULL)
                OR x.issue_projection_digest IS DISTINCT FROM
                   public.slice50_release_issue_projection_digest(i.id)
                OR (x.risk_acceptance_record_id IS NOT NULL AND
                   x.risk_projection_digest IS DISTINCT FROM
                   public.slice50_risk_projection_digest(x.risk_acceptance_record_id))
                OR NOT EXISTS (
                  SELECT 1 FROM public.evidence_pack_source_refs s
                  WHERE s.evidence_pack_id=v.evidence_pack_id
                    AND s.source_kind='release_issue' AND s.source_id=i.id
                    AND s.projection_digest=x.issue_projection_digest)
                OR NOT EXISTS (
                  SELECT 1 FROM public.evidence_pack_source_refs s
                  WHERE s.evidence_pack_id=v.evidence_pack_id
                    AND s.source_kind='release_candidate_issue_binding'
                    AND s.source_id=b.id)
                OR (x.risk_acceptance_record_id IS NOT NULL AND NOT EXISTS (
                  SELECT 1 FROM public.evidence_pack_source_refs s
                  WHERE s.evidence_pack_id=v.evidence_pack_id
                    AND s.source_kind='risk_acceptance_record'
                    AND s.source_id=x.risk_acceptance_record_id
                    AND s.projection_digest=x.risk_projection_digest))
              )
          ) THEN
            RAISE EXCEPTION 'release verdict issue result does not match frozen/core evidence';
          END IF;
          RETURN true;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_release_verdict_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD); verdict_uuid uuid;
        BEGIN
          verdict_uuid := CASE WHEN TG_TABLE_NAME='release_verdicts'
            THEN COALESCE((n->>'id')::uuid,(o->>'id')::uuid)
            ELSE COALESCE((n->>'verdict_id')::uuid,(o->>'verdict_id')::uuid) END;
          PERFORM public.verify_release_verdict(verdict_uuid);
          RETURN NULL;
        END $fn$
        """
    )
    for table in ("release_verdicts", "release_verdict_issue_results"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_verify AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.verify_release_verdict_trigger()"
        )
    op.execute(
        """
        CREATE FUNCTION public.verify_release_verdict_run(run_uuid uuid) RETURNS boolean
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE r record; verdict_count bigint;
        BEGIN
          SELECT * INTO r FROM public.release_verdict_runs WHERE id=run_uuid;
          IF r.id IS NULL THEN RETURN true; END IF;
          SELECT count(*) INTO verdict_count FROM public.release_verdicts WHERE run_id=run_uuid;
          IF (r.execution_status='succeeded' AND verdict_count<>1)
             OR (r.execution_status IN ('failed','refused') AND verdict_count<>0) THEN
            RAISE EXCEPTION 'release verdict run/attestation cardinality mismatch';
          END IF;
          RETURN true;
        END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.verify_release_verdict_run_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE n jsonb := to_jsonb(NEW); o jsonb := to_jsonb(OLD); run_uuid uuid;
        BEGIN
          run_uuid := CASE WHEN TG_TABLE_NAME='release_verdict_runs'
            THEN COALESCE((n->>'id')::uuid,(o->>'id')::uuid)
            ELSE COALESCE((n->>'run_id')::uuid,(o->>'run_id')::uuid) END;
          PERFORM public.verify_release_verdict_run(run_uuid);
          RETURN NULL;
        END $fn$
        """
    )
    for table in ("release_verdict_runs", "release_verdicts"):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {table}_run_verify AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.verify_release_verdict_run_trigger()"
        )


def upgrade() -> None:
    _create_runs()
    _create_verdicts()
    _create_issue_results()
    _create_guards()
    for table in ("release_verdict_runs", "release_verdicts", "release_verdict_issue_results"):
        _tenant_table(table)


def downgrade() -> None:
    op.execute(
        """
        DO $fn$ BEGIN
          IF EXISTS(SELECT 1 FROM public.release_verdict_runs)
             OR EXISTS(SELECT 1 FROM public.release_verdicts)
             OR EXISTS(SELECT 1 FROM public.release_verdict_issue_results) THEN
            RAISE EXCEPTION 'Slice-50 rows exist; downgrade refuses to erase verdict history';
          END IF;
        END $fn$
        """
    )
    for table in ("release_verdict_runs", "release_verdicts"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_run_verify ON public.{table}")
    for table in ("release_verdicts", "release_verdict_issue_results"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_verify ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS public.verify_release_verdict_run_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_release_verdict_run(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.verify_release_verdict_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_release_verdict(uuid)")
    op.execute("DROP TRIGGER IF EXISTS release_verdict_guard ON public.release_verdicts")
    op.execute("DROP FUNCTION IF EXISTS public.release_verdict_guard()")
    op.execute("DROP TRIGGER IF EXISTS release_verdict_run_guard ON public.release_verdict_runs")
    op.execute("DROP FUNCTION IF EXISTS public.release_verdict_run_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.slice50_risk_projection_digest(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.slice50_release_issue_projection_digest(uuid)")
    for table in ("release_verdict_issue_results", "release_verdicts", "release_verdict_runs"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON public.{table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
        op.drop_table(table)
