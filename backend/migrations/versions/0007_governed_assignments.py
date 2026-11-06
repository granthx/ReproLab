"""add governed role assignments, deliverables, and review delegations

Revision ID: 0007_governed_assignments
Revises: 0006_evidence_linked_reports
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_governed_assignments"
down_revision: Union[str, None] = "0006_evidence_linked_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_GOVERNANCE_TABLES = (
    "assignment_events", "assignment_deliverables", "delegation_events",
)


def upgrade() -> None:
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("task_kind", sa.String(length=128), nullable=False),
        sa.Column("constitution_version", sa.String(length=64), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("input_contract", sa.String(length=128), nullable=True),
        sa.Column("output_contract", sa.String(length=128), nullable=True),
        sa.Column("input_references", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("budget", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="assigned", nullable=False),
        sa.Column("lifecycle_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_event_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("not_required_reason", sa.Text(), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "constitution_version", "constitution_hash"],
            [
                "scientist_constitution_snapshots.role_id",
                "scientist_constitution_snapshots.constitution_version",
                "scientist_constitution_snapshots.constitution_hash",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "investigation_id", name="uq_role_assignment_id_investigation"),
        sa.CheckConstraint(
            "status IN ('assigned', 'in_progress', 'completed', 'revoked', 'blocked', "
            "'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_role_assignment_status",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0",
            name="ck_role_assignment_lifecycle_version_positive",
        ),
        sa.CheckConstraint(
            "length(trim(objective, ' \t\n\r\f\v')) > 0",
            name="ck_role_assignment_objective_nonblank",
        ),
        sa.CheckConstraint(
            "input_contract IS NULL OR output_contract IS NULL OR input_contract <> output_contract",
            name="ck_role_assignment_contracts_distinct",
        ),
        sa.CheckConstraint(
            "length(constitution_hash) = 64",
            name="ck_role_assignment_constitution_hash_length",
        ),
        sa.CheckConstraint(
            "last_event_hash IS NULL OR length(last_event_hash) = 64",
            name="ck_role_assignment_last_event_hash_length",
        ),
        sa.CheckConstraint(
            "status <> 'blocked' OR "
            "(blocked_reason IS NOT NULL AND length(trim(blocked_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_role_assignment_blocked_reason",
        ),
        sa.CheckConstraint(
            "status <> 'not_required' OR "
            "(not_required_reason IS NOT NULL AND length(trim(not_required_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_role_assignment_not_required_reason",
        ),
        sa.CheckConstraint(
            "status <> 'revoked' OR "
            "(revoked_reason IS NOT NULL AND length(trim(revoked_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_role_assignment_revoked_reason",
        ),
    )
    op.create_index(
        "ix_role_assignments_investigation_id",
        "role_assignments",
        ["investigation_id"],
    )
    op.create_index("ix_role_assignments_role_id", "role_assignments", ["role_id"])
    op.create_index("ix_role_assignments_status", "role_assignments", ["status"])

    op.create_table(
        "assignment_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("actor_role_id", sa.String(length=64), nullable=True),
        sa.Column("attribution_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assignment_id",
            "sequence_number",
            name="uq_assignment_event_sequence_number",
        ),
        sa.UniqueConstraint("assignment_id", "event_hash", name="uq_assignment_event_hash"),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_assignment_event_sequence_number_positive",
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'started', 'deliverable_submitted', 'completed', "
            "'revoked', 'blocked', 'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_assignment_event_type",
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN ('assigned', 'in_progress', 'completed', "
            "'revoked', 'blocked', 'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_assignment_event_from_status",
        ),
        sa.CheckConstraint(
            "to_status IS NULL OR to_status IN ('assigned', 'in_progress', 'completed', "
            "'revoked', 'blocked', 'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_assignment_event_to_status",
        ),
        sa.CheckConstraint(
            "event_type = 'created' OR to_status IS NOT NULL",
            name="ck_assignment_event_transition_target",
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('blocked', 'revoked', 'not_required', 'abstained', "
            "'handed_off', 'disputed') OR "
            "(reason IS NOT NULL AND length(trim(reason, ' \t\n\r\f\v')) > 0)",
            name="ck_assignment_event_terminal_reason",
        ),
        sa.CheckConstraint(
            "length(event_hash) = 64",
            name="ck_assignment_event_hash_length",
        ),
        sa.CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="ck_assignment_event_previous_hash_length",
        ),
    )
    op.create_index(
        "ix_assignment_events_investigation_id",
        "assignment_events",
        ["investigation_id"],
    )
    op.create_index("ix_assignment_events_assignment_id", "assignment_events", ["assignment_id"])

    op.create_table(
        "assignment_deliverables",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("schema_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("input_references", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
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
            name="uq_assignment_deliverable_id_investigation",
        ),
        sa.CheckConstraint(
            "kind IN ('analysis', 'audit', 'dataset_manifest', 'evidence_verification', "
            "'implementation_assessment', 'methodology_assessment', 'review', 'report_draft')",
            name="ck_assignment_deliverable_kind",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'accepted', 'rejected', 'superseded', 'withdrawn')",
            name="ck_assignment_deliverable_status",
        ),
        sa.CheckConstraint(
            "length(trim(schema_name, ' \t\n\r\f\v')) > 0",
            name="ck_assignment_deliverable_schema_nonblank",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_assignment_deliverable_content_hash_length",
        ),
    )
    op.create_index(
        "ix_assignment_deliverables_investigation_id",
        "assignment_deliverables",
        ["investigation_id"],
    )
    op.create_index(
        "ix_assignment_deliverables_assignment_id",
        "assignment_deliverables",
        ["assignment_id"],
    )
    op.create_index("ix_assignment_deliverables_status", "assignment_deliverables", ["status"])

    op.create_table(
        "review_delegations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("reviewer_role_id", sa.String(length=64), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("scope_hash", sa.String(length=64), nullable=False),
        sa.Column("delegation_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("target_kind", sa.String(length=32), server_default="finding_version_review", nullable=False),
        sa.Column("target_finding_version_id", sa.String(length=36), nullable=False),
        sa.Column("target_content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="issued", nullable=False),
        sa.Column("issued_by_role_id", sa.String(length=64), nullable=True),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), server_default="1", nullable=False),
        sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("issued_by_attribution_id", sa.String(length=36), nullable=False),
        sa.Column("redeemed_by_attribution_id", sa.String(length=36), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["issued_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["redeemed_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "assignment_id",
            "investigation_id",
            name="uq_review_delegation_assignment",
        ),
        sa.UniqueConstraint(
            "id",
            "assignment_id",
            "investigation_id",
            "delegation_hash",
            name="uq_review_delegation_identity",
        ),
        sa.UniqueConstraint("delegation_hash", name="uq_review_delegation_hash"),
        sa.CheckConstraint(
            "status IN ('issued', 'redeemed', 'revoked', 'expired')",
            name="ck_review_delegation_status",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0",
            name="ck_review_delegation_lifecycle_version_positive",
        ),
        sa.CheckConstraint(
            "length(scope_hash) = 64",
            name="ck_review_delegation_scope_hash_length",
        ),
        sa.CheckConstraint(
            "length(delegation_hash) = 64",
            name="ck_review_delegation_hash_length",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_review_delegation_token_hash_length",
        ),
        sa.CheckConstraint(
            "target_kind = 'finding_version_review'",
            name="ck_review_delegation_target_kind",
        ),
        sa.CheckConstraint(
            "length(target_content_hash) = 64",
            name="ck_review_delegation_target_content_hash_length",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_review_delegation_expiry_after_issue",
        ),
        sa.CheckConstraint(
            "max_uses > 0 AND max_uses <= 10 AND use_count >= 0 AND use_count <= max_uses",
            name="ck_review_delegation_use_count",
        ),
    )
    op.create_index(
        "ix_review_delegations_investigation_id",
        "review_delegations",
        ["investigation_id"],
    )
    op.create_index("ix_review_delegations_assignment_id", "review_delegations", ["assignment_id"])
    op.create_index(
        "ix_review_delegations_reviewer_role_id",
        "review_delegations",
        ["reviewer_role_id"],
    )
    op.create_index("ix_review_delegations_status", "review_delegations", ["status"])

    op.create_table(
        "delegation_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("delegation_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("delegation_hash", sa.String(length=64), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("actor_role_id", sa.String(length=64), nullable=True),
        sa.Column("reviewer_role_id", sa.String(length=64), nullable=True),
        sa.Column("attribution_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["delegation_id", "assignment_id", "investigation_id", "delegation_hash"],
            [
                "review_delegations.id",
                "review_delegations.assignment_id",
                "review_delegations.investigation_id",
                "review_delegations.delegation_hash",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delegation_id",
            "sequence_number",
            name="uq_delegation_event_sequence_number",
        ),
        sa.UniqueConstraint("delegation_id", "event_hash", name="uq_delegation_event_hash"),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_delegation_event_sequence_number_positive",
        ),
        sa.CheckConstraint(
            "event_type IN ('issued', 'redeemed', 'revoked', 'expired')",
            name="ck_delegation_event_type",
        ),
        sa.CheckConstraint(
            "event_type <> 'revoked' OR "
            "(reason IS NOT NULL AND length(trim(reason, ' \t\n\r\f\v')) > 0)",
            name="ck_delegation_event_revoke_reason",
        ),
        sa.CheckConstraint(
            "length(event_hash) = 64",
            name="ck_delegation_event_hash_length",
        ),
        sa.CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="ck_delegation_event_previous_hash_length",
        ),
    )
    op.create_index(
        "ix_delegation_events_investigation_id",
        "delegation_events",
        ["investigation_id"],
    )
    op.create_index("ix_delegation_events_delegation_id", "delegation_events", ["delegation_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table_name in IMMUTABLE_GOVERNANCE_TABLES:
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
    elif op.get_bind().dialect.name == "sqlite":
        for table_name in IMMUTABLE_GOVERNANCE_TABLES:
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
        for table_name in reversed(IMMUTABLE_GOVERNANCE_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name};")
            op.execute(f"DROP FUNCTION IF EXISTS reject_{table_name}_mutation();")
    elif op.get_bind().dialect.name == "sqlite":
        for table_name in reversed(IMMUTABLE_GOVERNANCE_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_delete;")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_update;")

    op.drop_index("ix_delegation_events_delegation_id", table_name="delegation_events")
    op.drop_index("ix_delegation_events_investigation_id", table_name="delegation_events")
    op.drop_table("delegation_events")
    op.drop_index("ix_review_delegations_status", table_name="review_delegations")
    op.drop_index("ix_review_delegations_reviewer_role_id", table_name="review_delegations")
    op.drop_index("ix_review_delegations_assignment_id", table_name="review_delegations")
    op.drop_index("ix_review_delegations_investigation_id", table_name="review_delegations")
    op.drop_table("review_delegations")
    op.drop_index("ix_assignment_deliverables_status", table_name="assignment_deliverables")
    op.drop_index("ix_assignment_deliverables_assignment_id", table_name="assignment_deliverables")
    op.drop_index(
        "ix_assignment_deliverables_investigation_id",
        table_name="assignment_deliverables",
    )
    op.drop_table("assignment_deliverables")
    op.drop_index("ix_assignment_events_assignment_id", table_name="assignment_events")
    op.drop_index("ix_assignment_events_investigation_id", table_name="assignment_events")
    op.drop_table("assignment_events")
    op.drop_index("ix_role_assignments_status", table_name="role_assignments")
    op.drop_index("ix_role_assignments_role_id", table_name="role_assignments")
    op.drop_index("ix_role_assignments_investigation_id", table_name="role_assignments")
    op.drop_table("role_assignments")
