"""Slice 50 release-verdict tests (§24.3 / Appendix B gate #7).

The verdict is a deterministic, bounded decision over one exact frozen candidate and one
re-audited Slice-49 core.  It is never a human approval or deployment authorization.
"""

from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.release.release_manager import (
    CANONICAL_VERDICTS,
    DECISION_SCOPE,
    SPEC_VERDICTS,
    IssueDisposition,
    ReleaseVerdictContractError,
    ReleaseVerdictInput,
    evaluate_release_verdict,
    project_canonical_verdict,
)
from app.release.production_autonomy import NO_GO_LIVE_REASONS, evaluate_production_autonomy
from app.release.evidence_pack import (
    EvidenceSourceRef,
    INVENTORY_SECTIONS,
    SectionInventory,
    assemble_core,
    canonical_json_bytes,
    derive_repo_commit_binding,
    digest_bytes,
    project_source_record,
)


def _issue(**overrides) -> IssueDisposition:
    values = {
        "binding_id": "binding-1",
        "issue_id": "issue-1",
        "status": "resolved",
        "trusted_provenance": True,
        "blocking": False,
        "hard_blocker": False,
        "exact_risk_acceptance": False,
        "risk_authority_verified": False,
    }
    values.update(overrides)
    return IssueDisposition(**values)


def _input(*issues: IssueDisposition, **overrides) -> ReleaseVerdictInput:
    values = {
        "assembly_complete": True,
        "inventory_complete": True,
        "issue_binding_exact": True,
        "input_current": True,
        "issues": tuple(issues),
    }
    values.update(overrides)
    return ReleaseVerdictInput(**values)


def test_verdict_vocabulary_and_lossy_projection_are_explicit():
    assert SPEC_VERDICTS == (
        "passed",
        "passed_with_limitations",
        "failed_blocking_issue",
        "failed_missing_evidence",
        "requires_human_decision",
        "not_applicable",
    )
    assert CANONICAL_VERDICTS == (
        "passed",
        "passed_with_accepted_risk",
        "failed",
        "blocked",
    )
    assert project_canonical_verdict("passed") == "passed"
    assert project_canonical_verdict("passed_with_limitations") == "passed_with_accepted_risk"
    assert project_canonical_verdict("failed_blocking_issue") == "failed"
    assert project_canonical_verdict("failed_missing_evidence") == "failed"
    assert project_canonical_verdict("requires_human_decision") == "blocked"
    assert project_canonical_verdict("not_applicable") == "blocked"
    with pytest.raises(ReleaseVerdictContractError, match="spec_verdict_invalid"):
        project_canonical_verdict("caller_passed")


def test_clean_and_explicit_exact_zero_inventory_pass_bounded_gate_scope():
    clean = evaluate_release_verdict(_input(_issue()))
    zero = evaluate_release_verdict(_input())

    for decision in (clean, zero):
        assert decision.spec_verdict == "passed"
        assert decision.canonical_verdict == "passed"
        assert decision.gate_eligible is True
        assert decision.decision_scope == DECISION_SCOPE == "known_bound_issue_disposition"
        assert decision.reason_code == "bound_release_issue_disposition_clean"


@pytest.mark.parametrize(
    "overrides",
    [
        {"assembly_complete": False},
        {"inventory_complete": False},
        {"issue_binding_exact": False},
        {"input_current": False},
    ],
)
def test_missing_or_stale_core_evidence_fails_missing_evidence(overrides):
    decision = evaluate_release_verdict(_input(_issue(), **overrides))

    assert decision.spec_verdict == "failed_missing_evidence"
    assert decision.canonical_verdict == "failed"
    assert decision.gate_eligible is False
    assert decision.reason_code == "release_verdict_evidence_incomplete_or_stale"


def test_untrusted_issue_fails_missing_evidence():
    decision = evaluate_release_verdict(_input(_issue(trusted_provenance=False)))

    assert decision.spec_verdict == "failed_missing_evidence"
    assert decision.reason_code == "bound_issue_provenance_incomplete"
    assert decision.gate_eligible is False


