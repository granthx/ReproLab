"""add Stage 7 scientific evaluations and system backup records

Revision ID: 0010_release_evaluation
Revises: 0009_experiment_execution
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_release_evaluation"
down_revision: Union[str, None] = "0009_experiment_execution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scientific_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column(
            "evaluation_version",
            sa.String(length=32),
            server_default="1.0.0",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="completed",
            nullable=False,
        ),
        sa.Column("verdict", sa.String(length=64), nullable=False),
        sa.Column(
            "extraction_quality_score",
            sa.Float(),
            server_default="0.0",
            nullable=False,
        ),
        sa.Column("extraction_quality_breakdown", sa.JSON(), nullable=False),
        sa.Column(
            "technical_reproducibility_score",
            sa.Float(),
            server_default="0.0",
            nullable=False,
        ),
        sa.Column("technical_reproducibility_breakdown", sa.JSON(), nullable=False),
        sa.Column(
            "claim_verification_score",
            sa.Float(),
            server_default="0.0",
            nullable=False,
        ),
        sa.Column("claim_verification_breakdown", sa.JSON(), nullable=False),
        sa.Column("summary_notes", sa.Text(), nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name=op.f("fk_scientific_evaluations_claim_id_claims"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            name=op.f("fk_scientific_evaluations_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["experiment_jobs.id"],
            name=op.f("fk_scientific_evaluations_job_id_experiment_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scientific_evaluations")),
    )
    op.create_index(
        op.f("ix_scientific_evaluations_investigation_id"),
        "scientific_evaluations",
        ["investigation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_scientific_evaluations_job_id"),
        "scientific_evaluations",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_scientific_evaluations_claim_id"),
        "scientific_evaluations",
        ["claim_id"],
        unique=False,
    )

    op.create_table(
        "system_backup_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("backup_id", sa.String(length=128), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("database_dump_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="created", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_backup_records")),
    )
    op.create_index(
        op.f("ix_system_backup_records_backup_id"),
        "system_backup_records",
        ["backup_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_system_backup_records_backup_id"),
        table_name="system_backup_records",
    )
    op.drop_table("system_backup_records")

    op.drop_index(
        op.f("ix_scientific_evaluations_claim_id"),
        table_name="scientific_evaluations",
    )
    op.drop_index(
        op.f("ix_scientific_evaluations_job_id"),
        table_name="scientific_evaluations",
    )
    op.drop_index(
        op.f("ix_scientific_evaluations_investigation_id"),
        table_name="scientific_evaluations",
    )
    op.drop_table("scientific_evaluations")

