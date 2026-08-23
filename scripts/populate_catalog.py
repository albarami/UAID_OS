"""Admin-path populate of the declared catalog. Prints counts only."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.ecosystem.catalog_populate import populate_declared_catalog


async def main() -> None:
    """Run populate against ADMIN_DATABASE_URL and print counts only."""
    engine = create_async_engine(settings.admin_database_url)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                report = await populate_declared_catalog(session)
        print(len(report.connector_listed))
        print(len(report.connector_skipped))
        print(report.blueprint_listed)
        print(report.blueprint_skipped)
        print(report.intake_listed)
        print(report.intake_skipped)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
