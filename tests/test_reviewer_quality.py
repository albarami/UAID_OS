from __future__ import annotations

import json
import hashlib
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.llm.client import FakeLLMClient
from tests.reviewer_quality_support import seed_current_reviewer_quality


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


_QUALITY_BASE_COLUMNS = (
    "tenant_id",
    "project_id",
    "reviewer_instance_id",
    "reviewer_realization_id",
    "qualification_run_id",
    "reviewer_blueprint_id",
    "reviewer_version_id",
    "reviewer_version_hash",
    "model_route_hash",
    "prompt_hash",
    "fixture_suite_id",
    "fixture_suite_hash",
    "schema_version",
    "qa_contract_hash",
    "policy_digest",
    "execution_status",
    "failure_code",
    "execution_provenance",
    "blind_to_fixture_labels",
    "live_sampling_executed",
    "planted_defect_sampling_rate",
    "max_critical_defect_miss_rate",
    "max_false_approval_rate",
    "case_count",
    "defective_case_count",
    "clean_case_count",
    "critical_label_count",
    "missed_critical_label_count",
    "major_label_count",
    "missed_major_label_count",
    "false_approval_count",
    "false_rejection_count",
    "matched_evidence_count",
    "specific_required_change_count",
    "input_tokens",
    "output_tokens",
    "total_latency_ms",
    "coverage_complete",
    "created_at",
    "next_calibration_due",
)


def _clone_record_sql() -> str:
    columns = ",".join(("id", *_QUALITY_BASE_COLUMNS))
    selections = ",".join(("gen_random_uuid()", *_QUALITY_BASE_COLUMNS))
    return (
        f"INSERT INTO reviewer_quality_records ({columns}) "
        f"SELECT {selections} FROM reviewer_quality_records WHERE id=:r"
    )


def test_canonical_policy_uses_shipped_thresholds_only():
    from app.verify.reviewer_qa import load_canonical_policy

    policy = load_canonical_policy()

    assert policy.planted_defect_sampling_rate == Decimal("0.05")
    assert policy.max_critical_defect_miss_rate == Decimal("0.00")
    assert policy.max_false_approval_rate == Decimal("0.03")
    assert not hasattr(policy, "max_major_defect_miss_rate")
    assert not hasattr(policy, "allowed_critical_miss_rate")


def test_controlled_suite_has_ruled_minimums_and_controls():
    from app.verify.reviewer_qa import (
        CHALLENGE_FAMILIES,
        CONTROL_KINDS,
        controlled_fixture_suite,
        validate_fixture_suite,
    )

    suite = controlled_fixture_suite()
    validate_fixture_suite(suite)

    defective = [case for case in suite.cases if case.expected_defects]
    assert len(defective) >= 40
    assert {case.challenge_family for case in defective} == set(CHALLENGE_FAMILIES)
    for family in CHALLENGE_FAMILIES:
        assert any(
            defect.severity == "critical"
            for case in defective
            if case.challenge_family == family
            for defect in case.expected_defects
        )
    assert CONTROL_KINDS <= {case.control_kind for case in suite.cases if case.control_kind}
    incomplete = next(case for case in suite.cases if case.control_kind == "incomplete")
    assert incomplete.expected_verdict == "rejected_with_required_changes"
    assert incomplete.expected_defects[0].category == "missing_evidence"
    assert suite.suite_digest.startswith("sha256:")


def test_contract_and_policy_digests_are_canonical_and_versioned():
    from app.verify.reviewer_qa import policy_digest, reviewer_qa_contract_hash

    assert reviewer_qa_contract_hash().startswith("sha256:")
    assert policy_digest().startswith("sha256:")
    assert reviewer_qa_contract_hash() == reviewer_qa_contract_hash()
    assert policy_digest() == policy_digest()


def test_blind_packet_excludes_hidden_labels_thresholds_and_prior_state():
    from app.verify.reviewer_qa import build_blind_packet, controlled_fixture_suite

    case = next(case for case in controlled_fixture_suite().cases if case.expected_defects)
    packet = build_blind_packet(case)

    assert "Controlled defect challenge variant 1" in packet
    assert case.expected_verdict not in packet
    for defect in case.expected_defects:
        assert defect.defect_key not in packet
        assert defect.severity not in packet
        assert defect.expected_evidence_ref in packet
    for forbidden in (
        "0.00",
        "0.03",
        "expected_defects",
        "quality_status",
        "prescribed_decision",
        "prior_verdict",
    ):
        assert forbidden not in packet


