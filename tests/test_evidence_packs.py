"""Slice 49 evidence-pack contract tests.

Pure tests run without Docker. DB-backed catalog, RLS, append-only, checkpoint,
and repository tests are marked below as the migration/repository lands.
"""

from __future__ import annotations

import json
import asyncio
import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.release.evidence_export import (
    CanonicalExportUnavailable,
    ReleaseVerdictAttestation,
    build_canonical_export,
    build_core_preview,
    build_markdown_export,
    build_unsigned_manifest,
)
from app.release.evidence_pack import (
    CANONICAL_SCHEMA_VERSION,
    EVIDENCE_PACK_CONTRACT_VERSION,
    INVENTORY_SECTIONS,
    PROJECTION_CONTRACT_VERSION,
    AuditCheckpointRef,
    EvidencePackContractError,
    EvidenceSourceRef,
    SectionInventory,
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
    validate_canonical_payload,
    validate_semantic_payload,
    project_source_record,
)
from app.release.release_manager import VERDICT_CONTRACT_HASH


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
COMMIT_A = "a" * 40


def _checkpoint() -> AuditCheckpointRef:
    return AuditCheckpointRef(
        id=uuid.UUID("49000000-0000-4000-8000-000000000049"),
        verification_ok=True,
        verified_through_seq=12,
        verified_through_entry_hash="a" * 64,
        verifier_contract_version="slice49.evidence_audit.v1",
        verifier_contract_hash=SHA_B,
        created_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
    )


def _source(kind: str = "test_oracle_run") -> EvidenceSourceRef:
    return EvidenceSourceRef(
        source_kind=kind,
        source_id=uuid.uuid5(uuid.NAMESPACE_URL, kind),
        truth_tier="system_executed",
        source_created_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
        projection={
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, kind)),
            "execution_status": "succeeded",
            "verdict": "passed",
            "commit_sha": COMMIT_A,
            "repo_binding_hash": SHA_A,
        },
    )


def _inventories(*, missing: str | None = None) -> tuple[SectionInventory, ...]:
    return tuple(
        SectionInventory(
            section_code=section,
            presence_code=("missing_required_source" if section == missing else "present_zero_rows"),
            item_count=0,
            section_digest=digest_bytes(canonical_json_bytes([])),
            required=True,
            failure_code=("missing_required_source" if section == missing else None),
        )
        for section in INVENTORY_SECTIONS
    )


def _core(*, missing: str | None = None):
    project_id = uuid.UUID("49000000-0000-4000-8000-000000000001")
    release_id = uuid.UUID("49000000-0000-4000-8000-000000000002")
    return assemble_core(
        project_id=project_id,
        release_candidate_id=release_id,
        release_ref_digest=SHA_A,
        generated_at=datetime(2026, 7, 13, 10, 30, tzinfo=timezone.utc),
        frozen_at=datetime(2026, 7, 12, 10, 30, tzinfo=timezone.utc),
        artifact_scope_digest=SHA_A,
        issue_binding_digest=SHA_B,
        source_refs=(_source(),),
        inventories=_inventories(missing=missing),
        traceability=(),
        audit_checkpoint=_checkpoint(),
        repo_commit_binding=derive_repo_commit_binding(
            [
                {
                    "repo_binding_hash": SHA_A,
                    "commit_sha": COMMIT_A,
                    "truth_tier": "connector_verified_ci",
                }
            ]
        ),
    )


def test_direct_jsonschema_dependency_and_canonical_asset_are_fixed() -> None:
    pyproject = open("pyproject.toml", encoding="utf-8").read()
    assert '"jsonschema' in pyproject
    assert CANONICAL_SCHEMA_VERSION == "uaid.evidence_pack.v1.2"
    assert EVIDENCE_PACK_CONTRACT_VERSION == "slice49.evidence_pack.v1"
    assert PROJECTION_CONTRACT_VERSION == "slice49.evidence_projection.v1"


def test_canonical_bytes_are_exact_sorted_compact_utf8_and_hashed() -> None:
    payload = {"z": "سلام", "a": [2, 1]}
    exact = canonical_json_bytes(payload)
    assert exact == b'{"a":[2,1],"z":"\xd8\xb3\xd9\x84\xd8\xa7\xd9\x85"}'
    assert digest_bytes(exact).startswith("sha256:")
    assert digest_bytes(exact) == digest_bytes(canonical_json_bytes(payload))


