from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DDL,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from reprolab.db.base import Base


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_report_id_investigation"),
        Index("ix_reports_investigation_id", "investigation_id"),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'withdrawn')",
            name="ck_report_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_report_version_id_investigation"),
        UniqueConstraint(
            "id", "report_id", "investigation_id",
            name="uq_report_version_id_report_investigation",
        ),
        UniqueConstraint(
            "id", "investigation_id", "content_hash",
            name="uq_report_version_id_investigation_hash",
        ),
        UniqueConstraint(
            "report_id",
            "version_number",
            name="uq_report_version_number",
        ),
        Index("ix_report_versions_investigation_id", "investigation_id"),
        Index("ix_report_versions_report_id", "report_id"),
        ForeignKeyConstraint(
            ["report_id", "investigation_id"],
            ["reports.id", "reports.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_version_id", "report_id", "investigation_id"],
            ["report_versions.id", "report_versions.report_id", "report_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "version_number > 0", name="ck_report_version_number_positive",
        ),
        CheckConstraint(
            "report_kind = 'analysis_record'", name="ck_report_version_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    report_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="analysis_record", server_default="analysis_record"
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    scope_claim_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False)
    unresolved_questions: Mapped[list] = mapped_column(JSON, nullable=False)
    canonical_content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="report.v1", server_default="report.v1"
    )
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReportFindingLink(Base):
    __tablename__ = "report_finding_links"
    __table_args__ = (
        UniqueConstraint(
            "report_version_id",
            "finding_version_id",
            name="uq_report_finding_version_selection",
        ),
        UniqueConstraint(
            "report_version_id",
            "section",
            "position",
            name="uq_report_finding_section_position",
        ),
        Index("ix_report_finding_links_investigation_id", "investigation_id"),
        Index("ix_report_finding_links_finding_version_id", "finding_version_id"),
        ForeignKeyConstraint(
            ["report_version_id", "investigation_id"],
            ["report_versions.id", "report_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "disposition IN ('included', 'excluded_with_reason')",
            name="ck_report_finding_disposition",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_report_finding_position_nonnegative",
        ),
        CheckConstraint(
            "length(trim(section, ' \t\n\r\f\v')) > 0",
            name="ck_report_finding_section_nonblank",
        ),
        CheckConstraint(
            "(disposition = 'included' AND exclusion_reason IS NULL) OR "
            "(disposition = 'excluded_with_reason' AND exclusion_reason IS NOT NULL "
            "AND length(trim(exclusion_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_report_finding_exclusion_reason",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    finding_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    finding_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    section: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReportEvent(Base):
    __tablename__ = "report_events"
    __table_args__ = (
        UniqueConstraint("report_id", "sequence_number", name="uq_report_event_sequence_number"),
        Index("ix_report_events_investigation_id", "investigation_id"),
        Index("ix_report_events_report_id", "report_id"),
        ForeignKeyConstraint(
            ["report_id", "investigation_id"],
            ["reports.id", "reports.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_version_id", "report_id", "investigation_id"],
            ["report_versions.id", "report_versions.report_id", "report_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_version_id", "investigation_id", "target_content_hash"],
            ["report_versions.id", "report_versions.investigation_id", "report_versions.content_hash"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "sequence_number > 0", name="ck_report_event_sequence_number_positive",
        ),
        CheckConstraint(
            "event_type IN ('published', 'withdrawn')",
            name="ck_report_event_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    report_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReportExport(Base):
    __tablename__ = "report_exports"
    __table_args__ = (
        UniqueConstraint("report_version_id", name="uq_report_export_report_version"),
        Index("ix_report_exports_investigation_id", "investigation_id"),
        Index("ix_report_exports_report_version_id", "report_version_id"),
        ForeignKeyConstraint(
            ["report_version_id", "investigation_id", "report_content_hash"],
            ["report_versions.id", "report_versions.investigation_id", "report_versions.content_hash"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(json_bytes) <= 2097152 AND json_size_bytes = length(json_bytes)",
            name="ck_report_export_json_size",
        ),
        CheckConstraint(
            "length(markdown_bytes) <= 2097152 AND markdown_size_bytes = length(markdown_bytes)",
            name="ck_report_export_markdown_size",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    report_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    json_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    markdown_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    json_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    markdown_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    json_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    markdown_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Keep metadata-created schemas guarded as well as migration-created PostgreSQL.
for _table in (ReportVersion.__table__, ReportFindingLink.__table__, ReportEvent.__table__):
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
