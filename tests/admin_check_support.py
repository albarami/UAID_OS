"""Helpers for Slice 63 privilege/catalog probes. Not a production path."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import text

from app.admin.db_checks import CHECK_SQL_BY_NAME
from app.admin.ddl import PREDICATE
from app.admin.rbac import OPERATOR_PROVENANCE
from app.admin.policy_sql import MONOTONIC_BODY, WRITER_BODY
from tests.admin_support import trigger_state

SLICE63_TRIGGERS = (
    "admin_role_grants_guard",
    "admin_role_grants_no_delete",
    "admin_role_grants_no_truncate",
    "admin_actions_guard",
    "admin_actions_no_update_delete",
    "admin_actions_no_truncate",
    "admin_policy_changes_guard",
    "admin_policy_changes_no_update_delete",
    "admin_policy_changes_no_truncate",
    "tenant_admin_events_guard",
    "tenant_admin_events_no_update_delete",
    "tenant_admin_events_no_truncate",
)
TABLES = (
    "admin_role_grants",
    "admin_actions",
    "admin_policy_changes",
    "tenant_admin_events",
)


def _assert_check_drift(sql: str, defn: str) -> None:
    """Postgres pretty-prints CHECKs; vocabulary and ranks must still appear."""
    compact = re.sub(r"\s+", " ", defn)
    stripped = re.sub(r"E'[^']*'", "", sql)
    for literal in re.findall(r"'((?:''|[^'])*)'", stripped):
        assert literal.replace("''", "'") in defn
    for match in re.finditer(r"THEN (\d+)", sql):
        assert f"THEN {match.group(1)}" in compact
    for match in re.finditer(r"BETWEEN (\d+) AND (\d+)", sql):
        assert match.group(1) in defn
        assert match.group(2) in defn
    if "char_length" in sql:
        assert "char_length" in defn
    if "btrim" in sql:
        assert "btrim" in defn


async def committed_world(admin_engine) -> dict:
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = (
            await c.execute(
                text("INSERT INTO organizations (name, slug) VALUES ('Chk', :s) RETURNING id"),
                {"s": f"chk-{sfx}"},
            )
        ).scalar_one()
        tenant = (
            await c.execute(
                text(
                    "INSERT INTO tenants (organization_id, name, slug) "
                    "VALUES (:o, 't', :s) RETURNING id"
                ),
                {"o": org, "s": f"chk-t-{sfx}"},
            )
        ).scalar_one()
        project = (
            await c.execute(
                text(
                    "INSERT INTO projects (tenant_id, name, slug) VALUES (:t, 'P', :s) RETURNING id"
                ),
                {"t": tenant, "s": f"chk-p-{sfx}"},
            )
        ).scalar_one()
    return {"org": org, "t": tenant, "p": project, "sfx": sfx}


def priv_statement(table: str, priv: str, world: dict, ids: dict):
    if table == "admin_role_grants" and priv == "INSERT":
        return text(
            "INSERT INTO admin_role_grants ("
            "tenant_id, principal_subject, admin_role, status, "
            "granted_by, granted_by_provenance) "
            f"VALUES ('{world['t']}', 'throw-{world['sfx']}', 'tenant_viewer', "
            f"'active', 'op', '{OPERATOR_PROVENANCE}')"
        )
    if table == "admin_role_grants" and priv == "UPDATE":
        return text(f"UPDATE admin_role_grants SET status='revoked' WHERE id='{ids['grant']}'")
    if table == "admin_role_grants" and priv == "DELETE":
        return text(f"DELETE FROM admin_role_grants WHERE id='{ids['grant']}'")
    if table == "admin_actions" and priv == "UPDATE":
        return text(f"UPDATE admin_actions SET decision='allowed' WHERE id='{ids['action']}'")
    if table == "admin_actions" and priv == "DELETE":
        return text(f"DELETE FROM admin_actions WHERE id='{ids['action']}'")
    if table == "admin_policy_changes" and priv == "INSERT":
        return text(
            "INSERT INTO admin_policy_changes ("
            "tenant_id, project_id, admin_action_id, autonomy_policy_id, "
            "previous_autonomy_level, new_autonomy_level, override_key_count) "
            f"VALUES ('{world['t']}', '{world['p']}', '{ids['action']}', "
            f"'{ids['policy']}', 2, 2, 0)"
        )
    if table == "admin_policy_changes" and priv == "UPDATE":
        return text(
            f"UPDATE admin_policy_changes SET new_autonomy_level=2 WHERE id='{ids['change']}'"
        )
    if table == "admin_policy_changes" and priv == "DELETE":
        return text(f"DELETE FROM admin_policy_changes WHERE id='{ids['change']}'")
    if table == "tenant_admin_events" and priv == "INSERT":
        return text(
            "INSERT INTO tenant_admin_events ("
            "tenant_id, organization_id, event_kind, performed_by, "
            "performed_by_provenance) "
            f"VALUES ('{world['t']}', '{world['org']}', 'tenant_reinstated', "
            f"'op', '{OPERATOR_PROVENANCE}')"
        )
    if table == "tenant_admin_events" and priv == "UPDATE":
        return text(
            f"UPDATE tenant_admin_events SET event_kind='tenant_reinstated' "
            f"WHERE id='{ids['event']}'"
        )
    if table == "tenant_admin_events" and priv == "DELETE":
        return text(f"DELETE FROM tenant_admin_events WHERE id='{ids['event']}'")
    raise AssertionError((table, priv))


async def assert_catalog(admin_engine, session) -> None:
    async with admin_engine.connect() as c:
        for table in TABLES:
            privs = {
                r[0]
                for r in (
                    await c.execute(
                        text(
                            "SELECT privilege_type FROM information_schema.role_table_grants "
                            "WHERE table_name=:t AND grantee='uaid_app'"
                        ),
                        {"t": table},
                    )
                ).all()
            }
            if table == "admin_actions":
                assert privs == {"SELECT", "INSERT"}
            else:
                assert privs == {"SELECT"}
        ap = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='autonomy_policies' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert ap == {"SELECT"}
        owner = (
            await c.execute(
                text(
                    "SELECT r.rolname, p.prosecdef FROM pg_proc p "
                    "JOIN pg_roles r ON r.oid = p.proowner "
                    "WHERE p.proname='admin_write_autonomy_policy'"
                )
            )
        ).one()
        assert owner == ("policy_admin_writer", True)
        flags = (
            await c.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
                    "WHERE rolname='policy_admin_writer'"
                )
            )
        ).one()
        assert flags == (False, False, False)
        empty = "{}"
        allow_false = '{"run_tests":{"allow":false}}'
        min3 = '{"run_tests":{"min_level":3}}'
        min4 = '{"run_tests":{"min_level":4}}'
        req_true = '{"run_tests":{"requires_approval":true}}'
        mono = (
            await c.execute(
                text(
                    "SELECT public.admin_overrides_is_monotonic("
                    "CAST(:empty AS jsonb), CAST(:empty AS jsonb)), "
                    "public.admin_overrides_is_monotonic("
                    "CAST(:empty AS jsonb), CAST(:allow_false AS jsonb)), "
                    "public.admin_overrides_is_monotonic("
                    "CAST(:allow_false AS jsonb), CAST(:empty AS jsonb)), "
                    "public.admin_overrides_is_monotonic("
                    "CAST(:allow_false AS jsonb), CAST(:min3 AS jsonb)), "
                    "public.admin_overrides_is_monotonic("
                    "CAST(:min3 AS jsonb), CAST(:min4 AS jsonb)), "
                    "public.admin_overrides_is_monotonic("
                    "CAST(:min4 AS jsonb), CAST(:min3 AS jsonb)), "
                    "public.admin_overrides_is_monotonic("
                    "CAST(:req_true AS jsonb), CAST(:empty AS jsonb))"
                ),
                {
                    "empty": empty,
                    "allow_false": allow_false,
                    "min3": min3,
                    "min4": min4,
                    "req_true": req_true,
                },
            )
        ).one()
        assert mono == (True, True, False, False, True, False, False)
        for table in TABLES:
            row = (
                await c.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE relname=:t"
                    ),
                    {"t": table},
                )
            ).one()
            assert row == (True, True)
            expr = (
                await c.execute(
                    text(
                        "SELECT pg_get_expr(polqual, polrelid) FROM pg_policy "
                        "WHERE polname='tenant_isolation' AND polrelid = CAST(:t AS regclass)"
                    ),
                    {"t": f"public.{table}"},
                )
            ).scalar_one()
            canonical = (
                await c.execute(
                    text(
                        "SELECT pg_get_expr(polqual, polrelid) FROM pg_policy "
                        "WHERE polname='tenant_isolation' "
                        "AND polrelid = 'public.autonomy_policies'::regclass"
                    )
                )
            ).scalar_one()
            assert expr == canonical
            assert "app.current_tenant" in expr
            assert PREDICATE.split("=", 1)[0].strip() in expr
        body = (
            await c.execute(
                text("SELECT prosrc FROM pg_proc WHERE proname='admin_write_autonomy_policy'")
            )
        ).scalar_one()
        assert body.strip() == WRITER_BODY.strip()
        mono_body = (
            await c.execute(
                text("SELECT prosrc FROM pg_proc WHERE proname='admin_overrides_is_monotonic'")
            )
        ).scalar_one()
        assert MONOTONIC_BODY.strip() in mono_body
        for name, sql in CHECK_SQL_BY_NAME.items():
            if name == "ck_organizations_status_valid":
                continue
            defn = (
                await c.execute(
                    text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname=:n"),
                    {"n": name},
                )
            ).scalar_one()
            _assert_check_drift(sql, defn)
        for trigger in SLICE63_TRIGGERS:
            assert await trigger_state(session, trigger) == "O"
