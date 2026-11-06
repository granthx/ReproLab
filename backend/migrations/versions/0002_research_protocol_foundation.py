"""add investigations, evidence, and immutable protocol foundation

Revision ID: 0002_research_protocol
Revises: 0001_papers_artifacts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_research_protocol"
down_revision: Union[str, None] = "0001_papers_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("claim_assessment", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_investigations_created_at", "investigations", ["created_at"])

    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("reported_value", sa.Float(), nullable=True),
        sa.Column("metric_direction", sa.String(length=8), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("source_locator", sa.String(length=500), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verification_status", sa.String(length=24), nullable=False, server_default="unverified"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_investigation_id", "claims", ["investigation_id"])

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_locator", sa.String(length=500), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("verification_status", sa.String(length=24), nullable=False, server_default="unverified"),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_investigation_id", "evidence_items", ["investigation_id"])

    op.create_table(
        "protocol_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("parent_protocol_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("canonical_protocol_json", sa.JSON(), nullable=False),
        sa.Column("protocol_hash", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_protocol_id"], ["protocol_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investigation_id", "version_number", name="uq_protocol_investigation_version"),
    )
    op.create_index("ix_protocols_investigation_id", "protocol_versions", ["investigation_id"])


def downgrade() -> None:
    op.drop_index("ix_protocols_investigation_id", table_name="protocol_versions")
    op.drop_table("protocol_versions")
    op.drop_index("ix_evidence_investigation_id", table_name="evidence_items")
    op.drop_table("evidence_items")
    op.drop_index("ix_claims_investigation_id", table_name="claims")
    op.drop_table("claims")
    op.drop_index("ix_investigations_created_at", table_name="investigations")
    op.drop_table("investigations")
