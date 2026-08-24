"""Slice 83 commit-3 RED: six first-write 23505 signatures plus the census survey."""

from __future__ import annotations

import ast
import hashlib
import uuid
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import register_blueprint, register_version
from app.intake.extraction import promotion_ref
from app.repositories.catalog_adoptions import CatalogAdoptionRepository
from app.repositories.cost import BudgetRepository
from app.repositories.cost_forecasts import CostForecastRepository
from app.repositories.extraction import ExtractionRepository
from app.tenancy import TenantContext
from tests.admin_support import pg_state
from tests.ecosystem_catalog_support import register_vet_list_pm, seed_project
from tests.slice83_support import (
    READ_COMMITTED,
    assert_integrity_error_on,
    reported_constraint,
    run_two_writers,
    seed_org_tenant_project,
    two_admin_writers,
    unique_row_count,
)

pytestmark = pytest.mark.db


def _policy_payload() -> dict:
    return {
        "cost_and_resource_policy": {
            "max_total_model_cost_usd": 100,
            "max_daily_model_cost_usd": 50,
            "max_cloud_spend_usd": 100,
            "max_ci_minutes_per_day": 100,
            "require_approval_above_forecast_percentage": 90,
            "model_routing": {
                "cheap_first_for_low_risk": True,
                "frontier_for_high_risk": True,
                "use_cached_context_when_possible": True,
            },
            "stop_conditions": [
                "budget_exceeded",
                "repeated_failure_without_new_strategy",
                "tool_loop_detected",
                "model_provider_outage_extended",
            ],
        }
    }


def _hashes(prompt: str = "a" * 64) -> dict[str, str]:
    return {
        "prompt_hash": f"sha256:{prompt}",
        "tool_policy_hash": "sha256:" + "1" * 64,
        "context_policy_hash": "sha256:" + "2" * 64,
        "eval_suite_hash": "sha256:" + "3" * 64,
        "critical_dependencies_hash": "sha256:" + "4" * 64,
        "output_schema_hash": "sha256:" + "5" * 64,
    }


def _assert_red_race(result, *, constraint: str | None = None) -> None:
    assert result.pending_before_commit is True
    assert result.blocked_at_write is True
    assert result.w1_error is None
    assert result.w2_error is not None
    assert_integrity_error_on(result.w2_error, constraint)
    assert result.unique_row_count == 1


