from __future__ import annotations

import copy
import hashlib

import pytest
import pytest_asyncio
from sqlalchemy import text

from tests.reviewer_quality_support import seed_current_reviewer_quality


def _evidence(**overrides):
    from app.verify.acceptance import AuthorshipEvidence

    values = {
        "acceptance_criterion_id": "00000000-0000-0000-0000-000000000001",
        "authorship_status": "system_authored_independent_approved",
        "authorship_provenance": "db_verified_independent_agent_lineage",
        "source_kind": "agent_generated",
        "approval_basis": "independent_agent_lineage",
        "source_db_proven": True,
        "approval_db_bound": True,
        "reviewer_active": True,
        "reviewer_qualified": True,
        "distinct_blueprint": True,
        "distinct_version": True,
        "distinct_model_route": True,
        "current_record": True,
    }
    values.update(overrides)
    return AuthorshipEvidence(**values)


def test_independent_agent_lineage_is_the_only_gate_eligible_approval_path():
    from app.verify.acceptance import evaluate_authorship

    result = evaluate_authorship(_evidence())
    assert result.eligibility_status == "eligible"
    assert result.reason_code == "verified_independent_agent_approval"

    for change in (
        {"authorship_provenance": "caller_supplied_unverified"},
        {"approval_basis": "human_owner"},
        {"approval_db_bound": False},
        {"reviewer_active": False},
        {"reviewer_qualified": False},
        {"distinct_blueprint": False},
        {"distinct_version": False},
        {"distinct_model_route": False},
    ):
        assert evaluate_authorship(_evidence(**change)).eligibility_status == "untrusted"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("system_authored_unapproved", "unapproved"),
        ("disputed", "disputed"),
        ("system_authored_human_approved", "untrusted"),
        ("user_authored", "untrusted"),
        ("user_authored_system_normalized", "untrusted"),
    ],
)
def test_unapproved_disputed_human_and_unknown_paths_fail_closed(status, expected):
    from app.verify.acceptance import evaluate_authorship

    assert evaluate_authorship(_evidence(authorship_status=status)).eligibility_status == expected


def test_schema_rejects_unknown_fields_and_caller_truth_flags():
    from app.verify.acceptance import InvalidAcceptanceEvidence, validate_authorship_payload

    payload = {
        "acceptance_criterion_id": "00000000-0000-0000-0000-000000000001",
        "authorship_status": "system_authored_unapproved",
        "source_kind": "extraction_promoted",
        "source_reference": "00000000-0000-0000-0000-000000000002",
        "evidence_reference": "sha256:" + "a" * 64,
    }
    validated = validate_authorship_payload(payload)
    assert validated["authorship_status"] == "system_authored_unapproved"
    for forbidden in ("eligible", "complete", "passed", "trusted", "gate"):
        forged = copy.deepcopy(payload)
        forged[forbidden] = True
        with pytest.raises(InvalidAcceptanceEvidence, match="unknown or missing"):
            validate_authorship_payload(forged)


def test_scope_and_authorship_digests_are_canonical_and_order_independent():
    from app.verify.acceptance import authorship_digest, scope_digest

    ac1 = "00000000-0000-0000-0000-000000000001"
    ac2 = "00000000-0000-0000-0000-000000000002"
    assert scope_digest([ac2, ac1]) == scope_digest([ac1, ac2])
    chain = [(ac1, 1, "system_authored_unapproved"), (ac2, 2, "disputed")]
    assert authorship_digest(reversed(chain)) == authorship_digest(chain)


