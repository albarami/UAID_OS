"""Operator CLI for Slice 63 tenant/org administration.

Prints ids and status only. Never prints keys or override values.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.admin.tenant_admin import (
    grant_admin_role,
    reinstate_organization,
    reinstate_tenant,
    revoke_admin_role,
    suspend_organization,
    suspend_tenant,
)
from app.config import settings


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="admin_roles")
    sub = parser.add_subparsers(dest="command", required=True)
    grant = sub.add_parser("grant")
    grant.add_argument("--tenant-id", type=_uuid, required=True)
    grant.add_argument("--principal", required=True)
    grant.add_argument("--role", required=True)
    grant.add_argument("--performed-by", required=True)
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--tenant-id", type=_uuid, required=True)
    revoke.add_argument("--principal", required=True)
    revoke.add_argument("--role", required=True)
    revoke.add_argument("--performed-by", required=True)
    suspend_t = sub.add_parser("suspend-tenant")
    suspend_t.add_argument("--tenant-id", type=_uuid, required=True)
    suspend_t.add_argument("--performed-by", required=True)
    reinstate_t = sub.add_parser("reinstate-tenant")
    reinstate_t.add_argument("--tenant-id", type=_uuid, required=True)
    reinstate_t.add_argument("--performed-by", required=True)
    suspend_o = sub.add_parser("suspend-org")
    suspend_o.add_argument("--organization-id", type=_uuid, required=True)
    suspend_o.add_argument("--performed-by", required=True)
    reinstate_o = sub.add_parser("reinstate-org")
    reinstate_o.add_argument("--organization-id", type=_uuid, required=True)
    reinstate_o.add_argument("--performed-by", required=True)
    return parser


def _print_result(result) -> None:
    print(result.tenant_id)
    print(result.event_id)
    print(result.status)
    if result.grant_id is not None:
        print(result.grant_id)


async def _run(args: argparse.Namespace) -> None:
    engine = create_async_engine(settings.admin_database_url)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                if args.command == "grant":
                    _print_result(
                        await grant_admin_role(
                            session,
                            tenant_id=args.tenant_id,
                            principal_subject=args.principal,
                            admin_role=args.role,
                            performed_by=args.performed_by,
                        )
                    )
                elif args.command == "revoke":
                    _print_result(
                        await revoke_admin_role(
                            session,
                            tenant_id=args.tenant_id,
                            principal_subject=args.principal,
                            admin_role=args.role,
                            performed_by=args.performed_by,
                        )
                    )
                elif args.command == "suspend-tenant":
                    _print_result(
                        await suspend_tenant(
                            session,
                            tenant_id=args.tenant_id,
                            performed_by=args.performed_by,
                        )
                    )
                elif args.command == "reinstate-tenant":
                    _print_result(
                        await reinstate_tenant(
                            session,
                            tenant_id=args.tenant_id,
                            performed_by=args.performed_by,
                        )
                    )
                elif args.command == "suspend-org":
                    for result in await suspend_organization(
                        session,
                        organization_id=args.organization_id,
                        performed_by=args.performed_by,
                    ):
                        _print_result(result)
                elif args.command == "reinstate-org":
                    for result in await reinstate_organization(
                        session,
                        organization_id=args.organization_id,
                        performed_by=args.performed_by,
                    ):
                        _print_result(result)
    finally:
        await engine.dispose()


def main() -> None:
    """Parse argv and run the matching operator command."""
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