@pytest.mark.parametrize(
    "issue",
    [
        _issue(status="open", blocking=True),
        _issue(status="open", blocking=True, hard_blocker=True),
        _issue(status="accepted", blocking=True, hard_blocker=True),
    ],
)
def test_open_blocking_or_hard_issue_forces_failing_verdict(issue):
    decision = evaluate_release_verdict(_input(issue))

    assert decision.spec_verdict == "failed_blocking_issue"
    assert decision.canonical_verdict == "failed"
    assert decision.gate_eligible is False
    assert decision.reason_code == "open_blocking_or_hard_refusal_issue"


def test_unverified_risk_authority_routes_to_decision_only_human_outcome():
    decision = evaluate_release_verdict(
        _input(
            _issue(
                status="open",
                exact_risk_acceptance=True,
                risk_authority_verified=False,
            )
        )
    )

    assert decision.spec_verdict == "requires_human_decision"
    assert decision.canonical_verdict == "blocked"
    assert decision.gate_eligible is False
    assert decision.reason_code == "risk_acceptance_authority_unverified"


def test_verified_future_authority_is_the_only_limitation_projection_path():
    decision = evaluate_release_verdict(
        _input(
            _issue(
                status="open",
                exact_risk_acceptance=True,
                risk_authority_verified=True,
            )
        )
    )

    assert decision.spec_verdict == "passed_with_limitations"
    assert decision.canonical_verdict == "passed_with_accepted_risk"
    assert decision.gate_eligible is True
    assert decision.reason_code == "bound_release_limitations_authoritatively_accepted"


def test_open_nonblocking_issue_without_exact_acceptance_requires_human_decision():
    decision = evaluate_release_verdict(_input(_issue(status="open")))

    assert decision.spec_verdict == "requires_human_decision"
    assert decision.canonical_verdict == "blocked"
    assert decision.gate_eligible is False
    assert decision.reason_code == "open_issue_requires_risk_acceptance_authority"


def test_not_applicable_and_caller_truth_fields_are_not_inputs():
    with pytest.raises(TypeError):
        ReleaseVerdictInput(
            assembly_complete=True,
            inventory_complete=True,
            issue_binding_exact=True,
            input_current=True,
            issues=(),
            verdict="not_applicable",  # type: ignore[call-arg]
        )


def test_release_verdict_models_map_only_the_three_slice50_tables():
    from app.models.release_verdict import (
        ReleaseVerdict,
        ReleaseVerdictIssueResult,
        ReleaseVerdictRun,
    )

    assert ReleaseVerdictRun.__tablename__ == "release_verdict_runs"
    assert ReleaseVerdict.__tablename__ == "release_verdicts"
    assert ReleaseVerdictIssueResult.__tablename__ == "release_verdict_issue_results"


