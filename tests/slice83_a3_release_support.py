"""Slice 83 commit-13 helpers: remaining A3 writers (release / verify / keys)."""

from __future__ import annotations

import copy
import json
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.llm.client import FakeLLMClient
from app.llm.pricing import ModelPrice
from app.release.scm_connector import FakeSCMConnector
from app.repositories.api_keys import TenantApiKeyRepository
from app.repositories.cost import BudgetRepository
from app.repositories.intake_categories import IntakeCategoryRepository
from app.repositories.reviewer_quality import ReviewerQualityRepository
from app.repositories.security_scans import SecurityScanRepository
from app.repositories.shortcut_detectors import ShortcutDetectorRepository
from app.repositories.test_oracles import TestOracleRepository
from app.tenancy import TenantContext
from app.verify.oracles import definition_hash
from tests.slice83_support import Writer, bind_tenant, seed_org_tenant_project
from tests.test_issue_provenance import _security_payload
from tests.test_reviewer_quality import _passing_suite_responses
from tests.test_shortcut_detector import _corpus_payload, _seed_shortcut_panel
from tests.test_test_oracles import (
    RESULTS_SCHEMA_VERSION,
    _common,
    _judgment_result_artifact,
    _qualify_oracle_judges,
)

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40


def _unwrap(fn: Any) -> Any:
    inner = fn
    while hasattr(inner, "__wrapped__"):
        inner = inner.__wrapped__
    return inner


def key_id(value: Any) -> Any:
    """Parent identifier from ``issue()``'s ``(raw_key, row)`` pair."""
    return None if value is None else value[1].id


def run_id(value: Any) -> Any:
    """Parent identifier from a verdict or oracle/scan run row."""
    if value is None:
        return None
    return getattr(value, "run_id", value.id)


def key_writer(tenant_id: uuid.UUID, label: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await TenantApiKeyRepository(session).issue(
            tenant_id=tenant_id,
            label=label,
            principal_subject=f"s83-a3-{label}",
            actor_type="service",
        )

    return writer


def collapsed_hash_key() -> Any:
    """Force both issuers onto one ``key_hash`` (A3 parent collapse)."""
    frozen = "sha256:" + "e" * 64
    return patch("app.repositories.api_keys.hash_key", return_value=frozen)


async def declare_repo(
    session: AsyncSession, ctx: TenantContext, project_id: uuid.UUID, repo: str
) -> None:
    await IntakeCategoryRepository(session, ctx).declare(
        project_id=project_id,
        category="existing_assets_and_repositories",
        actor="s83-a3",
        origin="s83",
        data={"primary_repository": repo, "protected_branch": "main"},
    )


def _scan_payload(sha: str) -> dict[str, Any]:
    payload = copy.deepcopy(_security_payload())
    payload["commit_sha"] = sha
    return payload


async def seed_scan_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        await declare_repo(session, ctx, world["project"], "owner/s83-scan")
        await session.commit()
    world["ctx"] = ctx
    return world


def scan_writer(world: dict[str, Any], sha: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await SecurityScanRepository(session, world["ctx"]).execute_ci(
            project_id=world["project"],
            commit_sha=sha,
            connector=FakeSCMConnector(security_scan_artifact=_scan_payload(sha)),
            actor="s83-a3",
        )

    return writer


def _shortcut_corpus(sha: str) -> dict[str, Any]:
    payload = _corpus_payload(
        entries=[
            {
                "path": "app/service.py",
                "content": (
                    "SENTINEL_SECRET_VALUE\nVALIDATION_ENABLED = False\ndef run(): return value\n"
                ),
            }
        ]
    )
    payload["commit_sha"] = sha
    return payload


async def seed_shortcut_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    await _seed_shortcut_panel(
        admin_engine,
        {"t1": world["tenant"], "p1": world["project"], "suffix": world["sfx"]},
    )
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        await declare_repo(session, ctx, world["project"], "owner/s83-shortcut")
        await BudgetRepository(session, ctx).upsert(
            project_id=world["project"], max_total_cost_usd="100", actor="s83-a3"
        )
        await session.commit()
    world["ctx"] = ctx
    return world


def shortcut_writer(world: dict[str, Any], sha: str) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        price = ModelPrice(Decimal("0.001"), Decimal("0.002"))
        return await ShortcutDetectorRepository(session, world["ctx"]).execute_hybrid(
            project_id=world["project"],
            commit_sha=sha,
            connector=FakeSCMConnector(shortcut_corpus=_shortcut_corpus(sha)),
            reviewer_refs=("reviewer-a", "reviewer-b"),
            clients={
                "reviewer-a": FakeLLMClient(response_text='{"findings": []}'),
                "reviewer-b": FakeLLMClient(response_text='{"findings": []}'),
            },
            price_card={"model-a": price, "model-b": price},
            actor="s83-a3",
        )

    return writer


async def seed_oracle_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    world = await seed_org_tenant_project(admin_engine)
    ctx = TenantContext(world["tenant"])
    definition = _common(
        "specified",
        target_requirement="REQ-1",
        runner_key="canonical_json_exact",
        expected_behavior="canonical output matches SENTINEL_ORACLE_SECRET",
        tolerance="exact",
        cases=[
            {"case_ref": "CASE-1", "expected": {"ok": True}},
            {"case_ref": "CASE-2", "expected": {"ok": True}},
        ],
    )
    async with admin_engine.begin() as conn:
        req = (
            await conn.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,data) "
                    "VALUES (:t,:p,'requirement','REQ-1','REQ-1','{}'::jsonb) RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"]},
            )
        ).scalar_one()
        ac = (
            await conn.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,parent_id,data) "
                    "VALUES (:t,:p,'acceptance_criterion','AC-1','AC-1',:parent,'{}'::jsonb) "
                    "RETURNING id"
                ),
                {"t": world["tenant"], "p": world["project"], "parent": req},
            )
        ).scalar_one()
        oracle = (
            await conn.execute(
                text(
                    "INSERT INTO intake_artifacts "
                    "(tenant_id,project_id,kind,ref,title,parent_id,data) "
                    "VALUES (:t,:p,'test_oracle','OR-1','OR-1',:parent,CAST(:data AS jsonb)) "
                    "RETURNING id"
                ),
                {
                    "t": world["tenant"],
                    "p": world["project"],
                    "parent": ac,
                    "data": json.dumps(definition),
                },
            )
        ).scalar_one()
        for artifact_id in (req, ac, oracle):
            await conn.execute(
                text(
                    "INSERT INTO intake_provenance "
                    "(tenant_id,project_id,artifact_id,origin) VALUES (:t,:p,:a,'s83')"
                ),
                {"t": world["tenant"], "p": world["project"], "a": artifact_id},
            )
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, world["tenant"])
        await declare_repo(session, ctx, world["project"], "owner/s83-oracle")
        await session.commit()
    world["ctx"] = ctx
    world["oracle"] = oracle
    world["definition"] = definition
    return world


