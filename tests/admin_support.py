"""Shared Slice-63 seeding. Reaches policies only via ``apply_policy_change``."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.admin.policy_admin import PolicyChangeResult, apply_policy_change
from app.admin.rbac import OPERATOR_PROVENANCE
from app.identity import AuthenticatedActor
from app.tenancy import TenantContext

ExecuteConn = AsyncSession | AsyncConnection


class SeedPreconditionError(RuntimeError):
    """Raised when runtime-mode seeding cannot see a committed tenant."""


_SEED_MSG = (
    "gated policy seeding in runtime mode needs the "
    "admin_engine fixture and an already-committed tenant; seed before entering tenant_scope, "
    "or pass session_is_admin=True"
)

_GRANT_SQL = """
INSERT INTO public.admin_role_grants (
    tenant_id, principal_subject, admin_role, status,
    granted_by, granted_by_provenance
)
SELECT :t, :p, 'tenant_admin', 'active', 'test:seed', :prov
WHERE NOT EXISTS (
    SELECT 1 FROM public.admin_role_grants
    WHERE tenant_id = :t AND principal_subject = :p AND admin_role = 'tenant_admin'
)
"""


async def _set_guc(session: ExecuteConn, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


async def _insert_grant(session: ExecuteConn, tenant_id: uuid.UUID, principal: str) -> None:
    await session.execute(
        text(_GRANT_SQL),
        {"t": tenant_id, "p": principal, "prov": OPERATOR_PROVENANCE},
    )


def _auth_ctx(ctx: TenantContext, principal: str) -> TenantContext:
    return TenantContext(
        ctx.tenant_id,
        actor=AuthenticatedActor(subject=principal, actor_type="service"),
    )


async def seed_gated_policy(
    *,
    session: AsyncSession,
    ctx: TenantContext,
    project_id: uuid.UUID,
    autonomy_level: int,
    overrides: Mapping[str, Any] | None = None,
    session_is_admin: bool = False,
    admin_engine: AsyncEngine | None = None,
    principal: str = "test:tenant_admin",
) -> PolicyChangeResult:
    """Seed a grant and apply a policy change on the caller's session.

    Builds no engine. Runtime mode requires the existing ``admin_engine``
    fixture and a tenant that connection can already see.
    """
    auth = _auth_ctx(ctx, principal)
    if session_is_admin:
        await _set_guc(session, ctx.tenant_id)
        await _insert_grant(session, ctx.tenant_id, principal)
    else:
        if admin_engine is None:
            raise SeedPreconditionError(_SEED_MSG)
        async with admin_engine.connect() as conn:
            seen = (
                await conn.execute(
                    text("SELECT 1 FROM public.tenants WHERE id = :t"),
                    {"t": ctx.tenant_id},
                )
            ).scalar_one_or_none()
            if seen is None:
                raise SeedPreconditionError(_SEED_MSG)
        async with admin_engine.begin() as conn:
            await _set_guc(conn, ctx.tenant_id)
            await _insert_grant(conn, ctx.tenant_id, principal)
    result = await apply_policy_change(
        session,
        auth,
        project_id=project_id,
        action_kind="set_autonomy_policy",
        autonomy_level=int(autonomy_level),
        overrides=overrides,
    )
    if result.decision.decision != "allowed":
        raise SeedPreconditionError(
            f"gated policy seeding expected allowed, got {result.decision.decision}"
        )
    return result


async def set_guc(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Set ``app.current_tenant`` on this connection."""
    await _set_guc(session, tenant_id)


async def insert_grant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    principal: str,
    role: str,
    *,
    status: str = "active",
) -> uuid.UUID:
    """Insert one grant row as the current role (admin in tests)."""
    from app.admin.rbac import OPERATOR_PROVENANCE

    return (
        await session.execute(
            text(
                "INSERT INTO admin_role_grants ("
                "tenant_id, principal_subject, admin_role, status, "
                "granted_by, granted_by_provenance) "
                "VALUES (:t, :p, :r, :s, 'op', :prov) RETURNING id"
            ),
            {
                "t": tenant_id,
                "p": principal,
                "r": role,
                "s": status,
                "prov": OPERATOR_PROVENANCE,
            },
        )
    ).scalar_one()


async def insert_action(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    kind: str = "set_autonomy_policy",
    decision: str = "allowed",
    role: str | None = "tenant_admin",
    required: str | None = None,
    provenance: str = "request_authenticated",
    principal: str = "alice",
) -> uuid.UUID:
    """Insert one ``admin_actions`` row."""
    from app.admin.rbac import RULESET_VERSION

    required = required or ("tenant_admin" if kind == "set_autonomy_policy" else "tenant_operator")

    async def _run() -> uuid.UUID:
        return (
            await session.execute(
                text(
                    "INSERT INTO admin_actions ("
                    "tenant_id, project_id, action_kind, actor_principal, "
                    "actor_provenance, required_role, actor_role, decision, "
                    "ruleset_version) "
                    "VALUES (:t, :p, :k, :prin, :pr, :req, :ar, :d, :rs) "
                    "RETURNING id"
                ),
                {
                    "t": tenant_id,
                    "p": project_id,
                    "k": kind,
                    "prin": principal,
                    "pr": provenance,
                    "req": required,
                    "ar": role,
                    "d": decision,
                    "rs": RULESET_VERSION,
                },
            )
        ).scalar_one()

    return await in_savepoint(session, _run)


