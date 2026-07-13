"""DB-test seed for a current, challenge-qualified Slice-48 reviewer record."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import text

from app.verify.reviewer_qa import (
    EXECUTION_PROVENANCE,
    FIXTURE_SUITE_ID,
    SCHEMA_VERSION,
    controlled_fixture_suite,
    fixture_case_id,
    fixture_defect_id,
    policy_digest,
    reviewer_qa_contract_hash,
    text_digest,
)


async def _scalar(conn, sql: str, **params):
    return (await conn.execute(text(sql), params)).scalar_one()


async def seed_current_reviewer_quality(
    conn,
    *,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    reviewer_instance_id: uuid.UUID,
) -> uuid.UUID:
    lineage = (
        await conn.execute(
            text(
                "SELECT r.id AS realization_id,r.qualified_via_run_id AS qualification_run_id,"
                "v.id AS version_id,v.blueprint_id,v.content_hash,v.model_route,v.prompt_hash "
                "FROM agent_instances i JOIN agent_versions v ON v.id=i.version_id "
                "JOIN agent_realizations r ON r.instance_id=i.id "
                "WHERE i.id=:i AND i.tenant_id=:t AND i.project_id=:p"
            ),
            {"i": reviewer_instance_id, "t": tenant_id, "p": project_id},
        )
    ).mappings().one()
    suite = controlled_fixture_suite()
    record_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO reviewer_quality_records "
            "(id,tenant_id,project_id,reviewer_instance_id,reviewer_realization_id,"
            "qualification_run_id,reviewer_blueprint_id,reviewer_version_id,reviewer_version_hash,"
            "model_route_hash,prompt_hash,fixture_suite_id,fixture_suite_hash,schema_version,"
            "qa_contract_hash,policy_digest,execution_status,failure_code,execution_provenance,"
            "blind_to_fixture_labels,live_sampling_executed,planted_defect_sampling_rate,"
            "max_critical_defect_miss_rate,max_false_approval_rate,case_count,defective_case_count,"
            "clean_case_count,critical_label_count,missed_critical_label_count,major_label_count,"
            "missed_major_label_count,false_approval_count,false_rejection_count,"
            "matched_evidence_count,specific_required_change_count,input_tokens,output_tokens,"
            "total_latency_ms,coverage_complete,created_at,next_calibration_due) VALUES "
            "(:id,:t,:p,:i,:r,:q,:b,:v,:vh,:mh,:ph,:s,:sh,:sv,:ch,:pd,'succeeded',NULL,:ep,"
            "true,false,0.05,0.00,0.03,46,41,5,41,0,0,0,0,0,41,41,0,0,0,true,"
            "clock_timestamp(),clock_timestamp())"
        ),
        {
            "id": record_id,
            "t": tenant_id,
            "p": project_id,
            "i": reviewer_instance_id,
            "r": lineage["realization_id"],
            "q": lineage["qualification_run_id"],
            "b": lineage["blueprint_id"],
            "v": lineage["version_id"],
            "vh": lineage["content_hash"],
            "mh": text_digest(lineage["model_route"]),
            "ph": lineage["prompt_hash"],
            "s": FIXTURE_SUITE_ID,
            "sh": suite.suite_digest,
            "sv": SCHEMA_VERSION,
            "ch": reviewer_qa_contract_hash(),
            "pd": policy_digest(),
            "ep": EXECUTION_PROVENANCE,
        },
    )
    for case in suite.cases:
        injection = case.control_kind == "injection"
        response_digest = None if injection else "sha256:" + hashlib.sha256(
            f"response:{record_id}:{case.case_ref}".encode()
        ).hexdigest()
        case_result_id = await _scalar(
            conn,
            "INSERT INTO reviewer_quality_case_results "
            "(tenant_id,project_id,reviewer_quality_record_id,fixture_suite_id,fixture_case_id,"
            "execution_status,reviewer_decision,response_digest,reported_finding_count,"
            "matched_evidence_count,specific_required_change_count,input_tokens,output_tokens,latency_ms) "
            "VALUES (:t,:p,:r,:s,:c,:es,:d,:rd,:fc,:mc,:sc,0,0,0) RETURNING id",
            t=tenant_id,
            p=project_id,
            r=record_id,
            s=FIXTURE_SUITE_ID,
            c=fixture_case_id(case.case_ref),
            es="control_refused" if injection else "succeeded",
            d=None if injection else case.expected_verdict,
            rd=response_digest,
            fc=len(case.expected_defects),
            mc=len(case.expected_defects),
            sc=len(case.expected_defects),
        )
        for defect in case.expected_defects:
            await conn.execute(
                text(
                    "INSERT INTO reviewer_quality_defect_results "
                    "(tenant_id,project_id,reviewer_quality_case_result_id,fixture_suite_id,"
                    "fixture_case_id,fixture_defect_id,detected,evidence_matched) "
                    "VALUES (:t,:p,:cr,:s,:c,:d,true,true)"
                ),
                {
                    "t": tenant_id,
                    "p": project_id,
                    "cr": case_result_id,
                    "s": FIXTURE_SUITE_ID,
                    "c": fixture_case_id(case.case_ref),
                    "d": fixture_defect_id(case.case_ref, defect.defect_key),
                },
            )
    return record_id
