"""Slice 83 commit-5 inventory: seven classification tests (OD-9 batch 2)."""

from __future__ import annotations

import ast
import io
import re
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.writer_inventory import (
    B2_EDGE_EVIDENCE,
    CANDIDATE_ENDPOINTS,
    CENSUS_SCANNER,
    Candidate,
    LEAVES_BY_ID,
    PENDING_TIER_A_BATCHES,
    POST_FIX_MECHANISMS,
    TIER_A_NODES,
    WRITE_LEAVES,
)

pytestmark = pytest.mark.db

OD8_SQL = """
WITH pk AS (
  SELECT i.indrelid AS reloid,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)
           WHERE ord <= i.indnkeyatts) AS cols
    FROM pg_index i
   WHERE i.indisprimary
),
uq AS (
  SELECT i.indrelid AS reloid, ic.relname AS idxname,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)
           WHERE ord <= i.indnkeyatts) AS cols,
         i.indpred IS NOT NULL AS partial
    FROM pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c  ON c.oid  = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND i.indisunique AND NOT i.indisprimary AND c.relkind = 'r'
)
SELECT c.relname, uq.idxname, uq.partial
  FROM uq JOIN pk ON pk.reloid = uq.reloid JOIN pg_class c ON c.oid = uq.reloid
 WHERE NOT (pk.cols <@ uq.cols)
 ORDER BY c.relname, uq.idxname
"""

OD8_WHOLE_INDKEY_SQL = """
WITH pk AS (
  SELECT i.indrelid AS reloid,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)) AS cols
    FROM pg_index i
   WHERE i.indisprimary
),
uq AS (
  SELECT i.indrelid AS reloid, ic.relname AS idxname,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)) AS cols,
         i.indpred IS NOT NULL AS partial
    FROM pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c  ON c.oid  = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND i.indisunique AND NOT i.indisprimary AND c.relkind = 'r'
)
SELECT c.relname, uq.idxname, uq.partial
  FROM uq JOIN pk ON pk.reloid = uq.reloid JOIN pg_class c ON c.oid = uq.reloid
 WHERE NOT (pk.cols <@ uq.cols)
 ORDER BY c.relname, uq.idxname
"""

B2_SQL = """
WITH uq AS (
  SELECT i.indrelid AS reloid, ic.relname AS idxname,
         (SELECT array_agg(k ORDER BY ord)
            FROM unnest(i.indkey::int[]) WITH ORDINALITY AS t(k, ord)
           WHERE ord <= i.indnkeyatts) AS cols
    FROM pg_index i
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_class c  ON c.oid  = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'public' AND i.indisunique AND NOT i.indisprimary AND c.relkind = 'r'
),
strict_fk AS (
  SELECT con.conrelid, con.confrelid, con.conname,
         ca.attname AS child_col, ca.attnum AS child_attnum, pa.attname AS parent_col,
         (pg_get_expr(d.adbin, d.adrelid) ILIKE '%gen_random_uuid%'
            OR pa.attidentity <> '')                                AS parent_server_generated,
         EXISTS (SELECT 1 FROM pg_index pi
                  WHERE pi.indrelid = con.confrelid AND pi.indisprimary
                    AND pa.attnum = ANY(pi.indkey::int2[]))          AS parent_col_is_pk
    FROM pg_constraint con
    JOIN LATERAL generate_subscripts(con.conkey, 1) AS s(i) ON TRUE
    JOIN pg_attribute ca ON ca.attrelid = con.conrelid  AND ca.attnum = con.conkey[s.i]
    JOIN pg_attribute pa ON pa.attrelid = con.confrelid AND pa.attnum = con.confkey[s.i]
    LEFT JOIN pg_attrdef d ON d.adrelid = con.confrelid AND d.adnum = pa.attnum
   WHERE con.contype = 'f'
     AND ca.attname NOT IN ('tenant_id', 'project_id')
)
SELECT child.relname AS child_table, uq.idxname, parent.relname AS parent_table,
       f.child_col, f.parent_col, f.parent_server_generated, f.parent_col_is_pk
  FROM uq
  JOIN pg_class child  ON child.oid  = uq.reloid
  JOIN strict_fk f     ON f.conrelid = uq.reloid AND f.child_attnum = ANY(uq.cols)
  JOIN pg_class parent ON parent.oid = f.confrelid
 WHERE f.parent_server_generated AND f.parent_col_is_pk
 ORDER BY child.relname, uq.idxname, parent.relname
"""

_ROW_RE = re.compile(r"^(app/[^:]+):(\d+)\|([^|]+)\|(.+)$")


@dataclass(frozen=True)
class _Census:
    direct: int
    mechanisms: str
    rows: set[tuple[str, int, str, str]]


