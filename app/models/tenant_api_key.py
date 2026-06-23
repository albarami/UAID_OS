"""``tenant_api_keys`` — GLOBAL auth-lookup table (Slice 10, §18.6 / D4; Slice 27 principal).

Maps a bearer API key (by its **hash only** — never the raw key) to a tenant **and** a verified
principal (Slice 27: `principal_subject` + `actor_type`). This is the pre-tenant request-auth lookup:
it must be readable WITHOUT a tenant GUC, so it is intentionally **NOT** RLS-tenant-scoped (like
`organizations`/`tenants`). Admin-issued/revoked; the runtime role `uaid_app` has **EXECUTE-only**
access to the `resolve_tenant_api_key` SECURITY DEFINER function and **no direct SELECT** on this
table (D4).

Stores no raw key and no tenant content — `key_hash` + `label` + `status` + `principal_subject` +
`actor_type`.
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
        # Slice 27: the verified principal this key represents (§23.4 human vs machine).
        CheckConstraint(
            "octet_length(principal_subject) BETWEEN 1 AND 255", name="principal_subject_bounded"
        ),
        CheckConstraint("actor_type IN ('human', 'service')", name="actor_type_valid"),
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
    # Slice 27: the principal bound to this key (resolved alongside tenant_id, never alone).
    principal_subject: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