def test_semantic_contract_rejects_unknown_and_caller_truth_fields() -> None:
    core = _core().payload
    validate_semantic_payload(core, canonical_export=False)
    for field in ("unknown", "complete", "verified", "passed", "trusted", "signed", "gate"):
        attacked = dict(core)
        attacked[field] = True
        with pytest.raises(EvidencePackContractError, match="field_not_allowed"):
            validate_semantic_payload(attacked, canonical_export=False)
    nested = json.loads(_core().canonical_text)
    nested["source_refs"][0]["projection"]["summary"] = "SENTINEL_SECRET_PROSE"
    with pytest.raises(EvidencePackContractError, match="projection_field_not_allowed"):
        validate_semantic_payload(nested, canonical_export=False)


def test_schema_format_checking_rejects_malformed_generated_at() -> None:
    core = _core()
    final = dict(core.payload)
    final["assurance_limitations"] = [
        "assembled_evidence_does_not_prove_release_readiness",
        "candidate_has_no_direct_commit_foreign_key",
        "issue_bindings_do_not_prove_issue_completeness",
        "release_verdict_bounded_known_issue_disposition_not_go_live_authorization",
        "signer_tier_deferred_to_slice_60",
    ]
    final.update(
        {
            "verdict": "blocked",
            "verdict_attestation": {
                "id": str(uuid.uuid4()),
                "evidence_pack_id": str(uuid.uuid4()),
                "spec_verdict": "requires_human_decision",
                "canonical_verdict": "blocked",
                "reason_code": "risk_acceptance_authority_unverified",
                "decision_scope": "known_bound_issue_disposition",
                "attestation_provenance": "system_derived_release_verdict",
                "verdict_contract_version": "slice50.release_verdict.v1",
                "projection_contract_version": "slice50.verdict_projection.v1",
                "verdict_contract_hash": VERDICT_CONTRACT_HASH,
                "input_digest": SHA_B,
                "core_content_hash": core.content_hash,
                "created_at": "2026-07-13T12:00:00Z",
            },
            "signatures": [],
            "signature_status": "unsigned_signer_tier_not_implemented",
        }
    )
    validate_canonical_payload(final)
    mismatched_projection = dict(final)
    mismatched_projection["verdict"] = "failed"
    mismatched_projection["verdict_attestation"] = {
        **final["verdict_attestation"],
        "canonical_verdict": "failed",
    }
    with pytest.raises(EvidencePackContractError, match="verdict_projection_invalid"):
        validate_canonical_payload(mismatched_projection)
    final["generated_at"] = "not-a-date"
    with pytest.raises(EvidencePackContractError, match="canonical_schema_invalid"):
        validate_canonical_payload(final)


def test_repo_commit_binding_is_consensus_missing_or_disagreement() -> None:
    agreed = derive_repo_commit_binding(
        [
            {
                "repo_binding_hash": SHA_A,
                "commit_sha": COMMIT_A,
                "truth_tier": "connector_verified_ci_security",
            },
            {
                "repo_binding_hash": SHA_A,
                "commit_sha": COMMIT_A,
                "truth_tier": "connector_verified_ci_shortcut_corpus",
            },
        ]
    )
    assert (agreed.state, agreed.repo_binding_hash, agreed.commit_sha) == (
        "agreed",
        SHA_A,
        COMMIT_A,
    )
    assert derive_repo_commit_binding([]).state == "missing_trusted_binding"
    disagreement = derive_repo_commit_binding(
        [
            {"repo_binding_hash": SHA_A, "commit_sha": COMMIT_A, "truth_tier": "connector_verified_ci"},
            {"repo_binding_hash": SHA_B, "commit_sha": "b" * 40, "truth_tier": "connector_verified_ci"},
        ]
    )
    assert disagreement.state == "trusted_binding_disagreement"
    assert disagreement.repo_binding_hash is None
    assert disagreement.commit_sha is None


def test_source_projection_rejects_prose_secret_and_unknown_keys() -> None:
    source = _source()
    assert "verdict" in source.projection
    for prohibited in ("summary", "detail", "prompt", "response", "secret", "raw_json", "url"):
        with pytest.raises(EvidencePackContractError, match="projection_field_not_allowed"):
            EvidenceSourceRef(
                source_kind=source.source_kind,
                source_id=source.source_id,
                truth_tier=source.truth_tier,
                source_created_at=source.source_created_at,
                projection={**source.projection, prohibited: "SENTINEL_SECRET_PROSE"},
            )


