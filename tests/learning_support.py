"""Shared Slice 62 fixtures: isolated DB, seeds, trigger helpers, frozen hashes."""

from __future__ import annotations

import atexit
import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.ecosystem.cost_optimizer import RoutingFlags
from app.repositories.cost import BudgetRepository, CostEventRepository
from app.tenancy import TenantContext
from tests.conftest import TEST_ADMIN_URL, TEST_RUNTIME_URL

FROZEN_HASHES: dict[str, str] = {
    "app/tools/broker.py": "20728181a65073d0ec5cacb63385fa2101760ec670e54621991eb24a97a33c57",
    "app/tools/registry.py": "c10023cfcbd074bb8c99e4dc0fa5a2b7de89d685820394b0902cde1ccfcc94e3",
    "app/policy/matrix.py": "c69a09ee8f910bffa839a8b75154dd3f3025fdb44c0c5aa0b9bfdd6e6f31a43f",
    "app/release/production_autonomy.py": (
        "55d8bb179321e57ffd4ee3b514cb1ff386e6e5b81cf00e2bfdcbab02fd093029"
    ),
    "app/intake/readiness.py": "7671979fa7d4f700436439965a85df22052a384b1245bc9a1bfacc261ac63b26",
    "app/runtime/control_loop.py": "3fa5270902b505824358d5ebd61153fa16b16c4b0dcf01d0fef32833edbe1180",
    "app/cost.py": "2dc1e1d1a0dcfb433af536b69bba926b5c74f3c028bda841d243416546819b43",
    "app/cost_forecast.py": "0fb050597363bcb4af6393e48e8822d975094108f92f4c5770ea4656b3ce02b6",
    "app/llm/pricing.py": "0693ab457daefd45fedbf3bd6df08e531568c89e2ca9a91dbd710c40febe5d59",
    "app/agents/registry.py": "d22471117d28958251a375cbc7cfebf6ac3c027ae21e28393f7e58c14cb5e1f5",
}

LEARNING_TABLES: tuple[str, ...] = (
    "cross_project_aggregate_runs",
    "cross_project_aggregate_buckets",
    "cost_optimizer_runs",
    "cost_optimizer_citations",
)

CALLER_FLAGS = RoutingFlags(
    cheap_first_for_low_risk=True,
    frontier_for_high_risk=False,
    use_cached_context_when_possible=False,
)

CHEAP_HIGH_FLAGS = RoutingFlags(
    cheap_first_for_low_risk=False,
    frontier_for_high_risk=True,
    use_cached_context_when_possible=True,
)


def file_sha256(path: str) -> str:
    """Return the sha256 hex digest of a workspace file."""
    return __import__("hashlib").sha256(Path(path).read_bytes()).hexdigest()


def policy_payload(
    *,
    cheap_first: bool = True,
    frontier: bool = True,
    cached: bool = True,
) -> dict:
    """Structured policy dict. Tests own the USD figures; optimizer must not read them."""
    return {
        "cost_and_resource_policy": {
            "max_total_model_cost_usd": 100,
            "max_daily_model_cost_usd": 50,
            "max_cloud_spend_usd": 100,
            "max_ci_minutes_per_day": 100,
            "require_approval_above_forecast_percentage": 90,
            "model_routing": {
                "cheap_first_for_low_risk": cheap_first,
                "frontier_for_high_risk": frontier,
                "use_cached_context_when_possible": cached,
            },
            "stop_conditions": [
                "budget_exceeded",
                "repeated_failure_without_new_strategy",
                "tool_loop_detected",
                "model_provider_outage_extended",
            ],
        }
    }


@contextmanager
def _alembic_url(url: str) -> Iterator[Config]:
    prior = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield Config("alembic.ini")
    finally:
        if prior is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = prior


async def _admin_connect(database: str = "postgres"):
    import asyncpg

    url = make_url(TEST_ADMIN_URL)
    return await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=database,
    )


_TEMPLATE_NAME: str | None = None


def _sync_exec(sql: str, database: str = "postgres") -> None:
    async def _go() -> None:
        conn = await _admin_connect(database)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_go())


def _drop_database_sync(dbname: str) -> None:
    _sync_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')


def _drop_template_atexit() -> None:
    global _TEMPLATE_NAME
    if _TEMPLATE_NAME is None:
        return
    try:
        _drop_database_sync(_TEMPLATE_NAME)
    except Exception:
        pass
    _TEMPLATE_NAME = None


atexit.register(_drop_template_atexit)


def _build_template_sync() -> str:
    """Create and migrate the empty template (must not run inside an event loop)."""
    url = make_url(TEST_ADMIN_URL)
    dbname = f"app_test_s62_tpl_{uuid.uuid4().hex[:8]}"
    _sync_exec(f'CREATE DATABASE "{dbname}"')
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    with _alembic_url(alembic_url) as cfg:
        command.upgrade(cfg, "head")
    _sync_exec(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{dbname}' AND pid <> pg_backend_pid()"
    )
    return dbname


