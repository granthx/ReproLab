"use client";

import { FormEvent, useCallback, useEffect, useId, useRef, useState } from "react";
import {
  workflowApi,
  type AttributionInput,
  type Scientist,
  type WorkflowCheckpoint,
  type WorkflowEvent,
  type WorkflowKind,
  type WorkflowModelCall,
  type WorkflowProviderMode,
  type WorkflowRun,
} from "../../../lib/api";
import AttributionFields, { emptyAttribution } from "./AttributionFields";
import { AssignmentDrilldown, StatusBadge, chainStatus, formatTime, humanize, shortId } from "./GovernanceStatus";

/** Mirrors backend reprolab/workflow/graph.py NODE_SPECS order. Display only; state comes from checkpoints. */
const ANALYSIS_PIPELINE: { node: string; role: string | null; task: string }[] = [
  { node: "atlas_intake", role: "atlas", task: "Intake prerequisites & coordination" },
  { node: "quill_extraction", role: "quill", task: "Source-grounded claim extraction" },
  { node: "sagan_verification", role: "sagan", task: "Evidence lineage & manual-review check" },
  { node: "hypatia_audit", role: "hypatia", task: "Methodology audit" },
  { node: "turing_assessment", role: "turing", task: "Implementation assessment (no execution)" },
  { node: "curie_dataset", role: "curie", task: "Dataset provenance manifest" },
  { node: "human_review_gate", role: null, task: "Explicit human review decision" },
  { node: "popper_review", role: "popper", task: "Skeptical review" },
  { node: "franklin_synthesis", role: "franklin", task: "Qualified report draft" },
];

/** Mirrors backend reprolab/workflow/graph.py REPRODUCTION_NODE_SPECS order. */
const REPRODUCTION_PIPELINE: { node: string; role: string | null; task: string }[] = [
  { node: "atlas_intake", role: "atlas", task: "Intake prerequisites & coordination" },
  { node: "quill_extraction", role: "quill", task: "Source-grounded claim extraction" },
  { node: "sagan_verification", role: "sagan", task: "Evidence lineage & manual-review check" },
  { node: "hypatia_audit", role: "hypatia", task: "Methodology audit" },
  { node: "turing_assessment", role: "turing", task: "Implementation environment assessment" },
  { node: "curie_dataset", role: "curie", task: "Dataset provenance manifest" },
  { node: "human_review_gate", role: null, task: "Explicit human execution approval gate" },
  { node: "faraday_execution", role: "faraday", task: "Hermetic sandbox execution against frozen protocol" },
  { node: "fisher_evaluation", role: "fisher", task: "Statistical scoring & Wilson confidence intervals" },
  { node: "popper_review", role: "popper", task: "Adversarial critique of empirical findings" },
  { node: "shannon_sensitivity", role: "shannon", task: "Sensitivity & sample-size perturbation assessment" },
  { node: "noether_replication", role: "noether", task: "Replication invariance & consistency review" },
  { node: "sagan_provenance", role: "sagan", task: "Cryptographic output artifact & digest audit" },
  { node: "franklin_synthesis", role: "franklin", task: "End-to-end scientific synthesis & evaluation" },
];

const TERMINAL: WorkflowRun["status"][] = ["completed", "cancelled"];

type Props = { investigationId: string; scientists: Scientist[]; enabled: boolean; onChanged: () => void };

type Detail = { checkpoints: WorkflowCheckpoint[]; events: WorkflowEvent[]; modelCalls: WorkflowModelCall[] };

function nodeState(node: string, run: WorkflowRun, checkpoints: WorkflowCheckpoint[]): { status: string; checkpoint?: WorkflowCheckpoint } {
  const rows = checkpoints.filter((row) => row.node_name === node).sort((a, b) => b.sequence_number - a.sequence_number);
  const latest = rows[0];
  if (latest) return { status: latest.stage_status, checkpoint: latest };
  if (run.current_node === node && run.status === "running") return { status: "running" };
  return { status: "pending" };
}

