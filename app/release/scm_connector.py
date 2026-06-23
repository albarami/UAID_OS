"""Source-control connector (Slice 28, App. B #3 / §26.3) — GitHub-first, fake-in-tests.

Mirrors the ``app/llm`` pattern: a ``SCMConnector`` protocol + a ``FakeSCMConnector`` (**all
tests/CI — no network, no token**) + a shipped ``GitHubSCMConnector`` adapter (**NEVER exercised in
tests**; token env-only, fail-closed, redacted).

**Honesty (D-28-8):** a ``200`` from the branch-protection endpoint means protection is **ON** and
yields a mapped result; ``403`` (insufficient token), ``404`` ("branch not protected" / missing / no
access — indistinguishable), any non-200 / timeout / malformed ⇒ ``SCMConnectorError`` ⇒ the caller
writes **no** verified snapshot. The connector never fabricates a "verified-off" snapshot. The live
HTTP call exists only in ``GitHubSCMConnector`` and is not run in CI.
"""

from __future__ import annotations

from typing import Any, Protocol


class SCMConnectorError(Exception):
    """Provider response missing / ambiguous / malformed, or transport failure (fail-closed)."""


class MissingConnectorCredential(SCMConnectorError):
    """No connector credential is configured (fail-closed)."""


class SCMConnector(Protocol):
    async def fetch_branch_protection(self, *, repo_ref: str, branch: str) -> dict | None:
        """Return MAPPED snapshot fields for a protected branch, or ``None`` if not configured.
        Raise ``SCMConnectorError`` on a provider/transport failure (fail-closed)."""
        ...


def map_github_branch_protection(payload: Any) -> dict:
    """Map a GitHub ``GET .../branches/{branch}/protection`` 200 body to snapshot fields (pure).

    A 200 means protection is ON. Unexpected shape ⇒ ``SCMConnectorError``. No token/URL in the result.
    """
    if not isinstance(payload, dict):
        raise SCMConnectorError("branch-protection payload must be a JSON object")
    enforce = payload.get("enforce_admins")
    if not isinstance(enforce, dict) or not isinstance(enforce.get("enabled"), bool):
        raise SCMConnectorError("enforce_admins.enabled must be a bool")
    contexts: list[str] = []
    rsc = payload.get("required_status_checks")
    if rsc is not None:
        if not isinstance(rsc, dict):
            raise SCMConnectorError("required_status_checks must be an object")
        if "contexts" in rsc:
            raw = rsc["contexts"]
            if not isinstance(raw, list) or not all(isinstance(c, str) for c in raw):
                raise SCMConnectorError("required_status_checks.contexts must be a list of strings")
            contexts = list(raw)
        elif "checks" in rsc:
            raw = rsc["checks"]
            if not isinstance(raw, list) or not all(
                isinstance(c, dict) and isinstance(c.get("context"), str) for c in raw
            ):
                raise SCMConnectorError(
                    "required_status_checks.checks must be a list of {context: str}"
                )
            contexts = [c["context"] for c in raw]
    return {
        "provider": "github",
        "protection_enabled": True,  # a 200 ⇒ protection is on
        "required_pull_request_reviews": isinstance(
            payload.get("required_pull_request_reviews"), dict
        ),
        "required_status_checks": contexts,
        "enforce_admins": enforce["enabled"],
    }


class FakeSCMConnector:
    """Test/CI connector — no network, no token. Returns a canned mapped result, ``None``, or raises."""

    def __init__(self, result: dict | None = None, *, error: Exception | None = None):
        self._result = result
        self._error = error

    async def fetch_branch_protection(self, *, repo_ref: str, branch: str) -> dict | None:
        if self._error is not None:
            raise self._error
        return self._result


class GitHubSCMConnector:
    """Shipped GitHub adapter — **NEVER exercised in tests** (no network in CI). Token env-only,
    fail-closed, redacted. Only a ``200`` yields a mapped result; ``403``/``404``/non-200/timeout/
    malformed raise ``SCMConnectorError`` (caller writes no verified snapshot). Min token permission:
    a classic ``repo`` scope or fine-grained **Administration: read** (branch-protection read needs
    admin)."""

    def __init__(self, token: str):
        if not token:
            raise MissingConnectorCredential("no GitHub connector token configured")
        self._token = token  # never logged/persisted/serialized

    async def fetch_branch_protection(self, *, repo_ref: str, branch: str) -> dict | None:
        import httpx  # lazy so the pure parts import without the dependency

        url = f"https://api.github.com/repos/{repo_ref}/branches/{branch}/protection"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:  # message carries no token/URL
            raise SCMConnectorError("github branch-protection request failed") from exc
        if resp.status_code == 200:
            try:
                return map_github_branch_protection(resp.json())
            except SCMConnectorError:
                raise  # already a fail-closed mapping error
            except Exception as exc:  # invalid JSON / unexpected mapping failure ⇒ fail-closed
                raise SCMConnectorError("github branch-protection response was malformed") from exc
        # 403 insufficient scope, 404 not-protected/missing/no-access, anything else ⇒ fail-closed.
        raise SCMConnectorError(
            f"github branch-protection not available (status {resp.status_code})"
        )
