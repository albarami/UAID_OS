"""DDL helpers for Slice-63 migration ``0062`` only.

Not imported by the runtime repository path.
"""

from __future__ import annotations

from alembic import op

from app.admin.guards_sql import (
    ADMIN_ACTIONS_GUARD_SQL,
    ADMIN_POLICY_CHANGES_GUARD_SQL,
    ADMIN_ROLE_GRANTS_GUARD_SQL,
    RESOLVER_0026_SQL,
    RESOLVER_0062_SQL,
    RESOLVER_FN,
    TENANT_ADMIN_EVENTS_GUARD_SQL,
    block_dml_sql,
)
from app.admin.policy_sql import (
    MONOTONIC_CREATE_SQL,
    MONOTONIC_SIG,
    WRITER_CREATE_SQL,
    WRITER_SIG,
)

PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
TENANT_TABLES: tuple[str, ...] = (
    "admin_role_grants",
    "admin_actions",
    "admin_policy_changes",
    "tenant_admin_events",
)
POPULATED_TABLES: tuple[str, ...] = (
    "admin_policy_changes",
    "tenant_admin_events",
    "admin_actions",
    "admin_role_grants",
)


def assert_policy_admin_writer_exists() -> None:
    """Fail closed if the bootstrap role is missing."""
    op.execute(
        """
        DO $fn$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'policy_admin_writer'
            ) THEN
                RAISE EXCEPTION
                    'policy_admin_writer role is missing; run make db-bootstrap-rls-role';
            END IF;
        END
        $fn$
        """
    )


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} "
        f"USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )
    op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")


def _install_block_dml(table: str, *, allow_update: bool) -> None:
    op.execute(block_dml_sql(table))
    if allow_update:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE "
            f"ON public.{table} FOR EACH ROW "
            f"EXECUTE FUNCTION public.{table}_block_dml()"
        )
    else:
        op.execute(
            f"CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE "
            f"ON public.{table} FOR EACH ROW "
            f"EXECUTE FUNCTION public.{table}_block_dml()"
        )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION public.{table}_block_dml()"
    )


def install_resolver_0062() -> None:
    """DROP+recreate the bearer-key resolver with status joins."""
    op.execute(f"DROP FUNCTION {RESOLVER_FN}")
    op.execute(RESOLVER_0062_SQL)
    op.execute(f"ALTER FUNCTION {RESOLVER_FN} OWNER TO api_key_resolver")
    op.execute(f"REVOKE ALL ON FUNCTION {RESOLVER_FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {RESOLVER_FN} TO uaid_app")
    op.execute("GRANT SELECT ON public.tenants, public.organizations TO api_key_resolver")


def restore_resolver_0026() -> None:
    """Restore the 0026 resolver body and revoke the additive SELECTs."""
    op.execute(f"DROP FUNCTION {RESOLVER_FN}")
    op.execute(RESOLVER_0026_SQL)
    op.execute(f"ALTER FUNCTION {RESOLVER_FN} OWNER TO api_key_resolver")
    op.execute(f"REVOKE ALL ON FUNCTION {RESOLVER_FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {RESOLVER_FN} TO uaid_app")
    op.execute(
        "REVOKE SELECT ON public.tenants, public.organizations FROM api_key_resolver"
    )


def install_admin_guards() -> None:
    """Install RLS, grants, guards, append-only triggers, and the policy lock."""
    for table in TENANT_TABLES:
        _rls(table)
    op.execute("GRANT SELECT ON public.admin_role_grants TO uaid_app")
    op.execute("GRANT SELECT, INSERT ON public.admin_actions TO uaid_app")
    op.execute("GRANT SELECT ON public.admin_policy_changes TO uaid_app")
    op.execute("GRANT SELECT ON public.tenant_admin_events TO uaid_app")
    op.execute(ADMIN_ROLE_GRANTS_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER admin_role_grants_guard BEFORE INSERT OR UPDATE "
        "ON public.admin_role_grants FOR EACH ROW "
        "EXECUTE FUNCTION public.admin_role_grants_guard()"
    )
    _install_block_dml("admin_role_grants", allow_update=True)
    op.execute(ADMIN_ACTIONS_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER admin_actions_guard BEFORE INSERT "
        "ON public.admin_actions FOR EACH ROW "
        "EXECUTE FUNCTION public.admin_actions_guard()"
    )
    _install_block_dml("admin_actions", allow_update=False)
    op.execute(ADMIN_POLICY_CHANGES_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER admin_policy_changes_guard BEFORE INSERT "
        "ON public.admin_policy_changes FOR EACH ROW "
        "EXECUTE FUNCTION public.admin_policy_changes_guard()"
    )
    _install_block_dml("admin_policy_changes", allow_update=False)
    op.execute(TENANT_ADMIN_EVENTS_GUARD_SQL)
    op.execute(
        "CREATE TRIGGER tenant_admin_events_guard BEFORE INSERT "
        "ON public.tenant_admin_events FOR EACH ROW "
        "EXECUTE FUNCTION public.tenant_admin_events_guard()"
    )
    _install_block_dml("tenant_admin_events", allow_update=False)
    install_policy_lock()


