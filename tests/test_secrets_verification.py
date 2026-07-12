"""Secrets-reference verifier tests (Slice 32, R5 App. A l.2968 / §26.3 / spec:1094).

Immutable, append-only ``secret_reference_checks`` (RLS, latest-wins, two-tier provenance). A broker-gated,
**env-only** verifier confirms each declared ``secrets_and_credentials_manifest`` reference **resolves in
its approved manager** — recording only ``(manager, reference_name, outcome, resolved)``. **ZERO secret-value
leakage:** no value is stored/logged/audited/persisted/returned/bound; the only value contact is transient
in-process ``env`` non-empty inspection (B4/B6). Honesty (B1/B2): ``manager`` is bounded safe text (a non-
``env`` manager ⇒ ``unsupported_manager`` + not-resolved); ``reference_name`` is a bounded shape that
ACCEPTS legit names like ``prod/db_password`` / ``app/api_key`` (no denylist). **Store-only — no A5/readiness
change; current ruleset is slice43.v1.**

Docker-free for the pure validators / shapes / outcome builders; ``db`` for the store, DB guard, broker-
gated service, zero-leak proof, and the no-A5-impact (``before==after``) regression.
"""

import pytest

from app.release.secrets_verification import (
    OUTCOMES,
    PROVENANCES,
    SUPPORTED_MANAGERS,
    WRITABLE_PROVENANCES,
    InvalidSecretCheck,
    build_env_outcome,
    is_valid_manager,
    is_valid_reference_name,
    observation_probe_error,
    observation_unsupported_manager,
    validate_connector_secret_check,
    validate_new_secret_check,
)

_CHECKED_AT = "2026-06-25T12:00:00+00:00"  # opaque marker; the model uses a real datetime


def _rec(**over) -> dict:
    rec = {
        "manager": "env",
        "reference_name": "GITHUB_CONNECTOR_TOKEN",
        "outcome": "resolved",
        "resolved": True,
    }
    rec.update(over)
    return rec


def _conn(**over) -> dict:
    rec = _rec(provenance="connector_verified", checked_at=_CHECKED_AT)
    rec.update(over)
    return rec


# --- constants + shapes -------------------------------------------------------


def test_constants():
    assert SUPPORTED_MANAGERS == ("env",)
    assert set(OUTCOMES) == {"resolved", "not_found", "unsupported_manager", "probe_error"}
    assert PROVENANCES == ("caller_supplied_unverified", "connector_verified")
    assert WRITABLE_PROVENANCES == ("caller_supplied_unverified",)


@pytest.mark.parametrize("m", ["env", "vault", "aws_secrets_manager", "gcp.secret-manager"])
def test_valid_manager_shapes(m):
    assert is_valid_manager(m)


@pytest.mark.parametrize("m", ["", "ENV", "has space", "x" * 65, "a\tb"])
def test_invalid_manager_shapes(m):
    assert not is_valid_manager(m)


@pytest.mark.parametrize(
    "name", ["GITHUB_CONNECTOR_TOKEN", "prod/db_password", "app/api_key", "a", "x" * 256]
)
def test_valid_reference_names_accept_legit_names(name):
    # B2: names containing 'password'/'api_key'/'token' are legitimate references, not values.
    assert is_valid_reference_name(name)


@pytest.mark.parametrize("name", ["", "has space", "x" * 257, "bad\nname", "a$b"])
def test_invalid_reference_names(name):
    assert not is_valid_reference_name(name)


# --- outcome builders (honesty; never a value) --------------------------------


def test_build_env_outcome_present_and_absent():
    assert build_env_outcome(present=True) == {"outcome": "resolved", "resolved": True}
    assert build_env_outcome(present=False) == {"outcome": "not_found", "resolved": False}


def test_unsupported_and_probe_error_are_unresolved():
    assert observation_unsupported_manager() == {
        "outcome": "unsupported_manager",
        "resolved": False,
    }
    assert observation_probe_error() == {"outcome": "probe_error", "resolved": False}


# --- validators ---------------------------------------------------------------


def test_valid_records_pass():
    validate_new_secret_check(_rec())  # resolved env
    validate_new_secret_check(_rec(outcome="not_found", resolved=False))
    validate_new_secret_check(_rec(manager="vault", outcome="unsupported_manager", resolved=False))
    validate_connector_secret_check(_conn())
    validate_connector_secret_check(_conn(outcome="not_found", resolved=False))