def test_core_is_immutable_exact_bytes_and_missing_required_stays_explicit() -> None:
    complete = _core()
    assert complete.assembly_status == "complete"
    assert complete.content_hash == digest_bytes(complete.canonical_text.encode("utf-8"))
    assert "verdict" not in complete.payload
    assert "signatures" not in complete.payload
    incomplete = _core(missing="test_oracles")
    assert incomplete.assembly_status == "incomplete"
    inv = {row["section_code"]: row for row in incomplete.payload["source_inventory"]}
    assert inv["test_oracles"]["presence_code"] == "missing_required_source"


def test_preview_is_labelled_and_canonical_export_refuses_without_real_verdict() -> None:
    core = _core()
    preview = build_core_preview(core)
    assert preview.file_name == "evidence_pack_core.preview.json"
    assert json.loads(preview.content)["export_kind"] == "not_canonical_export"
    with pytest.raises(CanonicalExportUnavailable, match="real_verdict_attestation_required"):
        build_canonical_export(core, verdict_attestation=None)


def test_caller_shaped_future_verdict_cannot_unlock_canonical_export() -> None:
    core = _core()
    attestation = ReleaseVerdictAttestation(
        id=uuid.UUID("50000000-0000-4000-8000-000000000001"),
        evidence_pack_id=uuid.UUID("49000000-0000-4000-8000-000000000099"),
        verdict="blocked",
        attestation_provenance="db_verified_release_verdict",
        created_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    with pytest.raises(
        CanonicalExportUnavailable,
        match="db_bound_slice50_verdict_store_not_implemented",
    ):
        build_canonical_export(core, verdict_attestation=attestation)


def test_markdown_and_unsigned_manifest_are_deterministic_and_safe() -> None:
    core = _core()
    preview = build_core_preview(core)
    first = build_markdown_export(core)
    second = build_markdown_export(core)
    assert first == second
    assert b"not_canonical_export" in first.content
    assert b"SENTINEL_SECRET_PROSE" not in first.content
    manifest = build_unsigned_manifest(preview)
    parsed = json.loads(manifest.content)
    assert parsed["signature_status"] == "unsigned_signer_tier_not_implemented"
    assert parsed["files"][0]["sha256"] == digest_bytes(preview.content)
    assert not any("signature_bytes" in key for key in parsed)


def test_frozen_a5_readiness_and_schema_assets_remain_byte_stable() -> None:
    expected = {
        "app/release/production_autonomy.py": (
                "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
        ),
        "app/intake/readiness.py": (
            "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26"
        ),
        "docs/UAID_OS_Intake_Template_Pack_v1_2/schemas/evidence_pack_schema.json": (
            "48ae2621b39221d4a08f3b982ead9f3ca0589326e59e146fb78e715ab5155feb"
        ),
    }
    for path, digest in expected.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest

    from app.release.production_autonomy import evaluate_production_autonomy

    before = evaluate_production_autonomy(str(uuid.uuid4()), readiness_level="R5").to_dict()
    after = evaluate_production_autonomy(str(uuid.uuid4()), readiness_level="R5").to_dict()
    before.pop("project_id")
    after.pop("project_id")
    assert before == after
    assert before["ruleset_version"] == "slice54.v1"
    assert before["can_go_live_autonomously"] is False


def test_reviewer_quality_projection_keeps_generated_metrics_and_drops_raw_material() -> None:
    row_id = uuid.uuid4()
    row = SimpleNamespace(
        id=row_id,
        created_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        reviewer_instance_id=uuid.uuid4(),
        reviewer_version_hash=SHA_A,
        model_route_hash=SHA_B,
        prompt_hash=SHA_A,
        fixture_suite_hash=SHA_B,
        schema_version="slice48.reviewer_qa.v1",
        qa_contract_hash=SHA_A,
        policy_digest=SHA_B,
        execution_status="succeeded",
        execution_provenance="system_executed_reviewer_qa",
        failure_code=None,
        case_count=46,
        critical_miss_rate=Decimal("0"),
        false_approval_rate=Decimal("0"),
        quality_status="challenge_qualified",
        prescribed_decision="none",
        coverage_complete=True,
        next_calibration_due=datetime(2026, 8, 12, tzinfo=timezone.utc),
        raw_fixture_body="SENTINEL_SECRET_PROSE",
        raw_prompt="SENTINEL_SECRET_PROSE",
        raw_response="SENTINEL_SECRET_PROSE",
    )
    projected = project_source_record("reviewer_quality_record", row)
    encoded = canonical_json_bytes(projected.as_dict())
    assert projected.truth_tier == "system_executed_reviewer_qa"
    assert projected.projection["quality_status"] == "challenge_qualified"
    assert b"SENTINEL_SECRET_PROSE" not in encoded
    assert b"raw_fixture_body" not in encoded


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def evidence_pack_ctx(db_session):
    suffix = uuid.uuid4().hex[:10]
    org = await _scalar(
        db_session,
        "INSERT INTO organizations (name,slug) VALUES ('EvidenceOrg',:s) RETURNING id",
        s=f"evidence-org-{suffix}",
    )
    tenant = await _scalar(
        db_session,
        "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'EvidenceTenant',:s) "
        "RETURNING id",
        o=org,
        s=f"evidence-tenant-{suffix}",
    )
    project = await _scalar(
        db_session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'EvidenceProject',:s) "
        "RETURNING id",
        t=tenant,
        s=f"evidence-project-{suffix}",
    )
    candidate = await _scalar(
        db_session,
        "INSERT INTO release_candidates (tenant_id,project_id,release_ref,status) "
        "VALUES (:t,:p,:r,'draft') RETURNING id",
        t=tenant,
        p=project,
        r=f"release-{suffix}",
    )
    await db_session.execute(
        text(
            "UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() "
            "WHERE id=:c"
        ),
        {"c": candidate},
    )
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"),
        {"t": str(tenant)},
    )
    await db_session.execute(
        text("SELECT * FROM audit_append('slice49-test','seed',NULL,'{}'::jsonb)")
    )
    frozen_at = await _scalar(
        db_session,
        "SELECT frozen_at FROM release_candidates WHERE id=:c",
        c=candidate,
    )
    return {
        "tenant": tenant,
        "project": project,
        "candidate": candidate,
        "frozen_at": frozen_at,
    }


