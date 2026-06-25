"""Approval-channel adapters (Slice 33) — dashboard-only, fake-in-tests.

An ``ApprovalChannel`` protocol + a ``FakeChannel`` (**all tests/CI**) + a ``DashboardChannel`` (the only
real channel this slice — **no external I/O**: the approval is already surfaced by the existing read API
``GET /api/projects/{id}/approvals``, so "delivery" is a no-op that returns ``delivered``). External
channels (slack/teams/email/ticketing) are protocol-conformant adapters **deferred** to a follow-up (each
needs operator-controlled credentials/audience — out of scope; **no secret material** this slice). The
``notification`` passed to ``deliver`` carries only routing facts (no recipient/secret)."""

from __future__ import annotations

from typing import Protocol


class ApprovalChannel(Protocol):
    name: str

    async def deliver(self, notification: dict) -> str:
        """Deliver the notification; return a status ∈ {delivered, failed, skipped}. Never reads/returns
        a secret value."""
        ...


class FakeChannel:
    """Test/CI channel — no I/O. Returns a canned status (default ``delivered``) or raises."""

    def __init__(
        self, *, name: str = "dashboard", status: str = "delivered", error: Exception | None = None
    ):
        self.name = name
        self._status = status
        self._error = error

    async def deliver(self, notification: dict) -> str:
        if self._error is not None:
            raise self._error
        return self._status


class DashboardChannel:
    """The dashboard channel — no external I/O. The approval is surfaced by the existing read API; delivery
    is a recorded no-op returning ``delivered``."""

    name = "dashboard"

    async def deliver(self, notification: dict) -> str:
        return "delivered"
