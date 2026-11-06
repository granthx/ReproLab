"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { recordsApi, type AttributionInput, type Report, type ReportEvent, type ReportVersion, type Scientist } from "../../../lib/api";
import AttributionFields, { AttributionDisplay, emptyAttribution } from "./AttributionFields";

export type ReportLifecycleProps = {
  investigationId: string;
  report: Report;
  version: ReportVersion;
  scientists: Scientist[];
  reviewRevision?: number;
  onEvent: (event: ReportEvent) => void;
  onRefresh?: (report: Report) => void;
};

type Eligibility = { versionId: string; hash: string; reviewId?: string; reviewedAt?: string; problems: string[] };
type Review = Awaited<ReturnType<typeof recordsApi.findingReviews>>[number];
const message = (reason: unknown) => reason instanceof Error ? reason.message : "The request failed.";
const latestEvent = (events: ReportEvent[]) => events.reduce<ReportEvent | undefined>((latest, event) => !latest || event.sequence_number > latest.sequence_number ? event : latest, undefined);

function newestReview(reviews: Review[]) {
  return [...reviews].sort((a, b) => {
    const time = Date.parse(b.reviewed_at) - Date.parse(a.reviewed_at);
    if (time) return time;
    // Preserve backend microsecond ordering rather than rounding to JS milliseconds.
    const fractionA = (a.reviewed_at.match(/\.(\d+)/)?.[1] ?? "").padEnd(9, "0");
    const fractionB = (b.reviewed_at.match(/\.(\d+)/)?.[1] ?? "").padEnd(9, "0");
    if (fractionA !== fractionB) return fractionA < fractionB ? 1 : -1;
    return a.id === b.id ? 0 : a.id < b.id ? 1 : -1;
  })[0];
}

async function checkEligibility(investigationId: string, reportId: string, viewed: ReportVersion, signal?: AbortSignal): Promise<Eligibility[]> {
  const saved = await recordsApi.reportVersion(investigationId, reportId, viewed.id, signal);
  if (saved.content_hash !== viewed.content_hash) throw new Error("The saved report hash differs from the viewed version. Refresh the report before publishing.");
  const context = saved.canonical_content_json.source_context;
  const included = saved.canonical_content_json.finding_links.filter((link) => link.disposition === "included");
  return Promise.all(included.map(async (link): Promise<Eligibility> => {
    const result: Eligibility = { versionId: link.finding_version_id, hash: link.finding_content_hash, problems: [] };
    const pinned = context?.findings.find((item) => item.finding_version_id === link.finding_version_id && item.finding_content_hash === link.finding_content_hash);
    if (!pinned) return { ...result, problems: ["Canonical finding context is missing or has a different hash."] };
    const [finding, reviews] = await Promise.all([
      recordsApi.findingVersion(investigationId, pinned.finding_id, link.finding_version_id, signal),
      recordsApi.findingReviews(investigationId, pinned.finding_id, link.finding_version_id, signal),
    ]);
    if (finding.content_hash !== link.finding_content_hash) result.problems.push("The pinned finding hash does not match the saved finding version.");
    const review = newestReview(reviews.filter((item) => item.finding_version_id === link.finding_version_id && item.target_content_hash === link.finding_content_hash));
    if (!review) result.problems.push("No exact-hash manual review is recorded.");
    else {
      result.reviewId = review.id; result.reviewedAt = review.reviewed_at;
      if (review.review_method !== "manual_review" || review.outcome !== "accepted_for_inclusion") result.problems.push(`Latest exact-hash review outcome: ${review.outcome}.`);
      if (!review.citations_checked) result.problems.push("Citations have not been checked.");
      if (!review.limitations_checked) result.problems.push("Limitations have not been checked.");
      if (!review.execution_wording_checked) result.problems.push("Execution wording has not been checked.");
      if (finding.finding.assertions.some((assertion) => assertion.numbers.length > 0) && review.numeric_transcription_checked !== true) result.problems.push("Numeric transcription has not been checked.");
    }
    return result;
  }));
}

