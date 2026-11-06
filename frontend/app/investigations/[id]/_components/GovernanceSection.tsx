"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { governanceApi, type Assignment, type ReviewDelegation } from "../../../lib/api";
import { AssignmentDrilldown, StatusBadge, formatTime, humanize, shortId } from "./GovernanceStatus";

type Props = { investigationId: string; revision: number };

const STATUS_ORDER = ["assigned", "in_progress", "completed", "blocked", "abstained", "not_required", "handed_off", "disputed", "revoked"];

function outcomeReason(assignment: Assignment): string | null {
  if (assignment.status === "blocked") return assignment.blocked_reason;
  if (assignment.status === "not_required") return assignment.not_required_reason;
  if (assignment.status === "revoked") return assignment.revoked_reason;
  return null;
}

export default function GovernanceSection(props: Props) {
  return <GovernanceWorkspace key={props.investigationId} {...props} />;
}

function GovernanceWorkspace({ investigationId, revision }: Props) {
  const headingId = useId();
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [delegations, setDelegations] = useState<ReviewDelegation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [delegationError, setDelegationError] = useState("");
  const [filter, setFilter] = useState("all");
  const [openId, setOpenId] = useState("");
  const [localRevision, setLocalRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(""); setDelegationError("");
    governanceApi.assignments(investigationId, controller.signal).then((rows) => {
      if (!controller.signal.aborted) setAssignments(rows);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not load assignments.");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    governanceApi.reviewDelegations(investigationId, controller.signal).then((rows) => {
      if (!controller.signal.aborted) setDelegations(rows);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setDelegationError(reason instanceof Error ? reason.message : "Could not load review delegations.");
    });
    return () => controller.abort();
  }, [investigationId, revision, localRevision]);

  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    for (const row of assignments) result[row.status] = (result[row.status] ?? 0) + 1;
    return result;
  }, [assignments]);
  const visible = filter === "all" ? assignments : assignments.filter((row) => row.status === filter);

  return <section className="records-panel" aria-labelledby={headingId}>
    <div className="records-row"><h3 id={headingId}>Role Assignments & Delegations</h3><div className="records-actions"><button type="button" disabled={loading} onClick={() => setLocalRevision((value) => value + 1)}>{loading ? "Refreshing assignments…" : "Refresh assignments"}</button></div></div>
    <p className="records-note">Persisted research pipeline role assignments and deliverables. Each state tracks reviewer sign-offs and peer delegation tokens.</p>
    {error && <p className="records-error" role="alert">Assignment list failed to load: {error}</p>}
    {!loading && !error && !assignments.length && <p className="records-note">No assignments recorded for this investigation. Starting an analysis workflow run, or recording a manual assignment through the API, creates them.</p>}
    {assignments.length > 0 && <>
      <div className="gov-summary" role="list" aria-label="Assignment outcome counts">
        {STATUS_ORDER.filter((status) => counts[status]).map((status) => <span role="listitem" key={status}><StatusBadge status={status} /> {counts[status]}</span>)}
      </div>
      <label>Filter by recorded status<select value={filter} onChange={(event) => setFilter(event.target.value)}>
        <option value="all">All statuses ({assignments.length})</option>
        {STATUS_ORDER.filter((status) => counts[status]).map((status) => <option key={status} value={status}>{humanize(status)} ({counts[status]})</option>)}
      </select></label>
      <ul className="gov-list">{visible.map((assignment) => {
        const reason = outcomeReason(assignment);
        const open = openId === assignment.id;
        return <li key={assignment.id} className="records-card">
          <div className="gov-row">
            <div><strong>{assignment.role_id}</strong> · {humanize(assignment.task_kind)}<p className="records-meta">Assignment {shortId(assignment.id)} · created {formatTime(assignment.created_at)}{assignment.requested_by ? ` · requested by ${assignment.requested_by}` : ""}</p></div>
            <StatusBadge status={assignment.status} />
          </div>
          {reason && <p className="records-note">Recorded reason: {reason}</p>}
          <button type="button" aria-expanded={open} onClick={() => setOpenId(open ? "" : assignment.id)}>{open ? "Hide provenance" : "Inspect events & deliverables"}</button>
          {open && <AssignmentDrilldown investigationId={investigationId} assignment={assignment} assignmentId={assignment.id} />}
        </li>;
      })}</ul>
    </>}
    <h4>Review delegations</h4>
    <p className="records-note">Exact-hash, bounded review grants. Bearer tokens are shown only once at issue time and are never displayed here.</p>
    {delegationError && <p className="records-error" role="alert">Review delegations failed to load: {delegationError}</p>}
    {!delegationError && !delegations.length && <p className="records-note">No review delegations issued.</p>}
    {delegations.map((delegation) => <article className="records-card" key={delegation.id}>
      <div className="gov-row"><div><strong>{delegation.reviewer_role_id}</strong> reviews finding version {shortId(delegation.target.finding_version_id)}<p className="records-meta">Issued {formatTime(delegation.issued_at)} · expires {formatTime(delegation.expires_at)} · uses {delegation.use_count}/{delegation.max_uses}</p></div><StatusBadge status={delegation.status === "redeemed" ? "completed" : delegation.status === "issued" ? "assigned" : delegation.status === "expired" ? "not_required" : "revoked"} label={delegation.status} /></div>
      <p className="records-hash">Target content hash: {delegation.target.content_hash}</p>
    </article>)}
  </section>;
}

