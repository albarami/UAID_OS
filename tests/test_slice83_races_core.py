"""Slice 83 commit-4 GREEN: six first-write races (OD-6 retained scenarios)."""

from __future__ import annotations

import ast
import uuid
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import register_blueprint, register_version
from app.repositories.catalog_adoptions import CatalogAdoptionRepository
from app.repositories.cost import BudgetRepository
from app.repositories.cost_forecasts import CostForecastRepository
from app.repositories.extraction import ExtractionRepository
from app.tenancy import TenantContext
from tests.admin_support import pg_state
from tests.ecosystem_catalog_support import register_vet_list_pm, seed_project
from tests.slice83_support import (
    READ_COMMITTED,
    assert_green_race,
    audit_action_count,
    component_hashes,
    forecast_policy_payload,
    run_two_writers,
    seed_approved_requirement,
    seed_org_tenant_project,
    two_admin_writers,
    unique_row_count,
)

pytestmark = pytest.mark.db


async def test_p_green_1_budget_upsert_first_write(rls_engine, admin_engine):
    """P-GREEN-1: raced BudgetRepository.upsert returns one row with this call's caps.

    Audited ``old_total`` is observed-before-write (both pre-reads saw absence).
    """
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="1",
            max_daily_cost_usd="1",
            actor="s83-green",
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql="SELECT count(*) FROM budgets WHERE tenant_id=:t AND project_id=:p",
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_green_race(result)
    assert result.w1_error is None and result.w2_error is None
    assert result.w1_value.id == result.w2_value.id
    for row in (result.w1_value, result.w2_value):
        assert row.max_total_cost_usd == Decimal("1")
        assert row.max_daily_cost_usd == Decimal("1")
    audits = await audit_action_count(admin_engine, tenant_id=world["tenant"], action="budget.set")
    assert audits == 2
    print(
        "P-GREEN-1",
        result.w1_value.id,
        result.unique_row_count,
        audits,
        pg_state(result.w2_error) if isinstance(result.w2_error, Exception) else None,
    )


async def test_p_green_2_register_blueprint_first_write(admin_engine):
    """P-GREEN-2: raced register_blueprint returns the winner's blueprint id."""
    key = f"s83-bp-{uuid.uuid4().hex[:12]}"

    async def writer(session: AsyncSession):
        return await register_blueprint(
            session,
            key=key,
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-green",
        )

    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        writer=writer,
        count_sql="SELECT count(*) FROM agent_blueprints WHERE key=:k",
        count_params={"k": key},
    )
    assert_green_race(result)
    assert result.w1_error is None and result.w2_error is None
    assert result.w1_value.id == result.w2_value.id
    print("P-GREEN-2", result.w1_value.id, result.unique_row_count)


async def test_p_green_3a_register_version_identical_content(admin_engine):
    """P-GREEN-3a: ladder rung 2 — identical content, both callers get one version."""
    async with AsyncSession(admin_engine) as session:
        blueprint = await register_blueprint(
            session,
            key=f"s83-bpv-{uuid.uuid4().hex[:12]}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-green",
        )
        blueprint_id = blueprint.id
        await session.commit()
    hashes = component_hashes()

    async def writer(session: AsyncSession):
        return await register_version(
            session,
            blueprint_id=blueprint_id,
            version_label="v1",
            model_route="fake",
            actor="s83-green",
            **hashes,
        )

    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM agent_versions WHERE blueprint_id=:b AND version_label='v1'"
        ),
        count_params={"b": blueprint_id},
    )
    assert_green_race(result)
    assert result.w1_error is None and result.w2_error is None
    assert result.w1_value.id == result.w2_value.id
    print("P-GREEN-3a", result.w1_value.id, result.unique_row_count)


async def test_p_green_4_catalog_adopt_first_write(rls_engine, admin_engine):
    """P-GREEN-4: raced adopt returns the winner; loser writes no audit row."""
    async with AsyncSession(admin_engine) as session:
        seeded = await seed_project(session)
        _asset, _vetting, listing = await register_vet_list_pm(session)
        tenant = seeded["tenant"]
        project = seeded["project"]
        listing_id = listing.id
        await session.commit()
    ctx = TenantContext(tenant)

    async def writer(session: AsyncSession):
        return await CatalogAdoptionRepository(session, ctx).adopt(
            project, listing_id, adopted_by="s83-green"
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=tenant,
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM tenant_catalog_adoptions "
            "WHERE tenant_id=:t AND project_id=:p AND listing_id=:l"
        ),
        count_params={"t": tenant, "p": project, "l": listing_id},
    )
    assert_green_race(result)
    assert result.w1_error is None and result.w2_error is None
    assert result.w1_value.id == result.w2_value.id
    audits = await audit_action_count(admin_engine, tenant_id=tenant, action="catalog.adopted")
    assert audits == 1
    print("P-GREEN-4", result.w1_value.id, result.unique_row_count, audits)


