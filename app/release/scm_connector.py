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

from app.release.pr_evidence import normalize_approvals, parse_iso_timestamp


class SCMConnectorError(Exception):
    """Provider response missing / ambiguous / malformed, or transport failure (fail-closed)."""


class MissingConnectorCredential(SCMConnectorError):
    """No connector credential is configured (fail-closed)."""


class SCMConnector(Protocol):
    async def fetch_branch_protection(self, *, repo_ref: str, branch: str) -> dict | None:
        """Return MAPPED snapshot fields for a protected branch, or ``None`` if not configured.
        Raise ``SCMConnectorError`` on a provider/transport failure (fail-closed)."""
        ...

    async def fetch_pull_request(self, *, repo_ref: str, pr_number: int) -> dict | None:
        """Return MAPPED PR-evidence fields, or ``None`` if not configured. Raise
        ``SCMConnectorError`` on a PR/reviews provider/transport failure (fail-closed, B-29-7)."""
        ...


# GitHub check-run conclusion -> our observed CHECK_STATES (B-29-1).
_CONCLUSION_TO_STATE = {
    "success": "success",
    "failure": "failure",
    "timed_out": "failure",
    "cancelled": "failure",
    "action_required": "failure",
    "neutral": "neutral",
    "skipped": "neutral",
    "stale": "unknown",
}


def _summarize_checks(checks: Any, combined_status: Any) -> dict | None:
    """Map head-SHA check-runs + combined status to an observed ``check_status_summary`` (B-29-1).
    ``None`` when no check evidence was observed — NEVER a fabricated 'passed'."""
    if checks is None and combined_status is None:
        return None
    summary: dict[str, Any] = {}
    runs = checks.get("check_runs", []) if isinstance(checks, dict) else []
    for run in runs if isinstance(runs, list) else []:
        if not isinstance(run, dict):
            continue
        if run.get("status") in ("queued", "in_progress"):
            state = "pending"
        else:  # completed (or unknown status) -> map by conclusion
            state = _CONCLUSION_TO_STATE.get(run.get("conclusion") or "", "unknown")
        summary[state] = summary.get(state, 0) + 1
    if isinstance(combined_status, dict):
        cs = combined_status.get("state")
        if cs == "error":  # GitHub legacy combined status 'error' is a non-success -> failure tier
            cs = "failure"
        if cs in ("success", "failure", "pending"):
            summary["combined_state"] = cs
    return summary or None


def _requested_principals(requested_reviewers: Any) -> list[str]:
    """Extract requested reviewer/team handles from the GitHub requested-reviewers shape."""
    out: list[str] = []
    if isinstance(requested_reviewers, dict):
        for user in requested_reviewers.get("users", []) or []:
            if isinstance(user, dict) and isinstance(user.get("login"), str):
                out.append(user["login"])
        for team in requested_reviewers.get("teams", []) or []:
            if isinstance(team, dict) and isinstance(team.get("slug"), str):
                out.append("team:" + team["slug"])
    elif isinstance(requested_reviewers, list):  # PR object embeds a flat user list
        for user in requested_reviewers:
            if isinstance(user, dict) and isinstance(user.get("login"), str):
                out.append(user["login"])
    return out