@pytest.mark.parametrize(
    "over",
    [
        {"manager": "ENV"},  # bad manager shape
        {"reference_name": "bad name"},  # bad reference-name shape
        {"outcome": "boom"},  # bad outcome
        {"outcome": "resolved", "resolved": False},  # resolved != (outcome=='resolved')
        {"outcome": "not_found", "resolved": True},  # resolved != (outcome=='resolved')
        # B1: a non-env manager MUST be unsupported_manager + not resolved
        {"manager": "vault", "outcome": "resolved", "resolved": True},
        {"manager": "vault", "outcome": "not_found", "resolved": False},
    ],
)
def test_invalid_records_rejected(over):
    with pytest.raises(InvalidSecretCheck):
        validate_new_secret_check(_rec(**over))


def test_caller_path_rejects_connector_verified():
    with pytest.raises(InvalidSecretCheck):
        validate_new_secret_check(_rec(provenance="connector_verified"))


def test_connector_path_requires_verified_and_checked_at():
    with pytest.raises(InvalidSecretCheck):
        validate_connector_secret_check(_rec(provenance="caller_supplied_unverified"))
    with pytest.raises(InvalidSecretCheck):
        validate_connector_secret_check(_rec(provenance="connector_verified"))  # no checked_at


# --- DB-backed fixtures + guard -----------------------------------------------

import uuid  # noqa: E402

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def _scalar(conn, sql, **p):
    return (await conn.execute(text(sql), p)).scalar_one()


@pytest_asyncio.fixture
async def src_ctx(admin_engine):
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as c:
        org = await _scalar(
            c,
            "INSERT INTO organizations (name, slug) VALUES ('SrcOrg',:s) RETURNING id",
            s=f"src-org-{sfx}",
        )
        out = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                c,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"src-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                c,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"src-{proj}-{sfx}",
            )
    return out


_RAW = (
    "INSERT INTO secret_reference_checks "
    "(tenant_id, project_id, manager, reference_name, outcome, resolved, provenance) "
    "VALUES (:t,:p,:manager,:ref,:outcome,:resolved,:prov)"
)


async def _raw_insert(rls_engine, t1, p1, **over):
    params = {
        "t": str(t1),
        "p": str(p1),
        "manager": "env",
        "ref": "GITHUB_CONNECTOR_TOKEN",
        "outcome": "resolved",
        "resolved": True,
        "prov": "caller_supplied_unverified",
    }
    params.update(over)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            await conn.execute(text(_RAW), params)


@pytest.mark.db
async def test_guard_accepts_valid_rows(src_ctx, rls_engine):
    t1, p1 = src_ctx["t1"], src_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1)  # env resolved
    await _raw_insert(rls_engine, t1, p1, outcome="not_found", resolved=False)
    await _raw_insert(
        rls_engine, t1, p1, ref="prod/db_password", outcome="not_found", resolved=False
    )  # B2
    await _raw_insert(
        rls_engine, t1, p1, manager="vault", outcome="unsupported_manager", resolved=False
    )  # B1
    await _raw_insert(rls_engine, t1, p1, prov="connector_verified")


@pytest.mark.db
@pytest.mark.parametrize(
    "over",
    [
        {"manager": "ENV"},  # bad manager shape
        {"ref": "bad name"},  # bad reference-name shape
        {"outcome": "boom"},  # bad outcome
        {"outcome": "resolved", "resolved": False},  # honesty invariant
        {"outcome": "not_found", "resolved": True},  # honesty invariant
        {
            "manager": "vault",
            "outcome": "resolved",
            "resolved": True,
        },  # B1: non-env must be unsupported
        {
            "manager": "vault",
            "outcome": "not_found",
            "resolved": False,
        },  # B1: non-env must be unsupported
        {"prov": "bogus"},  # provenance enum
    ],
)
async def test_guard_rejects_bad_rows(src_ctx, rls_engine, over):
    t1, p1 = src_ctx["t1"], src_ctx["p1"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, p1, **over)


