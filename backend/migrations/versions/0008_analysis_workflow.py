"""add Stage 4 analysis-only LangGraph workflow runs, checkpoints, events, and model calls

Revision ID: 0008_analysis_workflow
Revises: 0007_governed_assignments
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_analysis_workflow"
down_revision: Union[str, None] = "0007_governed_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABLE_WORKFLOW_TABLES = (
    "workflow_checkpoints",
    "workflow_events",
    "workflow_model_calls",
)


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column(
            "workflow_kind",
            sa.String(length=32),
            server_default="analysis_only_v1",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column(
            "current_node",
            sa.String(length=64),
            server_default="atlas_intake",
            nullable=False,
        ),
        sa.Column(
            "provider_mode",
            sa.String(length=32),
            server_default="source_grounded",
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("lifecycle_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("latest_checkpoint_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latest_checkpoint_hash", sa.String(length=64), nullable=True),
        sa.Column("latest_event_hash", sa.String(length=64), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("abstained_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("id", "investigation_id", name="uq_workflow_run_id_investigation"),
        sa.UniqueConstraint(
            "investigation_id",
            "idempotency_key",
            name="uq_workflow_run_investigation_idempotency",
        ),
        sa.CheckConstraint(
            "workflow_kind = 'analysis_only_v1'",
            name="ck_workflow_run_kind",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'awaiting_human_review', 'blocked', 'abstained', "
            "'completed', 'cancelled')",
            name="ck_workflow_run_status",
        ),
        sa.CheckConstraint(
            "current_node IN ('atlas_intake', 'quill_extraction', 'sagan_verification', "
            "'hypatia_audit', 'turing_assessment', 'curie_dataset', 'human_review_gate', "
            "'popper_review', 'franklin_synthesis', 'terminal')",
            name="ck_workflow_run_current_node",
        ),
        sa.CheckConstraint(
            "provider_mode IN ('source_grounded', 'gemini')",
            name="ck_workflow_run_provider_mode",
        ),
        sa.CheckConstraint(
            "lifecycle_version > 0",
            name="ck_workflow_run_lifecycle_version_positive",
        ),
        sa.CheckConstraint(
            "latest_checkpoint_seq >= 0",
            name="ck_workflow_run_latest_checkpoint_seq_nonnegative",
        ),
        sa.CheckConstraint(
            "latest_checkpoint_hash IS NULL OR length(latest_checkpoint_hash) = 64",
            name="ck_workflow_run_latest_checkpoint_hash_length",
        ),
        sa.CheckConstraint(
            "latest_event_hash IS NULL OR length(latest_event_hash) = 64",
            name="ck_workflow_run_latest_event_hash_length",
        ),
        sa.CheckConstraint(
            "status <> 'blocked' OR "
            "(blocked_reason IS NOT NULL AND length(trim(blocked_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_run_blocked_reason",
        ),
        sa.CheckConstraint(
            "status <> 'abstained' OR "
            "(abstained_reason IS NOT NULL AND length(trim(abstained_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_run_abstained_reason",
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' OR "
            "(cancelled_reason IS NOT NULL AND length(trim(cancelled_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_run_cancelled_reason",
        ),
    )
    op.create_index("ix_workflow_runs_investigation_id", "workflow_runs", ["investigation_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "workflow_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("node_name", sa.String(length=64), nullable=False),
        sa.Column("stage_status", sa.String(length=32), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=True),
        sa.Column("assignment_id", sa.String(length=36), nullable=True),
        sa.Column("deliverable_id", sa.String(length=36), nullable=True),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_checkpoint_hash", sa.String(length=64), nullable=True),
        sa.Column("checkpoint_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "investigation_id"],
            ["workflow_runs.id", "workflow_runs.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deliverable_id", "investigation_id"],
            ["assignment_deliverables.id", "assignment_deliverables.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_run_id",
            "sequence_number",
            name="uq_workflow_checkpoint_sequence_number",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "checkpoint_hash",
            name="uq_workflow_checkpoint_hash",
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_workflow_checkpoint_sequence_positive",
        ),
        sa.CheckConstraint(
            "node_name IN ('atlas_intake', 'quill_extraction', 'sagan_verification', "
            "'hypatia_audit', 'turing_assessment', 'curie_dataset', 'human_review_gate', "
            "'popper_review', 'franklin_synthesis', 'terminal')",
            name="ck_workflow_checkpoint_node_name",
        ),
        sa.CheckConstraint(
            "stage_status IN ('entered', 'completed', 'awaiting_human_review', 'blocked', 'abstained')",
            name="ck_workflow_checkpoint_stage_status",
        ),
        sa.CheckConstraint(
            "length(state_hash) = 64",
            name="ck_workflow_checkpoint_state_hash_length",
        ),
        sa.CheckConstraint(
            "previous_checkpoint_hash IS NULL OR length(previous_checkpoint_hash) = 64",
            name="ck_workflow_checkpoint_previous_hash_length",
        ),
        sa.CheckConstraint(
            "length(checkpoint_hash) = 64",
            name="ck_workflow_checkpoint_hash_length",
        ),
    )
    op.create_index(
        "ix_workflow_checkpoints_investigation_id",
        "workflow_checkpoints",
        ["investigation_id"],
    )
    op.create_index(
        "ix_workflow_checkpoints_workflow_run_id",
        "workflow_checkpoints",
        ["workflow_run_id"],
    )

    op.create_table(
        "workflow_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("node_name", sa.String(length=64), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=True),
        sa.Column("attribution_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "investigation_id"],
            ["workflow_runs.id", "workflow_runs.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_run_id",
            "sequence_number",
            name="uq_workflow_event_sequence_number",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "event_hash",
            name="uq_workflow_event_hash",
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_workflow_event_sequence_positive",
        ),
        sa.CheckConstraint(
            "event_type IN ('run_created', 'node_completed', 'gate_paused', 'gate_approved', "
            "'gate_rejected', 'model_call_recorded', 'run_blocked', 'run_abstained', "
            "'run_resumed', 'run_completed', 'run_cancelled')",
            name="ck_workflow_event_type",
        ),
        sa.CheckConstraint(
            "node_name IN ('atlas_intake', 'quill_extraction', 'sagan_verification', "
            "'hypatia_audit', 'turing_assessment', 'curie_dataset', 'human_review_gate', "
            "'popper_review', 'franklin_synthesis', 'terminal')",
            name="ck_workflow_event_node_name",
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('gate_rejected', 'run_blocked', 'run_abstained', 'run_cancelled') OR "
            "(reason IS NOT NULL AND length(trim(reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_event_terminal_reason",
        ),
        sa.CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="ck_workflow_event_previous_hash_length",
        ),
        sa.CheckConstraint(
            "length(event_hash) = 64",
            name="ck_workflow_event_hash_length",
        ),
    )
    op.create_index("ix_workflow_events_investigation_id", "workflow_events", ["investigation_id"])
    op.create_index("ix_workflow_events_workflow_run_id", "workflow_events", ["workflow_run_id"])

    op.create_table(
        "workflow_model_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("routing_category", sa.String(length=64), nullable=False),
        sa.Column("call_index", sa.Integer(), nullable=False),
        sa.Column("max_calls_ceiling", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_sha256", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id", "investigation_id"],
            ["workflow_runs.id", "workflow_runs.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assignment_id",
            "call_index",
            name="uq_workflow_model_call_assignment_index",
        ),
        sa.CheckConstraint(
            "provider IN ('gemini', 'deterministic_none')",
            name="ck_workflow_model_call_provider",
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'skipped_deterministic', 'skipped_conditional_not_needed', "
            "'failed_provider_error', 'blocked_budget')",
            name="ck_workflow_model_call_status",
        ),
        sa.CheckConstraint(
            "call_index > 0",
            name="ck_workflow_model_call_index_positive",
        ),
        sa.CheckConstraint(
            "max_calls_ceiling >= 0",
            name="ck_workflow_model_call_ceiling_nonnegative",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name="ck_workflow_model_call_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "length(prompt_sha256) = 64",
            name="ck_workflow_model_call_prompt_hash_length",
        ),
        sa.CheckConstraint(
            "response_sha256 IS NULL OR length(response_sha256) = 64",
            name="ck_workflow_model_call_response_hash_length",
        ),
        sa.CheckConstraint(
            "length(trim(model_name, ' \t\n\r\f\v')) > 0",
            name="ck_workflow_model_call_model_name_nonblank",
        ),
        sa.CheckConstraint(
            "length(trim(routing_category, ' \t\n\r\f\v')) > 0",
            name="ck_workflow_model_call_routing_nonblank",
        ),
    )
    op.create_index(
        "ix_workflow_model_calls_investigation_id",
        "workflow_model_calls",
        ["investigation_id"],
    )
    op.create_index(
        "ix_workflow_model_calls_workflow_run_id",
        "workflow_model_calls",
        ["workflow_run_id"],
    )
    op.create_index(
        "ix_workflow_model_calls_assignment_id",
        "workflow_model_calls",
        ["assignment_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table_name in IMMUTABLE_WORKFLOW_TABLES:
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
        for table_name in IMMUTABLE_WORKFLOW_TABLES:
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
        for table_name in reversed(IMMUTABLE_WORKFLOW_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name};")
            op.execute(f"DROP FUNCTION IF EXISTS reject_{table_name}_mutation();")
    elif op.get_bind().dialect.name == "sqlite":
        for table_name in reversed(IMMUTABLE_WORKFLOW_TABLES):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_delete;")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_update;")

    op.drop_index("ix_workflow_model_calls_assignment_id", table_name="workflow_model_calls")
    op.drop_index("ix_workflow_model_calls_workflow_run_id", table_name="workflow_model_calls")
    op.drop_index("ix_workflow_model_calls_investigation_id", table_name="workflow_model_calls")
    op.drop_table("workflow_model_calls")
    op.drop_index("ix_workflow_events_workflow_run_id", table_name="workflow_events")
    op.drop_index("ix_workflow_events_investigation_id", table_name="workflow_events")
    op.drop_table("workflow_events")
    op.drop_index("ix_workflow_checkpoints_workflow_run_id", table_name="workflow_checkpoints")
    op.drop_index("ix_workflow_checkpoints_investigation_id", table_name="workflow_checkpoints")
    op.drop_table("workflow_checkpoints")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_investigation_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")

