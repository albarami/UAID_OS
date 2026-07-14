from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.release.evidence_pack import (
    INVENTORY_SECTIONS,
    SectionInventory,
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
)


COMMIT_SHA = "a" * 40
TARGET_HASH = "b" * 64
FROM_DIGEST = "c" * 64
TO_DIGEST = "d" * 64
MANIFEST_HASH = "73064081141351425c245a6f8bcbe5c6427f130c9a0bf5f8c0aee991ad0a3e53"


def _phase(
    ordinal: int,
    code: str,
    *,
    expected: str,
    observed: str | None = None,
    status: str = "passed",
) -> dict:
    probe = code.endswith("_probe")
    return {
        "ordinal": ordinal,
        "phase_code": code,
        "phase_status": status,
        "result_code": "healthy"
        if probe and status == "passed"
        else ("operation_complete" if status == "passed" else "operation_failed"),
        "target_binding_hash": TARGET_HASH,
        "expected_version_digest": expected,
        "observed_version_digest": observed if probe else None,
        "health_ok": status == "passed" if probe else None,
        "operation_ok": status == "passed" if not probe else None,
        "started_at": f"2026-07-13T00:0{ordinal}:00Z",
        "completed_at": f"2026-07-13T00:0{ordinal}:30Z",
    }


def _valid_payload() -> dict:
    return {
        "schema_version": "slice52.rollback_drill.v1",
        "commit_sha": COMMIT_SHA,
        "target_binding_hash": TARGET_HASH,
        "from_artifact_digest": FROM_DIGEST,
        "to_artifact_digest": TO_DIGEST,
        "runner_manifest_hash": MANIFEST_HASH,
        "workflow_conclusion": "success",
        "completed_at": "2026-07-13T00:05:30Z",
        "phases": [
            _phase(1, "baseline_a_probe", expected=FROM_DIGEST, observed=FROM_DIGEST),
            _phase(2, "forward_deploy_b", expected=TO_DIGEST),
            _phase(3, "forward_b_probe", expected=TO_DIGEST, observed=TO_DIGEST),
            _phase(4, "rollback_to_a", expected=FROM_DIGEST),
            _phase(5, "post_rollback_a_probe", expected=FROM_DIGEST, observed=FROM_DIGEST),
        ],
    }


def test_five_phase_a_to_b_to_a_artifact_derives_connector_observed_pass():
    from app.release.rollback import validate_rollback_drill_artifact

    artifact = validate_rollback_drill_artifact(_valid_payload(), expected_commit_sha=COMMIT_SHA)

    assert artifact.passed is True
    assert artifact.execution_observation == "connector_observed_ci"
    assert artifact.artifact_provenance == "connector_verified_ci_rollback"
    assert tuple(phase.phase_code for phase in artifact.phases) == (
        "baseline_a_probe",
        "forward_deploy_b",
        "forward_b_probe",
        "rollback_to_a",
        "post_rollback_a_probe",
    )
    assert len(artifact.phase_digest) == 64
    assert len(artifact.artifact_content_hash) == 64


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda p: p["phases"].pop(), "exactly five"),
        (lambda p: p["phases"].reverse(), "phase order"),
        (lambda p: p.update(commit_sha="f" * 40), "commit_sha"),
        (lambda p: p.update(to_artifact_digest=FROM_DIGEST), "must differ"),
        (lambda p: p["phases"][4].update(observed_version_digest=TO_DIGEST), "version"),
        (lambda p: p["phases"][0].update(target_binding_hash="f" * 64), "target"),
        (lambda p: p.update(runner_manifest_hash="f" * 64), "runner manifest"),
        (lambda p: p.update(verified=True), "unknown"),
        (lambda p: p["phases"][0].update(logs="secret"), "unknown"),
    ],
)
def test_rollback_artifact_contract_fails_closed(mutation, message):
    from app.release.rollback import InvalidRollbackArtifact, validate_rollback_drill_artifact

    payload = copy.deepcopy(_valid_payload())
    mutation(payload)

    with pytest.raises(InvalidRollbackArtifact, match=message):
        validate_rollback_drill_artifact(payload, expected_commit_sha=COMMIT_SHA)


