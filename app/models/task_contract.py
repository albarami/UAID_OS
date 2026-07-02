"""``task_contracts`` + children — tenant-owned §27.2 task-contract store (Slice 42).

``task_contracts`` records who must build, against which FK-proven spine targets, under
which bounds — content is frozen at ``draft→ready_for_development`` (migration ``0041``
guard). ``task_contract_artifact_links`` (append-only, draft-only inserts) FK-pins the
§27.2 requirement/AC/oracle references to same-project ``intake_artifacts`` (existence by
composite FK; kind by DB guard). ``task_contract_reviewers`` (append-only, draft-only
inserts) is the §13.1 3-layer reviewer registry — the DB guard refuses any reviewer whose
ACTUAL blueprint (instance→version→blueprint) equals the builder's (§2.2).
``task_contract_events`` (append-only) is the transition trail: one row per creation
(``from_status`` NULL ⇔ ``to_status='draft'``) and per guarded transition. The §12.3
``spec:1207`` done-rule is enforced by the ``0041`` transition guard: ``done`` requires
every registration's OWN latest ``review_reports`` verdict to be ``approved``. Nothing
here executes or authorizes any work.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.review.task_contracts import (
    ARTIFACT_LINK_KINDS,
    MAX_DESCRIPTION,
    MAX_TASK_REF,
    MAX_TITLE,
    REVIEW_LAYERS,
    RISK_LEVELS,
)
from app.review.workflow import CONTRACT_STATUSES

_RISKS = ", ".join(repr(r) for r in RISK_LEVELS)
_STATUSES = ", ".join(repr(s) for s in CONTRACT_STATUSES)
_LAYERS = ", ".join(repr(la) for la in REVIEW_LAYERS)
_LINK_KINDS = ", ".join(repr(k) for k in ARTIFACT_LINK_KINDS)

# The Python str.strip() whitespace set as a Postgres E-literal (the Slice-41 pattern).
_TRIM = r"E' \t\n\r\x0b\x0c'"


def _bounded_required(column: str, cap: int) -> str:
    return f"char_length({column}) BETWEEN 1 AND {cap} AND btrim({column}, {_TRIM}) <> ''"


class TaskContract(Base):
    __tablename__ = "task_contracts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        ForeignKeyConstraint(
            ["builder_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            ondelete="RESTRICT",
            name="builder_project_tenant",
        ),
        CheckConstraint(f"risk_level IN ({_RISKS})", name="risk_level_valid"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_valid"),
        CheckConstraint(_bounded_required("task_ref", MAX_TASK_REF), name="task_ref_len"),
        CheckConstraint(_bounded_required("title", MAX_TITLE), name="title_len"),
        CheckConstraint(_bounded_required("description", MAX_DESCRIPTION), name="description_len"),
        UniqueConstraint("tenant_id", "project_id", "task_ref", name="uq_task_contracts_ref"),
        UniqueConstraint("id", "tenant_id", name="uq_task_contracts_id_tenant"),
        UniqueConstraint(
            "id", "project_id", "tenant_id", name="uq_task_contracts_id_project_tenant"
        ),
        Index("ix_task_contracts_project_status", "tenant_id", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_ref: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    must_have: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    must_not_do: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    required_evidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    definition_of_done: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    allowed_tools: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    forbidden_tools: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'")
    )
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    builder_instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class TaskContractArtifactLink(Base):
    __tablename__ = "task_contract_artifact_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            ondelete="RESTRICT",
            name="contract_project_tenant",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "project_id", "tenant_id"],
            ["intake_artifacts.id", "intake_artifacts.project_id", "intake_artifacts.tenant_id"],
            ondelete="RESTRICT",
            name="artifact_project_tenant",
        ),
        CheckConstraint(f"link_kind IN ({_LINK_KINDS})", name="link_kind_valid"),
        UniqueConstraint(
            "task_contract_id", "artifact_id", "link_kind", name="uq_tc_artifact_links_triple"
        ),
        Index("ix_tc_artifact_links_contract", "tenant_id", "task_contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    link_kind: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class TaskContractReviewer(Base):
    __tablename__ = "task_contract_reviewers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            ondelete="RESTRICT",
            name="contract_project_tenant",
        ),
        ForeignKeyConstraint(
            ["reviewer_instance_id", "project_id", "tenant_id"],
            ["agent_instances.id", "agent_instances.project_id", "agent_instances.tenant_id"],
            ondelete="RESTRICT",
            name="reviewer_project_tenant",
        ),
        CheckConstraint(f"layer IN ({_LAYERS})", name="layer_valid"),
        UniqueConstraint(
            "task_contract_id", "reviewer_instance_id", "layer", name="uq_tc_reviewers_triple"
        ),
        # The review_reports registration-FK target (report must bind to a registration).
        UniqueConstraint(
            "task_contract_id",
            "reviewer_instance_id",
            "layer",
            "project_id",
            "tenant_id",
            name="uq_tc_reviewers_registration",
        ),
        Index("ix_tc_reviewers_contract", "tenant_id", "task_contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    layer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class TaskContractEvent(Base):
    __tablename__ = "task_contract_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_contract_id", "project_id", "tenant_id"],
            ["task_contracts.id", "task_contracts.project_id", "task_contracts.tenant_id"],
            ondelete="RESTRICT",
            name="contract_project_tenant",
        ),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"],
            ["projects.id", "projects.tenant_id"],
            ondelete="RESTRICT",
            name="project_tenant",
        ),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUSES})", name="from_status_valid"
        ),
        CheckConstraint(f"to_status IN ({_STATUSES})", name="to_status_valid"),
        # The creation-event duality: exactly the creation row has no from_status.
        CheckConstraint("(from_status IS NULL) = (to_status = 'draft')", name="creation_duality"),
        CheckConstraint(_bounded_required("actor", 200), name="actor_len"),
        Index("ix_tc_events_contract", "tenant_id", "task_contract_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