def _gate8(**overrides):
    from app.release.production_autonomy import evaluate_production_autonomy

    values = {
        "acceptance_scope_resolved": True,
        "acceptance_binding_resolved": True,
        "acceptance_scope_count": 1,
        "acceptance_verification_run_present": True,
        "acceptance_verification_failed": False,
        "acceptance_missing_authorship_count": 0,
        "acceptance_untrusted_count": 0,
        "acceptance_disputed_count": 0,
        "acceptance_unapproved_count": 0,
        "acceptance_controls_failed_count": 0,
        "acceptance_eligible_count": 1,
        "acceptance_evidence_consistent": True,
    }
    values.update(overrides)
    report = evaluate_production_autonomy("project", readiness_level="R0", **values)
    return next(gate for gate in report.gates if gate.number == 8)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"acceptance_scope_resolved": False}, "insufficient_evidence:acceptance_scope_unresolved"),
        ({"acceptance_binding_resolved": False}, "insufficient_evidence:acceptance_binding_unresolved"),
        ({"acceptance_scope_count": 0}, "insufficient_evidence:no_proven_release_gating_acceptance_scope"),
        ({"acceptance_verification_run_present": False}, "insufficient_evidence:acceptance_verification_not_run"),
        ({"acceptance_verification_failed": True}, "insufficient_evidence:acceptance_verification_failed"),
        ({"acceptance_missing_authorship_count": 1, "acceptance_eligible_count": 0}, "insufficient_evidence:acceptance_authorship_missing"),
        ({"acceptance_untrusted_count": 1, "acceptance_eligible_count": 0}, "insufficient_evidence:authorship_approval_unverified"),
        ({"acceptance_disputed_count": 1, "acceptance_eligible_count": 0}, "insufficient_evidence:disputed_acceptance_criteria_in_release_scope"),
        ({"acceptance_unapproved_count": 1, "acceptance_eligible_count": 0}, "insufficient_evidence:unapproved_generated_acceptance_criteria_in_release_scope"),
        ({"acceptance_controls_failed_count": 1, "acceptance_eligible_count": 0}, "insufficient_evidence:acceptance_authorship_controls_failed"),
        ({"acceptance_evidence_consistent": False}, "insufficient_evidence:acceptance_evidence_inconsistent"),
    ],
)
def test_gate8_fail_closed_ladder(change, reason):
    assert _gate8(**change).reason == reason


def test_gate8_pass_is_narrow_and_go_live_remains_false():
    from app.release.production_autonomy import A5_RULESET_VERSION, evaluate_production_autonomy

    gate = _gate8()
    assert gate.status == "passed"
    assert gate.reason == "passed:no_unapproved_generated_acceptance_criteria_in_critical_gates_verified"
    report = evaluate_production_autonomy(
        "project",
        readiness_level="R0",
        acceptance_scope_resolved=True,
        acceptance_binding_resolved=True,
        acceptance_scope_count=1,
        acceptance_verification_run_present=True,
        acceptance_eligible_count=1,
        acceptance_evidence_consistent=True,
    )
    assert A5_RULESET_VERSION == "slice50.v1"
    assert report.a5_satisfied is False
    assert report.to_dict()["can_go_live_autonomously"] is False


def test_slice46_changes_only_gate8_for_identical_other_inputs():
    from app.release.production_autonomy import evaluate_production_autonomy

    before = evaluate_production_autonomy("project", readiness_level="R5").to_dict()
    after = evaluate_production_autonomy(
        "project",
        readiness_level="R5",
        acceptance_scope_resolved=True,
        acceptance_binding_resolved=True,
        acceptance_scope_count=1,
        acceptance_verification_run_present=True,
        acceptance_eligible_count=1,
        acceptance_evidence_consistent=True,
    ).to_dict()
    before_other = [gate for gate in before["gates"] if gate["number"] != 8]
    after_other = [gate for gate in after["gates"] if gate["number"] != 8]
    assert before_other == after_other


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


@pytest_asyncio.fixture
async def acceptance_db_ctx(admin_engine):
    suffix = __import__("uuid").uuid4().hex[:8]
    async with admin_engine.begin() as conn:
        org = await _scalar(
            conn,
            "INSERT INTO organizations (name,slug) VALUES ('AcceptanceOrg',:s) RETURNING id",
            s=f"acceptance-org-{suffix}",
        )
        tenant = await _scalar(
            conn,
            "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'T1',:s) RETURNING id",
            o=org,
            s=f"acceptance-t-{suffix}",
        )
        project = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P1',:s) RETURNING id",
            t=tenant,
            s=f"acceptance-p-{suffix}",
        )
        requirement = await _scalar(
            conn,
            "INSERT INTO intake_artifacts (tenant_id,project_id,kind,ref,title,data) "
            "VALUES (:t,:p,'requirement','REQ-1','Requirement','{}') RETURNING id",
            t=tenant,
            p=project,
        )
        await conn.execute(
            text(
                "INSERT INTO intake_provenance (tenant_id,project_id,artifact_id,origin) "
                "VALUES (:t,:p,:a,'db-test')"
            ),
            {"t": tenant, "p": project, "a": requirement},
        )
        ac = await _scalar(
            conn,
            "INSERT INTO intake_artifacts (tenant_id,project_id,kind,ref,title,data,parent_id) "
            "VALUES (:t,:p,'acceptance_criterion','AC-1','SENTINEL_ACCEPTANCE_SECRET','{}',:r) RETURNING id",
            t=tenant,
            p=project,
            r=requirement,
        )
        await conn.execute(
            text(
                "INSERT INTO intake_provenance (tenant_id,project_id,artifact_id,origin) "
                "VALUES (:t,:p,:a,'db-test')"
            ),
            {"t": tenant, "p": project, "a": ac},
        )
    return {"tenant": tenant, "project": project, "requirement": requirement, "ac": ac, "suffix": suffix}


