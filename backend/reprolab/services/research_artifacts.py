from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.models.artifact import ResearchArtifact, ResearchArtifactBlob, ResearchArtifactReference
from reprolab.models.research import Investigation, ProtocolVersion
from reprolab.storage.local import LocalPrivateStorage


class ResearchArtifactStore:
    """Internal persistence boundary with shared content blobs and provenance references."""

    def __init__(self, storage: LocalPrivateStorage):
        self.storage = storage

    async def persist(
        self,
        db: AsyncSession,
        *,
        investigation_id: str,
        protocol_version_id: str,
        kind: str,
        content: bytes,
        content_type: str,
        extension: str,
        producer: str,
        provenance: dict[str, Any],
    ) -> ResearchArtifactReference:
        investigation = await db.get(Investigation, investigation_id)
        protocol = await db.get(ProtocolVersion, protocol_version_id)
        if investigation is None or protocol is None or protocol.investigation_id != investigation_id:
            raise ValueError("Research artifact investigation and protocol must belong together")

        stored = self.storage.store_research_bytes(content, content_type=content_type, extension=extension)
        blob = await db.scalar(
            select(ResearchArtifactBlob).where(
                ResearchArtifactBlob.sha256 == stored.sha256,
                ResearchArtifactBlob.content_type == stored.content_type,
            )
        )
        if blob is None:
            blob = ResearchArtifactBlob(
                storage_key=stored.storage_key,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                content_type=stored.content_type,
            )
            db.add(blob)
            await db.flush()
        else:
            self.storage.read_research_bytes(blob.storage_key, expected_sha256=blob.sha256)

        existing = await db.scalar(
            select(ResearchArtifactReference).where(
                ResearchArtifactReference.blob_id == blob.id,
                ResearchArtifactReference.investigation_id == investigation_id,
                ResearchArtifactReference.protocol_version_id == protocol_version_id,
                ResearchArtifactReference.kind == kind,
            )
        )
        if existing is not None:
            return existing

        reference = ResearchArtifactReference(
            blob_id=blob.id,
            investigation_id=investigation_id,
            protocol_version_id=protocol_version_id,
            kind=kind,
            storage_key=blob.storage_key,
            sha256=blob.sha256,
            size_bytes=blob.size_bytes,
            content_type=blob.content_type,
            producer=producer,
            provenance_json=provenance,
        )
        db.add(reference)
        # Never delete the underlying bytes on transaction failure. A shared blob
        # may already be referenced, and orphan cleanup must be explicit and safe.
        await db.commit()
        await db.refresh(reference)
        return reference

    def read_verified(self, artifact: ResearchArtifactReference | ResearchArtifact) -> bytes:
        return self.storage.read_research_bytes(artifact.storage_key, expected_sha256=artifact.sha256)

    async def delete_reference(self, db: AsyncSession, reference_id: str) -> bool:
        reference = await db.get(ResearchArtifactReference, reference_id)
        if reference is None:
            return False
        blob_id = reference.blob_id
        await db.delete(reference)
        await db.flush()
        remaining = await db.scalar(
            select(func.count()).select_from(ResearchArtifactReference).where(
                ResearchArtifactReference.blob_id == blob_id
            )
        )
        blob = await db.get(ResearchArtifactBlob, blob_id) if not remaining else None
        if blob is not None:
            await db.delete(blob)
        await db.commit()
        if blob is not None:
            self.storage.delete_research(blob.storage_key)
        return True
