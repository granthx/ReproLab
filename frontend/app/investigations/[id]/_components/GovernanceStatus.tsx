"use client";

import { useEffect, useState } from "react";
import { governanceApi, type Assignment, type AssignmentEvent, type Deliverable } from "../../../lib/api";

/**
 * Status vocabulary shared by assignments, workflow runs, checkpoints and model calls.
 * Each terminal outcome keeps its own label: blocked, abstained and not-required are
 * never displayed as completed work.
 */
const TONES: Record<string, "done" | "wait" | "stop" | "neutral" | "skip"> = {
  completed: "done",
  succeeded: "done",
  awaiting_human_review: "wait",
  in_progress: "wait",
  running: "wait",
  assigned: "neutral",
  entered: "neutral",
  pending: "neutral",
  blocked: "stop",
  abstained: "stop",
  failed_provider_error: "stop",
  blocked_budget: "stop",
  revoked: "stop",
  disputed: "stop",
  cancelled: "stop",
  failed: "stop",
  timeout: "stop",
  queued: "wait",
  handed_off: "neutral",
  not_required: "skip",
  skipped_deterministic: "skip",
  skipped_conditional_not_needed: "skip",
};

export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = TONES[status] ?? "neutral";
  return <span className={`gov-badge gov-${tone}`} data-status={status}>{label ?? humanize(status)}</span>;
}

export function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

/** Verify that each record's previous hash equals the prior record's hash. */
export function chainStatus<T extends { sequence_number: number }>(
  rows: T[],
  hashOf: (row: T) => string,
  previousOf: (row: T) => string | null,
): { linked: boolean; message: string } {
  const sorted = [...rows].sort((a, b) => a.sequence_number - b.sequence_number);
  let previous: string | null = null;
  for (let index = 0; index < sorted.length; index += 1) {
    const row = sorted[index];
    if (row.sequence_number !== index + 1) return { linked: false, message: `Sequence gap before record ${row.sequence_number}.` };
    if (previousOf(row) !== previous) return { linked: false, message: `Hash chain break at record ${row.sequence_number}.` };
    previous = hashOf(row);
  }
  return { linked: true, message: sorted.length ? `Hash chain linked across ${sorted.length} record(s).` : "No records." };
}

export function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** Read-only drill-down into one persisted assignment: lifecycle events and deliverables. */
export function AssignmentDrilldown({ investigationId, assignment, assignmentId }: { investigationId: string; assignment?: Assignment; assignmentId: string }) {
  const [events, setEvents] = useState<AssignmentEvent[] | null>(null);
  const [deliverables, setDeliverables] = useState<Deliverable[] | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    Promise.all([
      governanceApi.assignmentEvents(investigationId, assignmentId, controller.signal),
      governanceApi.assignmentDeliverables(investigationId, assignmentId, controller.signal),
    ]).then(([eventRows, deliverableRows]) => {
      if (controller.signal.aborted) return;
      setEvents(eventRows); setDeliverables(deliverableRows);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not load assignment records.");
    });
    return () => controller.abort();
  }, [investigationId, assignmentId, revision]);

  const chain = events ? chainStatus(events, (row) => row.event_hash, (row) => row.previous_event_hash) : null;

  return <div className="gov-drilldown">
    {assignment && <>
      <p className="records-meta">Assignment {assignment.id} · {assignment.role_id} · {humanize(assignment.task_kind)} · lifecycle v{assignment.lifecycle_version}</p>
      <p>{assignment.objective}</p>
      <p className="records-hash">Pinned constitution {assignment.constitution_version} · {assignment.constitution_hash}</p>
      {assignment.budget && <p className="records-meta">Model-call ceiling {assignment.budget.max_model_calls} · input tokens {assignment.budget.max_input_tokens} · output tokens {assignment.budget.max_output_tokens}</p>}
      {assignment.input_references.length > 0 && <details><summary>Input references ({assignment.input_references.length})</summary><ul>{assignment.input_references.map((ref) => <li key={`${ref.kind}:${ref.id}`}>{ref.kind} · {ref.id}{ref.content_hash ? <span className="records-hash"> · {ref.content_hash}</span> : null}</li>)}</ul></details>}
    </>}
    {error && <p className="records-error" role="alert">{error} <button type="button" onClick={() => setRevision((value) => value + 1)}>Retry</button></p>}
    {!error && (!events || !deliverables) && <p className="records-note" role="status">Loading assignment records…</p>}
    {events && <>
      <h6>Lifecycle events</h6>
      <p className={chain?.linked ? "records-success" : "records-error"}>{chain?.message}</p>
      <ol className="gov-timeline">{events.map((event) => <li key={event.id}>
        <strong>#{event.sequence_number} {humanize(event.event_type)}</strong>
        {event.from_status || event.to_status ? <span className="records-meta"> · {event.from_status ? humanize(event.from_status) : "∅"} → {event.to_status ? humanize(event.to_status) : "∅"}</span> : null}
        <span className="records-meta"> · {formatTime(event.occurred_at)}</span>
        {event.reason && <p className="records-note">Reason: {event.reason}</p>}
        <p className="records-hash">{event.event_hash}</p>
      </li>)}</ol>
    </>}
    {deliverables && <>
      <h6>Deliverables ({deliverables.length})</h6>
      {!deliverables.length && <p className="records-note">No deliverable was submitted for this assignment.</p>}
      {deliverables.map((item) => <article className="records-card" key={item.id}>
        <p><strong>{humanize(item.schema_name)}</strong> · {humanize(item.kind)} · {item.status}</p>
        {typeof item.content.summary === "string" && <p>{item.content.summary}</p>}
        {typeof item.content.reason === "string" && <p className="records-note">Abstention reason: {humanize(item.content.reason)}</p>}
        {typeof item.content.required_action === "string" && <p className="records-note">Required action: {item.content.required_action}</p>}
        {item.limitations.length > 0 && <ul>{item.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>}
        <p className="records-hash">Content SHA-256: {item.content_hash}</p>
        <details><summary>Canonical deliverable content</summary><pre>{JSON.stringify(item.content, null, 2)}</pre></details>
      </article>)}
    </>}
  </div>;
}
