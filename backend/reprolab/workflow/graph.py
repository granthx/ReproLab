"""LangGraph StateGraph definition for the Stage 4 analysis-only workflow.

Pipeline sequence:
  atlas_intake
    -> quill_extraction
    -> sagan_verification
    -> hypatia_audit
    -> turing_assessment
    -> curie_dataset
    -> human_review_gate  (pauses in `awaiting_human_review` until approved)
    -> popper_review
    -> franklin_synthesis
    -> END

Isolated experiment execution (`faraday`), production statistical scoring
(`fisher`), sensitivity runs (`shannon`), and independent replication execution
(`noether`) are explicitly excluded from the Stage 4 graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph


@dataclass(frozen=True, slots=True)
class AnalysisNodeSpec:
    node_name: str
    role_id: str | None
    task_kind: str | None
    deliverable_kind: str | None
    deliverable_content_kind: str | None
    objective: str
    next_node: str


NODE_SPECS: dict[str, AnalysisNodeSpec] = {
    "atlas_intake": AnalysisNodeSpec(
        node_name="atlas_intake",
        role_id="atlas",
        task_kind="coordination_decision",
        deliverable_kind="analysis",
        deliverable_content_kind="coordination_decision",
        objective="Verify investigation intake prerequisites and schedule source-grounded analysis.",
        next_node="quill_extraction",
    ),
    "quill_extraction": AnalysisNodeSpec(
        node_name="quill_extraction",
        role_id="quill",
        task_kind="claim_extraction",
        deliverable_kind="analysis",
        deliverable_content_kind="claim_extraction",
        objective="Extract source-grounded claims, reported metrics, and locators without filling gaps.",
        next_node="sagan_verification",
    ),
    "sagan_verification": AnalysisNodeSpec(
        node_name="sagan_verification",
        role_id="sagan",
        task_kind="evidence_verification",
        deliverable_kind="evidence_verification",
        deliverable_content_kind="evidence_verification",
        objective="Verify evidence lineage, locators, quotations, and manual review status.",
        next_node="hypatia_audit",
    ),
    "hypatia_audit": AnalysisNodeSpec(
        node_name="hypatia_audit",
        role_id="hypatia",
        task_kind="methodology_audit",
        deliverable_kind="methodology_assessment",
        deliverable_content_kind="methodology_audit",
        objective="Audit documented methodology, splits, controls, and missing information.",
        next_node="turing_assessment",
    ),
    "turing_assessment": AnalysisNodeSpec(
        node_name="turing_assessment",
        role_id="turing",
        task_kind="implementation_assessment",
        deliverable_kind="implementation_assessment",
        deliverable_content_kind="implementation_assessment",
        objective="Assess implementation specifications and protocol deviations without host execution.",
        next_node="curie_dataset",
    ),
    "curie_dataset": AnalysisNodeSpec(
        node_name="curie_dataset",
        role_id="curie",
        task_kind="dataset_manifest",
        deliverable_kind="dataset_manifest",
        deliverable_content_kind="dataset_manifest",
        objective="Establish dataset provenance, hashes, and limitations deterministically.",
        next_node="human_review_gate",
    ),
    "human_review_gate": AnalysisNodeSpec(
        node_name="human_review_gate",
        role_id=None,
        task_kind=None,
        deliverable_kind=None,
        deliverable_content_kind=None,
        objective="Require explicit human review gate approval before adversarial review and synthesis.",
        next_node="popper_review",
    ),
    "popper_review": AnalysisNodeSpec(
        node_name="popper_review",
        role_id="popper",
        task_kind="skeptical_review",
        deliverable_kind="review",
        deliverable_content_kind="skeptical_review",
        objective="Challenge supportive and adverse interpretations and preserve unresolved issues.",
        next_node="franklin_synthesis",
    ),
    "franklin_synthesis": AnalysisNodeSpec(
        node_name="franklin_synthesis",
        role_id="franklin",
        task_kind="report_draft",
        deliverable_kind="report_draft",
        deliverable_content_kind="report_draft",
        objective="Synthesize validated analysis findings and limitations into a qualified record.",
        next_node="terminal",
    ),
}

ORDERED_NODES: tuple[str, ...] = tuple(NODE_SPECS.keys())


REPRODUCTION_NODE_SPECS: dict[str, AnalysisNodeSpec] = {
    "atlas_intake": AnalysisNodeSpec(
        node_name="atlas_intake",
        role_id="atlas",
        task_kind="coordination_decision",
        deliverable_kind="analysis",
        deliverable_content_kind="coordination_decision",
        objective="Verify investigation intake prerequisites and schedule source-grounded analysis.",
        next_node="quill_extraction",
    ),
    "quill_extraction": AnalysisNodeSpec(
        node_name="quill_extraction",
        role_id="quill",
        task_kind="claim_extraction",
        deliverable_kind="analysis",
        deliverable_content_kind="claim_extraction",
        objective="Extract source-grounded claims, reported metrics, and locators without filling gaps.",
        next_node="sagan_verification",
    ),
    "sagan_verification": AnalysisNodeSpec(
        node_name="sagan_verification",
        role_id="sagan",
        task_kind="evidence_verification",
        deliverable_kind="evidence_verification",
        deliverable_content_kind="evidence_verification",
        objective="Verify evidence lineage, locators, quotations, and manual review status.",
        next_node="hypatia_audit",
    ),
    "hypatia_audit": AnalysisNodeSpec(
        node_name="hypatia_audit",
        role_id="hypatia",
        task_kind="methodology_audit",
        deliverable_kind="methodology_assessment",
        deliverable_content_kind="methodology_audit",
        objective="Audit documented methodology, splits, controls, and missing information.",
        next_node="turing_assessment",
    ),
    "turing_assessment": AnalysisNodeSpec(
        node_name="turing_assessment",
        role_id="turing",
        task_kind="implementation_assessment",
        deliverable_kind="implementation_assessment",
        deliverable_content_kind="implementation_assessment",
        objective="Assess implementation specifications and protocol deviations without host execution.",
        next_node="curie_dataset",
    ),
    "curie_dataset": AnalysisNodeSpec(
        node_name="curie_dataset",
        role_id="curie",
        task_kind="dataset_manifest",
        deliverable_kind="dataset_manifest",
        deliverable_content_kind="dataset_manifest",
        objective="Establish dataset provenance, hashes, and limitations deterministically.",
        next_node="human_review_gate",
    ),
    "human_review_gate": AnalysisNodeSpec(
        node_name="human_review_gate",
        role_id=None,
        task_kind=None,
        deliverable_kind=None,
        deliverable_content_kind=None,
        objective="Require explicit human review gate approval before experiment execution.",
        next_node="faraday_execution",
    ),
    "faraday_execution": AnalysisNodeSpec(
        node_name="faraday_execution",
        role_id="faraday",
        task_kind="execution",
        deliverable_kind="implementation_assessment",
        deliverable_content_kind="execution_summary",
        objective="Execute the approved frozen protocol inside the isolated, hermetic subprocess sandbox.",
        next_node="fisher_evaluation",
    ),
    "fisher_evaluation": AnalysisNodeSpec(
        node_name="fisher_evaluation",
        role_id="fisher",
        task_kind="statistical_assessment",
        deliverable_kind="analysis",
        deliverable_content_kind="statistical_evaluation",
        objective="Evaluate statistical power, Wilson score intervals, and significance from trusted production measurements.",
        next_node="popper_review",
    ),
    "popper_review": AnalysisNodeSpec(
        node_name="popper_review",
        role_id="popper",
        task_kind="skeptical_review",
        deliverable_kind="review",
        deliverable_content_kind="skeptical_review",
        objective="Adversarially challenge empirical results, baseline discrepancies, and methodological threats.",
        next_node="shannon_sensitivity",
    ),
    "shannon_sensitivity": AnalysisNodeSpec(
        node_name="shannon_sensitivity",
        role_id="shannon",
        task_kind="sensitivity_assessment",
        deliverable_kind="analysis",
        deliverable_content_kind="sensitivity_assessment",
        objective="Assess perturbation boundaries, metric sensitivity, and parameter robustness.",
        next_node="noether_replication",
    ),
    "noether_replication": AnalysisNodeSpec(
        node_name="noether_replication",
        role_id="noether",
        task_kind="independent_review",
        deliverable_kind="review",
        deliverable_content_kind="independent_replication",
        objective="Evaluate replication validity, shared environment dependencies, and independent reproducibility.",
        next_node="sagan_provenance",
    ),
    "sagan_provenance": AnalysisNodeSpec(
        node_name="sagan_provenance",
        role_id="sagan",
        task_kind="evidence_verification",
        deliverable_kind="evidence_verification",
        deliverable_content_kind="provenance_audit",
        objective="Validate end-to-end cryptographic lineage, artifact SHA-256 hashes, and measurement audit trail.",
        next_node="franklin_synthesis",
    ),
    "franklin_synthesis": AnalysisNodeSpec(
        node_name="franklin_synthesis",
        role_id="franklin",
        task_kind="report_draft",
        deliverable_kind="report_draft",
        deliverable_content_kind="report_draft",
        objective="Synthesize validated findings, execution measurements, and statistical reviews into a qualified final reproduction report.",
        next_node="terminal",
    ),
}

ORDERED_REPRODUCTION_NODES: tuple[str, ...] = tuple(REPRODUCTION_NODE_SPECS.keys())


class AnalysisWorkflowState(TypedDict, total=False):
    workflow_run_id: str
    investigation_id: str
    workflow_kind: str
    provider_mode: str
    current_node: str
    status: str
    gate_approved: bool
    completed_nodes: list[str]
    node_assignments: dict[str, str]
    node_deliverables: dict[str, str]
    claim_ids: list[str]
    evidence_ids: list[str]
    accepted_evidence_ids: list[str]
    protocol_ids: list[str]
    finding_version_ids: list[str]
    report_ids: list[str]
    job_id: str | None
    attempt_id: str | None
    measurement_ids: list[str]
    evaluation_id: str | None
    blocked_reason: str | None
    abstained_reason: str | None


StepHandler = Callable[[str, AnalysisWorkflowState], Awaitable[dict[str, Any]]]


def _route_from_entry(state: AnalysisWorkflowState) -> str:
    target = state.get("current_node", "atlas_intake")
    if target not in NODE_SPECS:
        return END
    return target


def _make_router(next_node: str) -> Callable[[AnalysisWorkflowState], str]:
    def router(state: AnalysisWorkflowState) -> str:
        status = state.get("status", "running")
        if status != "running":
            return END
        if next_node == "terminal":
            return END
        return next_node

    return router


def build_analysis_workflow_graph(step_handler: StepHandler):
    """Compile the Stage 4 LangGraph StateGraph around the governed async step handler."""

    graph = StateGraph(AnalysisWorkflowState)
    for node_name in ORDERED_NODES:
        def _bind_node(bound_name: str):
            async def _node(state: AnalysisWorkflowState) -> dict[str, Any]:
                return await step_handler(bound_name, state)
            return _node

        graph.add_node(node_name, _bind_node(node_name))

    branch_map = {name: name for name in ORDERED_NODES}
    branch_map[END] = END
    graph.add_conditional_edges(START, _route_from_entry, branch_map)

    for node_name, spec in NODE_SPECS.items():
        next_target = END if spec.next_node == "terminal" else spec.next_node
        graph.add_conditional_edges(
            node_name,
            _make_router(spec.next_node),
            {next_target: next_target, END: END},
        )

    return graph.compile()


def _route_from_reproduction_entry(state: AnalysisWorkflowState) -> str:
    target = state.get("current_node", "atlas_intake")
    if target not in REPRODUCTION_NODE_SPECS:
        return END
    return target


def build_reproduction_workflow_graph(step_handler: StepHandler):
    """Compile the Stage 8 Full Reproduction LangGraph StateGraph around the governed async step handler."""

    graph = StateGraph(AnalysisWorkflowState)
    for node_name in ORDERED_REPRODUCTION_NODES:
        def _bind_node(bound_name: str):
            async def _node(state: AnalysisWorkflowState) -> dict[str, Any]:
                return await step_handler(bound_name, state)
            return _node

        graph.add_node(node_name, _bind_node(node_name))

    branch_map = {name: name for name in ORDERED_REPRODUCTION_NODES}
    branch_map[END] = END
    graph.add_conditional_edges(START, _route_from_reproduction_entry, branch_map)

    for node_name, spec in REPRODUCTION_NODE_SPECS.items():
        next_target = END if spec.next_node == "terminal" else spec.next_node
        graph.add_conditional_edges(
            node_name,
            _make_router(spec.next_node),
            {next_target: next_target, END: END},
        )

    return graph.compile()
