"""Slice-53 production pre-approval: pure contracts, gate #12, and hard-false boundary."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.identity import AuthenticatedActor
from app.release.production_autonomy import (
    A5_RULESET_VERSION,
    NO_GO_LIVE_REASONS,
    GateResult,
    ProductionAutonomyReport,
    STATUS_PASSED,
    evaluate_production_autonomy,
)
from app.release.production_approval import (
    CONDITIONS_CONTRACT_VERSION,
    POLICY_CONTRACT_VERSION,
    PREAPPROVAL_CONTRACT_VERSION,
    ProductionApprovalContractError,
    actor_evidence,
    canonical_digest,
    fixed_conditions_digest,
    parse_recorded_policy,
    preapproval_is_expired,
    release_binding_digest,
    subject_digest,
)


def _policy(*, approvers: list[str] | None = None) -> dict:
    return {
        "approval_channel": "dashboard",
        "daily_digest_time": "09:00",
        "batch_low_risk_questions": True,
        "realtime_for": [
            "production_deployment",
            "security_exception",
            "cost_overrun",
            "data_access",
            "legal_or_regulatory_decision",
        ],
        "non_response_policy": {
            "low_risk": "proceed_with_safe_assumption_after_24h",
            "medium_risk": "pause_affected_work_after_24h",
            "high_risk": "block_until_approval",
            "production": "block_until_approval",
        },
        "approvers": approvers if approvers is not None else ["release.owner@example.test"],
    }


def _checklist() -> dict:
    return {
        "product": {},
        "engineering": {},
        "ai_and_data": {},
        "security": {},
        "operations": {},
        "governance": {
            "evidence_pack_complete": "required",
            "approval_events_recorded": "required",
            "separation_of_duties_confirmed": "required",
            "open_issues_have_risk_acceptance": "required_if_any_open_issues",
        },
    }


def _gate(report: ProductionAutonomyReport, number: int) -> dict:
    return next(item for item in report.to_dict()["gates"] if item["number"] == number)


def _gate12_kwargs() -> dict:
    return {
        "preapproval_candidate_present": True,
        "preapproval_core_present": True,
        "preapproval_core_reaudited": True,
        "preapproval_verdict_present": True,
        "preapproval_verdict_gate_eligible": True,
        "preapproval_policy_present": True,
        "preapproval_policy_valid": True,
        "preapproval_approver_count": 1,
        "preapproval_autonomy_policy_eligible": True,
        "preapproval_request_present": True,
        "preapproval_binding_current": True,
        "preapproval_requester_authenticated": True,
        "preapproval_notification_valid": True,
        "preapproval_request_status": "approved",
        "preapproval_attestation_present": True,
        "preapproval_approver_authenticated": True,
        "preapproval_approver_in_policy": True,
        "preapproval_separation_ok": True,
        "preapproval_lifecycle_status": "approved_anchor",
        "preapproval_expired": False,
        "preapproval_evidence_consistent": True,
        "preapproval_gate_eligible": True,
        "preapproval_requester_actor_type": "service",
        "preapproval_approver_actor_type": "human",
        "preapproval_policy_contract_version": POLICY_CONTRACT_VERSION,
        "preapproval_condition_contract_version": CONDITIONS_CONTRACT_VERSION,
        "preapproval_contract_version": PREAPPROVAL_CONTRACT_VERSION,
    }


def test_recorded_policy_parses_exact_checked_in_shape_without_upgrading_authority():
    parsed = parse_recorded_policy(_policy(), _checklist())

    assert parsed.policy_contract_version == POLICY_CONTRACT_VERSION
    assert parsed.source_provenance == "caller_supplied_unverified_structured_approval_policy"
    assert parsed.approval_channel == "dashboard"
    assert parsed.production_realtime is True
    assert parsed.production_nonresponse_code == "block_until_approval"
    assert parsed.approver_count == 1
    assert parsed.approver_subject_hashes == (subject_digest("release.owner@example.test"),)
    assert "release.owner@example.test" not in repr(parsed)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p, c: p.update(approval_channel="dashboard | slack | teams | email | ticketing_system"),
        lambda p, c: p.update(approval_channel="email"),
        lambda p, c: p.update(approvers=[]),
        lambda p, c: p.update(approvers=["*"]),
        lambda p, c: p.update(approvers=["role:release-manager"]),
        lambda p, c: p.update(approvers=["same", "same"]),
        lambda p, c: p["realtime_for"].remove("production_deployment"),
        lambda p, c: p["non_response_policy"].update(production="proceed_with_safe_assumption_after_24h"),
        lambda p, c: c["governance"].update(evidence_pack_complete="optional"),
        lambda p, c: p.update(approved=True),
        lambda p, c: c["governance"].update(human_signed=True),
    ],
)
def test_recorded_policy_fails_closed_on_placeholder_missing_authority_or_truth_fields(mutator):
    policy, checklist = _policy(), _checklist()
    mutator(policy, checklist)

    with pytest.raises(ProductionApprovalContractError):
        parse_recorded_policy(policy, checklist)


def test_recorded_policy_rejects_missing_extra_and_more_than_100_approvers():
    for policy, checklist in (
        ({key: value for key, value in _policy().items() if key != "daily_digest_time"}, _checklist()),
        ({**_policy(), "unknown": "value"}, _checklist()),
        (_policy(approvers=[f"principal-{i}" for i in range(101)]), _checklist()),
        (_policy(), {**_checklist(), "unknown": {}}),
    ):
        with pytest.raises(ProductionApprovalContractError):
            parse_recorded_policy(policy, checklist)


def test_digests_are_canonical_and_every_binding_component_matters():
    parsed = parse_recorded_policy(_policy(), _checklist())
    baseline = release_binding_digest(
        release_candidate_id="00000000-0000-0000-0000-000000000001",
        evidence_pack_id="00000000-0000-0000-0000-000000000002",
        release_verdict_id="00000000-0000-0000-0000-000000000003",
        core_content_hash=canonical_digest({"core": 1}),
        issue_binding_digest=canonical_digest({"issues": 1}),
        source_set_digest=canonical_digest({"sources": 1}),
        traceability_digest=canonical_digest({"edges": 1}),
        verdict_input_digest=canonical_digest({"input": 1}),
        verdict_contract_hash=canonical_digest({"verdict": 1}),
        autonomy_policy_digest=canonical_digest({"level": 5}),
        policy_digest=parsed.policy_digest,
        checklist_digest=parsed.checklist_digest,
        condition_contract_hash=fixed_conditions_digest(),
    )
    changed = release_binding_digest(
        release_candidate_id="00000000-0000-0000-0000-000000000009",
        evidence_pack_id="00000000-0000-0000-0000-000000000002",
        release_verdict_id="00000000-0000-0000-0000-000000000003",
        core_content_hash=canonical_digest({"core": 1}),
        issue_binding_digest=canonical_digest({"issues": 1}),
        source_set_digest=canonical_digest({"sources": 1}),
        traceability_digest=canonical_digest({"edges": 1}),
        verdict_input_digest=canonical_digest({"input": 1}),
        verdict_contract_hash=canonical_digest({"verdict": 1}),
        autonomy_policy_digest=canonical_digest({"level": 5}),
        policy_digest=parsed.policy_digest,
        checklist_digest=parsed.checklist_digest,
        condition_contract_hash=fixed_conditions_digest(),
    )

    assert baseline.startswith("sha256:") and len(baseline) == 71
    assert baseline != changed
    assert fixed_conditions_digest() == fixed_conditions_digest()


def test_actor_evidence_is_exact_case_sensitive_and_separated():
    members = (subject_digest("approver@example.test"),)
    result = actor_evidence(
        requester=AuthenticatedActor("release-service", "service"),
        approver=AuthenticatedActor("approver@example.test", "human"),
        member_subject_hashes=members,
    )
    wrong_case = actor_evidence(
        requester=AuthenticatedActor("release-service", "service"),
        approver=AuthenticatedActor("Approver@example.test", "human"),
        member_subject_hashes=members,
    )

    assert result.requester_authenticated and result.approver_authenticated
    assert result.approver_in_policy and result.separation_ok and result.gate_eligible
    assert wrong_case.approver_in_policy is False
    assert wrong_case.gate_eligible is False


@pytest.mark.parametrize(
    ("requester", "approver"),
    [
        (None, AuthenticatedActor("approver@example.test", "human")),
        (AuthenticatedActor("requester", "human"), None),
        (AuthenticatedActor("same", "human"), AuthenticatedActor("same", "human")),
        (AuthenticatedActor("requester", "human"), AuthenticatedActor("approver@example.test", "service")),
    ],
)
def test_actor_evidence_fails_closed_on_missing_self_or_service_approver(requester, approver):
    result = actor_evidence(
        requester=requester,
        approver=approver,
        member_subject_hashes=(subject_digest("approver@example.test"), subject_digest("same")),
    )
    assert result.gate_eligible is False


def test_expiry_is_utc_injected_and_expires_at_the_boundary():
    approved = datetime(2026, 7, 14, 10, tzinfo=timezone.utc)
    expires = approved + timedelta(hours=24)

    assert preapproval_is_expired(expires, expires - timedelta(microseconds=1)) is False
    assert preapproval_is_expired(expires, expires) is True
    assert preapproval_is_expired(expires, expires + timedelta(microseconds=1)) is True
    with pytest.raises(ProductionApprovalContractError):
        preapproval_is_expired(expires.replace(tzinfo=None), expires)


def test_gate12_passes_only_for_the_exact_ruled_evidence_state():
    report = evaluate_production_autonomy("project", readiness_level="R5", **_gate12_kwargs())
    gate = _gate(report, 12)

    assert gate["status"] == "passed"
    assert gate["reason"] == "passed:request_authenticated_preapproval_under_recorded_conditions"
    assert report.to_dict()["ruleset_version"] == A5_RULESET_VERSION == "slice53.v1"
    assert report.to_dict()["a5_satisfied"] is False
    assert report.to_dict()["can_go_live_autonomously"] is False
    assert NO_GO_LIVE_REASONS == ("a5_gates_not_all_satisfied",)


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"preapproval_candidate_present": False}, "no_current_frozen_release_candidate"),
        ({"preapproval_core_present": False}, "no_complete_reauditable_evidence_core"),
        ({"preapproval_core_reaudited": False}, "release_core_reaudit_failed"),
        ({"preapproval_verdict_present": False}, "no_current_gate_eligible_release_verdict"),
        ({"preapproval_policy_present": False}, "release_approval_policy_missing_or_invalid"),
        ({"preapproval_approver_count": 0}, "release_approval_policy_has_no_exact_approver"),
        ({"preapproval_autonomy_policy_eligible": False}, "a5_autonomy_policy_missing_or_ineligible"),
        ({"preapproval_request_present": False}, "no_production_preapproval_request_for_current_binding"),
        ({"preapproval_binding_current": False}, "latest_preapproval_request_binding_stale_or_inconsistent"),
        ({"preapproval_requester_authenticated": False}, "preapproval_requester_not_request_authenticated"),
        ({"preapproval_notification_valid": False}, "production_approval_notification_missing_or_invalid"),
        ({"preapproval_request_status": "pending"}, "production_preapproval_pending"),
        ({"preapproval_request_status": "rejected"}, "production_preapproval_rejected_or_cancelled"),
        ({"preapproval_approver_authenticated": False}, "preapproval_approver_not_request_authenticated"),
        ({"preapproval_approver_in_policy": False}, "preapproval_approver_not_in_recorded_policy"),
        ({"preapproval_separation_ok": False}, "preapproval_separation_of_duties_failed"),
        ({"preapproval_lifecycle_status": "revoked"}, "production_preapproval_revoked_or_superseded"),
        ({"preapproval_expired": True}, "production_preapproval_expired"),
        ({"preapproval_evidence_consistent": False}, "production_preapproval_evidence_inconsistent"),
    ],
)
def test_gate12_twenty_rung_ladder_is_fail_closed_and_ordered(updates, reason):
    kwargs = _gate12_kwargs()
    kwargs.update(updates)
    gate = _gate(evaluate_production_autonomy("project", readiness_level="R5", **kwargs), 12)

    assert gate["status"] == "insufficient_evidence"
    assert gate["reason"] == f"insufficient_evidence:{reason}"


def test_gate12_newest_negative_state_cannot_fall_back_to_an_older_pass():
    kwargs = _gate12_kwargs()
    kwargs.update(preapproval_request_status="cancelled", preapproval_attestation_present=False)
    gate = _gate(evaluate_production_autonomy("project", readiness_level="R5", **kwargs), 12)
    assert gate["reason"] == "insufficient_evidence:production_preapproval_rejected_or_cancelled"


def test_slice53_golden_matrix_changes_only_gate12_and_no_go_tuple():
    before = evaluate_production_autonomy("project", readiness_level="R5").to_dict()
    after = evaluate_production_autonomy("project", readiness_level="R5", **_gate12_kwargs()).to_dict()

    before_gates = {gate["number"]: gate for gate in before["gates"]}
    after_gates = {gate["number"]: gate for gate in after["gates"]}
    assert {number: gate for number, gate in before_gates.items() if number != 12} == {
        number: gate for number, gate in after_gates.items() if number != 12
    }
    assert before_gates[12] != after_gates[12]
    assert after_gates[13]["reason"] == "no_evidence_source:emergency_stop"
    assert after["can_go_live_reasons"] == ["a5_gates_not_all_satisfied"]


def test_literal_hard_false_survives_even_a_synthetic_all_thirteen_pass_report():
    report = ProductionAutonomyReport(
        project_id="synthetic",
        gates=[GateResult(number, f"gate-{number}", STATUS_PASSED, "synthetic") for number in range(1, 14)],
    ).to_dict()

    assert report["a5_satisfied"] is True
    assert report["can_go_live_autonomously"] is False
    assert report["can_go_live_reasons"] == ["a5_gates_not_all_satisfied"]


def test_safe_gate_context_contains_no_principal_hash_or_release_digest():
    gate = _gate(evaluate_production_autonomy("project", readiness_level="R5", **_gate12_kwargs()), 12)
    forbidden = {"principal", "subject", "digest", "hash", "repo", "commit", "credential", "token"}
    assert not any(fragment in key.lower() for key in gate["context"] for fragment in forbidden)
    assert "human" not in gate["reason"] and "signed" not in gate["reason"]


def test_narrow_api_declares_no_request_body_or_caller_truth_schema():
    from app.main import app

    schema = app.openapi()
    mutation_paths = [
        path
        for path in schema["paths"]
        if "/production-preapprovals/" in path and "current" not in path
    ]
    assert len(mutation_paths) == 5
    for path in mutation_paths:
        assert "requestBody" not in schema["paths"][path]["post"]


@pytest.mark.asyncio
async def test_narrow_api_rejects_any_caller_body_with_a_generic_safe_error():
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.api.production_preapprovals import _empty_body

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {
            "type": "http.request",
            "body": b'{"approved":true,"actor":"SENTINEL_PRINCIPAL"}',
            "more_body": False,
        }

    request = Request({"type": "http", "method": "POST", "path": "/"}, receive)
    with pytest.raises(HTTPException) as rejected:
        await _empty_body(request)
    assert rejected.value.status_code == 409
    assert rejected.value.detail == "production preapproval unavailable"
    assert "SENTINEL" not in rejected.value.detail


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


def _zero_inventories():
    from app.release.evidence_pack import (
        INVENTORY_SECTIONS,
        SectionInventory,
        canonical_json_bytes,
        digest_bytes,
    )

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


@pytest_asyncio.fixture
async def production_preapproval_ctx(db_session):
    from app.identity import AuthenticatedActor
    from app.release.evidence_pack import (
        assemble_core,
        canonical_json_bytes,
        derive_repo_commit_binding,
        digest_bytes,
    )
    from app.repositories.evidence_packs import EvidencePackRepository
    from app.repositories.release_verdicts import ReleaseVerdictRepository
    from app.tenancy import TenantContext

    suffix = uuid.uuid4().hex[:10]
    organization = await _scalar(
        db_session,
        "INSERT INTO organizations (name,slug) VALUES ('PreapprovalOrg',:slug) RETURNING id",
        slug=f"preapproval-org-{suffix}",
    )
    tenant = await _scalar(
        db_session,
        "INSERT INTO tenants (organization_id,name,slug) VALUES (:org,'PreapprovalTenant',:slug) RETURNING id",
        org=organization,
        slug=f"preapproval-tenant-{suffix}",
    )
    project = await _scalar(
        db_session,
        "INSERT INTO projects (tenant_id,name,slug) VALUES (:tenant,'PreapprovalProject',:slug) RETURNING id",
        tenant=tenant,
        slug=f"preapproval-project-{suffix}",
    )
    candidate = await _scalar(
        db_session,
        "INSERT INTO release_candidates (tenant_id,project_id,release_ref,status) "
        "VALUES (:tenant,:project,:ref,'draft') RETURNING id",
        tenant=tenant,
        project=project,
        ref=f"preapproval-release-{suffix}",
    )
    await db_session.execute(
        text("UPDATE release_candidates SET status='frozen',frozen_at=clock_timestamp() WHERE id=:id"),
        {"id": candidate},
    )
    await db_session.execute(
        text("SELECT set_config('app.current_tenant',:tenant,true)"), {"tenant": str(tenant)}
    )
    await db_session.execute(
        text("SELECT * FROM audit_append('slice53-test','seed',NULL,'{}'::jsonb)")
    )
    frozen_at = await _scalar(
        db_session, "SELECT frozen_at FROM release_candidates WHERE id=:id", id=candidate
    )
    system_context = TenantContext(tenant)
    packs = EvidencePackRepository(db_session, system_context)
    checkpoint = await packs.record_audit_checkpoint()
    inventories = _zero_inventories()
    empty_digest = digest_bytes(canonical_json_bytes([]))
    core = assemble_core(
        project_id=project,
        release_candidate_id=candidate,
        release_ref_digest="sha256:" + "a" * 64,
        generated_at=checkpoint.created_at,
        frozen_at=frozen_at,
        artifact_scope_digest="sha256:" + "b" * 64,
        issue_binding_digest=empty_digest,
        source_refs=(),
        inventories=inventories,
        traceability=(),
        audit_checkpoint=checkpoint,
        repo_commit_binding=derive_repo_commit_binding([]),
    )
    pack = await packs._persist_core(
        project_id=project,
        release_candidate_id=candidate,
        core=core,
        source_refs=(),
        inventories=inventories,
        traceability_edge_count=0,
        actor="slice53_seed",
    )
    verdict = await ReleaseVerdictRepository(db_session, system_context).evaluate_and_record(
        project_id=project,
        release_candidate_id=candidate,
        evidence_pack_id=pack.id,
        actor="slice53_seed",
    )
    policy = _policy(
        approvers=[
            "requester@example.test",
            "approver@example.test",
            "self@example.test",
        ]
    )
    checklist = _checklist()
    await db_session.execute(
        text(
            "INSERT INTO intake_categories "
            "(tenant_id,project_id,category,status,data,origin) VALUES "
            "(:tenant,:project,'human_approval_policy','declared',CAST(:policy AS jsonb),'slice53_test'),"
            "(:tenant,:project,'go_live_checklist','declared',CAST(:checklist AS jsonb),'slice53_test')"
        ),
        {
            "tenant": tenant,
            "project": project,
            "policy": json.dumps(policy),
            "checklist": json.dumps(checklist),
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO autonomy_policies (tenant_id,project_id,autonomy_level,overrides) "
            "VALUES (:tenant,:project,5,'{}'::jsonb)"
        ),
        {"tenant": tenant, "project": project},
    )
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    return {
        "tenant": tenant,
        "project": project,
        "candidate": candidate,
        "pack": pack.id,
        "verdict": verdict.id,
        "requester_context": TenantContext(
            tenant, actor=AuthenticatedActor("requester@example.test", "service")
        ),
        "approver_context": TenantContext(
            tenant, actor=AuthenticatedActor("approver@example.test", "human")
        ),
        "self_context": TenantContext(
            tenant, actor=AuthenticatedActor("self@example.test", "human")
        ),
    }


@pytest.mark.db
async def test_request_authenticated_workflow_passes_gate12_but_remains_hard_false(
    production_preapproval_ctx, db_session
):
    from app.release.production_approval_service import ProductionApprovalService
    from app.repositories.production_preapprovals import ProductionPreapprovalRepository

    ctx = production_preapproval_ctx
    requested = await ProductionApprovalService(
        db_session, ctx["requester_context"]
    ).request(project_id=ctx["project"], idempotency_key="request-1")
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    approved = await ProductionApprovalService(
        db_session, ctx["approver_context"]
    ).approve(
        project_id=ctx["project"],
        request_id=requested.request_id,
        idempotency_key="approve-1",
    )
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    repo = ProductionPreapprovalRepository(db_session, ctx["requester_context"])
    coverage = await repo.coverage_for_project(ctx["project"])
    report = evaluate_production_autonomy(
        ctx["project"], readiness_level="R5", **coverage.gate_kwargs()
    ).to_dict()
    gate12 = next(gate for gate in report["gates"] if gate["number"] == 12)
    assert approved.status == "approved"
    assert gate12["status"] == "passed"
    assert gate12["reason"] == "passed:request_authenticated_preapproval_under_recorded_conditions"
    assert report["can_go_live_autonomously"] is False
    assert report["can_go_live_reasons"] == ["a5_gates_not_all_satisfied"]
    assert next(gate for gate in report["gates"] if gate["number"] == 13)["reason"] == (
        "no_evidence_source:emergency_stop"
    )

    attestation = await repo.get_attestation(ctx["project"], approved.attestation_id)
    expired = await repo.coverage_for_project(ctx["project"], as_of=attestation.expires_at)
    expired_gate = _gate(
        evaluate_production_autonomy(
            ctx["project"], readiness_level="R5", **expired.gate_kwargs()
        ),
        12,
    )
    assert expired_gate["reason"] == "insufficient_evidence:production_preapproval_expired"

    audit_surface = await _scalar(
        db_session,
        "SELECT COALESCE(string_agg(actor||' '||payload::text,' '),'') FROM audit_logs "
        "WHERE action LIKE 'production_preapproval.%' OR action LIKE 'approval.%' "
        "OR action='approval.notification_recorded'",
    )
    assert "requester@example.test" not in audit_surface
    assert "approver@example.test" not in audit_surface
    assert "human signature" not in audit_surface.lower()

    with pytest.raises(DBAPIError, match="cannot downgrade Slice 53"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "DO $fn$ BEGIN IF EXISTS "
                    "(SELECT 1 FROM production_preapproval_requests) THEN "
                    "RAISE EXCEPTION 'cannot downgrade Slice 53 while production preapproval rows exist'; "
                    "END IF; END $fn$"
                )
            )


@pytest.mark.db
async def test_newest_pending_or_rejected_request_supersedes_an_older_pass(
    production_preapproval_ctx, db_session
):
    from app.release.production_approval_service import ProductionApprovalService
    from app.repositories.production_preapprovals import ProductionPreapprovalRepository

    ctx = production_preapproval_ctx
    requester = ProductionApprovalService(db_session, ctx["requester_context"])
    first = await requester.request(project_id=ctx["project"], idempotency_key="first-request")
    await ProductionApprovalService(db_session, ctx["approver_context"]).approve(
        project_id=ctx["project"], request_id=first.request_id, idempotency_key="first-approve"
    )
    second = await requester.request(project_id=ctx["project"], idempotency_key="second-request")
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    repo = ProductionPreapprovalRepository(db_session, ctx["requester_context"])
    pending = await repo.coverage_for_project(ctx["project"])
    pending_gate = _gate(
        evaluate_production_autonomy(
            ctx["project"], readiness_level="R5", **pending.gate_kwargs()
        ),
        12,
    )
    assert pending.request_id == second.request_id
    assert pending_gate["reason"] == "insufficient_evidence:production_preapproval_pending"

    await ProductionApprovalService(db_session, ctx["approver_context"]).reject(
        project_id=ctx["project"], request_id=second.request_id, idempotency_key="second-reject"
    )
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    rejected = await repo.coverage_for_project(ctx["project"])
    rejected_gate = _gate(
        evaluate_production_autonomy(
            ctx["project"], readiness_level="R5", **rejected.gate_kwargs()
        ),
        12,
    )
    assert rejected_gate["reason"] == (
        "insufficient_evidence:production_preapproval_rejected_or_cancelled"
    )


@pytest.mark.db
async def test_direct_sql_self_approval_graph_is_rejected_at_commit(
    production_preapproval_ctx, db_session
):
    from app.release.production_approval_service import ProductionApprovalService
    from app.release.production_approval import canonical_digest, subject_digest

    ctx = production_preapproval_ctx
    requested = await ProductionApprovalService(db_session, ctx["self_context"]).request(
        project_id=ctx["project"], idempotency_key="self-request"
    )
    request = (
        await db_session.execute(
            text("SELECT * FROM production_preapproval_requests WHERE id=:id"),
            {"id": requested.request_id},
        )
    ).mappings().one()
    self_hash = subject_digest("self@example.test")
    with pytest.raises(DBAPIError, match="production preapproval"):
        async with db_session.begin_nested():
            resolved_at = await _scalar(
                db_session,
                "UPDATE approvals SET status='approved',resolved_by=:actor,"
                "approver_provenance='request_authenticated',resolved_at=clock_timestamp() "
                "WHERE id=:id RETURNING resolved_at",
                actor=self_hash,
                id=request["generic_approval_id"],
            )
            attestation_id = await _scalar(
                db_session,
                "INSERT INTO production_preapproval_attestations "
                "(tenant_id,project_id,request_id,generic_approval_id,policy_version_id,"
                "release_candidate_id,evidence_pack_id,release_verdict_id,requester_subject_hash,"
                "requester_actor_type,requester_provenance,approver_subject_hash,approver_actor_type,"
                "approver_provenance,resolution_idempotency_key_hash,approved_at,valid_from,expires_at,"
                "policy_membership_ok) VALUES "
                "(:tenant,:project,:request,:approval,:policy,:candidate,:pack,:verdict,:requester,"
                "'human','request_authenticated',:approver,'human','request_authenticated',:idem,"
                ":approved,:approved,:expires,true) RETURNING id",
                tenant=ctx["tenant"],
                project=ctx["project"],
                request=requested.request_id,
                approval=request["generic_approval_id"],
                policy=request["policy_version_id"],
                candidate=request["release_candidate_id"],
                pack=request["evidence_pack_id"],
                verdict=request["release_verdict_id"],
                requester=self_hash,
                approver=self_hash,
                idem=canonical_digest({"idem": "forged-self"}),
                approved=resolved_at,
                expires=resolved_at + timedelta(hours=1),
            )
            await db_session.execute(
                text(
                    "INSERT INTO production_preapproval_lifecycle_events "
                    "(tenant_id,project_id,attestation_id,event_type,actor_subject_hash,actor_type,"
                    "actor_provenance,reason_code,idempotency_key_hash) VALUES "
                    "(:tenant,:project,:attestation,'approved_anchor',:actor,'human',"
                    "'request_authenticated','forged_anchor',:idem)"
                ),
                {
                    "tenant": ctx["tenant"],
                    "project": ctx["project"],
                    "attestation": attestation_id,
                    "actor": self_hash,
                    "idem": canonical_digest({"idem": "forged-anchor"}),
                },
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.db
async def test_slice53_catalog_rls_generated_truth_and_findings_guard_pin(admin_engine):
    tables = {
        "production_approval_policy_versions",
        "production_approval_policy_approvers",
        "production_preapproval_requests",
        "production_preapproval_attestations",
        "production_preapproval_lifecycle_events",
    }
    async with admin_engine.connect() as conn:
        catalog = (
            await conn.execute(
                text(
                    "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                    "WHERE relname=ANY(:tables) ORDER BY relname"
                ),
                {"tables": sorted(tables)},
            )
        ).all()
        assert {row[0] for row in catalog} == tables
        assert all(row[1] and row[2] for row in catalog)
        generated = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT attname FROM pg_attribute WHERE attrelid="
                        "'production_preapproval_attestations'::regclass AND attgenerated='s'"
                    )
                )
            ).all()
        }
        assert generated == {
            "attestation_result",
            "identity_separation_ok",
            "gate_eligible_at_creation",
        }
        guard_md5 = await conn.scalar(
            text("SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))")
        )
        assert guard_md5 == "808036faf2660d6810aeca4342e6f1ac"
