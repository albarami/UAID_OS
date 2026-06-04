"""key_resolver

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-04

D4 hardening: replace uaid_app's direct SELECT on tenant_api_keys with a
SECURITY DEFINER resolver. The runtime role gets EXECUTE-only access to a narrow
hash→tenant lookup; the function is owned by the least-privilege NOLOGIN role
``api_key_resolver`` (created in scripts/bootstrap_rls_role.sql), which holds the
only SELECT on tenant_api_keys for the definer. Raw keys never enter SQL — the app
passes the stored hash form. No schema/table change.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FN = "public.resolve_tenant_api_key(text)"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.resolve_tenant_api_key(p_key_hash text) RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $fn$
            SELECT tenant_id FROM public.tenant_api_keys
            WHERE key_hash = p_key_hash AND status = 'active'
            LIMIT 1
        $fn$
        """
    )
    # Least-privilege owner; lock down PUBLIC; runtime gets EXECUTE only.
    op.execute(f"ALTER FUNCTION {_FN} OWNER TO api_key_resolver")
    op.execute(f"REVOKE ALL ON FUNCTION {_FN} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_FN} TO uaid_app")
    # The SECURITY DEFINER owner needs to read the table; uaid_app no longer does.
    op.execute("GRANT SELECT ON tenant_api_keys TO api_key_resolver")
    op.execute("REVOKE SELECT ON tenant_api_keys FROM uaid_app")


def downgrade() -> None:
    # Restore the exact 0012 privilege model: uaid_app reads the table directly.
    op.execute("GRANT SELECT ON tenant_api_keys TO uaid_app")
    op.execute("REVOKE SELECT ON tenant_api_keys FROM api_key_resolver")
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}")
    # The api_key_resolver role is bootstrap-managed (like audit_writer); not dropped here.
