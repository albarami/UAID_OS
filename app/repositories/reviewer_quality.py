"""Repository-controlled Slice-48 reviewer QA execution and reversible eligibility."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.cost import CostError, to_decimal
from app.intake.extraction import actual_cost, project_cost
from app.llm.client import LLMClient
from app.llm.pricing import ModelPrice, UnpricedModelError, get_price
from app.models.agent_blueprint import AgentBlueprint
from app.models.agent_instance import AgentInstance
from app.models.agent_realization import AgentRealization
from app.models.agent_version import AgentVersion
from app.models.qualification_run import QualificationRun
from app.models.reviewer_quality import (
    ReviewerQAFixtureSuite,
    ReviewerQualityCaseResult,
    ReviewerQualityDefectResult,
    ReviewerQualityRecord,
)
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.tenancy import TenantContext, TenantScopedRepository
from app.verify.reviewer_qa import (
    EXECUTION_PROVENANCE,
    FIXTURE_SUITE_ID,
    MAX_OUTPUT_TOKENS,
    MAX_PACKET_CHARS,
    SCHEMA_VERSION,
    InvalidReviewerQA,
    ReviewerFixtureCase,
    ReviewerFixtureSuite,
    controlled_fixture_suite,
    derive_metrics,
    execute_reviewer_case,
    fixture_case_id,
    fixture_defect_id,
    load_canonical_policy,
    policy_digest,
    reviewer_qa_contract_hash,
    text_digest,
    validate_fixture_suite,
)


@dataclass(frozen=True)
class _Lineage:
    instance: AgentInstance
    version: AgentVersion
    blueprint: AgentBlueprint
    realization: AgentRealization
    qualification_run: QualificationRun


class ReviewerQualityError(ValueError):
    """Reviewer QA execution or exact evidence binding could not be established."""


class ReviewerQualityRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ReviewerQualityRecord)

    async def execute_suite(
        self,
        *,
        project_id: uuid.UUID,
        reviewer_instance_id: uuid.UUID,
        client: LLMClient,
        price_card: dict[str, ModelPrice] | None,
        actor: str,
    ) -> ReviewerQualityRecord:
        lineage = await self._lineage(project_id, reviewer_instance_id)
        if lineage is None:
            raise ReviewerQualityError(
                "reviewer must be active, qualified, same-project, and reviewer-archetype"
            )
        suite = controlled_fixture_suite()
        validate_fixture_suite(suite)
        catalog = await self._catalog(suite)
        policy = load_canonical_policy()
        try:
            price = get_price(lineage.version.model_route, price_card)
            to_decimal(price.input_usd_per_1k, "input_usd_per_1k")
            to_decimal(price.output_usd_per_1k, "output_usd_per_1k")
        except (CostError, ValueError, ArithmeticError, UnpricedModelError):
            return await self._failure(
                project_id, lineage, catalog, "refused", "reviewer_qa_price_invalid", actor
            )

        llm_cases = [case for case in suite.cases if case.control_kind != "injection"]
        projected = sum(
            (
                project_cost(
                    price,
                    est_input_tokens=(MAX_PACKET_CHARS // 4) + 1_000,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )
                for _case in llm_cases
            ),
            Decimal(0),
        )
        if await self._projected_exceeds_budget(project_id, projected):
            return await self._failure(
                project_id, lineage, catalog, "refused", "reviewer_qa_blocked_by_budget", actor
            )

        record_id = uuid.uuid4()
        calls = {}

        async def record_usage(case_ref: str, call) -> None:
            await CostEventRepository(self.session, self.context).record(
                project_id=project_id,
                component="model_inference",
                amount_usd=actual_cost(
                    price,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                ),
                quantity=call.input_tokens + call.output_tokens,
                source_system="llm",
                external_ref=f"reviewer_quality_record:{record_id}:case:{case_ref}",
                actor=actor,
            )

        try:
            for case in llm_cases:
                call = await execute_reviewer_case(
                    case=case,
                    model_route=lineage.version.model_route,
                    client=client,
                )
                await record_usage(case.case_ref, call)
                calls[case.case_ref] = call
        except InvalidReviewerQA as exc:
            failure = (
                "reviewer_qa_refused_injection"
                if "injection" in str(exc)
                else "reviewer_qa_execution_failed"
            )
            return await self._failure(
                project_id,
                lineage,
                catalog,
                "refused" if "refused" in failure else "failed",
                failure,
                actor,
            )

        metrics = derive_metrics(tuple(call.observation for call in calls.values()))
        record = ReviewerQualityRecord(
            id=record_id,
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            reviewer_instance_id=lineage.instance.id,
            reviewer_realization_id=lineage.realization.id,
            qualification_run_id=lineage.qualification_run.id,
            reviewer_blueprint_id=lineage.blueprint.id,
            reviewer_version_id=lineage.version.id,
            reviewer_version_hash=lineage.version.content_hash,
            model_route_hash=text_digest(lineage.version.model_route),
            prompt_hash=lineage.version.prompt_hash,
            fixture_suite_id=catalog.id,
            fixture_suite_hash=suite.suite_digest,
            schema_version=SCHEMA_VERSION,
            qa_contract_hash=reviewer_qa_contract_hash(),
            policy_digest=policy_digest(),
            execution_status="succeeded",
            failure_code=None,
            execution_provenance=EXECUTION_PROVENANCE,
            blind_to_fixture_labels=True,
            live_sampling_executed=False,
            planted_defect_sampling_rate=policy.planted_defect_sampling_rate,
            max_critical_defect_miss_rate=policy.max_critical_defect_miss_rate,
            max_false_approval_rate=policy.max_false_approval_rate,
            case_count=len(suite.cases),
            defective_case_count=sum(bool(case.expected_defects) for case in suite.cases),
            clean_case_count=sum(not case.expected_defects for case in suite.cases),
            critical_label_count=metrics.critical_label_count,
            missed_critical_label_count=metrics.missed_critical_label_count,
            major_label_count=metrics.major_label_count,
            missed_major_label_count=metrics.missed_major_label_count,
            false_approval_count=metrics.false_approval_count,
            false_rejection_count=metrics.false_rejection_count,
            matched_evidence_count=metrics.matched_evidence_count,
            specific_required_change_count=metrics.specific_required_change_count,
            input_tokens=sum(call.input_tokens for call in calls.values()),
            output_tokens=sum(call.output_tokens for call in calls.values()),
            total_latency_ms=sum(call.observation.latency_ms for call in calls.values()),
            coverage_complete=True,
            created_at=datetime.now(timezone.utc),
            next_calibration_due=datetime.now(timezone.utc),
        )
        self.session.add(record)
        await self.session.flush()
        for case in suite.cases:
            await self._record_case(project_id, record, case, calls.get(case.case_ref))
        await self.session.flush()
        await self.session.refresh(record)
        await self._audit(record, actor)
        return record

    async def is_currently_eligible(
        self, *, project_id: uuid.UUID, reviewer_instance_id: uuid.UUID
    ) -> bool:
        lineage = await self._lineage(project_id, reviewer_instance_id)
        if lineage is None:
            return False
        suite = controlled_fixture_suite()
        contract = reviewer_qa_contract_hash()
        breach_count = (
            await self.session.execute(
                select(func.count())
                .select_from(ReviewerQualityRecord)
                .where(
                    ReviewerQualityRecord.tenant_id == self.context.tenant_id,
                    ReviewerQualityRecord.project_id == project_id,
                    ReviewerQualityRecord.reviewer_instance_id == reviewer_instance_id,
                    ReviewerQualityRecord.reviewer_version_hash == lineage.version.content_hash,
                    ReviewerQualityRecord.quality_status == "threshold_breached",
                )
            )
        ).scalar_one()
        if breach_count:
            return False
        latest = (
            await self.session.execute(
                select(ReviewerQualityRecord)
                .where(
                    ReviewerQualityRecord.tenant_id == self.context.tenant_id,
                    ReviewerQualityRecord.project_id == project_id,
                    ReviewerQualityRecord.reviewer_instance_id == reviewer_instance_id,
                    ReviewerQualityRecord.reviewer_version_hash == lineage.version.content_hash,
                    ReviewerQualityRecord.fixture_suite_hash == suite.suite_digest,
                    ReviewerQualityRecord.qa_contract_hash == contract,
                )
                .order_by(
                    ReviewerQualityRecord.created_at.desc(), ReviewerQualityRecord.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return bool(
            latest is not None
            and latest.execution_status == "succeeded"
            and latest.quality_status == "challenge_qualified"
            and latest.next_calibration_due >= datetime.now(timezone.utc)
        )

    async def _lineage(
        self, project_id: uuid.UUID, reviewer_instance_id: uuid.UUID
    ) -> _Lineage | None:
        row = (
            await self.session.execute(
                select(
                    AgentInstance,
                    AgentVersion,
                    AgentBlueprint,
                    AgentRealization,
                    QualificationRun,
                )
                .join(AgentVersion, AgentVersion.id == AgentInstance.version_id)
                .join(AgentBlueprint, AgentBlueprint.id == AgentVersion.blueprint_id)
                .join(AgentRealization, AgentRealization.instance_id == AgentInstance.id)
                .join(
                    QualificationRun,
                    QualificationRun.id == AgentRealization.qualified_via_run_id,
                )
                .where(
                    AgentInstance.id == reviewer_instance_id,
                    AgentInstance.tenant_id == self.context.tenant_id,
                    AgentInstance.project_id == project_id,
                    AgentInstance.status == "active",
                    AgentBlueprint.status == "active",
                    AgentBlueprint.archetype == "reviewer",
                    AgentRealization.qualification_status == "qualified",
                    QualificationRun.verdict == "passed",
                )
            )
        ).one_or_none()
        return _Lineage(*row) if row is not None else None

    async def _catalog(self, suite: ReviewerFixtureSuite) -> ReviewerQAFixtureSuite:
        catalog = await self.session.get(ReviewerQAFixtureSuite, FIXTURE_SUITE_ID)
        if (
            catalog is None
            or catalog.suite_digest != suite.suite_digest
            or catalog.qa_contract_hash != reviewer_qa_contract_hash()
            or catalog.policy_digest != policy_digest()
            or catalog.case_count != len(suite.cases)
        ):
            raise ReviewerQualityError("controlled reviewer QA catalog does not match code")
        return catalog

    async def _record_case(
        self,
        project_id: uuid.UUID,
        record: ReviewerQualityRecord,
        case: ReviewerFixtureCase,
        call,
    ) -> None:
        injection = case.control_kind == "injection"
        row = ReviewerQualityCaseResult(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            reviewer_quality_record_id=record.id,
            fixture_suite_id=record.fixture_suite_id,
            fixture_case_id=fixture_case_id(case.case_ref),
            execution_status="control_refused" if injection else "succeeded",
            reviewer_decision=None if injection else call.observation.reviewer_decision,
            response_digest=None if injection else call.response_digest,
            reported_finding_count=0 if injection else len(call.findings),
            matched_evidence_count=0 if injection else call.observation.matched_evidence_count,
            specific_required_change_count=(
                0 if injection else call.observation.specific_required_change_count
            ),
            input_tokens=0 if injection else call.input_tokens,
            output_tokens=0 if injection else call.output_tokens,
            latency_ms=0 if injection else call.observation.latency_ms,
        )
        self.session.add(row)
        await self.session.flush()
        if injection:
            return
        matches = {(item.category, item.evidence_ref) for item in call.findings}
        for defect in case.expected_defects:
            detected = (defect.category, defect.expected_evidence_ref) in matches
            self.session.add(
                ReviewerQualityDefectResult(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    reviewer_quality_case_result_id=row.id,
                    fixture_suite_id=record.fixture_suite_id,
                    fixture_case_id=row.fixture_case_id,
                    fixture_defect_id=fixture_defect_id(case.case_ref, defect.defect_key),
                    detected=detected,
                    evidence_matched=detected,
                )
            )

    async def _failure(
        self,
        project_id: uuid.UUID,
        lineage: _Lineage,
        catalog: ReviewerQAFixtureSuite,
        status: str,
        failure_code: str,
        actor: str,
    ) -> ReviewerQualityRecord:
        policy = load_canonical_policy()
        record = ReviewerQualityRecord(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            reviewer_instance_id=lineage.instance.id,
            reviewer_realization_id=lineage.realization.id,
            qualification_run_id=lineage.qualification_run.id,
            reviewer_blueprint_id=lineage.blueprint.id,
            reviewer_version_id=lineage.version.id,
            reviewer_version_hash=lineage.version.content_hash,
            model_route_hash=text_digest(lineage.version.model_route),
            prompt_hash=lineage.version.prompt_hash,
            fixture_suite_id=catalog.id,
            fixture_suite_hash=catalog.suite_digest,
            schema_version=SCHEMA_VERSION,
            qa_contract_hash=catalog.qa_contract_hash,
            policy_digest=catalog.policy_digest,
            execution_status=status,
            failure_code=failure_code,
            execution_provenance=EXECUTION_PROVENANCE,
            blind_to_fixture_labels=True,
            live_sampling_executed=False,
            planted_defect_sampling_rate=policy.planted_defect_sampling_rate,
            max_critical_defect_miss_rate=policy.max_critical_defect_miss_rate,
            max_false_approval_rate=policy.max_false_approval_rate,
            case_count=0,
            defective_case_count=0,
            clean_case_count=0,
            critical_label_count=0,
            missed_critical_label_count=0,
            major_label_count=0,
            missed_major_label_count=0,
            false_approval_count=0,
            false_rejection_count=0,
            matched_evidence_count=0,
            specific_required_change_count=0,
            input_tokens=0,
            output_tokens=0,
            total_latency_ms=0,
            coverage_complete=False,
            created_at=datetime.now(timezone.utc),
            next_calibration_due=datetime.now(timezone.utc),
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        await self._audit(record, actor)
        return record

    async def _projected_exceeds_budget(self, project_id: uuid.UUID, projected: Decimal) -> bool:
        budget = await BudgetRepository(self.session, self.context).get(project_id)
        if budget is None:
            return True
        costs = CostEventRepository(self.session, self.context)
        if await costs.total_spent(project_id) + projected >= budget.max_total_cost_usd:
            return True
        if budget.max_daily_cost_usd is not None:
            if (
                await costs.daily_spent(project_id, datetime.now(timezone.utc).date()) + projected
                >= budget.max_daily_cost_usd
            ):
                return True
        return False

    async def _audit(self, record: ReviewerQualityRecord, actor: str) -> None:
        await audit_record(
            self.session,
            action="reviewer.quality_recorded",
            actor=actor,
            target=f"reviewer_quality_record:{record.id}",
            payload={
                "reviewer_quality_record_id": str(record.id),
                "project_id": str(record.project_id),
                "reviewer_instance_id": str(record.reviewer_instance_id),
                "schema_version": record.schema_version,
                "execution_status": record.execution_status,
                "failure_code": record.failure_code,
                "quality_status": record.quality_status,
                "prescribed_decision": record.prescribed_decision,
                "case_count": record.case_count,
                "critical_label_count": record.critical_label_count,
                "missed_critical_label_count": record.missed_critical_label_count,
                "false_approval_count": record.false_approval_count,
                "blind_to_fixture_labels": record.blind_to_fixture_labels,
                "live_sampling_executed": record.live_sampling_executed,
            },
        )
