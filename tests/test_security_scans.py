from __future__ import annotations

import copy
import io
import json
import zipfile
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text


COMMIT_SHA = "a" * 40


def _valid_payload():
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
            categories.append(
                {
                    "category": category,
                    "scanner_key": scanner_key,
                    "scanner_version": contract["scanner_version"],
                    "rule_pack_hash": contract["rule_pack_hash"],
                    "coverage_status": "completed_clean",
                    "findings": [],
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": COMMIT_SHA,
        "scanner_manifest": manifest,
        "categories": categories,
    }


def _finding(*, severity: str = "critical") -> dict:
    return {
        "fingerprint": "sha256:" + "b" * 64,
        "severity": severity,
        "summary": "Authorization bypass",
        "detail": "A protected operation can be reached without the required role.",
        "evidence_ref": "scan://authz/AUTHZ-001",
    }


def test_complete_five_category_zero_finding_artifact_is_coverage_complete():
    from app.verify.security_scan import MANDATORY_CATEGORIES, validate_security_scan_artifact

    artifact = validate_security_scan_artifact(
        _valid_payload(), expected_commit_sha=COMMIT_SHA
    )

    assert {item.category for item in artifact.categories} == set(MANDATORY_CATEGORIES)
    assert artifact.coverage.complete is True
    assert artifact.coverage.finding_count == 0
    assert artifact.coverage.failed_category_count == 0
    assert json.loads(json.dumps(artifact.to_dict()))["schema_version"] == (
        "slice44.security_scan.v1"
    )


def test_gate5_evidence_is_a_pure_deterministic_value_object():
    from app.verify.security_scan import Gate5Evidence

    evidence = Gate5Evidence(
        scope_resolved=True,
        binding_resolved=True,
        run_present=True,
        artifact_trusted=True,
        execution_failed=False,
        coverage_complete=True,
        evidence_consistent=True,
        mandatory_category_count=5,
        completed_category_count=5,
        failed_category_count=0,
        finding_count=0,
    )
    assert evidence.to_dict() == evidence.gate_kwargs()


def test_missing_category_never_becomes_clean_coverage():
    from app.verify.security_scan import InvalidSecurityScanArtifact, validate_security_scan_artifact

    payload = _valid_payload()
    payload["categories"].pop()

    with pytest.raises(InvalidSecurityScanArtifact, match="mandatory category coverage"):
        validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)


def test_completed_findings_are_normalized_and_counted():
    from app.verify.security_scan import validate_security_scan_artifact

    payload = _valid_payload()
    authz = next(item for item in payload["categories"] if item["category"] == "authz")
    authz["coverage_status"] = "completed_with_findings"
    authz["findings"] = [_finding()]

    artifact = validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)

    normalized = next(item for item in artifact.categories if item.category == "authz")
    assert normalized.findings[0].severity == "critical"
    assert artifact.coverage.complete is True
    assert artifact.coverage.finding_count == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda p: p.update(commit_sha="b" * 40), "commit_sha"),
        (lambda p: p.update(extra=True), "unknown or missing"),
        (
            lambda p: p["scanner_manifest"][0].update(scanner_key="unknown"),
            "scanner manifest",
        ),
        (
            lambda p: p["categories"][0].update(category="other"),
            "mandatory category coverage",
        ),
        (
            lambda p: p["categories"][0].update(
                coverage_status="completed_with_findings", findings=[]
            ),
            "completed_with_findings",
        ),
    ],
)
def test_artifact_contract_fails_closed(mutation, message):
    from app.verify.security_scan import InvalidSecurityScanArtifact, validate_security_scan_artifact

    payload = copy.deepcopy(_valid_payload())
    mutation(payload)

    with pytest.raises(InvalidSecurityScanArtifact, match=message):
        validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)


