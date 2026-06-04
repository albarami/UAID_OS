"""Bearer API-key → TenantContext request auth (Slice 10, §18.6 / D4).

The single place untrusted HTTP input is resolved to a tenant. Deny-by-default:
a missing/malformed/unknown/revoked key ⇒ 401 with no fallback tenant. Resolution
runs on a plain (non-tenant-scoped) session because ``tenant_api_keys`` is a global
auth-lookup table; endpoints then open ``tenant_scope`` for the actual reads.
"""

from fastapi import Header, HTTPException, status

from app.db import get_sessionmaker
from app.repositories.api_keys import TenantApiKeyRepository
from app.tenancy import TenantContext

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid or missing API key",  # generic — no key-exists oracle
    headers={"WWW-Authenticate": "Bearer"},
)


def parse_bearer(authorization: str | None) -> str | None:
    """Extract a non-empty bearer token, or None if absent/malformed."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


async def require_tenant(authorization: str | None = Header(default=None)) -> TenantContext:
    """FastAPI dependency: resolve the bearer key to a TenantContext, or raise 401."""
    raw_key = parse_bearer(authorization)
    if raw_key is None:
        raise _UNAUTHORIZED
    # Pre-tenant lookup: plain session, no GUC (tenant_api_keys is global/non-RLS).
    async with get_sessionmaker()() as session:
        tenant_id = await TenantApiKeyRepository(session).resolve(raw_key)
    if tenant_id is None:
        raise _UNAUTHORIZED
    return TenantContext(tenant_id)
