"""Slice 62 catalog CHECKs, GENERATED published, and the security-barrier view."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ecosystem.learning_db_checks import (
    BUCKET_CHECK_CONSTRAINTS,
    OPT_RUN_CHECK_CONSTRAINTS,
    RUN_CHECK_CONSTRAINTS,
)
from tests.learning_support import learning_world


@pytest.mark.db
async def test_checks_generated_view_and_p11() -> None:
    async with learning_world() as world:
        async with AsyncSession(world["admin"]) as session:
            run_names = {
                row[0]
                for row in (
                    await session.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'cross_project_aggregate_runs'::regclass "
                            "AND contype = 'c'"
                        )
                    )
                ).all()
            }
            bucket_names = {
                row[0]
                for row in (
                    await session.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'cross_project_aggregate_buckets'::regclass "
                            "AND contype = 'c'"
                        )
                    )
                ).all()
            }
            opt_names = {
                row[0]
                for row in (
                    await session.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'cost_optimizer_runs'::regclass "
                            "AND contype = 'c'"
                        )
                    )
                ).all()
            }
            def _present(expected: str, names: set[str]) -> bool:
                return expected in names or any(expected in item for item in names)

            for name, _sql in RUN_CHECK_CONSTRAINTS:
                assert _present(name, run_names)
            for name, _sql in BUCKET_CHECK_CONSTRAINTS:
                assert _present(name, bucket_names)
            for name, _sql in OPT_RUN_CHECK_CONSTRAINTS:
                assert _present(name, opt_names)

            generated = (
                await session.execute(
                    text(
                        "SELECT is_generated FROM information_schema.columns "
                        "WHERE table_name='cross_project_aggregate_buckets' "
                        "AND column_name='published'"
                    )
                )
            ).scalar_one()
            assert generated == "ALWAYS"

            barrier = (
                await session.execute(
                    text(
                        "SELECT relkind FROM pg_class "
                        "WHERE relname='cross_project_published_buckets'"
                    )
                )
            ).scalar_one()
            assert (barrier.decode() if isinstance(barrier, bytes) else str(barrier)) == "v"
            options = (
                await session.execute(
                    text(
                        "SELECT reloptions FROM pg_class "
                        "WHERE relname='cross_project_published_buckets'"
                    )
                )
            ).scalar_one()
            assert options is not None
            assert any("security_barrier=true" in item for item in options)

            forbidden = {
                "tenant_id",
                "project_id",
                "description",
                "params",
                "summary",
                "detail",
                "body",
                "title",
                "content",
                "prompt",
                "target_ref",
                "reference_name",
                "repo_ref",
                "actor",
                "external_ref",
            }
            for table in (
                "cross_project_aggregate_runs",
                "cross_project_aggregate_buckets",
            ):
                cols = {
                    row[0]
                    for row in (
                        await session.execute(
                            text(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_schema='public' AND table_name=:t"
                            ),
                            {"t": table},
                        )
                    ).all()
                }
                assert cols.isdisjoint(forbidden)
