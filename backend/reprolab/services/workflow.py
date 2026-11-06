"""Transactional service layer for Stage 4 analysis-only LangGraph workflows.

Coordinates LangGraph state transitions with Stage 3 governed role assignments,
constitution snapshots, deliverables, append-only workflow checkpoints/events,
and bounded model-call audit logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.core.config import Settings, get_settings
from reprolab.governance.contracts import ROLE_MAX_MODEL_CALLS
from reprolab.models.governance import AssignmentDeliverable, RoleAssignment
from reprolab.models.records import FindingVersion
from reprolab.models.reports import ReportVersion
from reprolab.models.research import Claim, EvidenceItem, EvidenceReview, Investigation, ProtocolVersion
from reprolab.models.workflow import (
    WorkflowCheckpoint,
    WorkflowEvent,
    WorkflowModelCall,
    WorkflowRun,
)
from reprolab.schemas.governance import (
    AbstentionOutput,
    AbstentionReason,
    AssignmentBudget,
    AssignmentCreate,
    AssignmentStatus,
    AssignmentTransitionRequest,
    DeliverableCreate,
    DeliverableKind,
    GovernanceReference,
    ManualDeliverableContent,
    ReferenceKind,
    canonical_json_hash,
)
from reprolab.schemas.records import AttributionInput
from reprolab.schemas.workflow import (
    CheckpointStageStatus,
    GateDecision,
    WorkflowCancelRequest,
    WorkflowEventType,
    WorkflowGateDecisionRequest,
    WorkflowNode,
    WorkflowResumeRequest,
    WorkflowRunCreate,
    WorkflowStatus,
)
from reprolab.evaluation.engine import run_scientific_evaluation
from reprolab.models.execution import AttemptRecord, ExperimentJob, ProductionMeasurement
from reprolab.schemas.execution import ExperimentJobCreate
from reprolab.services.execution import submit_and_run_experiment_job
from reprolab.services.governance import (
    _registered_snapshot,
    create_assignment as _governed_create_assignment,
    create_attribution as _governed_create_attribution,
    create_deliverable as _governed_create_deliverable,
    transition_assignment as _governed_transition_assignment,
)
from reprolab.storage.local import LocalPrivateStorage
from reprolab.workflow.graph import (
    AnalysisNodeSpec,
    AnalysisWorkflowState,
    NODE_SPECS,
    ORDERED_NODES,
    ORDERED_REPRODUCTION_NODES,
    REPRODUCTION_NODE_SPECS,
    build_analysis_workflow_graph,
    build_reproduction_workflow_graph,
)
from reprolab.workflow.provider import (
    CONDITIONAL_REPRODUCTION_ROLES,
    DETERMINISTIC_REPRODUCTION_ROLES,
    DETERMINISTIC_STAGE4_ROLES,
    WorkflowModelAdapter,
    assert_reproduction_role_and_tool_allowed,
    assert_stage4_role_and_tool_allowed,
    execute_governed_model_step,
)


_create_assignment_in_tx = _governed_create_assignment.__wrapped__
_transition_assignment_in_tx = _governed_transition_assignment.__wrapped__
_create_deliverable_in_tx = _governed_create_deliverable.__wrapped__


def _atomic_workflow_mutation(operation):
    """Wrap a workflow service operation in an atomic commit/rollback boundary."""

    @wraps(operation)
    async def wrapped(db: AsyncSession, *args, **kwargs):
        try:
            result = await operation(db, *args, **kwargs)
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            raise _conflict("Workflow mutation conflicts with stored record integrity.") from exc
        except (ValidationError, ValueError) as exc:
            await db.rollback()
            raise _conflict(f"Workflow operation failed contract validation: {exc}") from exc
        except BaseException:
            await db.rollback()
            raise

    return wrapped


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _investigation_or_404(db: AsyncSession, investigation_id: str) -> Investigation:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("Investigation not found.")
    return investigation


async def _workflow_run_or_404(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
    *,
    lock: bool = False,
) -> WorkflowRun:
    statement = select(WorkflowRun).where(
        WorkflowRun.id == run_id,
        WorkflowRun.investigation_id == investigation_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    run = await db.scalar(statement)
    if run is None:
        raise _not_found("Workflow run not found in this investigation.")
    return run


def _checkpoint_hash(
    *,
    workflow_run_id: str,
    investigation_id: str,
    sequence_number: int,
    node_name: str,
    stage_status: str,
    role_id: str | None,
    assignment_id: str | None,
    deliverable_id: str | None,
    state_hash: str,
    previous_checkpoint_hash: str | None,
    created_at: datetime,
) -> str:
    return canonical_json_hash(
        {
            "workflow_run_id": workflow_run_id,
            "investigation_id": investigation_id,
            "sequence_number": sequence_number,
            "node_name": node_name,
            "stage_status": stage_status,
            "role_id": role_id,
            "assignment_id": assignment_id,
            "deliverable_id": deliverable_id,
            "state_hash": state_hash,
            "previous_checkpoint_hash": previous_checkpoint_hash,
            "created_at": _as_utc(created_at).isoformat(),
        }
    )


def _workflow_event_hash(
    *,
    workflow_run_id: str,
    investigation_id: str,
    sequence_number: int,
    event_type: str,
    node_name: str,
    role_id: str | None,
    attribution_id: str,
    reason: str | None,
    payload: dict[str, Any],
    previous_event_hash: str | None,
    occurred_at: datetime,
) -> str:
    return canonical_json_hash(
        {
            "workflow_run_id": workflow_run_id,
            "investigation_id": investigation_id,
            "sequence_number": sequence_number,
            "event_type": event_type,
            "node_name": node_name,
            "role_id": role_id,
            "attribution_id": attribution_id,
            "reason": reason,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "occurred_at": _as_utc(occurred_at).isoformat(),
        }
    )


async def _append_workflow_checkpoint(
    db: AsyncSession,
    workflow_run: WorkflowRun,
    *,
    node_name: str,
    stage_status: str,
    role_id: str | None,
    assignment_id: str | None,
    deliverable_id: str | None,
    state_json: dict[str, Any],
) -> WorkflowCheckpoint:
    sequence_number = int(
        await db.scalar(
            select(func.max(WorkflowCheckpoint.sequence_number)).where(
                WorkflowCheckpoint.workflow_run_id == workflow_run.id
            )
        )
        or 0
    ) + 1
    previous_checkpoint_hash = workflow_run.latest_checkpoint_hash
    created_at = _now()
    state_hash = canonical_json_hash(state_json)
    checkpoint_hash = _checkpoint_hash(
        workflow_run_id=workflow_run.id,
        investigation_id=workflow_run.investigation_id,
        sequence_number=sequence_number,
        node_name=node_name,
        stage_status=stage_status,
        role_id=role_id,
        assignment_id=assignment_id,
        deliverable_id=deliverable_id,
        state_hash=state_hash,
        previous_checkpoint_hash=previous_checkpoint_hash,
        created_at=created_at,
    )
    checkpoint = WorkflowCheckpoint(
        id=str(uuid4()),
        workflow_run_id=workflow_run.id,
        investigation_id=workflow_run.investigation_id,
        sequence_number=sequence_number,
        node_name=node_name,
        stage_status=stage_status,
        role_id=role_id,
        assignment_id=assignment_id,
        deliverable_id=deliverable_id,
        state_json=state_json,
        state_hash=state_hash,
        previous_checkpoint_hash=previous_checkpoint_hash,
        checkpoint_hash=checkpoint_hash,
        created_at=created_at,
    )
    db.add(checkpoint)
    workflow_run.latest_checkpoint_seq = sequence_number
    workflow_run.latest_checkpoint_hash = checkpoint_hash
    workflow_run.updated_at = created_at
    await db.flush()
    return checkpoint


async def _append_workflow_event(
    db: AsyncSession,
    workflow_run: WorkflowRun,
    *,
    event_type: str,
    node_name: str,
    role_id: str | None,
    attribution_id: str,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> WorkflowEvent:
    sequence_number = int(
        await db.scalar(
            select(func.max(WorkflowEvent.sequence_number)).where(
                WorkflowEvent.workflow_run_id == workflow_run.id
            )
        )
        or 0
    ) + 1
    previous_event_hash = workflow_run.latest_event_hash
    occurred_at = _now()
    event_payload = payload or {}
    event_hash = _workflow_event_hash(
        workflow_run_id=workflow_run.id,
        investigation_id=workflow_run.investigation_id,
        sequence_number=sequence_number,
        event_type=event_type,
        node_name=node_name,
        role_id=role_id,
        attribution_id=attribution_id,
        reason=reason,
        payload=event_payload,
        previous_event_hash=previous_event_hash,
        occurred_at=occurred_at,
    )
    event = WorkflowEvent(
        id=str(uuid4()),
        workflow_run_id=workflow_run.id,
        investigation_id=workflow_run.investigation_id,
        sequence_number=sequence_number,
        event_type=event_type,
        node_name=node_name,
        role_id=role_id,
        attribution_id=attribution_id,
        reason=reason,
        payload=event_payload,
        previous_event_hash=previous_event_hash,
        event_hash=event_hash,
        occurred_at=occurred_at,
    )
    db.add(event)
    workflow_run.latest_event_hash = event_hash
    workflow_run.updated_at = occurred_at
    await db.flush()
    return event


async def _load_investigation_context(
    db: AsyncSession,
    investigation_id: str,
) -> dict[str, Any]:
    claims = list(
        (
            await db.scalars(
                select(Claim)
                .where(Claim.investigation_id == investigation_id)
                .order_by(Claim.created_at.asc(), Claim.id.asc())
            )
        ).all()
    )
    evidence_items = list(
        (
            await db.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.investigation_id == investigation_id)
                .order_by(EvidenceItem.created_at.asc(), EvidenceItem.id.asc())
            )
        ).all()
    )
    accepted_evidence_ids: list[str] = []
    for ev in evidence_items:
        if ev.verification_status == "manually_reviewed":
            accepted_evidence_ids.append(ev.id)
            continue
        accepted_review = await db.scalar(
            select(EvidenceReview.id)
            .where(
                EvidenceReview.evidence_item_id == ev.id,
                EvidenceReview.outcome == "accepted_for_protocol",
            )
            .limit(1)
        )
        if accepted_review is not None:
            accepted_evidence_ids.append(ev.id)

    protocols = list(
        (
            await db.scalars(
                select(ProtocolVersion)
                .where(ProtocolVersion.investigation_id == investigation_id)
                .order_by(ProtocolVersion.version_number.asc(), ProtocolVersion.id.asc())
            )
        ).all()
    )
    finding_versions = list(
        (
            await db.scalars(
                select(FindingVersion)
                .where(FindingVersion.investigation_id == investigation_id)
                .order_by(FindingVersion.version_number.asc(), FindingVersion.id.asc())
            )
        ).all()
    )
    report_versions = list(
        (
            await db.scalars(
                select(ReportVersion)
                .where(ReportVersion.investigation_id == investigation_id)
                .order_by(ReportVersion.version_number.asc(), ReportVersion.id.asc())
            )
        ).all()
    )
    return {
        "claims": claims,
        "evidence_items": evidence_items,
        "accepted_evidence_ids": accepted_evidence_ids,
        "protocols": protocols,
        "finding_versions": finding_versions,
        "report_versions": report_versions,
    }


async def _build_input_references(
    db: AsyncSession,
    investigation_id: str,
    context: dict[str, Any],
    node_deliverables: dict[str, str],
) -> list[GovernanceReference]:
    refs: list[GovernanceReference] = [
        GovernanceReference(kind=ReferenceKind.INVESTIGATION, id=investigation_id)
    ]
    for claim in context["claims"][:10]:
        refs.append(GovernanceReference(kind=ReferenceKind.CLAIM, id=claim.id))
    for ev in context["evidence_items"][:10]:
        refs.append(
            GovernanceReference(
                kind=ReferenceKind.EVIDENCE,
                id=ev.id,
                content_hash=ev.sha256,
            )
        )
    for protocol in context["protocols"][:5]:
        refs.append(
            GovernanceReference(
                kind=ReferenceKind.PROTOCOL,
                id=protocol.id,
                content_hash=protocol.protocol_hash,
            )
        )
    for deliverable_id in node_deliverables.values():
        deliverable = await db.get(AssignmentDeliverable, deliverable_id)
        if deliverable is not None and deliverable.investigation_id == investigation_id:
            refs.append(
                GovernanceReference(
                    kind=ReferenceKind.DELIVERABLE,
                    id=deliverable.id,
                    content_hash=deliverable.content_hash,
                )
            )
    return refs


def _role_attribution(base: AttributionInput, role_id: str) -> AttributionInput:
    return AttributionInput(
        recorder_id=base.recorder_id,
        recorder_label=base.recorder_label,
        entry_method=base.entry_method,
        associated_role_id=role_id,
        role_association_note=base.role_association_note
        or f"Governed Stage 4 workflow node for role {role_id}.",
    )


def _build_node_prompt(
    spec: AnalysisNodeSpec,
    investigation_id: str,
    context: dict[str, Any],
) -> str:
    claim_statements = "; ".join(
        f"{c.id}:{c.metric_name}={c.reported_value} ({c.statement[:120]})"
        for c in context["claims"][:5]
    )
    evidence_locators = "; ".join(
        f"{e.id}:{e.source_locator} [{e.verification_status}]"
        for e in context["evidence_items"][:5]
    )
    return (
        f"Investigation={investigation_id} | Node={spec.node_name} | Role={spec.role_id} | "
        f"Task={spec.task_kind} | Objective={spec.objective} | "
        f"Claims=[{claim_statements}] | Evidence=[{evidence_locators}]"
    )


def _build_node_summary(
    spec: AnalysisNodeSpec,
    context: dict[str, Any],
    summary_note: str | None,
) -> str:
    claims_count = len(context["claims"])
    evidence_count = len(context["evidence_items"])
    accepted_count = len(context["accepted_evidence_ids"])
    protocols_count = len(context["protocols"])
    base = (
        f"[{spec.node_name}:{spec.role_id}] Completed {spec.task_kind} across "
        f"{claims_count} claim(s), {evidence_count} evidence item(s) "
        f"({accepted_count} manually reviewed/accepted), and {protocols_count} protocol version(s). "
        "No experiment execution, sandbox jobs, or fabricated measurements were performed."
    )
    if summary_note:
        combined = f"{base} Model synthesis note: {summary_note.strip()}"
        return combined[:4900]
    return base[:4900]


async def _find_completed_checkpoint(
    db: AsyncSession,
    workflow_run_id: str,
    node_name: str,
) -> WorkflowCheckpoint | None:
    return await db.scalar(
        select(WorkflowCheckpoint)
        .where(
            WorkflowCheckpoint.workflow_run_id == workflow_run_id,
            WorkflowCheckpoint.node_name == node_name,
            WorkflowCheckpoint.stage_status == CheckpointStageStatus.COMPLETED.value,
        )
        .order_by(WorkflowCheckpoint.sequence_number.desc())
        .limit(1)
    )


async def _drive_workflow_graph(
    db: AsyncSession,
    workflow_run: WorkflowRun,
    *,
    actor_attribution: AttributionInput,
    actor_attribution_id: str,
    gate_approved: bool,
    settings: Settings,
    model_adapter: WorkflowModelAdapter | None,
    runner: Any | None = None,
) -> None:
    context = await _load_investigation_context(db, workflow_run.investigation_id)
    is_reproduction = workflow_run.workflow_kind == "full_reproduction_v1"
    active_specs = REPRODUCTION_NODE_SPECS if is_reproduction else NODE_SPECS

    prior_completed = list(
        (
            await db.scalars(
                select(WorkflowCheckpoint)
                .where(
                    WorkflowCheckpoint.workflow_run_id == workflow_run.id,
                    WorkflowCheckpoint.stage_status == CheckpointStageStatus.COMPLETED.value,
                )
                .order_by(WorkflowCheckpoint.sequence_number.asc())
            )
        ).all()
    )
    completed_nodes: list[str] = []
    node_assignments: dict[str, str] = {}
    node_deliverables: dict[str, str] = {}
    for cp in prior_completed:
        if cp.node_name not in completed_nodes:
            completed_nodes.append(cp.node_name)
        if cp.assignment_id:
            node_assignments[cp.node_name] = cp.assignment_id
        if cp.deliverable_id:
            node_deliverables[cp.node_name] = cp.deliverable_id

    initial_state: AnalysisWorkflowState = {
        "workflow_run_id": workflow_run.id,
        "investigation_id": workflow_run.investigation_id,
        "workflow_kind": workflow_run.workflow_kind,
        "provider_mode": workflow_run.provider_mode,
        "current_node": workflow_run.current_node,
        "status": WorkflowStatus.RUNNING.value,
        "gate_approved": gate_approved,
        "completed_nodes": completed_nodes,
        "node_assignments": node_assignments,
        "node_deliverables": node_deliverables,
        "claim_ids": [c.id for c in context["claims"]],
        "evidence_ids": [e.id for e in context["evidence_items"]],
        "accepted_evidence_ids": list(context["accepted_evidence_ids"]),
        "protocol_ids": [p.id for p in context["protocols"]],
        "finding_version_ids": [f.id for f in context["finding_versions"]],
        "report_ids": [r.id for r in context["report_versions"]],
        "blocked_reason": None,
        "abstained_reason": None,
    }

    async def _step_handler(node_name: str, state: AnalysisWorkflowState) -> dict[str, Any]:
        spec = active_specs[node_name]
        existing_cp = await _find_completed_checkpoint(db, workflow_run.id, node_name)
        if existing_cp is not None:
            next_completed = list(state["completed_nodes"])
            if node_name not in next_completed:
                next_completed.append(node_name)
            next_assignments = dict(state["node_assignments"])
            if existing_cp.assignment_id:
                next_assignments[node_name] = existing_cp.assignment_id
            next_deliverables = dict(state["node_deliverables"])
            if existing_cp.deliverable_id:
                next_deliverables[node_name] = existing_cp.deliverable_id
            next_node = spec.next_node
            workflow_run.current_node = next_node
            return {
                **state,
                "current_node": next_node,
                "completed_nodes": next_completed,
                "node_assignments": next_assignments,
                "node_deliverables": next_deliverables,
            }

        if node_name == WorkflowNode.HUMAN_REVIEW_GATE.value:
            if not state["gate_approved"]:
                next_state: AnalysisWorkflowState = {
                    **state,
                    "current_node": WorkflowNode.HUMAN_REVIEW_GATE.value,
                    "status": WorkflowStatus.AWAITING_HUMAN_REVIEW.value,
                }
                workflow_run.status = WorkflowStatus.AWAITING_HUMAN_REVIEW.value
                workflow_run.current_node = WorkflowNode.HUMAN_REVIEW_GATE.value
                workflow_run.lifecycle_version += 1
                await _append_workflow_checkpoint(
                    db,
                    workflow_run,
                    node_name=node_name,
                    stage_status=CheckpointStageStatus.AWAITING_HUMAN_REVIEW.value,
                    role_id=None,
                    assignment_id=None,
                    deliverable_id=None,
                    state_json=dict(next_state),
                )
                await _append_workflow_event(
                    db,
                    workflow_run,
                    event_type=WorkflowEventType.GATE_PAUSED.value,
                    node_name=node_name,
                    role_id=None,
                    attribution_id=actor_attribution_id,
                    reason="Awaiting human review gate approval before adversarial review and synthesis.",
                    payload={"completed_nodes": list(state["completed_nodes"])},
                )
                return dict(next_state)

            next_completed = list(state["completed_nodes"])
            if node_name not in next_completed:
                next_completed.append(node_name)
            next_state = {
                **state,
                "current_node": spec.next_node,
                "status": WorkflowStatus.RUNNING.value,
                "completed_nodes": next_completed,
            }
            workflow_run.current_node = spec.next_node
            await _append_workflow_checkpoint(
                db,
                workflow_run,
                node_name=node_name,
                stage_status=CheckpointStageStatus.COMPLETED.value,
                role_id=None,
                assignment_id=None,
                deliverable_id=None,
                state_json=dict(next_state),
            )
            await _append_workflow_event(
                db,
                workflow_run,
                event_type=WorkflowEventType.NODE_COMPLETED.value,
                node_name=node_name,
                role_id=None,
                attribution_id=actor_attribution_id,
                payload={"next_node": spec.next_node},
            )
            return dict(next_state)

        assert spec.role_id is not None
        assert spec.task_kind is not None
        assert spec.deliverable_kind is not None
        assert spec.deliverable_content_kind is not None

        if is_reproduction:
            assert_reproduction_role_and_tool_allowed(spec.role_id)
            role_ceiling = (
                0
                if spec.role_id in DETERMINISTIC_REPRODUCTION_ROLES
                else int(ROLE_MAX_MODEL_CALLS.get(spec.role_id, 0))
            )
        else:
            assert_stage4_role_and_tool_allowed(spec.role_id)
            role_ceiling = (
                0
                if spec.role_id in DETERMINISTIC_STAGE4_ROLES
                else int(ROLE_MAX_MODEL_CALLS.get(spec.role_id, 0))
            )

        role_attr = _role_attribution(actor_attribution, spec.role_id)
        input_refs = await _build_input_references(
            db,
            workflow_run.investigation_id,
            context,
            state["node_deliverables"],
        )

        # Dr. Faraday Hermetic Execution Node Handler
        if node_name == WorkflowNode.FARADAY_EXECUTION.value:
            frozen_protocol = await db.scalar(
                select(ProtocolVersion)
                .where(
                    ProtocolVersion.investigation_id == workflow_run.investigation_id,
                    ProtocolVersion.status == "frozen",
                )
                .order_by(ProtocolVersion.version_number.desc())
                .limit(1)
            )
            faraday_attribution = await _governed_create_attribution(db, workflow_run.investigation_id, role_attr)
            snapshot = await _registered_snapshot(db, "faraday", None, None)

            if frozen_protocol is None:
                abstention_reason_text = (
                    "Dr. Faraday execution abstained: No approved frozen protocol version found for this investigation."
                )
                assignment = RoleAssignment(
                    id=str(uuid4()),
                    investigation_id=workflow_run.investigation_id,
                    role_id="faraday",
                    task_kind="execution",
                    constitution_version=snapshot.constitution_version,
                    constitution_hash=snapshot.constitution_hash,
                    objective=spec.objective,
                    input_contract="manual.input",
                    output_contract="deliverable",
                    input_references=[r.model_dump(mode="json") for r in input_refs],
                    requested_by="atlas",
                    budget={"max_model_calls": 0, "max_input_tokens": 0, "max_output_tokens": 0},
                    status=AssignmentStatus.ABSTAINED.value,
                    lifecycle_version=1,
                    created_by_attribution_id=faraday_attribution.id,
                )
                db.add(assignment)
                await db.flush()

                abstention_payload = {
                    "kind": "implementation_assessment",
                    "summary": abstention_reason_text,
                    "reason": "insufficient_evidence",
                    "input_references": [r.model_dump(mode="json") for r in input_refs],
                }
                deliverable = AssignmentDeliverable(
                    id=str(uuid4()),
                    investigation_id=workflow_run.investigation_id,
                    assignment_id=assignment.id,
                    kind="implementation_assessment",
                    schema_name="abstention",
                    content=abstention_payload,
                    content_hash=canonical_json_hash(abstention_payload),
                    input_references=[r.model_dump(mode="json") for r in input_refs],
                    limitations=[abstention_reason_text],
                    status="submitted",
                    created_by_attribution_id=faraday_attribution.id,
                )
                db.add(deliverable)
                await db.flush()

                next_assignments = {**state["node_assignments"], node_name: assignment.id}
                next_deliverables = {**state["node_deliverables"], node_name: deliverable.id}
                next_state = {
                    **state,
                    "current_node": node_name,
                    "status": WorkflowStatus.ABSTAINED.value,
                    "abstained_reason": abstention_reason_text,
                    "node_assignments": next_assignments,
                    "node_deliverables": next_deliverables,
                }
                workflow_run.status = WorkflowStatus.ABSTAINED.value
                workflow_run.abstained_reason = abstention_reason_text
                workflow_run.current_node = node_name
                workflow_run.lifecycle_version += 1
                await _append_workflow_checkpoint(
                    db,
                    workflow_run,
                    node_name=node_name,
                    stage_status=CheckpointStageStatus.ABSTAINED.value,
                    role_id="faraday",
                    assignment_id=assignment.id,
                    deliverable_id=deliverable.id,
                    state_json=dict(next_state),
                )
                await _append_workflow_event(
                    db,
                    workflow_run,
                    event_type=WorkflowEventType.RUN_ABSTAINED.value,
                    node_name=node_name,
                    role_id="faraday",
                    attribution_id=actor_attribution_id,
                    reason=abstention_reason_text,
                    payload={"assignment_id": assignment.id, "deliverable_id": deliverable.id},
                )
                return dict(next_state)

            assignment = RoleAssignment(
                id=str(uuid4()),
                investigation_id=workflow_run.investigation_id,
                role_id="faraday",
                task_kind="execution",
                constitution_version=snapshot.constitution_version,
                constitution_hash=snapshot.constitution_hash,
                objective=spec.objective,
                input_contract="manual.input",
                output_contract="deliverable",
                input_references=[r.model_dump(mode="json") for r in input_refs],
                requested_by="atlas",
                budget={"max_model_calls": 0, "max_input_tokens": 0, "max_output_tokens": 0},
                status=AssignmentStatus.IN_PROGRESS.value,
                lifecycle_version=1,
                created_by_attribution_id=faraday_attribution.id,
            )
            db.add(assignment)
            await db.flush()

            job_payload = ExperimentJobCreate(
                protocol_version_id=frozen_protocol.id,
                submission_key=f"repro-{workflow_run.id}-{spec.node_name}",
                attribution=role_attr,
            )
            storage = LocalPrivateStorage(settings.storage_root, settings.max_upload_bytes)
            job = await submit_and_run_experiment_job.__wrapped__(
                db,
                workflow_run.investigation_id,
                job_payload,
                storage=storage,
                runner=runner,
            )

            if job.status != "completed":
                blocked_msg = f"Dr. Faraday execution sandbox job ended with status '{job.status}'."
                assignment.status = AssignmentStatus.BLOCKED.value
                assignment.blocked_reason = blocked_msg
                assignment.lifecycle_version += 1

                deliverable_content = {
                    "kind": "implementation_assessment",
                    "summary": blocked_msg,
                    "input_references": [r.model_dump(mode="json") for r in input_refs],
                    "job_id": job.id,
                    "execution_bundle_hash": job.execution_bundle_hash,
                    "job_status": job.status,
                }
                deliverable = AssignmentDeliverable(
                    id=str(uuid4()),
                    investigation_id=workflow_run.investigation_id,
                    assignment_id=assignment.id,
                    kind="implementation_assessment",
                    schema_name="deliverable",
                    content=deliverable_content,
                    content_hash=canonical_json_hash(deliverable_content),
                    input_references=[r.model_dump(mode="json") for r in input_refs],
                    limitations=[blocked_msg],
                    status="submitted",
                    created_by_attribution_id=faraday_attribution.id,
                )
                db.add(deliverable)
                await db.flush()

                next_assignments = {**state["node_assignments"], node_name: assignment.id}
                next_deliverables = {**state["node_deliverables"], node_name: deliverable.id}
                next_state = {
                    **state,
                    "current_node": node_name,
                    "status": WorkflowStatus.BLOCKED.value,
                    "blocked_reason": blocked_msg,
                    "node_assignments": next_assignments,
                    "node_deliverables": next_deliverables,
                    "job_id": job.id,
                }
                workflow_run.status = WorkflowStatus.BLOCKED.value
                workflow_run.blocked_reason = blocked_msg
                workflow_run.current_node = node_name
                workflow_run.lifecycle_version += 1
                await _append_workflow_checkpoint(
                    db,
                    workflow_run,
                    node_name=node_name,
                    stage_status=CheckpointStageStatus.BLOCKED.value,
                    role_id="faraday",
                    assignment_id=assignment.id,
                    deliverable_id=deliverable.id,
                    state_json=dict(next_state),
                )
                await _append_workflow_event(
                    db,
                    workflow_run,
                    event_type=WorkflowEventType.RUN_BLOCKED.value,
                    node_name=node_name,
                    role_id="faraday",
                    attribution_id=actor_attribution_id,
                    reason=blocked_msg,
                    payload={"assignment_id": assignment.id, "job_id": job.id, "job_status": job.status},
                )
                return dict(next_state)

            assignment.status = AssignmentStatus.COMPLETED.value
            assignment.lifecycle_version += 1
            deliverable_content = {
                "kind": "implementation_assessment",
                "summary": (
                    f"[faraday_execution:faraday] Hermetic isolated runner completed successfully. "
                    f"Job ID: {job.id}. Execution bundle hash: {job.execution_bundle_hash}."
                ),
                "input_references": [r.model_dump(mode="json") for r in input_refs],
                "job_id": job.id,
                "execution_bundle_hash": job.execution_bundle_hash,
                "job_status": job.status,
            }
            deliverable = AssignmentDeliverable(
                id=str(uuid4()),
                investigation_id=workflow_run.investigation_id,
                assignment_id=assignment.id,
                kind="implementation_assessment",
                schema_name="deliverable",
                content=deliverable_content,
                content_hash=canonical_json_hash(deliverable_content),
                input_references=[r.model_dump(mode="json") for r in input_refs],
                limitations=["Hermetic sandbox execution in isolated environment."],
                status="submitted",
                created_by_attribution_id=faraday_attribution.id,
            )
            db.add(deliverable)
            await db.flush()

            next_completed = list(state["completed_nodes"])
            if node_name not in next_completed:
                next_completed.append(node_name)
            next_assignments = {**state["node_assignments"], node_name: assignment.id}
            next_deliverables = {**state["node_deliverables"], node_name: deliverable.id}
            next_state = {
                **state,
                "current_node": spec.next_node,
                "status": WorkflowStatus.RUNNING.value,
                "completed_nodes": next_completed,
                "node_assignments": next_assignments,
                "node_deliverables": next_deliverables,
                "job_id": job.id,
            }
            workflow_run.current_node = spec.next_node
            await _append_workflow_checkpoint(
                db,
                workflow_run,
                node_name=node_name,
                stage_status=CheckpointStageStatus.COMPLETED.value,
                role_id="faraday",
                assignment_id=assignment.id,
                deliverable_id=deliverable.id,
                state_json=dict(next_state),
            )
            await _append_workflow_event(
                db,
                workflow_run,
                event_type=WorkflowEventType.NODE_COMPLETED.value,
                node_name=node_name,
                role_id="faraday",
                attribution_id=actor_attribution_id,
                payload={"assignment_id": assignment.id, "deliverable_id": deliverable.id, "job_id": job.id, "next_node": spec.next_node},
            )
            return dict(next_state)
        budget = AssignmentBudget(
            max_model_calls=role_ceiling if workflow_run.provider_mode == "gemini" else 0,
            max_input_tokens=4000 if (workflow_run.provider_mode == "gemini" and role_ceiling > 0) else 0,
            max_output_tokens=1000 if (workflow_run.provider_mode == "gemini" and role_ceiling > 0) else 0,
        )
        assignment = await _create_assignment_in_tx(
            db,
            workflow_run.investigation_id,
            AssignmentCreate(
                investigation_id=workflow_run.investigation_id,
                role_id=spec.role_id,
                task_kind=spec.task_kind,
                objective=spec.objective,
                input_references=input_refs,
                requested_by="atlas" if spec.role_id != "atlas" else None,
                budget=budget,
                attribution=role_attr,
            ),
        )
        await _transition_assignment_in_tx(
            db,
            workflow_run.investigation_id,
            assignment.id,
            AssignmentTransitionRequest(
                assignment_id=assignment.id,
                from_status=AssignmentStatus.ASSIGNED,
                to_status=AssignmentStatus.IN_PROGRESS,
                expected_lifecycle_version=assignment.lifecycle_version,
                actor_role_id=spec.role_id,
                attribution=role_attr,
            ),
        )

        # Prerequisite gate 1: Atlas intake requires at least one claim and one evidence item
        if node_name == WorkflowNode.ATLAS_INTAKE.value and (
            not context["claims"] or not context["evidence_items"]
        ):
            prompt = _build_node_prompt(spec, workflow_run.investigation_id, context)
            model_result = execute_governed_model_step(
                role_id=spec.role_id,
                provider_mode=workflow_run.provider_mode,
                prompt=prompt,
                existing_calls_for_assignment=0,
                settings=settings,
                adapter=model_adapter,
            )
            await _record_model_call(
                db,
                workflow_run,
                assignment_id=assignment.id,
                role_id=spec.role_id,
                node_name=node_name,
                attribution_id=actor_attribution_id,
                model_result=model_result,
            )
            abstention_reason_text = (
                "Investigation intake abstained because source claims or evidence items are missing."
            )
            inv_ref = GovernanceReference(
                kind=ReferenceKind.INVESTIGATION,
                id=workflow_run.investigation_id,
            )
            abstention_payload = AbstentionOutput(
                assignment_id=assignment.id,
                role_id=spec.role_id,
                summary=abstention_reason_text,
                input_references=[inv_ref],
                reason=AbstentionReason.INSUFFICIENT_EVIDENCE,
                missing_references=[inv_ref],
                required_action=(
                    "Register at least one source-grounded claim and one evidence item before running analysis."
                ),
            ).model_dump(mode="json")
            deliverable = await _create_deliverable_in_tx(
                db,
                workflow_run.investigation_id,
                DeliverableCreate(
                    assignment_id=assignment.id,
                    kind=DeliverableKind(spec.deliverable_kind),
                    schema_name="abstention",
                    content=abstention_payload,
                    content_hash=canonical_json_hash(abstention_payload),
                    input_references=[inv_ref],
                    limitations=[abstention_reason_text],
                    attribution=role_attr,
                ),
            )
            await _transition_assignment_in_tx(
                db,
                workflow_run.investigation_id,
                assignment.id,
                AssignmentTransitionRequest(
                    assignment_id=assignment.id,
                    from_status=AssignmentStatus.IN_PROGRESS,
                    to_status=AssignmentStatus.ABSTAINED,
                    expected_lifecycle_version=assignment.lifecycle_version,
                    reason=abstention_reason_text,
                    actor_role_id=spec.role_id,
                    attribution=role_attr,
                ),
            )
            next_assignments = {**state["node_assignments"], node_name: assignment.id}
            next_deliverables = {**state["node_deliverables"], node_name: deliverable.id}
            next_state = {
                **state,
                "current_node": node_name,
                "status": WorkflowStatus.ABSTAINED.value,
                "abstained_reason": abstention_reason_text,
                "node_assignments": next_assignments,
                "node_deliverables": next_deliverables,
            }
            workflow_run.status = WorkflowStatus.ABSTAINED.value
            workflow_run.abstained_reason = abstention_reason_text
            workflow_run.current_node = node_name
            workflow_run.lifecycle_version += 1
            await _append_workflow_checkpoint(
                db,
                workflow_run,
                node_name=node_name,
                stage_status=CheckpointStageStatus.ABSTAINED.value,
                role_id=spec.role_id,
                assignment_id=assignment.id,
                deliverable_id=deliverable.id,
                state_json=dict(next_state),
            )
            await _append_workflow_event(
                db,
                workflow_run,
                event_type=WorkflowEventType.RUN_ABSTAINED.value,
                node_name=node_name,
                role_id=spec.role_id,
                attribution_id=actor_attribution_id,
                reason=abstention_reason_text,
                payload={"assignment_id": assignment.id, "deliverable_id": deliverable.id},
            )
            return dict(next_state)

        # Prerequisite gate 2: Sagan verification requires at least one manually reviewed / accepted evidence item
        if node_name == WorkflowNode.SAGAN_VERIFICATION.value and not context["accepted_evidence_ids"]:
            blocked_msg = (
                "Evidence requires an accepted manual review before methodology and synthesis stages can proceed."
            )
            missing_refs = [
                GovernanceReference(
                    kind=ReferenceKind.EVIDENCE,
                    id=ev.id,
                    content_hash=ev.sha256,
                )
                for ev in context["evidence_items"][:10]
            ] or [
                GovernanceReference(
                    kind=ReferenceKind.INVESTIGATION,
                    id=workflow_run.investigation_id,
                )
            ]
            abstention_payload = AbstentionOutput(
                assignment_id=assignment.id,
                role_id=spec.role_id,
                summary=blocked_msg,
                input_references=input_refs,
                reason=AbstentionReason.INSUFFICIENT_EVIDENCE,
                missing_references=missing_refs,
                required_action="Record an accepted manual review on at least one evidence item and resume the workflow.",
            ).model_dump(mode="json")
            deliverable = await _create_deliverable_in_tx(
                db,
                workflow_run.investigation_id,
                DeliverableCreate(
                    assignment_id=assignment.id,
                    kind=DeliverableKind(spec.deliverable_kind),
                    schema_name="abstention",
                    content=abstention_payload,
                    content_hash=canonical_json_hash(abstention_payload),
                    input_references=input_refs,
                    limitations=[blocked_msg],
                    attribution=role_attr,
                ),
            )
            await _transition_assignment_in_tx(
                db,
                workflow_run.investigation_id,
                assignment.id,
                AssignmentTransitionRequest(
                    assignment_id=assignment.id,
                    from_status=AssignmentStatus.IN_PROGRESS,
                    to_status=AssignmentStatus.ABSTAINED,
                    expected_lifecycle_version=assignment.lifecycle_version,
                    reason=blocked_msg,
                    actor_role_id=spec.role_id,
                    attribution=role_attr,
                ),
            )
            next_assignments = {**state["node_assignments"], node_name: assignment.id}
            next_deliverables = {**state["node_deliverables"], node_name: deliverable.id}
            next_state = {
                **state,
                "current_node": node_name,
                "status": WorkflowStatus.BLOCKED.value,
                "blocked_reason": blocked_msg,
                "node_assignments": next_assignments,
                "node_deliverables": next_deliverables,
            }
            workflow_run.status = WorkflowStatus.BLOCKED.value
            workflow_run.blocked_reason = blocked_msg
            workflow_run.current_node = node_name
            workflow_run.lifecycle_version += 1
            await _append_workflow_checkpoint(
                db,
                workflow_run,
                node_name=node_name,
                stage_status=CheckpointStageStatus.BLOCKED.value,
                role_id=spec.role_id,
                assignment_id=assignment.id,
                deliverable_id=deliverable.id,
                state_json=dict(next_state),
            )
            await _append_workflow_event(
                db,
                workflow_run,
                event_type=WorkflowEventType.RUN_BLOCKED.value,
                node_name=node_name,
                role_id=spec.role_id,
                attribution_id=actor_attribution_id,
                reason=blocked_msg,
                payload={"assignment_id": assignment.id, "deliverable_id": deliverable.id},
            )
            return dict(next_state)

        existing_calls = int(
            await db.scalar(
                select(func.count(WorkflowModelCall.id)).where(
                    WorkflowModelCall.assignment_id == assignment.id
                )
            )
            or 0
        )
        prompt = _build_node_prompt(spec, workflow_run.investigation_id, context)
        model_result = execute_governed_model_step(
            role_id=spec.role_id,
            provider_mode=workflow_run.provider_mode,
            prompt=prompt,
            existing_calls_for_assignment=existing_calls,
            settings=settings,
            adapter=model_adapter,
            workflow_kind=workflow_run.workflow_kind,
        )
        await _record_model_call(
            db,
            workflow_run,
            assignment_id=assignment.id,
            role_id=spec.role_id,
            node_name=node_name,
            attribution_id=actor_attribution_id,
            model_result=model_result,
        )

        if model_result.status in {"failed_provider_error", "blocked_budget"}:
            reason_text = (
                model_result.error_detail
                or f"Model step for role {spec.role_id!r} failed with status {model_result.status!r}."
            )
            await _transition_assignment_in_tx(
                db,
                workflow_run.investigation_id,
                assignment.id,
                AssignmentTransitionRequest(
                    assignment_id=assignment.id,
                    from_status=AssignmentStatus.IN_PROGRESS,
                    to_status=AssignmentStatus.BLOCKED,
                    expected_lifecycle_version=assignment.lifecycle_version,
                    reason=reason_text,
                    actor_role_id=spec.role_id,
                    attribution=role_attr,
                ),
            )
            next_assignments = {**state["node_assignments"], node_name: assignment.id}
            next_state = {
                **state,
                "current_node": node_name,
                "status": WorkflowStatus.BLOCKED.value,
                "blocked_reason": reason_text,
                "node_assignments": next_assignments,
            }
            workflow_run.status = WorkflowStatus.BLOCKED.value
            workflow_run.blocked_reason = reason_text
            workflow_run.current_node = node_name
            workflow_run.lifecycle_version += 1
            await _append_workflow_checkpoint(
                db,
                workflow_run,
                node_name=node_name,
                stage_status=CheckpointStageStatus.BLOCKED.value,
                role_id=spec.role_id,
                assignment_id=assignment.id,
                deliverable_id=None,
                state_json=dict(next_state),
            )
            await _append_workflow_event(
                db,
                workflow_run,
                event_type=WorkflowEventType.RUN_BLOCKED.value,
                node_name=node_name,
                role_id=spec.role_id,
                attribution_id=actor_attribution_id,
                reason=reason_text,
                payload={
                    "assignment_id": assignment.id,
                    "model_call_status": model_result.status,
                },
            )
            return dict(next_state)

        evaluation_id: str | None = None
        if node_name == WorkflowNode.FISHER_EVALUATION.value:
            measurements = list(
                (
                    await db.scalars(
                        select(ProductionMeasurement)
                        .where(ProductionMeasurement.job_id == state.get("job_id"))
                    )
                ).all()
            )
            if measurements:
                m = measurements[0]
                fisher_note = (
                    f"Fisher evaluation: {m.metric_name}={m.value:.4f} "
                    f"(95% Wilson CI [{m.interval_lower:.4f}, {m.interval_upper:.4f}], n={m.sample_size})."
                )
                summary_note = f"{model_result.summary_note or ''} {fisher_note}".strip()
            else:
                summary_note = model_result.summary_note
        elif node_name == WorkflowNode.SAGAN_PROVENANCE.value:
            measurements = list(
                (
                    await db.scalars(
                        select(ProductionMeasurement)
                        .where(ProductionMeasurement.job_id == state.get("job_id"))
                    )
                ).all()
            )
            sagan_note = (
                f"Sagan cryptographic provenance: verified {len(measurements)} measurement(s) "
                f"and sandbox output artifact digests."
            )
            summary_note = f"{model_result.summary_note or ''} {sagan_note}".strip()
        elif node_name == WorkflowNode.FRANKLIN_SYNTHESIS.value and is_reproduction:
            evaluation = await run_scientific_evaluation(
                workflow_run.investigation_id,
                db,
                job_id=state.get("job_id"),
                commit=False,
            )
            evaluation_id = evaluation.id
            franklin_note = (
                f"Franklin final synthesis: Tri-partite evaluation {evaluation.id} complete. "
                f"Extraction={evaluation.extraction_quality_score:.2f}, "
                f"Technical={evaluation.technical_reproducibility_score:.2f}, "
                f"Verdict={evaluation.verdict}."
            )
            summary_note = f"{model_result.summary_note or ''} {franklin_note}".strip()
        else:
            summary_note = model_result.summary_note

        summary_text = _build_node_summary(spec, context, summary_note)
        deliverable_content = ManualDeliverableContent(
            kind=spec.task_kind,
            summary=summary_text,
            input_references=input_refs,
        ).model_dump(mode="json")
        limitations = (
            ["Hermetic reproduction pipeline with isolated execution and independent scoring."]
            if is_reproduction
            else ["Stage 4 analysis-only workflow: no code execution, sandbox runner, or new empirical measurements."]
        )
        deliverable = await _create_deliverable_in_tx(
            db,
            workflow_run.investigation_id,
            DeliverableCreate(
                assignment_id=assignment.id,
                kind=DeliverableKind(spec.deliverable_kind),
                schema_name="deliverable",
                content=deliverable_content,
                content_hash=canonical_json_hash(deliverable_content),
                input_references=input_refs,
                limitations=limitations,
                attribution=role_attr,
            ),
        )
        await _transition_assignment_in_tx(
            db,
            workflow_run.investigation_id,
            assignment.id,
            AssignmentTransitionRequest(
                assignment_id=assignment.id,
                from_status=AssignmentStatus.IN_PROGRESS,
                to_status=AssignmentStatus.COMPLETED,
                expected_lifecycle_version=assignment.lifecycle_version,
                actor_role_id=spec.role_id,
                attribution=role_attr,
            ),
        )

        next_completed = list(state["completed_nodes"])
        if node_name not in next_completed:
            next_completed.append(node_name)
        next_assignments = {**state["node_assignments"], node_name: assignment.id}
        next_deliverables = {**state["node_deliverables"], node_name: deliverable.id}
        is_terminal = spec.next_node == WorkflowNode.TERMINAL.value
        next_status = WorkflowStatus.COMPLETED.value if is_terminal else WorkflowStatus.RUNNING.value
        next_state = {
            **state,
            "current_node": spec.next_node,
            "status": next_status,
            "completed_nodes": next_completed,
            "node_assignments": next_assignments,
            "node_deliverables": next_deliverables,
        }
        if evaluation_id:
            next_state["evaluation_id"] = evaluation_id
        workflow_run.current_node = spec.next_node
        if is_terminal:
            workflow_run.status = WorkflowStatus.COMPLETED.value
            workflow_run.blocked_reason = None
            workflow_run.lifecycle_version += 1

        await _append_workflow_checkpoint(
            db,
            workflow_run,
            node_name=node_name,
            stage_status=CheckpointStageStatus.COMPLETED.value,
            role_id=spec.role_id,
            assignment_id=assignment.id,
            deliverable_id=deliverable.id,
            state_json=dict(next_state),
        )
        await _append_workflow_event(
            db,
            workflow_run,
            event_type=WorkflowEventType.NODE_COMPLETED.value,
            node_name=node_name,
            role_id=spec.role_id,
            attribution_id=actor_attribution_id,
            payload={
                "assignment_id": assignment.id,
                "deliverable_id": deliverable.id,
                "next_node": spec.next_node,
            },
        )
        if is_terminal:
            await _append_workflow_event(
                db,
                workflow_run,
                event_type=WorkflowEventType.RUN_COMPLETED.value,
                node_name=WorkflowNode.TERMINAL.value,
                role_id=spec.role_id,
                attribution_id=actor_attribution_id,
                payload={
                    "completed_nodes": next_completed,
                    "final_deliverable_id": deliverable.id,
                },
            )
        return dict(next_state)

    if is_reproduction:
        compiled_graph = build_reproduction_workflow_graph(_step_handler)
    else:
        compiled_graph = build_analysis_workflow_graph(_step_handler)
    await compiled_graph.ainvoke(initial_state)


async def _record_model_call(
    db: AsyncSession,
    workflow_run: WorkflowRun,
    *,
    assignment_id: str,
    role_id: str,
    node_name: str,
    attribution_id: str,
    model_result,
) -> WorkflowModelCall:
    call_row = WorkflowModelCall(
        id=str(uuid4()),
        workflow_run_id=workflow_run.id,
        investigation_id=workflow_run.investigation_id,
        assignment_id=assignment_id,
        role_id=role_id,
        provider=model_result.provider,
        model_name=model_result.model_name,
        routing_category=model_result.routing_category,
        call_index=model_result.call_index,
        max_calls_ceiling=model_result.max_calls_ceiling,
        status=model_result.status,
        prompt_sha256=model_result.prompt_sha256,
        response_sha256=model_result.response_sha256,
        input_tokens=model_result.input_tokens,
        output_tokens=model_result.output_tokens,
        error_detail=model_result.error_detail,
        recorded_at=_now(),
    )
    db.add(call_row)
    await db.flush()
    await _append_workflow_event(
        db,
        workflow_run,
        event_type=WorkflowEventType.MODEL_CALL_RECORDED.value,
        node_name=node_name,
        role_id=role_id,
        attribution_id=attribution_id,
        reason=model_result.error_detail,
        payload={
            "model_call_id": call_row.id,
            "assignment_id": assignment_id,
            "provider": model_result.provider,
            "model_name": model_result.model_name,
            "routing_category": model_result.routing_category,
            "call_index": model_result.call_index,
            "max_calls_ceiling": model_result.max_calls_ceiling,
            "status": model_result.status,
            "input_tokens": model_result.input_tokens,
            "output_tokens": model_result.output_tokens,
        },
    )
    return call_row


@_atomic_workflow_mutation
async def create_and_run_workflow(
    db: AsyncSession,
    investigation_id: str,
    payload: WorkflowRunCreate,
    *,
    settings: Settings | None = None,
    model_adapter: WorkflowModelAdapter | None = None,
    runner: Any | None = None,
) -> WorkflowRun:
    await _investigation_or_404(db, investigation_id)
    active_settings = settings or get_settings()
    fingerprint = canonical_json_hash(payload.model_dump(mode="json"))

    if payload.idempotency_key is not None:
        existing = await db.scalar(
            select(WorkflowRun).where(
                WorkflowRun.investigation_id == investigation_id,
                WorkflowRun.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            created_event = await db.scalar(
                select(WorkflowEvent)
                .where(
                    WorkflowEvent.workflow_run_id == existing.id,
                    WorkflowEvent.sequence_number == 1,
                )
                .limit(1)
            )
            if (
                existing.provider_mode != payload.provider_mode.value
                or created_event is None
                or created_event.payload.get("request_fingerprint") != fingerprint
            ):
                raise _conflict(
                    "Workflow idempotency_key was already used with different request parameters."
                )
            return existing

    workflow_kind = getattr(payload, "workflow_kind", "analysis_only_v1") or "analysis_only_v1"
    attribution = await _governed_create_attribution(db, investigation_id, payload.attribution)
    workflow_run = WorkflowRun(
        id=str(uuid4()),
        investigation_id=investigation_id,
        workflow_kind=workflow_kind,
        status=WorkflowStatus.RUNNING.value,
        current_node=WorkflowNode.ATLAS_INTAKE.value,
        provider_mode=payload.provider_mode.value,
        idempotency_key=payload.idempotency_key,
        lifecycle_version=1,
        latest_checkpoint_seq=0,
        created_by_attribution_id=attribution.id,
    )
    db.add(workflow_run)
    await db.flush()

    await _append_workflow_event(
        db,
        workflow_run,
        event_type=WorkflowEventType.RUN_CREATED.value,
        node_name=WorkflowNode.ATLAS_INTAKE.value,
        role_id=payload.attribution.associated_role_id,
        attribution_id=attribution.id,
        payload={
            "workflow_kind": workflow_kind,
            "provider_mode": payload.provider_mode.value,
            "idempotency_key": payload.idempotency_key,
            "request_fingerprint": fingerprint,
            "ordered_nodes": list(ORDERED_REPRODUCTION_NODES if workflow_kind == "full_reproduction_v1" else ORDERED_NODES),
        },
    )

    await _drive_workflow_graph(
        db,
        workflow_run,
        actor_attribution=payload.attribution,
        actor_attribution_id=attribution.id,
        gate_approved=False,
        settings=active_settings,
        model_adapter=model_adapter,
        runner=runner,
    )
    await db.refresh(workflow_run)
    return workflow_run


@_atomic_workflow_mutation
async def decide_workflow_gate(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
    payload: WorkflowGateDecisionRequest,
    *,
    settings: Settings | None = None,
    model_adapter: WorkflowModelAdapter | None = None,
    runner: Any | None = None,
) -> WorkflowRun:
    await _investigation_or_404(db, investigation_id)
    workflow_run = await _workflow_run_or_404(db, investigation_id, run_id, lock=True)
    if workflow_run.lifecycle_version != payload.expected_lifecycle_version:
        raise _conflict("Workflow lifecycle_version is stale; reload before submitting gate decision.")
    if (
        workflow_run.status != WorkflowStatus.AWAITING_HUMAN_REVIEW.value
        or workflow_run.current_node != WorkflowNode.HUMAN_REVIEW_GATE.value
    ):
        raise _conflict("Workflow run is not currently awaiting human review gate approval.")

    attribution = await _governed_create_attribution(db, investigation_id, payload.attribution)
    if payload.decision == GateDecision.REJECT:
        workflow_run.status = WorkflowStatus.BLOCKED.value
        workflow_run.blocked_reason = payload.notes
        workflow_run.lifecycle_version += 1
        await _append_workflow_event(
            db,
            workflow_run,
            event_type=WorkflowEventType.GATE_REJECTED.value,
            node_name=WorkflowNode.HUMAN_REVIEW_GATE.value,
            role_id=payload.attribution.associated_role_id,
            attribution_id=attribution.id,
            reason=payload.notes,
            payload={"decision": payload.decision.value},
        )
        await _append_workflow_event(
            db,
            workflow_run,
            event_type=WorkflowEventType.RUN_BLOCKED.value,
            node_name=WorkflowNode.HUMAN_REVIEW_GATE.value,
            role_id=payload.attribution.associated_role_id,
            attribution_id=attribution.id,
            reason=payload.notes,
            payload={"blocked_at": WorkflowNode.HUMAN_REVIEW_GATE.value},
        )
        await db.refresh(workflow_run)
        return workflow_run

    workflow_run.status = WorkflowStatus.RUNNING.value
    workflow_run.blocked_reason = None
    workflow_run.lifecycle_version += 1
    await _append_workflow_event(
        db,
        workflow_run,
        event_type=WorkflowEventType.GATE_APPROVED.value,
        node_name=WorkflowNode.HUMAN_REVIEW_GATE.value,
        role_id=payload.attribution.associated_role_id,
        attribution_id=attribution.id,
        reason=payload.notes,
        payload={"decision": payload.decision.value},
    )
    await _append_workflow_event(
        db,
        workflow_run,
        event_type=WorkflowEventType.RUN_RESUMED.value,
        node_name=WorkflowNode.HUMAN_REVIEW_GATE.value,
        role_id=payload.attribution.associated_role_id,
        attribution_id=attribution.id,
        reason=payload.notes,
        payload={"resumed_from": WorkflowNode.HUMAN_REVIEW_GATE.value},
    )

    await _drive_workflow_graph(
        db,
        workflow_run,
        actor_attribution=payload.attribution,
        actor_attribution_id=attribution.id,
        gate_approved=True,
        settings=settings or get_settings(),
        model_adapter=model_adapter,
        runner=runner,
    )
    await db.refresh(workflow_run)
    return workflow_run


@_atomic_workflow_mutation
async def resume_workflow_run(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
    payload: WorkflowResumeRequest,
    *,
    settings: Settings | None = None,
    model_adapter: WorkflowModelAdapter | None = None,
    runner: Any | None = None,
) -> WorkflowRun:
    await _investigation_or_404(db, investigation_id)
    workflow_run = await _workflow_run_or_404(db, investigation_id, run_id, lock=True)
    if workflow_run.lifecycle_version != payload.expected_lifecycle_version:
        raise _conflict("Workflow lifecycle_version is stale; reload before resuming.")
    if workflow_run.status not in {
        WorkflowStatus.BLOCKED.value,
        WorkflowStatus.ABSTAINED.value,
    }:
        raise _conflict(
            f"Workflow run in status {workflow_run.status!r} cannot be resumed via /resume."
        )

    attribution = await _governed_create_attribution(db, investigation_id, payload.attribution)
    resume_node = workflow_run.current_node
    gate_already_approved = (
        await _find_completed_checkpoint(
            db, workflow_run.id, WorkflowNode.HUMAN_REVIEW_GATE.value
        )
        is not None
    )
    workflow_run.status = WorkflowStatus.RUNNING.value
    workflow_run.blocked_reason = None
    workflow_run.abstained_reason = None
    workflow_run.lifecycle_version += 1
    await _append_workflow_event(
        db,
        workflow_run,
        event_type=WorkflowEventType.RUN_RESUMED.value,
        node_name=resume_node,
        role_id=payload.attribution.associated_role_id,
        attribution_id=attribution.id,
        reason=payload.notes,
        payload={"resumed_from": resume_node},
    )

    await _drive_workflow_graph(
        db,
        workflow_run,
        actor_attribution=payload.attribution,
        actor_attribution_id=attribution.id,
        gate_approved=gate_already_approved,
        settings=settings or get_settings(),
        model_adapter=model_adapter,
        runner=runner,
    )
    await db.refresh(workflow_run)
    return workflow_run


@_atomic_workflow_mutation
async def cancel_workflow_run(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
    payload: WorkflowCancelRequest,
) -> WorkflowRun:
    await _investigation_or_404(db, investigation_id)
    workflow_run = await _workflow_run_or_404(db, investigation_id, run_id, lock=True)
    if workflow_run.lifecycle_version != payload.expected_lifecycle_version:
        raise _conflict("Workflow lifecycle_version is stale; reload before cancelling.")
    if workflow_run.status in {
        WorkflowStatus.COMPLETED.value,
        WorkflowStatus.CANCELLED.value,
    }:
        raise _conflict(f"Workflow run in status {workflow_run.status!r} cannot be cancelled.")

    attribution = await _governed_create_attribution(db, investigation_id, payload.attribution)
    workflow_run.status = WorkflowStatus.CANCELLED.value
    workflow_run.cancelled_reason = payload.reason
    workflow_run.lifecycle_version += 1
    await _append_workflow_event(
        db,
        workflow_run,
        event_type=WorkflowEventType.RUN_CANCELLED.value,
        node_name=workflow_run.current_node,
        role_id=payload.attribution.associated_role_id,
        attribution_id=attribution.id,
        reason=payload.reason,
        payload={"cancelled_at_node": workflow_run.current_node},
    )
    await db.refresh(workflow_run)
    return workflow_run


async def list_workflow_runs(
    db: AsyncSession,
    investigation_id: str,
) -> list[WorkflowRun]:
    await _investigation_or_404(db, investigation_id)
    rows = await db.scalars(
        select(WorkflowRun)
        .where(WorkflowRun.investigation_id == investigation_id)
        .order_by(WorkflowRun.created_at.asc(), WorkflowRun.id.asc())
    )
    return list(rows.all())


async def get_workflow_run(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
) -> WorkflowRun:
    await _investigation_or_404(db, investigation_id)
    return await _workflow_run_or_404(db, investigation_id, run_id)


async def list_workflow_checkpoints(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
) -> list[WorkflowCheckpoint]:
    await _workflow_run_or_404(db, investigation_id, run_id)
    rows = await db.scalars(
        select(WorkflowCheckpoint)
        .where(
            WorkflowCheckpoint.workflow_run_id == run_id,
            WorkflowCheckpoint.investigation_id == investigation_id,
        )
        .order_by(WorkflowCheckpoint.sequence_number.asc())
    )
    return list(rows.all())


async def list_workflow_events(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
) -> list[WorkflowEvent]:
    await _workflow_run_or_404(db, investigation_id, run_id)
    rows = await db.scalars(
        select(WorkflowEvent)
        .where(
            WorkflowEvent.workflow_run_id == run_id,
            WorkflowEvent.investigation_id == investigation_id,
        )
        .order_by(WorkflowEvent.sequence_number.asc())
    )
    return list(rows.all())


async def list_workflow_model_calls(
    db: AsyncSession,
    investigation_id: str,
    run_id: str,
) -> list[WorkflowModelCall]:
    await _workflow_run_or_404(db, investigation_id, run_id)
    rows = await db.scalars(
        select(WorkflowModelCall)
        .where(
            WorkflowModelCall.workflow_run_id == run_id,
            WorkflowModelCall.investigation_id == investigation_id,
        )
        .order_by(WorkflowModelCall.recorded_at.asc(), WorkflowModelCall.id.asc())
    )
    return list(rows.all())
