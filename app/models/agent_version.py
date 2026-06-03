"""``agent_versions`` — GLOBAL, IMMUTABLE, content-hashed agent version (§9.7, §22.2).

Every agent version is immutable once created (a strict superset of §9.7's
"immutable once used in a delivery run" — changes always create a new version).
Immutability is DB-enforced by a ``BEFORE UPDATE OR DELETE`` row trigger and a
``BEFORE TRUNCATE`` statement trigger plus ``REVOKE UPDATE, DELETE, TRUNCATE`` —
see migration ``0007``. **Honest threat model:** this blocks ordinary DML for all
roles including the table owner, but a DB superuser/schema owner can still
``DISABLE TRIGGER`` or drop the table via privileged migration/admin paths — it is
DB-enforced for DML, not tamper-proof against privileged actors (same bar as the
audit log).

Stores the §22.2 pinning snapshot as **opaque hashes only** (never the prompt /
tool / context / eval / dependency / output-schema bodies), so this global table
holds no tenant-derived content (§17.5). The artifacts these hashes cover are
produced by the Phase-4 Agent Factory; here they are caller-supplied fingerprints.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The six §22.2 component-hash columns (model route is stored separately).
COMPONENT_HASH_FIELDS = (
    "prompt_hash",
    "tool_policy_hash",
    "context_policy_hash",
    "eval_suite_hash",
    "critical_dependencies_hash",
    "output_schema_hash",
)


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("blueprint_id", "version_label"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    blueprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_blueprints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_label: Mapped[str] = mapped_column(String, nullable=False)
    model_route: Mapped[str] = mapped_column(String, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String, nullable=False)
    tool_policy_hash: Mapped[str] = mapped_column(String, nullable=False)
    context_policy_hash: Mapped[str] = mapped_column(String, nullable=False)
    eval_suite_hash: Mapped[str] = mapped_column(String, nullable=False)
    critical_dependencies_hash: Mapped[str] = mapped_column(String, nullable=False)
    output_schema_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Deterministic sha256: fingerprint over (blueprint_id, version_label,
    # model_route, all six component hashes). Unique => idempotent re-registration.
    content_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Immutable: created_at only, no updated_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
