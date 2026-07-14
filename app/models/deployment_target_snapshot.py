"""``deployment_target_snapshots`` — tenant-owned, append-only deployment-target evidence (Slice 30,
App. B #2 / §5.2 / §26.3).

One immutable row per observation of whether a project's declared production deploy **target is
available** (the A5 gate-#2 evidence class). Append-only: SELECT/INSERT only for the runtime role, with
UPDATE/DELETE/TRUNCATE blocked by triggers (migration ``0029``). ``provenance`` is two-tier
(``caller_supplied_unverified`` | ``connector_verified``). A ``connector_verified`` row is written for
every safely-attempted probe — **positive when serving, verified-negative when unavailable** — so the
latest-wins gate cannot keep a stale passing snapshot active. The **invariant**
``target_available = (provisioned AND reachable)`` is a column CHECK (DB-authoritative). Verification-only
— this never deploys, never authorizes production deploy (A4/A5), never enables go-live.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Strict FQDN (Postgres POSIX regex; ``[.]`` for a literal dot — unambiguous under
# standard_conforming_strings). Rejects IP literals (numeric TLD), single-label hosts, schemes/ports/creds.
_FQDN_SQL = r"^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?[.])+[A-Za-z]{2,63}$"


class DeploymentTargetSnapshot(Base):
    __tablename__ = "deployment_target_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name="ck_dts_provenance_valid",
        ),
        CheckConstraint("provider IN ('generic_https')", name="ck_dts_provider_valid"),
        CheckConstraint("environment IN ('production','staging')", name="ck_dts_environment_valid"),
        CheckConstraint(f"target_ref ~ '{_FQDN_SQL}'", name="ck_dts_target_ref_fqdn"),
        CheckConstraint("char_length(target_ref) BETWEEN 1 AND 253", name="ck_dts_target_ref_len"),
        CheckConstraint(
            "target_ref !~* '(gh[opusr]_|github_pat_)'", name="ck_dts_target_ref_not_tokenish"
        ),
        CheckConstraint(
            "observed_http_status IS NULL OR (observed_http_status BETWEEN 100 AND 599)",
            name="ck_dts_http_status_range",
        ),
        # B-30-6 invariant: target_available iff provisioned AND reachable.
        CheckConstraint(
            "target_available = (provisioned AND reachable)", name="ck_dts_available_invariant"
        ),
        UniqueConstraint("id", "project_id", "tenant_id", name="uq_dts_id_project_tenant"),
        Index(
            "ix_dts_tenant_project_target_created",
            "tenant_id",
            "project_id",
            "provider",
            "target_ref",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    environment: Mapped[str] = mapped_column(Text, nullable=False)
    target_ref: Mapped[str] = mapped_column(Text, nullable=False)
    reachable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provisioned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    target_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
