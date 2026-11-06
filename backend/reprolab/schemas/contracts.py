"""ReproLab Core Hardened Contracts (Milestone 1).

Defines Pydantic V2 schemas for:
- EmpiricalClaimContract (with numeric range enforcement and Wilson ordering)
- ProtocolSpecificationContract (with SHA-256 hash validation)
- ExecutionRunContract (with exit code and metric dictionary)
- DeliberationCritiqueContract (with the 12 Constitutional Scientist roles)
- InvestigationCaseContract (with rail gauge score bounds and verdict categorization)
- Stage7HumanGateContract (with PI signature verification)
"""

from datetime import datetime
import re
from typing import Any, Dict, List, Literal, Tuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONSTITUTIONAL_ROLES = (
    "principal_investigator",
    "statistical_auditor",
    "experimental_protocolist",
    "data_provenance_officer",
    "computational_reproducibility_specialist",
    "peer_review_skeptic",
    "domain_methodologist",
    "code_quality_and_security_auditor",
    "literature_contextualizer",
    "meta_science_analyst",
    "ethics_and_biosafety_reviewer",
    "plain_language_and_multilingual_bridge",
)

ConstitutionalRole = Literal[
    "principal_investigator",
    "statistical_auditor",
    "experimental_protocolist",
    "data_provenance_officer",
    "computational_reproducibility_specialist",
    "peer_review_skeptic",
    "domain_methodologist",
    "code_quality_and_security_auditor",
    "literature_contextualizer",
    "meta_science_analyst",
    "ethics_and_biosafety_reviewer",
    "plain_language_and_multilingual_bridge",
]

MetricDirection = Literal["maximize", "minimize"]
ReproductionVerdict = Literal[
    "VERIFIED_REPRODUCED",
    "PARTIALLY_REPRODUCED",
    "FAILED_TO_REPRODUCE",
    "EXECUTION_FAILED",
    "PENDING",
]
CaseStatus = Literal[
    "draft",
    "in_intake",
    "claims_extracted",
    "protocol_locked",
    "executing",
    "deliberating",
    "paused_for_pi_review",
    "sealed",
    "rejected",
]
SentimentCategory = Literal[
    "reproduced",
    "partially_reproduced",
    "failed_to_reproduce",
    "flawed_methodology",
    "inconclusive",
]
GateDecision = Literal["approved", "rejected", "request_reexecution"]

SHA256_REGEX = re.compile(r"^[0-9a-fA-F]{64}$")


class EmpiricalClaimContract(BaseModel):
    """Hardened contract for an empirical scientific claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., description="Unique claim UUID")
    case_id: str = Field(..., description="Parent investigation case UUID")
    metric_name: str = Field(..., min_length=1, max_length=120)
    claimed_mean: float = Field(..., description="Reported mean / primary empirical measurement")
    claimed_ci_low: float | None = Field(default=None, description="Lower bound of confidence interval")
    claimed_ci_high: float | None = Field(default=None, description="Upper bound of confidence interval")
    baseline_value: float | None = Field(default=None, description="Reported baseline metric for comparison")
    baseline_model: str | None = Field(default=None, max_length=200)
    p_value: float | None = Field(default=None, ge=0.0, le=1.0, description="P-value if significance reported")
    sample_size: int | None = Field(default=None, ge=1, description="Sample size N")
    random_seed: int | None = Field(default=None)
    direction: MetricDirection = Field(default="maximize")

    @model_validator(mode="after")
    def validate_confidence_intervals(self):
        if self.claimed_ci_low is not None and self.claimed_ci_high is not None:
            if self.claimed_ci_low > self.claimed_ci_high:
                raise ValueError(
                    f"claimed_ci_low ({self.claimed_ci_low}) cannot exceed claimed_ci_high ({self.claimed_ci_high})"
                )
        return self


class ProtocolSpecificationContract(BaseModel):
    """Hardened contract for a deterministic execution protocol specification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spec_hash: str = Field(..., description="64-character SHA-256 hash of specification content")
    case_id: str = Field(..., description="Investigation case UUID")
    environment_name: str = Field(..., min_length=1, max_length=120)
    python_version: str = Field(default="3.13.12", min_length=1, max_length=20)
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Package to version mapping")
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    seed_list: List[int] = Field(default_factory=list)
    entrypoint: str = Field(default="reproduce.py", max_length=200)
    hardware_requirements: Dict[str, Any] | None = None

    @field_validator("spec_hash")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        if not SHA256_REGEX.match(v):
            raise ValueError(f"spec_hash must be a 64-character hexadecimal SHA-256 string, got: {v}")
        return v.lower()


class ExecutionRunContract(BaseModel):
    """Hardened contract for an individual container reproduction execution run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(..., description="Run UUID")
    case_id: str = Field(..., description="Case UUID")
    run_number: int = Field(..., ge=1)
    seed: int
    exit_code: int
    replicated_metrics: Dict[str, float] = Field(default_factory=dict)
    stdout_log: str = Field(default="")
    stderr_log: str = Field(default="")
    duration_ms: int = Field(default=0, ge=0)
    cpu_peak_pct: float | None = Field(default=None, ge=0.0)
    memory_peak_mb: float | None = Field(default=None, ge=0.0)


class DeliberationCritiqueContract(BaseModel):
    """Hardened contract for one of the 12 Constitutional Scientist persona reviews."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    critique_id: str = Field(..., description="Critique UUID")
    case_id: str = Field(..., description="Case UUID")
    persona_role: ConstitutionalRole = Field(..., description="One of the 12 constitutional roles")
    critique_markdown: str = Field(..., min_length=1)
    verdict_sentiment: SentimentCategory = Field(default="inconclusive")
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    citations: List[str] = Field(default_factory=list)


class InvestigationCaseContract(BaseModel):
    """Hardened contract for an end-to-end investigation case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(..., description="Case UUID")
    title: str = Field(..., min_length=1, max_length=500)
    paper_sha256: str = Field(..., description="SHA-256 hash of paper artifact")
    status: CaseStatus = Field(default="draft")
    rail_gauge_score: float | None = Field(default=None, ge=0.0, le=100.0)
    wilson_95_ci: Tuple[float, float] | None = None
    reproduction_verdict: ReproductionVerdict = Field(default="PENDING")
    dual_lens_hindi_summary: str | None = None
    created_at: datetime
    sealed_at: datetime | None = None

    @field_validator("paper_sha256")
    @classmethod
    def validate_paper_sha256(cls, v: str) -> str:
        if not SHA256_REGEX.match(v):
            raise ValueError(f"paper_sha256 must be a 64-character hexadecimal SHA-256 string, got: {v}")
        return v.lower()


class Stage7HumanGateContract(BaseModel):
    """Hardened contract for Stage 7 Human Review Gate sign-off."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(..., description="Case UUID")
    reviewer_id: str = Field(..., min_length=1, max_length=120)
    reviewer_role: str = Field(..., min_length=1, max_length=120)
    decision: GateDecision = Field(..., description="PI verification decision")
    review_notes: str = Field(default="", max_length=5000)
    signature_hash: str = Field(..., description="SHA-256 cryptographic signature of approval")
    reviewed_at: datetime

    @field_validator("signature_hash")
    @classmethod
    def validate_signature_hash(cls, v: str) -> str:
        if not SHA256_REGEX.match(v):
            raise ValueError(f"signature_hash must be a 64-character hexadecimal SHA-256 string, got: {v}")
        return v.lower()

