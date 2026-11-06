"""add evidence-linked report versions and bounded exports

Revision ID: 0006_evidence_linked_reports
Revises: 0005_traceable_findings
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_evidence_linked_reports"
down_revision: Union[str, None] = "0005_traceable_findings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MAX_EXPORT_BYTES = 2 * 1024 * 1024
IMMUTABLE_REPORT_TABLES = ("report_versions", "report_finding_links", "report_events")


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "investigation_id", name="uq_report_id_investigation"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'withdrawn')",
            name="ck_report_status",
        ),
    )
    op.create_index(
        "ix_reports_investigation_id",
        "reports",
        ["investigation_id"],
    )

    op.create_table(
        "report_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("parent_version_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "report_kind",
            sa.String(length=32),
            server_default="analysis_record",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("scope_claim_ids", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("canonical_content_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=32),
            server_default="report.v1",
            nullable=False,
        ),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "investigation_id"],
            ["reports.id", "reports.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id", "report_id", "investigation_id"],
            ["report_versions.id", "report_versions.report_id", "report_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "investigation_id",
            name="uq_report_version_id_investigation",
        ),
        sa.UniqueConstraint(
            "id", "report_id", "investigation_id",
            name="uq_report_version_id_report_investigation",
        ),
        sa.UniqueConstraint(
            "id", "investigation_id", "content_hash",
            name="uq_report_version_id_investigation_hash",
        ),
        sa.UniqueConstraint(
            "report_id",
            "version_number",
            name="uq_report_version_number",
        ),
        sa.CheckConstraint(
            "version_number > 0", name="ck_report_version_number_positive",
        ),
        sa.CheckConstraint(
            "report_kind = 'analysis_record'", name="ck_report_version_kind",
        ),
    )
    op.create_index(
        "ix_report_versions_investigation_id",
        "report_versions",
        ["investigation_id"],
    )
    op.create_index("ix_report_versions_report_id", "report_versions", ["report_id"])

    op.create_table(
        "report_finding_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_version_id", sa.String(length=36), nullable=False),
        sa.Column("finding_version_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("finding_content_hash", sa.String(length=64), nullable=False),
        sa.Column("section", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["report_version_id", "investigation_id"],
            ["report_versions.id", "report_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_version_id",
            "finding_version_id",
            name="uq_report_finding_version_selection",
        ),
        sa.UniqueConstraint(
            "report_version_id",
            "section",
            "position",
            name="uq_report_finding_section_position",
        ),
        sa.CheckConstraint(
            "disposition IN ('included', 'excluded_with_reason')",
            name="ck_report_finding_disposition",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_report_finding_position_nonnegative",
        ),
        sa.CheckConstraint(
            "length(trim(section, ' \t\n\r\f\v')) > 0",
            name="ck_report_finding_section_nonblank",
        ),
        sa.CheckConstraint(
            "(disposition = 'included' AND exclusion_reason IS NULL) OR "
            "(disposition = 'excluded_with_reason' AND exclusion_reason IS NOT NULL "
            "AND length(trim(exclusion_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_report_finding_exclusion_reason",
        ),
    )
    op.create_index(
        "ix_report_finding_links_investigation_id",
        "report_finding_links",
        ["investigation_id"],
    )
    op.create_index(
        "ix_report_finding_links_finding_version_id",
        "report_finding_links",
        ["finding_version_id"],
    )

    op.create_table(
        "report_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("report_version_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("target_content_hash", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("attribution_id", sa.String(length=36), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "investigation_id"],
            ["reports.id", "reports.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_version_id", "report_id", "investigation_id"],
            ["report_versions.id", "report_versions.report_id", "report_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_version_id", "investigation_id", "target_content_hash"],
            ["report_versions.id", "report_versions.investigation_id", "report_versions.content_hash"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", "sequence_number", name="uq_report_event_sequence_number"),
        sa.CheckConstraint(
            "sequence_number > 0", name="ck_report_event_sequence_number_positive",
        ),
        sa.CheckConstraint(
            "event_type IN ('published', 'withdrawn')",
            name="ck_report_event_type",
        ),
    )
    op.create_index(
        "ix_report_events_investigation_id",
        "report_events",
        ["investigation_id"],
    )
    op.create_index("ix_report_events_report_id", "report_events", ["report_id"])

    op.create_table(
        "report_exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_version_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("report_content_hash", sa.String(length=64), nullable=False),
        sa.Column("json_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("markdown_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("json_size_bytes", sa.Integer(), nullable=False),
        sa.Column("markdown_size_bytes", sa.Integer(), nullable=False),
        sa.Column("json_sha256", sa.String(length=64), nullable=False),
        sa.Column("markdown_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["report_version_id", "investigation_id", "report_content_hash"],
            ["report_versions.id", "report_versions.investigation_id", "report_versions.content_hash"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_version_id", name="uq_report_export_report_version"),
        sa.CheckConstraint(
            f"length(json_bytes) <= {MAX_EXPORT_BYTES} AND json_size_bytes = length(json_bytes)",
            name="ck_report_export_json_size",
        ),
        sa.CheckConstraint(
            f"length(markdown_bytes) <= {MAX_EXPORT_BYTES} AND markdown_size_bytes = length(markdown_bytes)",
            name="ck_report_export_markdown_size",
        ),
    )
    op.create_index(
        "ix_report_exports_investigation_id",
        "report_exports",
        ["investigation_id"],
    )
    op.create_index(
        "ix_report_exports_report_version_id",
        "report_exports",
        ["report_version_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table_name in IMMUTABLE_REPORT_TABLES:
            op.execute(f"""
                CREATE FUNCTION reject_{table_name}_mutation() RETURNS trigger
                LANGUAGE plpgsql AS $$
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


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in reversed(IMMUTABLE_REPORT_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name};")
            op.execute(f"DROP FUNCTION IF EXISTS reject_{table_name}_mutation();")

    op.drop_index("ix_report_exports_report_version_id", table_name="report_exports")
    op.drop_index("ix_report_exports_investigation_id", table_name="report_exports")
    op.drop_table("report_exports")
    op.drop_index("ix_report_events_report_id", table_name="report_events")
    op.drop_index("ix_report_events_investigation_id", table_name="report_events")
    op.drop_table("report_events")
    op.drop_index(
        "ix_report_finding_links_finding_version_id",
        table_name="report_finding_links",
    )
    op.drop_index(
        "ix_report_finding_links_investigation_id",
        table_name="report_finding_links",
    )
    op.drop_table("report_finding_links")
    op.drop_index("ix_report_versions_report_id", table_name="report_versions")
    op.drop_index(
        "ix_report_versions_investigation_id",
        table_name="report_versions",
    )
    op.drop_table("report_versions")
    op.drop_index("ix_reports_investigation_id", table_name="reports")
    op.drop_table("reports")
