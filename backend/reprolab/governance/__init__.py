"""Static Stage 3 governance contracts.

The registry in this package is deliberately separate from the declarative
scientist constitutions.  A constitution describes intended responsibilities;
it does not grant a tool, permission, or runtime capability.
"""

from reprolab.governance.contracts import (
    BLOCKED_CONTRACTS,
    BLOCKED_CONTRACT_IDS,
    CONTRACT_REGISTRY,
    CONTRACTS,
    SUPPORTED_CONTRACTS,
    SUPPORTED_CONTRACT_IDS,
    ContractAvailability,
    ContractDefinition,
    ContractStatus,
    GovernanceContract,
    GovernedContract,
    contract_status,
    get_contract,
    get_contract_status,
    get_governance_contract,
    is_contract_available,
    is_supported_contract,
    list_contracts,
    require_available_contract,
    resolve_contract,
)

__all__ = [
    "BLOCKED_CONTRACTS",
    "BLOCKED_CONTRACT_IDS",
    "CONTRACT_REGISTRY",
    "CONTRACTS",
    "SUPPORTED_CONTRACTS",
    "SUPPORTED_CONTRACT_IDS",
    "ContractAvailability",
    "ContractDefinition",
    "ContractStatus",
    "GovernanceContract",
    "GovernedContract",
    "contract_status",
    "get_contract",
    "get_contract_status",
    "get_governance_contract",
    "is_contract_available",
    "is_supported_contract",
    "list_contracts",
    "require_available_contract",
    "resolve_contract",
]