def test_exact_matching_and_generated_quality_decision_fail_on_one_critical_miss():
    from app.verify.reviewer_qa import (
        CaseObservation,
        derive_metrics,
        evaluate_quality,
    )

    observations = (
        CaseObservation(
            case_ref="defect-1",
            expected_verdict="rejected_with_required_changes",
            reviewer_decision="approved",
            critical_labels=1,
            major_labels=0,
            detected_critical_labels=0,
            detected_major_labels=0,
            matched_evidence_count=0,
            specific_required_change_count=0,
            latency_ms=11,
        ),
        CaseObservation(
            case_ref="clean-1",
            expected_verdict="approved",
            reviewer_decision="approved",
            critical_labels=0,
            major_labels=0,
            detected_critical_labels=0,
            detected_major_labels=0,
            matched_evidence_count=0,
            specific_required_change_count=0,
            latency_ms=7,
        ),
    )
    metrics = derive_metrics(observations)
    decision = evaluate_quality(metrics)

    assert metrics.critical_miss_rate == Decimal("1")
    assert metrics.false_approval_rate == Decimal("1")
    assert metrics.false_rejection_rate == Decimal("0")
    assert decision.quality_status == "threshold_breached"
    assert decision.prescribed_decision == (
        "suspend_or_downgrade_review_authority_and_trigger_factory_replacement"
    )


def test_required_zero_denominator_is_inconclusive():
    from app.verify.reviewer_qa import CaseObservation, derive_metrics, evaluate_quality

    metrics = derive_metrics(
        (
            CaseObservation(
                case_ref="clean-1",
                expected_verdict="approved",
                reviewer_decision="approved",
                critical_labels=0,
                major_labels=0,
                detected_critical_labels=0,
                detected_major_labels=0,
                matched_evidence_count=0,
                specific_required_change_count=0,
                latency_ms=1,
            ),
        )
    )

    assert metrics.critical_miss_rate is None
    assert metrics.false_approval_rate is None
    assert evaluate_quality(metrics).quality_status == "inconclusive"


@pytest.mark.asyncio
async def test_blind_llm_call_is_system_executed_and_strictly_parsed():
    from app.verify.reviewer_qa import execute_reviewer_case, controlled_fixture_suite

    case = next(case for case in controlled_fixture_suite().cases if case.expected_defects)
    defect = case.expected_defects[0]
    response = json.dumps(
        {
            "decision": "rejected_with_required_changes",
            "findings": [
                {
                    "category": defect.category,
                    "evidence_ref": defect.expected_evidence_ref,
                    "summary": "The controlled critical defect is present.",
                    "required_change": "Remove the planted defect and add a behavioral regression test.",
                }
            ],
        }
    )
    client = FakeLLMClient(response_text=response)

    result = await execute_reviewer_case(case=case, model_route="reviewer-model", client=client)

    assert result.execution_provenance == "system_executed_reviewer_qa"
    assert result.observation.detected_critical_labels == 1
    assert result.observation.latency_ms > 0
    assert result.response_digest.startswith("sha256:")
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["temperature"] == 0.0
    assert defect.defect_key not in call["user"]
    assert defect.severity not in call["user"]


@pytest.mark.asyncio
async def test_injection_control_refuses_before_llm_call():
    from app.verify.reviewer_qa import InvalidReviewerQA, execute_reviewer_case, controlled_fixture_suite

    case = next(case for case in controlled_fixture_suite().cases if case.control_kind == "injection")
    client = FakeLLMClient(response_text='{"decision":"approved","findings":[]}')

    with pytest.raises(InvalidReviewerQA, match="injection"):
        await execute_reviewer_case(case=case, model_route="reviewer-model", client=client)

    assert client.calls == []


@pytest.mark.asyncio
async def test_reviewer_response_rejects_unknown_category_code():
    from app.verify.reviewer_qa import InvalidReviewerQA, controlled_fixture_suite, execute_reviewer_case

    case = next(case for case in controlled_fixture_suite().cases if case.expected_defects)
    client = FakeLLMClient(
        response_text=json.dumps(
            {
                "decision": "rejected_with_required_changes",
                "findings": [
                    {
                        "category": "caller_claimed_passed",
                        "evidence_ref": "src/example.py:1",
                        "summary": "Unsupported caller category.",
                        "required_change": "This response must be rejected.",
                    }
                ],
            }
        )
    )

    with pytest.raises(InvalidReviewerQA, match="category"):
        await execute_reviewer_case(case=case, model_route="reviewer-model", client=client)