def oracle_writer(world: dict[str, Any], sha: str) -> Writer:
    artifact = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "commit_sha": sha,
        "oracles": [
            {
                "oracle_artifact_id": str(world["oracle"]),
                "definition_hash": definition_hash(world["definition"]),
                "observations": [
                    {"case_ref": "CASE-1", "observed": {"ok": True}},
                    {"case_ref": "CASE-2", "observed": {"ok": True}},
                ],
            }
        ],
    }

    async def writer(session: AsyncSession) -> Any:
        return await TestOracleRepository(session, world["ctx"]).execute_ci(
            project_id=world["project"],
            oracle_artifact_id=world["oracle"],
            commit_sha=sha,
            connector=FakeSCMConnector(test_oracle_artifact=artifact),
            actor="s83-a3",
        )

    return writer


async def seed_judgment_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    from tests.test_test_oracles import judgment_db_ctx, oracle_db_ctx

    oracle_ctx = await _unwrap(oracle_db_ctx)(admin_engine)
    ctx = await _unwrap(judgment_db_ctx)(oracle_ctx, admin_engine)
    tenant = TenantContext(ctx["t1"])
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        await bind_tenant(session, ctx["t1"])
        await _qualify_oracle_judges(session, tenant, ctx)
        await BudgetRepository(session, tenant).upsert(
            project_id=ctx["p1"],
            max_total_cost_usd="100",
            max_daily_cost_usd="100",
            actor="s83-a3",
        )
        await declare_repo(session, tenant, ctx["p1"], "owner/s83-judgment")
        await session.commit()
    return {"tenant": ctx["t1"], "project": ctx["p1"], "ctx": tenant, "raw": ctx}


def judgment_writer(world: dict[str, Any], sha: str) -> Writer:
    response = json.dumps({"criteria": {"factual support": True, "user goal fit": True}})
    prices = {
        "model-a": ModelPrice(Decimal("0.001"), Decimal("0.001")),
        "model-b": ModelPrice(Decimal("0.001"), Decimal("0.001")),
    }

    async def writer(session: AsyncSession) -> Any:
        return await TestOracleRepository(session, world["ctx"]).execute_ci(
            project_id=world["project"],
            oracle_artifact_id=world["raw"]["judgment_oracle"],
            commit_sha=sha,
            connector=FakeSCMConnector(
                test_oracle_artifact=_judgment_result_artifact(world["raw"], sha)
            ),
            actor="s83-a3",
            llm_clients={
                "eval-a": FakeLLMClient(response_text=response),
                "eval-b": FakeLLMClient(response_text=response),
            },
            price_card=prices,
        )

    return writer


async def seed_qa_world(admin_engine: AsyncEngine) -> dict[str, Any]:
    from tests.test_reviewer_quality import reviewer_quality_ctx

    ctx = await _unwrap(reviewer_quality_ctx)(admin_engine)
    tenant = TenantContext(ctx["tenant"])
    return {
        "tenant": ctx["tenant"],
        "project": ctx["project"],
        "instance": ctx["instance"],
        "ctx": tenant,
    }


def qa_writer(world: dict[str, Any]) -> Writer:
    async def writer(session: AsyncSession) -> Any:
        return await ReviewerQualityRepository(session, world["ctx"]).execute_suite(
            project_id=world["project"],
            reviewer_instance_id=world["instance"],
            client=FakeLLMClient(response_texts=_passing_suite_responses()),
            price_card={
                "reviewer-model": ModelPrice(
                    input_usd_per_1k=Decimal("0.001"),
                    output_usd_per_1k=Decimal("0.001"),
                )
            },
            actor="s83-a3",
        )

    return writer
