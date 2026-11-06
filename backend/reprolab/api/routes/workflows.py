"""API routes for Stage 4 analysis-only LangGraph workflows."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.schemas.workflow import (
    WorkflowCancelRequest,
    WorkflowCheckpointRead,
    WorkflowEventRead,
    WorkflowGateDecisionRequest,
    WorkflowModelCallRead,
    WorkflowResumeRequest,
    WorkflowRunCreate,
    WorkflowRunRead,
)
from reprolab.services.workflow import (
    cancel_workflow_run,
    create_and_run_workflow,
    decide_workflow_gate,
    get_workflow_run,
    list_workflow_checkpoints,
    list_workflow_events,
    list_workflow_model_calls,
    list_workflow_runs,
    resume_workflow_run,
)


router = APIRouter(prefix="/api/v1/investigations", tags=["workflows"])


def _adapter_from_request(request: Request):
    return getattr(request.app.state, "workflow_model_adapter", None)


def _settings_from_request(request: Request):
    return getattr(request.app.state, "settings", None)


def _runner_from_request(request: Request):
    return getattr(request.app.state, "experiment_runner_backend", None)


@router.post(
    "/{investigation_id}/workflow-runs",
    response_model=WorkflowRunRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_run_route(
    investigation_id: str,
    payload: WorkflowRunCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunRead:
    run = await create_and_run_workflow(
        db,
        investigation_id,
        payload,
        settings=_settings_from_request(request),
        model_adapter=_adapter_from_request(request),
        runner=_runner_from_request(request),
    )
    return WorkflowRunRead.model_validate(run)


@router.get(
    "/{investigation_id}/workflow-runs",
    response_model=list[WorkflowRunRead],
)
async def list_workflow_runs_route(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowRunRead]:
    runs = await list_workflow_runs(db, investigation_id)
    return [WorkflowRunRead.model_validate(run) for run in runs]


@router.get(
    "/{investigation_id}/workflow-runs/{run_id}",
    response_model=WorkflowRunRead,
)
async def get_workflow_run_route(
    investigation_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunRead:
    run = await get_workflow_run(db, investigation_id, run_id)
    return WorkflowRunRead.model_validate(run)


@router.post(
    "/{investigation_id}/workflow-runs/{run_id}/review-gate",
    response_model=WorkflowRunRead,
)
async def decide_workflow_gate_route(
    investigation_id: str,
    run_id: str,
    payload: WorkflowGateDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunRead:
    run = await decide_workflow_gate(
        db,
        investigation_id,
        run_id,
        payload,
        settings=_settings_from_request(request),
        model_adapter=_adapter_from_request(request),
        runner=_runner_from_request(request),
    )
    return WorkflowRunRead.model_validate(run)


@router.post(
    "/{investigation_id}/workflow-runs/{run_id}/resume",
    response_model=WorkflowRunRead,
)
async def resume_workflow_run_route(
    investigation_id: str,
    run_id: str,
    payload: WorkflowResumeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunRead:
    run = await resume_workflow_run(
        db,
        investigation_id,
        run_id,
        payload,
        settings=_settings_from_request(request),
        model_adapter=_adapter_from_request(request),
        runner=_runner_from_request(request),
    )
    return WorkflowRunRead.model_validate(run)


@router.post(
    "/{investigation_id}/workflow-runs/{run_id}/cancel",
    response_model=WorkflowRunRead,
)
async def cancel_workflow_run_route(
    investigation_id: str,
    run_id: str,
    payload: WorkflowCancelRequest,
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunRead:
    run = await cancel_workflow_run(db, investigation_id, run_id, payload)
    return WorkflowRunRead.model_validate(run)


@router.get(
    "/{investigation_id}/workflow-runs/{run_id}/checkpoints",
    response_model=list[WorkflowCheckpointRead],
)
async def list_workflow_checkpoints_route(
    investigation_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowCheckpointRead]:
    rows = await list_workflow_checkpoints(db, investigation_id, run_id)
    return [WorkflowCheckpointRead.model_validate(row) for row in rows]


@router.get(
    "/{investigation_id}/workflow-runs/{run_id}/events",
    response_model=list[WorkflowEventRead],
)
async def list_workflow_events_route(
    investigation_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowEventRead]:
    rows = await list_workflow_events(db, investigation_id, run_id)
    return [WorkflowEventRead.model_validate(row) for row in rows]


@router.get(
    "/{investigation_id}/workflow-runs/{run_id}/model-calls",
    response_model=list[WorkflowModelCallRead],
)
async def list_workflow_model_calls_route(
    investigation_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowModelCallRead]:
    rows = await list_workflow_model_calls(db, investigation_id, run_id)
    return [WorkflowModelCallRead.model_validate(row) for row in rows]

