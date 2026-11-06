from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, model_validator

from reprolab.schemas.records import AttributionInput, FindingDefinition, Hash256, RecordAttributionRead, StrictModel


ReportText = Annotated[str, Field(min_length=1, max_length=5000, pattern=r"\S")]
RecordId = Annotated[str, Field(min_length=1, max_length=36)]


ReportDisposition = Literal["included", "excluded_with_reason"]
ReportEventType = Literal["published", "withdrawn"]


class ReportClaimSnapshot(StrictModel):
    id: RecordId
    statement: str
    metric_name: str
    reported_value: float | None
    metric_direction: str
    source_kind: str
    source_locator: str | None
    published: bool
    verification_status: str


class ReportEvidenceSnapshot(StrictModel):
    citation_key: str
    relationship: Literal["supports", "contradicts", "context"]
    rationale: str
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshot: dict[str, Any]


class ReportFindingSnapshot(StrictModel):
    finding_version_id: RecordId
    finding_id: RecordId
    finding_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    finding: FindingDefinition
    attribution: RecordAttributionRead
    evidence_snapshots: list[ReportEvidenceSnapshot] = Field(max_length=100)


class ReportInvestigationSnapshot(StrictModel):
    id: RecordId
    source_kind: Literal["paper", "synthetic_framework_test"]
    paper_id: str | None
    execution_status: Literal["not_started"]
    claim_assessment: Literal["not_assessed", "framework_test_only"]


class ReportSourceContext(StrictModel):
    investigation: ReportInvestigationSnapshot
    claims: list[ReportClaimSnapshot] = Field(max_length=100)
    findings: list[ReportFindingSnapshot] = Field(max_length=500)


class ReportFindingLinkInput(StrictModel):
    finding_version_id: str = Field(min_length=1, max_length=36)
    finding_content_hash: Hash256 = Field(
        pattern=r"^[0-9a-f]{64}$",
        validation_alias=AliasChoices(
            "finding_content_hash", "content_hash", "expected_content_hash"
        ),
    )
    section: str = Field(min_length=1, max_length=120, pattern=r"\S")
    position: int = Field(ge=0)
    disposition: ReportDisposition
    exclusion_reason: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_disposition(self):
        if self.disposition == "excluded_with_reason" and not (self.exclusion_reason or "").strip():
            raise ValueError("excluded_with_reason selections require exclusion_reason")
        if self.disposition == "included" and self.exclusion_reason is not None:
            raise ValueError("included selections cannot have exclusion_reason")
        return self


class ReportVersionDefinition(StrictModel):
    report_kind: Literal["analysis_record"] = "analysis_record"
    title: str = Field(min_length=1, max_length=500, pattern=r"\S")
    scope_claim_ids: list[RecordId] = Field(default_factory=list, max_length=100)
    finding_links: list[ReportFindingLinkInput] = Field(
        default_factory=list,
        max_length=500,
        validation_alias=AliasChoices(
            "finding_links", "findings", "selected_findings"
        ),
    )
    limitations: list[ReportText] = Field(default_factory=list, max_length=100)
    unresolved_questions: list[ReportText] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_selections(self):
        if len(self.scope_claim_ids) != len(set(self.scope_claim_ids)):
            raise ValueError("scope_claim_ids must be unique")
        finding_ids = [link.finding_version_id for link in self.finding_links]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("a report cannot select the same finding version twice")
        positions = [(link.section, link.position) for link in self.finding_links]
        if len(positions) != len(set(positions)):
            raise ValueError("finding link section and position pairs must be unique")
        return self