def test_unknown_severity_fails_instead_of_downgrading():
    from app.verify.security_scan import InvalidSecurityScanArtifact, validate_security_scan_artifact

    payload = _valid_payload()
    authz = next(item for item in payload["categories"] if item["category"] == "authz")
    authz["coverage_status"] = "completed_with_findings"
    authz["findings"] = [_finding(severity="urgent")]

    with pytest.raises(InvalidSecurityScanArtifact, match="severity"):
        validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)


def test_finding_fingerprint_is_unique_across_the_entire_run():
    from app.verify.security_scan import InvalidSecurityScanArtifact, validate_security_scan_artifact

    payload = _valid_payload()
    for category_name in ("authz", "injection"):
        category = next(
            item for item in payload["categories"] if item["category"] == category_name
        )
        category["coverage_status"] = "completed_with_findings"
        category["findings"] = [_finding(severity="high")]

    with pytest.raises(InvalidSecurityScanArtifact, match="duplicated within the run"):
        validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)


def test_raw_scanner_fields_and_over_cap_text_are_rejected():
    from app.verify.security_scan import InvalidSecurityScanArtifact, validate_security_scan_artifact

    payload = _valid_payload()
    authz = next(item for item in payload["categories"] if item["category"] == "authz")
    authz["coverage_status"] = "completed_with_findings"
    finding = _finding()
    finding["raw_snippet"] = "secret source"
    authz["findings"] = [finding]
    with pytest.raises(InvalidSecurityScanArtifact, match="finding fields"):
        validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)

    payload = _valid_payload()
    authz = next(item for item in payload["categories"] if item["category"] == "authz")
    authz["coverage_status"] = "completed_with_findings"
    finding = _finding()
    finding["summary"] = "x" * 501
    authz["findings"] = [finding]
    with pytest.raises(InvalidSecurityScanArtifact, match="summary"):
        validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)


def test_failed_category_is_valid_evidence_but_incomplete_coverage():
    from app.verify.security_scan import validate_security_scan_artifact

    payload = _valid_payload()
    payload["categories"][0]["coverage_status"] = "failed"

    artifact = validate_security_scan_artifact(payload, expected_commit_sha=COMMIT_SHA)

    assert artifact.coverage.complete is False
    assert artifact.coverage.failed_category_count == 1


def _security_archive(payload: dict, *, filename: str = "security-scan-results.json") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(filename, json.dumps(payload))
    return out.getvalue()


def test_security_scan_archive_parser_validates_exact_commit_and_shape():
    from app.release.scm_connector import parse_github_security_scan_artifact_archive

    artifact = parse_github_security_scan_artifact_archive(
        _security_archive(_valid_payload()), expected_commit_sha=COMMIT_SHA
    )

    assert artifact.commit_sha == COMMIT_SHA
    assert artifact.coverage.complete is True


@pytest.mark.parametrize(
    "archive",
    [
        _security_archive({"bad": True}),
        _security_archive({}, filename="../security-scan-results.json"),
    ],
)
def test_security_scan_archive_parser_fails_closed(archive):
    from app.release.scm_connector import (
        SCMConnectorError,
        parse_github_security_scan_artifact_archive,
    )

    with pytest.raises(SCMConnectorError):
        parse_github_security_scan_artifact_archive(
            archive, expected_commit_sha=COMMIT_SHA
        )


@pytest.mark.asyncio
async def test_fake_scm_has_separate_security_scan_artifact_channel():
    from app.release.scm_connector import FakeSCMConnector

    fake = FakeSCMConnector(security_scan_artifact=_valid_payload())

    artifact = await fake.fetch_security_scan_artifact(
        repo_ref="owner/repo", commit_sha=COMMIT_SHA
    )

    assert artifact is not None
    assert artifact.coverage.complete is True


