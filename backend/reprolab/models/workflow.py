from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DDL,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from reprolab.db.base import Base


WORKFLOW_KINDS = ("analysis_only_v1", "full_reproduction_v1")
WORKFLOW_STATUSES = (
    "running",
    "awaiting_human_review",
    "blocked",
    "abstained",
    "completed",
    "cancelled",
)
WORKFLOW_NODES = (
    "atlas_intake",
    "quill_extraction",
    "sagan_verification",
    "hypatia_audit",
    "turing_assessment",
    "curie_dataset",
    "human_review_gate",
    "faraday_execution",
    "fisher_evaluation",
    "popper_review",
    "shannon_sensitivity",
    "noether_replication",
    "sagan_provenance",
    "franklin_synthesis",
    "terminal",
)
WORKFLOW_PROVIDER_MODES = ("source_grounded", "gemini")
CHECKPOINT_STAGE_STATUSES = (
    "entered",
    "completed",
    "awaiting_human_review",
    "blocked",
    "abstained",
)
WORKFLOW_EVENT_TYPES = (
    "run_created",
    "node_completed",
    "gate_paused",
    "gate_approved",
    "gate_rejected",
    "model_call_recorded",
    "run_blocked",
    "run_abstained",
    "run_resumed",
    "run_completed",
    "run_cancelled",
)
MODEL_CALL_PROVIDERS = ("gemini", "deterministic_none")
MODEL_CALL_STATUSES = (
    "succeeded",
    "skipped_deterministic",
    "skipped_conditional_not_needed",
    "failed_provider_error",
    "blocked_budget",
)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_workflow_run_id_investigation"),
        UniqueConstraint(
            "investigation_id",
            "idempotency_key",
            name="uq_workflow_run_investigation_idempotency",
        ),
        Index("ix_workflow_runs_investigation_id", "investigation_id"),
        Index("ix_workflow_runs_status", "status"),
        ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "workflow_kind IN ('analysis_only_v1', 'full_reproduction_v1')",
            name="ck_workflow_run_kind",
        ),
        CheckConstraint(
            "status IN ('running', 'awaiting_human_review', 'blocked', 'abstained', "
            "'completed', 'cancelled')",
            name="ck_workflow_run_status",
        ),
        CheckConstraint(
            "current_node IN ('atlas_intake', 'quill_extraction', 'sagan_verification', "
            "'hypatia_audit', 'turing_assessment', 'curie_dataset', 'human_review_gate', "
            "'faraday_execution', 'fisher_evaluation', 'popper_review', 'shannon_sensitivity', "
            "'noether_replication', 'sagan_provenance', 'franklin_synthesis', 'terminal')",
            name="ck_workflow_run_current_node",
        ),
        CheckConstraint(
            "provider_mode IN ('source_grounded', 'gemini')",
            name="ck_workflow_run_provider_mode",
        ),
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_workflow_run_lifecycle_version_positive",
        ),
        CheckConstraint(
            "latest_checkpoint_seq >= 0",
            name="ck_workflow_run_latest_checkpoint_seq_nonnegative",
        ),
        CheckConstraint(
            "latest_checkpoint_hash IS NULL OR length(latest_checkpoint_hash) = 64",
            name="ck_workflow_run_latest_checkpoint_hash_length",
        ),
        CheckConstraint(
            "latest_event_hash IS NULL OR length(latest_event_hash) = 64",
            name="ck_workflow_run_latest_event_hash_length",
        ),
        CheckConstraint(
            "status <> 'blocked' OR "
            "(blocked_reason IS NOT NULL AND length(trim(blocked_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_run_blocked_reason",
        ),
        CheckConstraint(
            "status <> 'abstained' OR "
            "(abstained_reason IS NOT NULL AND length(trim(abstained_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_run_abstained_reason",
        ),
        CheckConstraint(
            "status <> 'cancelled' OR "
            "(cancelled_reason IS NOT NULL AND length(trim(cancelled_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_run_cancelled_reason",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workflow_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="analysis_only_v1", server_default="analysis_only_v1"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running", server_default="running"
    )
    current_node: Mapped[str] = mapped_column(
        String(64), nullable=False, default="atlas_intake", server_default="atlas_intake"
    )
    provider_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="source_grounded", server_default="source_grounded"
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    latest_checkpoint_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    latest_checkpoint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstained_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "sequence_number",
            name="uq_workflow_checkpoint_sequence_number",
        ),
        UniqueConstraint(
            "workflow_run_id",
            "checkpoint_hash",
            name="uq_workflow_checkpoint_hash",
        ),
        Index("ix_workflow_checkpoints_investigation_id", "investigation_id"),
        Index("ix_workflow_checkpoints_workflow_run_id", "workflow_run_id"),
        ForeignKeyConstraint(
            ["workflow_run_id", "investigation_id"],
            ["workflow_runs.id", "workflow_runs.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["deliverable_id", "investigation_id"],
            ["assignment_deliverables.id", "assignment_deliverables.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="ck_workflow_checkpoint_sequence_positive",
        ),
        CheckConstraint(
            "node_name IN ('atlas_intake', 'quill_extraction', 'sagan_verification', "
            "'hypatia_audit', 'turing_assessment', 'curie_dataset', 'human_review_gate', "
            "'faraday_execution', 'fisher_evaluation', 'popper_review', 'shannon_sensitivity', "
            "'noether_replication', 'sagan_provenance', 'franklin_synthesis', 'terminal')",
            name="ck_workflow_checkpoint_node_name",
        ),
        CheckConstraint(
            "stage_status IN ('entered', 'completed', 'awaiting_human_review', 'blocked', 'abstained')",
            name="ck_workflow_checkpoint_stage_status",
        ),
        CheckConstraint(
            "length(state_hash) = 64",
            name="ck_workflow_checkpoint_state_hash_length",
        ),
        CheckConstraint(
            "previous_checkpoint_hash IS NULL OR length(previous_checkpoint_hash) = 64",
            name="ck_workflow_checkpoint_previous_hash_length",
        ),
        CheckConstraint(
            "length(checkpoint_hash) = 64",
            name="ck_workflow_checkpoint_hash_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    role_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assignment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deliverable_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_checkpoint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checkpoint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "sequence_number",
            name="uq_workflow_event_sequence_number",
        ),
        UniqueConstraint(
            "workflow_run_id",
            "event_hash",
            name="uq_workflow_event_hash",
        ),
        Index("ix_workflow_events_investigation_id", "investigation_id"),
        Index("ix_workflow_events_workflow_run_id", "workflow_run_id"),
        ForeignKeyConstraint(
            ["workflow_run_id", "investigation_id"],
            ["workflow_runs.id", "workflow_runs.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="ck_workflow_event_sequence_positive",
        ),
        CheckConstraint(
            "event_type IN ('run_created', 'node_completed', 'gate_paused', 'gate_approved', "
            "'gate_rejected', 'model_call_recorded', 'run_blocked', 'run_abstained', "
            "'run_resumed', 'run_completed', 'run_cancelled')",
            name="ck_workflow_event_type",
        ),
        CheckConstraint(
            "node_name IN ('atlas_intake', 'quill_extraction', 'sagan_verification', "
            "'hypatia_audit', 'turing_assessment', 'curie_dataset', 'human_review_gate', "
            "'faraday_execution', 'fisher_evaluation', 'popper_review', 'shannon_sensitivity', "
            "'noether_replication', 'sagan_provenance', 'franklin_synthesis', 'terminal')",
            name="ck_workflow_event_node_name",
        ),
        CheckConstraint(
            "event_type NOT IN ('gate_rejected', 'run_blocked', 'run_abstained', 'run_cancelled') OR "
            "(reason IS NOT NULL AND length(trim(reason, ' \t\n\r\f\v')) > 0)",
            name="ck_workflow_event_terminal_reason",
        ),
        CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="ck_workflow_event_previous_hash_length",
        ),
        CheckConstraint(
            "length(event_hash) = 64",
            name="ck_workflow_event_hash_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    role_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowModelCall(Base):
    __tablename__ = "workflow_model_calls"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "call_index",
            name="uq_workflow_model_call_assignment_index",
        ),
        Index("ix_workflow_model_calls_investigation_id", "investigation_id"),
        Index("ix_workflow_model_calls_workflow_run_id", "workflow_run_id"),
        Index("ix_workflow_model_calls_assignment_id", "assignment_id"),
        ForeignKeyConstraint(
            ["workflow_run_id", "investigation_id"],
            ["workflow_runs.id", "workflow_runs.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "provider IN ('gemini', 'deterministic_none')",
            name="ck_workflow_model_call_provider",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'skipped_deterministic', 'skipped_conditional_not_needed', "
            "'failed_provider_error', 'blocked_budget')",
            name="ck_workflow_model_call_status",
        ),
        CheckConstraint(
            "call_index > 0",
            name="ck_workflow_model_call_index_positive",
        ),
        CheckConstraint(
            "max_calls_ceiling >= 0",
            name="ck_workflow_model_call_ceiling_nonnegative",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name="ck_workflow_model_call_tokens_nonnegative",
        ),
        CheckConstraint(
            "length(prompt_sha256) = 64",
            name="ck_workflow_model_call_prompt_hash_length",
        ),
        CheckConstraint(
            "response_sha256 IS NULL OR length(response_sha256) = 64",
            name="ck_workflow_model_call_response_hash_length",
        ),
        CheckConstraint(
            "length(trim(model_name, ' \t\n\r\f\v')) > 0",
            name="ck_workflow_model_call_model_name_nonblank",
        ),
        CheckConstraint(
            "length(trim(routing_category, ' \t\n\r\f\v')) > 0",
            name="ck_workflow_model_call_routing_nonblank",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assignment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    routing_category: Mapped[str] = mapped_column(String(64), nullable=False)
    call_index: Mapped[int] = mapped_column(Integer, nullable=False)
    max_calls_ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


for _table in (
    WorkflowCheckpoint.__table__,
    WorkflowEvent.__table__,
    WorkflowModelCall.__table__,
):
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


__all__ = [
    "WorkflowCheckpoint",
    "WorkflowEvent",
    "WorkflowModelCall",
    "WorkflowRun",
]

