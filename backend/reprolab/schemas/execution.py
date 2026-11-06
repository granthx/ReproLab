"""Pydantic contracts for Stage 6 isolated experiment execution and trusted scoring."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from reprolab.schemas.governance import Hash256, Identifier, MediumText
from reprolab.schemas.records import AttributionInput


class ExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutionReadModel(ExecutionModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class AttemptStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ExecutionEventType(str, Enum):
    JOB_SUBMITTED = "job_submitted"
    ATTEMPT_STARTED = "attempt_started"
    ATTEMPT_FINISHED = "attempt_finished"
    ARTIFACTS_COLLECTED = "artifacts_collected"
    SCORING_COMPLETED = "scoring_completed"
    JOB_CANCELLED = "job_cancelled"
    JOB_TIMEOUT = "job_timeout"


class ExperimentJobCreate(ExecutionModel):
    protocol_version_id: Identifier
    submission_key: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
    attribution: AttributionInput


class ExperimentJobCancel(ExecutionModel):
    expected_lifecycle_version: Annotated[int, Field(ge=1)]
    reason: MediumText
    attribution: AttributionInput


class AttemptRecordRead(ExecutionReadModel):
    id: Identifier
    job_id: Identifier
    investigation_id: Identifier
    attempt_number: int
    status: AttemptStatus
    exit_code: int | None = None
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    output_artifact_ids: list[str] | None = None
    resource_usage_json: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime | None = None


class ExecutionEventRead(ExecutionReadModel):
    id: Identifier
    job_id: Identifier
    investigation_id: Identifier
    attempt_id: Identifier | None = None
    sequence_number: int
    event_type: ExecutionEventType
    reason: str | None = None
    payload: dict[str, Any]
    event_hash: Hash256
    previous_event_hash: Hash256 | None = None
    occurred_at: datetime


class ProductionMeasurementRead(ExecutionReadModel):
    id: Identifier
    investigation_id: Identifier
    job_id: Identifier
    attempt_id: Identifier
    metric_name: str
    value: float
    unit: str
    sample_size: int
    analysis_unit: str
    confidence_level: float
    interval_lower: float
    interval_upper: float
    scoring_method: str
    scorer_version: str
    prediction_artifact_sha256: Hash256
    manifest_artifact_sha256: Hash256
    protocol_hash: Hash256
    recorded_at: datetime


class ExperimentJobRead(ExecutionReadModel):
    id: Identifier
    investigation_id: Identifier
    protocol_version_id: Identifier
    submission_key: str
    status: JobStatus
    lifecycle_version: int
    execution_bundle_hash: Hash256
    created_by_attribution_id: Identifier
    cancellation_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    attempts: list[AttemptRecordRead] = Field(default_factory=list)
    measurements: list[ProductionMeasurementRead] = Field(default_factory=list)