def map_github_pull_request(
    pull: Any,
    reviews: Any,
    *,
    requested_reviewers: Any = None,
    requested_reviewers_observed: bool = False,
    checks: Any = None,
    combined_status: Any = None,
) -> dict:
    """Map GitHub PR + reviews (+ optional requested-reviewers + head-SHA checks) to PR-evidence
    snapshot fields (pure). ``pull`` and ``reviews`` are **required** (missing/malformed ⇒
    ``SCMConnectorError``, B-29-7); requested-reviewers/checks are optional/observed. No
    token/URL/body/diff in the result. The caller (service) adds provider/repo_ref/pr_number/observed_at.
    """
    if not isinstance(pull, dict):
        raise SCMConnectorError("pull-request payload must be a JSON object")
    if not isinstance(reviews, list):
        raise SCMConnectorError("reviews payload must be a JSON array")

    merged = bool(pull.get("merged"))
    pr_state = "merged" if merged else ("open" if pull.get("state") == "open" else "closed")

    def _login(node: Any) -> str | None:
        return (
            node.get("login")
            if isinstance(node, dict) and isinstance(node.get("login"), str)
            else None
        )

    base = pull.get("base")
    base = base if isinstance(base, dict) else {}
    head = pull.get("head")
    head = head if isinstance(head, dict) else {}

    norm_reviews = []
    for rev in reviews:
        if not isinstance(rev, dict):
            continue
        login = _login(rev.get("user"))
        if login is None:
            continue
        norm_reviews.append(
            {"principal": login, "state": rev.get("state"), "submitted_at": rev.get("submitted_at")}
        )
    approver_principals, reviewer_principals, approval_count = normalize_approvals(norm_reviews)

    return {
        "pr_state": pr_state,
        "merged": merged,
        "merged_at": parse_iso_timestamp(pull.get("merged_at")),
        "merge_commit_sha": pull.get("merge_commit_sha"),
        "base_branch": base.get("ref"),
        "base_sha": base.get("sha"),
        "head_branch": head.get("ref"),
        "head_sha": head.get("sha"),
        "author_principal": _login(pull.get("user")),
        "merger_principal": _login(pull.get("merged_by")),
        "approver_principals": approver_principals,
        "reviewer_principals": reviewer_principals,
        "approval_count": approval_count,
        "requested_reviewer_principals": (
            _requested_principals(requested_reviewers) if requested_reviewers_observed else []
        ),
        "requested_reviewers_observed": bool(requested_reviewers_observed),
        "check_status_summary": _summarize_checks(checks, combined_status),
    }


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

    async def fetch_pull_request(self, *, repo_ref: str, pr_number: int) -> dict | None:
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

    async def fetch_pull_request(self, *, repo_ref: str, pr_number: int) -> dict | None:
        """Fetch PR + reviews (MANDATORY, B-29-7) + requested-reviewers (observed) + head-SHA checks
        (optional). PR/reviews non-200 or transport failure ⇒ ``SCMConnectorError`` (no snapshot);
        requested-reviewers/checks failure degrades gracefully. **Never exercised in CI.**"""
        import httpx  # lazy so the pure parts import without the dependency

        base_url = f"https://api.github.com/repos/{repo_ref}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # PR + reviews are MANDATORY — a non-200 here writes NO verified snapshot.
                pr_resp = await client.get(f"{base_url}/pulls/{pr_number}", headers=headers)
                if pr_resp.status_code != 200:
                    raise SCMConnectorError(
                        f"github pull-request not available (status {pr_resp.status_code})"
                    )
                rev_resp = await client.get(
                    f"{base_url}/pulls/{pr_number}/reviews", headers=headers
                )
                if rev_resp.status_code != 200:
                    raise SCMConnectorError(
                        f"github pull-request reviews not available (status {rev_resp.status_code})"
                    )
                pull, reviews = pr_resp.json(), rev_resp.json()
                # Requested reviewers: OBSERVED — non-200 OR transport failure ⇒ observed=false
                # (its own except so a transient failure on this OPTIONAL endpoint does NOT abort the
                # already-complete mandatory evidence; never a silent empty).
                requested, observed = None, False
                try:
                    rr_resp = await client.get(
                        f"{base_url}/pulls/{pr_number}/requested_reviewers", headers=headers
                    )
                    if rr_resp.status_code == 200:
                        requested, observed = rr_resp.json(), True
                except httpx.HTTPError:
                    requested, observed = None, False
                # Checks: OPTIONAL observed-only — non-200 OR transport failure ⇒ check_status_summary=None.
                checks = combined = None
                head_sha = (pull.get("head") or {}).get("sha") if isinstance(pull, dict) else None
                if isinstance(head_sha, str):
                    try:
                        cr_resp = await client.get(
                            f"{base_url}/commits/{head_sha}/check-runs", headers=headers
                        )
                        if cr_resp.status_code == 200:
                            checks = cr_resp.json()
                        cs_resp = await client.get(
                            f"{base_url}/commits/{head_sha}/status", headers=headers
                        )
                        if cs_resp.status_code == 200:
                            combined = cs_resp.json()
                    except httpx.HTTPError:
                        checks = combined = None
        except httpx.HTTPError as exc:  # PR/reviews transport failure ⇒ fail-closed (no snapshot)
            raise SCMConnectorError("github pull-request request failed") from exc
        try:
            return map_github_pull_request(
                pull,
                reviews,
                requested_reviewers=requested,
                requested_reviewers_observed=observed,
                checks=checks,
                combined_status=combined,
            )
        except SCMConnectorError:
            raise
        except Exception as exc:  # unexpected mapping failure ⇒ fail-closed
            raise SCMConnectorError("github pull-request response was malformed") from exc
