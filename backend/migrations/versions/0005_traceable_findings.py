"""add attributed, versioned findings and investigation-isolated links

Revision ID: 0005_traceable_findings
Revises: 0004_stage1_integrity
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_traceable_findings"
down_revision: Union[str, None] = "0004_stage1_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_evidence_id_investigation",
        "evidence_items",
        ["id", "investigation_id"],
    )

    op.create_table(
        "scientist_constitution_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=80), nullable=False),
        sa.Column("constitution_version", sa.String(length=80), nullable=False),
        sa.Column("constitution_json", sa.JSON(), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "role_id",
            "constitution_version",
            "constitution_hash",
            name="uq_constitution_snapshot_identity",
        ),
    )
    op.create_index(
        "ix_constitution_snapshots_role_id",
        "scientist_constitution_snapshots",
        ["role_id"],
    )

    op.create_table(
        "record_attributions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("recorder_id", sa.String(length=200), nullable=True),
        sa.Column("recorder_label", sa.String(length=200), nullable=False),
        sa.Column("entry_method", sa.String(length=32), server_default="manual_entry", nullable=False),
        sa.Column("associated_role_id", sa.String(length=80), nullable=True),
        sa.Column("role_association_note", sa.Text(), nullable=True),
        sa.Column("identity_assurance", sa.String(length=32), server_default="caller_asserted", nullable=False),
        sa.Column("constitution_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["constitution_snapshot_id"],
            ["scientist_constitution_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "investigation_id", name="uq_attribution_id_investigation"),
        sa.CheckConstraint(
            "entry_method = 'manual_entry'",
            name="ck_record_attribution_entry_method",
        ),
        sa.CheckConstraint(
            "identity_assurance = 'caller_asserted'",
            name="ck_record_attribution_identity_assurance",
        ),
    )
    op.create_index(
        "ix_record_attributions_investigation_id",
        "record_attributions",
        ["investigation_id"],
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "investigation_id", name="uq_finding_id_investigation"),
    )
    op.create_index("ix_findings_investigation_id", "findings", ["investigation_id"])

    op.create_table(
        "finding_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("parent_version_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("record_kind", sa.String(length=32), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column("protocol_version_id", sa.String(length=36), nullable=True),
        sa.Column("canonical_content_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), server_default="finding.v1", nullable=False),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_id", "investigation_id"],
            ["findings.id", "findings.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_version_id"],
            ["protocol_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "investigation_id", name="uq_finding_version_id_investigation"),
        sa.UniqueConstraint("finding_id", "version_number", name="uq_finding_version_number"),
        sa.CheckConstraint(
            "record_kind IN ('observation', 'interpretation', 'limitation', "
            "'unresolved_question', 'resolution_note')",
            name="ck_finding_version_record_kind",
        ),
    )
    op.create_index(
        "ix_finding_versions_investigation_id",
        "finding_versions",
        ["investigation_id"],
    )
    op.create_index("ix_finding_versions_finding_id", "finding_versions", ["finding_id"])

    op.create_table(
        "finding_evidence_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("finding_version_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_item_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("citation_key", sa.String(length=32), nullable=False),
        sa.Column("evidence_review_id", sa.String(length=36), nullable=True),
        sa.Column("relationship", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_item_id", "investigation_id"],
            ["evidence_items.id", "evidence_items.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_review_id"],
            ["evidence_reviews.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "finding_version_id",
            "citation_key",
            name="uq_finding_evidence_citation_key",
        ),
        sa.CheckConstraint(
            "relationship IN ('supports', 'contradicts', 'context')",
            name="ck_finding_evidence_relationship",
        ),
    )
    op.create_index(
        "ix_finding_evidence_links_investigation_id",
        "finding_evidence_links",
        ["investigation_id"],
    )
    op.create_index(
        "ix_finding_evidence_links_evidence_id",
        "finding_evidence_links",
        ["evidence_item_id"],
    )

    op.create_table(
        "finding_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("from_finding_version_id", sa.String(length=36), nullable=False),
        sa.Column("to_finding_version_id", sa.String(length=36), nullable=False),
        sa.Column("relation_kind", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_finding_version_id",
            "to_finding_version_id",
            "relation_kind",
            name="uq_finding_relation_edge",
        ),
        sa.CheckConstraint(
            "from_finding_version_id <> to_finding_version_id",
            name="ck_finding_relation_no_self",
        ),
        sa.CheckConstraint(
            "relation_kind IN ('disputes', 'responds_to', 'addresses_question')",
            name="ck_finding_relation_kind",
        ),
    )
    op.create_index(
        "ix_finding_relations_investigation_id",
        "finding_relations",
        ["investigation_id"],
    )

    op.create_table(
        "record_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("finding_version_id", sa.String(length=36), nullable=False),
        sa.Column("target_content_hash", sa.String(length=64), nullable=False),
        sa.Column("reviewer_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("review_method", sa.String(length=32), server_default="manual_review", nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("citations_checked", sa.Boolean(), nullable=False),
        sa.Column("numeric_transcription_checked", sa.Boolean(), nullable=True),
        sa.Column("limitations_checked", sa.Boolean(), nullable=False),
        sa.Column("execution_wording_checked", sa.Boolean(), nullable=False),
        sa.Column("dependency_disclosures", sa.JSON(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("review_method = 'manual_review'", name="ck_record_review_method"),
        sa.CheckConstraint(
            "outcome IN ('accepted_for_inclusion', 'needs_revision', 'abstained')",
            name="ck_record_review_outcome",
        ),
    )
    op.create_index("ix_record_reviews_investigation_id", "record_reviews", ["investigation_id"])
    op.create_index("ix_record_reviews_finding_version_id", "record_reviews", ["finding_version_id"])


def downgrade() -> None:
    op.drop_index("ix_record_reviews_finding_version_id", table_name="record_reviews")
    op.drop_index("ix_record_reviews_investigation_id", table_name="record_reviews")
    op.drop_table("record_reviews")
    op.drop_index("ix_finding_relations_investigation_id", table_name="finding_relations")
    op.drop_table("finding_relations")
    op.drop_index("ix_finding_evidence_links_evidence_id", table_name="finding_evidence_links")
    op.drop_index("ix_finding_evidence_links_investigation_id", table_name="finding_evidence_links")
    op.drop_table("finding_evidence_links")
    op.drop_index("ix_finding_versions_finding_id", table_name="finding_versions")
    op.drop_index("ix_finding_versions_investigation_id", table_name="finding_versions")
    op.drop_table("finding_versions")
    op.drop_index("ix_findings_investigation_id", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_record_attributions_investigation_id", table_name="record_attributions")
    op.drop_table("record_attributions")
    op.drop_index("ix_constitution_snapshots_role_id", table_name="scientist_constitution_snapshots")
    op.drop_table("scientist_constitution_snapshots")
    op.drop_constraint("uq_evidence_id_investigation", "evidence_items", type_="unique")