@pytest.mark.asyncio
async def test_fake_llm_supports_a_deterministic_response_sequence():
    client = FakeLLMClient(response_texts=["first", "second"])

    first = await client.complete(system="s", user="u1", model="m", max_output_tokens=1)
    second = await client.complete(system="s", user="u2", model="m", max_output_tokens=1)

    assert (first.text, second.text) == ("first", "second")


def test_slice50_advances_a5_while_readiness_stays_byte_stable():
    from pathlib import Path

    from app.intake.readiness import RULESET_VERSION as READINESS_RULESET_VERSION
    from app.release.production_autonomy import A5_RULESET_VERSION

    assert A5_RULESET_VERSION == "slice54.v1"
    assert READINESS_RULESET_VERSION == "slice20.v1"
    assert hashlib.sha256(Path("app/release/production_autonomy.py").read_bytes()).hexdigest() == (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    )
    assert hashlib.sha256(Path("app/intake/readiness.py").read_bytes()).hexdigest() == (
        "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26"
    )


@pytest.mark.asyncio
async def test_shortcut_panel_helper_denies_any_reviewer_without_current_qa(monkeypatch):
    from app.repositories.reviewer_quality import ReviewerQualityRepository
    from app.repositories.shortcut_detectors import ShortcutDetectorRepository

    eligibility = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(ReviewerQualityRepository, "is_currently_eligible", eligibility)
    repo = object.__new__(ShortcutDetectorRepository)
    repo.session = object()
    repo.context = SimpleNamespace(tenant_id=uuid.uuid4())
    reviewers = (uuid.uuid4(), uuid.uuid4())

    assert await repo._qa_panel_current(uuid.uuid4(), reviewers) is False
    assert eligibility.await_count == 2


@pytest.mark.asyncio
async def test_acceptance_independent_approval_refuses_missing_current_qa(monkeypatch):
    from app.repositories.acceptance_verification import AcceptanceVerificationRepository
    from app.repositories.reviewer_quality import ReviewerQualityRepository

    monkeypatch.setattr(
        ReviewerQualityRepository, "is_currently_eligible", AsyncMock(return_value=False)
    )
    repo = object.__new__(AcceptanceVerificationRepository)
    repo.session = object()
    repo.context = SimpleNamespace(tenant_id=uuid.uuid4())

    with pytest.raises(ValueError, match="current reviewer QA"):
        await repo.record_independent_approval(
            project_id=uuid.uuid4(),
            acceptance_criterion_id=uuid.uuid4(),
            generator_instance_id=uuid.uuid4(),
            reviewer_instance_id=uuid.uuid4(),
            approval_id=uuid.uuid4(),
            evidence_reference="sha256:" + "a" * 64,
            actor="qa-test",
        )


@pytest.mark.db
async def test_reviewer_qa_catalog_tables_and_findings_guard_pin(admin_engine):
    async with admin_engine.connect() as conn:
        tables = {
            await _scalar(conn, "SELECT to_regclass('public.reviewer_qa_fixture_suites')"),
            await _scalar(conn, "SELECT to_regclass('public.reviewer_qa_fixture_cases')"),
            await _scalar(conn, "SELECT to_regclass('public.reviewer_qa_fixture_defects')"),
            await _scalar(conn, "SELECT to_regclass('public.reviewer_quality_records')"),
            await _scalar(conn, "SELECT to_regclass('public.reviewer_quality_case_results')"),
            await _scalar(conn, "SELECT to_regclass('public.reviewer_quality_defect_results')"),
        }
        assert None not in tables
        assert await _scalar(conn, "SELECT count(*) FROM reviewer_qa_fixture_suites") == 1
        assert await _scalar(conn, "SELECT count(*) FROM reviewer_qa_fixture_cases") == 46
        assert await _scalar(conn, "SELECT count(*) FROM reviewer_qa_fixture_defects") == 41
        assert await _scalar(
            conn,
            "SELECT md5(pg_get_functiondef('release_findings_guard()'::regprocedure))",
        ) == "808036faf2660d6810aeca4342e6f1ac"
        assert await _scalar(
            conn,
            "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal "
            "AND tgname='acceptance_authorship_reviewer_qa_guard'",
        ) == 1
        assert await _scalar(
            conn,
            "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal "
            "AND tgname='shortcut_reviewer_qa_guard'",
        ) == 1