def test_valid_negative_artifact_is_preserved_but_never_passes():
    from app.release.rollback import validate_rollback_drill_artifact

    payload = _valid_payload()
    payload["workflow_conclusion"] = "failure"
    payload["phases"][2].update(
        phase_status="failed",
        result_code="unhealthy",
        health_ok=False,
    )
    for phase in payload["phases"][3:]:
        phase.update(
            phase_status="not_run",
            result_code="not_run_after_failure",
            health_ok=None,
            operation_ok=None,
            observed_version_digest=None,
        )

    artifact = validate_rollback_drill_artifact(payload, expected_commit_sha=COMMIT_SHA)

    assert artifact.passed is False
    assert artifact.failed_phase_count == 1
    assert artifact.not_run_phase_count == 2


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["phases"][0].update(completed_at=p["phases"][0]["started_at"]),
        lambda p: p["phases"][1].update(started_at=p["phases"][0]["completed_at"]),
        lambda p: p.update(completed_at=p["phases"][-1]["started_at"]),
        lambda p: p["phases"][0].update(started_at="2026-07-13T00:01:00+00:00"),
    ],
)
def test_rollback_artifact_rejects_reversed_overlapping_or_noncanonical_time(mutation):
    from app.release.rollback import InvalidRollbackArtifact, validate_rollback_drill_artifact

    payload = _valid_payload()
    mutation(payload)
    with pytest.raises(InvalidRollbackArtifact, match="timestamp|ordered|precedes"):
        validate_rollback_drill_artifact(payload, expected_commit_sha=COMMIT_SHA)


def test_staging_projection_is_strict_and_reuses_safe_fqdn_contract():
    from app.release.rollback import validate_staging_target_projection

    projection = validate_staging_target_projection(
        {
            "environments": {
                "staging": {"provider": "generic_https", "domain": "STAGING.Example.COM"}
            }
        }
    )

    assert projection.provider == "generic_https"
    assert projection.domain == "staging.example.com"
    assert len(projection.binding_hash) == 64


@pytest.mark.parametrize(
    "staging",
    [
        {},
        {"provider": "generic_https"},
        {"provider": "unknown", "domain": "staging.example.com"},
        {"provider": "generic_https", "domain": "https://staging.example.com"},
        {"provider": "generic_https", "domain": "127.0.0.1"},
        {"provider": "generic_https", "domain": "service.internal"},
        {"provider": "generic_https", "domain": "staging.example.com", "production": True},
    ],
)
def test_staging_projection_rejects_missing_unsafe_or_unknown_fields(staging):
    from app.release.rollback import InvalidStagingTarget, validate_staging_target_projection

    with pytest.raises(InvalidStagingTarget):
        validate_staging_target_projection({"environments": {"staging": staging}})


def _archive(payload: dict, *, filename: str = "rollback-drill-results.json") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(filename, json.dumps(payload))
    return out.getvalue()


def _raw_archive(raw: bytes, *, filename: str = "rollback-drill-results.json") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, raw)
    return out.getvalue()


def test_rollback_archive_parser_accepts_one_exact_safe_member():
    from app.release.scm_connector import parse_github_rollback_drill_artifact_archive

    artifact = parse_github_rollback_drill_artifact_archive(
        _archive(_valid_payload()), expected_commit_sha=COMMIT_SHA
    )

    assert artifact.passed is True


@pytest.mark.parametrize(
    "archive",
    [
        _archive(_valid_payload(), filename="../rollback-drill-results.json"),
        _archive(_valid_payload(), filename="other.json"),
        b"not-a-zip",
    ],
)
def test_rollback_archive_parser_rejects_unsafe_or_malformed_archives(archive):
    from app.release.scm_connector import (
        SCMConnectorError,
        parse_github_rollback_drill_artifact_archive,
    )

    with pytest.raises(SCMConnectorError):
        parse_github_rollback_drill_artifact_archive(archive, expected_commit_sha=COMMIT_SHA)


@pytest.mark.parametrize(
    "archive",
    [
        _raw_archive(b"\xff\xfe"),
        _raw_archive(json.dumps(_valid_payload()).encode() + b" " * (1024 * 1024)),
        _raw_archive(b"[" * 1100 + b"0" + b"]" * 1100),
    ],
)
def test_rollback_archive_rejects_utf8_compression_bombs_and_excessive_nesting(archive):
    from app.release.scm_connector import (
        SCMConnectorError,
        parse_github_rollback_drill_artifact_archive,
    )

    with pytest.raises(SCMConnectorError):
        parse_github_rollback_drill_artifact_archive(archive, expected_commit_sha=COMMIT_SHA)


def test_rollback_archive_rejects_duplicate_json_keys_and_nonfinite_numbers():
    from app.release.scm_connector import (
        SCMConnectorError,
        parse_github_rollback_drill_artifact_archive,
    )

    valid = json.dumps(_valid_payload()).encode()
    duplicate = valid.replace(
        b'{"schema_version": "slice52.rollback_drill.v1",',
        b'{"schema_version": "wrong", "schema_version": "slice52.rollback_drill.v1",',
        1,
    )
    nonfinite = valid.replace(b'"health_ok": true', b'"health_ok": NaN', 1)
    for raw in (duplicate, nonfinite):
        with pytest.raises(SCMConnectorError):
            parse_github_rollback_drill_artifact_archive(
                _raw_archive(raw), expected_commit_sha=COMMIT_SHA
            )


