"""Agent registry service (Slice 6, §9.7 / §17.4 / §22.2).

Two paths, matching the two trust zones:

- **Global catalog (admin path):** ``register_blueprint`` / ``register_version``
  operate on the GLOBAL tables. Blueprints/versions are admin-curated (the runtime
  role ``uaid_app`` has ``SELECT`` only), so these run on an admin session and are
  NOT audited here (the Slice-2 audit append derives the tenant from the GUC;
  platform/global-event audit is deferred). ``register_version`` validates the six
  §22.2 component hashes, computes a deterministic ``content_hash``, and is
  idempotent on it (identical content => existing row; changed content => new row).

- **Tenant path:** ``AgentInstanceRepository`` is a ``TenantScopedRepository`` for
  the tenant-owned ``agent_instances``. Every mutation writes an ``audit_logs``
  entry (run inside ``tenant_scope`` so the GUC is set). ``actor`` is an untrusted
  caller label (the agent registry is not wired to Slice 27 request-auth identity).

This is a registry skeleton: no Agent Factory, no qualification/eval execution, no
model routing, no agent execution, no broker wiring.
"""

import hashlib
import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.concurrency import ConcurrentWriteUnresolved
from app.models.agent_blueprint import AgentBlueprint
from app.models.agent_instance import AgentInstance
from app.models.agent_version import COMPONENT_HASH_FIELDS, AgentVersion
from app.tenancy import TenantContext, TenantScopedRepository

# Canonical archetype set (§9.5.1). A blueprint's archetype must be one of these.
ARCHETYPES: frozenset[str] = frozenset(
    {
        "builder",
        "reviewer",
        "security_reviewer",
        "data_engineer",
        "domain_reasoner",
        "prompt_engineer",
        "knowledge_graph_rag",
        "ai_evaluation",
        "integration_connector",
        "deployment_sre",
        "evidence_auditor",
    }
)

# Component/content hashes are "sha256:" + 64 lowercase hex chars.
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class RegistryError(Exception):
    """Base class for agent-registry validation/lifecycle errors."""


class InvalidArchetype(RegistryError):
    pass


class InvalidHash(RegistryError):
    pass


class VersionLabelConflict(RegistryError):
    """Same ``(blueprint_id, version_label)`` already stores different content."""


class InstanceNotFound(RegistryError):
    pass


class InstanceRebindRejected(RegistryError):
    pass


