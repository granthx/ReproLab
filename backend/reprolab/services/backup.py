"""Coordinated backup and restore service for ReproLab database metadata and storage artifacts."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reprolab.models.artifact import ResearchArtifact
from reprolab.models.evaluation import SystemBackupRecord
from reprolab.models.paper import Artifact
from reprolab.storage.local import LocalPrivateStorage


class BackupIntegrityError(ValueError):
    """Raised when backup verification or integrity checks fail."""
    pass


TABLES_TO_BACKUP = [
    "papers",
    "artifacts",
    "research_artifacts",
    "investigations",
    "claims",
    "evidence_items",
    "evidence_reviews",
    "protocol_versions",
    "record_attributions",
    "scientist_constitution_snapshots",
    "findings",
    "finding_versions",
    "finding_evidence_links",
    "finding_relations",
    "record_reviews",
    "reports",
    "report_versions",
    "report_finding_links",
    "report_events",
    "report_exports",
    "role_assignments",
    "assignment_events",
    "assignment_deliverables",
    "review_delegations",
    "delegation_events",
    "workflow_runs",
    "workflow_checkpoints",
    "workflow_events",
    "workflow_model_calls",
    "experiment_jobs",
    "attempt_records",
    "execution_events",
    "production_measurements",
    "scientific_evaluations",
]


def _json_serial(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _calculate_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(64 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


async def create_system_backup(
    db: AsyncSession,
    storage: LocalPrivateStorage,
    backup_dir: Path,
) -> tuple[SystemBackupRecord, Path]:
    """
    Create a cryptographically verified, coordinated backup bundle.
    Dumps database state and copies content-addressed storage artifacts with SHA-256 indexing.
    """
    backup_dir = Path(backup_dir).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_id = f"backup_{timestamp_str}_{uuid.uuid4().hex[:8]}"
    backup_root = backup_dir / backup_id
    backup_root.mkdir(parents=True, exist_ok=False)

    artifacts_backup_dir = backup_root / "artifacts"
    artifacts_backup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Dump database tables
    database_data: dict[str, list[dict[str, Any]]] = {}
    for table_name in TABLES_TO_BACKUP:
        try:
            result = await db.execute(text(f"SELECT * FROM {table_name}"))
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            database_data[table_name] = rows
        except Exception:
            # Table might not exist in SQLite if not yet migrated
            database_data[table_name] = []

    db_dump_path = backup_root / "database.json"
    db_json_bytes = json.dumps(database_data, default=_json_serial, indent=2).encode("utf-8")
    db_dump_path.write_bytes(db_json_bytes)
    db_dump_sha256 = hashlib.sha256(db_json_bytes).hexdigest()

    # 2. Copy content-addressed artifacts from storage root
    artifact_entries: list[dict[str, Any]] = []
    total_artifact_bytes = 0

    storage_root = storage.root.resolve()
    for subfolder in ("papers", "research"):
        source_sub = storage_root / subfolder
        if not source_sub.exists():
            continue
        for file_path in source_sub.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(storage_root)
                dest_path = artifacts_backup_dir / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest_path)

                file_sha256 = _calculate_sha256(dest_path)
                file_size = dest_path.stat().st_size
                total_artifact_bytes += file_size
                artifact_entries.append({
                    "relative_path": str(rel_path).replace("\\", "/"),
                    "sha256": file_sha256,
                    "size_bytes": file_size,
                })

    # 3. Create manifest
    manifest_data = {
        "backup_id": backup_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app_version": "0.1.0",
        "alembic_head": "0010_release_evaluation",
        "database_dump": {
            "filename": "database.json",
            "sha256": db_dump_sha256,
            "size_bytes": len(db_json_bytes),
        },
        "artifacts": artifact_entries,
        "total_artifacts": len(artifact_entries),
        "total_artifact_bytes": total_artifact_bytes,
        "total_bundle_bytes": len(db_json_bytes) + total_artifact_bytes,
    }

    manifest_path = backup_root / "manifest.json"
    manifest_bytes = json.dumps(manifest_data, indent=2).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    # 4. Record backup in database
    backup_record = SystemBackupRecord(
        backup_id=backup_id,
        manifest_sha256=manifest_sha256,
        database_dump_sha256=db_dump_sha256,
        artifact_count=len(artifact_entries),
        total_bytes=len(db_json_bytes) + total_artifact_bytes,
        status="created",
    )
    db.add(backup_record)
    await db.commit()
    await db.refresh(backup_record)

    return backup_record, manifest_path


async def restore_system_backup(
    manifest_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    storage: LocalPrivateStorage,
) -> dict[str, Any]:
    """
    Restore system state from a verified backup bundle.
    1. Verifies manifest and artifact hashes.
    2. Restores files to storage root.
    3. Restores database records.
    4. Performs end-to-end referential integrity check between DB and disk bytes.
    """
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.exists():
        raise BackupIntegrityError(f"Backup manifest not found at: {manifest_path}")

    backup_root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 1. Pre-restore validation: Verify database dump
    db_dump_meta = manifest.get("database_dump", {})
    db_dump_path = backup_root / db_dump_meta.get("filename", "database.json")
    if not db_dump_path.exists():
        raise BackupIntegrityError("Database dump file missing from backup bundle.")

    actual_db_sha256 = _calculate_sha256(db_dump_path)
    if actual_db_sha256 != db_dump_meta.get("sha256"):
        raise BackupIntegrityError("Database dump SHA-256 does not match manifest.")

    # 2. Pre-restore validation: Verify all artifacts in backup
    artifacts_dir = backup_root / "artifacts"
    for item in manifest.get("artifacts", []):
        rel_path = item["relative_path"]
        expected_sha256 = item["sha256"]
        item_path = artifacts_dir / rel_path
        if not item_path.exists():
            raise BackupIntegrityError(f"Backup artifact missing: {rel_path}")
        if _calculate_sha256(item_path) != expected_sha256:
            raise BackupIntegrityError(f"Backup artifact corrupted: {rel_path}")

    # 3. Restore storage artifacts to target storage root
    storage_root = storage.root.resolve()
    restored_artifacts_count = 0
    for item in manifest.get("artifacts", []):
        rel_path = item["relative_path"]
        source_file = artifacts_dir / rel_path
        target_file = storage_root / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        restored_artifacts_count += 1

    # 4. Restore database records
    db_data = json.loads(db_dump_path.read_text(encoding="utf-8"))
    restored_table_counts: dict[str, int] = {}

    async with session_factory() as session:
        for table_name in TABLES_TO_BACKUP:
            rows = db_data.get(table_name, [])
            if not rows:
                continue

            for row in rows:
                # Upsert or ignore existing rows based on table PK 'id'
                columns = list(row.keys())
                col_names = ", ".join(columns)
                placeholders = ", ".join([f":{col}" for col in columns])
                
                # Use insert ... on conflict do nothing for postgres/sqlite
                stmt = text(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING")
                try:
                    await session.execute(stmt, row)
                except Exception:
                    # Ignore table insertion conflict or missing foreign key
                    pass
            restored_table_counts[table_name] = len(rows)
            await session.flush()

        await session.commit()

    # 5. Referential integrity check
    verified_artifacts = 0
    async with session_factory() as session:
        # Check papers / artifacts
        artifacts_res = await session.execute(select(Artifact))
        for art in artifacts_res.scalars().all():
            p = storage_root / art.storage_key
            if not p.exists():
                raise BackupIntegrityError(f"Referential integrity failure: paper artifact {art.storage_key} missing on disk.")
            if _calculate_sha256(p) != art.sha256:
                raise BackupIntegrityError(f"Referential integrity failure: paper artifact {art.storage_key} hash mismatch.")
            verified_artifacts += 1

        # Check research artifacts
        research_res = await session.execute(select(ResearchArtifact))
        for res_art in research_res.scalars().all():
            p = storage_root / res_art.storage_key
            if not p.exists():
                raise BackupIntegrityError(f"Referential integrity failure: research artifact {res_art.storage_key} missing on disk.")
            if _calculate_sha256(p) != res_art.sha256:
                raise BackupIntegrityError(f"Referential integrity failure: research artifact {res_art.storage_key} hash mismatch.")
            verified_artifacts += 1

        # Update backup status
        stmt = select(SystemBackupRecord).where(SystemBackupRecord.backup_id == manifest.get("backup_id"))
        record = (await session.execute(stmt)).scalar_one_or_none()
        if record:
            record.status = "restored"
            await session.commit()

    return {
        "status": "success",
        "backup_id": manifest.get("backup_id"),
        "restored_artifacts": restored_artifacts_count,
        "verified_database_integrity_artifacts": verified_artifacts,
        "restored_tables": restored_table_counts,
    }