def test_rollback_archive_rejects_symlink_and_multiple_members():
    from app.release.scm_connector import (
        SCMConnectorError,
        parse_github_rollback_drill_artifact_archive,
    )

    symlink = io.BytesIO()
    with zipfile.ZipFile(symlink, "w") as archive:
        info = zipfile.ZipInfo("rollback-drill-results.json")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        archive.writestr(info, json.dumps(_valid_payload()))
    multiple = io.BytesIO()
    with zipfile.ZipFile(multiple, "w") as archive:
        archive.writestr("rollback-drill-results.json", json.dumps(_valid_payload()))
        archive.writestr("extra.json", "{}")

    for raw in (symlink.getvalue(), multiple.getvalue()):
        with pytest.raises(SCMConnectorError):
            parse_github_rollback_drill_artifact_archive(raw, expected_commit_sha=COMMIT_SHA)


def test_latest_completed_selection_does_not_preserve_older_success():
    from app.release.scm_connector import select_latest_completed_rollback_run

    selected = select_latest_completed_rollback_run(
        [
            {
                "id": 12,
                "head_sha": COMMIT_SHA,
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-07-13T00:01:00Z",
            },
            {
                "id": 11,
                "head_sha": COMMIT_SHA,
                "status": "completed",
                "conclusion": "failure",
                "updated_at": "2026-07-13T00:02:00Z",
            },
            {
                "id": 13,
                "head_sha": "f" * 40,
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-07-13T00:03:00Z",
            },
        ],
        commit_sha=COMMIT_SHA,
    )

    assert selected["id"] == 11
    assert selected["conclusion"] == "failure"


@pytest.mark.asyncio
async def test_fake_scm_connector_validates_rollback_artifact_without_network():
    from app.release.scm_connector import FakeSCMConnector

    artifact = await FakeSCMConnector(
        rollback_drill_artifact=_valid_payload()
    ).fetch_rollback_drill_artifact(repo_ref="owner/repo", commit_sha=COMMIT_SHA)

    assert artifact is not None
    assert artifact.passed is True
    assert artifact.provider_run_ref_hash is not None
    assert len(artifact.provider_run_ref_hash) == 64


def _gate10_kwargs() -> dict:
    return {
        "rollback_scope_resolved": True,
        "rollback_core_present": True,
        "rollback_core_reaudited": True,
        "rollback_repo_binding_agreed": True,
        "rollback_staging_target_valid": True,
        "rollback_staging_snapshot_present": True,
        "rollback_staging_snapshot_available": True,
        "rollback_staging_snapshot_fresh": True,
        "rollback_run_present": True,
        "rollback_attempt_failed": False,
        "rollback_artifact_trusted": True,
        "rollback_binding_current": True,
        "rollback_phase_coverage_complete": True,
        "rollback_evidence_consistent": True,
        "rollback_drill_passed": True,
        "rollback_gate_eligible": True,
        "rollback_phase_count": 5,
        "rollback_execution_observation": "connector_observed_ci",
    }


def test_gate10_passes_only_on_the_exact_connector_observed_state():
    from app.release.production_autonomy import evaluate_production_autonomy

    report = evaluate_production_autonomy(
        "project", readiness_level="R5", **_gate10_kwargs()
    ).to_dict()
    gate = next(item for item in report["gates"] if item["number"] == 10)

    assert gate["status"] == "passed"
    assert gate["reason"] == "passed:connector_observed_staging_rollback_drill_verified"
    assert report["ruleset_version"] == "slice54.v1"
    assert report["can_go_live_autonomously"] is False


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"rollback_scope_resolved": False}, "no_current_frozen_release_candidate"),
        ({"rollback_core_present": False}, "no_complete_reauditable_evidence_core"),
        ({"rollback_core_reaudited": False}, "release_core_reaudit_failed"),
        (
            {"rollback_repo_binding_agreed": False},
            "release_repo_commit_binding_missing_or_disagreed",
        ),
        ({"rollback_staging_target_valid": False}, "staging_target_declaration_missing_or_invalid"),
        (
            {"rollback_staging_snapshot_present": False},
            "no_current_connector_verified_staging_target",
        ),
        ({"rollback_staging_snapshot_available": False}, "staging_target_unavailable_or_stale"),
        ({"rollback_run_present": False}, "rollback_verification_not_run_for_current_binding"),
        ({"rollback_attempt_failed": True}, "latest_rollback_attempt_failed_or_refused"),
        ({"rollback_artifact_trusted": False}, "rollback_artifact_provenance_untrusted"),
        ({"rollback_binding_current": False}, "rollback_binding_stale_or_inconsistent"),
        ({"rollback_phase_coverage_complete": False}, "rollback_phase_coverage_incomplete"),
        ({"rollback_evidence_consistent": False}, "rollback_phase_evidence_inconsistent"),
        ({"rollback_drill_passed": False}, "rollback_drill_failed"),
    ],
)
def test_gate10_ladder_is_fail_closed_and_ordered(updates, reason):
    from app.release.production_autonomy import evaluate_production_autonomy

    kwargs = _gate10_kwargs()
    kwargs.update(updates)
    gate = next(
        item
        for item in evaluate_production_autonomy(
            "project", readiness_level="R5", **kwargs
        ).to_dict()["gates"]
        if item["number"] == 10
    )

    assert gate["status"] == "insufficient_evidence"
    assert gate["reason"] == f"insufficient_evidence:{reason}"


