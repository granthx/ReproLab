from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


SourceKind = Literal["paper", "synthetic_framework_test"]
MetricDirection = Literal["maximize", "minimize"]
VerificationStatus = Literal["unverified", "verified", "rejected"]


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)
    source_kind: SourceKind
    paper_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_kind == "paper" and self.paper_id is None:
            raise ValueError("paper investigations require paper_id")
        if self.source_kind == "synthetic_framework_test" and self.paper_id is not None:
            raise ValueError("synthetic framework tests cannot reference a paper")
        return self


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    paper_id: str | None
    name: str
    source_kind: str
    status: str
    execution_status: str
    claim_assessment: str
    created_at: datetime
    updated_at: datetime


class RailMetrics(BaseModel):
    claimed_mean: float | None = None
    replicated_mean: float | None = None
    wilson_ci_lower: float | None = None
    wilson_ci_upper: float | None = None
    sample_size: int | None = None
    metric_name: str = "accuracy"


class InvestigationSummaryRead(BaseModel):
    investigation_id: str
    name: str
    source_kind: str
    status: str
    execution_status: str
    claim_assessment: str
    reproduction_verdict: str
    plain_english_summary: str
    plain_hindi_summary: str
    technical_dossier_en: str
    technical_dossier_hi: str
    rail_metrics: RailMetrics


class ClaimCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=10000)
    metric_name: str = Field(min_length=1, max_length=120)
    reported_value: float | None = None
    metric_direction: MetricDirection
    source_kind: SourceKind
    source_locator: str | None = Field(default=None, max_length=500)
    published: bool = False

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_kind == "paper" and (not self.published or not self.source_locator):
            raise ValueError("published paper claims require published=true and source_locator")
        if self.source_kind == "synthetic_framework_test" and self.published:
            raise ValueError("synthetic framework tests cannot contain published claims")
        return self


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    investigation_id: str
    statement: str
    metric_name: str
    reported_value: float | None
    metric_direction: str
    source_kind: str
    source_locator: str | None
    published: bool
    verification_status: str
    created_at: datetime


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str | None = None
    artifact_id: str | None = None
    source_url: HttpUrl | None = None
    source_locator: str = Field(min_length=1, max_length=500)
    quoted_text: str | None = Field(default=None, max_length=30000)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_reference(self):
        if self.artifact_id is None and self.source_url is None:
            raise ValueError("evidence requires artifact_id or source_url")
        return self


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    investigation_id: str
    claim_id: str | None
    artifact_id: str | None
    source_url: str | None
    source_locator: str
    quoted_text: str | None
    sha256: str | None
    verification_status: str
    verification_notes: str | None
    created_at: datetime


class EvidenceReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_method: Literal["manual_review", "artifact_hash_check", "source_snapshot_check", "automated_locator_check"]
    outcome: Literal["accepted_for_protocol", "rejected", "unresolved"]
    reviewer_id: str | None = Field(default=None, max_length=200)
    reviewer_label: str | None = Field(default=None, max_length=200)
    notes: str = Field(min_length=1, max_length=5000)
    source_snapshot_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_attribution(self):
        if self.reviewer_id is None and self.reviewer_label is None:
            raise ValueError("evidence reviews require reviewer attribution")
        if self.review_method == "source_snapshot_check" and self.source_snapshot_hash is None:
            raise ValueError("source_snapshot_check requires source_snapshot_hash")
        return self


class EvidenceReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    evidence_item_id: str
    review_method: str
    outcome: str
    reviewer_id: str | None
    reviewer_label: str | None
    notes: str
    source_snapshot_hash: str | None
    reviewed_at: datetime


class ResearchArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    investigation_id: str
    protocol_version_id: str
    kind: str
    storage_key: str
    sha256: str
    size_bytes: int
    content_type: str
    producer: str
    provenance_json: dict[str, Any]
    created_at: datetime


class EvidenceVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str = Field(min_length=1, max_length=5000)


class DatasetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    version: str = Field(min_length=1, max_length=120)
    source_url: HttpUrl | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str = Field(min_length=1, max_length=300)


class DatasetSplit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(min_length=1, max_length=200)
    train_fraction: float = Field(gt=0, lt=1)
    test_fraction: float = Field(gt=0, lt=1)
    random_seed: int = Field(ge=0)
    split_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fraction(self):
        if self.train_fraction + self.test_fraction > 1:
            raise ValueError("train_fraction + test_fraction cannot exceed 1")
        return self


class PreprocessingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(min_length=1, max_length=50)
    fit_on_training_only: bool


class ImplementationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["author_code_rerun", "independent_reimplementation", "synthetic_adapter", "tabular_adapter"]
    adapter_version: str | None = Field(default=None, max_length=200)
    repository_url: HttpUrl | None = None
    commit_hash: str | None = None
    code_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    deviations: list[str] = Field(default_factory=list, max_length=50)


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    hyperparameters: dict[str, Any]


class PrimaryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    direction: MetricDirection
    unit: str = Field(min_length=1, max_length=80)
    analysis_unit: str = Field(min_length=1, max_length=200)


class ReportedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None
    source_locator: str = Field(min_length=1, max_length=500)
    is_published: bool


class ComparisonRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["absolute_tolerance", "relative_tolerance", "interval_overlap", "not_applicable"]
    tolerance: float | None = Field(default=None, ge=0)
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_tolerance(self):
        if self.method in {"absolute_tolerance", "relative_tolerance"} and self.tolerance is None:
            raise ValueError(f"{self.method} requires tolerance")
        if self.method == "not_applicable" and self.tolerance is not None:
            raise ValueError("not_applicable cannot define tolerance")
        return self


class StatisticalAnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = Field(min_length=1, max_length=300)
    confidence_level: float = Field(gt=0, lt=1)
    repetitions: int = Field(ge=1, le=100)
    seed_unit: str = Field(min_length=1, max_length=200)


class ResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_millis: int = Field(gt=0, le=16000)
    memory_mb: int = Field(gt=0, le=65536)
    wall_time_seconds: int = Field(gt=0, le=86400)
    max_output_bytes: int = Field(gt=0, le=1024 * 1024 * 1024)


class StoppingRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(ge=1, le=20)
    timeout_action: Literal["stop_and_mark_timeout", "retry_once_then_stop"]


class ProtocolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: SourceKind
    experiment_type: str | None = Field(default=None, pattern=r"^[a-z0-9_]+_v[0-9]+$")
    paper_id: str | None = None
    claim_id: str = Field(min_length=1)
    claim_text: str = Field(min_length=1, max_length=10000)
    evidence_reference_ids: list[str] = Field(min_length=1, max_length=50)
    dataset: DatasetIdentity
    split: DatasetSplit
    preprocessing: PreprocessingSpec
    implementation: ImplementationSpec
    model: ModelSpec
    random_seeds: list[int] = Field(min_length=1, max_length=100)
    primary_metric: PrimaryMetric
    reported_result: ReportedResult
    comparison: ComparisonRule
    statistical_analysis: StatisticalAnalysisPlan
    resource_limits: ResourceLimits
    stopping_rules: StoppingRules
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=100)
    known_deviations: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_source_and_result(self):
        if self.source_kind == "paper":
            if self.paper_id is None:
                raise ValueError("paper protocols require paper_id")
            if not self.reported_result.is_published or self.reported_result.value is None:
                raise ValueError("paper protocols require a published reported result")
            if self.implementation.mode == "synthetic_adapter":
                raise ValueError("paper protocols cannot use synthetic_adapter")
        else:
            if self.paper_id is not None:
                raise ValueError("synthetic protocols cannot reference a paper")
            if self.reported_result.is_published:
                raise ValueError("synthetic protocols cannot mark results as published")
            if self.implementation.mode not in ("synthetic_adapter", "tabular_adapter"):
                raise ValueError("synthetic protocols require synthetic_adapter or tabular_adapter")
            if self.experiment_type is None:
                # Preserve Phase 2A payload compatibility while assigning the only
                # currently allowlisted synthetic experiment explicitly.
                self.experiment_type = "synthetic_binary_classification_v1"
            if self.experiment_type not in ("synthetic_binary_classification_v1", "tabular_benchmark_classification_v1"):
                raise ValueError(
                    f"Unsupported synthetic experiment type '{self.experiment_type}'. "
                    "Must be 'synthetic_binary_classification_v1' or 'tabular_benchmark_classification_v1'."
                )
        return self


class ProtocolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: ProtocolDefinition
    parent_protocol_id: str | None = None


class ProtocolRead(BaseModel):
    id: str
    investigation_id: str
    parent_protocol_id: str | None
    version_number: int
    status: str
    protocol_hash: str
    protocol: dict[str, Any]
    approved_by: str | None
    approved_at: datetime | None
    frozen_at: datetime | None
    created_at: datetime


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_by: str = Field(min_length=1, max_length=200)
