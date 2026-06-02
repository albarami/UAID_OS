"""Alembic async environment.

URL resolution order (ADMIN credentials only — migrations must NEVER run as the
non-superuser runtime role ``uaid_app``, which cannot perform DDL / ALTER TABLE /
CREATE POLICY):
1. ``ALEMBIC_DATABASE_URL`` env var (the Make targets set this to an admin URL,
   e.g. ``TEST_ADMIN_DATABASE_URL`` for the test schema).
2. ``app.config.settings.admin_database_url`` (the owner/superuser ``app`` role).

There is intentionally **no** fallback to ``settings.database_url`` (the runtime
``uaid_app`` URL), so a misconfiguration fails closed rather than silently trying
to migrate as a role that lacks DDL rights.

``target_metadata`` is the full ``Base.metadata`` — importing ``app.models``
registers every table so autogenerate sees the complete schema.
"""

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Base  # noqa: F401  (populates Base.metadata)

config = context.config

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get("ALEMBIC_DATABASE_URL") or settings.admin_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
