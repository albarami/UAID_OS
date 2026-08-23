"""Slice 61a two-session freeze races (D-21h) and lock-before-load (D-21i)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.catalog import CHECK_NAMES, CONNECTOR_CHILDREN_FROZEN
from app.ecosystem.contract_test import run_connector_contract_test as real_checker
from app.repositories import catalog_admin as admin_mod
from app.repositories.catalog_admin import record_contract_test
from app.repositories.catalog_reads import scope_names
from tests.ecosystem_catalog_support import register_probe_connector


async def _insert_passing_vetting(conn, asset_id: uuid.UUID) -> None:
    record_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO catalog_vetting_records "
            "(id,asset_id,vetting_kind,provenance,outcome,reviewer) VALUES "
            "(:id,:a,'connector_contract_test','checker_output_admin_recorded','passed','r')"
        ),
        {"id": record_id, "a": asset_id},
    )
    for name in CHECK_NAMES:
        await conn.execute(
            text(
                "INSERT INTO catalog_vetting_check_results "
                "(vetting_record_id,check_name,passed) VALUES (:id,:n,true)"
            ),
            {"id": record_id, "n": name},
        )


async def _race_vetting_first(engine, asset_id: uuid.UUID) -> None:
    async with engine.connect() as vetting_conn, engine.connect() as scope_conn:
        await vetting_conn.begin()
        await vetting_conn.execute(
            text("SELECT id FROM catalog_assets WHERE id=:i FOR UPDATE"), {"i": asset_id}
        )
        await _insert_passing_vetting(vetting_conn, asset_id)

        async def late_scope() -> None:
            await scope_conn.begin()
            await scope_conn.execute(
                text(
                    "INSERT INTO connector_catalog_tool_scope "
                    "(asset_id,asset_kind,tool_name) VALUES "
                    "(:a,'connector','secrets.verify_reference')"
                ),
                {"a": asset_id},
            )
            await scope_conn.commit()

        task = asyncio.create_task(late_scope())
        await asyncio.sleep(0.15)
        await vetting_conn.commit()
        with pytest.raises((IntegrityError, DBAPIError, Exception)) as caught:
            await task
        assert CONNECTOR_CHILDREN_FROZEN in str(caught.value)
    async with engine.connect() as conn:
        scopes = (
            await conn.execute(
                text("SELECT count(*) FROM connector_catalog_tool_scope WHERE asset_id=:i"),
                {"i": asset_id},
            )
        ).scalar_one()
        vettings = (
            await conn.execute(
                text("SELECT count(*) FROM catalog_vetting_records WHERE asset_id=:i"),
                {"i": asset_id},
            )
        ).scalar_one()
        assert scopes == 1
        assert vettings == 1


async def _race_child_first(engine, asset_id: uuid.UUID) -> None:
    async with engine.connect() as scope_conn, engine.connect() as vetting_conn:
        await scope_conn.begin()
        await scope_conn.execute(
            text("SELECT id FROM catalog_assets WHERE id=:i FOR UPDATE"), {"i": asset_id}
        )
        await scope_conn.execute(
            text(
                "INSERT INTO connector_catalog_tool_scope "
                "(asset_id,asset_kind,tool_name) VALUES "
                "(:a,'connector','secrets.verify_reference')"
            ),
            {"a": asset_id},
        )

        async def late_vetting() -> None:
            await vetting_conn.begin()
            await _insert_passing_vetting(vetting_conn, asset_id)
            await vetting_conn.commit()

        task = asyncio.create_task(late_vetting())
        await asyncio.sleep(0.15)
        await scope_conn.commit()
        await task
    async with engine.connect() as conn:
        scopes = (
            await conn.execute(
                text("SELECT count(*) FROM connector_catalog_tool_scope WHERE asset_id=:i"),
                {"i": asset_id},
            )
        ).scalar_one()
        vettings = (
            await conn.execute(
                text("SELECT count(*) FROM catalog_vetting_records WHERE asset_id=:i"),
                {"i": asset_id},
            )
        ).scalar_one()
        assert scopes == 2
        assert vettings == 1
        await conn.commit()
        with pytest.raises((IntegrityError, DBAPIError, Exception)) as caught:
            await conn.execute(
                text(
                    "INSERT INTO connector_catalog_tool_scope "
                    "(asset_id,asset_kind,tool_name) VALUES "
                    "(:a,'connector','monitoring.read_status')"
                ),
                {"a": asset_id},
            )
            await conn.commit()
        assert CONNECTOR_CHILDREN_FROZEN in str(caught.value)


@pytest.mark.db
async def test_d21h_vetting_first_and_child_first(admin_engine):
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        asset = await register_probe_connector(session)
        await session.commit()
        asset_id = asset.id
    await asyncio.wait_for(_race_vetting_first(admin_engine, asset_id), timeout=15)
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        asset = await register_probe_connector(session)
        await session.commit()
        await asyncio.wait_for(_race_child_first(admin_engine, asset.id), timeout=15)


@pytest.mark.db
async def test_d21i_record_contract_test_locks_before_load(admin_engine, monkeypatch):
    captured: dict[str, tuple[str, ...]] = {}

    def spy(spec):
        captured["names"] = spec.tool_names
        return real_checker(spec)

    monkeypatch.setattr(admin_mod, "run_connector_contract_test", spy)
    async with AsyncSession(admin_engine, expire_on_commit=False) as session:
        asset = await register_probe_connector(session)
        await session.commit()
        asset_id = asset.id

    async def run_checker() -> None:
        async with AsyncSession(admin_engine, expire_on_commit=False) as session:
            await record_contract_test(session, asset_id=asset_id, reviewer="checker")
            await session.commit()

    async def extra_scope() -> str:
        try:
            async with admin_engine.connect() as scope_conn:
                async with scope_conn.begin():
                    await scope_conn.execute(
                        text(
                            "INSERT INTO connector_catalog_tool_scope "
                            "(asset_id,asset_kind,tool_name) VALUES "
                            "(:a,'connector','secrets.verify_reference')"
                        ),
                        {"a": asset_id},
                    )
            return "inserted"
        except Exception as exc:
            if CONNECTOR_CHILDREN_FROZEN in str(exc):
                return "frozen"
            raise

    async with admin_engine.connect() as holder:
        await holder.execute(
            text("SELECT id FROM catalog_assets WHERE id=:i FOR UPDATE"), {"i": asset_id}
        )
        checker_task = asyncio.create_task(run_checker())
        scope_task = asyncio.create_task(extra_scope())
        await asyncio.sleep(0.15)
        await holder.commit()
        await asyncio.wait_for(checker_task, timeout=15)
        scope_result = await asyncio.wait_for(scope_task, timeout=15)
    async with AsyncSession(admin_engine) as session:
        frozen = tuple(await scope_names(session, asset_id))
    assert "names" in captured
    assert set(captured["names"]) == set(frozen)
    assert scope_result in {"inserted", "frozen"}
    if scope_result == "inserted":
        assert "secrets.verify_reference" in frozen
    else:
        assert "secrets.verify_reference" not in frozen