@pytest.mark.db
async def test_append_only_no_update_delete_truncate(src_ctx, rls_engine):
    t1, p1 = src_ctx["t1"], src_ctx["p1"]
    await _raw_insert(rls_engine, t1, p1)
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
            )
            sid = (
                await conn.execute(text("SELECT id FROM secret_reference_checks LIMIT 1"))
            ).scalar_one()
    for verb in (
        "UPDATE secret_reference_checks SET resolved=false WHERE id=:i",
        "DELETE FROM secret_reference_checks WHERE id=:i",
        "TRUNCATE secret_reference_checks",
    ):
        with pytest.raises(Exception):
            async with rls_engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(
                        text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(t1)}
                    )
                    await conn.execute(text(verb), {"i": str(sid)})


@pytest.mark.db
async def test_fk_cross_project_tenant_rejected(src_ctx, rls_engine):
    t1, px = src_ctx["t1"], src_ctx["px"]
    with pytest.raises(Exception):
        await _raw_insert(rls_engine, t1, px)


@pytest.mark.db
async def test_no_value_column_exists(admin_engine):
    # structural zero-secret-value guarantee: there is NO column that could hold a value.
    async with admin_engine.connect() as c:
        cols = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='secret_reference_checks'"
                    )
                )
            ).all()
        }
    assert cols == {
        "id",
        "tenant_id",
        "project_id",
        "manager",
        "reference_name",
        "outcome",
        "resolved",
        "checked_at",
        "provenance",
        "created_at",
    }
    assert not any("value" in c or "secret" in c for c in cols)


@pytest.mark.db
async def test_catalog_grants_and_rls(admin_engine):
    async with admin_engine.connect() as c:
        grants = {
            r[0]
            for r in (
                await c.execute(
                    text(
                        "SELECT privilege_type FROM information_schema.role_table_grants "
                        "WHERE table_name='secret_reference_checks' AND grantee='uaid_app'"
                    )
                )
            ).all()
        }
        assert grants == {"SELECT", "INSERT"}
        rls = (
            await c.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='secret_reference_checks'"
                )
            )
        ).one()
        assert rls == (True, True)


# --- DB-backed: repository + resolver -----------------------------------------


def _src_repo(session, ctx):
    from app.repositories.secrets_verification import SecretReferenceCheckRepository

    return SecretReferenceCheckRepository(session, ctx)


def _conn_payload(**over):
    from datetime import datetime, timezone

    payload = {
        "manager": "env",
        "reference_name": "GITHUB_CONNECTOR_TOKEN",
        "outcome": "resolved",
        "resolved": True,
        "checked_at": datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc),
    }
    payload.update(over)
    return payload


async def _declare_secrets(session, ctx, project_id, references):
    from app.repositories.intake_categories import IntakeCategoryRepository

    await IntakeCategoryRepository(session, ctx).declare(
        project_id=project_id,
        category="secrets_and_credentials_manifest",
        actor="a",
        data={"references": references},
        origin="test",
    )


@pytest.mark.db
async def test_record_latest_and_count(src_ctx):
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    async with tenant_scope(ctx) as session:
        repo = _src_repo(session, ctx)
        await repo.record_connector_verified_check(
            project_id=p1, payload=_conn_payload(reference_name="A"), actor="conn"
        )
        # a later check for the same reference supersedes (latest-wins)
        await repo.record_connector_verified_check(
            project_id=p1,
            payload=_conn_payload(reference_name="A", outcome="not_found", resolved=False),
            actor="conn",
        )
        await repo.record_connector_verified_check(
            project_id=p1, payload=_conn_payload(reference_name="B"), actor="conn"
        )
        latest_a = await repo.latest_for_reference(p1, "env", "A")
        assert latest_a.outcome == "not_found" and latest_a.resolved is False  # latest, not first
        assert len(await repo.list_latest_for_project(p1)) == 2  # A + B, deduped
        assert await repo.count_resolved(p1) == 1  # only B's latest resolved


@pytest.mark.db
async def test_resolver_extracts_all_references(src_ctx):
    from app.release.project_repo import resolve_declared_secret_references
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    async with tenant_scope(ctx) as session:
        await _declare_secrets(
            session,
            ctx,
            p1,
            [
                {"manager": "env", "reference_name": "TOK_A"},
                {"manager": "vault", "reference_name": "db/pw"},
            ],
        )
        refs = await resolve_declared_secret_references(session, ctx, p1)
        assert ("env", "TOK_A") in refs and ("vault", "db/pw") in refs and len(refs) == 2