def _gate5(**overrides):
    from app.release.production_autonomy import evaluate_production_autonomy

    inputs = {
        "security_scan_scope_resolved": True,
        "security_scan_binding_resolved": True,
        "security_scan_run_present": True,
        "security_scan_artifact_trusted": True,
        "security_scan_execution_failed": False,
        "security_scan_coverage_complete": True,
        "security_scan_evidence_consistent": True,
        "security_scan_mandatory_category_count": 5,
        "security_scan_completed_category_count": 5,
        "security_scan_failed_category_count": 0,
        "security_scan_finding_count": 0,
        "open_unaccepted_critical_security_finding_count": 0,
    }
    inputs.update(overrides)
    report = evaluate_production_autonomy("p", readiness_level="R5", **inputs)
    return next(gate for gate in report.to_dict()["gates"] if gate["number"] == 5)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"security_scan_scope_resolved": False},
            "insufficient_evidence:security_scan_scope_unresolved",
        ),
        (
            {"security_scan_binding_resolved": False},
            "insufficient_evidence:security_scan_binding_unresolved",
        ),
        (
            {"security_scan_run_present": False},
            "insufficient_evidence:security_scan_not_executed",
        ),
        (
            {"security_scan_artifact_trusted": False},
            "insufficient_evidence:security_scan_observed_unverified",
        ),
        (
            {"security_scan_execution_failed": True},
            "insufficient_evidence:security_scan_execution_failed",
        ),
        (
            {"security_scan_coverage_complete": False},
            "insufficient_evidence:security_scan_coverage_incomplete",
        ),
        (
            {"security_scan_evidence_consistent": False},
            "insufficient_evidence:security_scan_evidence_inconsistent",
        ),
        (
            {"security_scan_completed_category_count": 4},
            "insufficient_evidence:security_scan_evidence_inconsistent",
        ),
        (
            {
                "open_security_finding_count": 1,
                "open_unaccepted_critical_security_finding_count": 1,
            },
            "insufficient_evidence:critical_security_findings_open",
        ),
    ],
)
def test_gate5_fail_closed_ladder(overrides, reason):
    gate = _gate5(**overrides)
    assert gate["status"] == "insufficient_evidence"
    assert gate["reason"] == reason


def test_gate5_passes_only_complete_trusted_coverage_without_open_critical():
    gate = _gate5(open_security_finding_count=2)
    assert gate["status"] == "passed"
    assert gate["reason"] == "passed:no_unaccepted_critical_security_findings_verified"


def test_security_coverage_changes_only_gate5_and_never_go_live():
    from app.release.production_autonomy import evaluate_production_autonomy

    before = evaluate_production_autonomy("p", readiness_level="R5").to_dict()
    complete = {
        "security_scan_scope_resolved": True,
        "security_scan_binding_resolved": True,
        "security_scan_run_present": True,
        "security_scan_artifact_trusted": True,
        "security_scan_execution_failed": False,
        "security_scan_coverage_complete": True,
        "security_scan_evidence_consistent": True,
        "security_scan_mandatory_category_count": 5,
        "security_scan_completed_category_count": 5,
        "security_scan_failed_category_count": 0,
        "security_scan_finding_count": 0,
    }
    after = evaluate_production_autonomy("p", readiness_level="R5", **complete).to_dict()

    assert {g["number"]: g for g in before["gates"] if g["number"] != 5} == {
        g["number"]: g for g in after["gates"] if g["number"] != 5
    }
    assert next(g for g in after["gates"] if g["number"] == 5)["status"] == "passed"
    assert after["a5_satisfied"] is False
    assert after["can_go_live_autonomously"] is False


