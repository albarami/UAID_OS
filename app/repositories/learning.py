"""Admin persist of a 62-row cross-project snapshot. No uaid_app bucket read."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.learning import (
    EXPECTED_BUCKET_COUNT,
    MIN_CONTRIBUTING_PROJECTS,
    MIN_CONTRIBUTING_TENANTS,
    BucketRow,
    LearningError,
    validate_bucket,
)
from app.models.cross_project_aggregate import (
    CrossProjectAggregateBucket,
    CrossProjectAggregateRun,
)


@dataclass(frozen=True)
class Snapshot:
    """Latest admin-visible snapshot."""

    run: CrossProjectAggregateRun
    buckets: tuple[CrossProjectAggregateBucket, ...]


class LearningRepository:
    """Admin-path persist and latest read over the base tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def persist(self, rows: list[BucketRow]) -> CrossProjectAggregateRun:
        """Insert the parent run first, then exactly 62 children."""
        if len(rows) != EXPECTED_BUCKET_COUNT:
            raise LearningError("bucket_count")
        validated = [validate_bucket(row) for row in rows]
        published = sum(
            1
            for row in validated
            if row.n_projects >= MIN_CONTRIBUTING_PROJECTS
            and row.n_tenants >= MIN_CONTRIBUTING_TENANTS
        )
        run = CrossProjectAggregateRun(
            bucket_count=EXPECTED_BUCKET_COUNT,
            published_bucket_count=published,
        )
        self.session.add(run)
        await self.session.flush()
        for row in validated:
            self.session.add(
                CrossProjectAggregateBucket(
                    run_id=run.id,
                    signal_class=row.signal_class,
                    bucket_key=row.bucket_key,
                    n_events=row.n_events,
                    n_projects=row.n_projects,
                    n_tenants=row.n_tenants,
                    metric_sum=row.metric_sum,
                    metric_unit=row.metric_unit,
                )
            )
        await self.session.flush()
        return run

    async def latest_snapshot(self) -> Snapshot | None:
        """Return the newest run and its children, or None."""
        run = (
            await self.session.execute(
                select(CrossProjectAggregateRun).order_by(
                    CrossProjectAggregateRun.created_at.desc(),
                    CrossProjectAggregateRun.id.desc(),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        buckets = (
            await self.session.execute(
                select(CrossProjectAggregateBucket).where(
                    CrossProjectAggregateBucket.run_id == run.id
                )
            )
        ).scalars().all()
        return Snapshot(run=run, buckets=tuple(buckets))


def row_from_mapping(mapping: dict) -> BucketRow:
    """Build a ``BucketRow`` from a source-query mapping."""
    raw_sum = mapping["metric_sum"]
    return BucketRow(
        signal_class=str(mapping["signal_class"]),
        bucket_key=str(mapping["bucket_key"]),
        n_events=int(mapping["n_events"]),
        n_projects=int(mapping["n_projects"]),
        n_tenants=int(mapping["n_tenants"]),
        metric_sum=None if raw_sum is None else Decimal(raw_sum),
        metric_unit=str(mapping["metric_unit"]),
    )
