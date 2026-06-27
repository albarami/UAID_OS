"""Agent Factory — realization + factory workflow (Slice 39, §9.1-9.4) — pure helpers + the orchestrator.

This module REALIZES an agent (§9.4 steps 1-4, 8): bind an **already-registered** version into a tenant
``agent_instance`` + its instance-scoped tool allowlist + FK-backed reviewers + an inert
``agent_realizations`` record stamped ``qualification_status='unqualified'``.

**Trust zone (B1):** the factory writes **tenant rows only** (inside ``tenant_scope``); blueprint/version
registration stays an **admin-path precondition** (``register_blueprint``/``register_version`` on an admin
session). **Qualification is Slice 40** (§9.5.1): every realization is ``unqualified`` and unlocks no
authority — the broker's qualification gate always denies (§9 honesty). No LLM, no execution.

The pure helpers (validators + status constants) live here; ``AgentRealizationRepository`` (the DB
orchestrator) lives in ``app.repositories.agent_realizations``.
"""

from __future__ import annotations

import re
import uuid

# §9.5.1 — qualification axis. Only ``unqualified`` is INSERT-able this slice (B4); the
# ``unqualified→qualified`` transition lands in Slice 40 under an eval gate.
QUALIFICATION_STATUSES = ("unqualified", "qualified")
REALIZE_INSERT_STATUS = "unqualified"

INSTANCE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
MAX_TOOLS_PER_REALIZATION = 64
MAX_REVIEWERS_PER_REALIZATION = 16
MAX_TOOL_NAME_CHARS = 128


def validate_realization_request(
    *,
    instance_key: str,
    tool_allowlist,
    reviewer_blueprint_ids,
) -> None:
    """Validate the SHAPE/bounds of a realization request (fail closed). The broker validates each
    granted tool at call time (``DENIED_UNKNOWN_TOOL``), so an unknown granted tool is inert."""
    if not isinstance(instance_key, str) or not INSTANCE_KEY_RE.match(instance_key):
        raise ValueError(f"invalid instance_key: {instance_key!r}")

    tools = list(tool_allowlist)
    if len(tools) > MAX_TOOLS_PER_REALIZATION:
        raise ValueError(f"too many tools (> {MAX_TOOLS_PER_REALIZATION})")
    for t in tools:
        if not isinstance(t, str) or not (1 <= len(t) <= MAX_TOOL_NAME_CHARS):
            raise ValueError(f"invalid tool name: {t!r}")

    reviewers = list(reviewer_blueprint_ids)
    if len(reviewers) > MAX_REVIEWERS_PER_REALIZATION:
        raise ValueError(f"too many reviewers (> {MAX_REVIEWERS_PER_REALIZATION})")
    for r in reviewers:
        try:
            uuid.UUID(str(r))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError(f"invalid reviewer_blueprint_id: {r!r}") from exc
