"""Slice 84 / F-021 helpers: exact-guard probes and in-place assertion bodies.

No production code. Shared by the five tightened tests and the two probe modules.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.admin_support import pg_state

NO_USABLE_RECORD_FINDING = "release_findings: no usable risk-acceptance record for this finding"
NO_USABLE_RECORD_ISSUE = "release_issues: no usable risk-acceptance record for this issue"
CRITICAL_CANNOT_ACCEPT = "critical findings cannot be accepted"
DB_CRITICAL_CANNOT_ACCEPT = "release_findings: critical findings cannot be accepted"
COST_EVENTS_IMMUTABLE = "cost_events is immutable (no UPDATE/DELETE/TRUNCATE)"
CANNOT_TRUNCATE_FK = "cannot truncate a table referenced in a foreign key constraint"
BINDING_NOT_EXACT = "risk_acceptance_records: release/subject binding is not exact"
PYTHON_CANDIDATE_LOOKUP = "release_id must resolve to one same-project frozen candidate"
RLS_RA_POLICY = 'new row violates row-level security policy for table "risk_acceptance_records"'
PERM_COST = "permission denied for table cost_events"
GLOBAL_TABLES = ("skills", "agent_skill_capabilities", "agent_provided_skills")
FINDING_ACCEPT_SQL = (
    "UPDATE release_findings SET status='accepted', risk_acceptance_record_id=:rid WHERE id=:fid"
)
ISSUE_ACCEPT_SQL = (
    "UPDATE release_issues SET status='accepted', risk_acceptance_record_id=:rid WHERE id=:iid"
)
NEIGHBOR_ABSENT = (
    "release/subject binding is not exact",
    "foreign key",
    "violates check constraint",
)
_FUTURE = date(2099, 1, 1)


def append_only_msg(table: str) -> str:
    """Return the per-table append-only / immutable trigger message."""
    return f"{table} is append-only / immutable (no UPDATE/DELETE/TRUNCATE)"


def perm_msg(table: str) -> str:
    """Return the runtime GRANT refusal for ``table``."""
    return f"permission denied for table {table}"


def err_text(exc: BaseException) -> str:
    """Return the exception text used for substring assertions."""
    return str(exc)


def sqlstate_of(exc: BaseException) -> str | None:
    """Return SQLSTATE from a SQLAlchemy/asyncpg error chain."""
    if isinstance(exc, Exception):
        return pg_state(exc)
    return None


def expect_db_error(
    exc: BaseException,
    message: str,
    sqlstate: str,
    absent: tuple[str, ...] = (),
) -> None:
    """Assert ``exc`` carries ``message`` and ``sqlstate``, and none of ``absent``."""
    text_ = err_text(exc)
    assert message in text_, text_
    assert sqlstate_of(exc) == sqlstate, (sqlstate_of(exc), text_)
    lowered = text_.lower()
    for snippet in absent:
        assert snippet.lower() not in lowered, text_


async def trigger_fire_state(engine: AsyncEngine, name: str) -> str:
    """Return ``pg_trigger.tgenabled`` for ``name`` ('O' = origin/enabled)."""
    async with engine.connect() as conn:
        value = (
            await conn.execute(
                text("SELECT tgenabled FROM pg_trigger WHERE tgname=:n"), {"n": name}
            )
        ).scalar_one()
    return value.decode() if isinstance(value, bytes) else str(value)


@asynccontextmanager
async def disabled_trigger(
    admin_engine: AsyncEngine, table: str, trigger: str
) -> AsyncIterator[None]:
    """DISABLE ``trigger`` in a committed admin txn; ENABLE in ``finally``.

    The toggle is committed so a separate ``rls_engine`` connection can see it.
    Session-scoped ``set_trigger`` is not sufficient here.
    """
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
    try:
        yield
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))
        assert await trigger_fire_state(admin_engine, trigger) == "O"


async def _scalar(conn, sql: str, **params: Any):
    return (await conn.execute(text(sql), params)).scalar_one()


async def seed_s84_ctx(admin_engine: AsyncEngine) -> dict[str, Any]:
    """Seed org, t1/t2, p1/p1b/px, a cost run, a blueprint, and t1's frozen RA graph."""
    sfx = uuid.uuid4().hex[:8]
    async with admin_engine.begin() as conn:
        org = await _scalar(
            conn,
            "INSERT INTO organizations (name, slug) VALUES ('S84Org',:s) RETURNING id",
            s=f"s84-org-{sfx}",
        )
        out: dict[str, Any] = {"sfx": sfx}
        for label in ("t1", "t2"):
            out[label] = await _scalar(
                conn,
                "INSERT INTO tenants (organization_id, name, slug) VALUES (:o,:n,:s) RETURNING id",
                o=org,
                n=label,
                s=f"s84-{label}-{sfx}",
            )
        for proj, tn in (("p1", "t1"), ("p1b", "t1"), ("px", "t2")):
            out[proj] = await _scalar(
                conn,
                "INSERT INTO projects (tenant_id, name, slug) VALUES (:t,'P',:s) RETURNING id",
                t=out[tn],
                s=f"s84-{proj}-{sfx}",
            )
        out["r1"] = await _scalar(
            conn,
            "INSERT INTO project_runs (tenant_id, project_id, status) "
            "VALUES (:t,:p,'running') RETURNING id",
            t=out["t1"],
            p=out["p1"],
        )
        out["bp"] = await _scalar(
            conn,
            "INSERT INTO agent_blueprints (key, role, mission, archetype) "
            "VALUES (:k,'Backend','build',:a) RETURNING id",
            k=f"s84-backend-{sfx}",
            a="builder",
        )
        out["cap"] = await _scalar(
            conn,
            "INSERT INTO agent_skill_capabilities "
            "(blueprint_id, cost_latency_class, provided_tools, domains) "
            "VALUES (:b,'medium','[]'::jsonb,'[]'::jsonb) RETURNING id",
            b=out["bp"],
        )
    from app.repositories.release_candidates import ReleaseCandidateRepository
    from app.repositories.release_issues import ReleaseIssueRepository
    from app.tenancy import TenantContext, tenant_scope

    for project_key, tenant_key in (("p1", "t1"), ("px", "t2")):
        ctx = TenantContext(out[tenant_key])
        async with tenant_scope(ctx) as session:
            issue = await ReleaseIssueRepository(session, ctx).create(
                project_id=out[project_key],
                payload={
                    "issue_category": "cost",
                    "severity": "medium",
                    "blocking": False,
                    "summary": "s84 fixture issue",
                    "detail": "fixture",
                    "source": "test",
                },
                actor="fixture",
            )
            release_ref = f"REL-{project_key.upper()}-{sfx}"
            candidates = ReleaseCandidateRepository(session, ctx)
            candidate = await candidates.create(
                project_id=out[project_key],
                payload={"release_ref": release_ref},
                actor="fixture",
            )
            await candidates.bind_issue(
                candidate_id=candidate.id, release_issue_id=issue.id, actor="fixture"
            )
            await candidates.freeze(candidate_id=candidate.id, actor="fixture")
            out[f"issue_{project_key}"] = issue.id
            out[f"release_{project_key}"] = release_ref
    return out