@pytest.mark.db
async def test_reviewer_quality_rates_status_and_decision_are_generated(admin_engine):
    async with admin_engine.connect() as conn:
        generated = dict(
            (
                await conn.execute(
                    text(
                        "SELECT column_name,is_generated FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name='reviewer_quality_records' "
                        "AND column_name IN "
                        "('critical_miss_rate','major_miss_rate','false_approval_rate',"
                        "'false_rejection_rate','quality_status','prescribed_decision',"
                        "'next_calibration_due')"
                    )
                )
            ).all()
        )
        assert generated == {
            "critical_miss_rate": "ALWAYS",
            "major_miss_rate": "ALWAYS",
            "false_approval_rate": "ALWAYS",
            "false_rejection_rate": "ALWAYS",
            "quality_status": "ALWAYS",
            "prescribed_decision": "ALWAYS",
            "next_calibration_due": "NEVER",
        }


@pytest.mark.db
async def test_reviewer_quality_tables_are_rls_forced_and_append_only(admin_engine):
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                    "WHERE relname IN "
                    "('reviewer_quality_records','reviewer_quality_case_results',"
                    "'reviewer_quality_defect_results') ORDER BY relname"
                )
            )
        ).all()
        assert rows == [
            ("reviewer_quality_case_results", True, True),
            ("reviewer_quality_defect_results", True, True),
            ("reviewer_quality_records", True, True),
        ]
        for table in (
            "reviewer_quality_records",
            "reviewer_quality_case_results",
            "reviewer_quality_defect_results",
        ):
            assert await _scalar(
                conn,
                "SELECT count(*) FROM pg_trigger WHERE tgrelid=CAST(:t AS regclass) "
                "AND NOT tgisinternal AND tgname=:n",
                t=table,
                n=f"{table}_no_update_delete",
            ) == 1


@pytest.mark.db
async def test_reviewer_quality_rows_do_not_cross_tenant_rls(
    reviewer_quality_ctx, admin_engine, rls_engine
):
    ctx = reviewer_quality_ctx
    async with admin_engine.begin() as conn:
        await seed_current_reviewer_quality(
            conn,
            tenant_id=ctx["tenant"],
            project_id=ctx["project"],
            reviewer_instance_id=ctx["instance"],
        )
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant',:t,true)"),
                {"t": str(ctx["tenant"])},
            )
            assert await _scalar(conn, "SELECT count(*) FROM reviewer_quality_records") == 1
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant',:t,true)"),
                {"t": str(uuid.uuid4())},
            )
            assert await _scalar(conn, "SELECT count(*) FROM reviewer_quality_records") == 0


