"""Tenant-path cost optimizer. Reads the published view only."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.ecosystem.cost_optimizer import (
    CostOptimizerError,
    PublishedBucket,
    RecommendInput,
    RoutingFlags,
    evaluate_recommendation,
)
from app.models.cost_forecast import CostForecastPolicyVersion
from app.models.cost_optimizer import CostOptimizerCitation, CostOptimizerRun
from app.models.cross_project_aggregate import CrossProjectAggregateRun
from app.repositories.cost import evaluate
from app.tenancy import TenantContext, TenantScopedRepository


class CostOptimizerRepository(TenantScopedRepository):
    """Persist one recommendation inside ``tenant_scope``."""

    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        super().__init__(session, context, CostOptimizerRun)

    async def recommend(
        self,
        *,
        project_id: UUID,
        task_class: str,
        risk_level: str,
        ambiguity_high: bool,
        actor: str,
        tool_name: str | None = None,
        routing_flags: RoutingFlags | None = None,
    ) -> CostOptimizerRun:
        """Resolve flags, STOP, published view, evaluate, persist parent then citations."""
        flags, flags_source, policy_version_id = await self._resolve_flags(
            project_id, routing_flags
        )
        stop = await evaluate(self.session, self.context, project_id=project_id)
        latest = (
            await self.session.execute(
                select(CrossProjectAggregateRun).order_by(
                    CrossProjectAggregateRun.created_at.desc(),
                    CrossProjectAggregateRun.id.desc(),
                ).limit(1)
            )
        ).scalar_one_or_none()
        buckets: tuple[PublishedBucket, ...] = ()
        aggregate_run_id = None
        published_bucket_count = 0
        if latest is not None:
            aggregate_run_id = latest.id
            published_bucket_count = latest.published_bucket_count
            buckets = await self._published_view(latest.id)
        rec = evaluate_recommendation(
            RecommendInput(
                task_class=task_class,
                risk_level=risk_level,
                ambiguity_high=ambiguity_high,
                flags=flags,
                tool_name=tool_name,
                stop=stop,
                buckets=buckets,
            )
        )
        run = CostOptimizerRun(
            project_id=project_id,
            task_class=task_class,
            risk_level=risk_level,
            ambiguity_high=ambiguity_high,
            tool_name=tool_name,
            cheap_first_for_low_risk=flags.cheap_first_for_low_risk,
            frontier_for_high_risk=flags.frontier_for_high_risk,
            use_cached_context_when_possible=flags.use_cached_context_when_possible,
            flags_source=flags_source,
            policy_version_id=policy_version_id,
            base_policy_tier=rec.base_policy_tier,
            clamped_policy_tier=rec.clamped_policy_tier,
            recommended_tier=rec.recommended_tier,
            overlay_applied=rec.overlay_applied,
            cache_hint=rec.cache_hint,
            requires_multiple_reviewers=rec.requires_multiple_reviewers,
            requires_model_diversity=rec.requires_model_diversity,
            published_bucket_count=published_bucket_count,
            citation_count=len(rec.cited),
            aggregate_run_id=aggregate_run_id,
        )
        await self.add(run)
        await self.session.flush()
        for cited in rec.cited:
            if cited.bucket_id is None:
                raise CostOptimizerError("citation_bucket_id")
            self.session.add(
                CostOptimizerCitation(
                    tenant_id=self.context.tenant_id,
                    project_id=project_id,
                    run_id=run.id,
                    bucket_id=cited.bucket_id,
                )
            )
        await self.session.flush()
        await audit_record(
            self.session,
            action="cost_optimizer.recorded",
            actor=actor,
            target=f"cost_optimizer:{run.id}",
            payload={
                "task_class": task_class,
                "recommended_tier": rec.recommended_tier,
                "overlay_applied": rec.overlay_applied,
                "citation_count": len(rec.cited),
                "run_id": str(run.id),
            },
        )
        return run

    async def latest_for(self, project_id: UUID) -> CostOptimizerRun | None:
        """Newest run for the project in this tenant."""
        stmt = (
            select(CostOptimizerRun)
            .where(
                CostOptimizerRun.tenant_id == self.context.tenant_id,
                CostOptimizerRun.project_id == project_id,
            )
            .order_by(CostOptimizerRun.created_at.desc(), CostOptimizerRun.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _resolve_flags(
        self, project_id: UUID, routing_flags: RoutingFlags | None
    ) -> tuple[RoutingFlags, str, UUID | None]:
        row = (
            await self.session.execute(
                select(
                    CostForecastPolicyVersion.id,
                    CostForecastPolicyVersion.cheap_first_for_low_risk,
                    CostForecastPolicyVersion.frontier_for_high_risk,
                    CostForecastPolicyVersion.use_cached_context_when_possible,
                    CostForecastPolicyVersion.created_at,
                )
                .where(
                    CostForecastPolicyVersion.tenant_id == self.context.tenant_id,
                    CostForecastPolicyVersion.project_id == project_id,
                )
                .order_by(
                    CostForecastPolicyVersion.created_at.desc(),
                    CostForecastPolicyVersion.id.desc(),
                )
                .limit(1)
            )
        ).one_or_none()
        if row is not None:
            return (
                RoutingFlags(
                    cheap_first_for_low_risk=row.cheap_first_for_low_risk,
                    frontier_for_high_risk=row.frontier_for_high_risk,
                    use_cached_context_when_possible=row.use_cached_context_when_possible,
                ),
                "recorded_cost_policy",
                row.id,
            )
        if routing_flags is None:
            raise CostOptimizerError("no_routing_flags")
        return routing_flags, "caller_supplied", None

    async def _published_view(self, run_id: UUID) -> tuple[PublishedBucket, ...]:
        result = await self.session.execute(
            text(
                "SELECT id, signal_class, bucket_key, n_events, n_projects, "
                "n_tenants, metric_sum, metric_unit, published "
                "FROM cross_project_published_buckets WHERE run_id = :rid"
            ),
            {"rid": run_id},
        )
        buckets = []
        for mapping in result.mappings():
            raw_sum = mapping["metric_sum"]
            buckets.append(
                PublishedBucket(
                    signal_class=str(mapping["signal_class"]),
                    bucket_key=str(mapping["bucket_key"]),
                    n_events=int(mapping["n_events"]),
                    n_projects=int(mapping["n_projects"]),
                    n_tenants=int(mapping["n_tenants"]),
                    metric_sum=None if raw_sum is None else Decimal(raw_sum),
                    metric_unit=str(mapping["metric_unit"]),
                    published=bool(mapping["published"]),
                    bucket_id=mapping["id"],
                )
            )
        return tuple(buckets)