def test_slice52_golden_matrix_changes_only_gate10_and_preserves_no_go_contracts():
    from app.release.production_autonomy import (
        NO_GO_LIVE_REASONS,
        evaluate_production_autonomy,
    )

    before = evaluate_production_autonomy("project", readiness_level="R5").to_dict()
    after = evaluate_production_autonomy(
        "project", readiness_level="R5", **_gate10_kwargs()
    ).to_dict()

    before_gates = {gate["number"]: gate for gate in before["gates"]}
    after_gates = {gate["number"]: gate for gate in after["gates"]}
    assert {number: gate for number, gate in before_gates.items() if number != 10} == {
        number: gate for number, gate in after_gates.items() if number != 10
    }
    assert before_gates[10] != after_gates[10]
    assert NO_GO_LIVE_REASONS == (
        "a5_gates_not_all_satisfied",
    )
    assert before["can_go_live_autonomously"] is after["can_go_live_autonomously"] is False


def test_ruled_byte_stable_files_match_pre_slice52_baseline():
    expected = {
        "app/intake/readiness.py": "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26",
        "docs/UAID_OS_Intake_Template_Pack_v1_2/16_environments_and_deployment_targets.yaml": (
            "0e9a3d69d18fdc415edfa5a9dc0bd6f6efac8db8d29fab5c8601391b608aeecd"
        ),
    }
    for path, digest in expected.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


@pytest.mark.db
async def test_slice52_catalog_rls_privileges_and_preservation_pins(admin_engine):
    tables = {"rollback_verification_runs", "rollback_verification_phase_results"}
    async with admin_engine.connect() as conn:
        present = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                        "AND tablename = ANY(:tables)"
                    ),
                    {"tables": list(tables)},
                )
            ).all()
        }
        assert present == tables
        for table in tables:
            assert (
                await conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname=:table"
                    ),
                    {"table": table},
                )
            ).one() == (True, True)
            grants = {
                row[0]
                for row in (
                    await conn.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:table AND grantee='uaid_app'"
                        ),
                        {"table": table},
                    )
                ).all()
            }
            assert grants == {"SELECT", "INSERT"}
        unique_exists = (
            await conn.execute(
                text("SELECT count(*) FROM pg_constraint WHERE conname='uq_dts_id_project_tenant'")
            )
        ).scalar_one()
        assert unique_exists == 1
        assert (
            await conn.execute(
                text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
            )
        ).scalar_one() == "808036faf2660d6810aeca4342e6f1ac"


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


def _zero_inventories() -> tuple[SectionInventory, ...]:
    digest = digest_bytes(canonical_json_bytes([]))
    return tuple(
        SectionInventory(
            section_code=section,
            presence_code="present_zero_rows",
            item_count=0,
            section_digest=digest,
            required=True,
            failure_code=None,
        )
        for section in INVENTORY_SECTIONS
    )