def run_census_scanner() -> _Census:
    """Execute the Appendix-B scanner in-process and parse its stdout."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        exec(compile(CENSUS_SCANNER, "<census_scanner>", "exec"), {})
    direct: int | None = None
    mechanisms: str | None = None
    rows: set[tuple[str, int, str, str]] = set()
    for line in buf.getvalue().splitlines():
        if line.startswith("DIRECT_WRITER_ENDPOINTS="):
            direct = int(line.split("=", 1)[1])
        elif line.startswith("MECHANISMS="):
            mechanisms = line.split("=", 1)[1]
        elif "|sql_function_wrapper" in line:
            continue
        else:
            match = _ROW_RE.match(line)
            if match:
                rows.add((match.group(1), int(match.group(2)), match.group(3), match.group(4)))
    assert direct is not None and mechanisms is not None
    return _Census(direct=direct, mechanisms=mechanisms, rows=rows)


def _assert_census_equality(candidates: tuple[Candidate, ...]) -> None:
    census = run_census_scanner()
    scanned = census.rows
    inventory = {
        (c.path, c.lineno, c.name, c.mechanism)
        for c in candidates
        if c.mechanism != "sql_function_wrapper"
    }
    missing = scanned - inventory
    extra = inventory - scanned
    assert not missing and not extra, (
        f"scanner-only={sorted(missing)} inventory-only={sorted(extra)}"
    )
    assert census.direct == 119
    assert len(candidates) == 122
    assert census.mechanisms == POST_FIX_MECHANISMS


def _node_exists(nodeid: str) -> bool:
    path, _, rest = nodeid.partition("::")
    name = rest.split("::")[-1]
    tree = ast.parse(Path(path).read_text())
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in ast.walk(tree)
    )


def _function_span(path: str, lineno: int, name: str) -> tuple[int, int]:
    tree = ast.parse(Path(path).read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
            and node.lineno == lineno
        ):
            return node.lineno, int(node.end_lineno or node.lineno)
    raise AssertionError(f"missing function {path}:{lineno}|{name}")


def _assert_b2_edge_evidence(candidates, leaves, edge_evidence) -> None:
    """B2-5 per-edge checks; shared by inventory test 7 and P-MUT-16."""
    leaves_by = {leaf.leaf_id: leaf for leaf in leaves}
    expected: list[tuple[str, int, str, str, str]] = []
    for candidate in candidates:
        for leaf_id in candidate.leaf_ids:
            leaf = leaves_by[leaf_id]
            if leaf.tier == "B2":
                expected.append(
                    (
                        candidate.path,
                        candidate.lineno,
                        candidate.name,
                        candidate.mechanism,
                        leaf_id,
                    )
                )
    observed = [
        (
            edge.candidate_path,
            edge.candidate_lineno,
            edge.candidate_name,
            edge.candidate_mechanism,
            edge.leaf_id,
        )
        for edge in edge_evidence
    ]
    missing = set(expected) - set(observed)
    extra = set(observed) - set(expected)
    assert not missing, f"missing B2-5 evidence for {sorted(missing)}"
    assert not extra, f"extra B2-5 evidence {sorted(extra)}"
    assert len(observed) == len(set(observed))
    for edge in edge_evidence:
        assert edge.parent_creation_citation.startswith("app/")
        path, _, line_s = edge.parent_creation_citation.rpartition(":")
        line = int(line_s)
        assert path == edge.candidate_path, (path, edge.candidate_path)
        start, end = _function_span(edge.candidate_path, edge.candidate_lineno, edge.candidate_name)
        assert start <= line <= end, (
            f"citation {edge.parent_creation_citation} outside {start}-{end} "
            f"for {edge.candidate_name}"
        )
        parent = leaves_by.get(edge.parent_leaf_id)
        assert parent is not None, edge.parent_leaf_id
        assert parent.tier == "A", f"parent leaf {edge.parent_leaf_id} is {parent.tier} not A"
        child = leaves_by[edge.leaf_id]
        assert parent.table == child.parent_table, (
            f"parent_table mismatch: leaf {parent.table} != declared {child.parent_table}"
        )


async def _od8_maps(admin_engine: AsyncEngine) -> tuple[dict[str, set[str]], set[str], int, int]:
    async with admin_engine.connect() as conn:
        rows = (await conn.execute(text(OD8_SQL))).mappings().all()
        tables = (
            await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        ).all()
    collidable: dict[str, set[str]] = {}
    for row in rows:
        collidable.setdefault(str(row["relname"]), set()).add(str(row["idxname"]))
    public = {str(name) for (name,) in tables}
    return collidable, public, len(rows), len(collidable)


def _assert_mapping_totality(candidates, leaves, public_tables: set[str]) -> None:
    ids = [leaf.leaf_id for leaf in leaves]
    assert len(ids) == len(set(ids))
    referenced: set[str] = set()
    leaves_by = {leaf.leaf_id: leaf for leaf in leaves}
    for candidate in candidates:
        assert candidate.leaf_ids, candidate.name
        for leaf_id in candidate.leaf_ids:
            leaf = leaves_by[leaf_id]
            referenced.add(leaf_id)
            if leaf.tier == "B1":
                assert leaf_id == f"{leaf.table}.-"
                assert leaf.unique_index is None
            else:
                assert leaf_id == f"{leaf.table}.{leaf.unique_index}"
            assert leaf.table in public_tables, leaf.table
    orphans = set(ids) - referenced
    assert not orphans, f"orphan leaves {sorted(orphans)}"


def _assert_tier_derivation(leaves, collidable: dict[str, set[str]]) -> None:
    present = set(collidable)
    for leaf in leaves:
        if leaf.tier in {"A", "B2"}:
            assert leaf.table in present, f"{leaf.leaf_id} table missing from OD-8"
        elif leaf.tier == "B1":
            assert leaf.table not in present, f"B1 {leaf.leaf_id} table is collidable"
        else:
            raise AssertionError(leaf.tier)
        if leaf.isolation_level == "READ COMMITTED":
            assert leaf.retryable_loser_sqlstates == ()
            assert leaf.isolation_citation is None
        elif leaf.isolation_level == "SERIALIZABLE":
            assert leaf.retryable_loser_sqlstates == ("40001", "40P01")
            assert leaf.isolation_citation == "app/repositories/go_live_decisions.py:445"
        else:
            raise AssertionError(leaf.isolation_level)
    s55 = next(c for c in CANDIDATE_ENDPOINTS if c.name == "slice55_finalize_decision")
    for leaf_id in s55.leaf_ids:
        assert LEAVES_BY_ID[leaf_id].isolation_level == "SERIALIZABLE"


def _assert_tier_a_registration(leaves, nodes=TIER_A_NODES, pending=PENDING_TIER_A_BATCHES) -> None:
    tier_a = {leaf.leaf_id for leaf in leaves if leaf.tier == "A"}
    registered = set(nodes)
    pending_ids = set(pending)
    assert registered.isdisjoint(pending_ids), sorted(registered & pending_ids)
    missing = tier_a - (registered | pending_ids)
    extra = (registered | pending_ids) - tier_a
    assert not missing and not extra, f"unregistered={sorted(missing)} extra={sorted(extra)}"
    for leaf_id, node_ids in nodes.items():
        assert node_ids, leaf_id
        for node in node_ids:
            assert _node_exists(node), node
    for leaf_id in pending_ids:
        assert leaf_id not in nodes, leaf_id


def _assert_pending_empty(pending: frozenset[str] = PENDING_TIER_A_BATCHES) -> None:
    """Commit-14 close-out: no Tier-A leaf may remain pending."""
    assert pending == frozenset(), sorted(pending)


def _assert_index_coverage(candidates, leaves, collidable: dict[str, set[str]]) -> None:
    leaves_by = {leaf.leaf_id: leaf for leaf in leaves}
    for candidate in candidates:
        by_table: dict[str, set[str | None]] = {}
        for leaf_id in candidate.leaf_ids:
            leaf = leaves_by[leaf_id]
            by_table.setdefault(leaf.table, set()).add(leaf.unique_index)
        for table, declared_raw in by_table.items():
            live = collidable.get(table, set())
            declared = {idx for idx in declared_raw if idx is not None}
            if declared != live:
                raise AssertionError(
                    f"{candidate.path}:{candidate.lineno}|{candidate.name} table {table} "
                    f"missing={sorted(live - declared)} extra={sorted(declared - live)}"
                )
    union: dict[str, set[str | None]] = {}
    for candidate in candidates:
        for leaf_id in candidate.leaf_ids:
            leaf = leaves_by[leaf_id]
            union.setdefault(leaf.table, set()).add(leaf.unique_index)
    for table, live in collidable.items():
        if table not in union:
            continue
        declared = {idx for idx in union[table] if idx is not None}
        assert declared == live, (table, sorted(declared), sorted(live))
    version = next(c for c in candidates if c.name == "register_version")
    assert "agent_versions.uq_agent_versions_content_hash" in version.leaf_ids
    assert "agent_versions.uq_agent_versions_blueprint_id_version_label" in version.leaf_ids


def _assert_b2_catalog(leaves, rows, collidable: dict[str, set[str]]) -> None:
    grouped: dict[tuple[str, str], list] = {}
    for row in rows:
        grouped.setdefault((str(row["child_table"]), str(row["idxname"])), []).append(row)
    for leaf in leaves:
        if leaf.tier != "B2":
            continue
        assert leaf.parent_fk_column not in {"tenant_id", "project_id"}, f"B2-2 {leaf.leaf_id}"
        for idx in collidable[leaf.table]:
            matches = [
                row
                for row in grouped.get((leaf.table, idx), [])
                if str(row["parent_table"]) == leaf.parent_table
                and str(row["child_col"]) == leaf.parent_fk_column
            ]
            assert matches, f"B2-1/B2-4 {leaf.leaf_id} index {idx} parent={leaf.parent_table}"
            row = matches[0]
            assert bool(row["parent_server_generated"]) and bool(row["parent_col_is_pk"]), (
                f"B2-3 {leaf.leaf_id}"
            )


def test_p_inventory_1_census_equality() -> None:
    """Inventory test 1: post-fix census equals CANDIDATE_ENDPOINTS minus wrappers."""
    _assert_census_equality(CANDIDATE_ENDPOINTS)


@pytest.mark.asyncio
async def test_p_inventory_2_mapping_totality(admin_engine) -> None:
    """Inventory test 2: every candidate names leaves; no orphans; canonical ids."""
    _collidable, public, _n, _t = await _od8_maps(admin_engine)
    _assert_mapping_totality(CANDIDATE_ENDPOINTS, WRITE_LEAVES, public)


@pytest.mark.asyncio
async def test_p_inventory_3_tier_derivation(admin_engine) -> None:
    """Inventory test 3: OD-8 presence, isolation tuples, slice55 SERIALIZABLE."""
    collidable, _public, n_rows, n_tables = await _od8_maps(admin_engine)
    assert (n_rows, n_tables) == (120, 88), (n_rows, n_tables)
    _assert_tier_derivation(WRITE_LEAVES, collidable)
    print(f"OD-8 live rows={n_rows} tables={n_tables}")


def test_p_inventory_4_tier_a_pending_union() -> None:
    """Inventory test 4: Tier A == registered ⊎ pending; pending is empty at commit 14."""
    _assert_tier_a_registration(WRITE_LEAVES, TIER_A_NODES, PENDING_TIER_A_BATCHES)
    _assert_pending_empty(PENDING_TIER_A_BATCHES)


@pytest.mark.asyncio
async def test_p_inventory_5_per_candidate_index_coverage(admin_engine) -> None:
    """Inventory test 5: each candidate declares every collidable index it writes."""
    collidable, _public, _n, _t = await _od8_maps(admin_engine)
    _assert_index_coverage(CANDIDATE_ENDPOINTS, WRITE_LEAVES, collidable)


@pytest.mark.asyncio
async def test_p_inventory_6_include_column_query(admin_engine) -> None:
    """Inventory test 6 / P-MUT-11: indnkeyatts query detects INCLUDE uniqueness."""
    async with admin_engine.connect() as conn:
        txn = await conn.begin()
        try:
            await conn.execute(
                text("CREATE TABLE slice83_include_probe (id int PRIMARY KEY, code text NOT NULL)")
            )
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX slice83_include_uq ON slice83_include_probe (code) INCLUDE (id)"
                )
            )
            bounded = [
                (str(r[0]), str(r[1]))
                for r in (await conn.execute(text(OD8_SQL))).all()
                if r[0] == "slice83_include_probe"
            ]
            whole = [
                (str(r[0]), str(r[1]))
                for r in (await conn.execute(text(OD8_WHOLE_INDKEY_SQL))).all()
                if r[0] == "slice83_include_probe"
            ]
            assert bounded == [("slice83_include_probe", "slice83_include_uq")], bounded
            assert whole == [], whole
        finally:
            await txn.rollback()


@pytest.mark.asyncio
async def test_p_inventory_7_b2_mapping(admin_engine) -> None:
    """Inventory test 7: B2-1…B2-4 from pg_constraint plus per-edge B2-5."""
    collidable, _public, _n, _t = await _od8_maps(admin_engine)
    async with admin_engine.connect() as conn:
        rows = (await conn.execute(text(B2_SQL))).mappings().all()
    _assert_b2_catalog(WRITE_LEAVES, rows, collidable)
    _assert_b2_edge_evidence(CANDIDATE_ENDPOINTS, WRITE_LEAVES, B2_EDGE_EVIDENCE)


def test_p_mut_7_census_symmetric_difference() -> None:
    """P-MUT-7: dropping or adding a candidate fails census equality by name."""
    dropped = CANDIDATE_ENDPOINTS[0]
    with pytest.raises(AssertionError, match=re.escape(dropped.path)):
        _assert_census_equality(CANDIDATE_ENDPOINTS[1:])
    fake = Candidate(
        "app/fake.py", 1, "not_a_writer", "orm_add", ("budgets.uq_budgets_tenant_id_project_id",)
    )
    with pytest.raises(AssertionError, match="app/fake.py"):
        _assert_census_equality((*CANDIDATE_ENDPOINTS, fake))
