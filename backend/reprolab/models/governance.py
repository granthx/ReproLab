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


ASSIGNMENT_STATUSES = (
    "assigned",
    "in_progress",
    "completed",
    "revoked",
    "blocked",
    "not_required",
    "abstained",
    "handed_off",
    "disputed",
)
ASSIGNMENT_EVENT_TYPES = (
    "created",
    "started",
    "deliverable_submitted",
    "completed",
    "revoked",
    "blocked",
    "not_required",
    "abstained",
    "handed_off",
    "disputed",
)
DELIVERABLE_KINDS = (
    "analysis",
    "audit",
    "dataset_manifest",
    "evidence_verification",
    "implementation_assessment",
    "methodology_assessment",
    "review",
    "report_draft",
)
DELIVERABLE_STATUSES = (
    "draft",
    "submitted",
    "accepted",
    "rejected",
    "superseded",
    "withdrawn",
)
DELEGATION_STATUSES = ("issued", "redeemed", "revoked", "expired")
DELEGATION_EVENT_TYPES = ("issued", "redeemed", "revoked", "expired")


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_role_assignment_id_investigation"),
        Index("ix_role_assignments_investigation_id", "investigation_id"),
        Index("ix_role_assignments_role_id", "role_id"),
        Index("ix_role_assignments_status", "status"),
        ForeignKeyConstraint(
            ["investigation_id"],
            ["investigations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["role_id", "constitution_version", "constitution_hash"],
            [
                "scientist_constitution_snapshots.role_id",
                "scientist_constitution_snapshots.constitution_version",
                "scientist_constitution_snapshots.constitution_hash",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('assigned', 'in_progress', 'completed', 'revoked', 'blocked', "
            "'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_role_assignment_status",
        ),
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_role_assignment_lifecycle_version_positive",
        ),
        CheckConstraint(
            "length(trim(objective, ' \t\n\r\f\v')) > 0",
            name="ck_role_assignment_objective_nonblank",
        ),
        CheckConstraint(
            "input_contract IS NULL OR output_contract IS NULL OR input_contract <> output_contract",
            name="ck_role_assignment_contracts_distinct",
        ),
        CheckConstraint(
            "length(constitution_hash) = 64",
            name="ck_role_assignment_constitution_hash_length",
        ),
        CheckConstraint(
            "last_event_hash IS NULL OR length(last_event_hash) = 64",
            name="ck_role_assignment_last_event_hash_length",
        ),
        CheckConstraint(
            "status <> 'blocked' OR "
            "(blocked_reason IS NOT NULL AND length(trim(blocked_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_role_assignment_blocked_reason",
        ),
        CheckConstraint(
            "status <> 'not_required' OR "
            "(not_required_reason IS NOT NULL AND length(trim(not_required_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_role_assignment_not_required_reason",
        ),
        CheckConstraint(
            "status <> 'revoked' OR "
            "(revoked_reason IS NOT NULL AND length(trim(revoked_reason, ' \t\n\r\f\v')) > 0)",
            name="ck_role_assignment_revoked_reason",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_kind: Mapped[str] = mapped_column(String(128), nullable=False)
    constitution_version: Mapped[str] = mapped_column(String(64), nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    input_contract: Mapped[str | None] = mapped_column(String(128), nullable=True)
    output_contract: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_references: Mapped[list] = mapped_column(JSON, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    budget: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="assigned", server_default="assigned"
    )
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    last_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    not_required_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssignmentEvent(Base):
    __tablename__ = "assignment_events"
    __table_args__ = (
        UniqueConstraint("assignment_id", "sequence_number", name="uq_assignment_event_sequence_number"),
        UniqueConstraint("assignment_id", "event_hash", name="uq_assignment_event_hash"),
        Index("ix_assignment_events_investigation_id", "investigation_id"),
        Index("ix_assignment_events_assignment_id", "assignment_id"),
        ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="ck_assignment_event_sequence_number_positive",
        ),
        CheckConstraint(
            "event_type IN ('created', 'started', 'deliverable_submitted', 'completed', "
            "'revoked', 'blocked', 'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_assignment_event_type",
        ),
        CheckConstraint(
            "from_status IS NULL OR from_status IN ('assigned', 'in_progress', 'completed', "
            "'revoked', 'blocked', 'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_assignment_event_from_status",
        ),
        CheckConstraint(
            "to_status IS NULL OR to_status IN ('assigned', 'in_progress', 'completed', "
            "'revoked', 'blocked', 'not_required', 'abstained', 'handed_off', 'disputed')",
            name="ck_assignment_event_to_status",
        ),
        CheckConstraint(
            "event_type = 'created' OR to_status IS NOT NULL",
            name="ck_assignment_event_transition_target",
        ),
        CheckConstraint(
            "event_type NOT IN ('blocked', 'revoked', 'not_required', 'abstained', "
            "'handed_off', 'disputed') OR "
            "(reason IS NOT NULL AND length(trim(reason, ' \t\n\r\f\v')) > 0)",
            name="ck_assignment_event_terminal_reason",
        ),
        CheckConstraint(
            "length(event_hash) = 64",
            name="ck_assignment_event_hash_length",
        ),
        CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="ck_assignment_event_previous_hash_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor_role_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AssignmentDeliverable(Base):
    __tablename__ = "assignment_deliverables"
    __table_args__ = (
        UniqueConstraint("id", "investigation_id", name="uq_assignment_deliverable_id_investigation"),
        Index("ix_assignment_deliverables_investigation_id", "investigation_id"),
        Index("ix_assignment_deliverables_assignment_id", "assignment_id"),
        Index("ix_assignment_deliverables_status", "status"),
        ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "kind IN ('analysis', 'audit', 'dataset_manifest', 'evidence_verification', "
            "'implementation_assessment', 'methodology_assessment', 'review', 'report_draft')",
            name="ck_assignment_deliverable_kind",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'accepted', 'rejected', 'superseded', 'withdrawn')",
            name="ck_assignment_deliverable_status",
        ),
        CheckConstraint(
            "length(trim(schema_name, ' \t\n\r\f\v')) > 0",
            name="ck_assignment_deliverable_schema_nonblank",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_assignment_deliverable_content_hash_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_references: Mapped[list] = mapped_column(JSON, nullable=False)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReviewDelegation(Base):
    __tablename__ = "review_delegations"
    __table_args__ = (
        UniqueConstraint("id", "assignment_id", "investigation_id", name="uq_review_delegation_assignment"),
        UniqueConstraint(
            "id",
            "assignment_id",
            "investigation_id",
            "delegation_hash",
            name="uq_review_delegation_identity",
        ),
        UniqueConstraint("delegation_hash", name="uq_review_delegation_hash"),
        Index("ix_review_delegations_investigation_id", "investigation_id"),
        Index("ix_review_delegations_assignment_id", "assignment_id"),
        Index("ix_review_delegations_reviewer_role_id", "reviewer_role_id"),
        Index("ix_review_delegations_status", "status"),
        ForeignKeyConstraint(
            ["assignment_id", "investigation_id"],
            ["role_assignments.id", "role_assignments.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_finding_version_id", "investigation_id"],
            ["finding_versions.id", "finding_versions.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["issued_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["redeemed_by_attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('issued', 'redeemed', 'revoked', 'expired')",
            name="ck_review_delegation_status",
        ),
        CheckConstraint(
            "lifecycle_version > 0",
            name="ck_review_delegation_lifecycle_version_positive",
        ),
        CheckConstraint(
            "length(scope_hash) = 64",
            name="ck_review_delegation_scope_hash_length",
        ),
        CheckConstraint(
            "length(delegation_hash) = 64",
            name="ck_review_delegation_hash_length",
        ),
        CheckConstraint(
            "length(token_hash) = 64",
            name="ck_review_delegation_token_hash_length",
        ),
        CheckConstraint(
            "target_kind = 'finding_version_review'",
            name="ck_review_delegation_target_kind",
        ),
        CheckConstraint(
            "length(target_content_hash) = 64",
            name="ck_review_delegation_target_content_hash_length",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="ck_review_delegation_expiry_after_issue",
        ),
        CheckConstraint(
            "max_uses > 0 AND max_uses <= 10 AND use_count >= 0 AND use_count <= max_uses",
            name="ck_review_delegation_use_count",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assignment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reviewer_role_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    delegation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="finding_version_review", server_default="finding_version_review"
    )
    target_finding_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="issued", server_default="issued"
    )
    issued_by_role_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    issued_by_attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    redeemed_by_attribution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lifecycle_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )


class DelegationEvent(Base):
    __tablename__ = "delegation_events"
    __table_args__ = (
        UniqueConstraint("delegation_id", "sequence_number", name="uq_delegation_event_sequence_number"),
        UniqueConstraint("delegation_id", "event_hash", name="uq_delegation_event_hash"),
        Index("ix_delegation_events_investigation_id", "investigation_id"),
        Index("ix_delegation_events_delegation_id", "delegation_id"),
        ForeignKeyConstraint(
            ["delegation_id", "assignment_id", "investigation_id", "delegation_hash"],
            [
                "review_delegations.id",
                "review_delegations.assignment_id",
                "review_delegations.investigation_id",
                "review_delegations.delegation_hash",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["attribution_id", "investigation_id"],
            ["record_attributions.id", "record_attributions.investigation_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="ck_delegation_event_sequence_number_positive",
        ),
        CheckConstraint(
            "event_type IN ('issued', 'redeemed', 'revoked', 'expired')",
            name="ck_delegation_event_type",
        ),
        CheckConstraint(
            "event_type <> 'revoked' OR "
            "(reason IS NOT NULL AND length(trim(reason, ' \t\n\r\f\v')) > 0)",
            name="ck_delegation_event_revoke_reason",
        ),
        CheckConstraint(
            "length(event_hash) = 64",
            name="ck_delegation_event_hash_length",
        ),
        CheckConstraint(
            "previous_event_hash IS NULL OR length(previous_event_hash) = 64",
            name="ck_delegation_event_previous_hash_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    delegation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assignment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    investigation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    delegation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_role_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewer_role_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attribution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


Assignment = RoleAssignment
Deliverable = AssignmentDeliverable
ReviewDelegationEvent = DelegationEvent


# Keep metadata-created schemas guarded as well as migration-created PostgreSQL.
for _table in (
    AssignmentEvent.__table__,
    AssignmentDeliverable.__table__,
    DelegationEvent.__table__,
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
    "Assignment",
    "AssignmentDeliverable",
    "AssignmentEvent",
    "DelegationEvent",
    "Deliverable",
    "ReviewDelegation",
    "ReviewDelegationEvent",
    "RoleAssignment",
]