async def _ensure_template() -> str:
    """Migrate one empty template once; later tests clone it."""
    global _TEMPLATE_NAME
    if _TEMPLATE_NAME is not None:
        return _TEMPLATE_NAME
    _TEMPLATE_NAME = await asyncio.to_thread(_build_template_sync)
    return _TEMPLATE_NAME


async def create_learning_database() -> tuple[str, str, str]:
    """Clone the migrated template and grant CONNECT. Return names/URLs."""
    url = make_url(TEST_ADMIN_URL)
    rls = make_url(TEST_RUNTIME_URL)
    template = await _ensure_template()
    dbname = f"app_test_s62_{uuid.uuid4().hex[:8]}"
    conn = await _admin_connect()
    try:
        await conn.execute(f'CREATE DATABASE "{dbname}" TEMPLATE "{template}"')
        await conn.execute(f'GRANT CONNECT ON DATABASE "{dbname}" TO uaid_app')
    finally:
        await conn.close()
    alembic_url = (
        f"postgresql+asyncpg://{url.username}:{url.password}@{url.host}:{url.port}/{dbname}"
    )
    rls_url = f"postgresql+asyncpg://{rls.username}:{rls.password}@{rls.host}:{rls.port}/{dbname}"
    return dbname, alembic_url, rls_url


async def drop_learning_database(dbname: str) -> None:
    """Drop an isolated learning database."""
    conn = await _admin_connect()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
    finally:
        await conn.close()


@asynccontextmanager
async def learning_world() -> AsyncIterator[dict]:
    """Isolated migrated database with admin and uaid_app engines."""
    dbname, admin_url, rls_url = await create_learning_database()
    admin_engine = create_async_engine(admin_url)
    rls_engine = create_async_engine(rls_url)
    try:
        yield {"admin": admin_engine, "rls": rls_engine, "dbname": dbname, "admin_url": admin_url}
    finally:
        await admin_engine.dispose()
        await rls_engine.dispose()
        await drop_learning_database(dbname)