def _gate7(**overrides):
    values = {
        "readiness_level": "R5",
        "frozen_release_candidate_count": 1,
        "release_evidence_core_present": True,
        "release_evidence_core_audited": True,
        "release_verdict_run_present": True,
        "release_verdict_attempt_failed": False,
        "release_verdict_binding_current": True,
        "release_verdict_evidence_consistent": True,
        "release_verdict_spec_verdict": "passed",
        "release_verdict_gate_eligible": True,
        "release_verdict_reason_code": "bound_release_issue_disposition_clean",
        "release_verdict_decision_scope": "known_bound_issue_disposition",
        "release_verdict_execution_provenance": "system_derived_release_verdict",
    }
    values.update(overrides)
    report = evaluate_production_autonomy("project", **values).to_dict()
    return report, next(gate for gate in report["gates"] if gate["number"] == 7)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"frozen_release_candidate_count": 0},
            "insufficient_evidence:no_issue_provenance_or_release_binding",
        ),
        (
            {"release_evidence_core_present": False},
            "insufficient_evidence:no_audited_release_evidence_core",
        ),
        (
            {"release_evidence_core_audited": False},
            "insufficient_evidence:no_audited_release_evidence_core",
        ),
        (
            {"release_verdict_attempt_failed": True},
            "insufficient_evidence:release_verdict_evidence_incomplete_or_stale",
        ),
        (
            {"release_verdict_binding_current": False},
            "insufficient_evidence:release_verdict_evidence_incomplete_or_stale",
        ),
        (
            {
                "release_verdict_run_present": False,
                "release_verdict_spec_verdict": None,
                "release_verdict_gate_eligible": False,
            },
            "insufficient_evidence:verified_known_issue_set_but_no_release_verdict",
        ),
        (
            {
                "release_verdict_spec_verdict": "failed_missing_evidence",
                "release_verdict_gate_eligible": False,
            },
            "insufficient_evidence:release_verdict_failed_missing_evidence",
        ),
        (
            {
                "release_verdict_spec_verdict": "failed_blocking_issue",
                "release_verdict_gate_eligible": False,
            },
            "insufficient_evidence:release_verdict_failed_blocking_issue",
        ),
        (
            {
                "release_verdict_spec_verdict": "requires_human_decision",
                "release_verdict_gate_eligible": False,
            },
            "insufficient_evidence:release_verdict_requires_human_decision",
        ),
        (
            {
                "release_verdict_spec_verdict": "not_applicable",
                "release_verdict_gate_eligible": False,
            },
            "insufficient_evidence:release_verdict_not_applicable",
        ),
        (
            {
                "release_verdict_spec_verdict": "passed_with_limitations",
                "release_verdict_gate_eligible": False,
            },
            "insufficient_evidence:release_limitations_not_authoritatively_accepted",
        ),
    ],
)
def test_gate7_ruled_fail_closed_ladder(overrides, reason):
    report, gate = _gate7(**overrides)

    assert gate["status"] == "insufficient_evidence"
    assert gate["reason"] == reason
    assert report["a5_satisfied"] is False
    assert report["can_go_live_autonomously"] is False


@pytest.mark.parametrize("spec_verdict", ["passed", "passed_with_limitations"])
def test_current_gate_eligible_verdict_is_gate7_pass_capable_only(spec_verdict):
    report, gate = _gate7(release_verdict_spec_verdict=spec_verdict)

    assert gate["status"] == "passed"
    assert gate["reason"] == "passed:bound_release_issue_disposition_verdict_current"
    assert gate["context"]["decision_scope"] == "known_bound_issue_disposition"
    assert report["ruleset_version"] == "slice50.v1"
    assert report["a5_satisfied"] is False
    assert report["can_go_live_autonomously"] is False
    assert (
        tuple(report["can_go_live_reasons"])
        == NO_GO_LIVE_REASONS
        == (
            "a5_gates_not_all_satisfied",
            "request_authenticated_a5_preapproval_not_implemented",
        )
    )


def test_slice50_inputs_change_only_gate7():
    baseline = evaluate_production_autonomy("project", readiness_level="R5").to_dict()
    advanced, _ = _gate7()

    before = {gate["number"]: gate for gate in baseline["gates"]}
    after = {gate["number"]: gate for gate in advanced["gates"]}
    assert {number for number in before if before[number] != after[number]} == {7}