@pytest_asyncio.fixture
async def reviewer_quality_ctx(admin_engine):
    suffix = uuid.uuid4().hex[:8]
    hash_value = "sha256:" + "a" * 64
    async with admin_engine.begin() as conn:
        org = await _scalar(
            conn,
            "INSERT INTO organizations (name,slug) VALUES ('ReviewerQAOrg',:s) RETURNING id",
            s=f"reviewer-qa-org-{suffix}",
        )
        tenant = await _scalar(
            conn,
            "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'T1',:s) RETURNING id",
            o=org,
            s=f"reviewer-qa-t-{suffix}",
        )
        project = await _scalar(
            conn,
            "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,'P1',:s) RETURNING id",
            t=tenant,
            s=f"reviewer-qa-p-{suffix}",
        )
        await conn.execute(
            text(
                "INSERT INTO budgets (tenant_id,project_id,max_total_cost_usd,max_daily_cost_usd) "
                "VALUES (:t,:p,100,100)"
            ),
            {"t": tenant, "p": project},
        )
        blueprint = await _scalar(
            conn,
            "INSERT INTO agent_blueprints (key,role,mission,archetype) "
            "VALUES (:k,'Reviewer','Review primary evidence','reviewer') RETURNING id",
            k=f"reviewer-qa-{suffix}",
        )
        version_hash = "sha256:" + hashlib.sha256(f"version-{suffix}".encode()).hexdigest()
        version = await _scalar(
            conn,
            "INSERT INTO agent_versions "
            "(blueprint_id,version_label,model_route,prompt_hash,tool_policy_hash,"
            "context_policy_hash,eval_suite_hash,critical_dependencies_hash,"
            "output_schema_hash,content_hash) VALUES "
            "(:b,'v1','reviewer-model',:h,:h,:h,:h,:h,:h,:ch) RETURNING id",
            b=blueprint,
            h=hash_value,
            ch=version_hash,
        )
        instance = await _scalar(
            conn,
            "INSERT INTO agent_instances (tenant_id,project_id,version_id,instance_key,status) "
            "VALUES (:t,:p,:v,'reviewer-qa','active') RETURNING id",
            t=tenant,
            p=project,
            v=version,
        )
        realization = await _scalar(
            conn,
            "INSERT INTO agent_realizations "
            "(tenant_id,project_id,instance_id,qualification_status,realized_by) "
            "VALUES (:t,:p,:i,'unqualified','db-test') RETURNING id",
            t=tenant,
            p=project,
            i=instance,
        )
        eval_id = await _scalar(
            conn,
            "SELECT id FROM archetype_evals WHERE archetype='reviewer' AND eval_version='v1'",
        )
        run = await _scalar(
            conn,
            "INSERT INTO qualification_runs "
            "(tenant_id,project_id,realization_id,archetype_eval_id,archetype,eval_version,"
            "min_aggregate_score,require_zero_critical,min_cases,required_categories,"
            "total_cases,passed_cases,critical_failure_count,coverage_complete,evaluated_by) "
            "VALUES (:t,:p,:r,:e,'reviewer','v1',0.900,true,5,"
            "'[\"positive\",\"negative\",\"edge\",\"adversarial\",\"incomplete\"]'::jsonb,"
            "5,5,0,true,'db-test') RETURNING id",
            t=tenant,
            p=project,
            r=realization,
            e=eval_id,
        )
        for index, category in enumerate(
            ("positive", "negative", "edge", "adversarial", "incomplete")
        ):
            await conn.execute(
                text(
                    "INSERT INTO qualification_case_results "
                    "(tenant_id,project_id,run_id,case_ref,case_category,passed,is_critical) "
                    "VALUES (:t,:p,:r,:ref,:cat,true,false)"
                ),
                {
                    "t": tenant,
                    "p": project,
                    "r": run,
                    "ref": f"qa-{index}",
                    "cat": category,
                },
            )
        await conn.execute(
            text(
                "UPDATE agent_realizations SET qualification_status='qualified',"
                "qualified_via_run_id=:q WHERE id=:r"
            ),
            {"q": run, "r": realization},
        )
    return {
        "tenant": tenant,
        "project": project,
        "blueprint": blueprint,
        "version": version,
        "version_hash": version_hash,
        "instance": instance,
        "realization": realization,
        "qualification_run": run,
    }


def _passing_suite_responses():
    from app.verify.reviewer_qa import controlled_fixture_suite

    responses = []
    for case in controlled_fixture_suite().cases:
        if case.control_kind == "injection":
            continue
        if case.expected_defects:
            defect = case.expected_defects[0]
            payload = {
                "decision": "rejected_with_required_changes",
                "findings": [
                    {
                        "category": defect.category,
                        "evidence_ref": defect.expected_evidence_ref,
                        "summary": "The controlled critical defect is present.",
                        "required_change": "Remove the planted defect and add a behavioral test.",
                    }
                ],
            }
        else:
            payload = {"decision": "approved", "findings": []}
        responses.append(json.dumps(payload))
    return responses


