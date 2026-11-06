"""SQLAlchemy models for Stage 6 isolated experiment execution and production measurements."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    DDL,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from reprolab.db.base import Base


class ExperimentJob(Base):
    __tablename__ = "experiment_jobs"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "submission_key",
            name="uq_experiment_job_submission",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'timeout')",
            name="ck_experiment_job_status",
        ),
        Index("ix_experiment_jobs_investigation", "investigation_id", "created_at"),
        Index("ix_experiment_jobs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    protocol_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("protocol_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submission_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", server_default="queued", nullable=False)
    lifecycle_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    execution_bundle_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_attribution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("record_attributions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AttemptRecord(Base):
    __tablename__ = "attempt_records"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number", name="uq_attempt_job_number"),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'timeout', 'cancelled')",
            name="ck_attempt_record_status",
        ),
        Index("ix_attempt_records_job", "job_id", "attempt_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("experiment_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", server_default="running", nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_artifact_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    resource_usage_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence_number", name="uq_execution_event_job_seq"),
        CheckConstraint("sequence_number >= 1", name="ck_execution_event_sequence_positive"),
        Index("ix_execution_events_job", "job_id", "sequence_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("experiment_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("attempt_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProductionMeasurement(Base):
    __tablename__ = "production_measurements"
    __table_args__ = (
        Index("ix_production_measurements_investigation", "investigation_id"),
        Index("ix_production_measurements_job", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("experiment_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("attempt_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_level: Mapped[float] = mapped_column(Float, nullable=False)
    interval_lower: Mapped[float] = mapped_column(Float, nullable=False)
    interval_upper: Mapped[float] = mapped_column(Float, nullable=False)
    scoring_method: Mapped[str] = mapped_column(String(120), nullable=False)
    scorer_version: Mapped[str] = mapped_column(String(120), nullable=False)
    prediction_artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


for _table in (ExecutionEvent.__table__,):
    _function_name = f"reject_{_table.name}_mutation"
    event.listen(
        _table,
        "before_create",
        DDL(f"""
            CREATE FUNCTION {_function_name}() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION '{_table.name} is append-only'
                    USING ERRCODE = '55000';
            END;
            $$;
        """).execute_if(dialect="postgresql"),
    )
    event.listen(
        _table,
        "after_create",
        DDL(f"""
            CREATE TRIGGER trg_{_table.name}_append_only
            BEFORE UPDATE OR DELETE ON {_table.name}
            FOR EACH ROW EXECUTE FUNCTION {_function_name}();
        """).execute_if(dialect="postgresql"),
    )
    event.listen(
        _table,
        "after_drop",
        DDL(f"DROP FUNCTION IF EXISTS {_function_name}();").execute_if(dialect="postgresql"),
    )
    for _operation in ("UPDATE", "DELETE"):
        event.listen(
            _table,
            "after_create",
            DDL(f"""
                CREATE TRIGGER trg_{_table.name}_no_{_operation.lower()}
                BEFORE {_operation} ON {_table.name}
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, '{_table.name} is append-only');
                END;
            """).execute_if(dialect="sqlite"),
        )

