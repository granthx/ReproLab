from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ScientistConstitution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: str = Field(pattern=r"^[a-z_]+$")
    name: str
    specialty: str
    version: str
    mandate: str
    responsibilities: list[str]
    prohibited_actions: list[str]
    input_schema: str
    output_schema: str
    permitted_tools: list[str]
    permissions: list[str]
    evidence_requirements: list[str]
    handoff_conditions: list[str]
    disagreement_rules: list[str]
    abstention_rules: list[str]
    completion_criteria: list[str]
    model: dict[str, Any]


EXPECTED_ROLE_IDS = {
    "atlas", "quill", "hypatia", "turing", "curie", "faraday",
    "fisher", "popper", "shannon", "noether", "sagan", "franklin",
}


@lru_cache(maxsize=1)
def get_constitutions() -> dict[str, ScientistConstitution]:
    source = Path(__file__).with_name("constitutions.yaml")
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    constitutions = {
        item["role_id"]: ScientistConstitution.model_validate(item)
        for item in raw["scientists"]
    }
    if set(constitutions) != EXPECTED_ROLE_IDS:
        missing = EXPECTED_ROLE_IDS - set(constitutions)
        extra = set(constitutions) - EXPECTED_ROLE_IDS
        raise ValueError(f"Scientist registry mismatch; missing={missing}, extra={extra}")
    return constitutions
