"""Admin-path publisher. Writes only the two global tables. No tenant scope."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.learning import EXPECTED_BUCKET_COUNT, LearningError
from app.ecosystem.learning_sql import SOURCE_QUERIES
from app.repositories.learning import LearningRepository, row_from_mapping


@dataclass(frozen=True)
class PublishReport:
    """Counts-only publish result."""

    run_id: UUID
    published_bucket_count: int


async def publish_cross_project_aggregates(session: AsyncSession) -> PublishReport:
    """Execute SOURCE_QUERIES, insert parent then 62 children, return counts."""
    rows = []
    for query in SOURCE_QUERIES.values():
        result = await session.execute(text(query))
        rows.extend(row_from_mapping(dict(mapping)) for mapping in result.mappings())
    if len(rows) != EXPECTED_BUCKET_COUNT:
        raise LearningError("bucket_count")
    run = await LearningRepository(session).persist(rows)
    return PublishReport(run_id=run.id, published_bucket_count=run.published_bucket_count)