def install_policy_lock() -> None:
    """Revoke runtime writes and install the definer writer."""
    op.execute("REVOKE INSERT, UPDATE ON public.autonomy_policies FROM uaid_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON public.autonomy_policies TO policy_admin_writer"
    )
    op.execute("GRANT SELECT ON public.admin_actions TO policy_admin_writer")
    op.execute("GRANT SELECT, INSERT ON public.admin_policy_changes TO policy_admin_writer")
    op.execute(MONOTONIC_CREATE_SQL)
    op.execute(f"REVOKE ALL ON FUNCTION {MONOTONIC_SIG} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {MONOTONIC_SIG} TO policy_admin_writer")
    op.execute(WRITER_CREATE_SQL)
    op.execute(f"ALTER FUNCTION {WRITER_SIG} OWNER TO policy_admin_writer")
    op.execute(f"REVOKE ALL ON FUNCTION {WRITER_SIG} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {WRITER_SIG} TO uaid_app")


def drop_admin_guards() -> None:
    """Reverse ``install_admin_guards`` after the populated-downgrade check."""
    op.execute(f"DROP FUNCTION IF EXISTS {WRITER_SIG}")
    op.execute(f"DROP FUNCTION IF EXISTS {MONOTONIC_SIG}")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON public.autonomy_policies FROM policy_admin_writer")
    op.execute("REVOKE SELECT ON public.admin_actions FROM policy_admin_writer")
    op.execute("REVOKE SELECT, INSERT ON public.admin_policy_changes FROM policy_admin_writer")
    op.execute("GRANT SELECT, INSERT, UPDATE ON public.autonomy_policies TO uaid_app")
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT ON public.admin_role_grants FROM uaid_app")
    op.execute("REVOKE SELECT, INSERT ON public.admin_actions FROM uaid_app")
    op.execute("REVOKE SELECT ON public.admin_policy_changes FROM uaid_app")
    op.execute("REVOKE SELECT ON public.tenant_admin_events FROM uaid_app")
    op.execute("DROP TRIGGER IF EXISTS admin_role_grants_guard ON public.admin_role_grants")
    op.execute("DROP TRIGGER IF EXISTS admin_role_grants_no_delete ON public.admin_role_grants")
    op.execute("DROP TRIGGER IF EXISTS admin_role_grants_no_truncate ON public.admin_role_grants")
    op.execute("DROP TRIGGER IF EXISTS admin_actions_guard ON public.admin_actions")
    op.execute("DROP TRIGGER IF EXISTS admin_actions_no_update_delete ON public.admin_actions")
    op.execute("DROP TRIGGER IF EXISTS admin_actions_no_truncate ON public.admin_actions")
    op.execute(
        "DROP TRIGGER IF EXISTS admin_policy_changes_guard ON public.admin_policy_changes"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS admin_policy_changes_no_update_delete "
        "ON public.admin_policy_changes"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS admin_policy_changes_no_truncate ON public.admin_policy_changes"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS tenant_admin_events_guard ON public.tenant_admin_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS tenant_admin_events_no_update_delete "
        "ON public.tenant_admin_events"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS tenant_admin_events_no_truncate ON public.tenant_admin_events"
    )
    op.execute("DROP FUNCTION IF EXISTS public.admin_role_grants_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.admin_actions_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.admin_policy_changes_guard()")
    op.execute("DROP FUNCTION IF EXISTS public.tenant_admin_events_guard()")
    for table in TENANT_TABLES:
        op.execute(f"DROP FUNCTION IF EXISTS public.{table}_block_dml()")


def populated_downgrade_sql() -> str:
    """Refuse a populated 0062→0061 downgrade, naming the occupied table."""
    checks = "\n".join(
        f"            IF EXISTS (SELECT 1 FROM public.{table}) THEN\n"
        f"                RAISE EXCEPTION 'cannot downgrade Slice 63 while "
        f"{table} rows exist';\n"
        f"            END IF;"
        for table in POPULATED_TABLES
    )
    return f"""
        DO $fn$
        BEGIN
{checks}
        END
        $fn$
        """
