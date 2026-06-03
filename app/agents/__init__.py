"""Agent registry (Slice 6, §9.7 / §17.4 / §22.2)."""

from app.agents.registry import (
    ARCHETYPES,
    AgentInstanceRepository,
    InstanceNotFound,
    InstanceRebindRejected,
    InvalidArchetype,
    InvalidHash,
    RegistryError,
    compute_content_hash,
    register_blueprint,
    register_version,
)

__all__ = [
    "ARCHETYPES",
    "AgentInstanceRepository",
    "InstanceNotFound",
    "InstanceRebindRejected",
    "InvalidArchetype",
    "InvalidHash",
    "RegistryError",
    "compute_content_hash",
    "register_blueprint",
    "register_version",
]
