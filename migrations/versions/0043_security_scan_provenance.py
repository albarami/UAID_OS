"""security scan provenance

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
_TABLES = ("security_scan_runs", "security_scan_category_results")
_SECURITY = ("authz", "injection", "secrets_exposure", "unsafe_tool", "supply_chain", "other")
_SHORTCUT = (
    "hardcoded_value", "static_response", "fake_integration", "disabled_validation",
    "weakened_tests", "error_swallowing", "placeholder_ui", "todo_in_required_path",
    "local_only_substitute", "acceptance_silently_skipped", "tests_check_implementation",
    "readiness_without_evidence", "other",
)
_ORIGINAL_IMMUTABLE = (
    "id", "tenant_id", "project_id", "finding_type", "category", "severity", "summary",
    "detail", "source", "source_provenance", "detected_at", "created_at",
)


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "security_scan_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("repo_binding_hash", sa.Text(), nullable=False),
        sa.Column("commit_sha", sa.Text(), nullable=False),
        sa.Column("artifact_schema_version", sa.Text(), nullable=False),
        sa.Column("scanner_manifest_hash", sa.Text(), nullable=False),
        sa.Column("artifact_digest", sa.Text(), nullable=True),
        sa.Column("execution_status", sa.Text(), nullable=False),
        sa.Column("artifact_provenance", sa.Text(), nullable=False),
        sa.Column("execution_observation", sa.Text(), nullable=False),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("reported_category_count", sa.Integer(), nullable=False),
        sa.Column("reported_finding_count", sa.Integer(), nullable=False),
        sa.Column("coverage_complete", sa.Boolean(), nullable=False),
        sa.Column("coverage_verdict", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.CheckConstraint("provider = 'github'", name="ck_ssr_provider"),
        sa.CheckConstraint(
            "artifact_schema_version = 'slice44.security_scan.v1'", name="ck_ssr_schema"
        ),
        sa.CheckConstraint(
            "execution_status IN ('succeeded','failed','refused')", name="ck_ssr_status"
        ),
        sa.CheckConstraint(
            "artifact_provenance IN "
            "('caller_supplied_unverified','connector_verified_ci_security')",
            name="ck_ssr_provenance",
        ),
        sa.CheckConstraint(
            "execution_observation IN ('connector_observed_ci','connector_attempted')",
            name="ck_ssr_observation",
        ),
        sa.CheckConstraint(
            "repo_binding_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_ssr_repo_hash"
        ),
        sa.CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="ck_ssr_commit"),
        sa.CheckConstraint(
            "scanner_manifest_hash = "
            "'sha256:76fc89f3fb671c61c08b5ddeccda651fc2afce35d5f5d7970e20b027070638fb'",
            name="ck_ssr_manifest_hash",
        ),
        sa.CheckConstraint(
            "artifact_digest IS NULL OR artifact_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_ssr_artifact_digest",
        ),
        sa.CheckConstraint(
            "reported_category_count BETWEEN 0 AND 5 "
            "AND reported_finding_count BETWEEN 0 AND 1000", name="ck_ssr_counts"
        ),
        sa.CheckConstraint("coverage_verdict IN ('covered','failed')", name="ck_ssr_verdict"),
        sa.CheckConstraint(
            "(execution_status = 'succeeded' AND failure_code IS NULL "
            "AND artifact_digest IS NOT NULL "
            "AND artifact_provenance = 'connector_verified_ci_security' "
            "AND execution_observation = 'connector_observed_ci') OR "
            "(execution_status IN ('failed','refused') AND failure_code IS NOT NULL "
            "AND artifact_digest IS NULL AND reported_category_count = 0 "
            "AND reported_finding_count = 0 AND NOT coverage_complete "
            "AND coverage_verdict = 'failed' "
            "AND execution_observation = 'connector_attempted')",
            name="ck_ssr_execution_shape",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (octet_length(failure_code) BETWEEN 1 AND 128 "
            "AND btrim(failure_code) <> '')", name="ck_ssr_failure_code"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_ssr_tenant", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_security_scan_runs"),
        sa.UniqueConstraint("id", "project_id", "tenant_id", name="uq_ssr_id_project_tenant"),
    )
    op.create_index(
        "ix_security_scan_runs_latest", "security_scan_runs",
        ["tenant_id", "project_id", "repo_binding_hash", "scanner_manifest_hash", "created_at", "id"],
    )

    op.create_table(
        "security_scan_category_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("security_scan_run_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("scanner_key", sa.Text(), nullable=False),
        sa.Column("scanner_version", sa.Text(), nullable=False),
        sa.Column("rule_pack_hash", sa.Text(), nullable=False),
        sa.Column("coverage_status", sa.Text(), nullable=False),
        sa.Column("reported_finding_count", sa.Integer(), nullable=False),
        sa.Column("evidence_digest", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('authz','injection','secrets_exposure','unsafe_tool','supply_chain')",
            name="ck_sscr_category",
        ),
        sa.CheckConstraint(
            "coverage_status IN "
            "('completed_clean','completed_with_findings','failed','unsupported')",
            name="ck_sscr_status",
        ),
        sa.CheckConstraint(
            "rule_pack_hash ~ '^sha256:[0-9a-f]{64}$'", name="ck_sscr_rule_hash"
        ),
        sa.CheckConstraint(
            "evidence_digest ~ '^sha256:[0-9a-f]{64}$'", name="ck_sscr_evidence_digest"
        ),
        sa.CheckConstraint(
            "octet_length(scanner_key) BETWEEN 1 AND 128 AND btrim(scanner_key) <> '' "
            "AND octet_length(scanner_version) BETWEEN 1 AND 128 "
            "AND btrim(scanner_version) <> ''", name="ck_sscr_scanner_bounds"
        ),
        sa.CheckConstraint(
            "reported_finding_count BETWEEN 0 AND 1000 AND "
            "((coverage_status = 'completed_clean' AND reported_finding_count = 0) OR "
            "(coverage_status = 'completed_with_findings' AND reported_finding_count > 0) OR "
            "(coverage_status IN ('failed','unsupported') AND reported_finding_count = 0))",
            name="ck_sscr_finding_shape",
        ),
        sa.CheckConstraint(
            "(category='authz' AND scanner_key='uaid.authz_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:7a7b60f9e5195353abef1603b2480a163fbd98c03293b95f71e49d4852bb1706') OR "
            "(category='injection' AND scanner_key='uaid.injection_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:9314613dc0b93d99fbe5bb70ea3155c7f5d07215b709983b88d9abeb64902b12') OR "
            "(category='secrets_exposure' AND scanner_key='uaid.secrets_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:688d0e8a5e7e58bda15f39195d09dba7282f24db356f73216adcbe43c465d470') OR "
            "(category='unsafe_tool' AND scanner_key='uaid.unsafe_tool_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:5750f7fdadcb7a4df52d391aa4d3d7441f48b54405fb97940a79fd9a7ff209aa') OR "
            "(category='supply_chain' AND scanner_key='uaid.supply_chain_scan' AND scanner_version='1' "
            "AND rule_pack_hash='sha256:7e5b8969bdd62d07a10c3fa79329ca4bda4dceb57162a297ae234f8406b6c10f')",
            name="ck_sscr_scanner_contract",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"],
            name="project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_scan_run_id", "project_id", "tenant_id"],
            ["security_scan_runs.id", "security_scan_runs.project_id", "security_scan_runs.tenant_id"],
            name="run_project_tenant", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_sscr_tenant", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_security_scan_category_results"),
        sa.UniqueConstraint("security_scan_run_id", "category", name="uq_sscr_run_category"),
        sa.UniqueConstraint(
            "id", "project_id", "tenant_id", "category", name="uq_sscr_attachment_target"
        ),
    )

    op.add_column(
        "release_findings", sa.Column("security_scan_category_result_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "release_findings", sa.Column("scan_finding_fingerprint", sa.Text(), nullable=True)
    )
    op.create_foreign_key(
        "security_scan_category_project_tenant", "release_findings",
        "security_scan_category_results",
        ["security_scan_category_result_id", "project_id", "tenant_id", "category"],
        ["id", "project_id", "tenant_id", "category"], ondelete="RESTRICT",
    )
    op.create_index(
        "uq_release_findings_scan_fingerprint", "release_findings",
        ["tenant_id", "security_scan_category_result_id", "scan_finding_fingerprint"],
        unique=True,
        postgresql_where=sa.text("security_scan_category_result_id IS NOT NULL"),
    )

    _create_scan_guards()
    _replace_release_findings_guard(slice44=True)
    _apply_rls_and_append_only()


def _create_scan_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.verify_security_scan_run(target_run uuid) RETURNS void
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE
            r public.security_scan_runs;
            actual_categories int; actual_findings int; completed_categories int;
            invalid_categories int; child_mismatch int; expected_complete boolean;
            expected_verdict text;
        BEGIN
            SELECT * INTO r FROM public.security_scan_runs WHERE id = target_run;
            IF NOT FOUND THEN RETURN; END IF;
            SELECT count(*),
                   count(*) FILTER (WHERE coverage_status IN
                       ('completed_clean','completed_with_findings'))
            INTO actual_categories, completed_categories
            FROM public.security_scan_category_results
            WHERE security_scan_run_id = target_run;
            SELECT count(*) INTO actual_findings
            FROM public.release_findings f
            JOIN public.security_scan_category_results c
              ON c.id = f.security_scan_category_result_id
            WHERE c.security_scan_run_id = target_run
              AND f.finding_type = 'security'
              AND f.source_provenance = 'connector_verified_security_scan';
            SELECT count(*) INTO child_mismatch
            FROM public.security_scan_category_results c
            WHERE c.security_scan_run_id = target_run
              AND c.reported_finding_count <> (
                  SELECT count(*) FROM public.release_findings f
                  WHERE f.security_scan_category_result_id = c.id
                    AND f.finding_type = 'security'
                    AND f.source_provenance = 'connector_verified_security_scan'
              );
            SELECT count(*) INTO invalid_categories
            FROM public.security_scan_category_results c
            WHERE c.security_scan_run_id = target_run AND NOT (
                (c.category='authz' AND c.scanner_key='uaid.authz_scan') OR
                (c.category='injection' AND c.scanner_key='uaid.injection_scan') OR
                (c.category='secrets_exposure' AND c.scanner_key='uaid.secrets_scan') OR
                (c.category='unsafe_tool' AND c.scanner_key='uaid.unsafe_tool_scan') OR
                (c.category='supply_chain' AND c.scanner_key='uaid.supply_chain_scan')
            );
            IF r.execution_status <> 'succeeded' THEN
                IF actual_categories <> 0 OR actual_findings <> 0 THEN
                    RAISE EXCEPTION 'security_scan_runs: failed/refused run has children';
                END IF;
                RETURN;
            END IF;
            expected_complete := actual_categories = 5 AND completed_categories = 5;
            expected_verdict := CASE WHEN expected_complete THEN 'covered' ELSE 'failed' END;
            IF actual_categories <> 5
               OR actual_categories <> r.reported_category_count
               OR actual_findings <> r.reported_finding_count
               OR child_mismatch <> 0 OR invalid_categories <> 0
               OR r.coverage_complete IS DISTINCT FROM expected_complete
               OR r.coverage_verdict IS DISTINCT FROM expected_verdict THEN
                RAISE EXCEPTION 'security_scan_runs: aggregate mismatch';
            END IF;
        END; $fn$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.security_scan_run_verify_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN PERFORM public.verify_security_scan_run(NEW.id); RETURN NULL; END $fn$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.security_scan_child_verify_trigger() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        DECLARE target uuid;
        BEGIN
            IF TG_TABLE_NAME = 'security_scan_category_results' THEN
                target := NEW.security_scan_run_id;
            ELSE
                SELECT security_scan_run_id INTO target
                FROM public.security_scan_category_results
                WHERE id = NEW.security_scan_category_result_id;
            END IF;
            IF target IS NOT NULL THEN PERFORM public.verify_security_scan_run(target); END IF;
            RETURN NULL;
        END $fn$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER security_scan_runs_verify AFTER INSERT ON security_scan_runs "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION public.security_scan_run_verify_trigger()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER security_scan_categories_verify "
        "AFTER INSERT ON security_scan_category_results DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION public.security_scan_child_verify_trigger()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER security_scan_findings_verify AFTER INSERT ON release_findings "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "WHEN (NEW.security_scan_category_result_id IS NOT NULL) "
        "EXECUTE FUNCTION public.security_scan_child_verify_trigger()"
    )


def _replace_release_findings_guard(*, slice44: bool) -> None:
    immutable = _ORIGINAL_IMMUTABLE + (
        ("security_scan_category_result_id", "scan_finding_fingerprint") if slice44 else ()
    )
    immutable_checks = "\n            OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in immutable
    )
    insert_provenance = (
        """
                IF NEW.source_provenance = 'caller_supplied_unverified' THEN
                    IF NEW.security_scan_category_result_id IS NOT NULL
                       OR NEW.scan_finding_fingerprint IS NOT NULL THEN
                        RAISE EXCEPTION 'release_findings: unverified finding cannot carry scan attachment';
                    END IF;
                ELSIF NEW.source_provenance = 'connector_verified_security_scan' THEN
                    IF NEW.security_scan_category_result_id IS NULL
                       OR NEW.scan_finding_fingerprint IS NULL THEN
                        RAISE EXCEPTION 'release_findings: verified security finding requires scan attachment';
                    END IF;
                    IF NEW.finding_type <> 'security'
                       OR NEW.scan_finding_fingerprint !~ '^sha256:[0-9a-f]{64}$'
                       OR octet_length(NEW.source) NOT BETWEEN 1 AND 128 OR btrim(NEW.source) = ''
                       OR octet_length(NEW.summary) NOT BETWEEN 1 AND 500 OR btrim(NEW.summary) = ''
                       OR NEW.detail IS NULL OR octet_length(NEW.detail) NOT BETWEEN 1 AND 4000
                       OR btrim(NEW.detail) = '' THEN
                        RAISE EXCEPTION 'release_findings: invalid verified security finding shape';
                    END IF;
                    SELECT count(*) INTO ok
                    FROM public.security_scan_category_results c
                    JOIN public.security_scan_runs r ON r.id = c.security_scan_run_id
                    WHERE c.id = NEW.security_scan_category_result_id
                      AND c.project_id = NEW.project_id AND c.tenant_id = NEW.tenant_id
                      AND c.category = NEW.category AND c.scanner_key = NEW.source
                      AND c.coverage_status = 'completed_with_findings'
                      AND r.execution_status = 'succeeded'
                      AND r.artifact_provenance = 'connector_verified_ci_security'
                      AND r.execution_observation = 'connector_observed_ci';
                    IF ok <> 1 THEN
                        RAISE EXCEPTION 'release_findings: scan attachment is not trusted category evidence';
                    END IF;
                    SELECT count(*) INTO ok
                    FROM public.release_findings f
                    JOIN public.security_scan_category_results prior
                      ON prior.id = f.security_scan_category_result_id
                    JOIN public.security_scan_category_results incoming
                      ON incoming.id = NEW.security_scan_category_result_id
                    WHERE prior.security_scan_run_id = incoming.security_scan_run_id
                      AND f.scan_finding_fingerprint = NEW.scan_finding_fingerprint;
                    IF ok <> 0 THEN
                        RAISE EXCEPTION 'release_findings: duplicate fingerprint within scan run';
                    END IF;
                ELSE
                    RAISE EXCEPTION 'release_findings source_provenance is unsupported';
                END IF;
        """
        if slice44
        else """
                IF NEW.source_provenance <> 'caller_supplied_unverified' THEN
                    RAISE EXCEPTION 'release_findings source_provenance must be caller_supplied_unverified';
                END IF;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS release_findings_guard ON public.release_findings")
    op.execute("DROP FUNCTION IF EXISTS public.release_findings_guard()")
    op.execute(
        f"""
        CREATE FUNCTION public.release_findings_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE ok int;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'open' THEN
                    RAISE EXCEPTION 'release_findings must be created with status=open';
                END IF;
                {insert_provenance}
                IF NEW.risk_acceptance_record_id IS NOT NULL
                OR NEW.resolution_note IS NOT NULL OR NEW.resolved_at IS NOT NULL
                OR NEW.resolved_by IS NOT NULL THEN
                    RAISE EXCEPTION 'release_findings: resolution/acceptance metadata must be NULL at creation';
                END IF;
                IF (NEW.finding_type = 'security' AND NEW.category NOT IN ({_sql_list(_SECURITY)}))
                OR (NEW.finding_type = 'shortcut' AND NEW.category NOT IN ({_sql_list(_SHORTCUT)})) THEN
                    RAISE EXCEPTION 'release_findings: category % invalid for finding_type %',
                        NEW.category, NEW.finding_type;
                END IF;
                IF NEW.category = 'other'
                AND (NEW.summary IS NULL OR btrim(NEW.summary) = ''
                     OR NEW.detail IS NULL OR btrim(NEW.detail) = '') THEN
                    RAISE EXCEPTION 'release_findings: category=other requires non-empty summary and detail';
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
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
                    IF OLD.status <> 'open' THEN
                        RAISE EXCEPTION 'release_findings: terminal status % cannot transition', OLD.status;
                    END IF;
                    IF NEW.status NOT IN ('resolved','false_positive','accepted','superseded') THEN
                        RAISE EXCEPTION 'release_findings: invalid target status %', NEW.status;
                    END IF;
                    IF NEW.status = 'accepted' THEN
                        IF OLD.severity = 'critical' THEN
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
                            WHERE r.id = NEW.risk_acceptance_record_id
                              AND r.tenant_id = NEW.tenant_id AND r.project_id = NEW.project_id
                              AND r.status = 'active' AND r.expiry_date >= CURRENT_DATE
                              AND r.blocking_category IS NULL AND r.issue_id = NEW.id::text;
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
        "CREATE TRIGGER release_findings_guard BEFORE INSERT OR UPDATE ON release_findings "
        "FOR EACH ROW EXECUTE FUNCTION public.release_findings_guard()"
    )


def _apply_rls_and_append_only() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            CREATE FUNCTION public.{table}_block_dml() RETURNS trigger
            LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
            BEGIN RAISE EXCEPTION '{table} is append-only'; END $fn$
            """
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO uaid_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS security_scan_findings_verify ON release_findings")
    _replace_release_findings_guard(slice44=False)
    op.drop_index("uq_release_findings_scan_fingerprint", table_name="release_findings")
    op.drop_constraint(
        "security_scan_category_project_tenant", "release_findings", type_="foreignkey"
    )
    op.drop_column("release_findings", "scan_finding_fingerprint")
    op.drop_column("release_findings", "security_scan_category_result_id")
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")
    op.execute("DROP TRIGGER IF EXISTS security_scan_categories_verify ON security_scan_category_results")
    op.execute("DROP TRIGGER IF EXISTS security_scan_runs_verify ON security_scan_runs")
    op.execute("DROP FUNCTION IF EXISTS public.security_scan_child_verify_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.security_scan_run_verify_trigger()")
    op.execute("DROP FUNCTION IF EXISTS public.verify_security_scan_run(uuid)")
    op.drop_table("security_scan_category_results")
    op.drop_index("ix_security_scan_runs_latest", table_name="security_scan_runs")
    op.drop_table("security_scan_runs")