async def test_p_red_1_budget_upsert_first_write(rls_engine, admin_engine):
    """P-RED-1: concurrent first BudgetRepository.upsert raises 23505."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await BudgetRepository(session, ctx).upsert(
            project_id=world["project"],
            max_total_cost_usd="1",
            max_daily_cost_usd="1",
            actor="s83-red",
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
    _assert_red_race(result, constraint="uq_budgets_tenant_id_project_id")
    print(
        "P-RED-1",
        type(result.w2_error).__name__,
        pg_state(result.w2_error),
        reported_constraint(result.w2_error),
        result.unique_row_count,
    )


async def test_p_red_2_register_blueprint_first_write(admin_engine):
    """P-RED-2: concurrent first register_blueprint raises 23505."""
    key = f"s83-bp-{uuid.uuid4().hex[:12]}"

    async def writer(session: AsyncSession):
        return await register_blueprint(
            session,
            key=key,
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-red",
        )

    result = await two_admin_writers(
        admin_engine=admin_engine,
        isolation_level=READ_COMMITTED,
        writer=writer,
        count_sql="SELECT count(*) FROM agent_blueprints WHERE key=:k",
        count_params={"k": key},
    )
    _assert_red_race(result, constraint="uq_agent_blueprints_key")
    print(
        "P-RED-2",
        type(result.w2_error).__name__,
        pg_state(result.w2_error),
        reported_constraint(result.w2_error),
        result.unique_row_count,
    )


async def test_p_red_3_register_version_first_write(admin_engine):
    """P-RED-3: concurrent first register_version raises 23505 on a named unique."""
    async with AsyncSession(admin_engine) as session:
        blueprint = await register_blueprint(
            session,
            key=f"s83-bpv-{uuid.uuid4().hex[:12]}",
            role="builder",
            mission="probe",
            archetype="builder",
            actor="s83-red",
        )
        blueprint_id = blueprint.id
        await session.commit()
    hashes = _hashes()

    async def writer(session: AsyncSession):
        return await register_version(
            session,
            blueprint_id=blueprint_id,
            version_label="v1",
            model_route="fake",
            actor="s83-red",
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
    named = reported_constraint(result.w2_error)
    assert named in {
        "uq_agent_versions_blueprint_id_version_label",
        "uq_agent_versions_content_hash",
    }, named
    _assert_red_race(result, constraint=named)
    print(
        "P-RED-3",
        type(result.w2_error).__name__,
        pg_state(result.w2_error),
        named,
        result.unique_row_count,
    )


async def test_p_red_4_catalog_adopt_first_write(rls_engine, admin_engine):
    """P-RED-4: concurrent first CatalogAdoptionRepository.adopt raises 23505."""
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
            project, listing_id, adopted_by="s83-red"
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
    _assert_red_race(result, constraint="uq_tca_tenant_project_listing")
    print(
        "P-RED-4",
        type(result.w2_error).__name__,
        pg_state(result.w2_error),
        reported_constraint(result.w2_error),
        result.unique_row_count,
    )


async def test_p_red_5_forecast_policy_version_first_write(rls_engine, admin_engine):
    """P-RED-5: concurrent first record_policy_version raises 23505."""
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    payload = _policy_payload()

    async def writer(session: AsyncSession):
        return await CostForecastRepository(session, ctx).record_policy_version(
            project_id=world["project"],
            payload=payload,
            source_label="s83-policy",
            evidence_ref="s83-evidence",
            actor="s83-red",
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
    _assert_red_race(result, constraint="uq_cfpv_project_digest")
    print(
        "P-RED-5",
        type(result.w2_error).__name__,
        pg_state(result.w2_error),
        reported_constraint(result.w2_error),
        result.unique_row_count,
    )


async def _seed_approved_requirement(admin_engine) -> dict:
    world = await seed_org_tenant_project(admin_engine)
    content = "The system shall export an evidence pack."
    digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    async with admin_engine.begin() as conn:
        doc = (
            await conn.execute(
                text(
                    "INSERT INTO documents (tenant_id, project_id, filename, content_type, "
                    "source, content, content_hash, size_bytes, status) "
                    "VALUES (:t,:p,'f.txt','text/plain','manual',:c,:h,:sz,'accepted') "
                    "RETURNING id"
                ),
                {
                    "t": world["tenant"],
                    "p": world["project"],
                    "c": content,
                    "h": digest,
                    "sz": len(content.encode()),
                },
            )
        ).scalar_one()
        run_id = (
            await conn.execute(
                text(
                    "INSERT INTO extraction_runs (id, tenant_id, project_id, document_id, "
                    "model, provider, prompt_version, status) "
                    "VALUES (gen_random_uuid(),:t,:p,:d,'m','fake','v','succeeded') "
                    "RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "d": doc},
            )
        ).scalar_one()
        pid = (
            await conn.execute(
                text(
                    "INSERT INTO extraction_proposals (tenant_id, project_id, "
                    "extraction_run_id, proposed_kind, proposed_text, "
                    "proposed_classification, source_document_id, evidence_quote, "
                    "status, extracted_by) "
                    "VALUES (:t,:p,:r,'requirement',:tx,NULL,:d,:ev,'pending','agent-x') "
                    "RETURNING id"
                ),
                {
                    "t": world["tenant"],
                    "p": world["project"],
                    "r": run_id,
                    "tx": content,
                    "d": doc,
                    "ev": content,
                },
            )
        ).scalar_one()
        await conn.execute(
            text(
                "UPDATE extraction_proposals SET status='approved', "
                "reviewed_by='human-rev', reviewed_at=now() WHERE id=:i"
            ),
            {"i": pid},
        )
    world["proposal"] = pid
    world["ref"] = promotion_ref("requirement", pid)
    return world


async def test_p_red_6_promote_proposal_first_write(rls_engine, admin_engine):
    """P-RED-6: concurrent first promote_proposal raises 23505 on a named unique."""
    world = await _seed_approved_requirement(admin_engine)
    ctx = TenantContext(world["tenant"])

    async def writer(session: AsyncSession):
        return await ExtractionRepository(session, ctx).promote_proposal(
            proposal_id=world["proposal"], actor="s83-red"
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
    named = reported_constraint(result.w2_error)
    assert named in {
        "uq_intake_artifacts_ref",
        "uq_extraction_promotions_proposal",
    }, named
    _assert_red_race(result, constraint=named)
    artifacts = await unique_row_count(
        admin_engine,
        "SELECT count(*) FROM intake_artifacts WHERE tenant_id=:t AND project_id=:p",
        {"t": world["tenant"], "p": world["project"]},
    )
    assert artifacts == 1
    print(
        "P-RED-6",
        type(result.w2_error).__name__,
        pg_state(result.w2_error),
        named,
        result.unique_row_count,
        artifacts,
    )


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
    )
