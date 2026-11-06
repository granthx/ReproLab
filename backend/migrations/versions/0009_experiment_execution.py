"""add Stage 6 isolated experiment execution, attempt records, events, and production measurements

Revision ID: 0009_experiment_execution
Revises: 0008_analysis_workflow
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_experiment_execution"
down_revision: Union[str, None] = "0008_analysis_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_EXECUTION_TABLES = ("execution_events",)


def upgrade() -> None:
    op.create_table(
        "experiment_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("protocol_version_id", sa.String(length=36), nullable=False),
        sa.Column("submission_key", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("lifecycle_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("execution_bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'timeout')",
            name="ck_experiment_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            name="fk_experiment_jobs_investigation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_version_id"],
            ["protocol_versions.id"],
            name="fk_experiment_jobs_protocol_version_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_attribution_id"],
            ["record_attributions.id"],
            name="fk_experiment_jobs_created_by_attribution_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "investigation_id",
            "submission_key",
            name="uq_experiment_job_submission",
        ),
    )
    op.create_index(
        "ix_experiment_jobs_investigation",
        "experiment_jobs",
        ["investigation_id", "created_at"],
    )
    op.create_index("ix_experiment_jobs_status", "experiment_jobs", ["status"])

    op.create_table(
        "attempt_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="running",
            nullable=False,
        ),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout_excerpt", sa.Text(), nullable=True),
        sa.Column("stderr_excerpt", sa.Text(), nullable=True),
        sa.Column("output_artifact_ids", sa.JSON(), nullable=True),
        sa.Column("resource_usage_json", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'timeout', 'cancelled')",
            name="ck_attempt_record_status",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["experiment_jobs.id"],
            name="fk_attempt_records_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            name="fk_attempt_records_investigation_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_attempt_job_number"),
    )
    op.create_index(
        "ix_attempt_records_job",
        "attempt_records",
        ["job_id", "attempt_number"],
    )

    op.create_table(
        "execution_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence_number >= 1",
            name="ck_execution_event_sequence_positive",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["experiment_jobs.id"],
            name="fk_execution_events_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            name="fk_execution_events_investigation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempt_records.id"],
            name="fk_execution_events_attempt_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "sequence_number",
            name="uq_execution_event_job_seq",
        ),
    )
    op.create_index(
        "ix_execution_events_job",
        "execution_events",
        ["job_id", "sequence_number"],
    )

    op.create_table(
        "production_measurements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("analysis_unit", sa.String(length=64), nullable=False),
        sa.Column("confidence_level", sa.Float(), nullable=False),
        sa.Column("interval_lower", sa.Float(), nullable=False),
        sa.Column("interval_upper", sa.Float(), nullable=False),
        sa.Column("scoring_method", sa.String(length=120), nullable=False),
        sa.Column("scorer_version", sa.String(length=120), nullable=False),
        sa.Column("prediction_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("protocol_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            name="fk_production_measurements_investigation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["experiment_jobs.id"],
            name="fk_production_measurements_job_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempt_records.id"],
            name="fk_production_measurements_attempt_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_production_measurements_investigation",
        "production_measurements",
        ["investigation_id"],
    )
    op.create_index(
        "ix_production_measurements_job",
        "production_measurements",
        ["job_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table_name in IMMUTABLE_EXECUTION_TABLES:
            op.execute(f"""
                CREATE FUNCTION reject_{table_name}_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION '{table_name} is append-only'
                        USING ERRCODE = '55000';
                END;
                $$;
            """)
            op.execute(f"""
                CREATE TRIGGER trg_{table_name}_append_only
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION reject_{table_name}_mutation();
            """)
    elif op.get_bind().dialect.name == "sqlite":
        for table_name in IMMUTABLE_EXECUTION_TABLES:
            op.execute(f"""
                CREATE TRIGGER trg_{table_name}_no_update
                BEFORE UPDATE ON {table_name}
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END;
            """)
            op.execute(f"""
                CREATE TRIGGER trg_{table_name}_no_delete
                BEFORE DELETE ON {table_name}
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END;
            """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in reversed(IMMUTABLE_EXECUTION_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name};")
            op.execute(f"DROP FUNCTION IF EXISTS reject_{table_name}_mutation();")
    elif op.get_bind().dialect.name == "sqlite":
        for table_name in reversed(IMMUTABLE_EXECUTION_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_delete;")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_update;")

    op.drop_index("ix_production_measurements_job", table_name="production_measurements")
    op.drop_index("ix_production_measurements_investigation", table_name="production_measurements")
    op.drop_table("production_measurements")

    op.drop_index("ix_execution_events_job", table_name="execution_events")
    op.drop_table("execution_events")

    op.drop_index("ix_attempt_records_job", table_name="attempt_records")
    op.drop_table("attempt_records")

    op.drop_index("ix_experiment_jobs_status", table_name="experiment_jobs")
    op.drop_index("ix_experiment_jobs_investigation", table_name="experiment_jobs")
    op.drop_table("experiment_jobs")