@pytest.mark.db
async def test_resolver_fail_closed_undeclared(src_ctx):
    from app.release.project_repo import resolve_declared_secret_references
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    async with tenant_scope(ctx) as session:
        assert await resolve_declared_secret_references(session, ctx, src_ctx["p1"]) == []


@pytest.mark.db
async def test_audit_safe_metadata_no_reference_name(src_ctx, admin_engine):
    # the audit payload must NEVER carry reference_name (defense-in-depth) or any value.
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    async with tenant_scope(ctx) as session:
        await _src_repo(session, ctx).record_connector_verified_check(
            project_id=p1,
            payload=_conn_payload(reference_name="VERY_DISTINCTIVE_REF_NAME"),
            actor="conn",
        )
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT payload::text FROM audit_logs WHERE action='secrets.reference_verified'"
                )
            )
        ).all()
    assert rows and all("VERY_DISTINCTIVE_REF_NAME" not in r[0] for r in rows)


@pytest.mark.db
async def test_rls_cross_tenant(src_ctx):
    from app.tenancy import TenantContext, tenant_scope

    t1, t2, p1 = src_ctx["t1"], src_ctx["t2"], src_ctx["p1"]
    async with tenant_scope(TenantContext(t1)) as session:
        await _src_repo(session, TenantContext(t1)).record_connector_verified_check(
            project_id=p1, payload=_conn_payload(), actor="conn"
        )
    async with tenant_scope(TenantContext(t2)) as session:
        assert (
            await _src_repo(session, TenantContext(t2)).latest_for_reference(
                p1, "env", "GITHUB_CONNECTOR_TOKEN"
            )
            is None
        )


# --- Docker-free: connector ---------------------------------------------------


async def test_env_connector_resolved_absent_and_value_never_returned(monkeypatch):
    from app.release.secrets_connector import EnvSecretsManagerConnector

    conn = EnvSecretsManagerConnector()
    monkeypatch.setenv("UAID_TEST_SECRET_REF", "super-secret-value-12345")
    obs = await conn.verify_reference(manager="env", reference_name="UAID_TEST_SECRET_REF")
    assert obs == {"outcome": "resolved", "resolved": True}  # exactly — no value key
    assert "super-secret" not in str(obs)  # the value never appears in the return
    monkeypatch.delenv("UAID_TEST_SECRET_REF", raising=False)
    assert await conn.verify_reference(manager="env", reference_name="UAID_TEST_SECRET_REF") == {
        "outcome": "not_found",
        "resolved": False,
    }


async def test_env_connector_empty_is_not_found(monkeypatch):
    from app.release.secrets_connector import EnvSecretsManagerConnector

    monkeypatch.setenv("UAID_TEST_EMPTY_REF", "   ")  # whitespace-only ⇒ not resolved
    obs = await EnvSecretsManagerConnector().verify_reference(
        manager="env", reference_name="UAID_TEST_EMPTY_REF"
    )
    assert obs == {"outcome": "not_found", "resolved": False}


async def test_env_connector_unsupported_manager_no_lookup():
    from app.release.secrets_connector import EnvSecretsManagerConnector

    obs = await EnvSecretsManagerConnector().verify_reference(manager="vault", reference_name="x")
    assert obs == {"outcome": "unsupported_manager", "resolved": False}


# --- DB-backed: broker-gated service ------------------------------------------


async def _src_allow_setup(session, ctx, project_id, references, agent_id="conn"):
    from app.policy.levels import AutonomyLevel
    from app.repositories.autonomy_policies import AutonomyPolicyRepository
    from app.repositories.tools import ToolAllowlistRepository

    await _declare_secrets(session, ctx, project_id, references)
    await AutonomyPolicyRepository(session, ctx).upsert(
        project_id=project_id, autonomy_level=int(AutonomyLevel.A5), actor="a"
    )
    await ToolAllowlistRepository(session, ctx).grant(
        agent_id=agent_id, tool_name="secrets.verify_reference", actor="admin"
    )