@pytest.mark.db
async def test_repository_executes_full_suite_and_persists_generated_quality(
    reviewer_quality_ctx, admin_engine
):
    from app.llm.pricing import ModelPrice
    from app.release.production_autonomy import evaluate_production_autonomy
    from app.repositories.reviewer_quality import ReviewerQualityRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = reviewer_quality_ctx
    tenant = TenantContext(ctx["tenant"])
    client = FakeLLMClient(response_texts=_passing_suite_responses())
    a5_before = evaluate_production_autonomy(
        str(ctx["project"]), readiness_level="R5"
    ).to_dict()
    async with tenant_scope(tenant) as session:
        repo = ReviewerQualityRepository(session, tenant)
        record = await repo.execute_suite(
            project_id=ctx["project"],
            reviewer_instance_id=ctx["instance"],
            client=client,
            price_card={
                "reviewer-model": ModelPrice(
                    input_usd_per_1k=Decimal("0.001"),
                    output_usd_per_1k=Decimal("0.001"),
                )
            },
            actor="qa-operator",
        )
        assert record.quality_status == "challenge_qualified"
        assert record.prescribed_decision == "none"
        assert record.case_count == 46
        assert record.defective_case_count == 41
        assert record.clean_case_count == 5
        assert record.critical_label_count == 41
        assert record.missed_critical_label_count == 0
        assert record.false_approval_count == 0
        assert record.critical_miss_rate == Decimal("0")
        assert record.false_approval_rate == Decimal("0")
        assert record.live_sampling_executed is False
        assert record.next_calibration_due - record.created_at == __import__("datetime").timedelta(
            days=30
        )
        assert await repo.is_currently_eligible(
            project_id=ctx["project"], reviewer_instance_id=ctx["instance"]
        )
        await session.commit()
    assert len(client.calls) == 45
    a5_after = evaluate_production_autonomy(
        str(ctx["project"]), readiness_level="R5"
    ).to_dict()
    assert a5_after == a5_before
    async with admin_engine.connect() as conn:
        assert await _scalar(
            conn,
            "SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND "
            "(payload::text LIKE '%src/defect.py%' OR payload::text LIKE '%planted release-blocking%' "
            "OR payload::text LIKE '%Remove the planted defect%')",
            t=ctx["tenant"],
        ) == 0


@pytest.mark.db
async def test_infrastructure_refusal_is_inconclusive_not_a_reviewer_miss(reviewer_quality_ctx):
    from app.repositories.reviewer_quality import ReviewerQualityRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = reviewer_quality_ctx
    tenant = TenantContext(ctx["tenant"])
    client = FakeLLMClient(response_text='{"decision":"approved","findings":[]}')
    async with tenant_scope(tenant) as session:
        repo = ReviewerQualityRepository(session, tenant)
        record = await repo.execute_suite(
            project_id=ctx["project"],
            reviewer_instance_id=ctx["instance"],
            client=client,
            price_card={},
            actor="qa-operator",
        )
        assert record.execution_status == "refused"
        assert record.failure_code == "reviewer_qa_price_invalid"
        assert record.quality_status == "inconclusive"
        assert record.prescribed_decision == "none"
        assert record.case_count == 0
        assert record.critical_miss_rate is None
        assert not await repo.is_currently_eligible(
            project_id=ctx["project"], reviewer_instance_id=ctx["instance"]
        )
        await session.commit()
    assert client.calls == []


@pytest.mark.db
async def test_direct_sql_cannot_supply_generated_quality_truth(reviewer_quality_ctx, admin_engine):
    ctx = reviewer_quality_ctx
    with pytest.raises(Exception, match="generated column"):
        async with admin_engine.begin() as conn:
            source = await seed_current_reviewer_quality(
                conn,
                tenant_id=ctx["tenant"],
                project_id=ctx["project"],
                reviewer_instance_id=ctx["instance"],
            )
            await conn.execute(
                text(
                    "INSERT INTO reviewer_quality_records "
                    "(id,tenant_id,project_id,reviewer_instance_id,reviewer_realization_id,"
                    "qualification_run_id,reviewer_blueprint_id,reviewer_version_id,"
                    "reviewer_version_hash,model_route_hash,prompt_hash,fixture_suite_id,"
                    "fixture_suite_hash,schema_version,qa_contract_hash,policy_digest,"
                    "execution_status,failure_code,execution_provenance,blind_to_fixture_labels,"
                    "live_sampling_executed,planted_defect_sampling_rate,"
                    "max_critical_defect_miss_rate,max_false_approval_rate,case_count,"
                    "defective_case_count,clean_case_count,critical_label_count,"
                    "missed_critical_label_count,major_label_count,missed_major_label_count,"
                    "false_approval_count,false_rejection_count,matched_evidence_count,"
                    "specific_required_change_count,input_tokens,output_tokens,total_latency_ms,"
                    "coverage_complete,created_at,next_calibration_due,quality_status) "
                    "SELECT gen_random_uuid(),tenant_id,project_id,reviewer_instance_id,"
                    "reviewer_realization_id,qualification_run_id,reviewer_blueprint_id,"
                    "reviewer_version_id,reviewer_version_hash,model_route_hash,prompt_hash,"
                    "fixture_suite_id,fixture_suite_hash,schema_version,qa_contract_hash,"
                    "policy_digest,execution_status,failure_code,execution_provenance,"
                    "blind_to_fixture_labels,live_sampling_executed,planted_defect_sampling_rate,"
                    "max_critical_defect_miss_rate,max_false_approval_rate,case_count,"
                    "defective_case_count,clean_case_count,critical_label_count,"
                    "missed_critical_label_count,major_label_count,missed_major_label_count,"
                    "false_approval_count,false_rejection_count,matched_evidence_count,"
                    "specific_required_change_count,input_tokens,output_tokens,total_latency_ms,"
                    "coverage_complete,created_at,next_calibration_due,'challenge_qualified' "
                    "FROM reviewer_quality_records WHERE id=:r"
                ),
                {"r": source},
            )


