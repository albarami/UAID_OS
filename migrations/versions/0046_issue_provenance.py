"""issue provenance + findings bridge + risk-acceptance release binding

Revision ID: 0046
Revises: 0045
Create Date: 2026-07-12

Slice 47. Adds an immutable trusted-finding attachment to ``release_issues`` and a
new-write-only (NOT VALID over history) composite FK from risk-acceptance release refs to
``release_candidates``. ``subject_type`` disambiguates the existing polymorphic issue/finding
reference. Existing rows are never relabelled. The Slice-44/45 ``release_findings_guard()`` is
untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HARD_REFUSALS = (
    "critical_security_blocker",
    "fake_done_finding",
    "missing_production_rollback",
    "missing_regulated_or_safety_authority",
)
_ISSUE_IMMUTABLE = (
    "id",
    "tenant_id",
    "project_id",
    "issue_category",
    "severity",
    "blocking",
    "blocking_category",
    "summary",
    "detail",
    "source",
    "source_provenance",
    "created_at",
)
_RISK_IMMUTABLE = (
    "id",
    "tenant_id",
    "project_id",
    "release_id",
    "issue_id",
    "severity",
    "affected_requirements",
    "reason_for_acceptance",
    "business_impact",
    "compensating_controls",
    "rollback_or_mitigation_plan",
    "evidence_links",
    "required_follow_up_ticket",
    "included_in_release_notes",
    "expiry_date",
    "owner",
    "approver",
    "accepted_by",
    "approval_authority_source",
    "blocking_category",
    "approver_provenance",
    "created_at",
)


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _risk_guard(*, slice47: bool) -> str:
    immutable = _RISK_IMMUTABLE + (("subject_type",) if slice47 else ())
    immutable_checks = "\n            OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in immutable
    )
    binding_check = (
        """
                IF NEW.subject_type NOT IN ('release_issue','release_finding') THEN
                    RAISE EXCEPTION 'risk_acceptance_records: subject_type is required for new rows';
                END IF;
                SELECT count(*) INTO ok
                FROM public.release_candidates c
                WHERE c.tenant_id=NEW.tenant_id
                  AND c.project_id=NEW.project_id
                  AND c.release_ref=NEW.release_id
                  AND c.status='frozen'
                  AND (
                    (NEW.subject_type='release_issue' AND EXISTS (
                        SELECT 1
                        FROM public.release_candidate_issue_bindings b
                        JOIN public.release_issues i
                          ON i.id=b.release_issue_id AND i.tenant_id=b.tenant_id
                        WHERE b.release_candidate_id=c.id
                          AND b.project_id=c.project_id
                          AND b.tenant_id=c.tenant_id
                          AND i.project_id=c.project_id
                          AND i.id::text=NEW.issue_id
                    ))
                    OR
                    (NEW.subject_type='release_finding' AND EXISTS (
                        SELECT 1
                        FROM public.release_findings f
                        JOIN public.release_issues i
                          ON i.source_finding_id=f.id AND i.tenant_id=f.tenant_id
                         AND i.project_id=f.project_id
                        JOIN public.release_candidate_issue_bindings b
                          ON b.release_issue_id=i.id AND b.tenant_id=i.tenant_id
                         AND b.project_id=i.project_id
                        WHERE b.release_candidate_id=c.id
                          AND f.tenant_id=c.tenant_id
                          AND f.project_id=c.project_id
                          AND f.id::text=NEW.issue_id
                          AND i.blocking_category IS NULL
                          AND i.severity<>'critical'
                    ))
                  );
                IF ok<>1 THEN
                    RAISE EXCEPTION 'risk_acceptance_records: release/subject binding is not exact';
                END IF;
        """
        if slice47
        else ""
    )
    declaration = "DECLARE ok int;" if slice47 else ""
    return f"""
        CREATE OR REPLACE FUNCTION public.risk_acceptance_records_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        {declaration}
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'active' THEN
                    RAISE EXCEPTION 'risk_acceptance_records must be created with status=active';
                END IF;
                IF NEW.approver_provenance NOT IN ('caller_supplied_unverified', 'request_authenticated') THEN
                    RAISE EXCEPTION 'risk_acceptance_records approver_provenance must be caller_supplied_unverified or request_authenticated';
                END IF;
                IF NEW.approval_authority_source <> 'approval_matrix' THEN
                    RAISE EXCEPTION 'risk_acceptance_records approval_authority_source must be approval_matrix';
                END IF;
                IF NEW.blocking_category IN ({_sql_list(_HARD_REFUSALS)}) THEN
                    RAISE EXCEPTION 'risk_acceptance_records: hard-refusal category cannot be accepted (%)',
                        NEW.blocking_category;
                END IF;
                {binding_check}
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'risk_acceptance_records: only status and updated_at are mutable';
                END IF;
                IF NEW.status IS DISTINCT FROM OLD.status THEN
                    IF OLD.status <> 'active'
                    OR NEW.status NOT IN ('expired', 'revoked', 'superseded') THEN
                        RAISE EXCEPTION 'risk_acceptance_records invalid status transition: % -> %',
                            OLD.status, NEW.status;
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
    """


def _issue_guard(*, slice47: bool) -> str:
    immutable = _ISSUE_IMMUTABLE + (("source_finding_id",) if slice47 else ())
    immutable_checks = "\n            OR ".join(
        f"NEW.{column} IS DISTINCT FROM OLD.{column}" for column in immutable
    )
    source_check = (
        """
                IF NEW.source_provenance='caller_supplied_unverified' THEN
                    IF NEW.source_finding_id IS NOT NULL THEN
                        RAISE EXCEPTION 'release_issues: unverified issue cannot carry trusted finding';
                    END IF;
                ELSIF NEW.source_provenance='db_verified_trusted_release_finding' THEN
                    IF NEW.source_finding_id IS NULL THEN
                        RAISE EXCEPTION 'release_issues: trusted issue requires source_finding_id';
                    END IF;
                    SELECT f.finding_type,f.category,f.severity,f.status,f.source_provenance,
                           f.security_scan_category_result_id,f.scan_finding_fingerprint,
                           f.shortcut_detector_category_result_id,f.shortcut_finding_fingerprint
                    INTO finding_type,finding_category,finding_severity,finding_status,
                         finding_provenance,security_result,security_fingerprint,
                         shortcut_result,shortcut_fingerprint
                    FROM public.release_findings f
                    WHERE f.id=NEW.source_finding_id
                      AND f.tenant_id=NEW.tenant_id
                      AND f.project_id=NEW.project_id;
                    IF NOT FOUND OR finding_status<>'open' THEN
                        RAISE EXCEPTION 'release_issues: trusted source finding is missing, cross-project, or non-open';
                    END IF;
                    IF finding_type='security' THEN
                        IF finding_provenance<>'connector_verified_security_scan'
                           OR security_result IS NULL
                           OR security_fingerprint !~ '^sha256:[0-9a-f]{64}$'
                           OR shortcut_result IS NOT NULL OR shortcut_fingerprint IS NOT NULL
                           OR finding_category='other' THEN
                            RAISE EXCEPTION 'release_issues: security source finding is not trusted';
                        END IF;
                        expected_blocking_category := CASE
                            WHEN finding_severity='critical' THEN 'critical_security_blocker'
                            ELSE NULL END;
                    ELSIF finding_type='shortcut' THEN
                        IF finding_provenance<>'system_executed_shortcut_review'
                           OR shortcut_result IS NULL
                           OR shortcut_fingerprint !~ '^sha256:[0-9a-f]{64}$'
                           OR security_result IS NOT NULL OR security_fingerprint IS NOT NULL
                           OR finding_category='other' THEN
                            RAISE EXCEPTION 'release_issues: shortcut source finding is not trusted';
                        END IF;
                        expected_blocking_category := 'fake_done_finding';
                    ELSE
                        RAISE EXCEPTION 'release_issues: source finding type is unsupported';
                    END IF;
                    expected_summary := 'Trusted ' || finding_type || ' finding ('
                        || finding_category || ') requires release disposition';
                    IF NEW.issue_category<>finding_type
                       OR NEW.severity<>finding_severity
                       OR NEW.blocking IS NOT TRUE
                       OR NEW.blocking_category IS DISTINCT FROM expected_blocking_category
                       OR NEW.source<>'slice47.finding_bridge.v1'
                       OR NEW.summary<>expected_summary
                       OR octet_length(NEW.summary)>500
                       OR NEW.detail IS NOT NULL THEN
                        RAISE EXCEPTION 'release_issues: trusted bridge fields do not match source finding';
                    END IF;
                ELSE
                    RAISE EXCEPTION 'release_issues source_provenance is unsupported';
                END IF;
        """
        if slice47
        else """
                IF NEW.source_provenance <> 'caller_supplied_unverified' THEN
                    RAISE EXCEPTION 'release_issues source_provenance must be caller_supplied_unverified';
                END IF;
        """
    )
    accepted_query = (
        """
                        SELECT count(*) INTO ok
                        FROM public.risk_acceptance_records r
                        JOIN public.release_candidates c
                          ON c.tenant_id=r.tenant_id AND c.project_id=r.project_id
                         AND c.release_ref=r.release_id AND c.status='frozen'
                        JOIN public.release_candidate_issue_bindings b
                          ON b.release_candidate_id=c.id AND b.project_id=c.project_id
                         AND b.tenant_id=c.tenant_id AND b.release_issue_id=NEW.id
                        WHERE r.id=NEW.risk_acceptance_record_id
                          AND r.tenant_id=NEW.tenant_id
                          AND r.project_id=NEW.project_id
                          AND r.status='active'
                          AND r.expiry_date>=CURRENT_DATE
                          AND r.blocking_category IS NULL
                          AND r.subject_type='release_issue'
                          AND r.issue_id=NEW.id::text;
        """
        if slice47
        else """
                        SELECT 1 INTO ok FROM public.risk_acceptance_records r
                            WHERE r.id = NEW.risk_acceptance_record_id
                              AND r.tenant_id = NEW.tenant_id
                              AND r.project_id = NEW.project_id
                              AND r.status = 'active'
                              AND r.expiry_date >= CURRENT_DATE
                              AND r.blocking_category IS NULL
                              AND r.issue_id = NEW.id::text;
        """
    )
    accepted_missing = "ok<>1" if slice47 else "ok IS NULL"
    declarations = (
        """DECLARE ok int;
        finding_type text; finding_category text; finding_severity text; finding_status text;
        finding_provenance text; security_result uuid; security_fingerprint text;
        shortcut_result uuid; shortcut_fingerprint text; expected_blocking_category text;
        expected_summary text;"""
        if slice47
        else "DECLARE ok int;"
    )
    return f"""
        CREATE OR REPLACE FUNCTION public.release_issues_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        {declarations}
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'open' THEN
                    RAISE EXCEPTION 'release_issues must be created with status=open';
                END IF;
                {source_check}
                IF NEW.risk_acceptance_record_id IS NOT NULL
                OR NEW.resolution_note IS NOT NULL
                OR NEW.resolved_at IS NOT NULL
                OR NEW.resolved_by IS NOT NULL THEN
                    RAISE EXCEPTION 'release_issues: resolution/acceptance metadata must be NULL at creation';
                END IF;
                IF NEW.issue_category = 'other'
                AND (NEW.summary IS NULL OR btrim(NEW.summary) = ''
                     OR NEW.detail IS NULL OR btrim(NEW.detail) = '') THEN
                    RAISE EXCEPTION 'release_issues: issue_category=other requires non-empty summary and detail';
                END IF;
                IF (NEW.severity = 'critical'
                    OR NEW.blocking_category IN ({_sql_list(_HARD_REFUSALS)}))
                AND NEW.blocking IS NOT TRUE THEN
                    RAISE EXCEPTION 'release_issues: hard-blocker issues (critical or hard-refusal category) must be blocking';
                END IF;
            ELSIF TG_OP = 'UPDATE' THEN
                IF {immutable_checks} THEN
                    RAISE EXCEPTION 'release_issues: identity/content/source fields are immutable';
                END IF;
                IF NEW.status IS NOT DISTINCT FROM OLD.status THEN
                    IF NEW.risk_acceptance_record_id IS DISTINCT FROM OLD.risk_acceptance_record_id
                    OR NEW.resolution_note IS DISTINCT FROM OLD.resolution_note
                    OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
                    OR NEW.resolved_by IS DISTINCT FROM OLD.resolved_by
                    OR NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
                        RAISE EXCEPTION 'release_issues: fields change only via a status transition';
                    END IF;
                ELSE
                    IF OLD.status <> 'open' THEN
                        RAISE EXCEPTION 'release_issues: terminal status % cannot transition', OLD.status;
                    END IF;
                    IF NEW.status NOT IN ('resolved','accepted','superseded') THEN
                        RAISE EXCEPTION 'release_issues: invalid target status %', NEW.status;
                    END IF;
                    IF NEW.status = 'accepted' THEN
                        IF OLD.severity = 'critical'
                        OR OLD.blocking_category IN ({_sql_list(_HARD_REFUSALS)}) THEN
                            RAISE EXCEPTION 'release_issues: critical/hard-blocker issues cannot be accepted';
                        END IF;
                        IF NEW.risk_acceptance_record_id IS NULL THEN
                            RAISE EXCEPTION 'release_issues: accepted requires a risk_acceptance_record_id';
                        END IF;
                        IF NEW.resolution_note IS NOT NULL
                        OR NEW.resolved_at IS NOT NULL
                        OR NEW.resolved_by IS NOT NULL THEN
                            RAISE EXCEPTION 'release_issues: accepted must not set resolution metadata';
                        END IF;
                        {accepted_query}
                        IF {accepted_missing} THEN
                            RAISE EXCEPTION 'release_issues: no usable risk-acceptance record for this issue';
                        END IF;
                    ELSE
                        IF NEW.risk_acceptance_record_id IS NOT NULL THEN
                            RAISE EXCEPTION 'release_issues: only accepted may set risk_acceptance_record_id';
                        END IF;
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
    """


def upgrade() -> None:
    op.add_column("release_issues", sa.Column("source_finding_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "source_finding_tenant",
        "release_issues",
        "release_findings",
        ["source_finding_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_release_issues_source_finding",
        "release_issues",
        ["tenant_id", "source_finding_id"],
        unique=True,
        postgresql_where=sa.text("source_finding_id IS NOT NULL"),
    )

    op.add_column("risk_acceptance_records", sa.Column("subject_type", sa.Text(), nullable=True))
    op.create_check_constraint(
        "subject_type_valid",
        "risk_acceptance_records",
        "subject_type IS NULL OR subject_type IN ('release_issue','release_finding')",
    )
    op.execute(
        "ALTER TABLE public.risk_acceptance_records "
        "ADD CONSTRAINT fk_risk_acceptance_release_ref "
        "FOREIGN KEY (tenant_id,project_id,release_id) "
        "REFERENCES public.release_candidates (tenant_id,project_id,release_ref) "
        "ON DELETE RESTRICT NOT VALID"
    )

    op.execute(_risk_guard(slice47=True))
    op.execute(_issue_guard(slice47=True))
    # Keep ``release_findings_guard()`` byte-stable while closing the new polymorphic subject-kind
    # boundary with a separate additive trigger.
    op.execute(
        """
        CREATE FUNCTION public.release_findings_slice47_subject_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $fn$
        DECLARE ok int;
        BEGIN
            IF TG_OP='UPDATE' AND NEW.status='accepted' AND OLD.status IS DISTINCT FROM NEW.status THEN
                IF OLD.finding_type='shortcut'
                   AND OLD.source_provenance='system_executed_shortcut_review' THEN
                    RAISE EXCEPTION 'release_findings: trusted shortcut findings cannot be accepted';
                END IF;
                SELECT count(*) INTO ok
                FROM public.risk_acceptance_records r
                WHERE r.id=NEW.risk_acceptance_record_id
                  AND r.tenant_id=NEW.tenant_id
                  AND r.project_id=NEW.project_id
                  AND r.subject_type='release_finding'
                  AND r.issue_id=NEW.id::text;
                IF ok<>1 THEN
                    RAISE EXCEPTION 'release_findings: accepted record subject kind must be release_finding';
                END IF;
            END IF;
            RETURN NEW;
        END
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_findings_slice47_subject_guard
        BEFORE UPDATE ON public.release_findings
        FOR EACH ROW EXECUTE FUNCTION public.release_findings_slice47_subject_guard()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.release_issues WHERE source_finding_id IS NOT NULL) THEN
                RAISE EXCEPTION '0046 downgrade refused: trusted issue attachments exist';
            END IF;
            IF EXISTS (SELECT 1 FROM public.risk_acceptance_records WHERE subject_type IS NOT NULL) THEN
                RAISE EXCEPTION '0046 downgrade refused: release-bound risk acceptances exist';
            END IF;
        END
        $fn$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS release_findings_slice47_subject_guard "
        "ON public.release_findings"
    )
    op.execute("DROP FUNCTION IF EXISTS public.release_findings_slice47_subject_guard()")
    op.execute(_issue_guard(slice47=False))
    op.execute(_risk_guard(slice47=False))

    op.drop_constraint(
        "fk_risk_acceptance_release_ref", "risk_acceptance_records", type_="foreignkey"
    )
    op.drop_constraint("subject_type_valid", "risk_acceptance_records", type_="check")
    op.drop_column("risk_acceptance_records", "subject_type")

    op.drop_index("uq_release_issues_source_finding", table_name="release_issues")
    op.drop_constraint("source_finding_tenant", "release_issues", type_="foreignkey")
    op.drop_column("release_issues", "source_finding_id")
