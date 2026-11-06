"""Deployment and operational maintenance routes (backup, restore, system audit)."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.core.config import Settings, get_settings
from reprolab.core.security import AuthenticatedUser, UserRole, require_role
from reprolab.db.session import get_db
from reprolab.models.evaluation import SystemBackupRecord
from reprolab.services.backup import (
    BackupIntegrityError,
    create_system_backup,
    restore_system_backup,
)
from reprolab.storage.local import LocalPrivateStorage

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


class RestoreRequest(BaseModel):
    manifest_path: str


@router.post("/backup")
async def trigger_backup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: AuthenticatedUser = Depends(require_role([UserRole.OPERATOR, UserRole.ADMIN])),
) -> dict[str, Any]:
    """Create a coordinated, cryptographically verified backup of database and storage artifacts."""
    storage: LocalPrivateStorage = request.app.state.storage
    backup_dir = settings.backup_dir
    record, manifest_path = await create_system_backup(db, storage, backup_dir)
    return {
        "status": "created",
        "backup_id": record.backup_id,
        "manifest_path": str(manifest_path),
        "manifest_sha256": record.manifest_sha256,
        "database_dump_sha256": record.database_dump_sha256,
        "artifact_count": record.artifact_count,
        "total_bytes": record.total_bytes,
        "created_at": record.created_at.isoformat(),
    }


@router.post("/restore")
async def trigger_restore(
    payload: RestoreRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_role([UserRole.ADMIN])),
) -> dict[str, Any]:
    """Restore database and storage artifacts from a verified backup manifest."""
    storage: LocalPrivateStorage = request.app.state.storage
    session_factory = request.app.state.session_factory
    manifest_path = Path(payload.manifest_path)

    try:
        result = await restore_system_backup(manifest_path, session_factory, storage)
        return result
    except BackupIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backup restore failed integrity verification: {str(exc)}",
        ) from exc


@router.get("/backups")
async def list_backups(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_role([UserRole.OPERATOR, UserRole.ADMIN])),
) -> list[dict[str, Any]]:
    """List historical coordinated backup records."""
    stmt = select(SystemBackupRecord).order_by(SystemBackupRecord.created_at.desc())
    records = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "backup_id": r.backup_id,
            "manifest_sha256": r.manifest_sha256,
            "database_dump_sha256": r.database_dump_sha256,
            "artifact_count": r.artifact_count,
            "total_bytes": r.total_bytes,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]

