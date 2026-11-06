"""add Stage 8 full reproduction pipeline check constraints

Revision ID: 0011_reproduction_pipeline
Revises: 0010_release_evaluation
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_reproduction_pipeline"
down_revision: Union[str, None] = "0010_release_evaluation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ALL_WORKFLOW_NODES_SQL = (
    "'atlas_intake', 'quill_extraction', 'sagan_verification', 'hypatia_audit', "
    "'turing_assessment', 'curie_dataset', 'human_review_gate', 'faraday_execution', "
    "'fisher_evaluation', 'popper_review', 'shannon_sensitivity', 'noether_replication', "
    "'sagan_provenance', 'franklin_synthesis', 'terminal'"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_workflow_run_kind", "workflow_runs", type_="check")
        op.create_check_constraint(
            "ck_workflow_run_kind",
            "workflow_runs",
            "workflow_kind IN ('analysis_only_v1', 'full_reproduction_v1')",
        )
        op.drop_constraint("ck_workflow_run_current_node", "workflow_runs", type_="check")
        op.create_check_constraint(
            "ck_workflow_run_current_node",
            "workflow_runs",
            f"current_node IN ({ALL_WORKFLOW_NODES_SQL})",
        )
        op.drop_constraint("ck_workflow_checkpoint_node_name", "workflow_checkpoints", type_="check")
        op.create_check_constraint(
            "ck_workflow_checkpoint_node_name",
            "workflow_checkpoints",
            f"node_name IN ({ALL_WORKFLOW_NODES_SQL})",
        )
        op.drop_constraint("ck_workflow_event_node_name", "workflow_events", type_="check")
        op.create_check_constraint(
            "ck_workflow_event_node_name",
            "workflow_events",
            f"node_name IN ({ALL_WORKFLOW_NODES_SQL})",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_workflow_run_kind", "workflow_runs", type_="check")
        op.create_check_constraint(
            "ck_workflow_run_kind",
            "workflow_runs",
            "workflow_kind = 'analysis_only_v1'",
        )

