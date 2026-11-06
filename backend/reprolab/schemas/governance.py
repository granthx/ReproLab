"""Pydantic contracts for the Stage 3 governed scientist boundary.

These models describe durable, auditable inputs and outputs.  They do not
start work, dispatch tools, grant permissions, or imply that a blocked
execution capability exists.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, model_validator

from reprolab.governance.contracts import get_contract, list_role_contracts, ContractStatus
from reprolab.schemas.records import AttributionInput, RecordReviewRead


HASH256_PATTERN = r"^[0-9a-f]{64}$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
ROLE_ID_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
CONTRACT_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$"
SEMVER_PATTERN = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"

Identifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=IDENTIFIER_PATTERN),
]
RoleId = Annotated[
    str,
    Field(min_length=2, max_length=64, pattern=ROLE_ID_PATTERN),
]
Hash256 = Annotated[str, Field(pattern=HASH256_PATTERN)]
ContractId = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=CONTRACT_ID_PATTERN),
]
ConstitutionVersion = Annotated[
    str,
    Field(min_length=5, max_length=64, pattern=SEMVER_PATTERN),
]
ShortText = Annotated[str, Field(min_length=1, max_length=5000, pattern=r"\S")]
MediumText = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


def canonical_json_hash(content: Any) -> str:
    """Hash JSON using ReproLab's existing canonical serialization rules."""

    try:
        serialized = json.dumps(
            content,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("content must be JSON serializable before it can be hashed") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class GovernanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GovernanceReadModel(GovernanceModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REVOKED = "revoked"
    BLOCKED = "blocked"
    ABSTAINED = "abstained"
    HANDED_OFF = "handed_off"
    DISPUTED = "disputed"
    NOT_REQUIRED = "not_required"


class AssignmentEventType(str, Enum):
    CREATED = "created"
    STARTED = "started"
    DELIVERABLE_SUBMITTED = "deliverable_submitted"
    COMPLETED = "completed"
    REVOKED = "revoked"
    BLOCKED = "blocked"
    ABSTAINED = "abstained"
    HANDED_OFF = "handed_off"
    DISPUTED = "disputed"
    NOT_REQUIRED = "not_required"


class DeliverableKind(str, Enum):
    ANALYSIS = "analysis"
    AUDIT = "audit"
    DATASET_MANIFEST = "dataset_manifest"
    EVIDENCE_VERIFICATION = "evidence_verification"
    IMPLEMENTATION_ASSESSMENT = "implementation_assessment"
    METHODOLOGY_ASSESSMENT = "methodology_assessment"
    REVIEW = "review"
    REPORT_DRAFT = "report_draft"


class DeliverableStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class ReferenceKind(str, Enum):
    INVESTIGATION = "investigation"
    PAPER = "paper"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    PROTOCOL = "protocol"
    ARTIFACT = "artifact"
    FINDING = "finding"
    REPORT = "report"
    ASSIGNMENT = "assignment"
    DELIVERABLE = "deliverable"
    REVIEW = "review"


class AbstentionReason(str, Enum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    MISSING_INPUT = "missing_input"
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_CONTRACT = "unsupported_contract"
    BLOCKED_CAPABILITY = "blocked_capability"
    SCOPE_EXCEEDED = "scope_exceeded"
    BUDGET_EXCEEDED = "budget_exceeded"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class HandoffReason(str, Enum):
    NEXT_ROLE_REQUIRED = "next_role_required"
    MISSING_CAPABILITY = "missing_capability"
    SCOPE_BOUNDARY = "scope_boundary"
    BLOCKED_DEPENDENCY = "blocked_dependency"
    REVIEW_REQUIRED = "review_required"
    DISAGREEMENT_REQUIRES_REVIEW = "disagreement_requires_review"


class DisagreementKind(str, Enum):
    FACTUAL = "factual"
    METHODOLOGICAL = "methodological"
    INTERPRETIVE = "interpretive"
    PROCEDURAL = "procedural"
    SCOPE = "scope"


class DisagreementStatus(str, Enum):
    OPEN = "open"
    UNRESOLVED = "unresolved"
    RESOLVED_BY_REVIEW = "resolved_by_review"


class ReviewDelegationStatus(str, Enum):
    ISSUED = "issued"
    REDEEMED = "redeemed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class GovernanceReference(GovernanceModel):
    """Exact record identity, never a latest-version lookup.

    finding/report/protocol IDs identify versions and require their canonical
    content hash; deliverables also require a content hash. Paper/artifact and
    evidence hashes pin stored SHA-256 digests. Kinds with no canonical digest
    reject supplied hashes in the service rather than silently ignoring them.
    """

    kind: ReferenceKind
    id: Identifier
    content_hash: Hash256 | None = None

    @model_validator(mode="after")
    def require_version_hash(self):
        if self.kind in {
            ReferenceKind.FINDING, ReferenceKind.REPORT,
            ReferenceKind.PROTOCOL, ReferenceKind.DELIVERABLE,
        } and self.content_hash is None:
            raise ValueError("canonical versioned record references require content_hash")
        return self


class ManualInputReferences(GovernanceModel):
    input_references: list[GovernanceReference] = Field(default_factory=list, max_length=100)


class ManualDeliverableContent(ManualInputReferences):
    """A bounded human-authored summary, with optional validated record refs."""

    kind: Identifier
    summary: ShortText

    @model_validator(mode="after")
    def validate_task(self):
        if self.kind not in {
            item.task_kind for item in list_role_contracts()
            if item.status is ContractStatus.AVAILABLE
        }:
            raise ValueError("deliverable kind must be a supported manual task")
        return self


class AssignmentBudget(GovernanceModel):
    max_model_calls: int = Field(ge=0, le=100, strict=True)
    max_input_tokens: int = Field(ge=0, le=2_000_000, strict=True)
    max_output_tokens: int = Field(ge=0, le=2_000_000, strict=True)


class AssignmentCreate(GovernanceModel):
    investigation_id: Identifier | None = None
    role_id: RoleId
    task_kind: Identifier | None = None
    constitution_version: ConstitutionVersion | None = None
    constitution_hash: Hash256 | None = None
    objective: MediumText
    input_contract: ContractId | None = None
    output_contract: ContractId | None = None
    input_references: list[GovernanceReference] = Field(default_factory=list, max_length=100)
    requested_by: Identifier | None = None
    budget: AssignmentBudget | None = None
    expires_at: datetime | None = None
    attribution: AttributionInput

    @model_validator(mode="after")
    def validate_constitution_pair(self):
        if (self.constitution_version is None) != (self.constitution_hash is None):
            raise ValueError("constitution_version and constitution_hash must be supplied together")
        return self

    @model_validator(mode="after")
    def validate_references(self):
        reference_ids = [(reference.kind, reference.id) for reference in self.input_references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("assignment input references must be unique")
        if self.input_contract is not None and self.output_contract is not None:
            if self.input_contract == self.output_contract:
                raise ValueError("assignment input and output contracts must be distinct")
        return self


class AssignmentRead(GovernanceReadModel):
    id: Identifier
    investigation_id: Identifier
    role_id: RoleId
    task_kind: Identifier
    constitution_version: ConstitutionVersion
    constitution_hash: Hash256
    objective: MediumText
    input_contract: ContractId | None = None
    output_contract: ContractId | None = None
    input_references: list[GovernanceReference] = Field(default_factory=list, max_length=100)
    requested_by: Identifier | None = None
    budget: AssignmentBudget | None = None
    status: AssignmentStatus
    lifecycle_version: int = Field(ge=1, le=1_000_000)
    last_event_hash: Hash256 | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    created_by_attribution_id: Identifier
    blocked_reason: str | None = None
    not_required_reason: str | None = None
    revoked_reason: str | None = None


_ALLOWED_TRANSITIONS: dict[AssignmentStatus, frozenset[AssignmentStatus]] = {
    AssignmentStatus.ASSIGNED: frozenset(
        {AssignmentStatus.IN_PROGRESS, AssignmentStatus.BLOCKED, AssignmentStatus.NOT_REQUIRED}
    ),
    AssignmentStatus.IN_PROGRESS: frozenset(
        {
            AssignmentStatus.COMPLETED,
            AssignmentStatus.REVOKED,
            AssignmentStatus.BLOCKED,
            AssignmentStatus.ABSTAINED,
            AssignmentStatus.HANDED_OFF,
            AssignmentStatus.DISPUTED,
        }
    ),
    AssignmentStatus.COMPLETED: frozenset({AssignmentStatus.REVOKED}),
    AssignmentStatus.REVOKED: frozenset(),
    AssignmentStatus.BLOCKED: frozenset(),
    AssignmentStatus.NOT_REQUIRED: frozenset(),
    AssignmentStatus.ABSTAINED: frozenset(),
    AssignmentStatus.HANDED_OFF: frozenset(),
    AssignmentStatus.DISPUTED: frozenset(),
}


class AssignmentTransitionRequest(GovernanceModel):
    assignment_id: Identifier | None = None
    from_status: AssignmentStatus
    to_status: AssignmentStatus
    expected_lifecycle_version: int = Field(ge=1, le=1_000_000)
    reason: ShortText | None = None
    actor_role_id: RoleId | None = None
    idempotency_key: Identifier | None = None
    attribution: AttributionInput

    @model_validator(mode="after")
    def validate_transition(self):
        if self.to_status == self.from_status:
            raise ValueError("assignment lifecycle transitions must change status")
        if self.to_status not in _ALLOWED_TRANSITIONS[self.from_status]:
            raise ValueError(
                f"invalid assignment transition: {self.from_status.value} -> {self.to_status.value}"
            )
        if self.to_status in {
            AssignmentStatus.BLOCKED,
            AssignmentStatus.ABSTAINED,
            AssignmentStatus.HANDED_OFF,
            AssignmentStatus.DISPUTED,
            AssignmentStatus.REVOKED,
            AssignmentStatus.NOT_REQUIRED,
        } and self.reason is None:
            raise ValueError(f"{self.to_status.value} transitions require a reason")
        return self


class AssignmentTransitionRead(GovernanceReadModel):
    id: Identifier
    assignment_id: Identifier
    from_status: AssignmentStatus
    to_status: AssignmentStatus
    lifecycle_version: int = Field(ge=1, le=1_000_000)
    reason: ShortText | None = None
    actor_role_id: RoleId | None = None
    attribution_id: Identifier
    event_hash: Hash256
    previous_event_hash: Hash256 | None = None
    occurred_at: datetime


class AssignmentEventCreate(GovernanceModel):
    assignment_id: Identifier
    event_type: AssignmentEventType
    from_status: AssignmentStatus | None = None
    to_status: AssignmentStatus | None = None
    actor_role_id: RoleId | None = None
    reason: ShortText | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_previous_event_hash: Hash256 | None = None
    attribution: AttributionInput

    @model_validator(mode="after")
    def validate_event(self):
        terminal_event_types = {
            AssignmentEventType.BLOCKED,
            AssignmentEventType.ABSTAINED,
            AssignmentEventType.HANDED_OFF,
            AssignmentEventType.DISPUTED,
            AssignmentEventType.REVOKED,
            AssignmentEventType.NOT_REQUIRED,
        }
        if self.event_type is AssignmentEventType.CREATED and self.from_status is not None:
            raise ValueError("created events cannot have a from_status")
        if self.event_type is not AssignmentEventType.CREATED and self.to_status is None:
            raise ValueError("non-created assignment events require to_status")
        if self.event_type in terminal_event_types and self.reason is None:
            raise ValueError(f"{self.event_type.value} events require a reason")
        return self


class AssignmentEventRead(GovernanceReadModel):
    id: Identifier
    assignment_id: Identifier
    sequence_number: int = Field(ge=1, le=1_000_000)
    event_type: AssignmentEventType
    from_status: AssignmentStatus | None = None
    to_status: AssignmentStatus | None = None
    actor_role_id: RoleId | None = None
    attribution_id: Identifier
    reason: ShortText | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    event_hash: Hash256
    previous_event_hash: Hash256 | None = None
    occurred_at: datetime


class DeliverableCreate(GovernanceModel):
    assignment_id: Identifier
    kind: DeliverableKind
    schema_name: ContractId = Field(
        validation_alias=AliasChoices("schema_name", "contract_id", "output_contract")
    )
    content: dict[str, Any]
    content_hash: Hash256
    input_references: list[GovernanceReference] = Field(default_factory=list, max_length=100)
    limitations: list[ShortText] = Field(default_factory=list, max_length=100)
    attribution: AttributionInput

    @model_validator(mode="after")
    def validate_content(self):
        parse_deliverable_content(self.schema_name, self.content)
        reference_ids = [(reference.kind, reference.id) for reference in self.input_references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("deliverable input references must be unique")
        if canonical_json_hash(self.content) != self.content_hash:
            raise ValueError("deliverable content_hash does not match canonical content")
        return self


class DeliverableRead(GovernanceReadModel):
    id: Identifier
    assignment_id: Identifier
    kind: DeliverableKind
    schema_name: ContractId
    status: DeliverableStatus
    content: dict[str, Any]
    content_hash: Hash256
    input_references: list[GovernanceReference] = Field(default_factory=list, max_length=100)
    limitations: list[ShortText] = Field(default_factory=list, max_length=100)
    created_at: datetime
    updated_at: datetime
    created_by_attribution_id: Identifier

    @model_validator(mode="after")
    def validate_content(self):
        if canonical_json_hash(self.content) != self.content_hash:
            raise ValueError("deliverable content_hash does not match canonical content")
        return self


class GovernedOutput(GovernanceModel):
    assignment_id: Identifier
    role_id: RoleId
    summary: ShortText
    input_references: list[GovernanceReference] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_references(self):
        reference_ids = [(reference.kind, reference.id) for reference in self.input_references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("governed output input references must be unique")
        return self


class AbstentionOutput(GovernedOutput):
    kind: Literal["abstention"] = "abstention"
    reason: AbstentionReason
    # Existing records whose information is missing/insufficient/invalid, not
    # invented IDs. Describe entirely absent inputs in required_action.
    missing_references: list[GovernanceReference] = Field(default_factory=list, max_length=50)
    required_action: ShortText

    @model_validator(mode="after")
    def validate_missing_inputs(self):
        if self.reason in {
            AbstentionReason.INSUFFICIENT_EVIDENCE,
            AbstentionReason.MISSING_INPUT,
            AbstentionReason.INVALID_INPUT,
        } and not self.missing_references:
            raise ValueError(f"{self.reason.value} abstentions require missing_references")
        return self


class HandoffOutput(GovernedOutput):
    kind: Literal["handoff"] = "handoff"
    target_role_id: RoleId
    reason: HandoffReason
    handoff_instructions: ShortText
    # IDs of submitted disagreement deliverables in the same investigation.
    preserved_disagreement_ids: list[Identifier] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_target(self):
        if self.target_role_id == self.role_id:
            raise ValueError("handoff target_role_id must differ from the current role_id")
        return self


class DisagreementOutput(GovernedOutput):
    kind: Literal["disagreement"] = "disagreement"
    disagreement_kind: DisagreementKind
    subject: ShortText
    position: ShortText
    alternative_position: ShortText
    basis_references: list[GovernanceReference] = Field(min_length=1, max_length=50)
    status: DisagreementStatus = DisagreementStatus.OPEN
    requested_review_role_id: RoleId | None = None

    @model_validator(mode="after")
    def validate_positions(self):
        if self.position.strip() == self.alternative_position.strip():
            raise ValueError("disagreement positions must preserve genuinely distinct alternatives")
        return self


def parse_deliverable_content(schema_name: str, content: dict[str, Any]) -> GovernanceModel:
    """Parse the actual bounded content, independently of its outer envelope.

    Preserve caller JSON for hashing; defaults in parsed objects do not rewrite
    the signed content. Available API verbs are not deliverable schemas.
    """

    schemas = {
        "deliverable": ManualDeliverableContent,
        "abstention": AbstentionOutput,
        "handoff": HandoffOutput,
        "disagreement": DisagreementOutput,
    }
    schema = schemas.get(get_contract(schema_name).contract_id)
    if schema is None:
        raise ValueError("schema_name must name a bounded manual output contract")
    return schema.model_validate(content)


class ReviewDelegationTarget(GovernanceModel):
    kind: Literal["finding_version_review"] = "finding_version_review"
    finding_version_id: Identifier
    finding_id: Identifier
    content_hash: Hash256


class ReviewDelegationIssue(GovernanceModel):
    assignment_id: Identifier
    reviewer_role_id: RoleId = Field(
        validation_alias=AliasChoices("reviewer_role_id", "delegate_role_id")
    )
    target: ReviewDelegationTarget
    expires_at: datetime
    max_uses: int = Field(default=1, ge=1, le=10)
    issued_by_role_id: RoleId | None = None
    attribution: AttributionInput


class ReviewDelegationRead(GovernanceReadModel):
    id: Identifier
    assignment_id: Identifier
    reviewer_role_id: RoleId
    target: ReviewDelegationTarget
    delegation_hash: Hash256
    status: ReviewDelegationStatus
    issued_by_role_id: RoleId | None = None
    issued_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None = None
    revoked_at: datetime | None = None
    lifecycle_version: int = Field(ge=1, le=1_000_000)
    max_uses: int = Field(ge=1, le=10)
    use_count: int = Field(ge=0, le=10)


class ReviewDelegationIssuedRead(ReviewDelegationRead):
    token: str = Field(min_length=32, max_length=512)


class ReviewDelegationRevoke(GovernanceModel):
    delegation_id: Identifier
    reason: ShortText
    expected_lifecycle_version: int = Field(
        ge=1,
        le=1_000_000,
        validation_alias=AliasChoices(
            "expected_lifecycle_version", "expected_version"
        ),
    )
    revoked_by_role_id: RoleId | None = None
    attribution: AttributionInput


class ReviewDelegationRedeem(GovernanceModel):
    delegation_id: Identifier
    token: str = Field(min_length=32, max_length=512)
    expected_content_hash: Hash256
    outcome: Literal["accepted_for_inclusion", "needs_revision", "abstained"]
    notes: ShortText
    citations_checked: bool
    numeric_transcription_checked: bool | None = None
    limitations_checked: bool
    execution_wording_checked: bool
    dependency_disclosures: list[ShortText] = Field(default_factory=list, max_length=50)
    attribution: AttributionInput

    @model_validator(mode="wrap")
    @classmethod
    def redact_invalid_request_inputs(cls, value, handler):
        """Do not let request-validation responses echo a bearer token.

        Root/missing-field errors can otherwise include the entire request,
        even when the error is unrelated to the token field itself.
        """

        try:
            return handler(value)
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                cls.__name__, exc.errors(include_input=False, include_url=False),
            ) from None


class ReviewDelegationRedeemRead(GovernanceReadModel):
    delegation: ReviewDelegationRead
    review: RecordReviewRead


# Public aliases keep the vocabulary usable by callers that refer to the
# generic lifecycle/event or request names while retaining one validation model.
AssignmentTransition = AssignmentTransitionRequest
LifecycleTransition = AssignmentTransitionRequest
LifecycleTransitionRequest = AssignmentTransitionRequest
LifecycleEventCreate = AssignmentEventCreate
LifecycleEventRead = AssignmentEventRead
AssignmentEvent = AssignmentEventRead
LifecycleEvent = AssignmentEventRead
DeliverableOutput = DeliverableCreate
AbstentionRecord = AbstentionOutput
HandoffRecord = HandoffOutput
DisagreementRecord = DisagreementOutput
ReviewDelegationIssueRequest = ReviewDelegationIssue
ReviewDelegationRevokeRequest = ReviewDelegationRevoke
ReviewDelegationRedeemRequest = ReviewDelegationRedeem


__all__ = [
    "AbstentionOutput",
    "AbstentionReason",
    "AssignmentBudget",
    "AssignmentCreate",
    "AssignmentEventCreate",
    "AssignmentEvent",
    "AssignmentEventRead",
    "AssignmentEventType",
    "AssignmentRead",
    "AssignmentStatus",
    "AssignmentTransition",
    "AssignmentTransitionRead",
    "AssignmentTransitionRequest",
    "AbstentionRecord",
    "ConstitutionVersion",
    "ContractId",
    "DisagreementKind",
    "DisagreementOutput",
    "DisagreementRecord",
    "DisagreementStatus",
    "DeliverableCreate",
    "DeliverableKind",
    "DeliverableOutput",
    "DeliverableRead",
    "DeliverableStatus",
    "GovernanceModel",
    "GovernanceReadModel",
    "GovernanceReference",
    "ManualInputReferences",
    "ManualDeliverableContent",
    "HandoffOutput",
    "HandoffRecord",
    "HandoffReason",
    "Hash256",
    "LifecycleEventCreate",
    "LifecycleEventRead",
    "LifecycleEvent",
    "LifecycleTransition",
    "LifecycleTransitionRequest",
    "ReferenceKind",
    "ReviewDelegationIssue",
    "ReviewDelegationIssueRequest",
    "ReviewDelegationIssuedRead",
    "ReviewDelegationRead",
    "ReviewDelegationRedeem",
    "ReviewDelegationRedeemRequest",
    "ReviewDelegationRedeemRead",
    "ReviewDelegationRevoke",
    "ReviewDelegationRevokeRequest",
    "ReviewDelegationTarget",
    "ReviewDelegationStatus",
    "canonical_json_hash",
    "parse_deliverable_content",
]