# --- DB-backed: migration 0043 invariants ------------------------------------


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def security_db_ctx(admin_engine):
    suffix = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as conn:
        org = await _scalar(
            conn,
            "INSERT INTO organizations (name,slug) VALUES ('SecurityOrg',:s) RETURNING id",
            s=f"security-org-{suffix}",
        )
        t1 = await _scalar(
            conn,
            "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'T1',:s) RETURNING id",
            o=org,
            s=f"security-t1-{suffix}",
        )
        t2 = await _scalar(
            conn,
            "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'T2',:s) RETURNING id",
            o=org,
            s=f"security-t2-{suffix}",
        )
        p1 = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P1',:s) RETURNING id",
            t=t1,
            s=f"security-p1-{suffix}",
        )
        p2 = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P2',:s) RETURNING id",
            t=t1,
            s=f"security-p2-{suffix}",
        )
        px = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'PX',:s) RETURNING id",
            t=t2,
            s=f"security-px-{suffix}",
        )
    return {"t1": t1, "t2": t2, "p1": p1, "p2": p2, "px": px}


@pytest.mark.db
async def test_security_scan_catalog_is_rls_forced_append_only(security_db_ctx, admin_engine):
    async with admin_engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname IN "
                    "('security_scan_runs','security_scan_category_results') ORDER BY relname"
                )
            )
        ).all()
        assert rows == [
            ("security_scan_category_results", True, True),
            ("security_scan_runs", True, True),
        ]
        columns = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='release_findings'"
                    )
                )
            ).all()
        }
        assert {"security_scan_category_result_id", "scan_finding_fingerprint"} <= columns


@pytest.mark.db
async def test_direct_sql_rejects_success_without_mandatory_category_children(
    security_db_ctx, admin_engine
):
    from app.verify.security_scan import code_owned_manifest_hash

    ctx = security_db_ctx
    with pytest.raises(Exception, match="security_scan_runs: aggregate mismatch"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO security_scan_runs "
                    "(tenant_id,project_id,provider,repo_binding_hash,commit_sha,"
                    "artifact_schema_version,scanner_manifest_hash,artifact_digest,"
                    "execution_status,artifact_provenance,execution_observation,failure_code,"
                    "reported_category_count,reported_finding_count,coverage_complete,coverage_verdict) "
                    "VALUES (:t,:p,'github',:h,:sha,'slice44.security_scan.v1',:mh,:h,"
                    "'succeeded','connector_verified_ci_security','connector_observed_ci',NULL,"
                    "5,0,true,'covered')"
                ),
                {
                    "t": ctx["t1"],
                    "p": ctx["p1"],
                    "h": "sha256:" + "a" * 64,
                    "mh": code_owned_manifest_hash(),
                    "sha": COMMIT_SHA,
                },
            )


@pytest.mark.db
async def test_direct_sql_preserves_slice23_insert_and_mutation_backstops(
    security_db_ctx, admin_engine
):
    ctx = security_db_ctx
    async with admin_engine.begin() as conn:
        finding_id = await _scalar(
            conn,
            "INSERT INTO release_findings "
            "(tenant_id,project_id,finding_type,category,severity,summary,source) "
            "VALUES (:t,:p,'security','authz','critical','manual critical','review') RETURNING id",
            t=ctx["t1"],
            p=ctx["p1"],
        )
    with pytest.raises(Exception, match="critical findings cannot be accepted"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("UPDATE release_findings SET status='accepted' WHERE id=:id"),
                {"id": finding_id},
            )
    with pytest.raises(Exception, match="identity/content/source fields are immutable"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("UPDATE release_findings SET summary='rewritten' WHERE id=:id"),
                {"id": finding_id},
            )
    with pytest.raises(Exception, match="does not allow DELETE"):
        async with admin_engine.begin() as conn:
            await conn.execute(text("DELETE FROM release_findings WHERE id=:id"), {"id": finding_id})


@pytest.mark.db
async def test_direct_sql_rejects_verified_finding_without_scan_attachment(
    security_db_ctx, admin_engine
):
    ctx = security_db_ctx
    with pytest.raises(Exception, match="verified security finding requires scan attachment"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO release_findings "
                    "(tenant_id,project_id,finding_type,category,severity,summary,source,source_provenance) "
                    "VALUES (:t,:p,'security','authz','high','scan finding','uaid.authz_scan',"
                    "'connector_verified_security_scan')"
                ),
                {"t": ctx["t1"], "p": ctx["p1"]},
            )