@dataclass(frozen=True)
class MintedSkillRows:
    """One frozen parameter set shared byte-identically by P-GREEN-2d and 2e."""

    skill_id: uuid.UUID
    skill_key: str
    capability_id: uuid.UUID
    blueprint_id: uuid.UUID


def mint_global_skill_rows(blueprint_id: uuid.UUID) -> MintedSkillRows:
    """Mint a non-colliding skills/capability/provided-skill triple over ``blueprint_id``."""
    return MintedSkillRows(
        skill_id=uuid.uuid4(),
        skill_key="s84_" + uuid.uuid4().hex,
        capability_id=uuid.uuid4(),
        blueprint_id=blueprint_id,
    )


def valid_global_inserts(minted: MintedSkillRows) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return per-table structurally valid INSERT SQL and bound parameters."""
    return {
        "skills": (
            "INSERT INTO skills (id, key, category) VALUES (:id, :key, :category)",
            {
                "id": str(minted.skill_id),
                "key": minted.skill_key,
                "category": "backend_engineering",
            },
        ),
        "agent_skill_capabilities": (
            "INSERT INTO agent_skill_capabilities "
            "(id, blueprint_id, cost_latency_class, provided_tools, domains) "
            "VALUES (:id, :bp, 'medium', '[]'::jsonb, '[]'::jsonb)",
            {"id": str(minted.capability_id), "bp": str(minted.blueprint_id)},
        ),
        "agent_provided_skills": (
            "INSERT INTO agent_provided_skills (capability_id, skill_id, can_review) "
            "VALUES (:c, :s, false)",
            {"c": str(minted.capability_id), "s": str(minted.skill_id)},
        ),
    }


def raw_risk_acceptance_insert_sql() -> str:
    """Return the structurally complete cross-tenant RA INSERT (plan §3.5)."""
    return (
        "INSERT INTO risk_acceptance_records "
        "(tenant_id, project_id, release_id, issue_id, subject_type, severity, "
        " reason_for_acceptance, business_impact, rollback_or_mitigation_plan, "
        " required_follow_up_ticket, expiry_date, owner, approver, accepted_by, "
        " approval_authority_source, status, approver_provenance) "
        "VALUES (:t, :p, :rel, :iid, 'release_issue', 'low', 'r', 'b', 'rb', 'T-1', :exp, "
        " 'o', 'a', '[\"o\"]'::jsonb, 'approval_matrix', 'active', "
        " 'caller_supplied_unverified')"
    )


def ra_insert_params(ctx: dict[str, Any], *, tenant_id, project_id) -> dict[str, Any]:
    """Bind t1's frozen candidate and issue into the raw INSERT."""
    return {
        "t": str(tenant_id),
        "p": str(project_id),
        "rel": ctx["release_p1"],
        "iid": str(ctx["issue_p1"]),
        "exp": _FUTURE,
    }


