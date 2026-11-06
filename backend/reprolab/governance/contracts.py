"""Static, explicit governance contract registry for Stage 3.

This module is an allowlist of *contract shapes*, not a dispatcher.  In
particular, it intentionally does not load ``constitutions.yaml``.  Names in
that file are declarations and cannot implicitly become permissions or tools.
Runtime permission checks and implementations are future work and must make a
separate explicit entry here before they can be considered available.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final, Mapping


class ContractStatus(str, Enum):
    """Availability of a governed contract in the current application."""

    AVAILABLE = "available"
    BLOCKED_CAPABILITY = "blocked_capability"
    UNSUPPORTED_CONTRACT = "unsupported_contract"


# These aliases make the status vocabulary explicit for callers that use
# "availability" terminology, without introducing a second set of values.
ContractAvailability = ContractStatus


@dataclass(frozen=True, slots=True)
class GovernedContract:
    """Static metadata for one explicitly known governance contract.

    ``permissions`` and ``tools`` are intentionally empty for every current
    entry.  They are metadata fields for a future reviewed implementation, not
    a projection of the YAML constitution declarations.
    """

    contract_id: str
    status: ContractStatus
    input_schema: str | None = None
    output_schema: str | None = None
    capability: str | None = None
    permissions: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()

    @property
    def availability(self) -> ContractStatus:
        """Compatibility name for callers that describe status as availability."""

        return self.status

    @property
    def allowed_permissions(self) -> tuple[str, ...]:
        """Explicit permissions attached to this contract, if any."""

        return self.permissions

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        """Explicit tools attached to this contract, if any."""

        return self.tools


@dataclass(frozen=True, slots=True)
class RoleContract:
    """Explicit mapping from a registered role to one bounded record task."""

    role_id: str
    task_kind: str
    contract_id: str
    input_schema: str
    output_schema: str
    status: ContractStatus
    capability: str | None = None


GovernanceContract = GovernedContract
ContractDefinition = GovernedContract


def _available(
    contract_id: str,
    *,
    input_schema: str | None = None,
    output_schema: str | None = None,
) -> GovernedContract:
    return GovernedContract(
        contract_id=contract_id,
        status=ContractStatus.AVAILABLE,
        input_schema=input_schema,
        output_schema=output_schema,
    )


def _blocked(contract_id: str, capability: str) -> GovernedContract:
    return GovernedContract(
        contract_id=contract_id,
        status=ContractStatus.BLOCKED_CAPABILITY,
        capability=capability,
    )


# These are schema contracts only.  No entry here grants a role a permission or
# tool, and the names are maintained independently of constitutions.yaml.
_SUPPORTED_CONTRACTS: dict[str, GovernedContract] = {
    "manual.input": _available(
        "manual.input", input_schema="ManualInputReferences",
    ),
    "manual.task": _available(
        "manual.task", input_schema="ManualInputReferences", output_schema="ManualDeliverableContent",
    ),
    "assignment.create": _available(
        "assignment.create",
        input_schema="AssignmentCreate",
        output_schema="AssignmentRead",
    ),
    "assignment.read": _available(
        "assignment.read",
        output_schema="AssignmentRead",
    ),
    "assignment.transition": _available(
        "assignment.transition",
        input_schema="AssignmentTransitionRequest",
        output_schema="AssignmentTransitionRead",
    ),
    "assignment.event": _available(
        "assignment.event",
        input_schema="AssignmentEventCreate",
        output_schema="AssignmentEventRead",
    ),
    "deliverable": _available(
        "deliverable",
        input_schema="ManualDeliverableContent",
        output_schema="DeliverableRead",
    ),
    "abstention": _available(
        "abstention",
        input_schema="AbstentionOutput",
    ),
    "handoff": _available(
        "handoff",
        input_schema="HandoffOutput",
    ),
    "disagreement": _available(
        "disagreement",
        input_schema="DisagreementOutput",
    ),
    "review_delegation.issue": _available(
        "review_delegation.issue",
        input_schema="ReviewDelegationIssue",
        output_schema="ReviewDelegationRead",
    ),
    "review_delegation.read": _available(
        "review_delegation.read",
        output_schema="ReviewDelegationRead",
    ),
    "review_delegation.revoke": _available(
        "review_delegation.revoke",
        input_schema="ReviewDelegationRevoke",
        output_schema="ReviewDelegationRead",
    ),
    "review_delegation.redeem": _available(
        "review_delegation.redeem",
        input_schema="ReviewDelegationRedeem",
        output_schema="ReviewDelegationRead",
    ),
}


# These entries are explicit so callers can distinguish an unavailable
# capability from a typo or a contract that ReproLab does not know about.
_BLOCKED_CONTRACTS: dict[str, GovernedContract] = {
    "experiment_runner": _blocked("experiment_runner", "execution"),
    "experiment_execution": _blocked("experiment_execution", "execution"),
    "execution": _blocked("execution", "execution"),
    "sandbox_execution": _blocked("sandbox_execution", "sandbox"),
    "sandbox": _blocked("sandbox", "sandbox"),
    "langgraph_workflow": _blocked("langgraph_workflow", "langgraph"),
    "langgraph": _blocked("langgraph", "langgraph"),
    "measurements": _blocked("measurements", "measurement"),
    "measurement": _blocked("measurement", "measurement"),
    "production_measurements": _blocked("production_measurements", "measurement"),
}


_REGISTRY = {**_SUPPORTED_CONTRACTS, **_BLOCKED_CONTRACTS}


def _manual_role(role_id: str, task_kind: str) -> RoleContract:
    return RoleContract(
        role_id, task_kind, "manual.task", "ManualInputReferences",
        "ManualDeliverableContent", ContractStatus.AVAILABLE,
    )


def _blocked_role(role_id: str, task_kind: str, capability: str) -> RoleContract:
    return RoleContract(
        role_id,
        task_kind,
        "execution",
        "ManualInputReferences",
        "ManualDeliverableContent",
        ContractStatus.BLOCKED_CAPABILITY,
        capability=capability,
    )


# This mapping is deliberately maintained separately from constitutions.yaml.
# Constitution declarations describe intended role boundaries; only this
# reviewed allowlist makes a role/task combination available to the API.
_ROLE_CONTRACTS: dict[tuple[str, str], RoleContract] = {
    ("atlas", "coordination_decision"): _manual_role("atlas", "coordination_decision"),
    ("quill", "claim_extraction"): _manual_role("quill", "claim_extraction"),
    ("hypatia", "methodology_audit"): _manual_role("hypatia", "methodology_audit"),
    ("turing", "implementation_assessment"): _manual_role("turing", "implementation_assessment"),
    ("curie", "dataset_manifest"): _manual_role("curie", "dataset_manifest"),
    ("fisher", "statistical_assessment"): _manual_role("fisher", "statistical_assessment"),
    ("popper", "skeptical_review"): _manual_role("popper", "skeptical_review"),
    ("sagan", "evidence_verification"): _manual_role("sagan", "evidence_verification"),
    ("franklin", "report_draft"): _manual_role("franklin", "report_draft"),
    ("shannon", "sensitivity_assessment"): _manual_role("shannon", "sensitivity_assessment"),
    ("faraday", "execution"): _blocked_role("faraday", "execution", "execution"),
    ("noether", "independent_review"): _manual_role("noether", "independent_review"),
}

# Requested ceilings are static policy metadata, never a runtime allocation.
# Stage 3's effective model/token budget is always zero, even below these bounds.
ROLE_MAX_MODEL_CALLS: Final[Mapping[str, int]] = MappingProxyType({
    "atlas": 1, "quill": 3, "hypatia": 2, "turing": 2, "curie": 0,
    "faraday": 0, "fisher": 0, "popper": 2, "shannon": 1, "noether": 1,
    "sagan": 2, "franklin": 0,
})
MANUAL_REVIEW_ROLES: Final = frozenset({"popper", "sagan", "hypatia"})
MANUAL_INPUT_CONTRACT: Final = "manual.input"
MANUAL_OUTPUT_CONTRACTS: Final = frozenset({"deliverable", "abstention", "handoff", "disagreement"})


def is_tool_allowed(role_id: str, tool_id: str) -> bool:
    """Deny by default: Stage 3 has no tool runtime or tool grants."""

    return False


# Public mappings are immutable views.  The values themselves are frozen
# dataclasses, so registry callers cannot mutate the allowlist at runtime.
SUPPORTED_CONTRACTS: Final[Mapping[str, GovernedContract]] = MappingProxyType(
    _SUPPORTED_CONTRACTS
)
BLOCKED_CONTRACTS: Final[Mapping[str, GovernedContract]] = MappingProxyType(
    _BLOCKED_CONTRACTS
)
CONTRACT_REGISTRY: Final[Mapping[str, GovernedContract]] = MappingProxyType(_REGISTRY)
CONTRACTS: Final[Mapping[str, GovernedContract]] = CONTRACT_REGISTRY

# A role constitution cannot add entries to either of these collections.
SUPPORTED_CONTRACT_IDS: Final[tuple[str, ...]] = tuple(sorted(SUPPORTED_CONTRACTS))
BLOCKED_CONTRACT_IDS: Final[tuple[str, ...]] = tuple(sorted(BLOCKED_CONTRACTS))


_ALIASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "assignment": "assignment.create",
        "assignment.lifecycle_transition": "assignment.transition",
        "assignment.lifecycle_event": "assignment.event",
        "lifecycle.transition": "assignment.transition",
        "lifecycle.event": "assignment.event",
        "deliverables": "deliverable",
        "deliverable.create": "deliverable",
        "deliverable.read": "deliverable",
        "abstention.output": "abstention",
        "handoff.output": "handoff",
        "disagreement.output": "disagreement",
        "review_delegation": "review_delegation.issue",
        "review_delegation.issue_request": "review_delegation.issue",
        "review_delegation.revoke_request": "review_delegation.revoke",
        "review_delegation.redeem_request": "review_delegation.redeem",
    }
)


def resolve_contract(contract_id: str) -> GovernedContract:
    """Resolve an explicit contract, returning an unsupported result if absent."""

    if not isinstance(contract_id, str) or not contract_id.strip():
        return GovernedContract(
            contract_id=str(contract_id),
            status=ContractStatus.UNSUPPORTED_CONTRACT,
        )
    normalized = contract_id.strip()
    canonical_id = _ALIASES.get(normalized, normalized)
    contract = CONTRACT_REGISTRY.get(canonical_id)
    if contract is not None:
        return contract
    return GovernedContract(
        contract_id=normalized,
        status=ContractStatus.UNSUPPORTED_CONTRACT,
    )


def resolve_role_contract(role_id: str, task_kind: str) -> RoleContract:
    """Resolve a role/task pair without deriving permissions from YAML."""

    contract = _ROLE_CONTRACTS.get((role_id, task_kind))
    if contract is not None:
        return contract
    return RoleContract(
        role_id=role_id,
        task_kind=task_kind,
        contract_id=f"{role_id}.{task_kind}",
        input_schema="",
        output_schema="",
        status=ContractStatus.UNSUPPORTED_CONTRACT,
    )


def list_role_contracts(role_id: str | None = None) -> tuple[RoleContract, ...]:
    values = _ROLE_CONTRACTS.values()
    if role_id is not None:
        values = (item for item in values if item.role_id == role_id)
    return tuple(sorted(values, key=lambda item: (item.role_id, item.task_kind)))


def get_contract(contract_id: str) -> GovernedContract:
    """Return a contract descriptor without turning unknown names into grants."""

    return resolve_contract(contract_id)


def get_contract_status(contract_id: str) -> ContractStatus:
    """Return ``unsupported_contract`` for every name outside the allowlist."""

    return resolve_contract(contract_id).status


def is_contract_available(contract_id: str) -> bool:
    return get_contract_status(contract_id) is ContractStatus.AVAILABLE


def list_contracts(status: ContractStatus | str | None = None) -> tuple[str, ...]:
    """List explicit registry IDs, optionally filtered by status."""

    if isinstance(status, str):
        try:
            status = ContractStatus(status)
        except ValueError:
            return ()
    contracts = CONTRACT_REGISTRY.values()
    if status is not None:
        contracts = (item for item in contracts if item.status is status)
    return tuple(sorted(item.contract_id for item in contracts))


def require_available_contract(contract_id: str) -> GovernedContract:
    """Return an available contract or fail with its precise availability state."""

    contract = resolve_contract(contract_id)
    if contract.status is not ContractStatus.AVAILABLE:
        raise ValueError(
            f"Governance contract {contract.contract_id!r} is "
            f"{contract.status.value}."
        )
    return contract


def get_governance_contract(contract_id: str) -> GovernedContract:
    return get_contract(contract_id)


def contract_status(contract_id: str) -> ContractStatus:
    return get_contract_status(contract_id)


def is_supported_contract(contract_id: str) -> bool:
    return is_contract_available(contract_id)


if any(item.permissions or item.tools for item in CONTRACT_REGISTRY.values()):
    raise RuntimeError("Static governance contracts cannot grant implicit tools or permissions.")