@pytest.mark.db
async def test_acceptance_tables_are_rls_forced_append_only(acceptance_db_ctx, admin_engine):
    async with admin_engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('acceptance_criterion_authorship_records',"
                    "'acceptance_verification_runs','acceptance_verification_results') ORDER BY relname"
                )
            )
        ).all()
        assert rows == [
            ("acceptance_criterion_authorship_records", True, True),
            ("acceptance_verification_results", True, True),
            ("acceptance_verification_runs", True, True),
        ]
        guard = await _scalar(
            conn,
            "SELECT pg_get_functiondef('release_findings_guard()'::regprocedure)",
        )
        assert "shortcut_detector_category_result_id" in guard
        assert "security_scan_category_result_id" in guard


@pytest.mark.db
async def test_direct_sql_rejects_non_ac_and_forked_authorship_chain(acceptance_db_ctx, admin_engine):
    ctx = acceptance_db_ctx
    with pytest.raises(Exception, match="canonical acceptance criterion"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO acceptance_criterion_authorship_records "
                    "(tenant_id,project_id,acceptance_criterion_id,sequence,authorship_status,"
                    "authorship_provenance,source_kind,evidence_reference) VALUES "
                    "(:t,:p,:a,1,'system_authored_unapproved','caller_supplied_unverified',"
                    "'extraction_promoted',:e)"
                ),
                {"t": ctx["tenant"], "p": ctx["project"], "a": ctx["requirement"], "e": "sha256:" + "a" * 64},
            )


@pytest.mark.db
async def test_direct_sql_rejects_forged_independent_approval(acceptance_db_ctx, admin_engine):
    ctx = acceptance_db_ctx
    with pytest.raises(Exception, match="verified independent-agent evidence"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO acceptance_criterion_authorship_records "
                    "(tenant_id,project_id,acceptance_criterion_id,sequence,authorship_status,"
                    "authorship_provenance,source_kind,approval_basis,evidence_reference) VALUES "
                    "(:t,:p,:a,1,'system_authored_independent_approved',"
                    "'db_verified_independent_agent_lineage','agent_generated',"
                    "'independent_agent_lineage',:e)"
                ),
                {"t": ctx["tenant"], "p": ctx["project"], "a": ctx["ac"], "e": "sha256:" + "b" * 64},
            )


