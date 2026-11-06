from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from reprolab.db.base import Base


class ResearchArtifact(Base):
    """Content-addressed non-paper artifact produced by internal research services."""

    __tablename__ = "research_artifacts"
    __table_args__ = (Index("ix_research_artifacts_investigation_id", "investigation_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    protocol_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("protocol_versions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    producer: Mapped[str] = mapped_column(String(200), nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ResearchArtifactBlob(Base):
    __tablename__ = "research_artifact_blobs"
    __table_args__ = (UniqueConstraint("sha256", "content_type", name="uq_research_blob_hash_content_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ResearchArtifactReference(Base):
    __tablename__ = "research_artifact_references"
    __table_args__ = (
        Index("ix_research_artifact_references_investigation_id", "investigation_id"),
        Index("ix_research_artifact_references_blob_id", "blob_id"),
        UniqueConstraint("blob_id", "investigation_id", "protocol_version_id", "kind", name="uq_research_artifact_reference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    blob_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_artifact_blobs.id", ondelete="RESTRICT"), nullable=False
    )
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    protocol_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("protocol_versions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    producer: Mapped[str] = mapped_column(String(200), nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
