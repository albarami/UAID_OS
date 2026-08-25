"""Slice 83 writer-leaf inventory (test-owned, not a product API)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tests.writer_inventory_b import (
    B2_META,
    COLLIDABLE,
    PENDING_TIER_A_BATCHES as PENDING_TIER_A_BATCHES,
    POST_FIX_MECHANISMS as POST_FIX_MECHANISMS,
    RETRYABLE,
    SERIALIZABLE_CITATION,
    SERIALIZABLE_TABLE,
    SPECS,
    TIER_A_NODE_MAP,
)
from tests.writer_inventory_c import (
    A1_LEAF_IDS as A1_LEAF_IDS,
    SUBTIER as SUBTIER,
)

CENSUS_SCANNER = 'import ast\nfrom collections import Counter\nfrom pathlib import Path\n\n\nclass LocalCalls(ast.NodeVisitor):\n    def __init__(self, root):\n        self.root = root\n        self.calls = []\n\n    def visit_FunctionDef(self, node):\n        if node is self.root:\n            self.generic_visit(node)\n\n    def visit_AsyncFunctionDef(self, node):\n        if node is self.root:\n            self.generic_visit(node)\n\n    def visit_Lambda(self, node):\n        return\n\n    def visit_Call(self, node):\n        self.calls.append(node)\n        self.generic_visit(node)\n\n\ndef receiver_kind(node):\n    if isinstance(node, ast.Name) and node.id in {"session", "self"}:\n        return node.id\n    if (\n        isinstance(node, ast.Attribute)\n        and node.attr == "session"\n        and isinstance(node.value, ast.Name)\n        and node.value.id == "self"\n    ):\n        return "self.session"\n    return None\n\n\nrows = []\nfor path in sorted(Path("app").rglob("*.py")):\n    tree = ast.parse(path.read_text())\n    functions = [\n        node\n        for node in ast.walk(tree)\n        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))\n    ]\n    for function in functions:\n        visitor = LocalCalls(function)\n        visitor.visit(function)\n        mechanisms = set()\n        for call in visitor.calls:\n            target = call.func\n            if (\n                isinstance(target, ast.Attribute)\n                and target.attr in {"add", "add_all"}\n                and receiver_kind(target.value)\n            ):\n                mechanisms.add("orm_add")\n            if isinstance(target, ast.Name) and target.id == "pg_insert":\n                mechanisms.add("pg_insert")\n            if (\n                isinstance(target, ast.Name)\n                and target.id == "text"\n                and call.args\n                and isinstance(call.args[0], ast.Constant)\n                and isinstance(call.args[0].value, str)\n                and "INSERT INTO" in call.args[0].value.upper()\n            ):\n                mechanisms.add("raw_insert")\n        if mechanisms:\n            rows.append(\n                (\n                    str(path),\n                    function.lineno,\n                    function.name,\n                    "+".join(sorted(mechanisms)),\n                )\n            )\n\nprint(f"DIRECT_WRITER_ENDPOINTS={len(rows)}")\nprint(f"PRIVATE_DIRECT={sum(name.startswith(\'_\') for _, _, name, _ in rows)}")\nprint(f"PUBLIC_DIRECT={sum(not name.startswith(\'_\') for _, _, name, _ in rows)}")\ncounts = Counter(mechanism for *_, mechanism in rows)\nprint("MECHANISMS=" + ",".join(f"{key}:{counts[key]}" for key in sorted(counts)))\nfor path, line, name, mechanism in sorted(rows):\n    print(f"{path}:{line}|{name}|{mechanism}")\n\nwrappers = (\n    "app/audit.py:30-52|audit_append|sql_function_wrapper",\n    "app/repositories/admin.py:91-114|admin_write_autonomy_policy|sql_function_wrapper",\n    "app/repositories/go_live_decisions.py:443-472|slice55_finalize_decision|sql_function_wrapper",\n)\nfor wrapper in wrappers:\n    print(wrapper)\nprint(f"INDIRECT_SQL_WRAPPER_ENDPOINTS={len(wrappers)}")\nprint(f"CANDIDATE_WRITER_ENDPOINT_TOTAL={len(rows) + len(wrappers)}")'


@dataclass(frozen=True)
class Candidate:
    """One census endpoint mapped onto one or more write leaves."""

    path: str
    lineno: int
    name: str
    mechanism: str
    leaf_ids: tuple[str, ...]


@dataclass(frozen=True)
class WriteLeaf:
    """One deduplicated (table, unique_index) barrier leaf."""

    leaf_id: str
    table: str
    unique_index: str | None
    tier: str
    parent_table: str | None
    parent_fk_column: str | None
    rationale: str
    isolation_level: str
    retryable_loser_sqlstates: tuple[str, ...]
    isolation_citation: str | None


@dataclass(frozen=True)
class B2EdgeEvidence:
    """B2-5 evidence for one candidate to one B2 leaf."""

    candidate_path: str
    candidate_lineno: int
    candidate_name: str
    candidate_mechanism: str
    leaf_id: str
    parent_leaf_id: str
    parent_creation_citation: str


def leaf_ids_for(tables: tuple[str, ...]) -> tuple[str, ...]:
    """Expand tables into canonical leaf ids using the collidable-index map."""
    ids: list[str] = []
    for table in tables:
        indexes = COLLIDABLE.get(table)
        if indexes:
            ids.extend(f"{table}.{idx}" for idx in indexes)
        else:
            ids.append(f"{table}.-")
    return tuple(ids)


def _leaf(leaf_id: str) -> WriteLeaf:
    table, _, idx = leaf_id.partition(".")
    if idx == "-":
        return WriteLeaf(
            leaf_id=leaf_id,
            table=table,
            unique_index=None,
            tier="B1",
            parent_table=None,
            parent_fk_column=None,
            rationale="table absent from the OD-8 collidable unique-index query",
            isolation_level="READ COMMITTED",
            retryable_loser_sqlstates=(),
            isolation_citation=None,
        )
    if leaf_id in B2_META:
        parent_table, parent_fk, parent_leaf_id, _citation = B2_META[leaf_id]
        return WriteLeaf(
            leaf_id=leaf_id,
            table=table,
            unique_index=idx,
            tier="B2",
            parent_table=parent_table,
            parent_fk_column=parent_fk,
            rationale=f"parent-serialized via {parent_fk}; parent leaf {parent_leaf_id}",
            isolation_level="READ COMMITTED",
            retryable_loser_sqlstates=(),
            isolation_citation=None,
        )
    serializable = table == SERIALIZABLE_TABLE
    return WriteLeaf(
        leaf_id=leaf_id,
        table=table,
        unique_index=idx,
        tier="A",
        parent_table=None,
        parent_fk_column=None,
        rationale="collidable unique index is not parent-serialized for every writer",
        isolation_level="SERIALIZABLE" if serializable else "READ COMMITTED",
        retryable_loser_sqlstates=RETRYABLE if serializable else (),
        isolation_citation=SERIALIZABLE_CITATION if serializable else None,
    )


CANDIDATE_ENDPOINTS: tuple[Candidate, ...] = tuple(
    Candidate(path, lineno, name, mechanism, leaf_ids_for(tables))
    for path, lineno, name, mechanism, tables in SPECS
)

_ordered: list[str] = []
_seen: set[str] = set()
for candidate in CANDIDATE_ENDPOINTS:
    for leaf_id in candidate.leaf_ids:
        if leaf_id not in _seen:
            _seen.add(leaf_id)
            _ordered.append(leaf_id)

WRITE_LEAVES: tuple[WriteLeaf, ...] = tuple(_leaf(leaf_id) for leaf_id in _ordered)
LEAVES_BY_ID: Mapping[str, WriteLeaf] = {leaf.leaf_id: leaf for leaf in WRITE_LEAVES}

_edges: list[B2EdgeEvidence] = []
for candidate in CANDIDATE_ENDPOINTS:
    for leaf_id in candidate.leaf_ids:
        leaf = LEAVES_BY_ID[leaf_id]
        if leaf.tier != "B2":
            continue
        _parent_table, _fk, parent_leaf_id, citation = B2_META[leaf_id]
        _edges.append(
            B2EdgeEvidence(
                candidate_path=candidate.path,
                candidate_lineno=candidate.lineno,
                candidate_name=candidate.name,
                candidate_mechanism=candidate.mechanism,
                leaf_id=leaf_id,
                parent_leaf_id=parent_leaf_id,
                parent_creation_citation=citation,
            )
        )
B2_EDGE_EVIDENCE: tuple[B2EdgeEvidence, ...] = tuple(_edges)

TIER_A_NODES: Mapping[str, tuple[str, ...]] = TIER_A_NODE_MAP
