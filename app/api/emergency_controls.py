"""Bodyless bearer-authenticated Slice-54 emergency-control API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api.auth import require_tenant
from app.release.emergency_control_service import (
    EmergencyControlConflict,
    EmergencyControlNotFound,
    EmergencyControlService,
)
from app.release.emergency_stop import EmergencyControlContractError
from app.repositories.emergency_controls import EmergencyControlRepositoryError
from app.tenancy import TenantContext, tenant_scope

router = APIRouter(prefix="/api", tags=["emergency-controls"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="emergency control not found"
)
_CONFLICT = HTTPException(
    status_code=status.HTTP_409_CONFLICT, detail="emergency control unavailable"
)


def _result(value) -> dict[str, object]:
    return {
        "binding_id": str(value.binding_id) if value.binding_id else None,
        "event_id": str(value.event_id) if value.event_id else None,
        "authorization_id": str(value.authorization_id) if value.authorization_id else None,
        "state": value.state,
        "reason_code": value.reason_code,
        "affected_run_count": value.affected_run_count,
    }


def _idempotency(value: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if value is None or not value.strip() or len(value.encode("utf-8")) > 128:
        raise _CONFLICT
    return value


async def _empty_body(request: Request) -> None:
    if (await request.body()).strip():
        raise _CONFLICT


async def _invoke(context: TenantContext, operation):
    try:
        async with tenant_scope(context) as session:
            return _result(await operation(EmergencyControlService(session, context)))
    except EmergencyControlNotFound:
        raise _NOT_FOUND from None
    except (
        EmergencyControlConflict,
        EmergencyControlRepositoryError,
        EmergencyControlContractError,
        IntegrityError,
        DBAPIError,
    ):
        raise _CONFLICT from None


@router.post("/projects/{project_id}/emergency-control/bind")
async def bind_emergency_control(
    project_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.bind(project_id=project_id, idempotency_key=idempotency_key),
    )


@router.post("/projects/{project_id}/emergency-stop/activate")
async def activate_emergency_stop(
    project_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.activate(project_id=project_id, idempotency_key=idempotency_key),
    )


@router.post("/projects/{project_id}/emergency-stop/clear")
async def clear_emergency_stop(
    project_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.clear(project_id=project_id, idempotency_key=idempotency_key),
    )


@router.post("/projects/{project_id}/emergency-rollback/authorize")
async def authorize_emergency_rollback(
    project_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.authorize_rollback(
            project_id=project_id, idempotency_key=idempotency_key
        ),
    )


@router.get("/projects/{project_id}/emergency-control/current")
async def current_emergency_control(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    return await _invoke(context, lambda service: service.current(project_id=project_id))
