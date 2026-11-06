"""add append-only evidence reviews and shared research artifact references

Revision ID: 0004_stage1_integrity
Revises: 0003_research_artifacts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_stage1_integrity"
down_revision: Union[str, None] = "0003_research_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evidence_item_id", sa.String(length=36), nullable=False),
        sa.Column("review_method", sa.String(length=48), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.String(length=200), nullable=True),
        sa.Column("reviewer_label", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_reviews_evidence_id", "evidence_reviews", ["evidence_item_id"])

    op.create_table(
        "research_artifact_blobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint("sha256", "content_type", name="uq_research_blob_hash_content_type"),
    )
    op.create_index("ix_research_artifact_blobs_sha256", "research_artifact_blobs", ["sha256"])

    op.create_table(
        "research_artifact_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("blob_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("protocol_version_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("producer", sa.String(length=200), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["blob_id"], ["research_artifact_blobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["protocol_version_id"], ["protocol_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blob_id", "investigation_id", "protocol_version_id", "kind", name="uq_research_artifact_reference"),
    )
    op.create_index("ix_research_artifact_references_investigation_id", "research_artifact_references", ["investigation_id"])
    op.create_index("ix_research_artifact_references_blob_id", "research_artifact_references", ["blob_id"])


def downgrade() -> None:
    op.drop_index("ix_research_artifact_references_blob_id", table_name="research_artifact_references")
    op.drop_index("ix_research_artifact_references_investigation_id", table_name="research_artifact_references")
    op.drop_table("research_artifact_references")
    op.drop_index("ix_research_artifact_blobs_sha256", table_name="research_artifact_blobs")
    op.drop_table("research_artifact_blobs")
    op.drop_index("ix_evidence_reviews_evidence_id", table_name="evidence_reviews")
    op.drop_table("evidence_reviews")
