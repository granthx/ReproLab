from typing import Any

from fastapi import APIRouter

from reprolab.execution.runner import is_docker_available
from reprolab.experiments.registry import list_experiment_types

router = APIRouter(prefix="/api/v1", tags=["capabilities"])


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    return {
        "paper_intake": True,
        "protocol_governance": True,
        "evidence_review": True,
        "traceable_findings": True,
        "scientist_registry": True,
        "trusted_fixture_scoring": True,
        "experiment_runner": True,
        "sandbox_execution": True,
        "docker_runner_supported": True,
        "docker_available": is_docker_available(),
        "runner_backends": ["subprocess", "docker"],
        "registered_experiment_types": list(list_experiment_types()),
        "langgraph_workflow": True,
        "measurements": True,
        "reports": True,
        "execution_state": "available",
    }