def _db_core(ctx, checkpoint):
    return assemble_core(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        release_ref_digest=SHA_A,
        generated_at=checkpoint.created_at,
        frozen_at=ctx["frozen_at"],
        artifact_scope_digest=SHA_A,
        issue_binding_digest=SHA_B,
        source_refs=(),
        inventories=_inventories(),
        traceability=(),
        audit_checkpoint=checkpoint,
        repo_commit_binding=derive_repo_commit_binding([]),
    )


@pytest.mark.db
async def test_evidence_pack_catalog_rls_privileges_and_preservation_pins(admin_engine):
    async with admin_engine.connect() as conn:
        tables = {
            "audit_chain_verifications",
            "evidence_pack_generation_runs",
            "evidence_packs",
            "evidence_pack_source_refs",
            "evidence_pack_section_results",
        }
        present = set(
            (
                await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                        "AND tablename = ANY(:tables)"
                    ),
                    {"tables": list(tables)},
                )
            ).scalars()
        )
        assert present == tables
        rls = (
            await conn.execute(
                text(
                    "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                    "WHERE relname LIKE 'evidence_pack%' ORDER BY relname"
                )
            )
        ).all()
        assert rls == [
            ("evidence_pack_generation_runs", True, True),
            ("evidence_pack_section_results", True, True),
            ("evidence_pack_source_refs", True, True),
            ("evidence_packs", True, True),
        ]
        assert await _scalar(
            conn,
            "SELECT has_table_privilege('uaid_app','audit_chain_verifications','INSERT')",
        ) is False
        assert await _scalar(
            conn,
            "SELECT has_table_privilege('uaid_app','audit_chain_verifications','SELECT')",
        ) is True
        assert await _scalar(
            conn,
            "SELECT has_function_privilege('uaid_app','audit_verify()','EXECUTE')",
        ) is False
        assert await _scalar(
            conn,
            "SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))",
        ) == "808036faf2660d6810aeca4342e6f1ac"