@pytest.mark.db
@pytest.mark.asyncio
async def test_slice50_catalog_owns_generated_verdict_and_preserves_findings_guard(admin_engine):
    async with admin_engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(:names) ORDER BY relname"
                ),
                {
                    "names": [
                        "release_verdict_issue_results",
                        "release_verdict_runs",
                        "release_verdicts",
                    ]
                },
            )
        ).all()
        assert tables == [
            ("release_verdict_issue_results", True, True),
            ("release_verdict_runs", True, True),
            ("release_verdicts", True, True),
        ]
        generated = (
            (
                await conn.execute(
                    text(
                        "SELECT attname FROM pg_attribute "
                        "WHERE attrelid='release_verdicts'::regclass AND attgenerated='s' "
                        "ORDER BY attname"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert generated == [
            "canonical_verdict",
            "gate_eligible",
            "reason_code",
            "spec_verdict",
        ]
        privileges = (
            await conn.execute(
                text(
                    "SELECT relname,"
                    "has_table_privilege('uaid_app',oid,'SELECT'),"
                    "has_table_privilege('uaid_app',oid,'INSERT'),"
                    "has_table_privilege('uaid_app',oid,'UPDATE'),"
                    "has_table_privilege('uaid_app',oid,'DELETE') "
                    "FROM pg_class WHERE relname = ANY(:names) ORDER BY relname"
                ),
                {
                    "names": [
                        "release_verdict_issue_results",
                        "release_verdict_runs",
                        "release_verdicts",
                    ]
                },
            )
        ).all()
        assert privileges == [
            ("release_verdict_issue_results", True, True, False, False),
            ("release_verdict_runs", True, True, False, False),
            ("release_verdicts", True, True, False, False),
        ]
        guard_md5 = await conn.scalar(
            text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
        )
        assert guard_md5 == "808036faf2660d6810aeca4342e6f1ac"


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


def _zero_inventories() -> tuple[SectionInventory, ...]:
    empty_digest = digest_bytes(canonical_json_bytes([]))
    return tuple(
        SectionInventory(
            section_code=section,
            presence_code="present_zero_rows",
            item_count=0,
            section_digest=empty_digest,
            required=True,
            failure_code=None,
        )
        for section in INVENTORY_SECTIONS
    )


def _issue_inventories(*refs: EvidenceSourceRef) -> tuple[SectionInventory, ...]:
    empty_digest = digest_bytes(canonical_json_bytes([]))
    issue_digest = digest_bytes(canonical_json_bytes([ref.as_dict() for ref in refs]))
    return tuple(
        SectionInventory(
            section_code=section,
            presence_code="present" if section == "candidate_issues" else "present_zero_rows",
            item_count=len(refs) if section == "candidate_issues" else 0,
            section_digest=issue_digest if section == "candidate_issues" else empty_digest,
            required=True,
            failure_code=None,
        )
        for section in INVENTORY_SECTIONS
    )


def _binding_digest(*binding_refs: EvidenceSourceRef) -> str:
    return digest_bytes(canonical_json_bytes([ref.projection_digest for ref in binding_refs]))


@pytest_asyncio.fixture
async def release_verdict_ctx(db_session):
    suffix = uuid.uuid4().hex[:10]
    org = await _scalar(
        db_session,
        "INSERT INTO organizations (name,slug) VALUES ('VerdictOrg',:s) RETURNING id",
        s=f"verdict-org-{suffix}",
    )
    tenant = await _scalar(
        db_session,
        "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'VerdictTenant',:s) RETURNING id",
        o=org,
        s=f"verdict-tenant-{suffix}",
    )
    project = await _scalar(
        db_session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'VerdictProject',:s) RETURNING id",
        t=tenant,
        s=f"verdict-project-{suffix}",
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
            "UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() WHERE id=:c"
        ),
        {"c": candidate},
    )
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:t,true)"), {"t": str(tenant)}
    )
    await db_session.execute(
        text("SELECT * FROM audit_append('slice50-test','seed',NULL,'{}'::jsonb)")
    )
    frozen_at = await _scalar(
        db_session, "SELECT frozen_at FROM release_candidates WHERE id=:c", c=candidate
    )
    return {
        "tenant": tenant,
        "project": project,
        "candidate": candidate,
        "frozen_at": frozen_at,
    }


