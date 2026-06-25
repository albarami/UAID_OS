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
from app.release.monitoring_evidence import (
    InvalidMonitoringSnapshot,
    parse_and_validate_status_url,
)
from app.release.secrets_verification import is_valid_manager, is_valid_reference_name
from app.repositories.intake_categories import IntakeCategoryRepository
from app.tenancy import TenantContext

_REPO_CATEGORY = "existing_assets_and_repositories"
_SECRETS_CATEGORY = "secrets_and_credentials_manifest"
_ENV_CATEGORY = "environments_and_deployment_targets"
_MONITORING_CATEGORY = "operations_observability_support"
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


async def resolve_declared_secret_references(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> list[tuple[str, str]]:
    """Return ALL declared ``(manager, reference_name)`` references from the project's
    ``secrets_and_credentials_manifest`` (Slice 32, B5) — the **canonical persisted category shape only**:
    ``data["references"]`` (list of ``{manager, reference_name}``) **or** a top-level
    ``{manager, reference_name}`` (the ``has_declared_credential`` read pattern). Template-YAML
    normalization (``secret_manager``/``secrets[]``) is out of scope. Fail-closed: undeclared / not
    ``declared`` / malformed entries are skipped. **Never a secret value** — only the names."""
    cat = await IntakeCategoryRepository(session, context).get_category(
        project_id, _SECRETS_CATEGORY
    )
    if cat is None or cat.status != "declared":
        return []
    data = cat.data if isinstance(cat.data, dict) else {}
    refs = data["references"] if isinstance(data.get("references"), list) else [data]
    out: list[tuple[str, str]] = []
    for entry in refs:
        if not isinstance(entry, dict):
            continue
        manager = entry.get("manager")
        reference_name = entry.get("reference_name")
        # Fail closed (D-32-10): skip entries that do not match the Slice-32 bounded shapes — the
        # upstream category validator permits short strings but does NOT enforce MANAGER_RE /
        # REFERENCE_NAME_RE, so a malformed persisted manager/name must never reach the broker or the
        # DB write. A VALID-shape but unsupported manager (e.g. ``vault``) is kept here and recorded
        # downstream as ``unsupported_manager`` (B1) — only malformed shapes are dropped.
        if is_valid_manager(manager) and is_valid_reference_name(reference_name):
            out.append((manager, reference_name))
    return out


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


async def resolve_declared_monitoring_target(
    session: AsyncSession, context: TenantContext, project_id: uuid.UUID
) -> tuple[str, str, str] | None:
    """Return ``(status_url, host, path)`` from the project's declared
    ``operations_observability_support`` (file 22) ``data["monitoring"]`` block (Slice 31, D-31-3), or
    ``None`` (caller fails closed). ``status_url`` is the full declared URL — the binding key (B2) — and
    is validated HTTPS-only / no-userinfo-query-fragment / port-443 / SSRF-safe-FQDN-host /
    normalized-bounded-path (``parse_and_validate_status_url``). **Unauthenticated-only (B9):** no
    credential is read or returned. Fail-closed: missing category / status ≠ ``declared`` / ``data`` not
    a dict / missing/non-dict ``monitoring`` / ``provider`` ≠ ``generic_monitoring_api`` / blank/non-string
    or invalid ``status_url``. Used by BOTH the connector (read time) AND gate #11 (evaluation time)."""
    cat = await IntakeCategoryRepository(session, context).get_category(
        project_id, _MONITORING_CATEGORY
    )
    if cat is None or cat.status != "declared":
        return None
    data = cat.data if isinstance(cat.data, dict) else {}
    monitoring = data.get("monitoring")
    if not isinstance(monitoring, dict):
        return None
    if monitoring.get("provider") != "generic_monitoring_api":
        return None
    status_url = monitoring.get("status_url")
    if not isinstance(status_url, str):
        return None
    try:
        host, path = parse_and_validate_status_url(status_url)
    except InvalidMonitoringSnapshot:
        return None
    return status_url, host, path