@pytest.mark.db
async def test_service_broker_allow_writes_per_reference(src_ctx, monkeypatch, admin_engine):
    from app.release.secrets_connector import EnvSecretsManagerConnector
    from app.release.secrets_verification_service import refresh_secret_reference_evidence
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = src_ctx["t1"], src_ctx["p1"]
    ctx = TenantContext(t1)
    monkeypatch.setenv("UAID_SVC_TOK", "the-real-secret-value")
    async with tenant_scope(ctx) as session:
        await _src_allow_setup(
            session,
            ctx,
            p1,
            [
                {"manager": "env", "reference_name": "UAID_SVC_TOK"},  # resolved
                {"manager": "env", "reference_name": "UAID_SVC_MISSING"},  # not_found
                {"manager": "vault", "reference_name": "db/pw"},
            ],  # unsupported_manager
        )
        result = await refresh_secret_reference_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=EnvSecretsManagerConnector(),
        )
        assert result.wrote == 3 and result.references == 3
        repo = _src_repo(session, ctx)
        assert (await repo.latest_for_reference(p1, "env", "UAID_SVC_TOK")).resolved is True
        assert (
            await repo.latest_for_reference(p1, "env", "UAID_SVC_MISSING")
        ).outcome == "not_found"
        assert (
            await repo.latest_for_reference(p1, "vault", "db/pw")
        ).outcome == "unsupported_manager"
    # B3 + zero-leak: broker params carry reference_present (un-redacted) and no value/reference_name.
    async with admin_engine.connect() as c:
        params = (
            await c.execute(
                text(
                    "SELECT params::text FROM tool_calls WHERE tenant_id=:t "
                    "AND tool_name='secrets.verify_reference'"
                ),
                {"t": str(t1)},
            )
        ).all()
    assert params
    for (p,) in params:
        assert (
            "reference_present" in p
            and "the-real-secret-value" not in p
            and "UAID_SVC_TOK" not in p
        )


@pytest.mark.db
async def test_service_secrets_unbound_no_write(src_ctx):
    from app.release.secrets_connector import FakeSecretsManagerConnector
    from app.release.secrets_verification_service import refresh_secret_reference_evidence
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    async with tenant_scope(ctx) as session:
        result = await refresh_secret_reference_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeSecretsManagerConnector(),
        )
        assert result.wrote == 0 and result.reason == "secrets_unbound"
        assert await _src_repo(session, ctx).count_resolved(p1) == 0


@pytest.mark.db
async def test_service_broker_denied_no_write(src_ctx):
    from app.release.secrets_connector import FakeSecretsManagerConnector
    from app.release.secrets_verification_service import refresh_secret_reference_evidence
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    async with tenant_scope(ctx) as session:
        # declared, but the agent is NOT allowlisted for secrets.verify_reference ⇒ broker denies.
        await _declare_secrets(session, ctx, p1, [{"manager": "env", "reference_name": "X"}])
        result = await refresh_secret_reference_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=FakeSecretsManagerConnector(result={"outcome": "resolved", "resolved": True}),
        )
        assert result.wrote == 0
        assert await _src_repo(session, ctx).latest_for_reference(p1, "env", "X") is None


# --- DB-backed: store-only — no A5 / readiness impact (the scope guard) --------


@pytest.mark.db
async def test_no_a5_impact_before_equals_after(src_ctx, monkeypatch):
    # Store-only: recording secret-reference evidence feeds NO gate and does not change the A5 report
    # or the readiness level; current ruleset is slice43.v1.
    from app.release.secrets_connector import EnvSecretsManagerConnector
    from app.release.secrets_verification_service import refresh_secret_reference_evidence
    from app.repositories.production_autonomy import ProductionAutonomyRepository
    from app.repositories.readiness import ReadinessRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    monkeypatch.setenv("UAID_REG_TOK", "secret-value")
    async with tenant_scope(ctx) as session:
        await _src_allow_setup(
            session, ctx, p1, [{"manager": "env", "reference_name": "UAID_REG_TOK"}]
        )
        before = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
        readiness_before = (await ReadinessRepository(session, ctx).evaluate(p1)).readiness_level
        result = await refresh_secret_reference_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=EnvSecretsManagerConnector(),
        )
        assert result.wrote == 1  # evidence WAS written...
        after = (await ProductionAutonomyRepository(session, ctx).evaluate(p1)).to_dict()
        readiness_after = (await ReadinessRepository(session, ctx).evaluate(p1)).readiness_level
    assert before == after  # ...yet the A5 report is byte-identical (store-only)
    assert readiness_before == readiness_after  # and readiness is unchanged
    assert after["ruleset_version"] == "slice44.v1"  # current A5 ruleset


