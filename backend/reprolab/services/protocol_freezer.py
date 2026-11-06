"""Protocol Freezer Engine for ReproLab (Milestone 2).

Provides:
- Deterministic canonicalization of execution specifications
- SHA-256 specification hash generation (64-character lowercase hex digest)
- Construction and validation of ProtocolSpecificationContract
- OpenTelemetry instrumentation on stage5.gen_ai.freeze_protocol
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

from reprolab.core.telemetry import trace_span
from reprolab.schemas.contracts import ProtocolSpecificationContract


class ProtocolFreezerEngine:
    """Freezes research execution specifications into content-addressed cryptographic contracts."""

    def compute_spec_hash(self, payload: Dict[str, Any]) -> str:
        """Compute the deterministic SHA-256 hash of a dictionary.
        
        Enforces:
        - Strict recursive key sorting (`sort_keys=True`)
        - Compact separators without whitespace (`(',', ':')`)
        - Explicit ASCII encoding
        """
        canonical_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest().lower()

    def freeze_protocol(
        self,
        case_id: str,
        environment_name: str,
        python_version: str = "3.13.12",
        dependencies: Optional[Dict[str, str]] = None,
        hyperparameters: Optional[Dict[str, Any]] = None,
        seed_list: Optional[List[int]] = None,
        entrypoint: str = "reproduce.py",
        hardware_requirements: Optional[Dict[str, Any]] = None,
    ) -> ProtocolSpecificationContract:
        """Lock and validate a deterministic protocol specification."""
        with trace_span("stage5.gen_ai.freeze_protocol", case_id=case_id) as span:
            deps = dependencies or {}
            params = hyperparameters or {}
            seeds = seed_list or [42]

            # Build canonical payload for hashing
            canonical_payload = {
                "environment_name": environment_name,
                "python_version": python_version,
                "dependencies": deps,
                "hyperparameters": params,
                "seed_list": seeds,
                "entrypoint": entrypoint,
                "hardware_requirements": hardware_requirements or {},
            }

            spec_hash = self.compute_spec_hash(canonical_payload)
            span.set_attribute("protocol.spec_hash", spec_hash)
            span.set_attribute("protocol.dependencies_count", len(deps))
            span.set_attribute("protocol.seeds_count", len(seeds))

            return ProtocolSpecificationContract(
                spec_hash=spec_hash,
                case_id=case_id,
                environment_name=environment_name,
                python_version=python_version,
                dependencies=deps,
                hyperparameters=params,
                seed_list=seeds,
                entrypoint=entrypoint,
                hardware_requirements=hardware_requirements,
            )

