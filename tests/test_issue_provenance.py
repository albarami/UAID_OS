"""Slice 47 issue provenance, finding bridge, and gate-#7 evidence tests."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.release import issues
from app.release.production_autonomy import evaluate_production_autonomy

COMMIT_SHA = "c" * 40


def _finding(**overrides):
    row = {
        "id": uuid.uuid4(),
        "finding_type": "security",
        "category": "authz",
        "severity": "high",
        "status": "open",
        "source_provenance": "connector_verified_security_scan",
        "security_scan_category_result_id": uuid.uuid4(),
        "scan_finding_fingerprint": "sha256:" + "a" * 64,
        "shortcut_detector_category_result_id": None,
        "shortcut_finding_fingerprint": None,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("severity", "blocking_category"),
    [("low", None), ("medium", None), ("high", None), ("critical", "critical_security_blocker")],
)
def test_trusted_security_finding_derives_conservative_issue(severity, blocking_category):
    finding = _finding(severity=severity)

    derived = issues.derive_issue_from_finding(finding)

    assert derived.source_finding_id == finding["id"]
    assert derived.issue_category == "security"
    assert derived.severity == severity
    assert derived.blocking is True
    assert derived.blocking_category == blocking_category
    assert derived.source == "slice47.finding_bridge.v1"
    assert derived.source_provenance == "db_verified_trusted_release_finding"
    assert derived.summary == "Trusted security finding (authz) requires release disposition"
    assert derived.detail is None


@pytest.mark.parametrize("severity", ["low", "medium", "high", "critical"])
def test_every_trusted_shortcut_finding_derives_unacceptable_hard_blocker(severity):
    finding = _finding(
        finding_type="shortcut",
        category="hardcoded_value",
        severity=severity,
        source_provenance="system_executed_shortcut_review",
        security_scan_category_result_id=None,
        scan_finding_fingerprint=None,
        shortcut_detector_category_result_id=uuid.uuid4(),
        shortcut_finding_fingerprint="sha256:" + "b" * 64,
    )

    derived = issues.derive_issue_from_finding(finding)

    assert derived.issue_category == "shortcut"
    assert derived.blocking is True
    assert derived.blocking_category == "fake_done_finding"
    assert issues.is_hard_blocker(derived.severity, derived.blocking_category)


@pytest.mark.parametrize(
    "mutation",
    [
        {"status": "resolved"},
        {"source_provenance": "caller_supplied_unverified"},
        {"source_provenance": "connector_verified"},
        {"security_scan_category_result_id": None},
        {"scan_finding_fingerprint": None},
        {"shortcut_detector_category_result_id": uuid.uuid4()},
        {"category": "other"},
        {"scan_finding_fingerprint": "reported"},
    ],
)
def test_bridge_rejects_untrusted_terminal_mixed_or_malformed_security_finding(mutation):
    with pytest.raises(issues.InvalidIssue):
        issues.derive_issue_from_finding(_finding(**mutation))


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({}, "insufficient_evidence:no_issue_provenance_or_release_binding"),
        (
            {"frozen_release_candidate_count": 1},
            "insufficient_evidence:no_declared_issue_inventory_or_release_verdict",
        ),
        (
            {
                "frozen_release_candidate_count": 1,
                "bound_issue_count": 2,
                "bound_trusted_issue_count": 1,
                "bound_untrusted_issue_count": 1,
            },
            "insufficient_evidence:bound_issue_provenance_incomplete",
        ),
        (
            {
                "frozen_release_candidate_count": 1,
                "bound_issue_count": 2,
                "bound_trusted_issue_count": 2,
                "bound_untrusted_issue_count": 0,
                "bound_finding_bridge_issue_count": 2,
                "bound_security_bridge_issue_count": 1,
                "bound_shortcut_bridge_issue_count": 1,
                "bound_accepted_issue_count": 1,
                "bound_release_consistent_accepted_issue_count": 0,
            },
            "insufficient_evidence:risk_acceptance_release_binding_incomplete",
        ),
        (
            {
                "frozen_release_candidate_count": 1,
                "bound_issue_count": 2,
                "bound_trusted_issue_count": 2,
                "bound_untrusted_issue_count": 0,
                "bound_finding_bridge_issue_count": 2,
                "bound_security_bridge_issue_count": 1,
                "bound_shortcut_bridge_issue_count": 1,
                "bound_accepted_issue_count": 1,
                "bound_release_consistent_accepted_issue_count": 1,
            },
            "insufficient_evidence:verified_known_issue_set_but_no_release_verdict",
        ),
    ],
)
def test_slice47_evidence_alone_never_passes_slice50_gate7(overrides, reason):
    report = evaluate_production_autonomy("p", readiness_level="R5", **overrides).to_dict()
    gate = next(item for item in report["gates"] if item["number"] == 7)

    assert gate["gate"] == "approved_risk_acceptance_records"
    assert gate["status"] == "insufficient_evidence"
    expected = (
        reason
        if overrides.get("frozen_release_candidate_count", 0) == 0
        else "insufficient_evidence:no_audited_release_evidence_core"
    )
    assert gate["reason"] == expected
    assert report["ruleset_version"] == "slice54.v1"
    assert report["a5_satisfied"] is False
    assert report["can_go_live_autonomously"] is False


def test_gate7_evidence_counts_fail_closed_when_inconsistent():
    report = evaluate_production_autonomy(
        "p",
        readiness_level="R5",
        frozen_release_candidate_count=1,
        bound_issue_count=2,
        bound_trusted_issue_count=2,
        bound_untrusted_issue_count=1,
        release_evidence_core_present=True,
        release_evidence_core_audited=True,
        release_verdict_run_present=True,
        release_verdict_binding_current=True,
        release_verdict_evidence_consistent=True,
        release_verdict_spec_verdict="passed",
        release_verdict_gate_eligible=True,
        release_verdict_reason_code="bound_release_issue_disposition_clean",
        release_verdict_decision_scope="known_bound_issue_disposition",
        release_verdict_execution_provenance="system_derived_release_verdict",
    ).to_dict()
    gate = next(item for item in report["gates"] if item["number"] == 7)

    assert gate["status"] == "insufficient_evidence"
    assert gate["reason"] == (
        "insufficient_evidence:release_verdict_evidence_incomplete_or_stale"
    )


def test_slice47_inputs_change_only_gate7():
    baseline = evaluate_production_autonomy("p", readiness_level="R5").to_dict()
    advanced = evaluate_production_autonomy(
        "p",
        readiness_level="R5",
        frozen_release_candidate_count=1,
        bound_issue_count=1,
        bound_trusted_issue_count=1,
        bound_untrusted_issue_count=0,
        bound_finding_bridge_issue_count=1,
        bound_security_bridge_issue_count=1,
    ).to_dict()

    before = {gate["number"]: gate for gate in baseline["gates"]}
    after = {gate["number"]: gate for gate in advanced["gates"]}
    assert {number for number in before if before[number] != after[number]} == {7}


async def _scalar(conn, sql, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def issue_provenance_ctx(admin_engine):
    suffix = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as conn:
        org = await _scalar(
            conn,
            "INSERT INTO organizations (name,slug) VALUES ('IssueProvOrg',:s) RETURNING id",
            s=f"issue-prov-org-{suffix}",
        )
        t1 = await _scalar(
            conn,
            "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'T1',:s) RETURNING id",
            o=org,
            s=f"issue-prov-t1-{suffix}",
        )
        t2 = await _scalar(
            conn,
            "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'T2',:s) RETURNING id",
            o=org,
            s=f"issue-prov-t2-{suffix}",
        )
        p1 = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P1',:s) RETURNING id",
            t=t1,
            s=f"issue-prov-p1-{suffix}",
        )
        p2 = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P2',:s) RETURNING id",
            t=t1,
            s=f"issue-prov-p2-{suffix}",
        )
        px = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"issue-prov-px-{suffix}",
        )
    return {"t1": t1, "t2": t2, "p1": p1, "p2": p2, "px": px, "suffix": suffix}


def _security_payload():
    from app.verify.security_scan import SCANNER_ALLOWLIST, SCHEMA_VERSION

    manifest = []
    categories = []
    for scanner_key, contract in SCANNER_ALLOWLIST.items():
        supported = sorted(contract["supported_categories"])
        manifest.append(
            {
                "scanner_key": scanner_key,
                "scanner_version": contract["scanner_version"],
                "rule_pack_hash": contract["rule_pack_hash"],
                "supported_categories": supported,
            }
        )
        for category in supported:
            findings = []
            coverage = "completed_clean"
            if category == "authz":
                coverage = "completed_with_findings"
                findings = [
                    {
                        "fingerprint": "sha256:" + "d" * 64,
                        "severity": "high",
                        "summary": "SENTINEL finding narrative",
                        "detail": "SENTINEL finding detail",
                        "evidence_ref": "scan://authz/SENTINEL",
                    }
                ]
            categories.append(
                {
                    "category": category,
                    "scanner_key": scanner_key,
                    "scanner_version": contract["scanner_version"],
                    "rule_pack_hash": contract["rule_pack_hash"],
                    "coverage_status": coverage,
                    "findings": findings,
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": COMMIT_SHA,
        "scanner_manifest": manifest,
        "categories": categories,
    }


async def _record_security_finding(ctx):
    from app.release.scm_connector import FakeSCMConnector
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.repositories.security_scans import SecurityScanRepository
    from app.tenancy import TenantContext, tenant_scope

    tenant = TenantContext(ctx["t1"])
    async with tenant_scope(tenant) as session:
        await IntakeCategoryRepository(session, tenant).declare(
            project_id=ctx["p1"],
            category="existing_assets_and_repositories",
            actor="coordinator",
            data={"primary_repository": "owner/issue-provenance", "protected_branch": "main"},
            origin="db-test",
        )
        await SecurityScanRepository(session, tenant).execute_ci(
            project_id=ctx["p1"],
            commit_sha=COMMIT_SHA,
            connector=FakeSCMConnector(security_scan_artifact=_security_payload()),
            actor="security-runner",
        )


@pytest.mark.db
async def test_slice47_catalog_and_findings_guard_are_exact(issue_provenance_ctx, admin_engine):
    async with admin_engine.begin() as conn:
        issue_columns = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='release_issues'"
                    )
                )
            ).all()
        }
        risk_columns = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='risk_acceptance_records'"
                    )
                )
            ).all()
        }
        fk_validated = await _scalar(
            conn,
            "SELECT convalidated FROM pg_constraint "
            "WHERE conname='fk_risk_acceptance_release_ref'",
        )
        findings_guard_md5 = await _scalar(
            conn,
            "SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))",
        )

    assert "source_finding_id" in issue_columns
    assert "subject_type" in risk_columns
    assert fk_validated is False
    assert findings_guard_md5 == "808036faf2660d6810aeca4342e6f1ac"


@pytest.mark.db
async def test_not_valid_fk_preserves_seeded_legacy_but_deliberate_validate_fails(
    issue_provenance_ctx, admin_engine
):
    """Exercise the ruled 0045→0046 legacy condition transactionally at head."""

    ctx = issue_provenance_ctx
    async with admin_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(
                text(
                    "ALTER TABLE risk_acceptance_records "
                    "DROP CONSTRAINT fk_risk_acceptance_release_ref"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE risk_acceptance_records "
                    "DISABLE TRIGGER risk_acceptance_records_guard"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO risk_acceptance_records "
                    "(tenant_id,project_id,release_id,issue_id,severity,reason_for_acceptance,"
                    "business_impact,rollback_or_mitigation_plan,required_follow_up_ticket,"
                    "expiry_date,owner,approver,accepted_by,approval_authority_source,status) "
                    "VALUES (:t,:p,:r,'legacy-external-issue','low','legacy','legacy','legacy',"
                    "'LEGACY-47','2099-01-01','legacy','legacy','[\"legacy\"]'::jsonb,"
                    "'approval_matrix','active')"
                ),
                {
                    "t": ctx["t1"],
                    "p": ctx["p1"],
                    "r": f"legacy-unmatched-{ctx['suffix']}",
                },
            )
            await conn.execute(
                text(
                    "ALTER TABLE risk_acceptance_records "
                    "ENABLE TRIGGER risk_acceptance_records_guard"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE risk_acceptance_records "
                    "ADD CONSTRAINT fk_risk_acceptance_release_ref "
                    "FOREIGN KEY (tenant_id,project_id,release_id) "
                    "REFERENCES release_candidates (tenant_id,project_id,release_ref) "
                    "ON DELETE RESTRICT NOT VALID"
                )
            )
            assert await _scalar(
                conn,
                "SELECT convalidated FROM pg_constraint "
                "WHERE conname='fk_risk_acceptance_release_ref'",
            ) is False
            with pytest.raises(Exception):
                await conn.execute(
                    text(
                        "ALTER TABLE risk_acceptance_records "
                        "VALIDATE CONSTRAINT fk_risk_acceptance_release_ref"
                    )
                )
        finally:
            await transaction.rollback()


@pytest.mark.db
async def test_security_producer_atomically_creates_safe_idempotent_issue_bridge(
    issue_provenance_ctx, admin_engine
):
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = issue_provenance_ctx
    await _record_security_finding(ctx)
    async with admin_engine.begin() as conn:
        finding_id, issue_id, summary, detail, provenance = (
            await conn.execute(
                text(
                    "SELECT f.id,i.id,i.summary,i.detail,i.source_provenance "
                    "FROM release_findings f JOIN release_issues i ON i.source_finding_id=f.id "
                    "WHERE f.project_id=:p"
                ),
                {"p": ctx["p1"]},
            )
        ).one()
        binding_count = await _scalar(
            conn,
            "SELECT count(*) FROM release_candidate_issue_bindings WHERE release_issue_id=:i",
            i=issue_id,
        )
        audit_blob = await _scalar(
            conn,
            "SELECT payload::text FROM audit_logs WHERE target=:target ORDER BY seq DESC LIMIT 1",
            target=f"release_issue:{issue_id}",
        )
    assert provenance == "db_verified_trusted_release_finding"
    assert summary == "Trusted security finding (authz) requires release disposition"
    assert detail is None
    assert binding_count == 0
    assert "SENTINEL" not in audit_blob

    tenant = TenantContext(ctx["t1"])
    async with tenant_scope(tenant) as session:
        count = await ReleaseIssueRepository(session, tenant).reconcile_trusted_findings(
            project_id=ctx["p1"], actor="reconciler", limit=10_000
        )
        issue = await ReleaseIssueRepository(session, tenant).get_by_source_finding(finding_id)
    assert count == 0
    assert issue is not None and issue.id == issue_id


@pytest.mark.db
async def test_direct_sql_rejects_forged_bridge_from_unverified_finding(
    issue_provenance_ctx, rls_engine
):
    from app.repositories.release_findings import ReleaseFindingRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = issue_provenance_ctx
    tenant = TenantContext(ctx["t1"])
    async with tenant_scope(tenant) as session:
        finding = await ReleaseFindingRepository(session, tenant).create(
            project_id=ctx["p1"],
            payload={
                "finding_type": "security",
                "category": "authz",
                "severity": "high",
                "summary": "reported",
                "detail": "reported",
                "source": "manual",
            },
            actor="reporter",
        )
        finding_id = finding.id

    with pytest.raises(Exception):
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant',:t,true)"),
                    {"t": str(ctx["t1"])},
                )
                await conn.execute(
                    text(
                        "INSERT INTO release_issues "
                        "(tenant_id,project_id,issue_category,severity,blocking,summary,source,"
                        "source_provenance,source_finding_id) VALUES "
                        "(:t,:p,'security','high',true,"
                        "'Trusted security finding (authz) requires release disposition',"
                        "'slice47.finding_bridge.v1','db_verified_trusted_release_finding',:f)"
                    ),
                    {"t": ctx["t1"], "p": ctx["p1"], "f": finding_id},
                )


@pytest.mark.db
async def test_new_risk_acceptance_is_frozen_release_and_subject_bound(
    issue_provenance_ctx, admin_engine
):
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = issue_provenance_ctx
    await _record_security_finding(ctx)
    tenant = TenantContext(ctx["t1"])
    async with tenant_scope(tenant) as session:
        issues_repo = ReleaseIssueRepository(session, tenant)
        issue = (await issues_repo.list_trusted_for_project(ctx["p1"], limit=10))[0]
        candidates = ReleaseCandidateRepository(session, tenant)
        candidate = await candidates.create(
            project_id=ctx["p1"], payload={"release_ref": "REL-S47"}, actor="release-manager"
        )
        await candidates.bind_issue(
            candidate_id=candidate.id, release_issue_id=issue.id, actor="release-manager"
        )
        await candidates.freeze(candidate_id=candidate.id, actor="release-manager")
        payload = {
            "release_id": "REL-S47",
            "issue_id": str(issue.source_finding_id),
            "subject_type": "release_finding",
            "severity": "high",
            "reason_for_acceptance": "known limitation",
            "business_impact": "bounded impact",
            "rollback_or_mitigation_plan": "mitigation",
            "required_follow_up_ticket": "ISSUE-47",
            "expiry_date": date(2099, 1, 1),
            "owner": "owner",
            "approver": "release-manager",
            "accepted_by": ["release-manager"],
            "approval_authority_source": "approval_matrix",
        }
        record = await RiskAcceptanceRepository(session, tenant).create(
            project_id=ctx["p1"], payload=payload, actor="release-manager"
        )
        assert record.subject_type == "release_finding"

        with pytest.raises(Exception):
            await RiskAcceptanceRepository(session, tenant).create(
                project_id=ctx["p1"],
                payload={**payload, "issue_id": str(issue.id), "subject_type": "release_finding"},
                actor="release-manager",
            )

    async with admin_engine.begin() as conn:
        assert await _scalar(
            conn,
            "SELECT count(*) FROM risk_acceptance_records WHERE id=:r AND release_id='REL-S47'",
            r=record.id,
        ) == 1


@pytest.mark.db
async def test_direct_sql_rejects_polymorphic_subject_kind_collision(
    issue_provenance_ctx, rls_engine
):
    """A same-UUID issue cannot make an issue acceptance record valid for a finding."""

    from app.models.release_finding import ReleaseFinding
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.risk_acceptance import RiskAcceptanceRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = issue_provenance_ctx
    await _record_security_finding(ctx)
    tenant = TenantContext(ctx["t1"])
    async with tenant_scope(tenant) as session:
        finding = (
            await session.execute(
                select(ReleaseFinding).where(
                    ReleaseFinding.tenant_id == ctx["t1"],
                    ReleaseFinding.project_id == ctx["p1"],
                    ReleaseFinding.source_provenance
                    == "connector_verified_security_scan",
                )
            )
        ).scalars().first()
        assert finding is not None
        await session.execute(
            text(
                "INSERT INTO release_issues "
                "(id,tenant_id,project_id,issue_category,severity,blocking,summary,detail,source) "
                "VALUES (:i,:t,:p,'cost','low',false,'collision fixture','fixture','test')"
            ),
            {"i": finding.id, "t": ctx["t1"], "p": ctx["p1"]},
        )
        candidates = ReleaseCandidateRepository(session, tenant)
        candidate = await candidates.create(
            project_id=ctx["p1"],
            payload={"release_ref": "REL-S47-KIND"},
            actor="fixture",
        )
        await candidates.bind_issue(
            candidate_id=candidate.id,
            release_issue_id=finding.id,
            actor="fixture",
        )
        await candidates.freeze(candidate_id=candidate.id, actor="fixture")
        record = await RiskAcceptanceRepository(session, tenant).create(
            project_id=ctx["p1"],
            payload={
                "release_id": candidate.release_ref,
                "issue_id": str(finding.id),
                "subject_type": "release_issue",
                "severity": "low",
                "reason_for_acceptance": "fixture",
                "business_impact": "fixture",
                "rollback_or_mitigation_plan": "fixture",
                "required_follow_up_ticket": "S47-KIND",
                "expiry_date": date(2099, 1, 1),
                "owner": "owner",
                "approver": "approver",
                "accepted_by": ["approver"],
                "approval_authority_source": "approval_matrix",
            },
            actor="fixture",
        )
        finding_id = finding.id
        record_id = record.id

    with pytest.raises(Exception):
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant',:t,true)"),
                    {"t": str(ctx["t1"])},
                )
                await conn.execute(
                    text(
                        "UPDATE release_findings SET status='accepted',"
                        "risk_acceptance_record_id=:r,updated_at=clock_timestamp() WHERE id=:f"
                    ),
                    {"r": record_id, "f": finding_id},
                )