function errorText(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export default function WorkflowSection({ enabled, ...props }: Props) {
  if (!enabled) return <section className="records-panel" aria-label="Analysis workflow"><h3>Analysis workflow</h3><p className="records-note">The analysis-only workflow capability is not reported as available by this API.</p></section>;
  return <WorkflowWorkspace key={props.investigationId} {...props} />;
}

function WorkflowWorkspace({ investigationId, scientists, onChanged }: Omit<Props, "enabled">) {
  const headingId = useId();
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [actionError, setActionError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [listRevision, setListRevision] = useState(0);
  const [detailRevision, setDetailRevision] = useState(0);
  const [workflowKind, setWorkflowKind] = useState<WorkflowKind>("full_reproduction_v1");
  const [providerMode, setProviderMode] = useState<WorkflowProviderMode>("source_grounded");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [attribution, setAttribution] = useState<AttributionInput>(emptyAttribution());
  const [notes, setNotes] = useState("");
  const [inspect, setInspect] = useState("");
  const mutation = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    setListError("");
    workflowApi.runs(investigationId, controller.signal).then((rows) => {
      if (controller.signal.aborted) return;
      setRuns(rows);
      setSelectedId((current) => rows.some((row) => row.id === current) ? current : rows[rows.length - 1]?.id ?? "");
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setListError(errorText(reason, "Could not load workflow runs.")); });
    return () => controller.abort();
  }, [investigationId, listRevision]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    const controller = new AbortController();
    setDetailError("");
    Promise.all([
      workflowApi.run(investigationId, selectedId, controller.signal),
      workflowApi.checkpoints(investigationId, selectedId, controller.signal),
      workflowApi.events(investigationId, selectedId, controller.signal),
      workflowApi.modelCalls(investigationId, selectedId, controller.signal),
    ]).then(([run, checkpoints, events, modelCalls]) => {
      if (controller.signal.aborted) return;
      setRuns((current) => current.map((row) => row.id === run.id ? run : row));
      setDetail({ checkpoints, events, modelCalls });
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setDetailError(errorText(reason, "Could not load workflow run records.")); });
    return () => controller.abort();
  }, [investigationId, selectedId, detailRevision]);

  const run = runs.find((row) => row.id === selectedId);

  const perform = useCallback(async (label: string, action: () => Promise<WorkflowRun>) => {
    if (mutation.current) return;
    if (!attribution.recorder_label.trim()) { setActionError("A human recorder label is required for every workflow action."); return; }
    mutation.current = true; setBusy(true); setActionError(""); setSuccess("");
    try {
      const updated = await action();
      setRuns((current) => current.some((row) => row.id === updated.id) ? current.map((row) => row.id === updated.id ? updated : row) : [...current, updated]);
      setSelectedId(updated.id);
      setSuccess(`${label}: run ${shortId(updated.id)} is now ${humanize(updated.status)} at ${humanize(updated.current_node)}.`);
      setNotes("");
      setDetailRevision((value) => value + 1);
      onChanged();
    } catch (reason) {
      setActionError(errorText(reason, `${label} failed.`));
      // Reload persisted state: a stale lifecycle version means the server changed.
      setDetailRevision((value) => value + 1);
    } finally { mutation.current = false; setBusy(false); }
  }, [attribution, onChanged]);

  function start(event: FormEvent) {
    event.preventDefault();
    void perform("Workflow started", () => workflowApi.start(investigationId, {
      workflow_kind: workflowKind,
      provider_mode: providerMode,
      idempotency_key: idempotencyKey.trim() || null,
      attribution,
    }));
  }

  function requireNotes(kind: string): string | null {
    const value = notes.trim();
    if (!value) { setActionError(`${kind} requires notes recorded by the human operator.`); return null; }
    return value;
  }

  const eventChain = detail ? chainStatus(detail.events, (row) => row.event_hash, (row) => row.previous_event_hash) : null;
  const checkpointChain = detail ? chainStatus(detail.checkpoints, (row) => row.checkpoint_hash, (row) => row.previous_checkpoint_hash) : null;

  return <section className="records-panel" aria-labelledby={headingId}>
    <div className="records-row"><h3 id={headingId}>Analysis-only workflow</h3><div className="records-actions"><button type="button" onClick={() => { setListRevision((value) => value + 1); setDetailRevision((value) => value + 1); }}>Refresh workflow runs</button></div></div>
    <p className="records-note">Every pipeline node produces a recorded deliverable, review checkpoint, or block. The analysis pipeline evaluates methodologies and code viability; it pauses for an explicit human decision before skeptical review and scientific synthesis.</p>
    {success && <p className="records-success" role="status">{success}</p>}
    {actionError && <p className="records-error" role="alert">{actionError}</p>}
    {listError && <p className="records-error" role="alert">Workflow run list failed to load: {listError}</p>}

    <AttributionFields value={attribution} onChange={setAttribution} scientists={scientists} disabled={busy} />

    <form className="records-card" onSubmit={start}>
      <h4>Start a workflow run</h4>
      <label>Workflow kind<select value={workflowKind} onChange={(event) => setWorkflowKind(event.target.value as WorkflowKind)}>
        <option value="full_reproduction_v1">Full Reproduction Pipeline (14 nodes: execution + evaluation)</option>
        <option value="analysis_only_v1">Analysis-Only Pipeline (9 nodes: no execution)</option>
      </select></label>
      <label>Provider mode<select value={providerMode} onChange={(event) => setProviderMode(event.target.value as WorkflowProviderMode)}>
        <option value="source_grounded">Source-grounded (no model calls)</option>
        <option value="gemini">Gemini for conditional roles (server API key required)</option>
      </select></label>
      <p className="records-note">{providerMode === "gemini"
        ? "Atlas, Curie and Franklin stay deterministic. A missing key, provider failure or exhausted call budget blocks the run; no output is substituted."
        : "Conditional roles record that no model call was needed. Summaries are derived only from persisted claims, evidence and protocols."}</p>
      <label>Idempotency key (optional)<input value={idempotencyKey} maxLength={128} onChange={(event) => setIdempotencyKey(event.target.value)} placeholder="Replays the same run instead of starting another" /></label>
      <button type="submit" disabled={busy}>{busy ? "Working…" : "Start analysis workflow"}</button>
    </form>

    {!listError && !runs.length && <p className="records-note">No workflow runs recorded for this investigation.</p>}
    {runs.length > 0 && <label>Workflow run<select value={selectedId} onChange={(event) => { setSelectedId(event.target.value); setInspect(""); setSuccess(""); setActionError(""); }}>
      {[...runs].reverse().map((row) => <option key={row.id} value={row.id}>{formatTime(row.created_at)} · {humanize(row.status)} · {row.provider_mode} · {shortId(row.id)}</option>)}
    </select></label>}

    {run && <article className="gov-run" aria-label="Selected workflow run">
      <div className="gov-row">
        <div><strong>Run {run.id}</strong><p className="records-meta">{run.workflow_kind} · {run.provider_mode} · lifecycle v{run.lifecycle_version} · current node {humanize(run.current_node)}{run.idempotency_key ? ` · key ${run.idempotency_key}` : ""}</p></div>
        <StatusBadge status={run.status} />
      </div>
      {run.blocked_reason && <p className="records-error">Blocked: {run.blocked_reason}</p>}
      {run.abstained_reason && <p className="records-error">Abstained: {run.abstained_reason}</p>}
      {run.cancelled_reason && <p className="records-note">Cancelled: {run.cancelled_reason}</p>}
      {detailError && <p className="records-error" role="alert">Run records failed to load: {detailError}</p>}

      {detail && <>
        <h5>Pipeline (from persisted checkpoints)</h5>
        <ol className="gov-pipeline">{(run.workflow_kind === "full_reproduction_v1" ? REPRODUCTION_PIPELINE : ANALYSIS_PIPELINE).map((step) => {
          const state = nodeState(step.node, run, detail.checkpoints);
          const assignmentId = state.checkpoint?.assignment_id;
          return <li key={step.node} className={`gov-step gov-step-${state.status}`}>
            <div className="gov-row"><div><strong>{humanize(step.node)}</strong><p className="records-meta">{step.role ?? "human"} · {step.task}</p></div><StatusBadge status={state.status} /></div>
            {state.checkpoint && <p className="records-meta">Checkpoint #{state.checkpoint.sequence_number}{assignmentId ? ` · assignment ${shortId(assignmentId)}` : ""}{state.checkpoint.deliverable_id ? ` · deliverable ${shortId(state.checkpoint.deliverable_id)}` : ""}</p>}
            {assignmentId && <button type="button" aria-expanded={inspect === assignmentId} onClick={() => setInspect(inspect === assignmentId ? "" : assignmentId)}>{inspect === assignmentId ? "Hide provenance" : "Inspect assignment"}</button>}
            {assignmentId && inspect === assignmentId && <AssignmentDrilldown investigationId={investigationId} assignmentId={assignmentId} />}
          </li>;
        })}</ol>

        {run.status === "awaiting_human_review" && <div className="records-card gov-gate">
          <h5>Human review gate</h5>
          <p className="records-note">Review the completed deliverables above. Approving runs Popper and Franklin; rejecting blocks the run with your notes. Neither decision is evidence that an experiment occurred.</p>
          <label>Decision notes (required)<textarea value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} /></label>
          <div className="records-actions">
            <button type="button" disabled={busy} onClick={() => { const value = requireNotes("A gate decision"); if (value) void perform("Gate approved", () => workflowApi.decideGate(investigationId, run.id, { decision: "approve", expected_lifecycle_version: run.lifecycle_version, notes: value, attribution })); }}>Approve and continue</button>
            <button type="button" disabled={busy} onClick={() => { const value = requireNotes("A gate decision"); if (value) void perform("Gate rejected", () => workflowApi.decideGate(investigationId, run.id, { decision: "reject", expected_lifecycle_version: run.lifecycle_version, notes: value, attribution })); }}>Reject and block</button>
          </div>
        </div>}

        {(run.status === "blocked" || run.status === "abstained") && <div className="records-card">
          <h5>Resume after resolving the recorded reason</h5>
          <p className="records-note">Completed nodes are reused from their checkpoints; only the blocked node and later nodes run again.</p>
          <label>Resume notes (optional)<textarea value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} /></label>
          <button type="button" disabled={busy} onClick={() => void perform("Workflow resumed", () => workflowApi.resume(investigationId, run.id, { expected_lifecycle_version: run.lifecycle_version, notes: notes.trim() || null, attribution }))}>Resume workflow</button>
        </div>}

        {!TERMINAL.includes(run.status) && <details className="records-card">
          <summary>Cancel this run</summary>
          <label>Cancellation reason (required)<textarea value={notes} maxLength={2000} onChange={(event) => setNotes(event.target.value)} /></label>
          <button type="button" disabled={busy} onClick={() => { const value = requireNotes("Cancellation"); if (value) void perform("Workflow cancelled", () => workflowApi.cancel(investigationId, run.id, { expected_lifecycle_version: run.lifecycle_version, reason: value, attribution })); }}>Cancel workflow run</button>
        </details>}

        <h5>Model-call audit ({detail.modelCalls.length})</h5>
        {!detail.modelCalls.length ? <p className="records-note">No model-call records.</p> : <div className="gov-table-wrap"><table className="gov-table">
          <thead><tr><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Provider / model</th><th scope="col">Call</th><th scope="col">Tokens in/out</th><th scope="col">Detail</th></tr></thead>
          <tbody>{detail.modelCalls.map((call) => <tr key={call.id}>
            <td>{call.role_id}<br /><span className="records-meta">{call.routing_category}</span></td>
            <td><StatusBadge status={call.status} /></td>
            <td>{call.provider}<br /><span className="records-meta">{call.model_name}</span></td>
            <td>{call.call_index} / ceiling {call.max_calls_ceiling}</td>
            <td>{call.input_tokens} / {call.output_tokens}</td>
            <td>{call.error_detail ?? <span className="records-hash">prompt {call.prompt_sha256.slice(0, 16)}…{call.response_sha256 ? ` · response ${call.response_sha256.slice(0, 16)}…` : ""}</span>}</td>
          </tr>)}</tbody>
        </table></div>}

        <h5>Workflow events ({detail.events.length})</h5>
        <p className={eventChain?.linked ? "records-success" : "records-error"}>{eventChain?.message}{eventChain?.linked && run.latest_event_hash && detail.events.length && detail.events[detail.events.length - 1].event_hash !== run.latest_event_hash ? " Latest run hash does not match the final event." : ""}</p>
        <ol className="gov-timeline">{detail.events.map((event) => <li key={event.id}>
          <strong>#{event.sequence_number} {humanize(event.event_type)}</strong>
          <span className="records-meta"> · {humanize(event.node_name)}{event.role_id ? ` · ${event.role_id}` : ""} · {formatTime(event.occurred_at)}</span>
          {event.reason && <p className="records-note">{event.reason}</p>}
          <p className="records-hash">{event.event_hash}</p>
        </li>)}</ol>

        <details><summary>Checkpoints ({detail.checkpoints.length}) · {checkpointChain?.message}</summary>
          {detail.checkpoints.map((checkpoint) => <article className="records-card" key={checkpoint.id}>
            <p><strong>#{checkpoint.sequence_number} {humanize(checkpoint.node_name)}</strong> <StatusBadge status={checkpoint.stage_status} /></p>
            <p className="records-hash">Checkpoint {checkpoint.checkpoint_hash}<br />State {checkpoint.state_hash}</p>
            <details><summary>Persisted graph state</summary><pre>{JSON.stringify(checkpoint.state_json, null, 2)}</pre></details>
          </article>)}
        </details>
      </>}
    </article>}
  </section>;
}
