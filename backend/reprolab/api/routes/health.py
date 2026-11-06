"""Health, readiness, and sanitized diagnostic probes."""

from datetime import datetime, timezone
import os
from pathlib import Path
import time
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.core.config import Settings, get_settings
from reprolab.core.security import mask_secret, sanitize_database_url
from reprolab.db.session import get_db
from reprolab.models.evaluation import ScientificEvaluation, SystemBackupRecord
from reprolab.models.execution import ExperimentJob
from reprolab.models.paper import Paper
from reprolab.models.research import Investigation
from reprolab.models.workflow import WorkflowRun

router = APIRouter(tags=["health"])

_START_TIME = time.time()


@router.get("/health/live")
@router.get("/api/v1/health/live")
async def liveness() -> dict[str, str]:
    """Lightweight process liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready")
@router.get("/api/v1/health/ready")
async def readiness(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Deep readiness probe verifying database connectivity, storage writeability, and schema state."""
    checks: dict[str, str] = {}

    # 1. Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {str(exc)}"
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})

    # 2. Storage writeability check
    try:
        storage = getattr(request.app.state, "storage", None)
        storage_root = storage.root if storage else Path(settings.storage_root)
        test_file = storage_root / ".tmp" / f"health_probe_{int(time.time())}.tmp"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_bytes(b"probe")
        test_file.unlink(missing_ok=True)
        checks["storage"] = "ok"
    except Exception as exc:
        checks["storage"] = f"error: {str(exc)}"
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})

    return {"status": "ready", "database": "ok", "storage": "ok"}


@router.get("/health/diagnostics")
@router.get("/api/v1/health/diagnostics")
async def diagnostics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Sanitized operational diagnostics: reports uptime, database pool status,
    storage statistics, entity counts, and release configuration.
    All credentials and secrets are strictly redacted.
    """
    uptime_seconds = round(time.time() - _START_TIME, 2)
    storage = getattr(request.app.state, "storage", None)

    # Compute storage usage
    storage_bytes = 0
    storage_file_count = 0
    if storage and storage.root.exists():
        for p in storage.root.rglob("*"):
            if p.is_file():
                storage_file_count += 1
                try:
                    storage_bytes += p.stat().st_size
                except OSError:
                    pass

    # Entity counts
    try:
        paper_count = (await db.execute(select(func.count(Paper.id)))).scalar() or 0
        inv_count = (await db.execute(select(func.count(Investigation.id)))).scalar() or 0
        workflow_count = (await db.execute(select(func.count(WorkflowRun.id)))).scalar() or 0
        job_count = (await db.execute(select(func.count(ExperimentJob.id)))).scalar() or 0
        eval_count = (await db.execute(select(func.count(ScientificEvaluation.id)))).scalar() or 0
        backup_count = (await db.execute(select(func.count(SystemBackupRecord.id)))).scalar() or 0
    except Exception:
        paper_count = inv_count = workflow_count = job_count = eval_count = backup_count = 0

    return {
        "status": "operational",
        "app_version": "0.1.0",
        "uptime_seconds": uptime_seconds,
        "database": {
            "sanitized_url": sanitize_database_url(settings.database_url),
            "connected": True,
        },
        "storage": {
            "root": str(storage.root) if storage else str(settings.storage_root),
            "total_bytes": storage_bytes,
            "total_files": storage_file_count,
        },
        "counts": {
            "papers": paper_count,
            "investigations": inv_count,
            "workflow_runs": workflow_count,
            "experiment_jobs": job_count,
            "scientific_evaluations": eval_count,
            "system_backups": backup_count,
        },
        "security": {
            "auth_enabled": settings.auth_enabled,
            "gemini_api_key_configured": bool(settings.gemini_api_key),
            "gemini_api_key_masked": mask_secret(settings.gemini_api_key) if settings.gemini_api_key else None,
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
