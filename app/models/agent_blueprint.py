"""``agent_blueprints`` — GLOBAL, reusable agent role identity (§9.3, §17.4).

Not tenant-owned (no ``tenant_id``, no RLS): reusable blueprints may be global
(§17.4). Admin-curated; the runtime role ``uaid_app`` gets ``SELECT`` only.

**Tenant-content boundary (invariant, §17.5):** global ``agent_blueprints`` and
``agent_versions`` may contain reusable role metadata and hashes only. They must
NOT contain tenant documents, tenant prompts, tenant code, project-specific
acceptance criteria, or tenant-identifying narrative. The schema can only enforce
this structurally (it exposes no prompt/body/document columns); keeping ``role``
and ``mission`` free of tenant prose is a curation responsibility, not something
the DB can detect.
"""

import uuid

from sqlalchemy import CheckConstraint, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AgentBlueprint(Base, TimestampMixin):
    __tablename__ = "agent_blueprints"
    __table_args__ = (CheckConstraint("status IN ('active', 'deprecated')", name="status_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Stable reusable slug (e.g. "domain_formula_verifier").
    key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    mission: Mapped[str] = mapped_column(String, nullable=False)
    # Validated app-side against the §9.5.1 archetype set (deny-by-default).
    archetype: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))