@pytest.mark.db
async def test_direct_sql_rejects_duplicate_fingerprint_across_categories_in_one_run(
    security_db_ctx, admin_engine
):
    from app.verify.security_scan import SCANNER_ALLOWLIST, code_owned_manifest_hash

    ctx = security_db_ctx
    digest = "sha256:" + "d" * 64
    async with admin_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            run_id = await _scalar(
                conn,
                "INSERT INTO security_scan_runs "
                "(tenant_id,project_id,provider,repo_binding_hash,commit_sha,"
                "artifact_schema_version,scanner_manifest_hash,artifact_digest,execution_status,"
                "artifact_provenance,execution_observation,failure_code,reported_category_count,"
                "reported_finding_count,coverage_complete,coverage_verdict) VALUES "
                "(:t,:p,'github',:h,:sha,'slice44.security_scan.v1',:mh,:d,'succeeded',"
                "'connector_verified_ci_security','connector_observed_ci',NULL,5,2,true,'covered') "
                "RETURNING id",
                t=ctx["t1"],
                p=ctx["p1"],
                h="sha256:" + "e" * 64,
                sha=COMMIT_SHA,
                mh=code_owned_manifest_hash(),
                d=digest,
            )
            results = {}
            for category in ("authz", "injection", "secrets_exposure", "unsafe_tool", "supply_chain"):
                key, contract = next(
                    (key, value)
                    for key, value in SCANNER_ALLOWLIST.items()
                    if category in value["supported_categories"]
                )
                results[category] = await _scalar(
                    conn,
                    "INSERT INTO security_scan_category_results "
                    "(tenant_id,project_id,security_scan_run_id,category,scanner_key,"
                    "scanner_version,rule_pack_hash,coverage_status,reported_finding_count,"
                    "evidence_digest) VALUES (:t,:p,:r,:c,:k,:v,:rh,:s,:n,:d) RETURNING id",
                    t=ctx["t1"],
                    p=ctx["p1"],
                    r=run_id,
                    c=category,
                    k=key,
                    v=contract["scanner_version"],
                    rh=contract["rule_pack_hash"],
                    s="completed_with_findings" if category in {"authz", "injection"} else "completed_clean",
                    n=1 if category in {"authz", "injection"} else 0,
                    d=digest,
                )
            for category in ("authz", "injection"):
                key = next(
                    key
                    for key, value in SCANNER_ALLOWLIST.items()
                    if category in value["supported_categories"]
                )
                await conn.execute(
                    text(
                        "INSERT INTO release_findings "
                        "(tenant_id,project_id,finding_type,category,severity,summary,detail,source,"
                        "source_provenance,security_scan_category_result_id,scan_finding_fingerprint) "
                        "VALUES (:t,:p,'security',:c,'high','finding','bounded detail',:s,"
                        "'connector_verified_security_scan',:cr,:fp)"
                    ),
                    {
                        "t": ctx["t1"],
                        "p": ctx["p1"],
                        "c": category,
                        "s": key,
                        "cr": results[category],
                        "fp": "sha256:" + "f" * 64,
                    },
                )
            pytest.fail("duplicate fingerprint was accepted")
        except Exception as exc:
            assert "duplicate fingerprint within scan run" in str(exc)
        finally:
            await transaction.rollback()


