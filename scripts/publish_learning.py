"""Admin-path publish of cross-project aggregates. Prints counts only."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.ecosystem.learning_publish import publish_cross_project_aggregates


async def main() -> None:
    """Run publish against ADMIN_DATABASE_URL and print run_id and count."""
    engine = create_async_engine(settings.admin_database_url)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                report = await publish_cross_project_aggregates(session)
        print(report.run_id)
        print(report.published_bucket_count)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
