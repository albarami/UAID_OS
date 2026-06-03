"""``agent_tool_allowlist`` — tenant-owned, append-only grant/revoke ledger.

Per-agent tool allowlist expressed as immutable events (no UPDATE/DELETE). An
agent may use a tool iff the LATEST event for (tenant, agent, tool) is `grant`.
This keeps allowlist changes auditable and history-preserving (§16.4).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentToolAllowlist(Base):
    __tablename__ = "agent_tool_allowlist"
    __table_args__ = (
        CheckConstraint("event_type IN ('grant', 'revoke')", name="event_type_valid"),
        Index(None, "tenant_id"),
        Index("ix_agent_tool_allowlist_lookup", "tenant_id", "agent_id", "tool_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Monotonic insertion order (now() is transaction-constant; UUIDs are random),
    # so the LATEST grant/revoke event is unambiguous even within one transaction.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
