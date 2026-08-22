"""Tenant-owned Slice-58 hotfix-intent evaluation store. Not a healed system."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.ops.hotfix import (
    ACTION_COUNT,
    DIGEST_RE,
    EXECUTION_POSTURES,
    PLAN_KINDS,
    POLICY_DECISIONS,
    REASON_CODES,
    RULESET_VERSION,
)
from app.ops.hotfix_db_checks import CHILD_CHECK_CONSTRAINTS, DECISION_SNAPSHOT_SQL

_IN_KIND = ", ".join(repr(item) for item in PLAN_KINDS)
_IN_DEC = ", ".join(repr(item) for item in POLICY_DECISIONS)
_IN_POST = ", ".join(repr(item) for item in EXECUTION_POSTURES)
_IN_REASON = ", ".join(repr(item) for item in REASON_CODES)


class OpsSelfHealingRun(Base):
    """One hotfix-intent evaluation. Local plans only; not §26.6 closure."""

    __tablename__ = "ops_self_healing_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["incident_id", "project_id", "tenant_id"],
            ["ops_incidents.id", "ops_incidents.project_id", "ops_incidents.tenant_id"],
            ondelete="RESTRICT",
            name="incident_project_tenant",
        ),
        ForeignKeyConstraint(
            ["policy_id", "project_id", "tenant_id"],
            [
                "autonomy_policies.id",
                "autonomy_policies.project_id",
                "autonomy_policies.tenant_id",
            ],
            ondelete="RESTRICT",
            name="policy_project_tenant",
        ),
        ForeignKeyConstraint(
            ["rollback_verification_run_id", "project_id", "tenant_id"],
            [
                "rollback_verification_runs.id",
                "rollback_verification_runs.project_id",
                "rollback_verification_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="rollback_project_tenant",
        ),
        ForeignKeyConstraint(
            ["emergency_control_binding_id", "project_id", "tenant_id"],
            [
                "emergency_control_bindings.id",
                "emergency_control_bindings.project_id",
                "emergency_control_bindings.tenant_id",
            ],
            ondelete="RESTRICT",
            name="binding_project_tenant",
        ),
        ForeignKeyConstraint(
            ["emergency_rollback_authorization_id", "project_id", "tenant_id"],
            [
                "emergency_rollback_authorizations.id",
                "emergency_rollback_authorizations.project_id",
                "emergency_rollback_authorizations.tenant_id",
            ],
            ondelete="RESTRICT",
            name="authorization_project_tenant",
        ),
        CheckConstraint(f"ruleset_version='{RULESET_VERSION}'", name="ruleset_version"),
        CheckConstraint(f"action_count={ACTION_COUNT}", name="action_count"),
        CheckConstraint(
            "(policy_present IS TRUE AND policy_id IS NOT NULL "
            "AND autonomy_level_snapshot BETWEEN 0 AND 5) OR "
            "(policy_present IS FALSE AND policy_id IS NULL "
            "AND autonomy_level_snapshot IS NULL)",
            name="policy_presence",
        ),
        CheckConstraint(f"policy_input_digest ~ '{DIGEST_RE}'", name="policy_input_digest"),
        CheckConstraint(f"request_digest ~ '{DIGEST_RE}'", name="request_digest"),
        CheckConstraint(
            f"rollback_coverage_digest ~ '{DIGEST_RE}'", name="rollback_coverage_digest"
        ),
        CheckConstraint(DECISION_SNAPSHOT_SQL, name="decision_snapshot"),
        CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200 "
            "AND idempotency_key = btrim(idempotency_key)",
            name="idempotency_key",
        ),
        CheckConstraint(
            "emergency_rollback_authorization_id IS NULL "
            "OR emergency_control_binding_id IS NOT NULL",
            name="authorization_requires_binding",
        ),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_ops_self_healing_runs_id_project_tenant"
        ),
        UniqueConstraint(
            "id",
            "incident_id",
            "project_id",
            "tenant_id",
            name="uq_ops_self_healing_runs_id_incident_project_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "incident_id",
            "idempotency_key",
            name="uq_ops_self_healing_runs_idempotency",
        ),
        Index("ix_ops_self_healing_runs_latest", "tenant_id", "incident_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    action_count: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    autonomy_level_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    request_digest: Mapped[str] = mapped_column(Text, nullable=False)
    decision_snapshot: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_verification_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    emergency_control_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    emergency_rollback_authorization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    rollback_coverage_digest: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsHotfixPlan(Base):
    """Local A2 plan row. Not a git branch or GitHub PR."""

    __tablename__ = "ops_hotfix_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_self_healing_runs.id",
                "ops_self_healing_runs.incident_id",
                "ops_self_healing_runs.project_id",
                "ops_self_healing_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_incident_project_tenant",
        ),
        CheckConstraint(f"plan_kind IN ({_IN_KIND})", name="plan_kind"),
        CheckConstraint(
            "char_length(intended_ref) BETWEEN 1 AND 200 AND intended_ref = btrim(intended_ref)",
            name="intended_ref",
        ),
        UniqueConstraint("tenant_id", "run_id", "plan_kind", name="uq_ops_hotfix_plans_run_kind"),
        UniqueConstraint(
            "id",
            "run_id",
            "project_id",
            "tenant_id",
            "plan_kind",
            name="uq_ops_hotfix_plans_id_run_project_tenant_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    plan_kind: Mapped[str] = mapped_column(Text, nullable=False)
    intended_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class OpsSelfHealingResult(Base):
    """One seq 3–7 child. Policy-first; never an executed hotfix."""

    __tablename__ = "ops_self_healing_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "incident_id", "project_id", "tenant_id"],
            [
                "ops_self_healing_runs.id",
                "ops_self_healing_runs.incident_id",
                "ops_self_healing_runs.project_id",
                "ops_self_healing_runs.tenant_id",
            ],
            ondelete="RESTRICT",
            name="run_incident_project_tenant",
        ),
        ForeignKeyConstraint(
            ["plan_id", "run_id", "project_id", "tenant_id", "plan_kind"],
            [
                "ops_hotfix_plans.id",
                "ops_hotfix_plans.run_id",
                "ops_hotfix_plans.project_id",
                "ops_hotfix_plans.tenant_id",
                "ops_hotfix_plans.plan_kind",
            ],
            ondelete="RESTRICT",
            name="plan_kind_project_tenant",
        ),
        CheckConstraint(f"policy_decision IN ({_IN_DEC})", name="policy_decision"),
        CheckConstraint(f"execution_posture IN ({_IN_POST})", name="execution_posture"),
        CheckConstraint(f"reason_code IN ({_IN_REASON})", name="reason_code"),
        *[CheckConstraint(sql, name=name) for name, sql in CHILD_CHECK_CONSTRAINTS],
        UniqueConstraint("run_id", "seq", name="uq_ops_self_healing_results_run_seq"),
        UniqueConstraint("run_id", "action", name="uq_ops_self_healing_results_run_action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    matrix_action: Mapped[str] = mapped_column(Text, nullable=False)
    policy_decision: Mapped[str] = mapped_column(Text, nullable=False)
    execution_posture: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    plan_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
