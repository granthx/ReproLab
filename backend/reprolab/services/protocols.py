import hashlib
import json
from typing import Any

from reprolab.schemas.research import ProtocolDefinition


def canonical_protocol(protocol: ProtocolDefinition) -> dict[str, Any]:
    """Return the JSON-compatible protocol snapshot used for hashing and storage."""
    return protocol.model_dump(mode="json")


def protocol_hash(protocol_json: dict[str, Any]) -> str:
    payload = json.dumps(protocol_json, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
