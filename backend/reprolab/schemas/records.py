from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from reprolab.scientists.registry import get_constitutions


Hash256 = str
RecordKind = Literal[
    "observation",
    "interpretation",
    "limitation",
    "unresolved_question",
    "resolution_note",
]
EvidenceRelationship = Literal["supports", "contradicts", "context"]
RelationKind = Literal["disputes", "responds_to", "addresses_question"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttributionInput(StrictModel):
    recorder_id: str | None = Field(default=None, max_length=200)
    recorder_label: str = Field(min_length=1, max_length=200)
    entry_method: Literal["manual_entry"] = "manual_entry"
    associated_role_id: str | None = Field(default=None, max_length=80)
    role_association_note: str | None = Field(default=None, max_length=2000)

    @field_validator("associated_role_id")
    @classmethod
    def validate_associated_role_id(cls, value: str | None) -> str | None:
        if value is not None and value not in get_constitutions():
            raise ValueError("associated_role_id is not a registered scientist role")
        return value

    @model_validator(mode="after")
    def validate_role_note(self):
        if self.associated_role_id is not None and not self.role_association_note:
            raise ValueError("role_association_note is required for an associated role")
        if self.associated_role_id is None and self.role_association_note is not None:
            raise ValueError("role_association_note requires associated_role_id")
        return self


class ConstitutionSnapshotRead(StrictModel):
    id: str
    role_id: str
    constitution_version: str
    constitution_json: dict[str, Any]
    constitution_hash: str
    created_at: datetime


class RecordAttributionRead(StrictModel):
    id: str
    investigation_id: str
    recorder_id: str | None
    recorder_label: str
    entry_method: str
    associated_role_id: str | None
    role_association_note: str | None
    identity_assurance: str
    constitution_snapshot: ConstitutionSnapshotRead | None
    created_at: datetime


class EvidenceLinkInput(StrictModel):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    evidence_item_id: str = Field(min_length=1, max_length=36)
    evidence_review_id: str | None = Field(default=None, max_length=36)
    relationship: EvidenceRelationship
    rationale: str = Field(min_length=1, max_length=5000)


class NumericAssertion(StrictModel):
    metric_name: str = Field(min_length=1, max_length=120)
    value: str = Field(
        pattern=r"^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$",
        max_length=80,
    )
    unit: str = Field(min_length=1, max_length=80)
    citation_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    source_lexeme: str = Field(min_length=1, max_length=200)
    normalization: Literal["identity", "percent_to_fraction"] = "identity"
    context: str = Field(min_length=1, max_length=2000)
    uncertainty_as_reported: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_span(self):
        if self.source_end <= self.source_start:
            raise ValueError("source_end must be greater than source_start")
        return self


class FindingAssertion(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    assertion_kind: Literal["source_reported", "interpretation", "uncertainty"]
    text: str = Field(min_length=1, max_length=10000)
    grounding: Literal["source_grounded", "unresolved"]
    citation_keys: list[str] = Field(default_factory=list, max_length=50)
    numbers: list[NumericAssertion] = Field(default_factory=list, max_length=50)
    unresolved_reason: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_grounding(self):
        if self.grounding == "source_grounded" and not self.citation_keys:
            raise ValueError("source_grounded assertions require citation_keys")
        if self.grounding == "unresolved" and not self.unresolved_reason:
            raise ValueError("unresolved assertions require unresolved_reason")
        if self.grounding == "unresolved" and self.numbers:
            raise ValueError("unresolved assertions cannot contain numeric assertions")
        return self


class FindingDefinition(StrictModel):
    record_kind: RecordKind
    title: str = Field(min_length=1, max_length=500)
    claim_id: str | None = Field(default=None, max_length=36)
    protocol_version_id: str | None = Field(default=None, max_length=36)
    assertions: list[FindingAssertion] = Field(min_length=1, max_length=100)
    evidence_links: list[EvidenceLinkInput] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_citations(self):
        assertion_keys = {assertion.key for assertion in self.assertions}
        if len(assertion_keys) != len(self.assertions):
            raise ValueError("finding assertion keys must be unique")
        citation_keys = {link.key for link in self.evidence_links}
        if len(citation_keys) != len(self.evidence_links):
            raise ValueError("finding evidence citation keys must be unique")
        missing = {
            citation
            for assertion in self.assertions
            for citation in assertion.citation_keys
            if citation not in citation_keys
        }
        if missing:
            raise ValueError(
                "finding assertions reference missing evidence citation keys: "
                + ", ".join(sorted(missing))
            )
        if any(assertion.numbers for assertion in self.assertions) and not self.evidence_links:
            raise ValueError("numeric assertions require evidence links")
        return self


class FindingCreate(StrictModel):
    attribution: AttributionInput
    finding: FindingDefinition


class FindingVersionCreate(StrictModel):
    attribution: AttributionInput
    finding: FindingDefinition
    parent_version_id: str = Field(min_length=1, max_length=36)


class FindingEvidenceLinkRead(StrictModel):
    id: str
    finding_version_id: str
    evidence_item_id: str
    investigation_id: str
    citation_key: str
    evidence_review_id: str | None
    relationship: str
    rationale: str
    source_snapshot_json: dict[str, Any]
    snapshot_hash: str
    created_at: datetime


class FindingVersionRead(StrictModel):
    id: str
    finding_id: str
    investigation_id: str
    parent_version_id: str | None
    version_number: int
    record_kind: str
    claim_id: str | None
    protocol_version_id: str | None
    schema_version: str
    canonical_content_json: dict[str, Any]
    content_hash: Hash256
    finding: FindingDefinition
    attribution: RecordAttributionRead
    evidence_links: list[FindingEvidenceLinkRead]
    created_at: datetime


class FindingSummary(StrictModel):
    id: str
    investigation_id: str
    latest_version_id: str
    latest_version_number: int
    record_kind: str
    title: str
    content_hash: Hash256
    created_at: datetime


class FindingRead(StrictModel):
    id: str
    investigation_id: str
    created_at: datetime
    versions: list[FindingVersionRead]


class RecordReviewCreate(StrictModel):
    attribution: AttributionInput
    expected_content_hash: Hash256 = Field(pattern=r"^[0-9a-f]{64}$")
    review_method: Literal["manual_review"] = "manual_review"
    outcome: Literal["accepted_for_inclusion", "needs_revision", "abstained"]
    notes: str = Field(min_length=1, max_length=5000)
    citations_checked: bool
    numeric_transcription_checked: bool | None = None
    limitations_checked: bool
    execution_wording_checked: bool
    dependency_disclosures: list[str] = Field(default_factory=list, max_length=50)


class RecordReviewRead(StrictModel):
    id: str
    investigation_id: str
    finding_version_id: str
    target_content_hash: Hash256
    reviewer_attribution: RecordAttributionRead
    review_method: str
    outcome: str
    notes: str
    citations_checked: bool
    numeric_transcription_checked: bool | None
    limitations_checked: bool
    execution_wording_checked: bool
    dependency_disclosures: list[str]
    reviewed_at: datetime


class FindingRelationCreate(StrictModel):
    attribution: AttributionInput
    from_finding_version_id: str = Field(min_length=1, max_length=36)
    to_finding_version_id: str = Field(min_length=1, max_length=36)
    relation_kind: RelationKind
    rationale: str = Field(min_length=1, max_length=5000)


class FindingRelationRead(StrictModel):
    id: str
    investigation_id: str
    from_finding_version_id: str
    to_finding_version_id: str
    relation_kind: str
    rationale: str
    attribution: RecordAttributionRead
    created_at: datetime