export default function ReportLifecycle({ investigationId, report, version, scientists, reviewRevision = 0, onEvent, onRefresh }: ReportLifecycleProps) {
  const [events, setEvents] = useState<ReportEvent[]>(report.events);
  const [eventRevision, setEventRevision] = useState(0);
  const [eventsPending, setEventsPending] = useState(false);
  const [eventsError, setEventsError] = useState("");
  const [eligibility, setEligibility] = useState<Eligibility[] | null>(null);
  const [eligibilityRevision, setEligibilityRevision] = useState(0);
  const [eligibilityPending, setEligibilityPending] = useState(false);
  const [eligibilityError, setEligibilityError] = useState("");
  const [attribution, setAttribution] = useState<AttributionInput>(emptyAttribution);
  const [notes, setNotes] = useState("");
  const [actionPending, setActionPending] = useState<"publish" | "withdraw" | "">("");
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");
  const actionLock = useRef(false);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    return () => controller.abort();
  }, []);

  const combinedEvents = Array.from(new Map([...events, ...report.events].map((event) => [event.id, event])).values()).sort((a, b) => a.sequence_number - b.sequence_number);
  const currentEvent = latestEvent(combinedEvents);
  const status = report.status === "withdrawn" || currentEvent?.event_type === "withdrawn" ? "withdrawn" : report.status === "published" || currentEvent?.event_type === "published" ? "published" : "draft";

  useEffect(() => {
    const controller = new AbortController();
    setEventsPending(true); setEventsError("");
    Promise.all([
      recordsApi.report(investigationId, report.id, controller.signal),
      recordsApi.reportEvents(investigationId, report.id, controller.signal),
    ]).then(([fresh, rows]) => {
      if (!controller.signal.aborted) { setEvents(rows); onRefresh?.({ ...fresh, events: rows }); }
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setEventsError(message(reason)); })
      .finally(() => { if (!controller.signal.aborted) setEventsPending(false); });
    return () => controller.abort();
  }, [investigationId, report.id, eventRevision]);

  useEffect(() => {
    if (status !== "draft") { setEligibilityPending(false); return; }
    const controller = new AbortController();
    setEligibilityPending(true); setEligibilityError(""); setEligibility(null);
    checkEligibility(investigationId, report.id, version, controller.signal).then((rows) => {
      if (!controller.signal.aborted) setEligibility(rows);
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setEligibilityError(message(reason)); })
      .finally(() => { if (!controller.signal.aborted) setEligibilityPending(false); });
    return () => controller.abort();
    // Immutable version identity/hash drive this read; object refreshes do not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId, report.id, version.id, version.content_hash, status, reviewRevision, eligibilityRevision]);

  const canPublish = status === "draft" && eligibility !== null && eligibility.length > 0 && eligibility.every((item) => item.problems.length === 0) && !eligibilityPending && !eligibilityError;
  const publishedEvent = status === "published" && currentEvent?.event_type === "published" ? currentEvent : undefined;
  const viewedPublication = publishedEvent?.report_version_id === version.id && publishedEvent.target_content_hash === version.content_hash ? "Currently published version"
    : combinedEvents.some((event) => event.event_type === "withdrawn" && event.report_version_id === version.id && event.target_content_hash === version.content_hash) ? "Publication withdrawn"
    : "Unpublished saved version";

  async function transition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (actionLock.current || status === "withdrawn") return;
    setActionError(""); setActionSuccess("");
    if (!attribution.recorder_label.trim() || (attribution.associated_role_id && !attribution.role_association_note?.trim()) || !notes.trim()) {
      setActionError("Human attribution, an association note when a role is selected, and nonblank lifecycle notes are required."); return;
    }
    const action = status === "published" ? "withdraw" : "publish";
    actionLock.current = true; setActionPending(action);
    const signal = lifetime.current?.signal;
    let persisted: ReportEvent;
    try {
      // Refresh lifecycle separately. Withdrawal must remain available even if
      // finding content or publication eligibility can no longer be read.
      const [freshReport, freshEvents] = await Promise.all([
        recordsApi.report(investigationId, report.id, signal),
        recordsApi.reportEvents(investigationId, report.id, signal),
      ]);
      if (signal?.aborted) return;
      setEvents(freshEvents);
      onRefresh?.({ ...freshReport, events: freshEvents });
      if (action === "withdraw") {
        const published = latestEvent(freshEvents);
        if (freshReport.status !== "published" || published?.event_type !== "published") throw new Error("The report is no longer published. Refresh its lifecycle events.");
        persisted = await recordsApi.withdrawReport(investigationId, report.id, { attribution, notes, report_version_id: published.report_version_id });
      } else {
        if (freshReport.status !== "draft") throw new Error("Only a draft report can be published. Refresh its lifecycle events.");
        const checked = await checkEligibility(investigationId, report.id, version, signal);
        if (signal?.aborted) return;
        setEligibility(checked); setEligibilityError("");
        if (!checked.length || checked.some((item) => item.problems.length > 0)) throw new Error("Publication eligibility changed or no finding is included. Review the refreshed checks below.");
        // Explicitly target the viewed saved version, including an older version.
        persisted = await recordsApi.publishReport(investigationId, report.id, { attribution, notes, report_version_id: version.id });
      }
    } catch (reason) {
      if (!signal?.aborted) setActionError(message(reason));
      return;
    } finally {
      actionLock.current = false;
      if (!signal?.aborted) setActionPending("");
    }
    if (signal?.aborted) return;
    setEvents((current) => [...current.filter((item) => item.id !== persisted.id), persisted]);
    setActionSuccess(`Recorded ${persisted.event_type} event ${persisted.id}.`);
    onEvent(persisted);
  }

  return <section className="records-panel" aria-label="Report lifecycle">
    <h4>Report lifecycle</h4>
    <p>Overall report status: <strong>{status}</strong></p>
    <p>Viewed version {version.version_number}: <strong>{viewedPublication}</strong></p>
    {publishedEvent && <p className="records-meta">Actual published version: {publishedEvent.report_version_id} · event sequence {publishedEvent.sequence_number}</p>}
    <p className="records-note">Publication is a manually recorded workflow action. It does not validate a scientific result, authenticate a person, host a public document, or assert experimental execution.</p>
    {status === "draft" && <div className="records-card">
      <h5>Publication eligibility for viewed version {version.version_number}</h5>
      <p className="records-note">Advisory only; the server makes the authoritative decision. Every included finding needs its latest exact-hash manual review to accept inclusion with all required checks. Review counts and majorities are not used.</p>
      <button type="button" disabled={eligibilityPending || Boolean(actionPending)} onClick={() => setEligibilityRevision((value) => value + 1)}>{eligibilityPending ? "Refreshing eligibility…" : "Refresh exact-hash eligibility"}</button>
      {eligibilityError && <p className="records-error" role="alert">Eligibility refresh failed: {eligibilityError}</p>}
      {eligibility !== null && !eligibility.length && <p className="records-note">At least one included finding is required for publication.</p>}
      {eligibility?.map((item) => <div className="records-card" key={item.versionId}>
        <p className="records-meta">Finding version {item.versionId}</p><p className="records-hash">Exact finding SHA-256: {item.hash}</p>
        {item.reviewId && <p className="records-meta">Latest exact-hash review: {item.reviewId} · {item.reviewedAt}</p>}
        {item.problems.length ? <ul className="records-note">{item.problems.map((problem) => <li key={problem}>{problem}</li>)}</ul> : <p className="records-success">Latest exact-hash review accepts inclusion with the required checks.</p>}
      </div>)}
    </div>}
    {status !== "withdrawn" ? <form className="records-form" onSubmit={transition}>
      <AttributionFields value={attribution} onChange={setAttribution} scientists={scientists} disabled={Boolean(actionPending)} />
      <label>Required {status === "published" ? "withdrawal" : "publication"} notes<textarea required maxLength={5000} disabled={Boolean(actionPending)} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
      {status === "published" && <p className="records-note">Withdrawal targets the actual published version shown above, even when a newer, unpublished version is being viewed. Finding eligibility does not gate withdrawal.</p>}
      <div className="records-actions"><button type="submit" disabled={Boolean(actionPending) || (status === "draft" ? !canPublish : !publishedEvent)}>{actionPending ? `${actionPending === "publish" ? "Publishing" : "Withdrawing"}…` : status === "published" ? "Withdraw actual published version" : `Publish viewed saved version ${version.version_number}`}</button></div>
    </form> : <p className="records-note">This report has been withdrawn. Further publication and editing are unavailable; its versions, events, and stored exports remain part of the record.</p>}
    {actionError && <p className="records-error" role="alert">Lifecycle action failed: {actionError}</p>}
    {actionSuccess && <p className="records-success" role="status">{actionSuccess}</p>}
    <div className="records-row"><h5>Append-only lifecycle events</h5><button type="button" disabled={eventsPending || Boolean(actionPending)} onClick={() => setEventRevision((value) => value + 1)}>{eventsPending ? "Refreshing events…" : "Refresh events"}</button></div>
    {eventsError && <p className="records-error" role="alert">Event refresh failed: {eventsError}{actionSuccess ? " The recorded action succeeded." : ""}</p>}
    {!eventsPending && !combinedEvents.length && <p className="records-note">No publication or withdrawal events recorded.</p>}
    <ol>{combinedEvents.map((event) => <li className="records-card" key={event.id}>
      <p><strong>Sequence {event.sequence_number}: {event.event_type}</strong></p>
      <p className="records-meta">Event {event.id} · {event.created_at}</p>
      <p className="records-meta">Target version: {event.report_version_id}</p><p className="records-hash">Target SHA-256: {event.target_content_hash}</p>
      <p>{event.notes}</p><AttributionDisplay value={event.attribution} />
    </li>)}</ol>
  </section>;
}