def compute_content_hash(
    *,
    blueprint_id: uuid.UUID,
    version_label: str,
    model_route: str,
    component_hashes: dict[str, str],
) -> str:
    """Deterministic ``sha256:`` fingerprint over the full §22.2 pinning snapshot."""
    canonical = {
        "blueprint_id": str(blueprint_id),
        "version_label": version_label,
        "model_route": model_route,
        **{field: component_hashes[field] for field in COMPONENT_HASH_FIELDS},
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _require_sha256(field: str, value: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        raise InvalidHash(f"{field} must be a 'sha256:<64 hex>' fingerprint")


async def _reselect_version_by_content_hash(
    session: AsyncSession, content_hash: str
) -> AgentVersion | None:
    """Ladder rung 2: identical-content winner, if visible."""
    return (
        await session.execute(select(AgentVersion).where(AgentVersion.content_hash == content_hash))
    ).scalar_one_or_none()


async def _reselect_version_by_label(
    session: AsyncSession, blueprint_id: uuid.UUID, version_label: str
) -> AgentVersion | None:
    """Ladder rung 3: same label, different content if rung 2 missed."""
    return (
        await session.execute(
            select(AgentVersion).where(
                AgentVersion.blueprint_id == blueprint_id,
                AgentVersion.version_label == version_label,
            )
        )
    ).scalar_one_or_none()


async def _version_insert_id(session: AsyncSession, stmt) -> uuid.UUID | None:
    """Execute a version insert-returning statement. Patch point for P-GREEN-3c."""
    return (await session.execute(stmt)).scalar_one_or_none()


async def register_blueprint(
    session: AsyncSession,
    *,
    key: str,
    role: str,
    mission: str,
    archetype: str,
    actor: str,
) -> AgentBlueprint:
    """Register (or return existing) a GLOBAL agent blueprint. Admin path."""
    if archetype not in ARCHETYPES:
        raise InvalidArchetype(f"unknown archetype: {archetype!r}")
    existing = (
        await session.execute(select(AgentBlueprint).where(AgentBlueprint.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    stmt = (
        pg_insert(AgentBlueprint)
        .values(key=key, role=role, mission=mission, archetype=archetype)
        .on_conflict_do_nothing(constraint="uq_agent_blueprints_key")
        .returning(AgentBlueprint.id)
    )
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    if new_id is not None:
        return (
            await session.execute(select(AgentBlueprint).where(AgentBlueprint.id == new_id))
        ).scalar_one()
    winner = (
        await session.execute(select(AgentBlueprint).where(AgentBlueprint.key == key))
    ).scalar_one_or_none()
    if winner is None:
        raise ConcurrentWriteUnresolved("uq_agent_blueprints_key")
    return winner


async def register_version(
    session: AsyncSession,
    *,
    blueprint_id: uuid.UUID,
    version_label: str,
    model_route: str,
    prompt_hash: str,
    tool_policy_hash: str,
    context_policy_hash: str,
    eval_suite_hash: str,
    critical_dependencies_hash: str,
    output_schema_hash: str,
    actor: str,
) -> AgentVersion:
    """Register a GLOBAL, immutable agent version. Admin path; idempotent on content.

    Validates all six §22.2 component hashes, computes ``content_hash``, and returns
    the existing row if identical content was already registered (changed content
    yields a new version row — never a mutation).
    """
    component_hashes = {
        "prompt_hash": prompt_hash,
        "tool_policy_hash": tool_policy_hash,
        "context_policy_hash": context_policy_hash,
        "eval_suite_hash": eval_suite_hash,
        "critical_dependencies_hash": critical_dependencies_hash,
        "output_schema_hash": output_schema_hash,
    }
    for field in COMPONENT_HASH_FIELDS:
        _require_sha256(field, component_hashes[field])

    content_hash = compute_content_hash(
        blueprint_id=blueprint_id,
        version_label=version_label,
        model_route=model_route,
        component_hashes=component_hashes,
    )
    existing = (
        await session.execute(select(AgentVersion).where(AgentVersion.content_hash == content_hash))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    new_id = await _version_insert_id(
        session,
        pg_insert(AgentVersion)
        .values(
            blueprint_id=blueprint_id,
            version_label=version_label,
            model_route=model_route,
            content_hash=content_hash,
            **component_hashes,
        )
        .on_conflict_do_nothing()
        .returning(AgentVersion.id),
    )
    if new_id is not None:
        return (
            await session.execute(select(AgentVersion).where(AgentVersion.id == new_id))
        ).scalar_one()
    by_hash = await _reselect_version_by_content_hash(session, content_hash)
    if by_hash is not None:
        return by_hash
    by_label = await _reselect_version_by_label(session, blueprint_id, version_label)
    if by_label is not None:
        raise VersionLabelConflict("agent version label already registered with different content")
    raise ConcurrentWriteUnresolved(
        "uq_agent_versions_content_hash,uq_agent_versions_blueprint_id_version_label"
    )


class AgentInstanceRepository(TenantScopedRepository):
    """Tenant-scoped CRUD + lifecycle for ``agent_instances`` (audited)."""

    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, AgentInstance)

    async def instantiate(
        self,
        *,
        project_id: uuid.UUID,
        version_id: uuid.UUID,
        instance_key: str,
        actor: str,
    ) -> AgentInstance:
        instance = AgentInstance(
            project_id=project_id, version_id=version_id, instance_key=instance_key
        )
        await self.add(instance)  # stamps tenant_id
        await self.session.flush()
        await self._audit("agent_instance.registered", actor, instance)
        return instance

    async def bind_to_run(
        self, *, instance_id: uuid.UUID, run_id: uuid.UUID, actor: str
    ) -> AgentInstance:
        instance = await self._require(instance_id)
        if instance.active_run_id is not None and instance.active_run_id != run_id:
            # active_run_id is set-once (the DB trigger also rejects this).
            raise InstanceRebindRejected("active_run_id is set-once; create a new instance")
        instance.active_run_id = run_id
        instance.status = "active"
        await self.session.flush()
        await self._audit("agent_instance.bound", actor, instance)
        return instance

    async def suspend(self, *, instance_id: uuid.UUID, reason: str, actor: str) -> AgentInstance:
        instance = await self._require(instance_id)
        instance.status = "suspended"
        await self.session.flush()
        await self._audit("agent_instance.suspended", actor, instance)
        return instance

    async def retire(self, *, instance_id: uuid.UUID, actor: str) -> AgentInstance:
        instance = await self._require(instance_id)
        instance.status = "retired"
        await self.session.flush()
        await self._audit("agent_instance.retired", actor, instance)
        return instance

    async def _require(self, instance_id: uuid.UUID) -> AgentInstance:
        instance = await self.get(instance_id)
        if instance is None:
            raise InstanceNotFound(str(instance_id))
        return instance

    async def _audit(self, action: str, actor: str, instance: AgentInstance) -> None:
        # Safe metadata only — no prompt/body/tenant-content fields exist on the row.
        await audit_record(
            self.session,
            action=action,
            actor=actor,
            target=f"agent_instance:{instance.id}",
            payload={
                "instance_id": str(instance.id),
                "project_id": str(instance.project_id),
                "version_id": str(instance.version_id),
                "instance_key": instance.instance_key,
                "status": instance.status,
            },
        )