async def _seed_agent_pair_and_approval(admin_engine, ctx):
    h = "sha256:" + "a" * 64
    async with admin_engine.begin() as conn:
        ids = []
        for archetype, key, model in (("builder", "generator", "model-a"), ("reviewer", "reviewer", "model-b")):
            blueprint = await _scalar(
                conn,
                "INSERT INTO agent_blueprints (key,role,mission,archetype) VALUES "
                "(:k,:r,'Acceptance verification',:a) RETURNING id",
                k=f"acceptance-{key}-{ctx['suffix']}",
                r=key.title(),
                a=archetype,
            )
            version = await _scalar(
                conn,
                "INSERT INTO agent_versions (blueprint_id,version_label,model_route,prompt_hash,"
                "tool_policy_hash,context_policy_hash,eval_suite_hash,critical_dependencies_hash,"
                "output_schema_hash,content_hash) VALUES (:b,'v1',:m,:h,:h,:h,:h,:h,:h,:ch) RETURNING id",
                b=blueprint,
                m=model,
                h=h,
                ch="sha256:" + hashlib.sha256(f"{key}-{ctx['suffix']}".encode()).hexdigest(),
            )
            instance = await _scalar(
                conn,
                "INSERT INTO agent_instances (tenant_id,project_id,version_id,instance_key,status) "
                "VALUES (:t,:p,:v,:k,'active') RETURNING id",
                t=ctx["tenant"], p=ctx["project"], v=version, k=key,
            )
            ids.append(instance)
        realization = await _scalar(
            conn,
            "INSERT INTO agent_realizations (tenant_id,project_id,instance_id,qualification_status,realized_by) "
            "VALUES (:t,:p,:i,'unqualified','db-test') RETURNING id",
            t=ctx["tenant"], p=ctx["project"], i=ids[1],
        )
        eval_id = await _scalar(conn, "SELECT id FROM archetype_evals WHERE archetype='reviewer' AND eval_version='v1'")
        run = await _scalar(
            conn,
            "INSERT INTO qualification_runs (tenant_id,project_id,realization_id,archetype_eval_id,"
            "archetype,eval_version,min_aggregate_score,require_zero_critical,min_cases,required_categories,"
            "total_cases,passed_cases,critical_failure_count,coverage_complete,evaluated_by) VALUES "
            "(:t,:p,:r,:e,'reviewer','v1',0.900,true,5,'[\"positive\",\"negative\",\"edge\",\"adversarial\",\"incomplete\"]'::jsonb,5,5,0,true,'db-test') RETURNING id",
            t=ctx["tenant"], p=ctx["project"], r=realization, e=eval_id,
        )
        for index, category in enumerate(("positive", "negative", "edge", "adversarial", "incomplete")):
            await conn.execute(
                text("INSERT INTO qualification_case_results (tenant_id,project_id,run_id,case_ref,case_category,passed,is_critical) VALUES (:t,:p,:r,:ref,:c,true,false)"),
                {"t": ctx["tenant"], "p": ctx["project"], "r": run, "ref": f"acceptance-{index}", "c": category},
            )
        await conn.execute(text("UPDATE agent_realizations SET qualification_status='qualified',qualified_via_run_id=:q WHERE id=:r"), {"q": run, "r": realization})
        await seed_current_reviewer_quality(
            conn,
            tenant_id=ctx["tenant"],
            project_id=ctx["project"],
            reviewer_instance_id=ids[1],
        )
        approval = await _scalar(
            conn,
            "INSERT INTO approvals (tenant_id,project_id,action,subject_ref,risk_tier,requires_explicit_approval,"
            "status,requested_by,requested_by_provenance,resolved_by,approver_provenance,resolved_at,reason) VALUES "
            "(:t,:p,'approve_acceptance_authorship',:s,'high',true,'approved',:g,'request_authenticated',"
            ":r,'request_authenticated',now(),'db-bound decision') RETURNING id",
            t=ctx["tenant"], p=ctx["project"], s=f"acceptance_criterion:{ctx['ac']}", g=str(ids[0]), r=str(ids[1]),
        )
    return ids[0], ids[1], approval


@pytest.mark.db
async def test_repository_records_db_bound_approval_and_gate8_coverage(acceptance_db_ctx, admin_engine):
    from app.repositories.acceptance_verification import AcceptanceVerificationRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = acceptance_db_ctx
    generator, reviewer, approval = await _seed_agent_pair_and_approval(admin_engine, ctx)
    tenant = TenantContext(ctx["tenant"])
    async with tenant_scope(tenant) as session:
        repo = AcceptanceVerificationRepository(session, tenant)
        record = await repo.record_independent_approval(
            project_id=ctx["project"], acceptance_criterion_id=ctx["ac"],
            generator_instance_id=generator, reviewer_instance_id=reviewer,
            approval_id=approval, evidence_reference="sha256:" + "c" * 64, actor="db-test",
        )
        assert record.authorship_status == "system_authored_independent_approved"
        run = await repo.verify_project(ctx["project"], actor="db-test")
        assert run.verdict == "eligible"
        coverage = await repo.coverage_for_project(ctx["project"])
        assert coverage.eligible_count == 1
        assert coverage.evidence_consistent is True
        await repo.record_failed_verification(
            ctx["project"], failure_code="structural_execution_failed", actor="db-test"
        )
        later = await repo.coverage_for_project(ctx["project"])
        assert later.verification_failed is True
        assert later.eligible_count == 0
    async with admin_engine.begin() as conn:
        audit_text = " ".join(
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT payload::text FROM audit_logs WHERE tenant_id=:t "
                        "AND action LIKE 'acceptance.%'"
                    ),
                    {"t": ctx["tenant"]},
                )
            ).all()
        )
        assert "SENTINEL_ACCEPTANCE_SECRET" not in audit_text
        assert "db-bound decision" not in audit_text
        assert "sha256:" + "c" * 64 not in audit_text