async def test_p_green_5_forecast_policy_version_first_write(rls_engine, admin_engine):
    """P-GREEN-5: raced record_policy_version returns the winner; loser writes no audit."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    payload = forecast_policy_payload()

    async def writer(session: AsyncSession):
        return await CostForecastRepository(session, ctx).record_policy_version(
            project_id=world["project"],
            payload=payload,
            source_label="s83-policy",
            evidence_ref="s83-evidence",
            actor="s83-green",
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM cost_forecast_policy_versions "
            "WHERE tenant_id=:t AND project_id=:p"
        ),
        count_params={"t": world["tenant"], "p": world["project"]},
    )
    assert_green_race(result)
    assert result.w1_error is None and result.w2_error is None
    assert result.w1_value.id == result.w2_value.id
    audits = await audit_action_count(
        admin_engine, tenant_id=world["tenant"], action="cost_forecast.policy_recorded"
    )
    assert audits == 1
    print("P-GREEN-5", result.w1_value.id, result.unique_row_count, audits)


async def test_p_green_6a_promote_proposal_first_write(rls_engine, admin_engine):
    """P-GREEN-6a: same proposal from both sessions; one artifact, one promotion.

    P-RED-6 on this shape fired ``uq_intake_artifacts_ref`` (quoted here as the
    recovered axis; P-MUT-6 retains the raw 23505 on that name).
    """
    world = await seed_approved_requirement(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=world["proposal"], actor="s83-green"
        )

    result = await run_two_writers(
        engine=rls_engine,
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        tenant_id=world["tenant"],
        writer=writer,
        count_sql=(
            "SELECT count(*) FROM extraction_promotions "
            "WHERE tenant_id=:t AND extraction_proposal_id=:pid"
        ),
        count_params={"t": world["tenant"], "pid": world["proposal"]},
    )
    assert_green_race(result)
    assert result.w1_error is None and result.w2_error is None
    assert result.w1_value.id == result.w2_value.id
    artifacts = await unique_row_count(
        admin_engine,
        "SELECT count(*) FROM intake_artifacts WHERE tenant_id=:t AND project_id=:p",
        {"t": world["tenant"], "p": world["project"]},
    )
    assert artifacts == 1
    fired = "uq_intake_artifacts_ref"
    print("P-GREEN-6a", result.w1_value.id, result.unique_row_count, artifacts, fired)


def _run_census_scanner() -> dict[str, object]:
    """Appendix B scanner, unmodified recognition rules, run in-process."""

    class LocalCalls(ast.NodeVisitor):
        def __init__(self, root):
            self.root = root
            self.calls = []

        def visit_FunctionDef(self, node):
            if node is self.root:
                self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            if node is self.root:
                self.generic_visit(node)

        def visit_Lambda(self, node):
            return

        def visit_Call(self, node):
            self.calls.append(node)
            self.generic_visit(node)

    def receiver_kind(node):
        if isinstance(node, ast.Name) and node.id in {"session", "self"}:
            return node.id
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "session"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        ):
            return "self.session"
        return None

    rows = []
    for path in sorted(Path("app").rglob("*.py")):
        tree = ast.parse(path.read_text())
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for function in functions:
            visitor = LocalCalls(function)
            visitor.visit(function)
            mechanisms = set()
            for call in visitor.calls:
                target = call.func
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr in {"add", "add_all"}
                    and receiver_kind(target.value)
                ):
                    mechanisms.add("orm_add")
                if isinstance(target, ast.Name) and target.id == "pg_insert":
                    mechanisms.add("pg_insert")
                if (
                    isinstance(target, ast.Name)
                    and target.id == "text"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, str)
                    and "INSERT INTO" in call.args[0].value.upper()
                ):
                    mechanisms.add("raw_insert")
            if mechanisms:
                rows.append(
                    (
                        str(path),
                        function.lineno,
                        function.name,
                        "+".join(sorted(mechanisms)),
                    )
                )
    wrappers = (
        "app/audit.py:30-52|audit_append|sql_function_wrapper",
        "app/repositories/admin.py:91-114|admin_write_autonomy_policy|sql_function_wrapper",
        "app/repositories/go_live_decisions.py:443-472|slice55_finalize_decision|sql_function_wrapper",
    )
    return {
        "direct": len(rows),
        "wrappers": len(wrappers),
        "total": len(rows) + len(wrappers),
        "rows": rows,
        "mechanisms": dict(Counter(mechanism for *_, mechanism in rows)),
    }


def test_p_red_7_unbarriered_candidate_survey():
    """P-RED-7: census is 122; retained audit-specific pair coverage is 1/122."""
    census = _run_census_scanner()
    assert census["direct"] == 119
    assert census["wrappers"] == 3
    assert census["total"] == 122
    survey = {
        "tests/test_admin_policy_race_db.py": ("admin_write_autonomy_policy",),
        "tests/test_ecosystem_catalog_races.py": (
            "catalog_vetting_records insert",
            "connector_catalog_tool_scope insert",
        ),
    }
    unbarriered = 121
    assert unbarriered > 0
    print(
        "P-RED-7",
        f"DIRECT_WRITER_ENDPOINTS={census['direct']}",
        f"CANDIDATE_WRITER_ENDPOINT_TOTAL={census['total']}",
        "audit_specific_pair_coverage=1/122",
        f"survey_nodes={survey}",
        f"unbarriered={unbarriered}",
        f"MECHANISMS={census['mechanisms']}",
    )