@pytest.mark.db
async def test_admin_checkpoint_uses_real_verifier_and_runtime_cannot_forge(
    evidence_pack_ctx, db_session
):
    from app.repositories.evidence_packs import record_audit_chain_verification

    checkpoint = await record_audit_chain_verification(db_session)
    assert checkpoint.verification_ok is True
    assert checkpoint.first_bad_seq is None
    assert checkpoint.verified_through_seq >= 1
    assert len(checkpoint.verified_through_entry_hash) == 64
    assert await _scalar(
        db_session,
        "SELECT count(*) FROM audit_chain_verifications WHERE id=:i",
        i=checkpoint.id,
    ) == 1


@pytest.mark.db
async def test_repository_persists_exact_core_and_reaudits_every_export(
    evidence_pack_ctx, db_session
):
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.tenancy import TenantContext

    ctx = evidence_pack_ctx
    repo = EvidencePackRepository(db_session, TenantContext(ctx["tenant"]))
    checkpoint = await repo.record_audit_checkpoint()
    core = _db_core(ctx, checkpoint)
    pack = await repo._persist_core(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        core=core,
        source_refs=(),
        inventories=_inventories(),
        traceability_edge_count=0,
        actor="slice49-test",
    )
    await db_session.flush()
    assert pack.canonical_core_text == core.canonical_text
    assert pack.core_content_hash == core.content_hash
    assert pack.verdict_status == "absent_deferred_slice50"
    assert pack.signature_status == "unsigned_signer_tier_not_implemented"
    history = await repo.get_history(ctx["candidate"])
    assert len(history) == 1
    assert history[0]["id"] == str(pack.id)
    assert "canonical_core_text" not in history[0]
    latest = await repo.get_latest_exact_binding(
        release_candidate_id=ctx["candidate"],
        audit_checkpoint_id=checkpoint.id,
        artifact_scope_digest=pack.artifact_scope_digest,
        issue_binding_digest=pack.issue_binding_digest,
        source_set_digest=pack.source_set_digest,
    )
    assert latest is not None and latest["id"] == str(pack.id)
    assert (
        await repo.get_latest_exact_binding(
            release_candidate_id=ctx["candidate"],
            audit_checkpoint_id=checkpoint.id,
            artifact_scope_digest=pack.artifact_scope_digest,
            issue_binding_digest=pack.issue_binding_digest,
            source_set_digest="sha256:" + "f" * 64,
        )
        is None
    )
    assert await repo.audit_pack(pack.id) == core
    preview = await repo.export_core_preview(pack.id, actor="slice49-test")
    assert json.loads(preview.content)["export_kind"] == "not_canonical_export"
    markdown = await repo.export_markdown(pack.id, actor="slice49-test")
    assert b"not_canonical_export" in markdown.content
    manifest = await repo.export_unsigned_manifest(pack.id, actor="slice49-test")
    assert json.loads(manifest.content)["signature_status"] == (
        "unsigned_signer_tier_not_implemented"
    )
    with pytest.raises(CanonicalExportUnavailable, match="real_verdict_attestation_required"):
        await repo.export_canonical_json(pack.id, actor="slice49-test")
    assert await _scalar(
        db_session,
        "SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action IN "
        "('evidence_pack.core_preview_exported','evidence_pack.markdown_exported',"
        "'evidence_pack.unsigned_manifest_exported','evidence_pack.canonical_export_refused')",
        t=ctx["tenant"],
    ) == 4
    assert await _scalar(
        db_session,
        "SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action LIKE 'evidence_pack.%' "
        "AND (payload::text LIKE '%SENTINEL_SECRET_PROSE%' OR payload::text LIKE '%canonical_core_text%')",
        t=ctx["tenant"],
    ) == 0