@pytest.mark.db
async def test_repository_records_verified_coverage_and_latest_failure_supersedes(
    security_db_ctx, admin_engine
):
    from app.release.scm_connector import FakeSCMConnector
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.repositories.security_scans import SecurityScanRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = security_db_ctx
    tenant = TenantContext(ctx["t1"])
    payload = _valid_payload()
    authz = next(item for item in payload["categories"] if item["category"] == "authz")
    authz["coverage_status"] = "completed_with_findings"
    authz["findings"] = [_finding(severity="high")]
    authz["findings"][0]["summary"] = "SENTINEL_SCAN_SUMMARY"
    authz["findings"][0]["detail"] = "SENTINEL_SCAN_DETAIL /private/path"
    authz["findings"][0]["evidence_ref"] = "https://secret.example/SENTINEL_SCAN_REF"

    async with tenant_scope(tenant) as session:
        await IntakeCategoryRepository(session, tenant).declare(
            project_id=ctx["p1"],
            category="existing_assets_and_repositories",
            actor="coordinator",
            data={"primary_repository": "owner/security-repo", "protected_branch": "main"},
            origin="db-test",
        )
        run = await SecurityScanRepository(session, tenant).execute_ci(
            project_id=ctx["p1"],
            commit_sha=COMMIT_SHA,
            connector=FakeSCMConnector(security_scan_artifact=payload),
            actor="security-runner",
        )
        assert run.coverage_complete is True
        assert run.reported_category_count == 5
        assert run.reported_finding_count == 1

    async with tenant_scope(tenant) as session:
        coverage = await SecurityScanRepository(session, tenant).coverage_for_project(ctx["p1"])
        assert coverage.artifact_trusted is True
        assert coverage.coverage_complete is True
        assert coverage.completed_category_count == 5
        assert coverage.finding_count == 1

    async with admin_engine.begin() as conn:
        stored = await _scalar(
            conn,
            "SELECT count(*) FROM release_findings WHERE project_id=:p "
            "AND source_provenance='connector_verified_security_scan'",
            p=ctx["p1"],
        )
        audit_payload = await _scalar(
            conn,
            "SELECT payload::text FROM audit_logs WHERE action='release.security_scan_observed' "
            "AND tenant_id=:t ORDER BY seq DESC LIMIT 1",
            t=ctx["t1"],
        )
    assert stored == 1
    assert "SENTINEL_SCAN" not in audit_payload
    assert "/private/path" not in audit_payload
    assert "secret.example" not in audit_payload

    async with tenant_scope(tenant) as session:
        failed = await SecurityScanRepository(session, tenant).execute_ci(
            project_id=ctx["p1"],
            commit_sha="b" * 40,
            connector=FakeSCMConnector(),
            actor="security-runner",
        )
        assert failed.execution_status == "failed"

    async with tenant_scope(tenant) as session:
        latest = await SecurityScanRepository(session, tenant).coverage_for_project(ctx["p1"])
        assert latest.run_present is True
        assert latest.artifact_trusted is False
        assert latest.execution_failed is True
        assert latest.coverage_complete is False


@pytest.mark.db
async def test_runtime_rls_hides_security_scan_rows_from_other_tenant(
    security_db_ctx, rls_engine, admin_engine
):
    from app.verify.security_scan import code_owned_manifest_hash

    ctx = security_db_ctx
    async with admin_engine.begin() as conn:
        await conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        await conn.execute(
            text(
                "INSERT INTO security_scan_runs "
                "(tenant_id,project_id,provider,repo_binding_hash,commit_sha,"
                "artifact_schema_version,scanner_manifest_hash,artifact_digest,execution_status,"
                "artifact_provenance,execution_observation,failure_code,reported_category_count,"
                "reported_finding_count,coverage_complete,coverage_verdict) VALUES "
                "(:t,:p,'github',:h,:sha,'slice44.security_scan.v1',:mh,NULL,'failed',"
                "'caller_supplied_unverified','connector_attempted','test_failure',0,0,false,'failed')"
            ),
            {
                "t": ctx["t1"],
                "p": ctx["p1"],
                "h": "sha256:" + "c" * 64,
                "mh": code_owned_manifest_hash(),
                "sha": COMMIT_SHA,
            },
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(ctx["t2"])}
            )
            count = await _scalar(conn, "SELECT count(*) FROM security_scan_runs")
    assert count == 0
