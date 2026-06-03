"""Slice 2 — append-only, hash-chained audit log (§16.6) tests.

Docker-free: the runtime service contract (no tenant param; minimal return).
DB-backed (`db`): GUC-derived append, forgery denial, fail-closed, append-only
enforcement, tamper detection, seq-gap tolerance, rollback semantics, minimal
return surface, and catalog/privilege proofs.

Note on isolation: committed audit rows pin their tenant (FK RESTRICT) and cannot
be deleted (append-only). Tests therefore use an idempotent shared audit tenant
and assert on their OWN rows (by id/action), never on global counts. The tamper
test restores the row so the global chain stays valid for other tests.
"""

import inspect
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record, verify_chain
from app.tenancy import TenantContext, tenant_scope

_SET_GUC = text("SELECT set_config('app.current_tenant', :tenant, true)")


# --- Docker-free: service contract -------------------------------------------


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def one(self):
        return self._row


class _RecordingSession:
    def __init__(self):
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))
        return _FakeResult({"id": uuid.uuid4(), "entry_hash": "deadbeef", "created_at": "t"})


def test_record_signature_takes_no_tenant():
    params = set(inspect.signature(record).parameters)
    assert "tenant_id" not in params
    assert "tenant" not in params
    # tenant is implicit via the GUC; only these are accepted:
    assert {"session", "action", "actor", "target", "payload"} == params


async def test_record_builds_guc_derived_minimal_call():
    s = _RecordingSession()
    await record(s, action="created", actor="user:1", target="project:x", payload={"k": 1})
    sql, params = s.calls[0]
    # No tenant passed from the caller (DB derives it from the GUC).
    assert set(params) == {"actor", "action", "target", "payload"}
    # Calls the append function and selects only the minimal surface.
    assert "audit_append(:actor, :action, :target" in sql
    assert "id, entry_hash, created_at" in sql
    assert "seq" not in sql and "prev_hash" not in sql


# --- DB-backed fixtures -------------------------------------------------------


@pytest_asyncio.fixture
async def audit_tenant(admin_engine):
    """Reset the audit chain to empty (admin) and return an idempotent test tenant.

    The reset gives each test a clean global chain — necessary because verification
    is full-chain and audit rows are append-only (can't be cleaned normally). Done
    with admin privileges only (disable guard trigger, delete, restart sequence).
    """
    async with admin_engine.begin() as c:
        await c.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_update_delete"))
        await c.execute(text("DELETE FROM audit_logs"))
        await c.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_no_update_delete"))
        await c.execute(text("ALTER SEQUENCE audit_logs_seq RESTART WITH 1"))
        org_id = (
            await c.execute(
                text(
                    "INSERT INTO organizations (name, slug) VALUES ('AuditOrg','audit-org') "
                    "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id"
                )
            )
        ).scalar_one()
        tenant_id = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o,'AuditT','audit-t') "
                    "ON CONFLICT (organization_id, slug) DO UPDATE SET slug = EXCLUDED.slug "
                    "RETURNING id"
                ),
                {"o": org_id},
            )
        ).scalar_one()
    return tenant_id


# --- DB-backed: behavioral proofs --------------------------------------------


@pytest.mark.db
async def test_append_via_service_and_verify(rls_engine, admin_engine, audit_tenant):
    async with tenant_scope(TenantContext(audit_tenant)) as session:
        r1 = await record(session, action="created", actor="user:1", target="project:1")
        r2 = await record(
            session, action="ran", actor="user:1", target="run:1", payload={"status": "ok"}
        )
    # Minimal return surface (Issue 5).
    assert set(r1.keys()) == {"id", "entry_hash", "created_at"}
    assert "seq" not in r1 and "prev_hash" not in r1

    async with admin_engine.connect() as c:
        # The rows we appended belong to the GUC tenant (no forgery possible).
        rows = (
            await c.execute(
                text(
                    "SELECT tenant_id, prev_hash, entry_hash FROM audit_logs "
                    "WHERE id IN (:a,:b) ORDER BY seq"
                ),
                {"a": r1["id"], "b": r2["id"]},
            )
        ).all()
        assert all(row[0] == audit_tenant for row in rows)
        # Chain linkage: r2.prev_hash == r1.entry_hash.
        assert rows[1][1] == rows[0][2]
        ok = (await c.execute(text("SELECT ok FROM audit_verify()"))).scalar_one()
    assert ok is True


@pytest.mark.db
async def test_fail_closed_without_tenant_context(rls_engine, audit_tenant):
    # No tenant_scope -> no GUC -> audit_append must raise.
    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                session = AsyncSession(bind=conn)
                await record(session, action="x", actor="u")

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "app.current_tenant" in str(ei.value) or "tenant context" in str(ei.value)


@pytest.mark.db
async def test_uaid_app_cannot_create_null_tenant_row(rls_engine, audit_tenant):
    # Direct insert (any tenant_id incl. NULL) is denied: uaid_app has no table grant.
    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text(
                        "INSERT INTO audit_logs (seq, actor, action, entry_hash, created_at) "
                        "VALUES (-1, 'u', 'x', 'h', now())"
                    )
                )

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "permission denied" in str(ei.value).lower()


@pytest.mark.db
async def test_uaid_app_direct_dml_denied(rls_engine, audit_tenant):
    for sql in (
        "SELECT count(*) FROM audit_logs",
        "UPDATE audit_logs SET actor='x'",
        "DELETE FROM audit_logs",
    ):

        async def attempt(s=sql):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(text(s))

        with pytest.raises(Exception) as ei:
            await attempt()
        assert "permission denied" in str(ei.value).lower()


