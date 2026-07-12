"""Tenant-scoped Slice-43 test-oracle execution and exact-binding coverage.

All writes are repository-controlled. CI observations become trusted only after the SCM
connector returns the versioned artifact for the declared repository and exact commit.
The gate reads a conservative scope: every structurally valid canonical project oracle.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.audit import record as audit_record
from app.cost import CostError, to_decimal
from app.intake.extraction import actual_cost, project_cost
from app.llm.client import LLMClient
from app.llm.pricing import ModelPrice, UnpricedModelError, get_price
from app.models.agent_blueprint import AgentBlueprint
from app.models.agent_instance import AgentInstance
from app.models.agent_realization import AgentRealization
from app.models.agent_version import AgentVersion
from app.models.intake_artifact import IntakeArtifact
from app.models.intake_provenance import IntakeProvenance
from app.models.test_oracle_run import TestOracleRun
from app.models.test_result import TestResult
from app.release.project_repo import resolve_declared_repo
from app.release.scm_connector import SCMConnector, SCMConnectorError
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.tenancy import TenantContext, TenantScopedRepository
from app.verify.oracles import (
    CaseResult,
    InvalidOracleDefinition,
    MAX_DEFINITION_BYTES,
    OracleDefinition,
    canonical_digest,
    definition_hash,
    evaluate_reference,
    evaluate_specified,
    validate_definition,
)
from app.verify.judgment import (
    MAX_JUDGMENT_OUTPUT_TOKENS,
    MAX_SAMPLE_CHARS,
    InvalidJudgmentExecution,
    JudgeLineage,
    JudgmentCallEvidence,
    JudgmentExecution,
    JudgmentUsageEvidence,
    execute_judgment,
)

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class OracleCoverage:
    scoped_oracle_count: int
    valid_definition_count: int
    invalid_definition_count: int
    binding_present: bool
    unrun_count: int
    untrusted_count: int
    incomplete_count: int
    execution_failed_count: int
    judgment_control_failed_count: int
    failed_count: int
    passed_count: int

    def gate_kwargs(self) -> dict[str, int | bool]:
        return {
            "test_oracle_scope_resolved": True,
            "test_oracle_scope_count": self.scoped_oracle_count,
            "test_oracle_valid_definition_count": self.valid_definition_count,
            "test_oracle_invalid_definition_count": self.invalid_definition_count,
            "test_oracle_binding_present": self.binding_present,
            "test_oracle_unrun_count": self.unrun_count,
            "test_oracle_untrusted_count": self.untrusted_count,
            "test_oracle_incomplete_count": self.incomplete_count,
            "test_oracle_execution_failed_count": self.execution_failed_count,
            "test_oracle_judgment_control_failed_count": self.judgment_control_failed_count,
            "test_oracle_failed_count": self.failed_count,
            "test_oracle_passed_count": self.passed_count,
        }


class TestOracleRepository(TenantScopedRepository):
    __test__ = False

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, TestOracleRun)

    async def execute_ci(
        self,
        *,
        project_id: uuid.UUID,
        oracle_artifact_id: uuid.UUID,
        commit_sha: str,
        connector: SCMConnector,
        actor: str,
        llm_clients: Mapping[str, LLMClient] | None = None,
        price_card: dict[str, ModelPrice] | None = None,
    ) -> TestOracleRun:
        """Execute one canonical oracle against connector-verified exact-commit observations."""
        if _COMMIT_RE.fullmatch(commit_sha) is None:
            raise ValueError("commit_sha must be 40 lowercase hexadecimal characters")
        declared = await resolve_declared_repo(self.session, self.context, project_id)
        if declared is None:
            raise ValueError("project has no valid declared repository")
        repo_ref, _branch = declared
        oracle, target_requirement = await self._canonical_oracle(
            project_id, oracle_artifact_id
        )
        definition = validate_definition(oracle.data)
        if definition.target_requirement != target_requirement:
            raise InvalidOracleDefinition(
                "target_requirement does not match the canonical requirement parent"
            )
        digest = definition_hash(definition)
        repo_hash = canonical_digest(repo_ref)

        try:
            payload = await connector.fetch_test_oracle_artifact(
                repo_ref=repo_ref, commit_sha=commit_sha
            )
        except (SCMConnectorError, ValueError):
            return await self._record_failure(
                project_id, oracle, definition, digest, repo_hash, commit_sha, "connector_failure", actor
            )
        if payload is None:
            return await self._record_failure(
                project_id, oracle, definition, digest, repo_hash, commit_sha, "artifact_missing", actor
            )
        matching = [
            item
            for item in payload["oracles"]
            if item["oracle_artifact_id"] == str(oracle_artifact_id)
        ]
        if not matching:
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "oracle_result_missing",
                actor,
            )
        item = matching[0]
        if item["definition_hash"] != digest:
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "definition_binding_mismatch",
                actor,
            )
        if definition.oracle_type == "judgment":
            return await self._execute_judgment(
                project_id=project_id,
                oracle=oracle,
                definition=definition,
                digest=digest,
                repo_hash=repo_hash,
                commit_sha=commit_sha,
                observations=item["observations"],
                clients=llm_clients,
                price_card=price_card,
                actor=actor,
            )
        try:
            results = (
                evaluate_specified(definition, item["observations"])
                if definition.oracle_type == "specified"
                else evaluate_reference(definition, item["observations"])
            )
        except InvalidOracleDefinition:
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "observation_validation_failed",
                actor,
            )
        return await self._record_deterministic_success(
            project_id, oracle, definition, digest, repo_hash, commit_sha, results, actor
        )

    async def coverage_for_project(self, project_id: uuid.UUID) -> OracleCoverage:
        """Compute conservative exact-binding latest-wins coverage with no wall-clock TTL."""
        scoped_oracles = list(await self._canonical_oracles(project_id))
        valid: list[tuple[IntakeArtifact, str]] = []
        invalid = 0
        for oracle, target_requirement in scoped_oracles:
            try:
                definition = validate_definition(oracle.data)
                if definition.target_requirement != target_requirement:
                    raise InvalidOracleDefinition(
                        "target_requirement does not match the canonical requirement parent"
                    )
                valid.append((oracle, definition_hash(definition)))
            except InvalidOracleDefinition:
                invalid += 1

        declared = await resolve_declared_repo(self.session, self.context, project_id)
        if declared is None or not valid:
            return OracleCoverage(
                len(scoped_oracles), len(valid), invalid, False, len(valid), 0, 0, 0, 0, 0, 0
            )
        repo_hash = canonical_digest(declared[0])
        oracle_ids = [oracle.id for oracle, _digest in valid]
        # Conservative inference: the repository has no separate persisted "current commit".
        # The newest committed run for the currently declared repo therefore selects ONE commit;
        # every scoped oracle must have current-definition evidence at that exact same commit.
        # A newer attempt shifts the selection and makes missing peer-oracle runs fail closed.
        selected = (
            await self.session.execute(
                select(TestOracleRun)
                .where(
                    TestOracleRun.tenant_id == self.context.tenant_id,
                    TestOracleRun.project_id == project_id,
                    TestOracleRun.oracle_artifact_id.in_(oracle_ids),
                    TestOracleRun.repo_binding_hash == repo_hash,
                )
                .order_by(TestOracleRun.created_at.desc(), TestOracleRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if selected is None:
            return OracleCoverage(
                len(scoped_oracles), len(valid), invalid, False, len(valid), 0, 0, 0, 0, 0, 0
            )

        counts = {
            "unrun": 0,
            "untrusted": 0,
            "incomplete": 0,
            "execution_failed": 0,
            "judgment_control_failed": 0,
            "failed": 0,
            "passed": 0,
        }
        for oracle, digest in valid:
            latest = (
                await self.session.execute(
                    select(TestOracleRun)
                    .where(
                        TestOracleRun.tenant_id == self.context.tenant_id,
                        TestOracleRun.project_id == project_id,
                        TestOracleRun.oracle_artifact_id == oracle.id,
                        TestOracleRun.definition_hash == digest,
                        TestOracleRun.repo_binding_hash == repo_hash,
                        TestOracleRun.commit_sha == selected.commit_sha,
                    )
                    .order_by(TestOracleRun.created_at.desc(), TestOracleRun.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if latest is None:
                counts["unrun"] += 1
            elif latest.execution_status != "succeeded":
                counts["execution_failed"] += 1
            elif latest.observation_provenance != "connector_verified_ci":
                counts["untrusted"] += 1
            elif latest.reported_distinct_case_count != latest.required_sample_size:
                counts["incomplete"] += 1
            elif latest.oracle_type == "judgment" and latest.verdict != "passed":
                counts["judgment_control_failed"] += 1
            elif latest.verdict == "passed":
                counts["passed"] += 1
            else:
                counts["failed"] += 1
        return OracleCoverage(
            len(scoped_oracles),
            len(valid),
            invalid,
            True,
            counts["unrun"],
            counts["untrusted"],
            counts["incomplete"],
            counts["execution_failed"],
            counts["judgment_control_failed"],
            counts["failed"],
            counts["passed"],
        )

    async def _canonical_oracle(
        self, project_id: uuid.UUID, oracle_artifact_id: uuid.UUID
    ) -> tuple[IntakeArtifact, str]:
        rows = await self._canonical_oracles(project_id, oracle_artifact_id)
        if not rows:
            raise ValueError("unknown canonical test oracle for this project/tenant")
        return rows[0]

    async def _canonical_oracles(
        self, project_id: uuid.UUID, oracle_artifact_id: uuid.UUID | None = None
    ) -> list[tuple[IntakeArtifact, str]]:
        parent = aliased(IntakeArtifact)
        requirement = aliased(IntakeArtifact)
        stmt = (
            select(IntakeArtifact, requirement.ref)
            .join(parent, IntakeArtifact.parent_id == parent.id)
            .join(requirement, parent.parent_id == requirement.id)
            .join(
                IntakeProvenance,
                (IntakeProvenance.artifact_id == IntakeArtifact.id)
                & (IntakeProvenance.project_id == IntakeArtifact.project_id)
                & (IntakeProvenance.tenant_id == IntakeArtifact.tenant_id),
            )
            .where(
                IntakeArtifact.tenant_id == self.context.tenant_id,
                IntakeArtifact.project_id == project_id,
                IntakeArtifact.kind == "test_oracle",
                parent.kind == "acceptance_criterion",
                requirement.kind == "requirement",
            )
            .distinct()
            .order_by(IntakeArtifact.id)
        )
        if oracle_artifact_id is not None:
            stmt = stmt.where(IntakeArtifact.id == oracle_artifact_id)
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]

    def _run_base(
        self,
        project_id: uuid.UUID,
        oracle: IntakeArtifact,
        definition: OracleDefinition,
        digest: str,
        repo_hash: str,
        commit_sha: str,
    ) -> dict:
        return {
            "tenant_id": self.context.tenant_id,
            "project_id": project_id,
            "oracle_artifact_id": oracle.id,
            "definition_hash": digest,
            "definition_schema_version": definition.schema_version,
            "repo_binding_hash": repo_hash,
            "commit_sha": commit_sha,
            "oracle_type": definition.oracle_type,
            "runner_key": definition.runner_key,
            "runner_version": "slice43.v1",
            "required_sample_size": definition.sample_size,
            "minimum_pass_rate": definition.minimum_pass_rate,
            "irr_minimum": definition.irr_minimum,
            "human_review_required": definition.human_review_required,
        }

    async def _record_failure(
        self,
        project_id: uuid.UUID,
        oracle: IntakeArtifact,
        definition: OracleDefinition,
        digest: str,
        repo_hash: str,
        commit_sha: str,
        failure_code: str,
        actor: str,
        run_id: uuid.UUID | None = None,
        execution_status: str = "failed",
    ) -> TestOracleRun:
        run = TestOracleRun(
            **({"id": run_id} if run_id is not None else {}),
            **self._run_base(project_id, oracle, definition, digest, repo_hash, commit_sha),
            execution_status=execution_status,
            observation_provenance="caller_supplied_unverified",
            execution_provenance="system_attempted",
            failure_code=failure_code,
            reported_result_count=0,
            reported_passed_count=0,
            reported_distinct_case_count=0,
            reported_evaluator_lineage_count=0,
            reported_irr=None,
            reported_unresolved_disagreement_count=0,
        )
        self.session.add(run)
        await self.session.flush()
        await self._audit(run, actor)
        return run

    async def _execute_judgment(
        self,
        *,
        project_id: uuid.UUID,
        oracle: IntakeArtifact,
        definition: OracleDefinition,
        digest: str,
        repo_hash: str,
        commit_sha: str,
        observations: list[dict],
        clients: Mapping[str, LLMClient] | None,
        price_card: dict[str, ModelPrice] | None,
        actor: str,
    ) -> TestOracleRun:
        run_id = uuid.uuid4()
        if clients is None:
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "judgment_clients_missing",
                actor,
                run_id,
                "refused",
            )
        resolved = await self._qualified_judges(project_id, definition)
        if resolved is None:
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "judgment_evaluators_unqualified",
                actor,
                run_id,
                "refused",
            )
        lineages, instance_ids = resolved
        prices: dict[str, ModelPrice] = {}
        try:
            for lineage in lineages:
                price = get_price(lineage.model_route, price_card)
                to_decimal(price.input_usd_per_1k, "input_usd_per_1k")
                to_decimal(price.output_usd_per_1k, "output_usd_per_1k")
                prices[lineage.evaluator_ref] = price
        except (CostError, ValueError, ArithmeticError):
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "judgment_price_invalid",
                actor,
                run_id,
                "refused",
            )
        except UnpricedModelError:
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "judgment_model_unpriced",
                actor,
                run_id,
                "refused",
            )

        estimated_input_tokens = ((MAX_SAMPLE_CHARS + MAX_DEFINITION_BYTES) // 4) + 2_000
        projected = sum(
            (
                project_cost(
                    prices[lineage.evaluator_ref],
                    est_input_tokens=estimated_input_tokens,
                    max_output_tokens=MAX_JUDGMENT_OUTPUT_TOKENS,
                )
                for _case in definition.cases
                for lineage in lineages
            ),
            Decimal(0),
        )
        if await self._projected_exceeds_budget(project_id, projected):
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                "judgment_blocked_by_budget",
                actor,
                run_id,
                "refused",
            )

        def cost_ref(call: JudgmentCallEvidence | JudgmentUsageEvidence) -> str:
            return (
                f"test_oracle_run:{run_id}:case:{call.case_ref}:"
                f"evaluator:{instance_ids[call.evaluator_ref]}"
            )

        async def record_usage(usage: JudgmentUsageEvidence) -> None:
            price = prices[usage.evaluator_ref]
            await CostEventRepository(self.session, self.context).record(
                project_id=project_id,
                component="model_inference",
                amount_usd=actual_cost(
                    price,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                ),
                quantity=usage.input_tokens + usage.output_tokens,
                source_system="llm",
                external_ref=cost_ref(usage),
                actor=actor,
            )

        try:
            execution = await execute_judgment(
                definition=definition,
                observations=observations,
                evaluators=lineages,
                clients=clients,
                on_usage=record_usage,
            )
        except InvalidJudgmentExecution as exc:
            failure = (
                "judgment_refused_injection"
                if "prompt_injection" in str(exc)
                else "judgment_execution_failed"
            )
            return await self._record_failure(
                project_id,
                oracle,
                definition,
                digest,
                repo_hash,
                commit_sha,
                failure,
                actor,
                run_id,
                "refused" if failure == "judgment_refused_injection" else "failed",
            )
        return await self._record_judgment_success(
            project_id,
            oracle,
            definition,
            digest,
            repo_hash,
            commit_sha,
            execution,
            lineages,
            instance_ids,
            cost_ref,
            actor,
            run_id,
        )

    async def _qualified_judges(
        self, project_id: uuid.UUID, definition: OracleDefinition
    ) -> tuple[tuple[JudgeLineage, ...], dict[str, uuid.UUID]] | None:
        rows = (
            await self.session.execute(
                select(AgentInstance, AgentVersion, AgentBlueprint, AgentRealization)
                .join(AgentVersion, AgentVersion.id == AgentInstance.version_id)
                .join(AgentBlueprint, AgentBlueprint.id == AgentVersion.blueprint_id)
                .join(AgentRealization, AgentRealization.instance_id == AgentInstance.id)
                .where(
                    AgentInstance.tenant_id == self.context.tenant_id,
                    AgentInstance.project_id == project_id,
                    AgentInstance.instance_key.in_(definition.reviewers),
                    AgentInstance.status == "active",
                    AgentRealization.qualification_status == "qualified",
                    AgentBlueprint.archetype == "ai_evaluation",
                    AgentBlueprint.status == "active",
                )
            )
        ).all()
        if len(rows) != len(definition.reviewers):
            return None
        by_ref = {
            instance.instance_key: (instance, version, blueprint)
            for instance, version, blueprint, _realization in rows
        }
        if set(by_ref) != set(definition.reviewers):
            return None
        lineages = tuple(
            JudgeLineage(
                evaluator_ref=ref,
                blueprint_id=str(by_ref[ref][2].id),
                version_hash=by_ref[ref][1].content_hash,
                model_route=by_ref[ref][1].model_route,
            )
            for ref in definition.reviewers
        )
        if (
            len({lineage.blueprint_id for lineage in lineages}) != len(lineages)
            or len({lineage.version_hash for lineage in lineages}) != len(lineages)
            or len({lineage.model_route for lineage in lineages}) != len(lineages)
        ):
            return None
        return lineages, {ref: by_ref[ref][0].id for ref in definition.reviewers}

    async def _projected_exceeds_budget(
        self, project_id: uuid.UUID, projected: Decimal
    ) -> bool:
        budget = await BudgetRepository(self.session, self.context).get(project_id)
        if budget is None:
            return True
        costs = CostEventRepository(self.session, self.context)
        if await costs.total_spent(project_id) + projected >= budget.max_total_cost_usd:
            return True
        if budget.max_daily_cost_usd is not None:
            today = datetime.now(timezone.utc).date()
            if await costs.daily_spent(project_id, today) + projected >= budget.max_daily_cost_usd:
                return True
        return False

    async def _record_judgment_success(
        self,
        project_id: uuid.UUID,
        oracle: IntakeArtifact,
        definition: OracleDefinition,
        digest: str,
        repo_hash: str,
        commit_sha: str,
        execution: JudgmentExecution,
        lineages: tuple[JudgeLineage, ...],
        instance_ids: dict[str, uuid.UUID],
        cost_ref: Callable[[JudgmentCallEvidence | JudgmentUsageEvidence], str],
        actor: str,
        run_id: uuid.UUID,
    ) -> TestOracleRun:
        calls = execution.calls
        run = TestOracleRun(
            id=run_id,
            **self._run_base(project_id, oracle, definition, digest, repo_hash, commit_sha),
            execution_status="succeeded",
            observation_provenance="connector_verified_ci",
            execution_provenance="system_executed",
            failure_code=None,
            reported_result_count=len(calls),
            reported_passed_count=sum(call.label for call in calls),
            reported_distinct_case_count=len({call.case_ref for call in calls}),
            reported_evaluator_lineage_count=len({call.evaluator_ref for call in calls}),
            reported_irr=execution.decision.irr,
            reported_unresolved_disagreement_count=(
                execution.decision.unresolved_disagreement_count
            ),
        )
        self.session.add(run)
        await self.session.flush()
        sample_classes = {case.case_ref: case.sample_class for case in definition.cases}
        version_hashes = {
            lineage.evaluator_ref: lineage.version_hash for lineage in lineages
        }
        for call in calls:
            self.session.add(
                TestResult(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    test_oracle_run_id=run.id,
                    case_ref=call.case_ref,
                    sample_class=sample_classes[call.case_ref],
                    result_kind="judgment_vote",
                    expected_digest=None,
                    observed_digest=None,
                    reference_digest=None,
                    observed_numeric=None,
                    reference_numeric=None,
                    tolerance_numeric=None,
                    evaluator_instance_id=instance_ids[call.evaluator_ref],
                    evaluator_version_hash=version_hashes[call.evaluator_ref],
                    llm_provider=call.provider,
                    llm_model=call.model,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    cost_external_ref=cost_ref(call),
                    criterion_scores=call.criterion_scores,
                    judgment_label=call.label,
                )
            )
        await self.session.flush()
        await self._audit(run, actor)
        return run

    async def _record_deterministic_success(
        self,
        project_id: uuid.UUID,
        oracle: IntakeArtifact,
        definition: OracleDefinition,
        digest: str,
        repo_hash: str,
        commit_sha: str,
        results: tuple[CaseResult, ...],
        actor: str,
    ) -> TestOracleRun:
        run = TestOracleRun(
            **self._run_base(project_id, oracle, definition, digest, repo_hash, commit_sha),
            execution_status="succeeded",
            observation_provenance="connector_verified_ci",
            execution_provenance="system_executed",
            failure_code=None,
            reported_result_count=len(results),
            reported_passed_count=sum(result.passed for result in results),
            reported_distinct_case_count=len({result.case_ref for result in results}),
            reported_evaluator_lineage_count=0,
            reported_irr=None,
            reported_unresolved_disagreement_count=0,
        )
        self.session.add(run)
        await self.session.flush()
        for result in results:
            self.session.add(
                TestResult(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    test_oracle_run_id=run.id,
                    case_ref=result.case_ref,
                    sample_class=None,
                    result_kind=result.result_kind,
                    expected_digest=result.expected_digest,
                    observed_digest=result.observed_digest,
                    reference_digest=result.reference_digest,
                    observed_numeric=result.observed_numeric,
                    reference_numeric=result.reference_numeric,
                    tolerance_numeric=result.tolerance_numeric,
                    evaluator_instance_id=None,
                    evaluator_version_hash=None,
                    llm_provider=None,
                    llm_model=None,
                    input_tokens=None,
                    output_tokens=None,
                    cost_external_ref=None,
                    criterion_scores={},
                    judgment_label=None,
                )
            )
        await self.session.flush()
        await self._audit(run, actor)
        return run

    async def _audit(self, run: TestOracleRun, actor: str) -> None:
        await audit_record(
            self.session,
            action="test_oracle.run_recorded",
            actor=actor,
            target=f"test_oracle_run:{run.id}",
            payload={
                "test_oracle_run_id": str(run.id),
                "project_id": str(run.project_id),
                "oracle_artifact_id": str(run.oracle_artifact_id),
                "oracle_type": run.oracle_type,
                "runner_key": run.runner_key,
                "execution_status": run.execution_status,
                "observation_provenance": run.observation_provenance,
                "commit_sha": run.commit_sha,
                "result_count": run.reported_result_count,
                "failure_code": run.failure_code,
                "verdict": run.verdict,
            },
        )