@pytest.mark.db
async def test_generator_derives_conservative_inventory_and_persists_incomplete_attempt(
    evidence_pack_ctx, db_session
):
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.tenancy import TenantContext

    ctx = evidence_pack_ctx
    artifact = await _scalar(
        db_session,
        "INSERT INTO intake_artifacts "
        "(tenant_id,project_id,kind,ref,title,body,data,classification,created_at,updated_at) "
        "VALUES (:t,:p,'requirement','REQ-GEN','bounded',NULL,'{}'::jsonb,NULL,"
        ":cutoff,:cutoff) RETURNING id",
        t=ctx["tenant"],
        p=ctx["project"],
        cutoff=ctx["frozen_at"],
    )
    await db_session.execute(
        text(
            "INSERT INTO intake_provenance "
            "(tenant_id,project_id,artifact_id,origin,created_at) "
            "VALUES (:t,:p,:a,'slice49-generator-test',:cutoff)"
        ),
        {
            "t": ctx["tenant"],
            "p": ctx["project"],
            "a": artifact,
            "cutoff": ctx["frozen_at"],
        },
    )
    repo = EvidencePackRepository(db_session, TenantContext(ctx["tenant"]))
    checkpoint = await repo.record_audit_checkpoint()
    pack = await repo.assemble_core(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        audit_checkpoint_id=checkpoint.id,
        actor="slice49-test",
    )
    assert pack.assembly_status == "incomplete"
    assert pack.repo_binding_state == "missing_trusted_binding"
    refs = (
        await db_session.execute(
            text(
                "SELECT source_kind,truth_tier FROM evidence_pack_source_refs "
                "WHERE evidence_pack_id=:p ORDER BY source_kind"
            ),
            {"p": pack.id},
        )
    ).all()
    assert refs == [
        ("intake_artifact", "db_proven_structural"),
        ("intake_provenance", "db_proven_sanad_record"),
    ]
    assert await _scalar(
        db_session,
        "SELECT count(*) FROM evidence_pack_section_results WHERE evidence_pack_id=:p "
        "AND presence_code='missing_required_source'",
        p=pack.id,
    ) >= 1
    assert await _scalar(
        db_session,
        "SELECT count(*) FROM evidence_pack_generation_runs WHERE id=:r "
        "AND execution_status='incomplete' AND failure_code='required_sources_incomplete'",
        r=pack.generation_run_id,
    ) == 1


@pytest.mark.db
async def test_failed_attempt_is_retained_without_fabricating_a_core(
    evidence_pack_ctx, db_session
):
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.tenancy import TenantContext

    ctx = evidence_pack_ctx
    repo = EvidencePackRepository(db_session, TenantContext(ctx["tenant"]))
    checkpoint = await repo.record_audit_checkpoint()
    run = await repo.record_failed_attempt(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        audit_checkpoint_id=checkpoint.id,
        failure_code="source_projection_contract_failed",
        actor="slice49-test",
    )
    assert run.execution_status == "failed"
    assert run.canonical_byte_count == 0
    assert await _scalar(
        db_session,
        "SELECT count(*) FROM evidence_packs WHERE generation_run_id=:r",
        r=run.id,
    ) == 0
    with pytest.raises(Exception, match="failure_code_not_allowed"):
        await repo.record_failed_attempt(
            project_id=ctx["project"],
            release_candidate_id=ctx["candidate"],
            audit_checkpoint_id=checkpoint.id,
            failure_code="caller_says_passed",
            actor="slice49-test",
        )


