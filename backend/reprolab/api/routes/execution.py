"""FastAPI routes for Stage 6 isolated experiment execution and production measurements."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.schemas.execution import (
    AttemptRecordRead,
    ExecutionEventRead,
    ExperimentJobCancel,
    ExperimentJobCreate,
    ExperimentJobRead,
    ProductionMeasurementRead,
)
from reprolab.services.execution import (
    cancel_experiment_job,
    get_experiment_job,
    list_experiment_jobs,
    list_job_attempts,
    list_job_events,
    list_job_measurements,
    submit_and_run_experiment_job,
)

router = APIRouter(prefix="/api/v1/investigations", tags=["execution"])


@router.post(
    "/{investigation_id}/experiment-jobs",
    response_model=ExperimentJobRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_experiment_job_route(
    investigation_id: str,
    payload: ExperimentJobCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ExperimentJobRead:
    storage = request.app.state.storage
    runner = getattr(request.app.state, "experiment_runner_backend", None)
    job = await submit_and_run_experiment_job(
        db,
        investigation_id,
        payload,
        storage=storage,
        runner=runner,
    )
    attempts = await list_job_attempts(db, investigation_id, job.id)
    measurements = await list_job_measurements(db, investigation_id, job.id)
    read_job = ExperimentJobRead.model_validate(job)
    read_job.attempts = [AttemptRecordRead.model_validate(a) for a in attempts]
    read_job.measurements = [ProductionMeasurementRead.model_validate(m) for m in measurements]
    return read_job


@router.get(
    "/{investigation_id}/experiment-jobs",
    response_model=list[ExperimentJobRead],
)
async def list_experiment_jobs_route(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ExperimentJobRead]:
    jobs = await list_experiment_jobs(db, investigation_id)
    result = []
    for job in jobs:
        attempts = await list_job_attempts(db, investigation_id, job.id)
        measurements = await list_job_measurements(db, investigation_id, job.id)
        read_job = ExperimentJobRead.model_validate(job)
        read_job.attempts = [AttemptRecordRead.model_validate(a) for a in attempts]
        read_job.measurements = [ProductionMeasurementRead.model_validate(m) for m in measurements]
        result.append(read_job)
    return result


@router.get(
    "/{investigation_id}/experiment-jobs/{job_id}",
    response_model=ExperimentJobRead,
)
async def get_experiment_job_route(
    investigation_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ExperimentJobRead:
    job = await get_experiment_job(db, investigation_id, job_id)
    attempts = await list_job_attempts(db, investigation_id, job.id)
    measurements = await list_job_measurements(db, investigation_id, job.id)
    read_job = ExperimentJobRead.model_validate(job)
    read_job.attempts = [AttemptRecordRead.model_validate(a) for a in attempts]
    read_job.measurements = [ProductionMeasurementRead.model_validate(m) for m in measurements]
    return read_job


@router.post(
    "/{investigation_id}/experiment-jobs/{job_id}/cancel",
    response_model=ExperimentJobRead,
)
async def cancel_experiment_job_route(
    investigation_id: str,
    job_id: str,
    payload: ExperimentJobCancel,
    db: AsyncSession = Depends(get_db),
) -> ExperimentJobRead:
    job = await cancel_experiment_job(db, investigation_id, job_id, payload)
    attempts = await list_job_attempts(db, investigation_id, job.id)
    measurements = await list_job_measurements(db, investigation_id, job.id)
    read_job = ExperimentJobRead.model_validate(job)
    read_job.attempts = [AttemptRecordRead.model_validate(a) for a in attempts]
    read_job.measurements = [ProductionMeasurementRead.model_validate(m) for m in measurements]
    return read_job


@router.get(
    "/{investigation_id}/experiment-jobs/{job_id}/attempts",
    response_model=list[AttemptRecordRead],
)
async def list_job_attempts_route(
    investigation_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[AttemptRecordRead]:
    attempts = await list_job_attempts(db, investigation_id, job_id)
    return [AttemptRecordRead.model_validate(a) for a in attempts]


@router.get(
    "/{investigation_id}/experiment-jobs/{job_id}/measurements",
    response_model=list[ProductionMeasurementRead],
)
async def list_job_measurements_route(
    investigation_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ProductionMeasurementRead]:
    measurements = await list_job_measurements(db, investigation_id, job_id)
    return [ProductionMeasurementRead.model_validate(m) for m in measurements]


@router.get(
    "/{investigation_id}/experiment-jobs/{job_id}/events",
    response_model=list[ExecutionEventRead],
)
async def list_job_events_route(
    investigation_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ExecutionEventRead]:
    events = await list_job_events(db, investigation_id, job_id)
    return [ExecutionEventRead.model_validate(e) for e in events]


@router.get(
    "/{investigation_id}/experiment-jobs/{job_id}/stream",
)
async def stream_job_logs(
    investigation_id: str,
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    job = await get_experiment_job(db, investigation_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        # 1. Initial Connection Handshake
        yield f"event: connected\ndata: {json.dumps({'job_id': job.id, 'status': job.status, 'submission_key': job.submission_key})}\n\n"

        # 2. Existing Execution Events
        events = await list_job_events(db, investigation_id, job.id)
        for evt in events:
            if await request.is_disconnected():
                return
            evt_data = {
                "sequence_number": evt.sequence_number,
                "event_type": evt.event_type,
                "occurred_at": evt.occurred_at.isoformat() if evt.occurred_at else None,
                "payload": evt.payload,
            }
            yield f"event: execution_event\ndata: {json.dumps(evt_data)}\n\n"
            await asyncio.sleep(0.005)

        # 3. Execution Attempts & Chunked Output Logs
        attempts = await list_job_attempts(db, investigation_id, job.id)
        for att in attempts:
            if await request.is_disconnected():
                return
            att_data = {
                "attempt_number": att.attempt_number,
                "status": att.status,
                "exit_code": att.exit_code,
                "wall_time_seconds": (
                    att.resource_usage_json.get("wall_time_seconds")
                    if att.resource_usage_json else None
                ),
            }
            yield f"event: attempt\ndata: {json.dumps(att_data)}\n\n"

            if att.stdout_excerpt:
                for line in att.stdout_excerpt.splitlines():
                    if await request.is_disconnected():
                        return
                    yield f"event: log\ndata: {json.dumps({'stream': 'stdout', 'attempt': att.attempt_number, 'text': line})}\n\n"
                    await asyncio.sleep(0.002)

            if att.stderr_excerpt:
                for line in att.stderr_excerpt.splitlines():
                    if await request.is_disconnected():
                        return
                    yield f"event: log\ndata: {json.dumps({'stream': 'stderr', 'attempt': att.attempt_number, 'text': line})}\n\n"
                    await asyncio.sleep(0.002)

        # 4. Production Measurements
        measurements = await list_job_measurements(db, investigation_id, job.id)
        for m in measurements:
            if await request.is_disconnected():
                return
            m_data = {
                "metric_name": m.metric_name,
                "value": m.value,
                "interval_lower": m.interval_lower,
                "interval_upper": m.interval_upper,
                "sample_size": m.sample_size,
            }
            yield f"event: measurement\ndata: {json.dumps(m_data)}\n\n"

        # 5. Stream Termination Event
        yield f"event: done\ndata: {json.dumps({'status': job.status, 'job_id': job.id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