@pytest.mark.db
async def test_direct_sql_rejects_success_without_results(acceptance_db_ctx, admin_engine):
    from app.verify.acceptance import verifier_contract_hash

    ctx = acceptance_db_ctx
    with pytest.raises(Exception, match="aggregate mismatch"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO acceptance_verification_runs (tenant_id,project_id,scope_digest,"
                    "authorship_digest,schema_version,verifier_contract_hash,execution_status,"
                    "execution_provenance,failure_code,reported_scope_count,reported_eligible_count,"
                    "reported_unapproved_count,reported_disputed_count,reported_missing_or_untrusted_count,"
                    "reported_controls_failed_count,evidence_consistent,verdict) VALUES "
                    "(:t,:p,:d,:d,'slice46.acceptance_verification.v1',:c,'succeeded',"
                    "'system_executed_structural',NULL,1,1,0,0,0,0,true,'eligible')"
                ),
                {"t": ctx["tenant"], "p": ctx["project"], "d": "sha256:" + "d" * 64, "c": verifier_contract_hash()},
            )


@pytest.mark.db
async def test_direct_sql_rejects_blank_failure_code(acceptance_db_ctx, admin_engine):
    from app.verify.acceptance import verifier_contract_hash

    ctx = acceptance_db_ctx
    with pytest.raises(Exception, match="failure_code_bounded"):
        async with admin_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO acceptance_verification_runs (tenant_id,project_id,scope_digest,"
                    "authorship_digest,schema_version,verifier_contract_hash,execution_status,"
                    "execution_provenance,failure_code,reported_scope_count,reported_eligible_count,"
                    "reported_unapproved_count,reported_disputed_count,reported_missing_or_untrusted_count,"
                    "reported_controls_failed_count,evidence_consistent,verdict) VALUES "
                    "(:t,:p,:d,:d,'slice46.acceptance_verification.v1',:c,'failed',"
                    "'system_executed_structural','',0,0,0,0,0,0,false,'blocked')"
                ),
                {"t": ctx["tenant"], "p": ctx["project"], "d": "sha256:" + "9" * 64, "c": verifier_contract_hash()},
            )


@pytest.mark.db
async def test_acceptance_evidence_is_hidden_cross_tenant(acceptance_db_ctx, admin_engine, rls_engine):
    ctx = acceptance_db_ctx
    generator, reviewer, approval = await _seed_agent_pair_and_approval(admin_engine, ctx)
    from app.repositories.acceptance_verification import AcceptanceVerificationRepository
    from app.tenancy import TenantContext, tenant_scope

    tenant = TenantContext(ctx["tenant"])
    async with tenant_scope(tenant) as session:
        await AcceptanceVerificationRepository(session, tenant).record_independent_approval(
            project_id=ctx["project"], acceptance_criterion_id=ctx["ac"],
            generator_instance_id=generator, reviewer_instance_id=reviewer, approval_id=approval,
            evidence_reference="sha256:" + "e" * 64, actor="db-test",
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(__import__("uuid").uuid4())},
            )
            assert await _scalar(conn, "SELECT count(*) FROM acceptance_criterion_authorship_records") == 0


@pytest.mark.db
async def test_authorship_records_refuse_update_delete_and_truncate(acceptance_db_ctx, admin_engine):
    ctx = acceptance_db_ctx
    generator, reviewer, approval = await _seed_agent_pair_and_approval(admin_engine, ctx)
    from app.repositories.acceptance_verification import AcceptanceVerificationRepository
    from app.tenancy import TenantContext, tenant_scope

    tenant = TenantContext(ctx["tenant"])
    async with tenant_scope(tenant) as session:
        row = await AcceptanceVerificationRepository(session, tenant).record_independent_approval(
            project_id=ctx["project"], acceptance_criterion_id=ctx["ac"],
            generator_instance_id=generator, reviewer_instance_id=reviewer, approval_id=approval,
            evidence_reference="sha256:" + "f" * 64, actor="db-test",
        )
    for statement in (
        "UPDATE acceptance_criterion_authorship_records SET sequence=2 WHERE id=:id",
        "DELETE FROM acceptance_criterion_authorship_records WHERE id=:id",
        "TRUNCATE acceptance_criterion_authorship_records CASCADE",
    ):
        with pytest.raises(Exception, match="append-only"):
            async with admin_engine.begin() as conn:
                await conn.execute(text(statement), {"id": row.id})
