"""create papers and artifacts

Revision ID: 0001_papers_artifacts
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_papers_artifacts"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_papers_created_at", "papers", ["created_at"])
    op.create_index("ix_papers_sha256", "papers", ["sha256"], unique=True)
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_artifacts_paper_id", "artifacts", ["paper_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_paper_id", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_papers_sha256", table_name="papers")
    op.drop_index("ix_papers_created_at", table_name="papers")
    op.drop_table("papers")
