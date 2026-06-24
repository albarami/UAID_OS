"""Shared project-repo + credential resolver (Slice 28, D-28-11/13) — fail-closed.

Used by BOTH the connector (fetch time) AND gate #3 (evaluation time), so the evidence written and the
evidence the gate trusts are bound to the **same** current declaration. A project can be evidenced
**only against its own declared repo**; revising the declaration invalidates old-repo evidence.

Leaf module: imports only the intake-category repo + the pure ``ci_evidence`` regexes — no
``production_autonomy``/``ci_evidence_service`` import (avoids a cycle).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.release.ci_evidence import REPO_REF_RE, TOKENISH_RE
from app.repositories.intake_categories import IntakeCategoryRepository
from app.tenancy import TenantContext

_REPO_CATEGORY = "existing_assets_and_repositories"
_SECRETS_CATEGORY = "secrets_and_credentials_manifest"
# This slice resolves the token from operator env GITHUB_CONNECTOR_TOKEN (D-28-3/9); the project's
# secrets manifest must name exactly that reference as the credential SOURCE.
_REQUIRED_MANAGER = "env"
_REQUIRED_REFERENCE_NAME = "GITHUB_CONNECTOR_TOKEN"


async def resolve_declared_repo(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> tuple[str, str] | None:
    """Return ``(repo_ref, branch)`` from the project's declared
    ``existing_assets_and_repositories``, or ``None`` (caller fails closed) when undeclared / not
    ``declared`` / malformed. Never guesses a repo; validates the slug + token denylist."""
    cat = await IntakeCategoryRepository(session, context).get_category(project_id, _REPO_CATEGORY)
    if cat is None or cat.status != "declared":
        return None
    data = cat.data if isinstance(cat.data, dict) else {}
    repo_ref = data.get("primary_repository")
    if (
        not isinstance(repo_ref, str)
        or REPO_REF_RE.fullmatch(repo_ref) is None
        or TOKENISH_RE.search(repo_ref) is not None
    ):
        return None
    branch = data.get("protected_branch", "main")
    if not isinstance(branch, str) or not branch.strip():
        return None
    return repo_ref, branch


async def has_declared_credential(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> bool:
    """True iff the project's ``secrets_and_credentials_manifest`` names a **usable, reference-only**
    GitHub-connector credential — an ``{manager: 'env', reference_name: 'GITHUB_CONNECTOR_TOKEN'}``
    entry (top-level or in ``references[]``). The reference is the credential **source**; the token
    value resolves from operator env (D-28-9). Fail-closed: missing / empty / unrelated ⇒ False."""
    cat = await IntakeCategoryRepository(session, context).get_category(
        project_id, _SECRETS_CATEGORY
    )
    if cat is None or cat.status != "declared":
        return False
    data = cat.data if isinstance(cat.data, dict) else {}
    refs = data["references"] if isinstance(data.get("references"), list) else [data]
    return any(
        isinstance(e, dict)
        and e.get("manager") == _REQUIRED_MANAGER
        and e.get("reference_name") == _REQUIRED_REFERENCE_NAME
        for e in refs
    )
