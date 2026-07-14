"""Narrow bearer-authenticated Slice-53 production pre-approval API.

Request bodies are deliberately absent.  Identity comes only from ``require_tenant``; current release
and policy bindings come only from the service.  Responses contain safe IDs, timestamps/status codes
only and expose no principal, policy, evidence, or authority claim.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api.auth import require_tenant
from app.release.production_approval import ProductionApprovalContractError
from app.release.production_approval_service import (
    ProductionApprovalService,
    ProductionPreapprovalConflict,
    ProductionPreapprovalNotFound,
)
from app.repositories.production_preapprovals import ProductionPreapprovalRepositoryError
from app.tenancy import TenantContext, tenant_scope

router = APIRouter(prefix="/api", tags=["production-preapprovals"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="production preapproval not found"
)
_CONFLICT = HTTPException(
    status_code=status.HTTP_409_CONFLICT, detail="production preapproval unavailable"
)


def _result(value) -> dict[str, str | None]:
    return {
        "request_id": str(value.request_id),
        "attestation_id": str(value.attestation_id) if value.attestation_id else None,
        "status": value.status,
        "reason_code": value.reason_code,
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
            return _result(await operation(ProductionApprovalService(session, context)))
    except ProductionPreapprovalNotFound:
        raise _NOT_FOUND from None
    except (
        ProductionPreapprovalConflict,
        ProductionPreapprovalRepositoryError,
        ProductionApprovalContractError,
        IntegrityError,
        DBAPIError,
    ):
        raise _CONFLICT from None


@router.post("/projects/{project_id}/production-preapprovals/requests")
async def request_production_preapproval(
    project_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.request(
            project_id=project_id, idempotency_key=idempotency_key
        ),
    )


@router.post("/projects/{project_id}/production-preapprovals/{request_id}/approve")
async def approve_production_preapproval(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.approve(
            project_id=project_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
        ),
    )


@router.post("/projects/{project_id}/production-preapprovals/{request_id}/reject")
async def reject_production_preapproval(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.reject(
            project_id=project_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
        ),
    )


@router.post("/projects/{project_id}/production-preapprovals/{request_id}/cancel")
async def cancel_production_preapproval(
    project_id: uuid.UUID,
    request_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.cancel(
            project_id=project_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
        ),
    )


@router.post("/projects/{project_id}/production-preapprovals/{attestation_id}/revoke")
async def revoke_production_preapproval(
    project_id: uuid.UUID,
    attestation_id: uuid.UUID,
    idempotency_key: str = Depends(_idempotency),
    _body: None = Depends(_empty_body),
    context: TenantContext = Depends(require_tenant),
) -> dict:
    return await _invoke(
        context,
        lambda service: service.revoke(
            project_id=project_id,
            attestation_id=attestation_id,
            idempotency_key=idempotency_key,
        ),
    )


@router.get("/projects/{project_id}/production-preapprovals/current")
async def current_production_preapproval(
    project_id: uuid.UUID, context: TenantContext = Depends(require_tenant)
) -> dict:
    return await _invoke(
        context, lambda service: service.current(project_id=project_id)
    )