@pytest.mark.db
async def test_repository_records_exact_zero_verdict_and_unlocks_unsigned_export(
    release_verdict_ctx, db_session
):
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.repositories.release_verdicts import ReleaseVerdictRepository
    from app.tenancy import TenantContext

    ctx = release_verdict_ctx
    tenant_context = TenantContext(ctx["tenant"])
    packs = EvidencePackRepository(db_session, tenant_context)
    checkpoint = await packs.record_audit_checkpoint()
    inventories = _zero_inventories()
    core = assemble_core(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        release_ref_digest="sha256:" + "a" * 64,
        generated_at=checkpoint.created_at,
        frozen_at=ctx["frozen_at"],
        artifact_scope_digest="sha256:" + "b" * 64,
        issue_binding_digest=_binding_digest(),
        source_refs=(),
        inventories=inventories,
        traceability=(),
        audit_checkpoint=checkpoint,
        repo_commit_binding=derive_repo_commit_binding([]),
    )
    pack = await packs._persist_core(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        core=core,
        source_refs=(),
        inventories=inventories,
        traceability_edge_count=0,
        actor="slice50-test",
    )

    verdicts = ReleaseVerdictRepository(db_session, tenant_context)
    verdict = await verdicts.evaluate_and_record(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        evidence_pack_id=pack.id,
        actor="slice50-test",
    )
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    assert verdict.spec_verdict == "passed"
    assert verdict.canonical_verdict == "passed"
    assert verdict.gate_eligible is True
    assert verdict.issue_count == 0
    coverage = await verdicts.coverage_for_project(ctx["project"])
    report = evaluate_production_autonomy(
        ctx["project"],
        readiness_level="R5",
        frozen_release_candidate_count=1,
        **coverage.gate_kwargs(),
    ).to_dict()
    gate7 = next(gate for gate in report["gates"] if gate["number"] == 7)
    assert gate7["status"] == "passed"

    artifact = await packs.export_canonical_json(pack.id, actor="slice50-test")
    payload = json.loads(artifact.content)
    assert payload["verdict"] == "passed"
    assert payload["verdict_attestation"]["spec_verdict"] == "passed"
    assert payload["verdict_attestation"]["decision_scope"] == DECISION_SCOPE
    assert payload["signatures"] == []
    assert payload["signature_status"] == "unsigned_signer_tier_not_implemented"
    assert "verdict_deferred_to_slice_50" not in payload["assurance_limitations"]
    stored = await _scalar(
        db_session,
        "SELECT canonical_core_text FROM evidence_packs WHERE id=:p",
        p=pack.id,
    )
    assert stored == core.canonical_text

    from app.repositories.production_autonomy import ProductionAutonomyRepository

    composed = await ProductionAutonomyRepository(db_session, tenant_context).evaluate(
        ctx["project"]
    )
    composed_gate7 = next(gate for gate in composed.to_dict()["gates"] if gate["number"] == 7)
    assert composed_gate7["status"] == "passed"

    await verdicts.record_failed_attempt(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        evidence_pack_id=pack.id,
        failure_code="verdict_reaudit_refused",
        actor="slice50-test",
    )
    superseding = await verdicts.coverage_for_project(ctx["project"])
    superseded_report = evaluate_production_autonomy(
        ctx["project"],
        readiness_level="R5",
        frozen_release_candidate_count=1,
        **superseding.gate_kwargs(),
    ).to_dict()
    superseded_gate7 = next(gate for gate in superseded_report["gates"] if gate["number"] == 7)
    assert superseded_gate7["status"] == "insufficient_evidence"
    assert superseded_gate7["reason"] == (
        "insufficient_evidence:release_verdict_evidence_incomplete_or_stale"
    )

    await packs.record_failed_attempt(
        project_id=ctx["project"],
        release_candidate_id=ctx["candidate"],
        audit_checkpoint_id=checkpoint.id,
        failure_code="assembly_contract_failed",
        actor="slice50-test",
    )
    failed_pack_supersedes = await verdicts.coverage_for_project(ctx["project"])
    assert failed_pack_supersedes.evidence_core_present is False
    assert failed_pack_supersedes.evidence_core_audited is False
    assert failed_pack_supersedes.verdict_attempt_failed is True


