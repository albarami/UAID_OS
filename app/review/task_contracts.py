"""§27.2 task-contract shape (Slice 42) — pure validators.

A task contract is created **before any builder starts** (§13.2, spec:1240) and records who
must build, who must check, and against which spine targets. This module validates the
caller-supplied shape fail-closed; nothing here executes or authorizes anything. Spine
references (requirements/ACs/oracles) are FK-proven at the storage layer via
``task_contract_artifact_links`` (existence by composite FK, kind by DB guard — this module
only validates the ``link_kind`` vocabulary). Every user text field is bounded AND non-blank
(the Slice-41 lesson); ``allowed_tools``/``forbidden_tools`` must be KNOWN broker-registry
tools and disjoint.
"""

from __future__ import annotations

import re

# §27.2 (spec:2563) — the contract risk axis.
RISK_LEVELS = ("low", "medium", "high", "critical")

# §13.1 (spec:1230-1236) — the three review layers.
REVIEW_LAYERS = ("role_specific", "cross_functional", "acceptance")

# D-42-2 — link kinds → the spine ``intake_artifacts.kind`` each must resolve to.
ARTIFACT_LINK_KINDS = {
    "source_requirement": "requirement",
    "acceptance_criterion": "acceptance_criterion",
    "test_oracle": "test_oracle",
}

MAX_TASK_REF = 64
TASK_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_TITLE = 200
MAX_DESCRIPTION = 4000
MAX_LIST_ITEMS = 32
MAX_ITEM_CHARS = 500
# Factory parity (app/agents/factory.py:27-29).
MAX_TOOLS = 64
MAX_REVIEWERS = 16
MAX_TOOL_NAME_CHARS = 128


def require_text(name: str, value, max_chars: int) -> None:
    """Bounded, NON-BLANK text (B3 + the Slice-41 whitespace lesson); cap on the raw value."""
    if not isinstance(value, str) or not (1 <= len(value) <= max_chars) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string of at most {max_chars} chars")


def require_text_list(name: str, value, *, max_items: int, max_chars: int) -> None:
    """A real list/tuple (never a bare string) of bounded, non-blank strings."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list of strings")
    if len(value) > max_items:
        raise ValueError(f"{name} must have at most {max_items} items")
    for item in value:
        require_text(f"{name} item", item, max_chars)


def validate_artifact_link(link_kind) -> None:
    if link_kind not in ARTIFACT_LINK_KINDS:
        raise ValueError(f"unknown link_kind: {link_kind!r}")


def validate_new_contract(
    *,
    task_ref,
    title,
    description,
    must_have,
    must_not_do,
    required_evidence,
    definition_of_done,
    allowed_tools,
    forbidden_tools,
    risk_level,
) -> None:
    """Fail-closed validation of a new (draft) §27.2 contract shape."""
    if not isinstance(task_ref, str) or not TASK_REF_RE.match(task_ref):
        raise ValueError(f"invalid task_ref: {task_ref!r}")
    require_text("title", title, MAX_TITLE)
    require_text("description", description, MAX_DESCRIPTION)
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"unknown risk_level: {risk_level!r}")
    for name, value in (
        ("must_have", must_have),
        ("must_not_do", must_not_do),
        ("required_evidence", required_evidence),
        ("definition_of_done", definition_of_done),
    ):
        require_text_list(name, value, max_items=MAX_LIST_ITEMS, max_chars=MAX_ITEM_CHARS)
    for name, value in (("allowed_tools", allowed_tools), ("forbidden_tools", forbidden_tools)):
        require_text_list(name, value, max_items=MAX_TOOLS, max_chars=MAX_TOOL_NAME_CHARS)

    # KNOWN broker-registry tools only (deny-by-default; the broker stays the authority).
    # Lazy import mirrors app/agents/factory.py:41-57 (dodges the app.tools package cycle).
    from app.tools.registry import get_contract

    for tool in list(allowed_tools) + list(forbidden_tools):
        if get_contract(tool) is None:
            raise ValueError(f"unknown tool (not in the broker registry): {tool!r}")
    overlap = set(allowed_tools) & set(forbidden_tools)
    if overlap:
        raise ValueError(f"allowed_tools and forbidden_tools overlap: {sorted(overlap)!r}")
