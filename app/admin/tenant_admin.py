"""Operator-path org/tenant administration (Slice 63).

Uses an admin session, sets the tenant GUC, writes the row plus
``tenant_admin_events``, and calls ``audit_append``. Provenance is
``operator_admin_session_unverified``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.rbac import OPERATOR_PROVENANCE, validate_admin_role, validate_principal
from app.audit import record as audit_record
from app.models.admin_policy import TenantAdminEvent
from app.models.admin_rbac import AdminRoleGrant
from app.models.organization import Organization
from app.models.tenant import Tenant


class TenantAdminError(ValueError):
    """Raised when an operator admin write cannot proceed."""


@dataclass(frozen=True)
class TenantAdminResult:
    """Safe identifier surface only — never keys or override values."""

    tenant_id: uuid.UUID
    event_id: uuid.UUID
    status: str
    grant_id: uuid.UUID | None = None


async def _bind_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantAdminError("tenant not found")
    return tenant


async def _record_event(
    session: AsyncSession,
    *,
    tenant: Tenant,
    event_kind: str,
    performed_by: str,
    subject_principal: str | None = None,
    admin_role: str | None = None,
    grant_id: uuid.UUID | None = None,
) -> TenantAdminEvent:
    event = TenantAdminEvent(
        tenant_id=tenant.id,
        organization_id=tenant.organization_id,
        event_kind=event_kind,
        subject_principal=subject_principal,
        admin_role=admin_role,
        admin_role_grant_id=grant_id,
        performed_by=performed_by,
        performed_by_provenance=OPERATOR_PROVENANCE,
    )
    session.add(event)
    await session.flush()
    return event


async def _audit(
    session: AsyncSession,
    *,
    action: str,
    performed_by: str,
    event: TenantAdminEvent,
    admin_role: str | None = None,
    subject_principal: str | None = None,
) -> None:
    payload = {
        "tenant_admin_event_id": str(event.id),
        "event_kind": event.event_kind,
    }
    if admin_role is not None:
        payload["admin_role"] = admin_role
    if subject_principal is not None:
        payload["subject_principal"] = subject_principal
    await audit_record(
        session,
        action=action,
        actor=performed_by,
        target=f"tenant:{event.tenant_id}",
        payload=payload,
    )


async def grant_admin_role(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    principal_subject: str,
    admin_role: str,
    performed_by: str,
) -> TenantAdminResult:
    """Insert an active grant and a ``role_granted`` event."""
    principal = validate_principal(principal_subject, field="principal_subject")
    role = validate_admin_role(admin_role)
    operator = validate_principal(performed_by, field="performed_by", max_len=200)
    tenant = await _bind_tenant(session, tenant_id)
    grant = AdminRoleGrant(
        tenant_id=tenant.id,
        principal_subject=principal,
        admin_role=role,
        status="active",
        granted_by=operator,
        granted_by_provenance=OPERATOR_PROVENANCE,
    )
    session.add(grant)
    await session.flush()
    event = await _record_event(
        session,
        tenant=tenant,
        event_kind="role_granted",
        performed_by=operator,
        subject_principal=principal,
        admin_role=role,
        grant_id=grant.id,
    )
    await _audit(
        session,
        action="admin_role.granted",
        performed_by=operator,
        event=event,
        admin_role=role,
        subject_principal=principal,
    )
    return TenantAdminResult(
        tenant_id=tenant.id, event_id=event.id, status=grant.status, grant_id=grant.id
    )


async def revoke_admin_role(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    principal_subject: str,
    admin_role: str,
    performed_by: str,
) -> TenantAdminResult:
    """One-way revoke of an active grant."""
    principal = validate_principal(principal_subject, field="principal_subject")
    role = validate_admin_role(admin_role)
    operator = validate_principal(performed_by, field="performed_by", max_len=200)
    tenant = await _bind_tenant(session, tenant_id)
    stmt = select(AdminRoleGrant).where(
        AdminRoleGrant.tenant_id == tenant.id,
        AdminRoleGrant.principal_subject == principal,
        AdminRoleGrant.admin_role == role,
        AdminRoleGrant.status == "active",
    )
    grant = (await session.execute(stmt)).scalar_one_or_none()
    if grant is None:
        raise TenantAdminError("no active grant to revoke")
    grant.status = "revoked"
    await session.flush()
    event = await _record_event(
        session,
        tenant=tenant,
        event_kind="role_revoked",
        performed_by=operator,
        subject_principal=principal,
        admin_role=role,
        grant_id=grant.id,
    )
    await _audit(
        session,
        action="admin_role.revoked",
        performed_by=operator,
        event=event,
        admin_role=role,
        subject_principal=principal,
    )
    return TenantAdminResult(
        tenant_id=tenant.id, event_id=event.id, status=grant.status, grant_id=grant.id
    )


async def suspend_tenant(
    session: AsyncSession, *, tenant_id: uuid.UUID, performed_by: str
) -> TenantAdminResult:
    """Set ``tenants.status='suspended'`` and record the event."""
    return await _set_tenant_status(
        session, tenant_id=tenant_id, performed_by=performed_by, status="suspended"
    )


async def reinstate_tenant(
    session: AsyncSession, *, tenant_id: uuid.UUID, performed_by: str
) -> TenantAdminResult:
    """Set ``tenants.status='active'`` and record the event."""
    return await _set_tenant_status(
        session, tenant_id=tenant_id, performed_by=performed_by, status="active"
    )


async def _set_tenant_status(
    session: AsyncSession, *, tenant_id: uuid.UUID, performed_by: str, status: str
) -> TenantAdminResult:
    operator = validate_principal(performed_by, field="performed_by", max_len=200)
    tenant = await _bind_tenant(session, tenant_id)
    tenant.status = status
    await session.flush()
    kind = "tenant_suspended" if status == "suspended" else "tenant_reinstated"
    event = await _record_event(
        session, tenant=tenant, event_kind=kind, performed_by=operator
    )
    await _audit(
        session,
        action="tenant.suspended" if status == "suspended" else "tenant.reinstated",
        performed_by=operator,
        event=event,
    )
    return TenantAdminResult(tenant_id=tenant.id, event_id=event.id, status=status)


async def suspend_organization(
    session: AsyncSession, *, organization_id: uuid.UUID, performed_by: str
) -> tuple[TenantAdminResult, ...]:
    """Suspend an organization and emit one event per tenant."""
    return await _set_org_status(
        session,
        organization_id=organization_id,
        performed_by=performed_by,
        status="suspended",
    )


async def reinstate_organization(
    session: AsyncSession, *, organization_id: uuid.UUID, performed_by: str
) -> tuple[TenantAdminResult, ...]:
    """Reinstate an organization and emit one event per tenant."""
    return await _set_org_status(
        session,
        organization_id=organization_id,
        performed_by=performed_by,
        status="active",
    )


async def _set_org_status(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    performed_by: str,
    status: str,
) -> tuple[TenantAdminResult, ...]:
    operator = validate_principal(performed_by, field="performed_by", max_len=200)
    org = await session.get(Organization, organization_id)
    if org is None:
        raise TenantAdminError("organization not found")
    await session.execute(
        update(Organization).where(Organization.id == organization_id).values(status=status)
    )
    tenants = (
        await session.execute(select(Tenant).where(Tenant.organization_id == organization_id))
    ).scalars().all()
    if not tenants:
        raise TenantAdminError("organization has no tenants")
    kind = (
        "organization_suspended" if status == "suspended" else "organization_reinstated"
    )
    action = (
        "organization.suspended" if status == "suspended" else "organization.reinstated"
    )
    results: list[TenantAdminResult] = []
    for tenant in tenants:
        await _bind_tenant(session, tenant.id)
        event = await _record_event(
            session, tenant=tenant, event_kind=kind, performed_by=operator
        )
        await _audit(session, action=action, performed_by=operator, event=event)
        results.append(
            TenantAdminResult(tenant_id=tenant.id, event_id=event.id, status=status)
        )
    return tuple(results)