@pytest.mark.db
async def test_runtime_rls_isolates_attempts_and_cannot_forge_audit_checkpoint(
    admin_engine, rls_engine
):
    suffix = uuid.uuid4().hex[:10]
    run_id = uuid.uuid4()
    async with admin_engine.begin() as conn:
        org = await _scalar(
            conn,
            "INSERT INTO organizations (name,slug) VALUES ('EvidenceRLSOrg',:s) RETURNING id",
            s=f"evidence-rls-org-{suffix}",
        )
        tenant = await _scalar(
            conn,
            "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'EvidenceRLS',:s) "
            "RETURNING id",
            o=org,
            s=f"evidence-rls-tenant-{suffix}",
        )
        project = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'EvidenceRLS',:s) "
            "RETURNING id",
            t=tenant,
            s=f"evidence-rls-project-{suffix}",
        )
        candidate = await _scalar(
            conn,
            "INSERT INTO release_candidates "
            "(tenant_id,project_id,release_ref,status) VALUES (:t,:p,:r,'draft') RETURNING id",
            t=tenant,
            p=project,
            r=f"release-rls-{suffix}",
        )
        await conn.execute(
            text(
                "UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() "
                "WHERE id=:c"
            ),
            {"c": candidate},
        )
        await conn.execute(
            text(
                "INSERT INTO evidence_pack_generation_runs "
                "(id,tenant_id,project_id,release_candidate_id,audit_checkpoint_id,"
                "release_ref_digest,schema_version,semantic_contract_version,"
                "semantic_contract_hash,projection_contract_version,projection_contract_hash,"
                "audit_contract_version,audit_contract_hash,execution_status,"
                "execution_provenance,failure_code,missing_required_section_count,"
                "inconsistent_section_count,source_ref_count,section_count,"
                "traceability_edge_count,canonical_byte_count,source_cutoff,generated_at) "
                "SELECT :i,:t,:p,:c,NULL,:h,'uaid.evidence_pack.v1.2',"
                "'slice49.evidence_pack.v1',:h,'slice49.evidence_projection.v1',:h,"
                "'slice49.evidence_audit.v1',:h,'failed','system_assembled_evidence_pack',"
                "'source_projection_contract_failed',0,0,0,0,0,0,frozen_at,clock_timestamp() "
                "FROM release_candidates WHERE id=:c"
            ),
            {"i": run_id, "t": tenant, "p": project, "c": candidate, "h": SHA_A},
        )
    try:
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant',:t,true)"),
                    {"t": str(tenant)},
                )
                assert await _scalar(
                    conn,
                    "SELECT count(*) FROM evidence_pack_generation_runs WHERE id=:i",
                    i=run_id,
                ) == 1
            async with conn.begin():
                await conn.execute(
                    text("SELECT set_config('app.current_tenant',:t,true)"),
                    {"t": str(uuid.uuid4())},
                )
                assert await _scalar(
                    conn,
                    "SELECT count(*) FROM evidence_pack_generation_runs WHERE id=:i",
                    i=run_id,
                ) == 0
            with pytest.raises(Exception, match="permission denied"):
                async with conn.begin():
                    await conn.execute(
                        text(
                            "INSERT INTO audit_chain_verifications "
                            "(verifier_contract_version,verifier_contract_hash,verification_ok,"
                            "verified_through_seq,verified_through_entry_hash) "
                            "VALUES ('slice49.evidence_audit.v1',:h,true,1,:e)"
                        ),
                        {"h": SHA_A, "e": "a" * 64},
                    )
    finally:
        async with admin_engine.begin() as cleanup:
            await cleanup.execute(
                text(
                    "ALTER TABLE evidence_pack_generation_runs DISABLE TRIGGER "
                    "evidence_pack_generation_runs_no_update_delete"
                )
            )
            await cleanup.execute(
                text("DELETE FROM evidence_pack_generation_runs WHERE id=:i"),
                {"i": run_id},
            )
            await cleanup.execute(
                text(
                    "ALTER TABLE evidence_pack_generation_runs ENABLE TRIGGER "
                    "evidence_pack_generation_runs_no_update_delete"
                )
            )


def test_slice48_has_explicit_safe_projection_method() -> None:
    from app.repositories.reviewer_quality import ReviewerQualityRepository

    assert hasattr(ReviewerQualityRepository, "evidence_pack_safe_projection")


@pytest.mark.db
async def test_deferred_backstop_and_source_resolution_reject_direct_sql_attacks(
    evidence_pack_ctx, db_session
):
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.tenancy import TenantContext

    ctx = evidence_pack_ctx
    repo = EvidencePackRepository(db_session, TenantContext(ctx["tenant"]))
    checkpoint = await repo.record_audit_checkpoint()
    pack = await repo._persist_core(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        core=_db_core(ctx, checkpoint),
        source_refs=(),
        inventories=_inventories(),
        traceability_edge_count=0,
        actor="slice49-test",
    )
    artifact = await _scalar(
        db_session,
        "INSERT INTO intake_artifacts "
        "(tenant_id,project_id,kind,ref,title,body,data,classification) "
        "VALUES (:t,:p,'requirement','REQ-EVIDENCE','bounded',NULL,'{}'::jsonb,NULL) "
        "RETURNING id",
        t=ctx["tenant"],
        p=ctx["project"],
    )
    await db_session.execute(
        text(
            "INSERT INTO intake_provenance (tenant_id,project_id,artifact_id,origin) "
            "VALUES (:t,:p,:a,'slice49-db-test')"
        ),
        {"t": ctx["tenant"], "p": ctx["project"], "a": artifact},
    )
    nested = await db_session.begin_nested()
    await db_session.execute(
        text(
            "INSERT INTO evidence_pack_source_refs "
            "(tenant_id,project_id,evidence_pack_id,source_kind,source_id,truth_tier,"
            "projection_digest,source_created_at,ordinal) "
            "VALUES (:t,:p,:e,'intake_artifact',:s,'db_proven_structural',:d,"
            "clock_timestamp(),1)"
        ),
        {"t": ctx["tenant"], "p": ctx["project"], "e": pack.id, "s": artifact, "d": SHA_A},
    )
    with pytest.raises(Exception, match="declared source-ref count"):
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await nested.rollback()

    nested = await db_session.begin_nested()
    with pytest.raises(Exception, match="source kind does not resolve"):
        await db_session.execute(
            text(
                "INSERT INTO evidence_pack_source_refs "
                "(tenant_id,project_id,evidence_pack_id,source_kind,source_id,truth_tier,"
                "projection_digest,source_created_at,ordinal) "
                "VALUES (:t,:p,:e,'review_report',:s,'caller_supplied_unverified',:d,"
                "clock_timestamp(),1)"
            ),
            {"t": ctx["tenant"], "p": ctx["project"], "e": pack.id, "s": artifact, "d": SHA_A},
        )
    await nested.rollback()


