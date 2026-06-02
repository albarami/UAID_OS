"""Test fixtures for DB-backed tests.

Schema source is Alembic only (never ``create_all``). A session-scoped fixture
auto-creates the ``app_test`` database from the maintenance connection if absent
and runs ``alembic upgrade head`` against it. Each test runs inside an outer
transaction that is rolled back on teardown (with a SAVEPOINT that restarts so
code under test may itself commit), so no test mutates persistent state.

DB-backed tests are skipped cleanly if Postgres is unreachable, so the
Docker-free ``make test`` run is unaffected.
"""

import asyncio

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings

# Admin (owner/superuser `app`) — schema build, migrations, and test seeding.
TEST_ADMIN_URL = settings.test_admin_database_url
# Runtime (non-superuser `uaid_app`) — the RLS-enforced connection under test.
TEST_RUNTIME_URL = settings.test_database_url


async def _create_test_db_if_missing() -> None:
    url = make_url(TEST_ADMIN_URL)
    admin = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await admin.close()


def _postgres_reachable() -> bool:
    async def _check() -> bool:
        url = make_url(TEST_ADMIN_URL)
        try:
            conn = await asyncpg.connect(
                user=url.username,
                password=url.password,
                host=url.host,
                port=url.port,
                database="postgres",
                timeout=2,
            )
            await conn.close()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


@pytest.fixture(scope="session")
def _schema() -> None:
    """Ensure app_test exists and is migrated to head via Alembic.

    Not autouse — only DB-backed tests (which request ``db_session``) trigger
    this, so the Docker-free ``make test`` run never touches Postgres.
    """
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable; run `make up` for DB-backed tests")
    asyncio.run(_create_test_db_if_missing())
    cfg = Config("alembic.ini")
    # env.py reads ALEMBIC_DATABASE_URL; migrations MUST run with ADMIN creds.
    import os

    prior = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_ADMIN_URL
    try:
        command.upgrade(cfg, "head")
    finally:
        # Restore to avoid leaking the override to the rest of the process.
        if prior is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = prior


@pytest.fixture
def postgres_ready(_schema) -> None:
    """Guarantee the target DB exists and is migrated (via `_schema`) before the
    readiness route test runs; skips cleanly if Postgres is unreachable
    (keeps `make test` Docker-free). Depends on `_schema` so Alembic remains the
    sole schema source and the readiness test hits the same migrated DB as the
    rest of the DB-backed suite."""
    if not _postgres_reachable():
        pytest.skip("Postgres not reachable; run `make up` for DB-backed tests")


@pytest_asyncio.fixture
async def db_session(_schema) -> AsyncSession:
    """A session joined to an external transaction; rolled back after each test.

    Connects with ADMIN creds (`app`). This bypasses RLS by design — it backs the
    Slice 1 app-layer tenancy tests (INV-1..4). RLS (INV-5) is proven separately
    via the `uaid_app` runtime fixtures below.
    """
    engine = create_async_engine(TEST_ADMIN_URL)
    conn = await engine.connect()
    trans = await conn.begin()
    await conn.begin_nested()
    session = AsyncSession(bind=conn, expire_on_commit=False)

    @event.listens_for(session.sync_session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        if conn.closed:
            return
        if not conn.in_nested_transaction():
            conn.sync_connection.begin_nested()

    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


# --- RLS (INV-5) fixtures: non-superuser `uaid_app` runtime connection ---------


@pytest_asyncio.fixture
async def admin_engine(_schema):
    """Engine with ADMIN creds for seeding tenant data (bypasses RLS)."""
    engine = create_async_engine(TEST_ADMIN_URL)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def rls_engine(_schema):
    """Engine connecting as the non-superuser `uaid_app` role — subject to RLS.

    FAILS (not skips) if the runtime connection is unusable: `make test-db`
    bootstraps the `uaid_app` role, so an unavailable role is a real defect in
    the setup, not a reason to silently skip the RLS proofs.
    """
    engine = create_async_engine(TEST_RUNTIME_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.fail(
            f"uaid_app runtime connection unavailable ({exc}); "
            "run `make db-bootstrap-rls-role` (needs RLS_DB_PASSWORD)."
        )
    try:
        yield engine
    finally:
        await engine.dispose()