@pytest.mark.db
async def test_uaid_app_cannot_execute_verify(rls_engine, audit_tenant):
    async def attempt():
        async with rls_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SELECT * FROM audit_verify()"))

    with pytest.raises(Exception) as ei:
        await attempt()
    assert "permission denied" in str(ei.value).lower()


@pytest.mark.db
async def test_admin_update_delete_blocked_by_trigger(admin_engine, audit_tenant):
    # Seed one row via the service (uaid_app path) so there is a row to attack.
    async with tenant_scope(TenantContext(audit_tenant)) as session:
        r = await record(session, action="created", actor="user:1")

    for sql in (
        "UPDATE audit_logs SET actor='tampered' WHERE id=:i",
        "DELETE FROM audit_logs WHERE id=:i",
    ):

        async def attempt(s=sql):
            async with admin_engine.begin() as c:
                await c.execute(text(s), {"i": r["id"]})

        with pytest.raises(Exception) as ei:
            await attempt()
        assert "append-only" in str(ei.value).lower()


@pytest.mark.db
async def test_tamper_is_detected(admin_engine, audit_tenant):
    async with tenant_scope(TenantContext(audit_tenant)) as session:
        r = await record(session, action="created", actor="user:1", payload={"v": 1})

    async with admin_engine.begin() as c:
        seq = (
            await c.execute(text("SELECT seq FROM audit_logs WHERE id=:i"), {"i": r["id"]})
        ).scalar_one()
        # Tampering requires deliberately disabling the guard (a log-admin action).
        await c.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_update_delete"))
        await c.execute(
            text("UPDATE audit_logs SET payload='{\"v\": 999}'::jsonb WHERE id=:i"),
            {"i": r["id"]},
        )
        await c.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_no_update_delete"))

    async with admin_engine.connect() as c:
        bad = (await c.execute(text("SELECT ok, first_bad_seq FROM audit_verify()"))).one()
    assert bad[0] is False
    assert bad[1] == seq


@pytest.mark.db
async def test_seq_gap_is_tolerated(rls_engine, admin_engine, audit_tenant):
    tid = str(audit_tenant)
    async with rls_engine.connect() as conn:
        async with conn.begin():  # committed append (seq = N)
            await conn.execute(_SET_GUC, {"tenant": tid})
            await conn.execute(text("SELECT audit_append('u','committed-1',NULL,'{}'::jsonb)"))
        # Consume a seq value then roll back -> gap (seq N+1 discarded).
        trans = await conn.begin()
        await conn.execute(_SET_GUC, {"tenant": tid})
        await conn.execute(text("SELECT audit_append('u','rolled-back',NULL,'{}'::jsonb)"))
        await trans.rollback()
        async with conn.begin():  # committed append (seq = N+2)
            await conn.execute(_SET_GUC, {"tenant": tid})
            await conn.execute(text("SELECT audit_append('u','committed-2',NULL,'{}'::jsonb)"))
    async with admin_engine.connect() as c:
        ok = (await c.execute(text("SELECT ok FROM audit_verify()"))).scalar_one()
        # The rolled-back action never persisted.
        n = (
            await c.execute(text("SELECT count(*) FROM audit_logs WHERE action='rolled-back'"))
        ).scalar_one()
    assert ok is True
    assert n == 0


@pytest.mark.db
async def test_rollback_drops_the_audit_row(rls_engine, admin_engine, audit_tenant):
    marker = f"rollback-{uuid.uuid4()}"
    async with rls_engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(_SET_GUC, {"tenant": str(audit_tenant)})
        await conn.execute(text("SELECT audit_append('u',:m,NULL,'{}'::jsonb)"), {"m": marker})
        await trans.rollback()
    async with admin_engine.connect() as c:
        n = (
            await c.execute(text("SELECT count(*) FROM audit_logs WHERE action=:m"), {"m": marker})
        ).scalar_one()
    assert n == 0


@pytest.mark.db
async def test_verify_chain_service_function(admin_engine, audit_tenant):
    session = AsyncSession(bind=admin_engine)
    try:
        status = await verify_chain(session)
    finally:
        await session.close()
    assert set(status.keys()) == {"ok", "first_bad_seq"}
    assert status["ok"] is True


# --- DB-backed: catalog / privilege proofs (Issue 6) -------------------------


@pytest.mark.db
async def test_audit_writer_role_is_limited(admin_engine):
    async with admin_engine.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                    "FROM pg_roles WHERE rolname='audit_writer'"
                )
            )
        ).one()
    assert row == (False, False, False, False, False)


@pytest.mark.db
async def test_function_ownership_and_security(admin_engine):
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT proname, prosecdef, pg_get_userbyid(proowner) "
                    "FROM pg_proc WHERE proname IN ('audit_append','audit_verify')"
                )
            )
        ).all()
    by = {r[0]: (r[1], r[2]) for r in rows}
    assert by["audit_append"] == (True, "audit_writer")
    assert by["audit_verify"] == (True, "audit_writer")


@pytest.mark.db
async def test_uaid_app_execute_grants_are_minimal(admin_engine):
    async with admin_engine.connect() as c:
        granted = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT routine_name FROM information_schema.routine_privileges "
                        "WHERE grantee='uaid_app' AND routine_name LIKE 'audit\\_%'"
                    )
                )
            ).all()
        }
    assert granted == {"audit_append"}  # NOT audit_verify, NOT audit_entry_hash


@pytest.mark.db
async def test_public_has_no_execute_on_audit_functions(admin_engine):
    async with admin_engine.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT routine_name FROM information_schema.routine_privileges "
                    "WHERE grantee='PUBLIC' AND routine_name IN "
                    "('audit_append','audit_verify','audit_entry_hash')"
                )
            )
        ).all()
    assert rows == []