async def in_savepoint(session: AsyncSession, factory):
    """Commit ``factory`` on a SAVEPOINT, or roll it back on error."""
    nested = await session.begin_nested()
    try:
        result = await factory()
        await nested.commit()
        return result
    except Exception:
        await nested.rollback()
        raise


async def prove_commits(session: AsyncSession, factory):
    """Run ``factory`` so a commit is proven, then undo it before restore."""
    nested = await session.begin_nested()
    try:
        result = await factory()
    except Exception:
        if nested.is_active:
            await nested.rollback()
        raise
    else:
        await nested.rollback()
        return result


async def as_uaid_app(session: AsyncSession, factory):
    """Execute ``factory`` after ``SET ROLE uaid_app`` on this connection.

    The factory runs inside a SAVEPOINT so a refused statement does not abort
    the outer test transaction before ``RESET ROLE``.
    """
    await session.execute(text("SET ROLE uaid_app"))
    nested = await session.begin_nested()
    try:
        result = await factory()
        await nested.commit()
        return result
    except Exception:
        await nested.rollback()
        raise
    finally:
        await session.execute(text("RESET ROLE"))


def _unwrap_db_errors(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        nxt = getattr(current, "orig", None)
        if isinstance(nxt, BaseException):
            current = nxt
            continue
        current = current.__cause__ or current.__context__


def pg_state(exc: Exception) -> str | None:
    """Return the SQLSTATE of a SQLAlchemy ``DBAPIError``."""
    for obj in _unwrap_db_errors(exc):
        state = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if state:
            return state
    return None


def pg_constraint(exc: Exception) -> str | None:
    """Return the named constraint of a SQLAlchemy ``DBAPIError``."""
    for obj in _unwrap_db_errors(exc):
        name = getattr(obj, "constraint_name", None)
        if name:
            return name
        diag = getattr(obj, "diag", None)
        name = getattr(diag, "constraint_name", None)
        if name:
            return name
    return None


async def seed_admin_world(session: AsyncSession) -> dict[str, Any]:
    """Create one org, two tenants, and one project each. Admin session."""
    sfx = uuid.uuid4().hex[:8]
    org = (
        await session.execute(
            text("INSERT INTO organizations (name, slug) VALUES ('AdmOrg', :s) RETURNING id"),
            {"s": f"adm-org-{sfx}"},
        )
    ).scalar_one()
    t1 = (
        await session.execute(
            text(
                "INSERT INTO tenants (organization_id, name, slug) "
                "VALUES (:o, 't1', :s) RETURNING id"
            ),
            {"o": org, "s": f"adm-t1-{sfx}"},
        )
    ).scalar_one()
    t2 = (
        await session.execute(
            text(
                "INSERT INTO tenants (organization_id, name, slug) "
                "VALUES (:o, 't2', :s) RETURNING id"
            ),
            {"o": org, "s": f"adm-t2-{sfx}"},
        )
    ).scalar_one()
    p1 = (
        await session.execute(
            text("INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P1', :s) RETURNING id"),
            {"t": t1, "s": f"adm-p1-{sfx}"},
        )
    ).scalar_one()
    p2 = (
        await session.execute(
            text("INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P2', :s) RETURNING id"),
            {"t": t2, "s": f"adm-p2-{sfx}"},
        )
    ).scalar_one()
    return {"org": org, "t1": t1, "t2": t2, "p1": p1, "p2": p2, "sfx": sfx}


async def trigger_state(session: AsyncSession, trigger: str) -> str:
    """Return ``tgenabled`` for ``trigger``."""
    value = (
        await session.execute(
            text("SELECT tgenabled FROM pg_trigger WHERE tgname = :n"),
            {"n": trigger},
        )
    ).scalar_one()
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode("ascii")
    return value


async def function_body(session: AsyncSession, name: str) -> str:
    """Return ``pg_proc.prosrc`` for ``name``."""
    return (
        await session.execute(
            text("SELECT prosrc FROM pg_proc WHERE proname = :n"),
            {"n": name},
        )
    ).scalar_one()


async def set_trigger(session: AsyncSession, table: str, trigger: str, *, enabled: bool) -> None:
    """Enable or disable one named trigger."""
    verb = "ENABLE" if enabled else "DISABLE"
    await session.execute(text(f"ALTER TABLE public.{table} {verb} TRIGGER {trigger}"))


async def add_check(session: AsyncSession, table: str, name: str) -> None:
    """Re-add a named CHECK from ``db_checks.CHECK_SQL_BY_NAME``."""
    from app.admin.db_checks import CHECK_SQL_BY_NAME

    await session.execute(
        text(f"ALTER TABLE public.{table} ADD CONSTRAINT {name} CHECK ({CHECK_SQL_BY_NAME[name]})")
    )


async def drop_check(session: AsyncSession, table: str, name: str) -> None:
    """Drop one named CHECK."""
    await session.execute(text(f"ALTER TABLE public.{table} DROP CONSTRAINT {name}"))


async def call_writer(
    session: AsyncSession,
    *,
    action_id: uuid.UUID,
    project_id: uuid.UUID,
    level: int,
    overrides: str,
) -> Any:
    """Call the gated writer on the current connection."""
    return await session.execute(
        text("SELECT * FROM public.admin_write_autonomy_policy(:a, :p, :l, CAST(:o AS jsonb))"),
        {"a": action_id, "p": project_id, "l": level, "o": overrides},
    )
