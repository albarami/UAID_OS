"""Async SQLAlchemy engine + session factory and a real readiness ping.

The engine is created lazily so importing this module never opens a connection
(keeps Docker-free tests and Alembic offline operations safe). ``ping()`` runs a
real ``SELECT 1`` round-trip and is what ``/health/ready`` depends on.
"""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def dispose_engine() -> None:
    """Dispose the engine and reset module state (used by app shutdown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def ping() -> None:
    """Real DB round-trip. Raises if the database is unreachable."""
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session for the request lifetime."""
    async with get_sessionmaker()() as session:
        yield session
