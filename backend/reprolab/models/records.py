from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from reprolab.db.base import Base


class ScientistConstitutionSnapshot(Base):
    __tablename__ = "scientist_constitution_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "constitution_version",
            "constitution_hash",
            name="uq_constitution_snapshot_identity",
        ),
        Index("ix_constitution_snapshots_role_id", "role_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    role_id: Mapped[str] = mapped_column(String(80), nullable=False)
    constitution_version: Mapped[str] = mapped_column(String(80), nullable=False)
    constitution_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecordAttribution(Base):
    __tablename__ = "record_attributions"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_attribution_id_investigation"),
        ForeignKeyConstraint(
            ["constitution_snapshot_id"],
            ["scientist_constitution_snapshots.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_record_attributions_investigation_id", "investigation_id"),
        CheckConstraint(
            "entry_method = 'manual_entry'",
            name="ck_record_attribution_entry_method",
        ),
        CheckConstraint(
            "identity_assurance = 'caller_asserted'",
            name="ck_record_attribution_identity_assurance",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    recorder_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recorder_label: Mapped[str] = mapped_column(String(200), nullable=False)
    entry_method: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_entry")
    associated_role_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    role_association_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    identity_assurance: Mapped[str] = mapped_column(
        String(32), nullable=False, default="caller_asserted"
    )
    constitution_snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_finding_id_investigation"),
        Index("ix_findings_investigation_id", "investigation_id"),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FindingVersion(Base):
    __tablename__ = "finding_versions"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_finding_version_id_investigation"),
        UniqueConstraint("finding_id", "version_number", name="uq_finding_version_number"),
        Index("ix_finding_versions_investigation_id", "investigation_id"),
        Index("ix_finding_versions_finding_id", "finding_id"),
        ForeignKeyConstraint(
            ["finding_id", "investigation_id"],
            ["findings.id", "findings.investigation_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["parent_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "record_kind IN ('observation', 'interpretation', 'limitation', "
            "'unresolved_question', 'resolution_note')",
            name="ck_finding_version_record_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    finding_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    claim_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("claims.id", ondelete="SET NULL"), nullable=True
    )
    protocol_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("protocol_versions.id", ondelete="SET NULL"), nullable=True
    )
    canonical_content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="finding.v1")
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FindingEvidenceLink(Base):
    __tablename__ = "finding_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "finding_version_id",
            "citation_key",
            name="uq_finding_evidence_citation_key",
        ),
        Index("ix_finding_evidence_links_investigation_id", "investigation_id"),
        Index("ix_finding_evidence_links_evidence_id", "evidence_item_id"),
        ForeignKeyConstraint(
            ["finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["evidence_item_id", "investigation_id"],
            ["evidence_items.id", "evidence_items.investigation_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["evidence_review_id"],
            ["evidence_reviews.id"],
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "relationship IN ('supports', 'contradicts', 'context')",
            name="ck_finding_evidence_relationship",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    finding_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    citation_key: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_review_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    relationship: Mapped[str] = mapped_column(String(16), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FindingRelation(Base):
    __tablename__ = "finding_relations"
    __table_args__ = (
        UniqueConstraint(
            "from_finding_version_id",
            "to_finding_version_id",
            "relation_kind",
            name="uq_finding_relation_edge",
        ),
        Index("ix_finding_relations_investigation_id", "investigation_id"),
        ForeignKeyConstraint(
            ["from_finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["to_finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "from_finding_version_id <> to_finding_version_id",
            name="ck_finding_relation_no_self",
        ),
        CheckConstraint(
            "relation_kind IN ('disputes', 'responds_to', 'addresses_question')",
            name="ck_finding_relation_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    from_finding_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_finding_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecordReview(Base):
    __tablename__ = "record_reviews"
    __table_args__ = (
        Index("ix_record_reviews_investigation_id", "investigation_id"),
        Index("ix_record_reviews_finding_version_id", "finding_version_id"),
        ForeignKeyConstraint(
            ["finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["reviewer_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "review_method = 'manual_review'",
            name="ck_record_review_method",
        ),
        CheckConstraint(
            "outcome IN ('accepted_for_inclusion', 'needs_revision', 'abstained')",
            name="ck_record_review_outcome",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    finding_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    review_method: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_review")
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    citations_checked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    numeric_transcription_checked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    limitations_checked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_wording_checked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dependency_disclosures: Mapped[list] = mapped_column(JSON, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
