"""Transactional service layer for Stage 6 isolated experiment execution and trusted scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.execution.runner import (
    IsolatedRunnerBackend,
    SubprocessSandboxRunner,
    get_default_runner,
)
from reprolab.experiments.contracts import FixtureSpec, FrozenProtocolSnapshot
from reprolab.experiments.fixture_loader import load_fixture
from reprolab.models.execution import (
    AttemptRecord,
    ExecutionEvent,
    ExperimentJob,
    ProductionMeasurement,
)
from reprolab.models.research import Investigation, ProtocolVersion
from reprolab.schemas.execution import (
    ExperimentJobCancel,
    ExperimentJobCreate,
    JobStatus,
)
from reprolab.schemas.governance import canonical_json_hash
from reprolab.scoring.accuracy import calculate_accuracy
from reprolab.services.governance import create_attribution as _governed_create_attribution
from reprolab.services.research_artifacts import ResearchArtifactStore
from reprolab.storage.local import LocalPrivateStorage


def _atomic_execution_mutation(operation):
    @wraps(operation)
    async def wrapped(db: AsyncSession, *args, **kwargs):
        try:
            result = await operation(db, *args, **kwargs)
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Execution mutation conflicts with stored record integrity.") from exc
        except (ValidationError, ValueError) as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail=f"Execution operation failed validation: {exc}") from exc
        except BaseException:
            await db.rollback()
            raise

    return wrapped


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _execution_event_hash(
    *,
    job_id: str,
    investigation_id: str,
    sequence_number: int,
    event_type: str,
    attempt_id: str | None,
    reason: str | None,
    payload: dict[str, Any],
    previous_event_hash: str | None,
    occurred_at: datetime,
) -> str:
    return canonical_json_hash(
        {
            "job_id": job_id,
            "investigation_id": investigation_id,
            "sequence_number": sequence_number,
            "event_type": event_type,
            "attempt_id": attempt_id,
            "reason": reason,
            "payload": payload,
            "previous_event_hash": previous_event_hash,
            "occurred_at": _as_utc(occurred_at).isoformat(),
        }
    )


async def _append_execution_event(
    db: AsyncSession,
    job: ExperimentJob,
    *,
    event_type: str,
    attempt_id: str | None = None,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ExecutionEvent:
    last_event = await db.scalar(
        select(ExecutionEvent)
        .where(ExecutionEvent.job_id == job.id)
        .order_by(ExecutionEvent.sequence_number.desc())
        .limit(1)
    )
    sequence_number = (last_event.sequence_number + 1) if last_event else 1
    previous_event_hash = last_event.event_hash if last_event else None
    occurred_at = _now()
    event_payload = payload or {}
    event_hash = _execution_event_hash(
        job_id=job.id,
        investigation_id=job.investigation_id,
        sequence_number=sequence_number,
        event_type=event_type,
        attempt_id=attempt_id,
        reason=reason,
        payload=event_payload,
        previous_event_hash=previous_event_hash,
        occurred_at=occurred_at,
    )
    event = ExecutionEvent(
        id=str(uuid4()),
        job_id=job.id,
        investigation_id=job.investigation_id,
        attempt_id=attempt_id,
        sequence_number=sequence_number,
        event_type=event_type,
        reason=reason,
        payload=event_payload,
        event_hash=event_hash,
        previous_event_hash=previous_event_hash,
        occurred_at=occurred_at,
    )
    db.add(event)
    await db.flush()
    return event


@_atomic_execution_mutation
async def submit_and_run_experiment_job(
    db: AsyncSession,
    investigation_id: str,
    payload: ExperimentJobCreate,
    *,
    storage: LocalPrivateStorage,
    runner: IsolatedRunnerBackend | None = None,
) -> ExperimentJob:
    investigation = await db.get(Investigation, investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found.")

    # Idempotent replay check
    existing = await db.scalar(
        select(ExperimentJob).where(
            ExperimentJob.investigation_id == investigation_id,
            ExperimentJob.submission_key == payload.submission_key,
        )
    )
    if existing:
        if existing.protocol_version_id != payload.protocol_version_id:
            raise HTTPException(
                status_code=409,
                detail="Submission key was already used with a different protocol version.",
            )
        return existing

    # Protocol must exist and be frozen
    protocol = await db.get(ProtocolVersion, payload.protocol_version_id)
    if not protocol or protocol.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Protocol version not found in this investigation.")
    if protocol.status != "frozen":
        raise HTTPException(status_code=409, detail="Experiment jobs can only execute frozen protocols.")

    attribution = await _governed_create_attribution(db, investigation_id, payload.attribution)

    # Compute execution bundle hash
    exp_type = protocol.canonical_protocol_json.get("experiment_type", "synthetic_binary_classification_v1")
    if exp_type == "synthetic_binary_classification_v1":
        fixture = load_fixture()
        dataset_hash = fixture.dataset_sha256
        split_hash = fixture.split_sha256
    else:
        fixture = None
        dataset_hash = protocol.canonical_protocol_json.get("dataset", {}).get("content_hash", "tabular_benchmark_sha256")
        split_hash = protocol.canonical_protocol_json.get("split", {}).get("split_hash", "fixed_split_sha256")

    bundle_manifest = {
        "protocol_hash": protocol.protocol_hash,
        "dataset_hash": dataset_hash,
        "split_hash": split_hash,
        "experiment_type": exp_type,
    }
    bundle_hash = canonical_json_hash(bundle_manifest)

    job = ExperimentJob(
        id=str(uuid4()),
        investigation_id=investigation_id,
        protocol_version_id=protocol.id,
        submission_key=payload.submission_key,
        status="running",
        lifecycle_version=1,
        execution_bundle_hash=bundle_hash,
        created_by_attribution_id=attribution.id,
    )
    db.add(job)
    await db.flush()

    await _append_execution_event(
        db,
        job,
        event_type="job_submitted",
        payload={"submission_key": payload.submission_key, "bundle_hash": bundle_hash},
    )

    # Launch attempt 1
    attempt = AttemptRecord(
        id=str(uuid4()),
        job_id=job.id,
        investigation_id=investigation_id,
        attempt_number=1,
        status="running",
    )
    db.add(attempt)
    await db.flush()

    await _append_execution_event(
        db,
        job,
        event_type="attempt_started",
        attempt_id=attempt.id,
        payload={"attempt_number": 1},
    )

    # Execute isolated runner
    active_runner = runner or get_default_runner()
    raw_dataset = b"dataset_placeholder"
    raw_split = b"split_placeholder"

    exec_result = active_runner.execute(
        protocol_json=protocol.canonical_protocol_json,
        dataset_bytes=raw_dataset,
        split_bytes=raw_split,
        wall_time_limit=60,
    )

    attempt.finished_at = _now()
    attempt.exit_code = exec_result.exit_code
    attempt.stdout_excerpt = exec_result.stdout
    attempt.stderr_excerpt = exec_result.stderr
    attempt.resource_usage_json = {
        "cpu_user_seconds": exec_result.cpu_user_seconds,
        "wall_time_seconds": exec_result.wall_time_seconds,
        "peak_memory_bytes": exec_result.peak_memory_bytes,
    }

    if exec_result.status == "completed":
        attempt.status = "completed"
        # Ingest prediction & manifest artifacts into research store
        store = ResearchArtifactStore(storage)
        pred_art = await store.persist(
            db,
            investigation_id=investigation_id,
            protocol_version_id=protocol.id,
            kind="prediction_output",
            content=exec_result.prediction_csv,
            content_type="text/csv",
            extension=".csv",
            producer="isolated_runner_v1",
            provenance={"job_id": job.id, "attempt_id": attempt.id},
        )
        man_art = await store.persist(
            db,
            investigation_id=investigation_id,
            protocol_version_id=protocol.id,
            kind="dataset_manifest",
            content=exec_result.manifest_json,
            content_type="application/json",
            extension=".json",
            producer="isolated_runner_v1",
            provenance={"job_id": job.id, "attempt_id": attempt.id},
        )
        attempt.output_artifact_ids = [pred_art.id, man_art.id]

        await _append_execution_event(
            db,
            job,
            event_type="artifacts_collected",
            attempt_id=attempt.id,
            payload={"prediction_artifact_id": pred_art.id, "manifest_artifact_id": man_art.id},
        )

        # Trusted independent scoring
        snapshot = FrozenProtocolSnapshot(
            id=protocol.id,
            status=protocol.status,
            canonical_protocol_json=protocol.canonical_protocol_json,
            protocol_hash=protocol.protocol_hash,
        )
        measurement = calculate_accuracy(
            protocol=snapshot,
            prediction_bytes=exec_result.prediction_csv,
            manifest_bytes=exec_result.manifest_json,
            fixture=fixture,
        )

        prod_measurement = ProductionMeasurement(
            id=str(uuid4()),
            investigation_id=investigation_id,
            job_id=job.id,
            attempt_id=attempt.id,
            metric_name=measurement.metric_name,
            value=measurement.value,
            unit=measurement.unit,
            sample_size=measurement.sample_size,
            analysis_unit=measurement.analysis_unit,
            confidence_level=measurement.confidence_level,
            interval_lower=measurement.interval_lower,
            interval_upper=measurement.interval_upper,
            scoring_method=measurement.scoring_method,
            scorer_version=measurement.scorer_version,
            prediction_artifact_sha256=measurement.prediction_artifact_sha256,
            manifest_artifact_sha256=measurement.manifest_artifact_sha256,
            protocol_hash=measurement.protocol_hash,
        )
        db.add(prod_measurement)
        job.status = "completed"

        await _append_execution_event(
            db,
            job,
            event_type="scoring_completed",
            attempt_id=attempt.id,
            payload={"metric_name": measurement.metric_name, "value": measurement.value},
        )
    elif exec_result.status == "timeout":
        attempt.status = "timeout"
        job.status = "timeout"
        await _append_execution_event(
            db,
            job,
            event_type="job_timeout",
            attempt_id=attempt.id,
            reason=exec_result.stderr,
        )
    else:
        attempt.status = "failed"
        job.status = "failed"
        await _append_execution_event(
            db,
            job,
            event_type="attempt_finished",
            attempt_id=attempt.id,
            reason=exec_result.stderr or "Runner process failed.",
        )

    job.lifecycle_version += 1
    await db.flush()
    await db.refresh(job)
    return job


@_atomic_execution_mutation
async def cancel_experiment_job(
    db: AsyncSession,
    investigation_id: str,
    job_id: str,
    payload: ExperimentJobCancel,
) -> ExperimentJob:
    job = await db.scalar(
        select(ExperimentJob)
        .where(ExperimentJob.id == job_id, ExperimentJob.investigation_id == investigation_id)
        .with_for_update()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Experiment job not found.")
    if job.lifecycle_version != payload.expected_lifecycle_version:
        raise HTTPException(status_code=409, detail="Job lifecycle_version is stale.")
    if job.status in {"completed", "cancelled", "failed", "timeout"}:
        raise HTTPException(status_code=409, detail=f"Job in terminal status '{job.status}' cannot be cancelled.")

    job.status = "cancelled"
    job.cancellation_reason = payload.reason
    job.lifecycle_version += 1

    await _append_execution_event(
        db,
        job,
        event_type="job_cancelled",
        reason=payload.reason,
    )
    await db.flush()
    await db.refresh(job)
    return job


async def list_experiment_jobs(db: AsyncSession, investigation_id: str) -> list[ExperimentJob]:
    rows = await db.scalars(
        select(ExperimentJob)
        .where(ExperimentJob.investigation_id == investigation_id)
        .order_by(ExperimentJob.created_at.asc())
    )
    return list(rows.all())


async def get_experiment_job(db: AsyncSession, investigation_id: str, job_id: str) -> ExperimentJob:
    job = await db.scalar(
        select(ExperimentJob).where(
            ExperimentJob.id == job_id,
            ExperimentJob.investigation_id == investigation_id,
        )
    )
    if not job:
        raise HTTPException(status_code=404, detail="Experiment job not found.")
    return job


async def list_job_attempts(db: AsyncSession, investigation_id: str, job_id: str) -> list[AttemptRecord]:
    await get_experiment_job(db, investigation_id, job_id)
    rows = await db.scalars(
        select(AttemptRecord)
        .where(AttemptRecord.job_id == job_id, AttemptRecord.investigation_id == investigation_id)
        .order_by(AttemptRecord.attempt_number.asc())
    )
    return list(rows.all())


async def list_job_measurements(db: AsyncSession, investigation_id: str, job_id: str) -> list[ProductionMeasurement]:
    await get_experiment_job(db, investigation_id, job_id)
    rows = await db.scalars(
        select(ProductionMeasurement)
        .where(ProductionMeasurement.job_id == job_id, ProductionMeasurement.investigation_id == investigation_id)
        .order_by(ProductionMeasurement.recorded_at.asc())
    )
    return list(rows.all())


async def list_job_events(db: AsyncSession, investigation_id: str, job_id: str) -> list[ExecutionEvent]:
    await get_experiment_job(db, investigation_id, job_id)
    rows = await db.scalars(
        select(ExecutionEvent)
        .where(ExecutionEvent.job_id == job_id, ExecutionEvent.investigation_id == investigation_id)
        .order_by(ExecutionEvent.sequence_number.asc())
    )
    return list(rows.all())

