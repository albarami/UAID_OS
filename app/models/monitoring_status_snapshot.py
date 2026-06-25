"""``monitoring_status_snapshots`` — tenant-owned, append-only monitoring/alerts evidence (Slice 31,
App. B #11 / §26.3 / §26.6).

One immutable row per observation of whether a project's declared monitoring provider reports **≥1 active
monitor AND ≥1 active alert rule** (the A5 gate-#11 evidence class). Append-only (migration ``0030``).
``target_ref`` is the full declared ``status_url`` (HTTPS, no userinfo/query/fragment, port 443, FQDN
host, bounded path) — the binding key (B2). **Read-state honesty (B4/B6) is DB-enforced:** a failed read
sets ``response_valid=false`` + a ``failure_kind`` + **NULL** counts (never fake zeros); a valid read
requires ``status=200`` + non-null counts + consistent active-booleans. Counts are ``0..32767`` (B7).
The connector is **unauthenticated-only** (no credential — B9). Verification-only — never enables go-live.
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The read-state honesty invariant (B4/B6), NULL-safe (IS [NOT] DISTINCT FROM) so an inconsistent row
# evaluates to FALSE — not NULL, which a CHECK would silently pass.
_READ_STATE_CK = """
(
  (response_valid AND provider_reachable
   AND observed_http_status IS NOT DISTINCT FROM 200 AND failure_kind IS NULL
   AND active_monitor_count IS NOT NULL AND active_alert_rule_count IS NOT NULL
   AND monitoring_active = (active_monitor_count >= 1)
   AND alerts_active = (active_alert_rule_count >= 1))
  OR
  (NOT response_valid AND failure_kind IS NOT NULL
   AND active_monitor_count IS NULL AND active_alert_rule_count IS NULL
   AND NOT monitoring_active AND NOT alerts_active
   AND (
     (failure_kind = 'unreachable' AND NOT provider_reachable AND observed_http_status IS NULL)
     OR (failure_kind = 'http_error' AND provider_reachable
         AND observed_http_status IS NOT NULL AND observed_http_status IS DISTINCT FROM 200)
     OR (failure_kind IN ('content_type','oversize','malformed') AND provider_reachable
         AND observed_http_status IS NOT DISTINCT FROM 200)
   ))
)
""".strip()


class MonitoringStatusSnapshot(Base):
    __tablename__ = "monitoring_status_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            "provenance IN ('caller_supplied_unverified','connector_verified')",
            name="ck_mss_provenance_valid",
        ),
        CheckConstraint("provider IN ('generic_monitoring_api')", name="ck_mss_provider_valid"),
        CheckConstraint("target_ref ~ '^https://'", name="ck_mss_target_ref_https"),
        CheckConstraint("target_ref !~ '[[:space:]@?#]'", name="ck_mss_target_ref_chars"),
        CheckConstraint("char_length(target_ref) BETWEEN 1 AND 2048", name="ck_mss_target_ref_len"),
        CheckConstraint(
            "target_ref !~* '(gh[opusr]_|github_pat_)'", name="ck_mss_target_ref_not_tokenish"
        ),
        CheckConstraint(
            "observed_http_status IS NULL OR (observed_http_status BETWEEN 100 AND 599)",
            name="ck_mss_http_status_range",
        ),
        CheckConstraint(
            "failure_kind IS NULL OR failure_kind IN "
            "('unreachable','http_error','content_type','oversize','malformed')",
            name="ck_mss_failure_kind_valid",
        ),
        CheckConstraint(
            "active_monitor_count IS NULL OR (active_monitor_count BETWEEN 0 AND 32767)",
            name="ck_mss_monitor_count_range",
        ),
        CheckConstraint(
            "active_alert_rule_count IS NULL OR (active_alert_rule_count BETWEEN 0 AND 32767)",
            name="ck_mss_alert_count_range",
        ),
        CheckConstraint(
            "overall_active = (monitoring_active AND alerts_active)",
            name="ck_mss_overall_invariant",
        ),
        CheckConstraint(_READ_STATE_CK, name="ck_mss_read_state"),
        Index(
            "ix_mss_tenant_project_target_created",
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
    target_ref: Mapped[str] = mapped_column(Text, nullable=False)
    provider_reachable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    failure_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_monitor_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    active_alert_rule_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    monitoring_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    alerts_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    overall_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'caller_supplied_unverified'")
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
