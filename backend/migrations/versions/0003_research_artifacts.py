"""add isolated research artifact records

Revision ID: 0003_research_artifacts
Revises: 0002_research_protocol
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_research_artifacts"
down_revision: Union[str, None] = "0002_research_protocol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["protocol_version_id"], ["protocol_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_research_artifacts_investigation_id", "research_artifacts", ["investigation_id"])
    op.create_index("ix_research_artifacts_sha256", "research_artifacts", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_research_artifacts_sha256", table_name="research_artifacts")
    op.drop_index("ix_research_artifacts_investigation_id", table_name="research_artifacts")
    op.drop_table("research_artifacts")
