"""Tenant-scoped Slice-56 ops-signal persistence.

Allowlisted reads: BudgetRepository.get, one bounded cost aggregate, distinct
failed-run ids from immutable run_steps. Threshold comparison uses pure
``app.cost.evaluate_stop``. Does not call ledger total helpers or the composed
repository stop evaluator.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.cost import BudgetCeilings, evaluate_stop, to_decimal
from app.models.budget import Budget
from app.models.cost_event import CostEvent
from app.models.ops_signal import OpsObservationRun, OpsSignalResult
from app.models.run_step import RunStep
from app.ops.signals import (
    HISTORY_LIMIT_DEFAULT,
    OpsObservationSnapshot,
    OpsSignalError,
    SignalRow,
    validate_history_limit,
)
from app.repositories.cost import BudgetRepository
from app.tenancy import TenantContext, TenantScopedRepository


def _row_from_orm(result: OpsSignalResult) -> SignalRow:
    return SignalRow(
        seq=result.seq,
        signal_class=result.signal_class,
        observation_status=result.observation_status,
        truth_tier=result.truth_tier,
        source_kind=result.source_kind,
        source_table=result.source_table,
        source_ref=result.source_ref,
        source_digest=result.source_digest,
        window_kind=result.window_kind,
        window_start=result.window_start,
        window_end=result.window_end,
        reason_code=result.reason_code,
        threshold_provenance=result.threshold_provenance,
        threshold_kind=result.threshold_kind,
        threshold_int=result.threshold_int,
        threshold_ratio=result.threshold_ratio,
        threshold_money=result.threshold_money,
        threshold_money_daily=result.threshold_money_daily,
        metric_kind=result.metric_kind,
        metric_int=result.metric_int,
        metric_ratio=result.metric_ratio,
        metric_money=result.metric_money,
        metric_money_daily=result.metric_money_daily,
        threshold_state=result.threshold_state,
    )


def snapshot_from_run(
    run: OpsObservationRun, results: list[OpsSignalResult]
) -> OpsObservationSnapshot:
    """Copy a persisted run into a detached snapshot."""
    ordered = sorted(results, key=lambda row: row.seq)
    return OpsObservationSnapshot(
        id=run.id,
        project_id=run.project_id,
        as_of=run.as_of,
        ruleset_version=run.ruleset_version,
        idempotency_key=run.idempotency_key,
        request_digest=run.request_digest,
        input_digest=run.input_digest,
        observed_count=run.observed_count,
        caller_supplied_count=run.caller_supplied_count,
        not_observed_count=run.not_observed_count,
        breached_count=run.breached_count,
        signals=tuple(_row_from_orm(row) for row in ordered),
    )


class OpsSignalRepository(TenantScopedRepository):
    """Persist and read ops observation runs inside an open tenant transaction."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, OpsObservationRun)

    async def cost_spend_as_of(
        self, project_id: uuid.UUID, as_of: datetime
    ) -> tuple[Decimal, Decimal]:
        """Return (total_spent, daily_spent) for ``occurred_at < as_of`` in one query."""
        utc_start = datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc)
        stmt = select(
            func.coalesce(
                func.sum(CostEvent.amount_usd).filter(CostEvent.occurred_at < as_of),
                0,
            ),
            func.coalesce(
                func.sum(CostEvent.amount_usd).filter(
                    CostEvent.occurred_at >= utc_start,
                    CostEvent.occurred_at < as_of,
                ),
                0,
            ),
        ).where(
            CostEvent.tenant_id == self.context.tenant_id,
            CostEvent.project_id == project_id,
        )
        total, daily = (await self.session.execute(stmt)).one()
        return to_decimal(total, "total_spent"), to_decimal(daily, "daily_spent")

    async def budget_ceilings(self, project_id: uuid.UUID) -> BudgetCeilings | None:
        """Return recorded budget ceilings, or None when no budget row exists."""
        row: Budget | None = await BudgetRepository(self.session, self.context).get(project_id)
        if row is None:
            return None
        return BudgetCeilings(
            max_total_cost_usd=row.max_total_cost_usd,
            max_daily_cost_usd=row.max_daily_cost_usd,
        )

    async def failed_run_ids_as_of(
        self, project_id: uuid.UUID, as_of: datetime
    ) -> tuple[uuid.UUID, ...]:
        """Distinct run_id values from immutable ``run_failed`` steps before as_of."""
        stmt = (
            select(RunStep.run_id)
            .where(
                RunStep.tenant_id == self.context.tenant_id,
                RunStep.project_id == project_id,
                RunStep.event_type == "run_failed",
                RunStep.created_at < as_of,
            )
            .group_by(RunStep.run_id)
            .order_by(RunStep.run_id.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return tuple(rows)

    async def get_by_idempotency(
        self, project_id: uuid.UUID, idempotency_key: str
    ) -> OpsObservationRun | None:
        stmt = select(OpsObservationRun).where(
            OpsObservationRun.tenant_id == self.context.tenant_id,
            OpsObservationRun.project_id == project_id,
            OpsObservationRun.idempotency_key == idempotency_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def try_insert_run(
        self,
        *,
        project_id: uuid.UUID,
        idempotency_key: str,
        request_digest: str,
        input_digest: str,
        as_of: datetime,
        observed_count: int,
        caller_supplied_count: int,
        not_observed_count: int,
        breached_count: int,
    ) -> uuid.UUID | None:
        """INSERT … ON CONFLICT DO NOTHING. Returns new id, or None on collision."""
        stmt = (
            pg_insert(OpsObservationRun)
            .values(
                tenant_id=self.context.tenant_id,
                project_id=project_id,
                ruleset_version="slice56.v1",
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                input_digest=input_digest,
                as_of=as_of,
                signal_count=11,
                observed_count=observed_count,
                caller_supplied_count=caller_supplied_count,
                not_observed_count=not_observed_count,
                breached_count=breached_count,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "project_id", "idempotency_key"],
            )
            .returning(OpsObservationRun.id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def insert_results(self, run: OpsObservationRun, rows: tuple[SignalRow, ...]) -> None:
        for row in rows:
            self.session.add(
                OpsSignalResult(
                    tenant_id=self.context.tenant_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    seq=row.seq,
                    signal_class=row.signal_class,
                    observation_status=row.observation_status,
                    truth_tier=row.truth_tier,
                    source_kind=row.source_kind,
                    source_table=row.source_table,
                    source_ref=row.source_ref,
                    source_digest=row.source_digest,
                    window_kind=row.window_kind,
                    window_start=row.window_start,
                    window_end=row.window_end,
                    reason_code=row.reason_code,
                    threshold_provenance=row.threshold_provenance,
                    threshold_kind=row.threshold_kind,
                    threshold_int=row.threshold_int,
                    threshold_ratio=row.threshold_ratio,
                    threshold_money=row.threshold_money,
                    threshold_money_daily=row.threshold_money_daily,
                    metric_kind=row.metric_kind,
                    metric_int=row.metric_int,
                    metric_ratio=row.metric_ratio,
                    metric_money=row.metric_money,
                    metric_money_daily=row.metric_money_daily,
                    threshold_state=row.threshold_state,
                )
            )
        await self.session.flush()

    async def results_for(self, run_id: uuid.UUID) -> list[OpsSignalResult]:
        stmt = (
            select(OpsSignalResult)
            .where(
                OpsSignalResult.tenant_id == self.context.tenant_id,
                OpsSignalResult.run_id == run_id,
            )
            .order_by(OpsSignalResult.seq.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def snapshot(self, run: OpsObservationRun) -> OpsObservationSnapshot:
        return snapshot_from_run(run, await self.results_for(run.id))

    async def record_run(
        self,
        *,
        project_id: uuid.UUID,
        idempotency_key: str,
        request_digest: str,
        input_digest: str,
        as_of: datetime,
        observed_count: int,
        caller_supplied_count: int,
        not_observed_count: int,
        breached_count: int,
        rows: tuple[SignalRow, ...],
        actor: str,
    ) -> OpsObservationSnapshot | None:
        """Insert the parent+children when this session wins the idempotency key."""
        new_id = await self.try_insert_run(
            project_id=project_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            input_digest=input_digest,
            as_of=as_of,
            observed_count=observed_count,
            caller_supplied_count=caller_supplied_count,
            not_observed_count=not_observed_count,
            breached_count=breached_count,
        )
        if new_id is None:
            return None
        run = await self.session.get(OpsObservationRun, new_id)
        if run is None:
            raise OpsSignalError("inserted ops observation run was not readable")
        await self.insert_results(run, rows)
        await audit_record(
            self.session,
            action="ops_signals.recorded",
            actor=actor,
            target=f"ops_observation_run:{run.id}",
            payload={
                "project_id": str(project_id),
                "run_id": str(run.id),
                "observed_count": observed_count,
                "caller_supplied_count": caller_supplied_count,
                "not_observed_count": not_observed_count,
                "breached_count": breached_count,
                "ruleset_version": run.ruleset_version,
                "request_digest": request_digest,
                "input_digest": input_digest,
            },
        )
        return await self.snapshot(run)

    async def latest(self, project_id: uuid.UUID) -> OpsObservationSnapshot | None:
        stmt = (
            select(OpsObservationRun)
            .where(
                OpsObservationRun.tenant_id == self.context.tenant_id,
                OpsObservationRun.project_id == project_id,
            )
            .order_by(OpsObservationRun.created_at.desc(), OpsObservationRun.id.desc())
            .limit(1)
        )
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if run is None:
            return None
        return await self.snapshot(run)

    async def history(
        self, project_id: uuid.UUID, *, limit: int = HISTORY_LIMIT_DEFAULT
    ) -> list[OpsObservationSnapshot]:
        bounded = validate_history_limit(limit)
        stmt = (
            select(OpsObservationRun)
            .where(
                OpsObservationRun.tenant_id == self.context.tenant_id,
                OpsObservationRun.project_id == project_id,
            )
            .order_by(OpsObservationRun.created_at.desc(), OpsObservationRun.id.desc())
            .limit(bounded)
        )
        runs = list((await self.session.execute(stmt)).scalars().all())
        return [await self.snapshot(run) for run in runs]


def stop_decision_for_snapshot(
    *,
    total_spent: Decimal,
    daily_spent: Decimal,
    budget: BudgetCeilings | None,
):
    """Pure evaluate_stop over the ops-owned snapshot. Not the composed ledger evaluator."""
    return evaluate_stop(total_spent=total_spent, daily_spent=daily_spent, budget=budget)