@asynccontextmanager
async def scoped(engine, ctx: TenantContext) -> AsyncIterator[AsyncSession]:
    """Open a session, set the tenant GUC, yield inside a transaction."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(ctx.tenant_id)},
            )
            yield session


async def seed_two_tenant_three_project(session: AsyncSession) -> dict:
    """Org + two tenants + three projects (t1 has two, t2 has one)."""
    suffix = uuid.uuid4().hex[:8]
    org = (
        await session.execute(
            text("INSERT INTO organizations (name,slug) VALUES ('LrnOrg',:s) RETURNING id"),
            {"s": f"lrn-org-{suffix}"},
        )
    ).scalar_one()
    t1 = (
        await session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'t1',:s) RETURNING id"
            ),
            {"o": org, "s": f"lrn-t1-{suffix}"},
        )
    ).scalar_one()
    t2 = (
        await session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'t2',:s) RETURNING id"
            ),
            {"o": org, "s": f"lrn-t2-{suffix}"},
        )
    ).scalar_one()
    projects = []
    for tenant, label in ((t1, "p1"), (t1, "p2"), (t2, "p3")):
        projects.append(
            (
                await session.execute(
                    text(
                        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,:n,:s) RETURNING id"
                    ),
                    {"t": tenant, "n": label, "s": f"lrn-{label}-{suffix}"},
                )
            ).scalar_one()
        )
    return {
        "org": org,
        "t1": t1,
        "t2": t2,
        "p1": projects[0],
        "p2": projects[1],
        "p3": projects[2],
        "pairs": ((t1, projects[0]), (t1, projects[1]), (t2, projects[2])),
    }


async def seed_one_tenant_three_project(session: AsyncSession) -> dict:
    """Org + one tenant + three projects."""
    suffix = uuid.uuid4().hex[:8]
    org = (
        await session.execute(
            text("INSERT INTO organizations (name,slug) VALUES ('LrnOne',:s) RETURNING id"),
            {"s": f"lrn1-org-{suffix}"},
        )
    ).scalar_one()
    tenant = (
        await session.execute(
            text(
                "INSERT INTO tenants (organization_id,name,slug) VALUES (:o,'t',:s) RETURNING id"
            ),
            {"o": org, "s": f"lrn1-t-{suffix}"},
        )
    ).scalar_one()
    projects = []
    for label in ("a", "b", "c"):
        projects.append(
            (
                await session.execute(
                    text(
                        "INSERT INTO projects (tenant_id,name,slug) VALUES (:t,:n,:s) RETURNING id"
                    ),
                    {"t": tenant, "n": label, "s": f"lrn1-{label}-{suffix}"},
                )
            ).scalar_one()
        )
    return {
        "org": org,
        "t1": tenant,
        "p1": projects[0],
        "p2": projects[1],
        "p3": projects[2],
        "pairs": ((tenant, projects[0]), (tenant, projects[1]), (tenant, projects[2])),
    }


async def record_cost(
    engine,
    tenant_id,
    project_id,
    *,
    component: str,
    amount: str,
    actor: str = "seed",
) -> None:
    """Record one cost event via the real repository on ``engine``."""
    ctx = TenantContext(tenant_id)
    async with scoped(engine, ctx) as session:
        await CostEventRepository(session, ctx).record(
            project_id=project_id,
            component=component,
            amount_usd=amount,
            actor=actor,
        )


async def upsert_budget(
    engine,
    tenant_id,
    project_id,
    *,
    total: str = "100",
    daily: str = "100",
) -> None:
    """Upsert a per-project budget strictly usable as a non-hold ceiling."""
    ctx = TenantContext(tenant_id)
    async with scoped(engine, ctx) as session:
        await BudgetRepository(session, ctx).upsert(
            project_id=project_id,
            max_total_cost_usd=total,
            max_daily_cost_usd=daily,
            actor="seed",
        )


async def seed_costs_on_pairs(
    engine,
    pairs: tuple,
    *,
    component: str,
    amount: str,
) -> None:
    """Record the same component/amount on each (tenant, project) pair."""
    for tenant_id, project_id in pairs:
        await record_cost(engine, tenant_id, project_id, component=component, amount=amount)


async def seed_budgets_on_pairs(engine, pairs: tuple, *, total: str = "100") -> None:
    """Upsert a budget on each pair."""
    for tenant_id, project_id in pairs:
        await upsert_budget(engine, tenant_id, project_id, total=total, daily=total)


async def trigger_enabled(session: AsyncSession, name: str) -> str:
    """Return ``tgenabled`` for a named trigger."""
    value = (
        await session.execute(
            text("SELECT tgenabled FROM pg_trigger WHERE tgname=:n"), {"n": name}
        )
    ).scalar_one()
    return value.decode() if isinstance(value, bytes) else str(value)


async def set_trigger(session: AsyncSession, table: str, name: str, *, enabled: bool) -> None:
    """Enable or disable one named trigger."""
    verb = "ENABLE" if enabled else "DISABLE"
    await session.execute(text(f"ALTER TABLE {table} {verb} TRIGGER {name}"))


async def set_constraints_immediate(session: AsyncSession, *names: str) -> None:
    """Fire named deferrable constraint triggers now."""
    await session.execute(text("SET CONSTRAINTS " + ", ".join(names) + " IMMEDIATE"))


async def insert_optimizer_sql(
    session: AsyncSession,
    *,
    tenant_id,
    project_id,
    overlay: str,
    recommended: str,
    citation_count: int,
    clamped: str = "cost_efficient",
    base: str = "cost_efficient",
    task_class: str = "code_review",
    risk_level: str = "low",
    tool_name: str | None = None,
    aggregate_run_id=None,
    published_bucket_count: int = 0,
    flags_source: str = "caller_supplied",
    policy_version_id=None,
    cheap_first: bool = True,
    frontier: bool = False,
    cached: bool = False,
    ambiguity_high: bool = False,
) -> uuid.UUID:
    """Insert one optimizer parent row. Caller must set the tenant GUC."""
    judgment = task_class == "judgment_oracle_review"
    row_id = (
        await session.execute(
            text(
                "INSERT INTO cost_optimizer_runs ("
                "tenant_id,project_id,task_class,risk_level,ambiguity_high,tool_name,"
                "cheap_first_for_low_risk,frontier_for_high_risk,"
                "use_cached_context_when_possible,flags_source,policy_version_id,"
                "base_policy_tier,clamped_policy_tier,recommended_tier,overlay_applied,"
                "cache_hint,requires_multiple_reviewers,requires_model_diversity,"
                "published_bucket_count,citation_count,aggregate_run_id"
                ") VALUES ("
                ":t,:p,:tc,:rk,:amb,:tool,:cheap,:front,:cache,:fs,:pv,"
                ":base,:clamped,:rec,:ov,:ch,:rm,:rd,:pbc,:cc,:agg"
                ") RETURNING id"
            ),
            {
                "t": tenant_id,
                "p": project_id,
                "tc": task_class,
                "rk": risk_level,
                "amb": ambiguity_high,
                "tool": tool_name,
                "cheap": cheap_first,
                "front": frontier,
                "cache": cached,
                "fs": flags_source,
                "pv": policy_version_id,
                "base": base,
                "clamped": clamped,
                "rec": recommended,
                "ov": overlay,
                "ch": cached,
                "rm": judgment,
                "rd": judgment,
                "pbc": published_bucket_count,
                "cc": citation_count,
                "agg": aggregate_run_id,
            },
        )
    ).scalar_one()
    return row_id


def money(value: str) -> Decimal:
    """Parse a ledger amount."""
    return Decimal(value)
