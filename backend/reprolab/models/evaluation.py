"""SQLAlchemy models for Stage 7 release hardening and scientific evaluation."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from reprolab.db.base import Base


class ScientificEvaluation(Base):
    """
    Structured scientific evaluation record tracking tri-partite evaluation scores:
    1. Extraction Quality (claim & protocol extraction accuracy from paper intake)
    2. Technical Reproducibility (hermetic execution success, artifact schema integrity)
    3. Scientific Claim Verification (independent statistical scorer vs paper claims)
    """

    __tablename__ = "scientific_evaluations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    investigation_id = Column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id = Column(
        String(36),
        ForeignKey("experiment_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    claim_id = Column(
        String(36),
        ForeignKey("claims.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evaluation_version = Column(String(32), nullable=False, default="1.0.0", server_default="1.0.0")
    status = Column(String(32), nullable=False, default="completed", server_default="completed")
    verdict = Column(String(64), nullable=False)  # reproduced, disconfirmed, inconclusive, execution_failed

    extraction_quality_score = Column(Float, nullable=False, default=0.0, server_default="0.0")
    extraction_quality_breakdown = Column(JSON, nullable=False, default=dict)

    technical_reproducibility_score = Column(Float, nullable=False, default=0.0, server_default="0.0")
    technical_reproducibility_breakdown = Column(JSON, nullable=False, default=dict)

    claim_verification_score = Column(Float, nullable=False, default=0.0, server_default="0.0")
    claim_verification_breakdown = Column(JSON, nullable=False, default=dict)

    summary_notes = Column(Text, nullable=True)
    evaluated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    investigation = relationship("Investigation", backref="scientific_evaluations")
    job = relationship("ExperimentJob", backref="scientific_evaluations")
    claim = relationship("Claim", backref="scientific_evaluations")


class SystemBackupRecord(Base):
    """
    Cryptographic audit record for coordinated database and storage artifact backups.
    """

    __tablename__ = "system_backup_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    backup_id = Column(String(128), unique=True, nullable=False, index=True)
    manifest_sha256 = Column(String(64), nullable=False)
    database_dump_sha256 = Column(String(64), nullable=False)
    artifact_count = Column(Integer, nullable=False, default=0, server_default="0")
    total_bytes = Column(BigInteger, nullable=False, default=0, server_default="0")
    status = Column(String(32), nullable=False, default="created", server_default="created")  # created, restored, verified, failed
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