@pytest.mark.db
async def test_direct_sql_parent_without_exact_children_fails_deferred_verification(
    reviewer_quality_ctx, admin_engine
):
    ctx = reviewer_quality_ctx
    with pytest.raises(Exception, match="case aggregates/coverage mismatch"):
        async with admin_engine.begin() as conn:
            source = await seed_current_reviewer_quality(
                conn,
                tenant_id=ctx["tenant"],
                project_id=ctx["project"],
                reviewer_instance_id=ctx["instance"],
            )
            await conn.execute(text(_clone_record_sql()), {"r": source})


@pytest.mark.db
async def test_later_refusal_supersedes_an_older_pass(reviewer_quality_ctx, admin_engine):
    from app.repositories.reviewer_quality import ReviewerQualityRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = reviewer_quality_ctx
    async with admin_engine.begin() as conn:
        await seed_current_reviewer_quality(
            conn,
            tenant_id=ctx["tenant"],
            project_id=ctx["project"],
            reviewer_instance_id=ctx["instance"],
        )
    tenant = TenantContext(ctx["tenant"])
    async with tenant_scope(tenant) as session:
        repo = ReviewerQualityRepository(session, tenant)
        assert await repo.is_currently_eligible(
            project_id=ctx["project"], reviewer_instance_id=ctx["instance"]
        )
        refused = await repo.execute_suite(
            project_id=ctx["project"],
            reviewer_instance_id=ctx["instance"],
            client=FakeLLMClient(),
            price_card={},
            actor="qa-operator",
        )
        assert refused.execution_status == "refused"
        assert not await repo.is_currently_eligible(
            project_id=ctx["project"], reviewer_instance_id=ctx["instance"]
        )
        await session.commit()


@pytest.mark.db
async def test_breached_immutable_version_cannot_self_clear(reviewer_quality_ctx):
    from app.llm.pricing import ModelPrice
    from app.repositories.reviewer_quality import ReviewerQualityRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = reviewer_quality_ctx
    tenant = TenantContext(ctx["tenant"])
    approved = json.dumps({"decision": "approved", "findings": []})
    price = {
        "reviewer-model": ModelPrice(
            input_usd_per_1k=Decimal("0.001"), output_usd_per_1k=Decimal("0.001")
        )
    }
    async with tenant_scope(tenant) as session:
        repo = ReviewerQualityRepository(session, tenant)
        breach = await repo.execute_suite(
            project_id=ctx["project"],
            reviewer_instance_id=ctx["instance"],
            client=FakeLLMClient(response_texts=[approved] * 45),
            price_card=price,
            actor="qa-operator",
        )
        assert breach.quality_status == "threshold_breached"
        assert breach.missed_critical_label_count == 41
        assert breach.false_approval_count == 41
        assert not await repo.is_currently_eligible(
            project_id=ctx["project"], reviewer_instance_id=ctx["instance"]
        )
        later_pass = await repo.execute_suite(
            project_id=ctx["project"],
            reviewer_instance_id=ctx["instance"],
            client=FakeLLMClient(response_texts=_passing_suite_responses()),
            price_card=price,
            actor="qa-operator",
        )
        assert later_pass.quality_status == "challenge_qualified"
        assert not await repo.is_currently_eligible(
            project_id=ctx["project"], reviewer_instance_id=ctx["instance"]
        )
        await session.commit()
