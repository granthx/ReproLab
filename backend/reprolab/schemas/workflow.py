"""Pydantic contracts for Stage 4 analysis-only LangGraph workflows."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from reprolab.schemas.governance import Hash256, Identifier, MediumText, RoleId
from reprolab.schemas.records import AttributionInput


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowReadModel(WorkflowModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    BLOCKED = "blocked"
    ABSTAINED = "abstained"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkflowNode(str, Enum):
    ATLAS_INTAKE = "atlas_intake"
    QUILL_EXTRACTION = "quill_extraction"
    SAGAN_VERIFICATION = "sagan_verification"
    HYPATIA_AUDIT = "hypatia_audit"
    TURING_ASSESSMENT = "turing_assessment"
    CURIE_DATASET = "curie_dataset"
    HUMAN_REVIEW_GATE = "human_review_gate"
    FARADAY_EXECUTION = "faraday_execution"
    FISHER_EVALUATION = "fisher_evaluation"
    POPPER_REVIEW = "popper_review"
    SHANNON_SENSITIVITY = "shannon_sensitivity"
    NOETHER_REPLICATION = "noether_replication"
    SAGAN_PROVENANCE = "sagan_provenance"
    FRANKLIN_SYNTHESIS = "franklin_synthesis"
    TERMINAL = "terminal"


class WorkflowProviderMode(str, Enum):
    SOURCE_GROUNDED = "source_grounded"
    GEMINI = "gemini"


class CheckpointStageStatus(str, Enum):
    ENTERED = "entered"
    COMPLETED = "completed"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    BLOCKED = "blocked"
    ABSTAINED = "abstained"


class WorkflowEventType(str, Enum):
    RUN_CREATED = "run_created"
    NODE_COMPLETED = "node_completed"
    GATE_PAUSED = "gate_paused"
    GATE_APPROVED = "gate_approved"
    GATE_REJECTED = "gate_rejected"
    MODEL_CALL_RECORDED = "model_call_recorded"
    RUN_BLOCKED = "run_blocked"
    RUN_ABSTAINED = "run_abstained"
    RUN_RESUMED = "run_resumed"
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"


class ModelCallProvider(str, Enum):
    GEMINI = "gemini"
    DETERMINISTIC_NONE = "deterministic_none"


class ModelCallStatus(str, Enum):
    SUCCEEDED = "succeeded"
    SKIPPED_DETERMINISTIC = "skipped_deterministic"
    SKIPPED_CONDITIONAL_NOT_NEEDED = "skipped_conditional_not_needed"
    FAILED_PROVIDER_ERROR = "failed_provider_error"
    BLOCKED_BUDGET = "blocked_budget"


class GateDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class WorkflowRunCreate(WorkflowModel):
    workflow_kind: Annotated[str, Field(pattern=r"^(analysis_only_v1|full_reproduction_v1)$")] = "analysis_only_v1"
    provider_mode: WorkflowProviderMode = WorkflowProviderMode.SOURCE_GROUNDED
    idempotency_key: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")] | None = None
    attribution: AttributionInput


class WorkflowGateDecisionRequest(WorkflowModel):
    decision: GateDecision
    expected_lifecycle_version: Annotated[int, Field(ge=1)]
    notes: MediumText
    attribution: AttributionInput


class WorkflowResumeRequest(WorkflowModel):
    expected_lifecycle_version: Annotated[int, Field(ge=1)]
    notes: MediumText | None = None
    attribution: AttributionInput


class WorkflowCancelRequest(WorkflowModel):
    expected_lifecycle_version: Annotated[int, Field(ge=1)]
    reason: MediumText
    attribution: AttributionInput


class WorkflowCheckpointRead(WorkflowReadModel):
    id: Identifier
    workflow_run_id: Identifier
    investigation_id: Identifier
    sequence_number: int
    node_name: WorkflowNode
    stage_status: CheckpointStageStatus
    role_id: RoleId | None = None
    assignment_id: Identifier | None = None
    deliverable_id: Identifier | None = None
    state_json: dict[str, Any]
    state_hash: Hash256
    previous_checkpoint_hash: Hash256 | None = None
    checkpoint_hash: Hash256
    created_at: datetime


class WorkflowEventRead(WorkflowReadModel):
    id: Identifier
    workflow_run_id: Identifier
    investigation_id: Identifier
    sequence_number: int
    event_type: WorkflowEventType
    node_name: WorkflowNode
    role_id: RoleId | None = None
    attribution_id: Identifier
    reason: str | None = None
    payload: dict[str, Any]
    previous_event_hash: Hash256 | None = None
    event_hash: Hash256
    occurred_at: datetime


class WorkflowModelCallRead(WorkflowReadModel):
    id: Identifier
    workflow_run_id: Identifier
    investigation_id: Identifier
    assignment_id: Identifier
    role_id: RoleId
    provider: ModelCallProvider
    model_name: str
    routing_category: str
    call_index: int
    max_calls_ceiling: int
    status: ModelCallStatus
    prompt_sha256: Hash256
    response_sha256: Hash256 | None = None
    input_tokens: int
    output_tokens: int
    error_detail: str | None = None
    recorded_at: datetime


class WorkflowRunRead(WorkflowReadModel):
    id: Identifier
    investigation_id: Identifier
    workflow_kind: str
    status: WorkflowStatus
    current_node: WorkflowNode
    provider_mode: WorkflowProviderMode
    idempotency_key: str | None = None
    lifecycle_version: int
    latest_checkpoint_seq: int
    latest_checkpoint_hash: Hash256 | None = None
    latest_event_hash: Hash256 | None = None
    blocked_reason: str | None = None
    abstained_reason: str | None = None
    cancelled_reason: str | None = None
    created_by_attribution_id: Identifier
    created_at: datetime
    updated_at: datetime

