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
from app.release.deploy_evidence import DeploySSRFRejected, validate_target_host
from app.repositories.intake_categories import IntakeCategoryRepository
from app.tenancy import TenantContext

_REPO_CATEGORY = "existing_assets_and_repositories"
_SECRETS_CATEGORY = "secrets_and_credentials_manifest"
_ENV_CATEGORY = "environments_and_deployment_targets"
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


async def resolve_declared_production_target(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> str | None:
    """Return the project's declared **production deploy host** (Slice 30, B-30-3) — the FQDN at
    ``data["environments"]["production"]["domain"]`` of the declared ``environments_and_deployment_targets``
    category (file 16), or ``None`` (caller fails closed). Fail-closed cases: missing category / status ≠
    ``declared`` / ``data`` not a dict / missing ``environments`` / missing/non-dict ``production`` block /
    blank/non-string ``domain`` / domain fails the SSRF host-shape rules (IP literal / localhost / .local /
    .internal). Used by BOTH the connector (probe time) AND gate #2 (evaluation time) so evidence is bound
    to the same current declaration."""
    cat = await IntakeCategoryRepository(session, context).get_category(project_id, _ENV_CATEGORY)
    if cat is None or cat.status != "declared":
        return None
    data = cat.data if isinstance(cat.data, dict) else {}
    envs = data.get("environments")
    if not isinstance(envs, dict):
        return None
    production = envs.get("production")
    if not isinstance(production, dict):
        return None
    domain = production.get("domain")
    if not isinstance(domain, str) or not domain.strip():
        return None
    host = domain.strip()
    try:
        validate_target_host(host)  # SSRF host-shape; unsafe ⇒ fail closed
    except DeploySSRFRejected:
        return None
    return host
