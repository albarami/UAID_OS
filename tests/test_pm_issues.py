"""PM / issue-tracker connector tests (Slice 34, §12.3 / §26.3).

A broker-gated **Jira** connector reflects external PM issues into an immutable, append-only
``pm_issue_mappings`` store — **mapping-only** (creates no ``release_issues``). Records observed facts only
``(external_ref, external_status, §12.3 board_column, title_present)`` — **no title/description/credential**;
``connector_verified`` = OBSERVATION-verified (not issue-provenance-complete). Jira-status → §12.3 column via
``map_board_column`` with an **``unmapped``** fail-closed sentinel for unknown statuses. Idempotent
latest-wins keyed by ``(tenant, project, external_system, instance_key, external_ref)``. **Store/infra-only —
no release_issues/production_autonomy/readiness change; ruleset stays slice31.v1.**

Docker-free for the pure validators / board-column map; ``db`` for the store, DB guard, resolver, broker-
gated service, idempotent sync, and the ``before==after`` no-A5-impact guard.
"""

import pytest

from app.release.pm_issues import (
    BOARD_COLUMNS,
    EXTERNAL_SYSTEMS,
    PROVENANCES,
    WRITABLE_PROVENANCES,
    InvalidPMMapping,
    is_valid_external_ref,
    is_valid_instance_key,
    map_board_column,
    validate_connector_mapping,
    validate_new_mapping,
)

_NOW = "2026-06-25T12:00:00+00:00"  # opaque marker; the model uses a real datetime

# The 16 §12.3 board columns (snake_case) + the unmapped fail-closed sentinel.
_SPEC_COLUMNS = (
    "backlog",
    "analysis",
    "requirements_review",
    "ready_for_development",
    "in_progress",
    "developer_self_check",
    "specialist_review",
    "changes_requested",
    "qa_testing",
    "security_review",
    "shortcut_detection",
    "acceptance_verification",
    "evidence_audit",
    "ready_for_release",
    "released",
    "done",
)


def _rec(**over) -> dict:
    rec = {
        "external_system": "jira",
        "instance_key": "acme-jira",
        "external_ref": "PROJ-123",
        "external_status": "In Progress",
        "board_column": "in_progress",
        "title_present": True,
    }
    rec.update(over)
    return rec


# --- pure: constants + board-column mapping (B2) ------------------------------


def test_constants():
    assert EXTERNAL_SYSTEMS == ("jira",)
    assert PROVENANCES == ("caller_supplied_unverified", "connector_verified")
    assert WRITABLE_PROVENANCES == ("caller_supplied_unverified",)
    # the §12.3 columns are all present, plus the unmapped sentinel
    for col in _SPEC_COLUMNS:
        assert col in BOARD_COLUMNS
    assert "unmapped" in BOARD_COLUMNS


@pytest.mark.parametrize(
    "status,column",
    [
        ("Backlog", "backlog"),
        ("In Progress", "in_progress"),
        ("in progress", "in_progress"),  # case-insensitive
        ("Done", "done"),
        ("Released", "released"),
    ],
)
def test_map_board_column_known(status, column):
    assert map_board_column(status) == column


@pytest.mark.parametrize("status", ["Frobnicating", "", None, "   ", 123])
def test_map_board_column_unknown_is_unmapped(status):
    # B2: any unknown/unmapped/blank Jira status maps to 'unmapped' (honest fail-closed, never guessed).
    assert map_board_column(status) == "unmapped"


# --- pure: shapes -------------------------------------------------------------


@pytest.mark.parametrize("ref", ["PROJ-123", "ABC-1", "x", "a.b_c-1"])
def test_valid_external_refs(ref):
    assert is_valid_external_ref(ref)


@pytest.mark.parametrize("ref", ["", "has space", "ghp_secrettoken", "x" * 129, "bad/ref"])
def test_invalid_external_refs(ref):
    assert not is_valid_external_ref(ref)


@pytest.mark.parametrize("key", ["acme-jira", "jira_1", "a"])
def test_valid_instance_keys(key):
    assert is_valid_instance_key(key)


@pytest.mark.parametrize("key", ["", "ACME", "has space", "x" * 65])
def test_invalid_instance_keys(key):
    assert not is_valid_instance_key(key)


# --- pure: validators ---------------------------------------------------------


def test_valid_records_pass():
    validate_new_mapping(_rec())
    validate_new_mapping(_rec(external_status="Frobnicating", board_column="unmapped"))
    validate_connector_mapping(_rec(provenance="connector_verified", observed_at=_NOW))


