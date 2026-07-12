"""shortcut detector execution

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLES = (
    "shortcut_detector_runs",
    "shortcut_detector_category_results",
    "shortcut_detector_reviewer_results",
)
_SECURITY = ("authz", "injection", "secrets_exposure", "unsafe_tool", "supply_chain", "other")
_SHORTCUT = (
    "hardcoded_value",
    "static_response",
    "fake_integration",
    "disabled_validation",
    "weakened_tests",
    "error_swallowing",
    "placeholder_ui",
    "todo_in_required_path",
    "local_only_substitute",
    "acceptance_silently_skipped",
    "tests_check_implementation",
    "readiness_without_evidence",
    "other",
)
_MANDATORY = _SHORTCUT[:-1]
_ORIGINAL_IMMUTABLE = (
    "id",
    "tenant_id",
    "project_id",
    "finding_type",
    "category",
    "severity",
    "summary",
    "detail",
    "source",
    "source_provenance",
    "detected_at",
    "created_at",
)
_SECURITY_IMMUTABLE = ("security_scan_category_result_id", "scan_finding_fingerprint")
_SHORTCUT_IMMUTABLE = (
    "shortcut_detector_category_result_id",
    "shortcut_finding_fingerprint",
)
_CONTRACT_HASH = "sha256:e154290c144b1b1372fbb8cf78e01741d4c9d28d9fd43676fc8abddf31b70deb"


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "shortcut_detector_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("repo_binding_hash", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("detector_contract_hash", sa.Text(), nullable=False),
        sa.Column("corpus_digest", sa.Text(), nullable=True),
        sa.Column("corpus_provenance", sa.Text(), nullable=False),
        sa.Column("deterministic_execution_provenance", sa.Text(), nullable=False),
        sa.Column("review_execution_provenance", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("reported_category_count", sa.Integer(), nullable=False),
        sa.Column("reported_reviewer_count", sa.Integer(), nullable=False),
        sa.Column("reported_reviewer_result_count", sa.Integer(), nullable=False),
        sa.Column("reported_finding_count", sa.Integer(), nullable=False),
        sa.Column("coverage_complete", sa.Boolean(), nullable=False),
        sa.Column("coverage_verdict", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("provider = 'github'", name="ck_sdr_provider"),
        sa.CheckConstraint("schema_version = 'slice45.shortcut_review.v1'", name="ck_sdr_schema"),
        sa.CheckConstraint("repo_binding_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_sdr_repo_hash"),
        sa.CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="ck_sdr_commit"),
        sa.CheckConstraint(f"detector_contract_hash = '{_CONTRACT_HASH}'", name="ck_sdr_contract"),
        sa.CheckConstraint(
            "corpus_digest IS NULL OR corpus_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_sdr_corpus"
        ),
        sa.CheckConstraint(
            "corpus_provenance IN ('caller_supplied_unverified','connector_verified_ci_shortcut_corpus')",
            name="ck_sdr_corpus_provenance",
        ),
        sa.CheckConstraint(
            "deterministic_execution_provenance IN ('none','system_executed_deterministic')",
            name="ck_sdr_deterministic_provenance",
        ),
        sa.CheckConstraint(
            "review_execution_provenance IN ('none','system_executed_llm_review')",
            name="ck_sdr_review_provenance",
        ),
        sa.CheckConstraint(
            "execution_status IN ('succeeded','failed','refused')", name="ck_sdr_status"
        ),
        sa.CheckConstraint("coverage_verdict IN ('covered','failed')", name="ck_sdr_verdict"),
        sa.CheckConstraint(
            "reported_category_count BETWEEN 0 AND 12 AND reported_reviewer_count BETWEEN 0 AND 16 AND reported_reviewer_result_count BETWEEN 0 AND 192 AND reported_finding_count BETWEEN 0 AND 1000",
            name="ck_sdr_counts",
        ),
        sa.CheckConstraint(
            "(execution_status='succeeded' AND failure_code IS NULL AND corpus_digest IS NOT NULL "
            "AND corpus_provenance='connector_verified_ci_shortcut_corpus' "
            "AND deterministic_execution_provenance='system_executed_deterministic' "
            "AND review_execution_provenance='system_executed_llm_review') OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL "
            "AND corpus_digest IS NULL AND corpus_provenance='caller_supplied_unverified' "
            "AND deterministic_execution_provenance='none' AND review_execution_provenance='none' "
            "AND reported_category_count=0 AND reported_reviewer_count=0 "
            "AND reported_reviewer_result_count=0 AND reported_finding_count=0 "
            "AND NOT coverage_complete AND coverage_verdict='failed')",
            name="ck_sdr_execution_shape",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (octet_length(failure_code) BETWEEN 1 AND 128 AND btrim(failure_code)<>'')",
            name="ck_sdr_failure_code",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_sdr_tenant", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shortcut_detector_runs"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_sdr_id_project_tenant"),
    )
    op.create_index(
        "ix_shortcut_detector_runs_latest",
        "shortcut_detector_runs",
        [
            "tenant_id",
            "project_id",
            "repo_binding_hash",
            "detector_contract_hash",
            "created_at",
            "id",
        ],
    )

    op.create_table(
        "shortcut_detector_category_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("shortcut_detector_run_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("deterministic_status", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("coverage_status", sa.Text(), nullable=False),
        sa.Column("deterministic_fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column("reported_reviewer_result_count", sa.Integer(), nullable=False),
        sa.Column("reported_finding_count", sa.Integer(), nullable=False),
        sa.Column("detector_evidence_digest", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(f"category IN ({_sql_list(_MANDATORY)})", name="ck_sdcr_category"),
        sa.CheckConstraint(
            "deterministic_status IN ('completed','failed','refused')",
            name="ck_sdcr_deterministic_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('completed','failed','refused')", name="ck_sdcr_review_status"
        ),
        sa.CheckConstraint(
            "coverage_status IN ('completed_clean','completed_with_findings','failed','refused')",
            name="ck_sdcr_coverage_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(deterministic_fingerprints)='array'", name="ck_sdcr_fingerprints_array"
        ),
        sa.CheckConstraint(
            "reported_reviewer_result_count BETWEEN 0 AND 16 AND reported_finding_count BETWEEN 0 AND 1000",
            name="ck_sdcr_counts",
        ),
        sa.CheckConstraint(
            "detector_evidence_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_sdcr_evidence"
        ),
        sa.CheckConstraint(
            "(coverage_status='completed_clean' AND deterministic_status='completed' "
            "AND review_status='completed' AND reported_finding_count=0) OR "
            "(coverage_status='completed_with_findings' AND deterministic_status='completed' "
            "AND review_status='completed' AND reported_finding_count>0) OR "
            "(coverage_status IN ('failed','refused') AND reported_finding_count=0)",
            name="ck_sdcr_coverage_shape",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_sdcr_tenant", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shortcut_detector_run_id", "project_id", "tenant_id"],
            [
                "shortcut_detector_runs.id",
                "shortcut_detector_runs.project_id",
                "shortcut_detector_runs.tenant_id",
            ],
            name="run_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shortcut_detector_category_results"),
        sa.UniqueConstraint("shortcut_detector_run_id", "category", name="uq_sdcr_run_category"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", "category", name="uq_sdcr_attachment_target"
        ),
    )

    op.create_table(
        "shortcut_detector_reviewer_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("shortcut_detector_category_result_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("reviewer_instance_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_blueprint_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_version_hash", sa.Text(), nullable=False),
        sa.Column("model_route_hash", sa.Text(), nullable=False),
        sa.Column("blind_call", sa.Boolean(), nullable=False),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("finding_fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column("reported_finding_count", sa.Integer(), nullable=False),
        sa.Column("response_digest", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_external_ref", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reviewer_version_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_sdrr_version_hash"
        ),
        sa.CheckConstraint("model_route_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_sdrr_model_hash"),
        sa.CheckConstraint(
            "response_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_sdrr_response_digest"
        ),
        sa.CheckConstraint("blind_call", name="ck_sdrr_blind"),
        sa.CheckConstraint("execution_status='succeeded'", name="ck_sdrr_status"),
        sa.CheckConstraint("decision IN ('clean','findings')", name="ck_sdrr_decision"),
        sa.CheckConstraint(
            "jsonb_typeof(finding_fingerprints)='array'", name="ck_sdrr_fingerprints_array"
        ),
        sa.CheckConstraint(
            "reported_finding_count BETWEEN 0 AND 1000 AND input_tokens>0 AND output_tokens>0",
            name="ck_sdrr_counts",
        ),
        sa.CheckConstraint(
            "octet_length(cost_external_ref) BETWEEN 1 AND 500 AND btrim(cost_external_ref)<>''",
            name="ck_sdrr_cost_ref",
        ),
        sa.CheckConstraint(
            "(decision='clean' AND reported_finding_count=0) OR (decision='findings' AND reported_finding_count>0)",
            name="ck_sdrr_decision_shape",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_sdrr_tenant", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            name="project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_blueprint_id"],
            ["agent_blueprints.id"],
            name="reviewer_blueprint",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shortcut_detector_category_result_id", "project_id", "tenant_id", "category"],
            [
                "shortcut_detector_category_results.id",
                "shortcut_detector_category_results.project_id",
                "shortcut_detector_category_results.tenant_id",
                "shortcut_detector_category_results.category",
            ],
            name="category_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            name="reviewer_project_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shortcut_detector_reviewer_results"),
        sa.UniqueConstraint(
            "shortcut_detector_category_result_id",
            "reviewer_instance_id",
            name="uq_sdrr_category_reviewer",
        ),
    )

    op.add_column(
        "release_findings",
        sa.Column("shortcut_detector_category_result_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "release_findings", sa.Column("shortcut_finding_fingerprint", sa.Text(), nullable=True)
    )
    op.create_foreign_key(
        "shortcut_detector_category_project_tenant",
        "release_findings",
        "shortcut_detector_category_results",
        ["shortcut_detector_category_result_id", "project_id", "tenant_id", "category"],
        ["id", "project_id", "tenant_id", "category"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_release_findings_shortcut_fingerprint",
        "release_findings",
        ["tenant_id", "shortcut_detector_category_result_id", "shortcut_finding_fingerprint"],
        unique=True,
        postgresql_where=sa.text("shortcut_detector_category_result_id IS NOT NULL"),
    )
    _create_shortcut_guards()
    _replace_release_findings_guard(slice45=True)
    _apply_rls_and_append_only()


def _create_shortcut_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.shortcut_model_route_hash(route text) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $fn$
        SELECT 'sha256:' || encode(sha256(convert_to(route, 'UTF8')), 'hex') $fn$
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION public.verify_shortcut_detector_run(target_run uuid) RETURNS void
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE
            r public.shortcut_detector_runs;
            actual_categories int; actual_review_results int; actual_reviewers int;
            actual_findings int; invalid_categories int; invalid_reviewers int;
            child_mismatch int; builder_count int; overlap_count int;
        BEGIN
            SELECT * INTO r FROM public.shortcut_detector_runs WHERE id=target_run;
            IF NOT FOUND THEN RETURN; END IF;
            SELECT count(*) INTO actual_categories FROM public.shortcut_detector_category_results
            WHERE shortcut_detector_run_id=target_run;
            SELECT count(*), count(DISTINCT rr.reviewer_instance_id)
            INTO actual_review_results, actual_reviewers
            FROM public.shortcut_detector_reviewer_results rr
            JOIN public.shortcut_detector_category_results c
              ON c.id=rr.shortcut_detector_category_result_id
            WHERE c.shortcut_detector_run_id=target_run;
            SELECT count(*) INTO actual_findings
            FROM public.release_findings f
            JOIN public.shortcut_detector_category_results c
              ON c.id=f.shortcut_detector_category_result_id
            WHERE c.shortcut_detector_run_id=target_run
              AND f.finding_type='shortcut'
              AND f.source_provenance='system_executed_shortcut_review';
            IF r.execution_status <> 'succeeded' THEN
                IF actual_categories<>0 OR actual_review_results<>0 OR actual_findings<>0 THEN
                    RAISE EXCEPTION 'shortcut_detector_runs: failed/refused run has children';
                END IF;
                RETURN;
            END IF;
            SELECT count(*) INTO invalid_categories
            FROM public.shortcut_detector_category_results c
            WHERE c.shortcut_detector_run_id=target_run AND (
                c.category NOT IN ({_sql_list(_MANDATORY)})
                OR c.deterministic_status<>'completed' OR c.review_status<>'completed'
                OR c.coverage_status NOT IN ('completed_clean','completed_with_findings')
                OR c.reported_reviewer_result_count<>2
                OR jsonb_array_length(c.deterministic_fingerprints)<>(
                    SELECT count(DISTINCT value) FROM jsonb_array_elements_text(c.deterministic_fingerprints)
                )
                OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(c.deterministic_fingerprints) value
                    WHERE value !~ '^sha256:[0-9a-f]{{64}}$'
                )
            );
            SELECT count(*) INTO invalid_reviewers
            FROM public.shortcut_detector_reviewer_results rr
            JOIN public.shortcut_detector_category_results c
              ON c.id=rr.shortcut_detector_category_result_id
            JOIN public.agent_instances i ON i.id=rr.reviewer_instance_id
            JOIN public.agent_versions v ON v.id=i.version_id
            JOIN public.agent_blueprints b ON b.id=v.blueprint_id
            JOIN public.agent_realizations ar ON ar.instance_id=i.id
            WHERE c.shortcut_detector_run_id=target_run AND (
                i.status<>'active' OR b.status<>'active' OR b.archetype<>'reviewer'
                OR ar.qualification_status<>'qualified'
                OR rr.reviewer_blueprint_id<>b.id
                OR rr.reviewer_version_hash<>v.content_hash
                OR rr.model_route_hash<>public.shortcut_model_route_hash(v.model_route)
                OR NOT rr.blind_call OR rr.execution_status<>'succeeded'
                OR jsonb_array_length(rr.finding_fingerprints)<>rr.reported_finding_count
                OR jsonb_array_length(rr.finding_fingerprints)<>
                   (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(rr.finding_fingerprints))
                OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements_text(rr.finding_fingerprints) value
                    WHERE value !~ '^sha256:[0-9a-f]{{64}}$'
                )
            );
            SELECT count(*) INTO child_mismatch
            FROM public.shortcut_detector_category_results c
            WHERE c.shortcut_detector_run_id=target_run AND (
                (SELECT count(*) FROM public.shortcut_detector_reviewer_results rr
                 WHERE rr.shortcut_detector_category_result_id=c.id)<>2
                OR c.reported_finding_count<>(
                    SELECT count(*) FROM public.release_findings f
                    WHERE f.shortcut_detector_category_result_id=c.id
                      AND f.finding_type='shortcut'
                      AND f.source_provenance='system_executed_shortcut_review'
                )
                OR c.reported_finding_count<>(
                    SELECT count(DISTINCT fp) FROM (
                        SELECT jsonb_array_elements_text(c.deterministic_fingerprints) AS fp
                        UNION
                        SELECT jsonb_array_elements_text(rr.finding_fingerprints) AS fp
                        FROM public.shortcut_detector_reviewer_results rr
                        WHERE rr.shortcut_detector_category_result_id=c.id
                    ) unioned
                )
                OR EXISTS (
                    SELECT 1 FROM (
                        SELECT jsonb_array_elements_text(c.deterministic_fingerprints) AS fp
                        UNION
                        SELECT jsonb_array_elements_text(rr.finding_fingerprints) AS fp
                        FROM public.shortcut_detector_reviewer_results rr
                        WHERE rr.shortcut_detector_category_result_id=c.id
                    ) expected
                    WHERE NOT EXISTS (
                        SELECT 1 FROM public.release_findings f
                        WHERE f.shortcut_detector_category_result_id=c.id
                          AND f.shortcut_finding_fingerprint=expected.fp
                          AND f.finding_type='shortcut'
                          AND f.source_provenance='system_executed_shortcut_review'
                    )
                )
            );
            SELECT count(DISTINCT b.id) INTO builder_count
            FROM public.agent_instances i
            JOIN public.agent_versions v ON v.id=i.version_id
            JOIN public.agent_blueprints b ON b.id=v.blueprint_id
            WHERE i.tenant_id=r.tenant_id AND i.project_id=r.project_id
              AND i.status='active' AND b.status='active' AND b.archetype='builder';
            SELECT count(*) INTO overlap_count
            FROM (
                SELECT DISTINCT rr.reviewer_blueprint_id
                FROM public.shortcut_detector_reviewer_results rr
                JOIN public.shortcut_detector_category_results c
                  ON c.id=rr.shortcut_detector_category_result_id
                WHERE c.shortcut_detector_run_id=target_run
            ) reviewers
            JOIN public.agent_versions v ON v.blueprint_id=reviewers.reviewer_blueprint_id
            JOIN public.agent_instances i ON i.version_id=v.id
            JOIN public.agent_blueprints b ON b.id=v.blueprint_id
            WHERE i.tenant_id=r.tenant_id AND i.project_id=r.project_id
              AND i.status='active' AND b.archetype='builder';
            IF actual_reviewers<>2 OR (
                SELECT count(DISTINCT rr.reviewer_blueprint_id)
                FROM public.shortcut_detector_reviewer_results rr
                JOIN public.shortcut_detector_category_results c
                  ON c.id=rr.shortcut_detector_category_result_id
                WHERE c.shortcut_detector_run_id=target_run
            )<>2 OR (
                SELECT count(DISTINCT rr.reviewer_version_hash)
                FROM public.shortcut_detector_reviewer_results rr
                JOIN public.shortcut_detector_category_results c
                  ON c.id=rr.shortcut_detector_category_result_id
                WHERE c.shortcut_detector_run_id=target_run
            )<>2 OR (
                SELECT count(DISTINCT rr.model_route_hash)
                FROM public.shortcut_detector_reviewer_results rr
                JOIN public.shortcut_detector_category_results c
                  ON c.id=rr.shortcut_detector_category_result_id
                WHERE c.shortcut_detector_run_id=target_run
            )<>2 THEN
                invalid_reviewers := invalid_reviewers + 1;
            END IF;
            IF actual_categories<>12 OR actual_review_results<>24 OR actual_reviewers<>2
               OR actual_categories<>r.reported_category_count
               OR actual_reviewers<>r.reported_reviewer_count
               OR actual_review_results<>r.reported_reviewer_result_count
               OR actual_findings<>r.reported_finding_count
               OR invalid_categories<>0 OR invalid_reviewers<>0 OR child_mismatch<>0
               OR builder_count=0 OR overlap_count<>0
               OR NOT r.coverage_complete OR r.coverage_verdict<>'covered' THEN
                RAISE EXCEPTION 'shortcut_detector_runs: aggregate mismatch';
            END IF;
        END; $fn$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.shortcut_run_verify_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN PERFORM public.verify_shortcut_detector_run(NEW.id); RETURN NULL; END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.shortcut_child_verify_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE target uuid;
        BEGIN
            IF TG_TABLE_NAME='shortcut_detector_category_results' THEN
                target:=NEW.shortcut_detector_run_id;
            ELSIF TG_TABLE_NAME='shortcut_detector_reviewer_results' THEN
                SELECT shortcut_detector_run_id INTO target
                FROM public.shortcut_detector_category_results
                WHERE id=NEW.shortcut_detector_category_result_id;
            ELSE
                SELECT shortcut_detector_run_id INTO target
                FROM public.shortcut_detector_category_results
                WHERE id=NEW.shortcut_detector_category_result_id;
            END IF;
            IF target IS NOT NULL THEN PERFORM public.verify_shortcut_detector_run(target); END IF;
            RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER shortcut_runs_verify AFTER INSERT ON shortcut_detector_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.shortcut_run_verify_trigger()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER shortcut_categories_verify AFTER INSERT ON shortcut_detector_category_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.shortcut_child_verify_trigger()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER shortcut_reviewers_verify AFTER INSERT ON shortcut_detector_reviewer_results DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.shortcut_child_verify_trigger()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER shortcut_findings_verify AFTER INSERT ON release_findings DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.shortcut_detector_category_result_id IS NOT NULL) EXECUTE FUNCTION public.shortcut_child_verify_trigger()"
    )


def _replace_release_findings_guard(*, slice45: bool) -> None:
    immutable = _ORIGINAL_IMMUTABLE + _SECURITY_IMMUTABLE + (_SHORTCUT_IMMUTABLE if slice45 else ())
    immutable_checks = "\n            OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in immutable
    )
    shortcut_null_check = (
        "OR NEW.shortcut_detector_category_result_id IS NOT NULL "
        "OR NEW.shortcut_finding_fingerprint IS NOT NULL"
        if slice45
        else ""
    )
    security_shortcut_check = (
        "OR NEW.shortcut_detector_category_result_id IS NOT NULL "
        "OR NEW.shortcut_finding_fingerprint IS NOT NULL"
        if slice45
        else ""
    )
    shortcut_branch = (
        """
                ELSIF NEW.source_provenance = 'system_executed_shortcut_review' THEN
                    IF NEW.shortcut_detector_category_result_id IS NULL
                       OR NEW.shortcut_finding_fingerprint IS NULL
                       OR NEW.security_scan_category_result_id IS NOT NULL
                       OR NEW.scan_finding_fingerprint IS NOT NULL THEN
                        RAISE EXCEPTION 'release_findings: trusted shortcut finding requires detector attachment';
                    END IF;
                    IF NEW.finding_type <> 'shortcut'
                       OR NEW.shortcut_finding_fingerprint !~ '^sha256:[0-9a-f]{64}$'
                       OR NEW.source NOT IN ('slice45.detector.v1','slice45.llm_reviewer')
                       OR octet_length(NEW.summary) NOT BETWEEN 1 AND 500 OR btrim(NEW.summary)=''
                       OR NEW.detail IS NULL OR octet_length(NEW.detail) NOT BETWEEN 1 AND 4000
                       OR btrim(NEW.detail)='' THEN
                        RAISE EXCEPTION 'release_findings: invalid trusted shortcut finding shape';
                    END IF;
                    SELECT count(*) INTO ok
                    FROM public.shortcut_detector_category_results c
                    JOIN public.shortcut_detector_runs r ON r.id=c.shortcut_detector_run_id
                    WHERE c.id=NEW.shortcut_detector_category_result_id
                      AND c.project_id=NEW.project_id AND c.tenant_id=NEW.tenant_id
                      AND c.category=NEW.category
                      AND c.coverage_status='completed_with_findings'
                      AND r.execution_status='succeeded'
                      AND r.corpus_provenance='connector_verified_ci_shortcut_corpus'
                      AND r.deterministic_execution_provenance='system_executed_deterministic'
                      AND r.review_execution_provenance='system_executed_llm_review';
                    IF ok<>1 THEN
                        RAISE EXCEPTION 'release_findings: shortcut attachment is not trusted category evidence';
                    END IF;
                    SELECT count(*) INTO ok
                    FROM public.release_findings f
                    JOIN public.shortcut_detector_category_results prior
                      ON prior.id=f.shortcut_detector_category_result_id
                    JOIN public.shortcut_detector_category_results incoming
                      ON incoming.id=NEW.shortcut_detector_category_result_id
                    WHERE prior.shortcut_detector_run_id=incoming.shortcut_detector_run_id
                      AND f.shortcut_finding_fingerprint=NEW.shortcut_finding_fingerprint;
                    IF ok<>0 THEN
                        RAISE EXCEPTION 'release_findings: duplicate shortcut fingerprint within run';
                    END IF;
        """
        if slice45
        else ""
    )
    op.execute("DROP TRIGGER IF EXISTS release_findings_guard ON public.release_findings")
    op.execute("DROP FUNCTION IF EXISTS public.release_findings_guard()")
    op.execute(
        f"""
        CREATE FUNCTION public.release_findings_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE ok int;
        BEGIN
            IF TG_OP='INSERT' THEN
                IF NEW.status<>'open' THEN
                    RAISE EXCEPTION 'release_findings must be created with status=open';
                END IF;
                IF NEW.source_provenance='caller_supplied_unverified' THEN
                    IF NEW.security_scan_category_result_id IS NOT NULL
                       OR NEW.scan_finding_fingerprint IS NOT NULL {shortcut_null_check} THEN
                        RAISE EXCEPTION 'release_findings: unverified finding cannot carry verified attachment';
                    END IF;
                ELSIF NEW.source_provenance='connector_verified_security_scan' THEN
                    IF NEW.security_scan_category_result_id IS NULL
                       OR NEW.scan_finding_fingerprint IS NULL {security_shortcut_check} THEN
                        RAISE EXCEPTION 'release_findings: verified security finding requires scan attachment';
                    END IF;
                    IF NEW.finding_type<>'security'
                       OR NEW.scan_finding_fingerprint !~ '^sha256:[0-9a-f]{{64}}$'
                       OR octet_length(NEW.source) NOT BETWEEN 1 AND 128 OR btrim(NEW.source)=''
                       OR octet_length(NEW.summary) NOT BETWEEN 1 AND 500 OR btrim(NEW.summary)=''
                       OR NEW.detail IS NULL OR octet_length(NEW.detail) NOT BETWEEN 1 AND 4000
                       OR btrim(NEW.detail)='' THEN
                        RAISE EXCEPTION 'release_findings: invalid verified security finding shape';
                    END IF;
                    SELECT count(*) INTO ok
                    FROM public.security_scan_category_results c
                    JOIN public.security_scan_runs r ON r.id=c.security_scan_run_id
                    WHERE c.id=NEW.security_scan_category_result_id
                      AND c.project_id=NEW.project_id AND c.tenant_id=NEW.tenant_id
                      AND c.category=NEW.category AND c.scanner_key=NEW.source
                      AND c.coverage_status='completed_with_findings'
                      AND r.execution_status='succeeded'
                      AND r.artifact_provenance='connector_verified_ci_security'
                      AND r.execution_observation='connector_observed_ci';
                    IF ok<>1 THEN
                        RAISE EXCEPTION 'release_findings: scan attachment is not trusted category evidence';
                    END IF;
                    SELECT count(*) INTO ok
                    FROM public.release_findings f
                    JOIN public.security_scan_category_results prior
                      ON prior.id=f.security_scan_category_result_id
                    JOIN public.security_scan_category_results incoming
                      ON incoming.id=NEW.security_scan_category_result_id
                    WHERE prior.security_scan_run_id=incoming.security_scan_run_id
                      AND f.scan_finding_fingerprint=NEW.scan_finding_fingerprint;
                    IF ok<>0 THEN
                        RAISE EXCEPTION 'release_findings: duplicate fingerprint within scan run';
                    END IF;
                {shortcut_branch}
                ELSE
                    RAISE EXCEPTION 'release_findings source_provenance is unsupported';
                END IF;
                IF NEW.risk_acceptance_record_id IS NOT NULL OR NEW.resolution_note IS NOT NULL
                   OR NEW.resolved_at IS NOT NULL OR NEW.resolved_by IS NOT NULL THEN
                    RAISE EXCEPTION 'release_findings: resolution/acceptance metadata must be NULL at creation';
                END IF;
                IF (NEW.finding_type='security' AND NEW.category NOT IN ({_sql_list(_SECURITY)}))
                   OR (NEW.finding_type='shortcut' AND NEW.category NOT IN ({_sql_list(_SHORTCUT)})) THEN
                    RAISE EXCEPTION 'release_findings: category % invalid for finding_type %', NEW.category, NEW.finding_type;
                END IF;
                IF NEW.category='other' AND (NEW.summary IS NULL OR btrim(NEW.summary)=''
                   OR NEW.detail IS NULL OR btrim(NEW.detail)='') THEN
                    RAISE EXCEPTION 'release_findings: category=other requires non-empty summary and detail';
                END IF;
            ELSIF TG_OP='UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'release_findings: identity/content/source fields are immutable';
                END IF;
                IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
                    IF NEW.risk_acceptance_record_id IS DISTINCT FROM OLD.risk_acceptance_record_id
                       OR NEW.resolution_note IS DISTINCT FROM OLD.resolution_note
                       OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
                       OR NEW.resolved_by IS DISTINCT FROM OLD.resolved_by
                       OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
                        RAISE EXCEPTION 'release_findings: fields change only via a status transition';
                    END IF;
                ELSE
                    IF OLD.status<>'open' THEN
                        RAISE EXCEPTION 'release_findings: terminal status % cannot transition', OLD.status;
                    END IF;
                    IF NEW.status NOT IN ('resolved','false_positive','accepted','superseded') THEN
                        RAISE EXCEPTION 'release_findings: invalid target status %', NEW.status;
                    END IF;
                    IF NEW.status='accepted' THEN
                        IF OLD.severity='critical' THEN
                            RAISE EXCEPTION 'release_findings: critical findings cannot be accepted';
                        END IF;
                        IF NEW.risk_acceptance_record_id IS NULL THEN
                            RAISE EXCEPTION 'release_findings: accepted requires a risk_acceptance_record_id';
                        END IF;
                        IF NEW.resolution_note IS NOT NULL OR NEW.resolved_at IS NOT NULL
                           OR NEW.resolved_by IS NOT NULL THEN
                            RAISE EXCEPTION 'release_findings: accepted must not set resolution metadata';
                        END IF;
                        SELECT 1 INTO ok FROM public.risk_acceptance_records r
                        WHERE r.id=NEW.risk_acceptance_record_id AND r.tenant_id=NEW.tenant_id
                          AND r.project_id=NEW.project_id AND r.status='active'
                          AND r.expiry_date>=CURRENT_DATE AND r.blocking_category IS NULL
                          AND r.issue_id=NEW.id::text;
                        IF ok IS NULL THEN
                            RAISE EXCEPTION 'release_findings: no usable risk-acceptance record for this finding';
                        END IF;
                    ELSE
                        IF NEW.risk_acceptance_record_id IS NOT NULL THEN
                            RAISE EXCEPTION 'release_findings: only accepted may set risk_acceptance_record_id';
                        END IF;
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END $fn$
        """
    )
    op.execute(
        "CREATE TRIGGER release_findings_guard BEFORE INSERT OR UPDATE ON release_findings FOR EACH ROW EXECUTE FUNCTION public.release_findings_guard()"
    )


def _apply_rls_and_append_only() -> None:
    for table in _TABLES:
        op.execute(
            f"""CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
            LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
            BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$"""
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS shortcut_findings_verify ON release_findings")
    _replace_release_findings_guard(slice45=False)
    op.drop_index("uq_release_findings_shortcut_fingerprint", table_name="release_findings")
    op.drop_constraint(
        "shortcut_detector_category_project_tenant", "release_findings", type_="foreignkey"
    )
    op.drop_column("release_findings", "shortcut_finding_fingerprint")
    op.drop_column("release_findings", "shortcut_detector_category_result_id")
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute(
        "DROP TRIGGER IF EXISTS shortcut_reviewers_verify ON shortcut_detector_reviewer_results"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS shortcut_categories_verify ON shortcut_detector_category_results"
    )
    op.execute("DROP TRIGGER IF EXISTS shortcut_runs_verify ON shortcut_detector_runs")
    op.execute("DROP FUNCTION IF EXISTS public.shortcut_child_verify_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.shortcut_run_verify_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_shortcut_detector_run(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.shortcut_model_route_hash(text)")
    op.drop_table("shortcut_detector_reviewer_results")
    op.drop_table("shortcut_detector_category_results")
    op.drop_index("ix_shortcut_detector_runs_latest", table_name="shortcut_detector_runs")
    op.drop_table("shortcut_detector_runs")