# --- DB-backed: malformed-reference skipping (D-32-10 fail-closed) -------------


@pytest.mark.db
async def test_resolver_skips_malformed_keeps_valid_and_unsupported(src_ctx):
    # D-32-10: malformed shapes (uppercase manager, spaced name, missing field) are SKIPPED, but a
    # valid-shape-yet-unsupported manager ('vault') is KEPT (recorded unsupported downstream, B1).
    from app.release.project_repo import resolve_declared_secret_references
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    async with tenant_scope(ctx) as session:
        await _declare_secrets(
            session,
            ctx,
            p1,
            [
                {"manager": "env", "reference_name": "VALID_TOK"},  # valid → kept
                {"manager": "vault", "reference_name": "db/pw"},  # valid shape, unsupported → kept
                {"manager": "ENV", "reference_name": "x"},  # invalid manager shape → skipped
                {"manager": "env", "reference_name": "bad name"},  # invalid name shape → skipped
                {"manager": "env"},  # missing reference_name → skipped
            ],
        )
        refs = await resolve_declared_secret_references(session, ctx, p1)
        assert set(refs) == {
            ("env", "VALID_TOK"),
            ("vault", "db/pw"),
        }  # only the two valid-shape refs


@pytest.mark.db
async def test_resolver_skips_malformed_top_level(src_ctx):
    from app.release.project_repo import resolve_declared_secret_references
    from app.repositories.intake_categories import IntakeCategoryRepository
    from app.tenancy import TenantContext, tenant_scope

    ctx = TenantContext(src_ctx["t1"])
    p1 = src_ctx["p1"]
    async with tenant_scope(ctx) as session:
        # top-level (no references[]) malformed manager — categories accepts the short string, the
        # resolver must skip it (no row, no broker).
        await IntakeCategoryRepository(session, ctx).declare(
            project_id=p1,
            category="secrets_and_credentials_manifest",
            actor="a",
            data={"manager": "ENV", "reference_name": "x"},
            origin="test",
        )
        assert await resolve_declared_secret_references(session, ctx, p1) == []


@pytest.mark.db
async def test_service_skips_malformed_no_broker_no_abort(src_ctx, monkeypatch, admin_engine):
    # Mixed valid + malformed: the service processes ONLY the valid ref, never brokers a malformed one,
    # and does not abort.
    from app.release.secrets_connector import EnvSecretsManagerConnector
    from app.release.secrets_verification_service import refresh_secret_reference_evidence
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = src_ctx["t1"], src_ctx["p1"]
    ctx = TenantContext(t1)
    monkeypatch.setenv("UAID_OK_TOK", "v")
    async with tenant_scope(ctx) as session:
        await _src_allow_setup(
            session,
            ctx,
            p1,
            [
                {"manager": "env", "reference_name": "UAID_OK_TOK"},  # valid
                {"manager": "ENV", "reference_name": "x"},  # malformed → skipped
                {"manager": "env", "reference_name": "bad name"},  # malformed → skipped
            ],
        )
        result = await refresh_secret_reference_evidence(
            session,
            ctx,
            project_id=p1,
            agent_id="conn",
            actor="conn",
            connector=EnvSecretsManagerConnector(),
        )
        assert result.references == 1 and result.wrote == 1  # only the valid ref; no abort
        rows = await _src_repo(session, ctx).list_latest_for_project(p1)
        assert {(r.manager, r.reference_name) for r in rows} == {("env", "UAID_OK_TOK")}
    # exactly ONE broker tool_call — the malformed refs never reached the broker.
    async with admin_engine.connect() as c:
        n = (
            await c.execute(
                text(
                    "SELECT count(*) FROM tool_calls WHERE tenant_id=:t "
                    "AND tool_name='secrets.verify_reference'"
                ),
                {"t": str(t1)},
            )
        ).scalar_one()
    assert n == 1
