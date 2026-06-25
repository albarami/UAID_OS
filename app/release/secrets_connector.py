"""Secrets-manager reference connector (Slice 32) — env-only, fake-in-tests.

A ``SecretsManagerConnector`` protocol + a ``FakeSecretsManagerConnector`` (**all tests/CI**) + a shipped
``EnvSecretsManagerConnector`` (**local, real** — operator process env). The connector answers *does this
reference resolve?* and returns **only** an outcome dict (`{outcome, resolved}`) — it **never returns,
logs, or stores a secret value** (B4). For the `env` manager it computes
``bool((os.environ.get(name) or "").strip())`` and discards the value immediately; a manager outside
``SUPPORTED_MANAGERS`` is honestly ``unsupported_manager`` (no env lookup, B1). No network ⇒ no SSRF
surface this slice.
"""

from __future__ import annotations

import os
from typing import Protocol

from app.release.secrets_verification import (
    SUPPORTED_MANAGERS,
    build_env_outcome,
    observation_probe_error,
    observation_unsupported_manager,
)


class SecretsManagerConnector(Protocol):
    async def verify_reference(self, *, manager: str, reference_name: str) -> dict:
        """Return an outcome dict ``{outcome, resolved}`` for the reference. Never returns a value."""
        ...


class FakeSecretsManagerConnector:
    """Test/CI connector — no real manager. Returns a canned outcome dict or raises."""

    def __init__(self, result: dict | None = None, *, error: Exception | None = None):
        self._result = result
        self._error = error

    async def verify_reference(self, *, manager: str, reference_name: str) -> dict:
        if self._error is not None:
            raise self._error
        if manager not in SUPPORTED_MANAGERS:
            return observation_unsupported_manager()
        return self._result if self._result is not None else build_env_outcome(present=False)


class EnvSecretsManagerConnector:
    """Shipped local adapter — verifies an ``env`` reference resolves (the env var is **set and non-empty**)
    WITHOUT exposing the value: the value is inspected transiently only to compute the boolean, never
    returned/logged/stored (B4). A non-``env`` manager ⇒ ``unsupported_manager`` (B1)."""

    async def verify_reference(self, *, manager: str, reference_name: str) -> dict:
        if manager not in SUPPORTED_MANAGERS:
            return observation_unsupported_manager()
        try:
            present = bool((os.environ.get(reference_name) or "").strip())
        except Exception:  # pragma: no cover - os.environ access is not expected to raise
            return observation_probe_error()
        return build_env_outcome(present=present)
