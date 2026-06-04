"""``tenant_api_keys`` — GLOBAL auth-lookup table (Slice 10, §18.6 / D4).

Maps a bearer API key (by its **hash only** — never the raw key) to a tenant. This
is the pre-tenant request-auth lookup: it must be readable WITHOUT a tenant GUC, so
it is intentionally **NOT** RLS-tenant-scoped (like `organizations`/`tenants`).
Admin-issued/revoked; the runtime role `uaid_app` gets `SELECT` only (resolve).

Stores no raw key and no tenant content — only `key_hash` + `label` + `status`.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TenantApiKey(Base, TimestampMixin):
    __tablename__ = "tenant_api_keys"
    __table_args__ = (
        CheckConstraint("key_hash ~ '^sha256:[0-9a-f]{64}$'", name="key_hash_format"),
        CheckConstraint("octet_length(label) BETWEEN 1 AND 255", name="label_bounded"),
        CheckConstraint("status IN ('active', 'revoked')", name="status_valid"),
        Index("ix_tenant_api_keys_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    # sha256:<64 lowercase hex> of the raw key — the raw key is NEVER stored.
    key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))
