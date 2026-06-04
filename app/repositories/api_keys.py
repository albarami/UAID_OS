"""Tenant API-key issuance + resolution (Slice 10, §18.6 / D4).

Issuance/revocation are **admin-path** (not HTTP): a raw key is generated server-side
with high entropy, only its ``sha256:`` hash is stored, and the raw key is returned
**once** (never persisted/logged/audited otherwise). Resolution is the runtime
pre-tenant lookup: it runs on a plain session (no GUC, since ``tenant_api_keys`` is a
global non-RLS auth table) and returns the tenant for an ACTIVE key, or ``None``.
"""

import hashlib
import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_api_key import TenantApiKey

_KEY_PREFIX = "uaidk_"


def generate_raw_key() -> str:
    """A high-entropy, URL-safe raw API key (256 bits). Shown to the caller once."""
    return _KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(raw_key: str) -> str:
    """``sha256:<64 lowercase hex>`` of the raw key — the form stored at rest."""
    return "sha256:" + hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class TenantApiKeyRepository:
    """Not tenant-scoped: the table is a global auth lookup (resolve runs pre-tenant)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def issue(self, *, tenant_id: uuid.UUID, label: str) -> tuple[str, TenantApiKey]:
        """Admin path: mint a key, store ONLY its hash, return ``(raw_key, row)`` once."""
        if not isinstance(label, str) or not (1 <= len(label.encode("utf-8")) <= 255):
            raise ValueError("label must be a 1..255-byte string")
        raw = generate_raw_key()
        row = TenantApiKey(tenant_id=tenant_id, key_hash=hash_key(raw), label=label)
        self.session.add(row)
        await self.session.flush()
        return raw, row

    async def revoke(self, *, key_id: uuid.UUID) -> None:
        await self.session.execute(
            update(TenantApiKey).where(TenantApiKey.id == key_id).values(status="revoked")
        )

    async def resolve(self, raw_key: str) -> uuid.UUID | None:
        """Runtime pre-tenant lookup: ACTIVE key hash → tenant_id, else None."""
        stmt = select(TenantApiKey.tenant_id).where(
            TenantApiKey.key_hash == hash_key(raw_key),
            TenantApiKey.status == "active",
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
