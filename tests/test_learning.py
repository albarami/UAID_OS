"""Slice 62 pure probes: vocabulary, SQL allowlist, frozen hashes, P-21/P-22."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from app.ecosystem import cost_optimizer as cost_optimizer_mod
from app.ecosystem import learning as learning_mod
from app.ecosystem import learning_publish as learning_publish_mod
from app.agents.failure_policy import FAILURE_PATTERNS
from app.agents.registry import ARCHETYPES
from app.cost import COST_COMPONENTS
from app.ecosystem.learning import (
    BUCKET_KEYS_BY_CLASS,
    CHALLENGE_FAMILY_KEYS,
    CONNECTOR_FORBIDDEN_COLUMNS,
    COST_COMPONENT_ORDER,
    EVAL_KEYS,
    EXPECTED_BUCKET_COUNT,
    FAILURE_KEYS,
    FORBIDDEN_SOURCE_COLUMNS,
    MIN_CONTRIBUTING_PROJECTS,
    MIN_CONTRIBUTING_TENANTS,
    SIGNAL_CLASSES,
    TOOL_BUCKET_KEYS,
)
from app.verify.reviewer_qa import CHALLENGE_FAMILIES
from app.ecosystem.learning_sql import SOURCE_QUERIES, expected_counts_function_body
from app.intake.readiness import RULESET_VERSION
from app.release.production_autonomy import A5_RULESET_VERSION, ProductionAutonomyReport
from app.tools.registry import TOOL_REGISTRY
from tests.learning_support import FROZEN_HASHES, file_sha256

_FORBIDDEN_FIGURES = ("25000", "1000", "5000", "10000", "50000", "250000", "1k", "USD")
_PUBLIC_PARAM_BAN = frozenset(
    {"content", "document", "prompt", "body", "evidence_pack", "schema"}
)


def test_p1_signal_classes_and_universe() -> None:
    assert SIGNAL_CLASSES == (
        "aggregate_eval_failure_rates",
        "aggregate_reviewer_miss_patterns",
        "anonymized_cost_and_latency_benchmarks",
        "generic_tool_reliability",
        "generic_connector_failure_categories",
        "failure_mode_frequency_counts",
        "security_safe_statistics",
    )
    assert EXPECTED_BUCKET_COUNT == 62
    assert sum(len(keys) for keys in BUCKET_KEYS_BY_CLASS.values()) == 62
    assert frozenset(TOOL_REGISTRY) == frozenset(TOOL_BUCKET_KEYS)
    assert frozenset(EVAL_KEYS) == ARCHETYPES
    assert EVAL_KEYS == tuple(sorted(ARCHETYPES))
    assert FAILURE_KEYS == FAILURE_PATTERNS
    assert CHALLENGE_FAMILY_KEYS == CHALLENGE_FAMILIES
    assert frozenset(COST_COMPONENT_ORDER) == COST_COMPONENTS
    assert MIN_CONTRIBUTING_PROJECTS == 3
    assert MIN_CONTRIBUTING_TENANTS == 2


def test_p4_sql_allowlist_and_no_budget_figures() -> None:
    sql_text = Path("app/ecosystem/learning_sql.py").read_text()
    body = expected_counts_function_body()
    for query in SOURCE_QUERIES.values():
        assert query in body
    for name in FORBIDDEN_SOURCE_COLUMNS:
        assert re.search(rf"\b{re.escape(name)}\b", sql_text) is None
    for name in CONNECTOR_FORBIDDEN_COLUMNS:
        assert re.search(rf"\b{re.escape(name)}\b", sql_text) is None
    for path in (
        Path("app/ecosystem/cost_optimizer.py"),
        Path("app/ecosystem/learning.py"),
    ):
        text = path.read_text()
        for token in _FORBIDDEN_FIGURES:
            assert token not in text


def test_p5_frozen_hashes() -> None:
    assert len(FROZEN_HASHES) == 10
    for path, expected in FROZEN_HASHES.items():
        assert file_sha256(path) == expected


def test_p6_rulesets_and_go_live_identity() -> None:
    assert A5_RULESET_VERSION == "slice54.v1"
    assert RULESET_VERSION == "slice20.v1"
    assert ProductionAutonomyReport(project_id="x").to_dict()["can_go_live_autonomously"] is False


def test_p21_publisher_does_not_name_frozen_engines() -> None:
    source = Path("app/ecosystem/learning_publish.py").read_text()
    for token in (
        "production_autonomy",
        "readiness",
        "control_loop",
        "broker",
        "matrix",
    ):
        assert token not in source


def test_p22_public_params_are_safe() -> None:
    for module in (learning_publish_mod, learning_mod, cost_optimizer_mod):
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if fn.__module__ != module.__name__:
                continue
            if name.startswith("_"):
                continue
            params = inspect.signature(fn).parameters
            assert _PUBLIC_PARAM_BAN.isdisjoint(params)


def test_p23b_connector_universe_is_twelve() -> None:
    assert len(BUCKET_KEYS_BY_CLASS["generic_connector_failure_categories"]) == 12


def test_p_sql_allowlist_migration_imports() -> None:
    migration = Path("migrations/versions/0061_cost_learning.py").read_text()
    assert "from app.ecosystem.learning_db_checks import" in migration
    assert "from app.ecosystem.learning_ddl import" in migration
    assert "expected_counts_function_body" in Path("app/ecosystem/learning_ddl.py").read_text()


def test_alembic_revision_0061_is_head() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    assert heads == ["0061"]
