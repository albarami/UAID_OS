"""PM / issue-tracker connector (Slice 34) — Jira, fake-in-tests; **live adapter deferred (B5)**.

An ``IssueTrackerConnector`` protocol + a ``FakeIssueTrackerConnector`` (**all tests/CI — no network**).
The shipped live ``JiraIssueTrackerConnector`` (HTTP, with its operator-allowlist base-URL / redirect /
timeout / pagination / body-cap / credential-audience contract) is **NOT shipped this slice** — deferred to
a dedicated follow-up. ``fetch_issues`` returns **observed facts only** per item —
``{external_ref, external_status, title_present}`` — and **never a title/description/credential**. Read-only:
the connector never writes back to the PM tool.
"""

from __future__ import annotations

from typing import Protocol


class IssueTrackerConnector(Protocol):
    async def fetch_issues(self, *, instance_key: str, project_key: str) -> list[dict]:
        """Return observed facts for the project's external PM issues — each a dict with
        ``external_ref`` / ``external_status`` / ``title_present`` only. Never returns a title/credential."""
        ...


class FakeIssueTrackerConnector:
    """Test/CI connector — no network. Returns a canned list of observations or raises."""

    def __init__(self, result: list[dict] | None = None, *, error: Exception | None = None):
        self._result = result if result is not None else []
        self._error = error

    async def fetch_issues(self, *, instance_key: str, project_key: str) -> list[dict]:
        if self._error is not None:
            raise self._error
        return list(self._result)