@pytest.mark.db
async def test_hard_blocker_cannot_be_downgraded_and_audit_excludes_prose(
    release_verdict_ctx, db_session
):
    from app.models.release_issue import ReleaseIssue
    from app.models.release_candidate_issue_binding import ReleaseCandidateIssueBinding
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.repositories.release_verdicts import ReleaseVerdictRepository
    from app.tenancy import TenantContext

    ctx = release_verdict_ctx
    suffix = uuid.uuid4().hex[:10]
    issue_id = await _scalar(
        db_session,
        "INSERT INTO release_issues "
        "(tenant_id,project_id,issue_category,severity,blocking,summary,detail,source,"
        "source_provenance,status) VALUES "
        "(:t,:p,'security','critical',true,'SENTINEL_SECRET_PROSE',"
        "'SENTINEL_BLOCKER_DETAIL','slice50-test','caller_supplied_unverified','open') "
        "RETURNING id",
        t=ctx["tenant"],
        p=ctx["project"],
    )
    candidate = await _scalar(
        db_session,
        "INSERT INTO release_candidates (tenant_id,project_id,release_ref,status) "
        "VALUES (:t,:p,:r,'draft') RETURNING id",
        t=ctx["tenant"],
        p=ctx["project"],
        r=f"critical-{suffix}",
    )
    binding_id = await _scalar(
        db_session,
        "INSERT INTO release_candidate_issue_bindings "
        "(tenant_id,project_id,release_candidate_id,release_issue_id) "
        "VALUES (:t,:p,:c,:i) RETURNING id",
        t=ctx["tenant"],
        p=ctx["project"],
        c=candidate,
        i=issue_id,
    )
    await db_session.execute(
        text(
            "UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() WHERE id=:c"
        ),
        {"c": candidate},
    )
    frozen_at = await _scalar(
        db_session, "SELECT frozen_at FROM release_candidates WHERE id=:c", c=candidate
    )
    issue = await db_session.get(ReleaseIssue, issue_id)
    binding = await db_session.get(ReleaseCandidateIssueBinding, binding_id)
    assert issue is not None
    assert binding is not None
    issue_ref = project_source_record("release_issue", issue)
    binding_ref = project_source_record("release_candidate_issue_binding", binding)
    refs = (binding_ref, issue_ref)
    inventories = _issue_inventories(*refs)
    tenant_context = TenantContext(ctx["tenant"])
    packs = EvidencePackRepository(db_session, tenant_context)
    checkpoint = await packs.record_audit_checkpoint()
    core = assemble_core(
        project_id=ctx["project"],
        release_candidate_id=candidate,
        release_ref_digest="sha256:" + "d" * 64,
        generated_at=checkpoint.created_at,
        frozen_at=frozen_at,
        artifact_scope_digest="sha256:" + "e" * 64,
        issue_binding_digest=_binding_digest(binding_ref),
        source_refs=refs,
        inventories=inventories,
        traceability=(),
        audit_checkpoint=checkpoint,
        repo_commit_binding=derive_repo_commit_binding([]),
    )
    pack = await packs._persist_core(
        project_id=ctx["project"],
        release_candidate_id=candidate,
        core=core,
        source_refs=refs,
        inventories=inventories,
        traceability_edge_count=0,
        actor="slice50-test",
    )
    verdict = await ReleaseVerdictRepository(db_session, tenant_context).evaluate_and_record(
        project_id=ctx["project"],
        release_candidate_id=candidate,
        evidence_pack_id=pack.id,
        actor="slice50-test",
    )
    assert verdict.spec_verdict in {"failed_blocking_issue", "failed_missing_evidence"}
    assert verdict.canonical_verdict == "failed"
    assert verdict.gate_eligible is False

    artifact = await packs.export_canonical_json(pack.id, actor="slice50-test")
    assert json.loads(artifact.content)["verdict"] == "failed"

    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE release_verdicts SET blocking_issue_count=0 WHERE id=:v"),
                {"v": verdict.id},
            )
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO release_verdicts (spec_verdict) VALUES ('passed')")
            )

    audit_text = await _scalar(
        db_session,
        "SELECT COALESCE(string_agg(payload::text,' '),'') FROM audit_logs "
        "WHERE action IN ('release.verdict_recorded','evidence_pack.canonical_exported')",
    )
    assert "SENTINEL_SECRET_PROSE" not in audit_text
    assert "SENTINEL_BLOCKER_DETAIL" not in audit_text

    await db_session.execute(
        text(
            "UPDATE release_issues SET status='resolved',resolution_note='fixed',"
            "resolved_at=clock_timestamp(),resolved_by='slice50-test' WHERE id=:i"
        ),
        {"i": issue_id},
    )

    forged_run_id = uuid.uuid4()
    forged_verdict_id = uuid.uuid4()
    with pytest.raises(DBAPIError, match="frozen/core evidence"):
        async with db_session.begin_nested():
            await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            await db_session.execute(
                text(
                    "INSERT INTO release_verdict_runs "
                    "(id,tenant_id,project_id,release_candidate_id,evidence_pack_id,"
                    "input_contract_version,verdict_contract_version,projection_contract_version,"
                    "input_digest,core_content_hash,verdict_contract_hash,execution_status,"
                    "execution_provenance) SELECT :new_id,tenant_id,project_id,"
                    "release_candidate_id,evidence_pack_id,input_contract_version,"
                    "verdict_contract_version,projection_contract_version,input_digest,"
                    "core_content_hash,verdict_contract_hash,'succeeded',execution_provenance "
                    "FROM release_verdict_runs WHERE id=:old_id"
                ),
                {"new_id": forged_run_id, "old_id": verdict.run_id},
            )
            await db_session.execute(
                text(
                    "INSERT INTO release_verdicts "
                    "(id,tenant_id,project_id,run_id,release_candidate_id,evidence_pack_id,"
                    "audit_checkpoint_id,input_digest,core_content_hash,issue_binding_digest,"
                    "source_set_digest,traceability_digest,verdict_contract_hash,"
                    "input_contract_version,verdict_contract_version,projection_contract_version,"
                    "decision_scope,execution_provenance,issue_count,missing_evidence_count,"
                    "blocking_issue_count,limitation_count,unverified_authority_count) "
                    "SELECT :new_id,tenant_id,project_id,:run_id,release_candidate_id,"
                    "evidence_pack_id,audit_checkpoint_id,input_digest,core_content_hash,"
                    "issue_binding_digest,source_set_digest,traceability_digest,"
                    "verdict_contract_hash,input_contract_version,verdict_contract_version,"
                    "projection_contract_version,decision_scope,execution_provenance,"
                    "issue_count,missing_evidence_count,0,0,0 FROM release_verdicts WHERE id=:old_id"
                ),
                {
                    "new_id": forged_verdict_id,
                    "run_id": forged_run_id,
                    "old_id": verdict.id,
                },
            )
            await db_session.execute(
                text(
                    "INSERT INTO release_verdict_issue_results "
                    "(tenant_id,project_id,verdict_id,release_candidate_id,binding_id,issue_id,"
                    "risk_acceptance_record_id,ordinal,issue_category,severity,blocking_category,"
                    "source_finding_id,issue_status,source_provenance,trusted_provenance,blocking,"
                    "hard_blocker,exact_risk_acceptance,risk_authority_verified,"
                    "issue_projection_digest,risk_projection_digest) "
                    "SELECT tenant_id,project_id,:verdict_id,release_candidate_id,binding_id,"
                    "issue_id,risk_acceptance_record_id,ordinal,issue_category,severity,"
                    "blocking_category,source_finding_id,'resolved',source_provenance,"
                    "trusted_provenance,blocking,hard_blocker,exact_risk_acceptance,"
                    "risk_authority_verified,issue_projection_digest,risk_projection_digest "
                    "FROM release_verdict_issue_results WHERE verdict_id=:old_id"
                ),
                {"verdict_id": forged_verdict_id, "old_id": verdict.id},
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    from app.repositories.release_verdicts import ReleaseVerdictRepositoryError

    with pytest.raises(ReleaseVerdictRepositoryError, match="core_issue_projection_stale"):
        await ReleaseVerdictRepository(db_session, tenant_context).evaluate_and_record(
            project_id=ctx["project"],
            release_candidate_id=candidate,
            evidence_pack_id=pack.id,
            actor="slice50-test",
        )
