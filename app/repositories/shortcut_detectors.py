"""Repository-controlled Slice-45 hybrid shortcut execution and gate coverage."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
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
from app.models.release_finding import ReleaseFinding
from app.models.release_finding_event import ReleaseFindingEvent
from app.models.shortcut_detector_category_result import ShortcutDetectorCategoryResult
from app.models.shortcut_detector_reviewer_result import ShortcutDetectorReviewerResult
from app.models.shortcut_detector_run import ShortcutDetectorRun
from app.release.project_repo import resolve_declared_repo
from app.release.scm_connector import SCMConnector, SCMConnectorError
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.tenancy import TenantContext, TenantScopedRepository
from app.verify.shortcut_detector import (
    CORPUS_SCHEMA_VERSION,
    MANDATORY_CATEGORIES,
    Gate6Evidence,
    NormalizedShortcutFinding,
    canonical_digest,
    detector_contract_hash,
    run_deterministic_detectors,
)
from app.verify.shortcut_review import (
    MAX_LLM_PACKET_CHARS,
    MAX_REVIEW_OUTPUT_TOKENS,
    InvalidShortcutReview,
    ReviewerCall,
    ReviewerLineage,
    execute_shortcut_review,
)

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _raw_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class ShortcutDetectorRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, ShortcutDetectorRun)

    async def execute_hybrid(
        self,
        *,
        project_id: uuid.UUID,
        commit_sha: str,
        connector: SCMConnector,
        reviewer_refs: Sequence[str],
        clients: Mapping[str, LLMClient],
        price_card: dict[str, ModelPrice] | None,
        actor: str,
    ) -> ShortcutDetectorRun:
        if _COMMIT_RE.fullmatch(commit_sha) is None:
            raise ValueError("commit_sha must be 40 lowercase hexadecimal characters")
        declared = await resolve_declared_repo(self.session, self.context, project_id)
        if declared is None:
            raise ValueError("project has no valid declared repository")
        repo_ref, _branch = declared
        repo_hash = canonical_digest(repo_ref)
        panel = await self._qualified_independent_panel(project_id, reviewer_refs)
        if panel is None:
            return await self._record_failure(
                project_id,
                repo_hash,
                commit_sha,
                "shortcut_independence_unresolved",
                "refused",
                actor,
            )
        lineages, instance_ids = panel
        prices = self._prices(lineages, price_card)
        if prices is None:
            return await self._record_failure(
                project_id, repo_hash, commit_sha, "shortcut_price_invalid", "refused", actor
            )
        projected = sum(
            (
                project_cost(
                    prices[lineage.reviewer_ref],
                    est_input_tokens=(MAX_LLM_PACKET_CHARS // 4) + 1_000,
                    max_output_tokens=MAX_REVIEW_OUTPUT_TOKENS,
                )
                for _category in MANDATORY_CATEGORIES
                for lineage in lineages
            ),
            Decimal(0),
        )
        if await self._projected_exceeds_budget(project_id, projected):
            return await self._record_failure(
                project_id, repo_hash, commit_sha, "shortcut_blocked_by_budget", "refused", actor
            )
        try:
            corpus = await connector.fetch_shortcut_review_corpus(
                repo_ref=repo_ref, commit_sha=commit_sha
            )
        except (SCMConnectorError, ValueError):
            corpus = None
        if corpus is None:
            return await self._record_failure(
                project_id, repo_hash, commit_sha, "shortcut_corpus_unavailable", "failed", actor
            )

        run_id = uuid.uuid4()

        def cost_ref(call: ReviewerCall) -> str:
            return (
                f"shortcut_detector_run:{run_id}:category:{call.category}:"
                f"reviewer:{instance_ids[call.reviewer_ref]}"
            )

        async def record_usage(call: ReviewerCall) -> None:
            await CostEventRepository(self.session, self.context).record(
                project_id=project_id,
                component="model_inference",
                amount_usd=actual_cost(
                    prices[call.reviewer_ref],
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                ),
                quantity=call.input_tokens + call.output_tokens,
                source_system="llm",
                external_ref=cost_ref(call),
                actor=actor,
            )

        deterministic = run_deterministic_detectors(corpus)
        try:
            review = await execute_shortcut_review(
                corpus=corpus,
                reviewers=lineages,
                clients=clients,
                on_usage=record_usage,
            )
        except InvalidShortcutReview as exc:
            failure = (
                "shortcut_review_refused_injection"
                if "prompt_injection" in str(exc)
                else "shortcut_review_execution_failed"
            )
            return await self._record_failure(
                project_id,
                repo_hash,
                commit_sha,
                failure,
                "refused" if "refused" in failure else "failed",
                actor,
            )
        return await self._record_success(
            project_id=project_id,
            repo_hash=repo_hash,
            corpus=corpus,
            deterministic=deterministic,
            review_calls=review.calls,
            lineages=lineages,
            instance_ids=instance_ids,
            cost_ref=cost_ref,
            actor=actor,
            run_id=run_id,
        )

    async def coverage_for_project(self, project_id: uuid.UUID) -> Gate6Evidence:
        declared = await resolve_declared_repo(self.session, self.context, project_id)
        if declared is None:
            return self._empty(binding=False)
        repo_hash = canonical_digest(declared[0])
        latest = (
            await self.session.execute(
                select(ShortcutDetectorRun)
                .where(
                    ShortcutDetectorRun.tenant_id == self.context.tenant_id,
                    ShortcutDetectorRun.project_id == project_id,
                    ShortcutDetectorRun.repo_binding_hash == repo_hash,
                    ShortcutDetectorRun.detector_contract_hash == detector_contract_hash(),
                )
                .order_by(ShortcutDetectorRun.created_at.desc(), ShortcutDetectorRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return self._empty(binding=True)
        categories = list(
            (
                await self.session.execute(
                    select(ShortcutDetectorCategoryResult).where(
                        ShortcutDetectorCategoryResult.tenant_id == self.context.tenant_id,
                        ShortcutDetectorCategoryResult.project_id == project_id,
                        ShortcutDetectorCategoryResult.shortcut_detector_run_id == latest.id,
                    )
                )
            ).scalars()
        )
        completed = sum(
            row.coverage_status in {"completed_clean", "completed_with_findings"}
            for row in categories
        )
        return Gate6Evidence(
            scope_resolved=True,
            binding_resolved=True,
            run_present=True,
            corpus_trusted=(latest.corpus_provenance == "connector_verified_ci_shortcut_corpus"),
            execution_failed=latest.execution_status in {"failed", "refused"},
            independence_resolved=(
                latest.execution_status == "succeeded" and latest.reported_reviewer_count >= 2
            ),
            coverage_complete=latest.coverage_complete,
            evidence_consistent=True,
            mandatory_category_count=len(MANDATORY_CATEGORIES),
            completed_category_count=completed,
            failed_category_count=len(categories) - completed,
            reviewer_count=latest.reported_reviewer_count,
            finding_count=latest.reported_finding_count,
        )

    async def _qualified_independent_panel(
        self, project_id: uuid.UUID, reviewer_refs: Sequence[str]
    ) -> tuple[tuple[ReviewerLineage, ...], dict[str, uuid.UUID]] | None:
        if len(reviewer_refs) != 2 or len(set(reviewer_refs)) != 2:
            return None
        rows = (
            await self.session.execute(
                select(AgentInstance, AgentVersion, AgentBlueprint, AgentRealization)
                .join(AgentVersion, AgentVersion.id == AgentInstance.version_id)
                .join(AgentBlueprint, AgentBlueprint.id == AgentVersion.blueprint_id)
                .join(AgentRealization, AgentRealization.instance_id == AgentInstance.id)
                .where(
                    AgentInstance.tenant_id == self.context.tenant_id,
                    AgentInstance.project_id == project_id,
                    AgentInstance.instance_key.in_(reviewer_refs),
                    AgentInstance.status == "active",
                    AgentBlueprint.status == "active",
                    AgentBlueprint.archetype == "reviewer",
                    AgentRealization.qualification_status == "qualified",
                )
            )
        ).all()
        if len(rows) != 2:
            return None
        by_ref = {
            instance.instance_key: (instance, version, blueprint)
            for instance, version, blueprint, _realization in rows
        }
        if set(by_ref) != set(reviewer_refs):
            return None
        builder_blueprints = set(
            (
                await self.session.execute(
                    select(AgentVersion.blueprint_id)
                    .join(AgentInstance, AgentInstance.version_id == AgentVersion.id)
                    .join(AgentBlueprint, AgentBlueprint.id == AgentVersion.blueprint_id)
                    .where(
                        AgentInstance.tenant_id == self.context.tenant_id,
                        AgentInstance.project_id == project_id,
                        AgentInstance.status == "active",
                        AgentBlueprint.status == "active",
                        AgentBlueprint.archetype == "builder",
                    )
                )
            ).scalars()
        )
        if not builder_blueprints:
            return None
        lineages = tuple(
            ReviewerLineage(
                reviewer_ref=ref,
                blueprint_id=str(by_ref[ref][2].id),
                version_hash=by_ref[ref][1].content_hash,
                model_route=by_ref[ref][1].model_route,
            )
            for ref in reviewer_refs
        )
        if any(uuid.UUID(item.blueprint_id) in builder_blueprints for item in lineages):
            return None
        if (
            len({item.blueprint_id for item in lineages}) != 2
            or len({item.version_hash for item in lineages}) != 2
            or len({item.model_route for item in lineages}) != 2
        ):
            return None
        return lineages, {ref: by_ref[ref][0].id for ref in reviewer_refs}

    @staticmethod
    def _prices(
        lineages: Sequence[ReviewerLineage], price_card: dict[str, ModelPrice] | None
    ) -> dict[str, ModelPrice] | None:
        prices: dict[str, ModelPrice] = {}
        try:
            for lineage in lineages:
                price = get_price(lineage.model_route, price_card)
                to_decimal(price.input_usd_per_1k, "input_usd_per_1k")
                to_decimal(price.output_usd_per_1k, "output_usd_per_1k")
                prices[lineage.reviewer_ref] = price
        except (CostError, ValueError, ArithmeticError, UnpricedModelError):
            return None
        return prices

    async def _projected_exceeds_budget(self, project_id: uuid.UUID, projected: Decimal) -> bool:
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

    async def _record_failure(
        self,
        project_id: uuid.UUID,
        repo_hash: str,
        commit_sha: str,
        failure_code: str,
        status: str,
        actor: str,
    ) -> ShortcutDetectorRun:
        row = ShortcutDetectorRun(
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider="github",
            repo_binding_hash=repo_hash,
            commit_sha=commit_sha,
            schema_version=CORPUS_SCHEMA_VERSION,
            detector_contract_hash=detector_contract_hash(),
            corpus_digest=None,
            corpus_provenance="caller_supplied_unverified",
            deterministic_execution_provenance="none",
            review_execution_provenance="none",
            execution_status=status,
            failure_code=failure_code,
            reported_category_count=0,
            reported_reviewer_count=0,
            reported_reviewer_result_count=0,
            reported_finding_count=0,
            coverage_complete=False,
            coverage_verdict="failed",
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, actor)
        return row

    async def _record_success(
        self,
        *,
        project_id,
        repo_hash,
        corpus,
        deterministic,
        review_calls,
        lineages,
        instance_ids,
        cost_ref,
        actor,
        run_id,
    ) -> ShortcutDetectorRun:
        calls_by_category = {
            category: [call for call in review_calls if call.category == category]
            for category in MANDATORY_CATEGORIES
        }
        deterministic_by_category = {item.category: item for item in deterministic}
        all_findings: dict[str, dict[str, NormalizedShortcutFinding]] = {}
        for category in MANDATORY_CATEGORIES:
            union = {
                finding.fingerprint: finding
                for finding in deterministic_by_category[category].findings
            }
            for call in calls_by_category[category]:
                union.update({finding.fingerprint: finding for finding in call.findings})
            all_findings[category] = union
        finding_count = sum(len(items) for items in all_findings.values())
        row = ShortcutDetectorRun(
            id=run_id,
            tenant_id=self.context.tenant_id,
            project_id=project_id,
            provider="github",
            repo_binding_hash=repo_hash,
            commit_sha=corpus.commit_sha,
            schema_version=corpus.schema_version,
            detector_contract_hash=detector_contract_hash(),
            corpus_digest=corpus.corpus_digest,
            corpus_provenance="connector_verified_ci_shortcut_corpus",
            deterministic_execution_provenance="system_executed_deterministic",
            review_execution_provenance="system_executed_llm_review",
            execution_status="succeeded",
            failure_code=None,
            reported_category_count=len(MANDATORY_CATEGORIES),
            reported_reviewer_count=len(lineages),
            reported_reviewer_result_count=len(review_calls),
            reported_finding_count=finding_count,
            coverage_complete=True,
            coverage_verdict="covered",
        )
        self.session.add(row)
        await self.session.flush()
        lineage_by_ref = {item.reviewer_ref: item for item in lineages}
        for category in MANDATORY_CATEGORIES:
            findings = all_findings[category]
            detector_result = deterministic_by_category[category]
            category_row = ShortcutDetectorCategoryResult(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                shortcut_detector_run_id=row.id,
                category=category,
                deterministic_status="completed",
                review_status="completed",
                coverage_status=("completed_with_findings" if findings else "completed_clean"),
                deterministic_fingerprints=[item.fingerprint for item in detector_result.findings],
                reported_reviewer_result_count=len(calls_by_category[category]),
                reported_finding_count=len(findings),
                detector_evidence_digest=detector_result.evidence_digest,
            )
            self.session.add(category_row)
            await self.session.flush()
            for call in calls_by_category[category]:
                lineage = lineage_by_ref[call.reviewer_ref]
                fingerprints = [item.fingerprint for item in call.findings]
                self.session.add(
                    ShortcutDetectorReviewerResult(
                        tenant_id=self.context.tenant_id,
                        project_id=project_id,
                        shortcut_detector_category_result_id=category_row.id,
                        category=category,
                        reviewer_instance_id=instance_ids[call.reviewer_ref],
                        reviewer_blueprint_id=uuid.UUID(lineage.blueprint_id),
                        reviewer_version_hash=lineage.version_hash,
                        model_route_hash=_raw_hash(lineage.model_route),
                        blind_call=True,
                        execution_status="succeeded",
                        decision="findings" if fingerprints else "clean",
                        finding_fingerprints=fingerprints,
                        reported_finding_count=len(fingerprints),
                        response_digest=canonical_digest(
                            {
                                "category": category,
                                "reviewer_ref": call.reviewer_ref,
                                "fingerprints": fingerprints,
                            }
                        ),
                        input_tokens=call.input_tokens,
                        output_tokens=call.output_tokens,
                        cost_external_ref=cost_ref(call),
                    )
                )
            await self.session.flush()
            deterministic_fingerprints = {item.fingerprint for item in detector_result.findings}
            for fingerprint, finding in findings.items():
                source = (
                    "slice45.detector.v1"
                    if fingerprint in deterministic_fingerprints
                    else "slice45.llm_reviewer"
                )
                finding_row = ReleaseFinding(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    finding_type="shortcut",
                    category=category,
                    severity=finding.severity,
                    summary=finding.summary,
                    detail=finding.detail,
                    source=source,
                    source_provenance="system_executed_shortcut_review",
                    status="open",
                    shortcut_detector_category_result_id=category_row.id,
                    shortcut_finding_fingerprint=fingerprint,
                )
                self.session.add(finding_row)
                await self.session.flush()
                self.session.add(
                    ReleaseFindingEvent(
                        tenant_id=self.context.tenant_id,
                        finding_id=finding_row.id,
                        event_type="created",
                        actor=actor,
                    )
                )
        await self.session.flush()
        await self._audit(row, actor)
        return row

    async def _audit(self, row: ShortcutDetectorRun, actor: str) -> None:
        await audit_record(
            self.session,
            action="release.shortcut_review_executed",
            actor=actor,
            target=f"shortcut_detector_run:{row.id}",
            payload={
                "shortcut_detector_run_id": str(row.id),
                "project_id": str(row.project_id),
                "provider": row.provider,
                "execution_status": row.execution_status,
                "corpus_provenance": row.corpus_provenance,
                "deterministic_execution_provenance": (row.deterministic_execution_provenance),
                "review_execution_provenance": row.review_execution_provenance,
                "failure_code": row.failure_code,
                "reported_category_count": row.reported_category_count,
                "reported_reviewer_count": row.reported_reviewer_count,
                "reported_reviewer_result_count": row.reported_reviewer_result_count,
                "reported_finding_count": row.reported_finding_count,
                "coverage_complete": row.coverage_complete,
                "schema_version": row.schema_version,
                "detector_contract_hash": row.detector_contract_hash,
            },
        )

    @staticmethod
    def _empty(*, binding: bool) -> Gate6Evidence:
        return Gate6Evidence(
            scope_resolved=True,
            binding_resolved=binding,
            run_present=False,
            corpus_trusted=False,
            execution_failed=False,
            independence_resolved=False,
            coverage_complete=False,
            evidence_consistent=True,
            mandatory_category_count=len(MANDATORY_CATEGORIES),
            completed_category_count=0,
            failed_category_count=0,
            reviewer_count=0,
            finding_count=0,
        )
