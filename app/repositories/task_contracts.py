"""Tenant-scoped task-contract repository (Slice 42, §13.2/§27.2/§12.3).

``create`` stores a **draft** §27.2 contract (``project_id`` derived from the resolved
same-tenant builder instance — never caller input, the ``agent_failures`` pattern);
``add_artifact_link``/``add_reviewer`` assemble the FK-proven spine Sanad + the §2.2
blueprint-distinct 3-layer reviewer registry (draft-only; the ``0041`` guards are the
backstop). Transitions run the pure D-42-5 matrix, then UPDATE (the DB guard enforces the
freeze prerequisites and the per-registration DONE-GATE), then write one
``task_contract_events`` row + an audit entry (safe metadata only — never
title/description/list prose). ``review_status`` is **compute-on-read** (D-42-6) — no
write, non-authorizing. Nothing here performs a review or executes any work; every actor
label is UNTRUSTED. Run inside ``tenant_scope``.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record as audit_record
from app.models.agent_instance import AgentInstance
from app.models.agent_version import AgentVersion
from app.models.intake_artifact import IntakeArtifact
from app.models.review_report import ReviewReport
from app.models.task_contract import (
    TaskContract,
    TaskContractArtifactLink,
    TaskContractEvent,
    TaskContractReviewer,
)
from app.review.task_contracts import (
    ARTIFACT_LINK_KINDS,
    MAX_REVIEWERS,
    REVIEW_LAYERS,
    require_text,
    validate_artifact_link,
    validate_new_contract,
)
from app.review.workflow import (
    DoneGateDecision,
    RegistrationView,
    evaluate_done_gate,
    validate_transition,
)
from app.tenancy import TenantContext, TenantScopedRepository


class TaskContractRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, TaskContract)

    async def create(
        self,
        *,
        builder_instance_id: uuid.UUID,
        task_ref: str,
        title: str,
        description: str,
        must_have: Sequence[str],
        must_not_do: Sequence[str],
        required_evidence: Sequence[str],
        definition_of_done: Sequence[str],
        allowed_tools: Sequence[str],
        forbidden_tools: Sequence[str],
        risk_level: str,
        created_by: str,
    ) -> TaskContract:
        validate_new_contract(
            task_ref=task_ref,
            title=title,
            description=description,
            must_have=must_have,
            must_not_do=must_not_do,
            required_evidence=required_evidence,
            definition_of_done=definition_of_done,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            risk_level=risk_level,
        )
        require_text("created_by", created_by, 200)
        builder = await self._instance(builder_instance_id)
        if builder is None:
            raise ValueError(f"unknown builder instance for this tenant: {builder_instance_id}")
        contract = TaskContract(
            tenant_id=self.context.tenant_id,
            project_id=builder.project_id,
            task_ref=task_ref,
            title=title,
            description=description,
            must_have=list(must_have),
            must_not_do=list(must_not_do),
            required_evidence=list(required_evidence),
            definition_of_done=list(definition_of_done),
            allowed_tools=list(allowed_tools),
            forbidden_tools=list(forbidden_tools),
            risk_level=risk_level,
            builder_instance_id=builder.id,
        )
        self.session.add(contract)
        await self.session.flush()
        self.session.add(
            TaskContractEvent(
                tenant_id=self.context.tenant_id,
                project_id=contract.project_id,
                task_contract_id=contract.id,
                from_status=None,
                to_status="draft",
                actor=created_by,
            )
        )
        await self.session.flush()
        await audit_record(
            self.session,
            action="task_contract.created",
            actor=created_by,
            target=f"task_contract:{contract.id}",
            payload={
                "task_contract_id": str(contract.id),
                "project_id": str(contract.project_id),
                "builder_instance_id": str(builder.id),
                "task_ref": task_ref,
                "risk_level": risk_level,
                "status": "draft",
            },
        )
        return contract

    async def add_artifact_link(
        self,
        *,
        contract_id: uuid.UUID,
        link_kind: str,
        artifact_id: uuid.UUID,
        actor: str,
    ) -> TaskContractArtifactLink:
        validate_artifact_link(link_kind)
        require_text("actor", actor, 200)
        contract = await self._get_or_raise(contract_id)
        if contract.status != "draft":
            raise ValueError("contract is not draft (links are freeze-locked)")
        stmt = select(IntakeArtifact).where(
            IntakeArtifact.id == artifact_id,
            IntakeArtifact.tenant_id == self.context.tenant_id,
            IntakeArtifact.project_id == contract.project_id,
        )
        artifact = (await self.session.execute(stmt)).scalars().first()
        if artifact is None:
            raise ValueError(f"unknown artifact for this project: {artifact_id}")
        expected = ARTIFACT_LINK_KINDS[link_kind]
        if artifact.kind != expected:
            raise ValueError(
                f"artifact kind mismatch: link {link_kind!r} requires {expected!r}, "
                f"got {artifact.kind!r}"
            )
        link = TaskContractArtifactLink(
            tenant_id=self.context.tenant_id,
            project_id=contract.project_id,
            task_contract_id=contract.id,
            artifact_id=artifact.id,
            link_kind=link_kind,
        )
        self.session.add(link)
        await self.session.flush()
        await audit_record(
            self.session,
            action="task_contract.artifact_linked",
            actor=actor,
            target=f"task_contract:{contract.id}",
            payload={
                "task_contract_id": str(contract.id),
                "artifact_id": str(artifact.id),
                "link_kind": link_kind,
            },
        )
        return link

    async def add_reviewer(
        self,
        *,
        contract_id: uuid.UUID,
        reviewer_instance_id: uuid.UUID,
        layer: str,
        actor: str,
    ) -> TaskContractReviewer:
        if layer not in REVIEW_LAYERS:
            raise ValueError(f"unknown layer: {layer!r}")
        require_text("actor", actor, 200)
        contract = await self._get_or_raise(contract_id)
        if contract.status != "draft":
            raise ValueError("contract is not draft (reviewers are freeze-locked)")
        reviewer = await self._instance(reviewer_instance_id)
        if reviewer is None or reviewer.project_id != contract.project_id:
            raise ValueError(f"unknown reviewer instance for this project: {reviewer_instance_id}")
        builder_bp = await self._blueprint_of(contract.builder_instance_id)
        reviewer_bp = await self._blueprint_of(reviewer.id)
        if builder_bp == reviewer_bp:
            raise ValueError(
                "reviewer cannot share the builder blueprint (self-review, section 2.2)"
            )
        count_stmt = (
            select(func.count())
            .select_from(TaskContractReviewer)
            .where(
                TaskContractReviewer.tenant_id == self.context.tenant_id,
                TaskContractReviewer.task_contract_id == contract.id,
            )
        )
        if (await self.session.execute(count_stmt)).scalar_one() >= MAX_REVIEWERS:
            raise ValueError(f"too many reviewers (> {MAX_REVIEWERS})")
        registration = TaskContractReviewer(
            tenant_id=self.context.tenant_id,
            project_id=contract.project_id,
            task_contract_id=contract.id,
            reviewer_instance_id=reviewer.id,
            layer=layer,
        )
        self.session.add(registration)
        await self.session.flush()
        await audit_record(
            self.session,
            action="task_contract.reviewer_registered",
            actor=actor,
            target=f"task_contract:{contract.id}",
            payload={
                "task_contract_id": str(contract.id),
                "reviewer_instance_id": str(reviewer.id),
                "layer": layer,
            },
        )
        return registration

    # --- transitions (D-42-5; the 0041 guard is the authoritative backstop) ----------

    async def submit_for_development(self, contract_id: uuid.UUID, *, actor: str) -> TaskContract:
        return await self._transition(contract_id, "ready_for_development", actor, "frozen")

    async def start(self, contract_id: uuid.UUID, *, actor: str) -> TaskContract:
        return await self._transition(contract_id, "in_progress", actor, "started")

    async def submit_for_review(self, contract_id: uuid.UUID, *, actor: str) -> TaskContract:
        return await self._transition(contract_id, "specialist_review", actor, "submitted")

    async def request_changes(self, contract_id: uuid.UUID, *, actor: str) -> TaskContract:
        return await self._transition(contract_id, "changes_requested", actor, "changes_requested")

    async def complete(self, contract_id: uuid.UUID, *, actor: str) -> TaskContract:
        return await self._transition(contract_id, "done", actor, "completed")

    async def cancel(self, contract_id: uuid.UUID, *, actor: str) -> TaskContract:
        return await self._transition(contract_id, "canceled", actor, "canceled")

    async def supersede(self, contract_id: uuid.UUID, *, actor: str) -> TaskContract:
        return await self._transition(contract_id, "superseded", actor, "superseded")

    async def _transition(
        self, contract_id: uuid.UUID, new_status: str, actor: str, action: str
    ) -> TaskContract:
        require_text("actor", actor, 200)
        contract = await self._get_or_raise(contract_id)
        old_status = contract.status
        validate_transition(old_status, new_status)
        contract.status = new_status
        contract.updated_at = func.clock_timestamp()
        await self.session.flush()  # the 0041 guard (matrix/freeze/done-gate) fires here
        self.session.add(
            TaskContractEvent(
                tenant_id=self.context.tenant_id,
                project_id=contract.project_id,
                task_contract_id=contract.id,
                from_status=old_status,
                to_status=new_status,
                actor=actor,
            )
        )
        await self.session.flush()
        await audit_record(
            self.session,
            action=f"task_contract.{action}",
            actor=actor,
            target=f"task_contract:{contract.id}",
            payload={
                "task_contract_id": str(contract.id),
                "from_status": old_status,
                "to_status": new_status,
            },
        )
        return contract

    # --- reads -----------------------------------------------------------------------

    async def get(self, contract_id: uuid.UUID) -> TaskContract | None:
        stmt = select(TaskContract).where(
            TaskContract.tenant_id == self.context.tenant_id,
            TaskContract.id == contract_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_for_project(self, project_id: uuid.UUID) -> Sequence[TaskContract]:
        stmt = (
            select(TaskContract)
            .where(
                TaskContract.tenant_id == self.context.tenant_id,
                TaskContract.project_id == project_id,
            )
            .order_by(TaskContract.created_at.desc(), TaskContract.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def review_status(self, contract_id: uuid.UUID) -> DoneGateDecision:
        """Compute-on-read done-gate view (D-42-6) — the same rule the DB guard enforces."""
        regs_stmt = (
            select(TaskContractReviewer)
            .where(
                TaskContractReviewer.tenant_id == self.context.tenant_id,
                TaskContractReviewer.task_contract_id == contract_id,
            )
            .order_by(TaskContractReviewer.created_at, TaskContractReviewer.id)
        )
        registrations = (await self.session.execute(regs_stmt)).scalars().all()
        views: list[RegistrationView] = []
        for reg in registrations:
            latest_stmt = (
                select(ReviewReport.verdict)
                .where(
                    ReviewReport.tenant_id == self.context.tenant_id,
                    ReviewReport.task_contract_id == contract_id,
                    ReviewReport.reviewer_instance_id == reg.reviewer_instance_id,
                    ReviewReport.layer == reg.layer,
                )
                .order_by(ReviewReport.created_at.desc(), ReviewReport.id.desc())
                .limit(1)
            )
            verdict = (await self.session.execute(latest_stmt)).scalars().first()
            views.append(
                RegistrationView(
                    layer=reg.layer,
                    reviewer_ref=str(reg.reviewer_instance_id),
                    latest_verdict=verdict,
                )
            )
        return evaluate_done_gate(views)

    # --- internals ---------------------------------------------------------------------

    async def _get_or_raise(self, contract_id: uuid.UUID) -> TaskContract:
        contract = await self.get(contract_id)
        if contract is None:
            raise ValueError(f"unknown task contract for this tenant: {contract_id}")
        return contract

    async def _instance(self, instance_id: uuid.UUID) -> AgentInstance | None:
        stmt = select(AgentInstance).where(
            AgentInstance.id == instance_id,
            AgentInstance.tenant_id == self.context.tenant_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def _blueprint_of(self, instance_id: uuid.UUID) -> uuid.UUID:
        stmt = (
            select(AgentVersion.blueprint_id)
            .join(AgentInstance, AgentInstance.version_id == AgentVersion.id)
            .where(
                AgentInstance.id == instance_id,
                AgentInstance.tenant_id == self.context.tenant_id,
            )
        )
        return (await self.session.execute(stmt)).scalar_one()