async def runtime_sql(rls_engine: AsyncEngine, tenant_id, sql: str, **params: Any) -> None:
    """Execute ``sql`` as ``uaid_app`` with transaction-local ``app.current_tenant``."""
    async with rls_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            await conn.execute(text(sql), params)


async def build_valid_finding_graph(
    session: AsyncSession, ctx, project_id, *, severity: str = "high"
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a trusted non-critical finding and a usable RA record. Raises on setup failure."""
    from tests.test_release_findings import _make_ra_record, _trusted_security_finding

    finding = await _trusted_security_finding(session, ctx, project_id, severity=severity)
    record = await _make_ra_record(session, ctx, project_id, finding.id)
    if record is None:
        raise AssertionError("usable risk-acceptance record was not created")
    return finding.id, record.id


async def build_valid_issue_graph(
    session: AsyncSession, ctx, project_id
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a non-hard-blocker issue and a usable RA record. Raises on setup failure."""
    from app.repositories.release_issues import ReleaseIssueRepository
    from tests.test_release_issues import _make_ra_record, _valid

    issue = await ReleaseIssueRepository(session, ctx).create(
        project_id=project_id, payload=_valid(blocking=False, severity="high"), actor="a"
    )
    record = await _make_ra_record(session, ctx, project_id, issue.id)
    if record is None:
        raise AssertionError("usable risk-acceptance record was not created")
    return issue.id, record.id


async def assert_cost_events_immutable(cost_ctx, rls_engine, admin_engine) -> None:
    """Pin runtime 42501 and split admin UPDATE/DELETE vs plain TRUNCATE (OD-2)."""
    from app.repositories.cost import CostEventRepository
    from app.tenancy import TenantContext, tenant_scope

    t1, p1 = cost_ctx["t1"], cost_ctx["p1"]
    ctx = TenantContext(t1)
    async with tenant_scope(ctx) as session:
        event = await CostEventRepository(session, ctx).record(
            project_id=p1, component="ci_cd", amount_usd="1", actor="a"
        )
        eid = event.id
    for stmt in (
        "UPDATE cost_events SET amount_usd=999 WHERE id=:i",
        "DELETE FROM cost_events WHERE id=:i",
    ):
        with pytest.raises(Exception) as ei:
            await runtime_sql(rls_engine, t1, stmt, i=str(eid))
        expect_db_error(ei.value, PERM_COST, "42501")
    for stmt in (
        "UPDATE cost_events SET amount_usd=999 WHERE id=:i",
        "DELETE FROM cost_events WHERE id=:i",
    ):
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as conn:
                await conn.execute(text(stmt), {"i": str(eid)})
        expect_db_error(ei.value, COST_EVENTS_IMMUTABLE, "P0001")
    with pytest.raises(Exception) as ei:
        async with admin_engine.begin() as conn:
            await conn.execute(text("TRUNCATE cost_events"))
    expect_db_error(ei.value, CANNOT_TRUNCATE_FK, "0A000", absent=(COST_EVENTS_IMMUTABLE,))


async def assert_runtime_cannot_write_global_tables(rls_engine, sk_ctx) -> None:
    """Pin SELECT-ok plus structurally valid INSERT/UPDATE/DELETE/TRUNCATE 42501."""
    minted = mint_global_skill_rows(sk_ctx["bp"])
    inserts = valid_global_inserts(minted)
    async with rls_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM skills"))).scalar_one() >= 1
    for table in GLOBAL_TABLES:
        sql, params = inserts[table]
        with pytest.raises(Exception) as ei:
            async with rls_engine.connect() as conn:
                await conn.execute(text(sql), params)
                await conn.commit()
        expect_db_error(
            ei.value,
            perm_msg(table),
            "42501",
            absent=(
                "null value in column",
                "violates not-null constraint",
                "violates foreign key constraint",
                "violates check constraint",
                "duplicate key value violates unique constraint",
            ),
        )
        for sql in (
            f"UPDATE {table} SET id = id WHERE false",
            f"DELETE FROM {table} WHERE false",
            f"TRUNCATE {table}",
        ):
            with pytest.raises(Exception) as ei:
                async with rls_engine.connect() as conn:
                    await conn.execute(text(sql))
                    await conn.commit()
            expect_db_error(ei.value, perm_msg(table), "42501")


async def assert_global_tables_dml_immutable(admin_engine, sk_ctx) -> None:
    """Pin UPDATE/DELETE to each table's exact append-only message (truncates live elsewhere)."""
    cap = str(sk_ctx["cap"])
    cases = (
        ("skills", "UPDATE skills SET description='z' WHERE key='security'"),
        (
            "agent_skill_capabilities",
            "UPDATE agent_skill_capabilities SET cost_latency_class='low' WHERE id=:cap",
        ),
        (
            "agent_provided_skills",
            "DELETE FROM agent_provided_skills WHERE capability_id=:cap",
        ),
        (
            "agent_skill_capabilities",
            "DELETE FROM agent_skill_capabilities WHERE id=:cap",
        ),
    )
    for table, sql in cases:
        with pytest.raises(Exception) as ei:
            async with admin_engine.begin() as conn:
                await conn.execute(text(sql), {"cap": cap})
        expect_db_error(ei.value, append_only_msg(table), "P0001")


def assert_acceptance_guard(exc: BaseException, message: str) -> None:
    """Pin one acceptance-guard message and SQLSTATE P0001 with no neighbour text."""
    expect_db_error(exc, message, "P0001", absent=NEIGHBOR_ABSENT)