@pytest_asyncio.fixture
async def rollback_ctx(db_session):
    from app.policy.levels import AutonomyLevel
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.repositories.tools import ToolAllowlistRepository
    from app.tenancy import TenantContext
    from app.verify.security_scan import canonical_digest

    suffix = uuid.uuid4().hex[:10]
    org = await _scalar(
        db_session,
        "INSERT INTO organizations (name,slug) VALUES ('RollbackOrg',:s) RETURNING id",
        s=f"rollback-org-{suffix}",
    )
    tenant = await _scalar(
        db_session,
        "INSERT INTO tenants (organization_id,name,slug) "
        "VALUES (:o,'RollbackTenant',:s) RETURNING id",
        o=org,
        s=f"rollback-tenant-{suffix}",
    )
    project = await _scalar(
        db_session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'RollbackProject',:s) RETURNING id",
        t=tenant,
        s=f"rollback-project-{suffix}",
    )
    candidate = await _scalar(
        db_session,
        "INSERT INTO release_candidates (tenant_id,project_id,release_ref,status) "
        "VALUES (:t,:p,:r,'draft') RETURNING id",
        t=tenant,
        p=project,
        r=f"release-{suffix}",
    )
    frozen_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.execute(
        text("UPDATE release_candidates SET status='frozen',frozen_at=:f WHERE id=:c"),
        {"c": candidate, "f": frozen_at},
    )
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(tenant)}
    )
    await db_session.execute(text("SELECT * FROM audit_append('slice52-test','seed',NULL,'{}')"))
    context = TenantContext(tenant)
    intake = IntakeCategoryRepository(db_session, context)
    await intake.declare(
        project_id=project,
        category="existing_assets_and_repositories",
        actor="slice52-test",
        origin="test",
        data={"primary_repository": "owner/repo", "protected_branch": "main"},
    )
    await intake.declare(
        project_id=project,
        category="environments_and_deployment_targets",
        actor="slice52-test",
        origin="test",
        data={
            "environments": {
                "staging": {"provider": "generic_https", "domain": "staging.example.com"}
            }
        },
    )
    await AutonomyPolicyRepository(db_session, context).upsert(
        project_id=project, autonomy_level=int(AutonomyLevel.A5), actor="slice52-test"
    )
    await ToolAllowlistRepository(db_session, context).grant(
        agent_id="rollback-connector",
        tool_name="deployment.read_target_status",
        actor="slice52-test",
    )
    packs = EvidencePackRepository(db_session, context)
    checkpoint = await packs.record_audit_checkpoint()
    repo_hash = canonical_digest("owner/repo")
    core = assemble_core(
        project_id=project,
        release_candidate_id=candidate,
        release_ref_digest="sha256:" + "1" * 64,
        generated_at=checkpoint.created_at,
        frozen_at=frozen_at,
        artifact_scope_digest="sha256:" + "2" * 64,
        issue_binding_digest=digest_bytes(canonical_json_bytes([])),
        source_refs=(),
        inventories=_zero_inventories(),
        traceability=(),
        audit_checkpoint=checkpoint,
        repo_commit_binding=derive_repo_commit_binding(
            [
                {
                    "truth_tier": "connector_verified_ci",
                    "repo_binding_hash": repo_hash,
                    "commit_sha": COMMIT_SHA,
                }
            ]
        ),
    )
    pack = await packs._persist_core(
        project_id=project,
        release_candidate_id=candidate,
        core=core,
        source_refs=(),
        inventories=_zero_inventories(),
        traceability_edge_count=0,
        actor="slice52-test",
    )
    return {
        "session": db_session,
        "context": context,
        "tenant": tenant,
        "project": project,
        "candidate": candidate,
        "pack": pack,
        "repo_hash": repo_hash,
    }


def _bound_payload() -> dict:
    from app.release.rollback import validate_staging_target_projection

    payload = _valid_payload()
    binding = validate_staging_target_projection(
        {
            "environments": {
                "staging": {"provider": "generic_https", "domain": "staging.example.com"}
            }
        }
    ).binding_hash
    payload["target_binding_hash"] = binding
    for phase in payload["phases"]:
        phase["target_binding_hash"] = binding
    return payload