class ReportCreate(StrictModel):
    attribution: AttributionInput
    title: str | None = None
    report_kind: Literal["analysis_record"] = "analysis_record"
    scope_claim_ids: list[RecordId] = Field(default_factory=list, max_length=100)
    finding_links: list[ReportFindingLinkInput] = Field(
        default_factory=list,
        max_length=500,
        validation_alias=AliasChoices(
            "finding_links", "findings", "selected_findings"
        ),
    )
    limitations: list[ReportText] = Field(default_factory=list, max_length=100)
    unresolved_questions: list[ReportText] = Field(default_factory=list, max_length=100)
    version: ReportVersionDefinition | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        flat_fields = {"title", "report_kind", "scope_claim_ids", "finding_links", "limitations", "unresolved_questions"}
        if self.version is not None and self.model_fields_set & flat_fields:
            raise ValueError("provide either version or flat report fields, not both")
        if self.version is None and self.title is None:
            raise ValueError("report title is required when version is not provided")
        if self.title is not None:
            definition = ReportVersionDefinition(
                report_kind=self.report_kind,
                title=self.title,
                scope_claim_ids=self.scope_claim_ids,
                finding_links=self.finding_links,
                limitations=self.limitations,
                unresolved_questions=self.unresolved_questions,
            )
            self.version = definition
        return self


class ReportVersionCreate(StrictModel):
    attribution: AttributionInput
    parent_version_id: str = Field(min_length=1, max_length=36)
    version: ReportVersionDefinition | None = None
    report_kind: Literal["analysis_record"] = "analysis_record"
    title: str | None = None
    scope_claim_ids: list[RecordId] = Field(default_factory=list, max_length=100)
    finding_links: list[ReportFindingLinkInput] = Field(
        default_factory=list,
        max_length=500,
        validation_alias=AliasChoices(
            "finding_links", "findings", "selected_findings"
        ),
    )
    limitations: list[ReportText] = Field(default_factory=list, max_length=100)
    unresolved_questions: list[ReportText] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_shape(self):
        flat_fields = {"title", "report_kind", "scope_claim_ids", "finding_links", "limitations", "unresolved_questions"}
        if self.version is not None and self.model_fields_set & flat_fields:
            raise ValueError("provide either version or flat report fields, not both")
        if self.version is None and self.title is None:
            raise ValueError("report title is required when version is not provided")
        if self.title is not None:
            self.version = ReportVersionDefinition(
                report_kind=self.report_kind,
                title=self.title,
                scope_claim_ids=self.scope_claim_ids,
                finding_links=self.finding_links,
                limitations=self.limitations,
                unresolved_questions=self.unresolved_questions,
            )
        return self


class ReportEventCreate(StrictModel):
    attribution: AttributionInput
    event_type: ReportEventType
    report_version_id: str | None = Field(default=None, max_length=36)
    notes: str = Field(min_length=1, max_length=5000)


class ReportTransitionRequest(StrictModel):
    attribution: AttributionInput
    report_version_id: str | None = Field(default=None, max_length=36)
    notes: str = Field(min_length=1, max_length=5000)


class ReportExportRead(StrictModel):
    id: str
    report_version_id: str
    investigation_id: str
    report_content_hash: Hash256
    json_size_bytes: int
    markdown_size_bytes: int
    json_sha256: Hash256
    markdown_sha256: Hash256
    created_at: datetime


class ReportEventRead(StrictModel):
    id: str
    report_id: str
    report_version_id: str
    investigation_id: str
    event_type: str
    sequence_number: int
    target_content_hash: Hash256
    attribution: RecordAttributionRead
    notes: str
    created_at: datetime


class ReportFindingLinkRead(StrictModel):
    id: str
    report_version_id: str
    finding_version_id: str
    investigation_id: str
    finding_content_hash: Hash256
    section: str
    position: int
    disposition: str
    exclusion_reason: str | None
    created_at: datetime


class ReportVersionRead(StrictModel):
    id: str
    report_id: str
    investigation_id: str
    parent_version_id: str | None
    version_number: int
    report_kind: str
    title: str
    scope_claim_ids: list[str]
    limitations: list[str]
    unresolved_questions: list[str]
    schema_version: str
    canonical_content_json: dict[str, Any]
    content_hash: Hash256
    finding_links: list[ReportFindingLinkRead]
    attribution: RecordAttributionRead
    created_at: datetime


class ReportRead(StrictModel):
    id: str
    investigation_id: str
    status: str
    created_by_attribution: RecordAttributionRead
    versions: list[ReportVersionRead]
    events: list[ReportEventRead]
    created_at: datetime