@pytest.mark.parametrize(
    "over",
    [
        {"external_system": "trello"},  # not jira
        {"instance_key": "BAD KEY"},  # bad shape
        {"external_ref": "has space"},  # bad shape
        {"external_ref": "ghp_token"},  # token denylist
        {"board_column": "in_review"},  # not a §12.3 column
        {"title_present": "yes"},  # not a bool
        {"external_status": ""},  # blank status
    ],
)
def test_invalid_records_rejected(over):
    with pytest.raises(InvalidPMMapping):
        validate_new_mapping(_rec(**over))


def test_caller_path_rejects_connector_verified():
    with pytest.raises(InvalidPMMapping):
        validate_new_mapping(_rec(provenance="connector_verified"))


def test_connector_path_requires_verified_and_observed_at():
    with pytest.raises(InvalidPMMapping):
        validate_connector_mapping(_rec(provenance="caller_supplied_unverified"))
    with pytest.raises(InvalidPMMapping):
        validate_connector_mapping(_rec(provenance="connector_verified"))  # no observed_at


# --- DB-backed fixtures + guard -----------------------------------------------

import uuid  # noqa: E402

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def pm_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c, "INSERT INTO organizations (name, slug) VALUES ('PmOrg',:s) RETURNING id", s=f"pm-org-{sfx}"
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org, n=label, s=f"pm-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn], s=f"pm-{proj}-{sfx}",
            )
    return out


_RAW = (
    "INSERT INTO pm_issue_mappings "
    "(tenant_id, project_id, external_system, instance_key, external_ref, external_status, "
    " board_column, title_present, provenance) "
    "VALUES (:t,:p,:sys,:inst,:ref,:status,:col,:tp,:prov)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    params = {
        "t": str(t1), "p": str(p1), "sys": "jira", "inst": "acme-jira", "ref": "PROJ-1",
        "status": "In Progress", "col": "in_progress", "tp": True,
        "prov": "caller_supplied_unverified",
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)})
            await conn.execute(text(_RAW), params)


@pytest.mark.db
async def test_guard_accepts_valid(pm_ctx, rls_engine):
    await _raw_insert(rls_engine, pm_ctx["t1"], pm_ctx["p1"])
    await _raw_insert(rls_engine, pm_ctx["t1"], pm_ctx["p1"], status="Frobnicating", col="unmapped")
    await _raw_insert(rls_engine, pm_ctx["t1"], pm_ctx["p1"], prov="connector_verified")


@pytest.mark.db
@pytest.mark.parametrize(
    "over",
    [
        {"sys": "trello"},  # not jira
        {"inst": "ACME"},  # bad instance shape
        {"ref": "has space"},  # bad ref shape
        {"ref": "ghp_token"},  # token denylist
        {"col": "in_review"},  # not a §12.3 column
        {"prov": "bogus"},  # provenance enum
    ],
)
async def test_guard_rejects_bad(pm_ctx, rls_engine, over):
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, pm_ctx["t1"], pm_ctx["p1"], **over)


@pytest.mark.db
async def test_no_title_or_credential_or_release_issue_column(admin_engine):
    # B6 + no-secret: structurally there is no title/description/credential/release_issue_id column.
    async with admin_engine.connect() as c:
        cols = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='pm_issue_mappings'"
                    )
                )
            ).all()
        }
    assert cols == {
        "id", "tenant_id", "project_id", "external_system", "instance_key", "external_ref",
        "external_status", "board_column", "title_present", "provenance", "observed_at", "created_at",
    }
    # the forbidden free-text/coupling columns are absent (title_present is a bool presence flag, allowed)
    assert {"title", "description", "credential", "token", "release_issue_id"}.isdisjoint(cols)


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(pm_ctx, rls_engine):
    await _raw_insert(rls_engine, pm_ctx["t1"], pm_ctx["p1"])
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(pm_ctx["t1"])})
            mid = (await conn.execute(text("SELECT id FROM pm_issue_mappings LIMIT 1"))).scalar_one()
    for verb in (
        "UPDATE pm_issue_mappings SET board_column='done' WHERE id=:i",
        "DELETE FROM pm_issue_mappings WHERE id=:i",
        "TRUNCATE pm_issue_mappings",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(pm_ctx["t1"])})
                    await conn.execute(text(verb), {"i": str(mid)})


@pytest.mark.db
async def test_fk_cross_project_tenant_rejected(pm_ctx, rls_engine):
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, pm_ctx["t1"], pm_ctx["px"])  # px is in t2, not t1


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='pm_issue_mappings' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='pm_issue_mappings'"
                )
            )
        ).one()
        assert rls == (True, True)