@pytest.mark.db
async def test_all_slice49_rows_are_append_only(evidence_pack_ctx, db_session):
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.tenancy import TenantContext

    ctx = evidence_pack_ctx
    repo = EvidencePackRepository(db_session, TenantContext(ctx["tenant"]))
    checkpoint = await repo.record_audit_checkpoint()
    pack = await repo._persist_core(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        core=_db_core(ctx, checkpoint),
        source_refs=(),
        inventories=_inventories(),
        traceability_edge_count=0,
        actor="slice49-test",
    )
    for table, row_id in (
        ("audit_chain_verifications", checkpoint.id),
        ("evidence_pack_generation_runs", pack.generation_run_id),
        ("evidence_packs", pack.id),
    ):
        nested = await db_session.begin_nested()
        with pytest.raises(Exception, match="append-only"):
            await db_session.execute(text(f"UPDATE {table} SET id=id WHERE id=:i"), {"i": row_id})
        await nested.rollback()


@pytest.mark.db
async def test_audit_lock_prevents_append_between_verification_and_tip_capture(admin_engine):
    checkpoint_id = None
    task = None
    async with admin_engine.connect() as verifier:
        tx_verify = await verifier.begin()
        try:
            await verifier.execute(text("SELECT pg_advisory_xact_lock(421)"))
            verified = (await verifier.execute(text("SELECT * FROM audit_verify()"))).mappings().one()
            assert verified["ok"] is True
            tip = (
                await verifier.execute(
                    text("SELECT seq,entry_hash FROM audit_logs ORDER BY seq DESC LIMIT 1")
                )
            ).mappings().one()

            async def append_after_lock():
                async with admin_engine.begin() as appender:
                    tenant = await _scalar(
                        appender, "SELECT tenant_id FROM audit_logs LIMIT 1"
                    )
                    await appender.execute(
                        text("SELECT set_config('app.current_tenant',:t,true)"),
                        {"t": str(tenant)},
                    )
                    return await _scalar(
                        appender,
                        "SELECT entry_hash FROM audit_append('slice49-race','append',NULL,'{}')",
                    )

            task = asyncio.create_task(append_after_lock())
            await asyncio.sleep(0.05)
            assert not task.done()
            checkpoint_id = await _scalar(
                verifier,
                "INSERT INTO audit_chain_verifications "
                "(verifier_contract_version,verifier_contract_hash,verification_ok,"
                "verified_through_seq,verified_through_entry_hash) "
                "VALUES ('slice49.evidence_audit.v1',:h,true,:s,:e) RETURNING id",
                h=SHA_B,
                s=tip["seq"],
                e=tip["entry_hash"],
            )
            await tx_verify.commit()
            await task
            async with verifier.begin():
                assert await _scalar(
                    verifier,
                    "SELECT max(seq) FROM audit_logs",
                ) > tip["seq"]
        finally:
            if tx_verify.is_active:
                await tx_verify.rollback()
            if task is not None and not task.done():
                await task
    if checkpoint_id is not None:
        async with admin_engine.begin() as cleanup:
            await cleanup.execute(
                text(
                    "ALTER TABLE audit_chain_verifications DISABLE TRIGGER "
                    "audit_chain_verifications_no_update_delete"
                )
            )
            await cleanup.execute(
                text("DELETE FROM audit_chain_verifications WHERE id=:i"),
                {"i": checkpoint_id},
            )
            await cleanup.execute(
                text(
                    "ALTER TABLE audit_chain_verifications ENABLE TRIGGER "
                    "audit_chain_verifications_no_update_delete"
                )
            )
