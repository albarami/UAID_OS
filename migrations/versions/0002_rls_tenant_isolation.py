"""rls tenant isolation

Enables row-level security on the tenant-owned tables (projects, project_runs)
and grants DML to the non-superuser runtime role `uaid_app`.

Deny-by-default: the policy compares `tenant_id` to the per-transaction GUC
`app.current_tenant`. When the GUC is unset, `NULLIF(current_setting(...), '')`
is NULL, so no row matches (read) and no write passes WITH CHECK.

RLS is ENABLEd and FORCEd (FORCE so even a table owner is subject to it).
Run as an ADMIN role only (never `uaid_app`). The `uaid_app` role itself is
created out-of-band by `make db-bootstrap-rls-role`, not here (roles are
cluster objects; the password is a secret).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-03

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = ("projects", "project_runs")
_RUNTIME_ROLE = "uaid_app"
_GUC = "app.current_tenant"
# Unset GUC -> NULL -> no row matches -> deny by default.
_PREDICATE = f"tenant_id = NULLIF(current_setting('{_GUC}', true), '')::uuid"


def upgrade() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_RUNTIME_ROLE}")
    # The runtime role needs to read the (non-tenant-owned) hierarchy tables.
    op.execute(f"GRANT SELECT ON organizations, tenants TO {_RUNTIME_ROLE}")
    for table in _TENANT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {_RUNTIME_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM {_RUNTIME_ROLE}")
    op.execute(f"REVOKE SELECT ON organizations, tenants FROM {_RUNTIME_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {_RUNTIME_ROLE}")