@pytest.mark.db
async def test_repository_records_exact_pass_and_gate10_coverage(rollback_ctx):
    from app.release.deploy_connector import FakeDeployTargetConnector
    from app.release.scm_connector import FakeSCMConnector
    from app.repositories.rollback_verifications import RollbackVerificationRepository

    ctx = rollback_ctx
    repo = RollbackVerificationRepository(ctx["session"], ctx["context"])
    run = await repo.observe_ci_drill(
        project_id=ctx["project"],
        scm_connector=FakeSCMConnector(rollback_drill_artifact=_bound_payload()),
        deploy_connector=FakeDeployTargetConnector(
            result={
                "reachable": True,
                "provisioned": True,
                "target_available": True,
                "observed_http_status": 200,
            }
        ),
        service_id="rollback-connector",
        actor="slice52-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    assert run.attempt_status == "succeeded"
    assert run.drill_result == "passed"
    assert run.gate_eligible is True
    coverage = await repo.coverage_for_project(ctx["project"])
    assert coverage.run_present is True
    assert coverage.phase_count == 5
    assert coverage.gate_eligible is True


async def _observe_bound_drill(ctx, payload: dict):
    from app.release.deploy_connector import FakeDeployTargetConnector
    from app.release.scm_connector import FakeSCMConnector
    from app.repositories.rollback_verifications import RollbackVerificationRepository

    return await RollbackVerificationRepository(ctx["session"], ctx["context"]).observe_ci_drill(
        project_id=ctx["project"],
        scm_connector=FakeSCMConnector(rollback_drill_artifact=payload),
        deploy_connector=FakeDeployTargetConnector(
            result={
                "reachable": True,
                "provisioned": True,
                "target_available": True,
                "observed_http_status": 200,
            }
        ),
        service_id="rollback-connector",
        actor="slice52-test",
    )


_COPIED_RUN_INSERT_SQL = (
    "INSERT INTO rollback_verification_runs "
    "(id,tenant_id,project_id,release_candidate_id,evidence_pack_id,"
    "staging_target_snapshot_id,drill_contract_version,verification_contract_version,"
    "staging_target_contract_version,artifact_provenance,execution_observation,"
    "repo_binding_hash,commit_sha,core_content_hash,artifact_scope_digest,"
    "issue_binding_digest,source_set_digest,traceability_digest,"
    "staging_target_binding_hash,staging_snapshot_digest,from_artifact_digest,"
    "to_artifact_digest,runner_manifest_hash,provider_run_ref_hash,artifact_content_hash,workflow_conclusion,"
    "attempt_status,reason_code,phase_count,phase_digest,drill_result,evidence_consistent,"
    "gate_eligible,scope_limitation_code,artifact_completed_at) "
    "SELECT :new_id,tenant_id,project_id,release_candidate_id,evidence_pack_id,"
    "staging_target_snapshot_id,drill_contract_version,verification_contract_version,"
    "staging_target_contract_version,artifact_provenance,execution_observation,"
    "repo_binding_hash,commit_sha,core_content_hash,artifact_scope_digest,"
    "issue_binding_digest,source_set_digest,traceability_digest,"
    "staging_target_binding_hash,staging_snapshot_digest,from_artifact_digest,"
    "to_artifact_digest,runner_manifest_hash,provider_run_ref_hash,artifact_content_hash,workflow_conclusion,"
    "attempt_status,reason_code,phase_count,phase_digest,drill_result,evidence_consistent,"
    "gate_eligible,scope_limitation_code,artifact_completed_at "
    "FROM rollback_verification_runs WHERE id=:old_id"
)


@pytest.mark.db
async def test_valid_negative_artifact_supersedes_older_pass(rollback_ctx):
    from app.repositories.rollback_verifications import RollbackVerificationRepository

    ctx = rollback_ctx
    passed = await _observe_bound_drill(ctx, _bound_payload())
    negative = _bound_payload()
    negative["workflow_conclusion"] = "failure"
    negative["phases"][2].update(
        phase_status="failed",
        result_code="unhealthy",
        health_ok=False,
    )
    for phase in negative["phases"][3:]:
        phase.update(
            phase_status="not_run",
            result_code="not_run_after_failure",
            health_ok=None,
            operation_ok=None,
            observed_version_digest=None,
        )
    failed = await _observe_bound_drill(ctx, negative)
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    coverage = await RollbackVerificationRepository(
        ctx["session"], ctx["context"]
    ).coverage_for_project(ctx["project"])
    assert passed.gate_eligible is True
    assert failed.attempt_status == "succeeded"
    assert failed.drill_result == "failed"
    assert failed.gate_eligible is False
    assert coverage.run_present is True
    assert coverage.drill_passed is False
    assert coverage.gate_eligible is False


@pytest.mark.db
async def test_direct_sql_cannot_forge_gate_truth_or_mutate_history(rollback_ctx):
    ctx = rollback_ctx
    run = await _observe_bound_drill(ctx, _bound_payload())
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    forged_id = uuid.uuid4()

    with pytest.raises(DBAPIError) as rejected:
        async with ctx["session"].begin_nested():
            await ctx["session"].execute(text("SET CONSTRAINTS ALL DEFERRED"))
            await ctx["session"].execute(
                text(
                    "INSERT INTO rollback_verification_runs "
                    "(id,tenant_id,project_id,release_candidate_id,evidence_pack_id,"
                    "staging_target_snapshot_id,drill_contract_version,verification_contract_version,"
                    "staging_target_contract_version,artifact_provenance,execution_observation,"
                    "repo_binding_hash,commit_sha,core_content_hash,artifact_scope_digest,"
                    "issue_binding_digest,source_set_digest,traceability_digest,"
                    "staging_target_binding_hash,staging_snapshot_digest,from_artifact_digest,"
                    "to_artifact_digest,runner_manifest_hash,provider_run_ref_hash,artifact_content_hash,workflow_conclusion,"
                    "attempt_status,reason_code,phase_count,phase_digest,drill_result,"
                    "evidence_consistent,gate_eligible,scope_limitation_code,artifact_completed_at) "
                    "SELECT :new_id,tenant_id,project_id,release_candidate_id,evidence_pack_id,"
                    "staging_target_snapshot_id,drill_contract_version,verification_contract_version,"
                    "staging_target_contract_version,artifact_provenance,execution_observation,"
                    "repo_binding_hash,commit_sha,core_content_hash,artifact_scope_digest,"
                    "issue_binding_digest,source_set_digest,traceability_digest,"
                    "staging_target_binding_hash,staging_snapshot_digest,from_artifact_digest,"
                    "to_artifact_digest,runner_manifest_hash,provider_run_ref_hash,artifact_content_hash,workflow_conclusion,"
                    "attempt_status,reason_code,phase_count,phase_digest,drill_result,"
                    "evidence_consistent,false,scope_limitation_code,artifact_completed_at "
                    "FROM rollback_verification_runs WHERE id=:old_id"
                ),
                {"new_id": forged_id, "old_id": run.id},
            )
            await ctx["session"].execute(
                text(
                    "INSERT INTO rollback_verification_phase_results "
                    "(tenant_id,project_id,run_id,ordinal,phase_code,phase_status,result_code,"
                    "target_binding_hash,expected_version_digest,observed_version_digest,health_ok,"
                    "operation_ok,started_at,completed_at) "
                    "SELECT tenant_id,project_id,:new_id,ordinal,phase_code,phase_status,result_code,"
                    "target_binding_hash,expected_version_digest,observed_version_digest,health_ok,"
                    "operation_ok,started_at,completed_at "
                    "FROM rollback_verification_phase_results WHERE run_id=:old_id"
                ),
                {"new_id": forged_id, "old_id": run.id},
            )
            await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert "rollback" in str(rejected.value).lower()
    assert (
        await _scalar(
            ctx["session"],
            "SELECT count(*) FROM rollback_verification_runs WHERE id=:id",
            id=forged_id,
        )
        == 0
    )

    with pytest.raises(DBAPIError):
        async with ctx["session"].begin_nested():
            await ctx["session"].execute(
                text("UPDATE rollback_verification_runs SET gate_eligible=false WHERE id=:id"),
                {"id": run.id},
            )


@pytest.mark.db
async def test_direct_sql_rejects_forged_or_incomplete_phase_sets(rollback_ctx):
    ctx = rollback_ctx
    run = await _observe_bound_drill(ctx, _bound_payload())
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    forged_phase_parent = uuid.uuid4()
    with pytest.raises(DBAPIError) as forged_phase:
        async with ctx["session"].begin_nested():
            await ctx["session"].execute(text("SET CONSTRAINTS ALL DEFERRED"))
            await ctx["session"].execute(
                text(_COPIED_RUN_INSERT_SQL),
                {"new_id": forged_phase_parent, "old_id": run.id},
            )
            await ctx["session"].execute(
                text(
                    "INSERT INTO rollback_verification_phase_results "
                    "(tenant_id,project_id,run_id,ordinal,phase_code,phase_status,result_code,"
                    "target_binding_hash,expected_version_digest,observed_version_digest,health_ok,"
                    "operation_ok,started_at,completed_at) "
                    "SELECT tenant_id,project_id,:new_id,ordinal,phase_code,phase_status,result_code,"
                    ":forged_target,expected_version_digest,observed_version_digest,health_ok,"
                    "operation_ok,started_at,completed_at "
                    "FROM rollback_verification_phase_results WHERE run_id=:old_id AND ordinal=1"
                ),
                {
                    "new_id": forged_phase_parent,
                    "old_id": run.id,
                    "forged_target": "f" * 64,
                },
            )
    assert "rollback phase" in str(forged_phase.value).lower()

    incomplete_parent = uuid.uuid4()
    with pytest.raises(DBAPIError) as incomplete:
        async with ctx["session"].begin_nested():
            await ctx["session"].execute(text("SET CONSTRAINTS ALL DEFERRED"))
            await ctx["session"].execute(
                text(_COPIED_RUN_INSERT_SQL),
                {"new_id": incomplete_parent, "old_id": run.id},
            )
            await ctx["session"].execute(
                text(
                    "INSERT INTO rollback_verification_phase_results "
                    "(tenant_id,project_id,run_id,ordinal,phase_code,phase_status,result_code,"
                    "target_binding_hash,expected_version_digest,observed_version_digest,health_ok,"
                    "operation_ok,started_at,completed_at) "
                    "SELECT tenant_id,project_id,:new_id,ordinal,phase_code,phase_status,result_code,"
                    "target_binding_hash,expected_version_digest,observed_version_digest,health_ok,"
                    "operation_ok,started_at,completed_at "
                    "FROM rollback_verification_phase_results WHERE run_id=:old_id AND ordinal<5"
                ),
                {"new_id": incomplete_parent, "old_id": run.id},
            )
            await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert "phase child set is incomplete" in str(incomplete.value).lower()


@pytest.mark.db
async def test_production_snapshot_cannot_bind_to_rollback_run(rollback_ctx):
    from app.repositories.deployments import DeploymentTargetRepository

    ctx = rollback_ctx
    run = await _observe_bound_drill(ctx, _bound_payload())
    production = await DeploymentTargetRepository(
        ctx["session"], ctx["context"]
    ).record_connector_verified_deployment_target(
        project_id=ctx["project"],
        payload={
            "provider": "generic_https",
            "environment": "production",
            "target_ref": "production.example.com",
            "reachable": True,
            "provisioned": True,
            "target_available": True,
            "observed_http_status": 200,
            "observed_at": datetime.now(timezone.utc),
        },
        actor="slice52-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    with pytest.raises(DBAPIError) as rejected:
        async with ctx["session"].begin_nested():
            await ctx["session"].execute(
                text(
                    "INSERT INTO rollback_verification_runs "
                    "(tenant_id,project_id,release_candidate_id,evidence_pack_id,"
                    "staging_target_snapshot_id,drill_contract_version,verification_contract_version,"
                    "staging_target_contract_version,artifact_provenance,execution_observation,"
                    "repo_binding_hash,commit_sha,core_content_hash,artifact_scope_digest,"
                    "issue_binding_digest,source_set_digest,traceability_digest,"
                    "staging_target_binding_hash,staging_snapshot_digest,from_artifact_digest,"
                    "to_artifact_digest,runner_manifest_hash,provider_run_ref_hash,artifact_content_hash,workflow_conclusion,"
                    "attempt_status,reason_code,phase_count,phase_digest,drill_result,"
                    "evidence_consistent,gate_eligible,scope_limitation_code,artifact_completed_at) "
                    "SELECT tenant_id,project_id,release_candidate_id,evidence_pack_id,:snapshot,"
                    "drill_contract_version,verification_contract_version,staging_target_contract_version,"
                    "artifact_provenance,execution_observation,repo_binding_hash,commit_sha,"
                    "core_content_hash,artifact_scope_digest,issue_binding_digest,source_set_digest,"
                    "traceability_digest,staging_target_binding_hash,staging_snapshot_digest,"
                    "from_artifact_digest,to_artifact_digest,runner_manifest_hash,provider_run_ref_hash,artifact_content_hash,"
                    "workflow_conclusion,attempt_status,reason_code,phase_count,phase_digest,"
                    "drill_result,evidence_consistent,gate_eligible,scope_limitation_code,"
                    "artifact_completed_at FROM rollback_verification_runs WHERE id=:id"
                ),
                {"snapshot": production.id, "id": run.id},
            )
    assert "staging" in str(rejected.value).lower()


@pytest.mark.db
async def test_rollback_audit_and_a5_context_are_safe_and_gate2_is_unchanged(rollback_ctx):
    from app.release.deploy_connector import FakeDeployTargetConnector
    from app.release.scm_connector import FakeSCMConnector, SCMConnectorError
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.rollback_verifications import RollbackVerificationRepository

    ctx = rollback_ctx
    await _observe_bound_drill(ctx, _bound_payload())
    await RollbackVerificationRepository(ctx["session"], ctx["context"]).observe_ci_drill(
        project_id=ctx["project"],
        scm_connector=FakeSCMConnector(
            error=SCMConnectorError("SENTINEL_SECRET_PROSE staging.example.com owner/repo")
        ),
        deploy_connector=None,
        service_id="rollback-connector",
        actor="slice52-test",
    )
    await RollbackVerificationRepository(ctx["session"], ctx["context"]).observe_ci_drill(
        project_id=ctx["project"],
        scm_connector=FakeSCMConnector(rollback_drill_artifact=_bound_payload()),
        deploy_connector=FakeDeployTargetConnector(
            error=RuntimeError("SENTINEL_DEPLOY_EXCEPTION_SECRET")
        ),
        service_id="rollback-connector",
        actor="slice52-test",
    )
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    report = (
        await ProductionAutonomyRepository(ctx["session"], ctx["context"]).evaluate(ctx["project"])
    ).to_dict()
    gate2 = next(gate for gate in report["gates"] if gate["number"] == 2)
    gate10 = next(gate for gate in report["gates"] if gate["number"] == 10)
    audit_text = await _scalar(
        ctx["session"],
        "SELECT COALESCE(string_agg(payload::text,' '),'') FROM audit_logs "
        "WHERE action IN ('release.rollback_drill_observed','deploy.target_fetch_failed')",
    )
    encoded_context = json.dumps(gate10["context"], sort_keys=True)

    assert gate2["reason"] == "no_environment_declaration"
    assert gate10["reason"] == "insufficient_evidence:latest_rollback_attempt_failed_or_refused"
    assert report["can_go_live_autonomously"] is False
    for forbidden in (
        "SENTINEL_SECRET_PROSE",
        "SENTINEL_DEPLOY_EXCEPTION_SECRET",
        "staging.example.com",
        "owner/repo",
        COMMIT_SHA,
        FROM_DIGEST,
        TO_DIGEST,
    ):
        assert forbidden not in audit_text
        assert forbidden not in encoded_context


@pytest.mark.db
async def test_rollback_rows_do_not_leak_across_tenants(rollback_ctx):
    ctx = rollback_ctx
    await _observe_bound_drill(ctx, _bound_payload())
    await ctx["session"].execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    other_tenant = uuid.uuid4()
    await ctx["session"].execute(text("SET LOCAL ROLE uaid_app"))
    await ctx["session"].execute(
        text("SELECT set_config('app.current_tenant',:t,true)"),
        {"t": str(other_tenant)},
    )
    assert await _scalar(ctx["session"], "SELECT count(*) FROM rollback_verification_runs") == 0
    assert (
        await _scalar(ctx["session"], "SELECT count(*) FROM rollback_verification_phase_results")
        == 0
    )
    await ctx["session"].execute(text("RESET ROLE"))
    await ctx["session"].execute(
        text("SELECT set_config('app.current_tenant',:t,true)"),
        {"t": str(ctx["tenant"])},
    )
