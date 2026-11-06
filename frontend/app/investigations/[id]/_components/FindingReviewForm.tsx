"use client";

import { type FormEvent, useId, useRef, useState } from "react";
import { recordsApi, type FindingVersion, type RecordReview, type RecordReviewCreate, type Scientist } from "../../../lib/api";
import AttributionFields, { emptyAttribution } from "./AttributionFields";

export type FindingReviewFormProps = {
  investigationId: string;
  findingId: string;
  version: FindingVersion;
  scientists: Scientist[];
  onSaved: (review: RecordReview) => Promise<void> | void;
  enabled?: boolean;
};

export default function FindingReviewForm(props: FindingReviewFormProps) {
  return <ReviewDraft key={`${props.investigationId}:${props.version.id}:${props.version.content_hash}`} {...props} />;
}

function ReviewDraft({ investigationId, findingId, version, scientists, onSaved, enabled = true }: FindingReviewFormProps) {
  const id = useId();
  const [attribution, setAttribution] = useState(emptyAttribution);
  const [outcome, setOutcome] = useState<RecordReviewCreate["outcome"] | "">("");
  const [notes, setNotes] = useState("");
  const [disclosures, setDisclosures] = useState("");
  const [citationsChecked, setCitationsChecked] = useState(false);
  const [numbersChecked, setNumbersChecked] = useState(false);
  const [limitationsChecked, setLimitationsChecked] = useState(false);
  const [executionChecked, setExecutionChecked] = useState(false);
  const [pending, setPending] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [refreshError, setRefreshError] = useState("");
  const [saved, setSaved] = useState<RecordReview | null>(null);
  const lock = useRef(false);
  const refreshLock = useRef(false);
  const hasNumbers = version.finding.assertions.some((assertion) => assertion.numbers.length > 0);
  const accepted = outcome === "accepted_for_inclusion";
  const acceptanceReady = citationsChecked && limitationsChecked && executionChecked && (!hasNumbers || numbersChecked);

  async function refresh(review: RecordReview) {
    if (refreshLock.current) return;
    refreshLock.current = true;
    setRefreshing(true);
    setRefreshError("");
    try { await onSaved(review); }
    catch (reason) { setRefreshError(`Review saved, but refreshing the view failed: ${reason instanceof Error ? reason.message : "Could not refresh."} Retry refresh; this will not submit another review.`); }
    finally { refreshLock.current = false; setRefreshing(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || saved || !enabled) return;
    setError("");
    if (!outcome || !notes.trim() || !attribution.recorder_label.trim() || (attribution.associated_role_id && !attribution.role_association_note?.trim())) {
      setError("Provide an outcome, review notes, a human recorder label, and a note for any associated role.");
      return;
    }
    if (accepted && !acceptanceReady) { setError("Acceptance requires every applicable review check to be explicitly confirmed."); return; }
    const dependencyDisclosures = disclosures.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (dependencyDisclosures.length > 50) { setError("Use at most 50 dependency disclosures."); return; }
    if (version.finding_id !== findingId || version.investigation_id !== investigationId) { setError("The review target does not belong to this finding and investigation."); return; }
    const payload: RecordReviewCreate = {
      attribution,
      expected_content_hash: version.content_hash,
      review_method: "manual_review",
      outcome,
      notes,
      citations_checked: citationsChecked,
      numeric_transcription_checked: hasNumbers ? numbersChecked : null,
      limitations_checked: limitationsChecked,
      execution_wording_checked: executionChecked,
      dependency_disclosures: dependencyDisclosures,
    };
    lock.current = true;
    setPending(true);
    let review: RecordReview;
    try { review = await recordsApi.createFindingReview(investigationId, findingId, version.id, payload); }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the review. Your draft is preserved.");
      lock.current = false;
      setPending(false);
      return;
    }
    setSaved(review);
    setAttribution(emptyAttribution()); setOutcome(""); setNotes(""); setDisclosures("");
    setCitationsChecked(false); setNumbersChecked(false); setLimitationsChecked(false); setExecutionChecked(false);
    await refresh(review);
    lock.current = false;
    setPending(false);
  }

  return <section className="records-panel" aria-labelledby={`${id}-heading`}>
    <h4 id={`${id}-heading`}>Manual review of version {version.version_number}</h4>
    <p className="records-hash">Exact review target: {version.content_hash}</p>
    <p className="records-note">Review method: manual_review. Checks are caller assertions and begin unchecked. A review does not indicate that an experiment ran.</p>
    {saved ? <>
      <p className="records-success" role="status">Review saved · {saved.id} · {saved.outcome.replaceAll("_", " ")}</p>
      {refreshError && <p className="records-error" role="alert">{refreshError}</p>}
      <div className="records-actions">
        {refreshError && <button type="button" disabled={pending || refreshing} onClick={() => void refresh(saved)}>{refreshing ? "Refreshing…" : "Retry refresh"}</button>}
        {!refreshError && <button type="button" disabled={pending || refreshing || !enabled} onClick={() => setSaved(null)}>Write another review</button>}
      </div>
    </> : <form className="records-form" onSubmit={submit}>
      <fieldset disabled={pending || !enabled}>
        <legend>Review decision</legend>
        <label htmlFor={`${id}-outcome`}>Review outcome (required)</label>
        <select id={`${id}-outcome`} value={outcome} required onChange={(event) => setOutcome(event.target.value as typeof outcome)}>
          <option value="">Select an outcome</option>
          <option value="accepted_for_inclusion">Accepted for inclusion</option>
          <option value="needs_revision">Needs revision</option>
          <option value="abstained">Abstained</option>
        </select>
        <label htmlFor={`${id}-citations`}><input id={`${id}-citations`} type="checkbox" checked={citationsChecked} required={accepted} onChange={(event) => setCitationsChecked(event.target.checked)} /> Citations and exact source snapshots checked</label>
        {hasNumbers ? <label htmlFor={`${id}-numbers`}><input id={`${id}-numbers`} type="checkbox" checked={numbersChecked} required={accepted} onChange={(event) => setNumbersChecked(event.target.checked)} /> Numeric transcription, source spans, units, context, and normalization checked</label> : <p className="records-meta">Numeric transcription check: not applicable; this version has no structured numeric assertions.</p>}
        <label htmlFor={`${id}-limitations`}><input id={`${id}-limitations`} type="checkbox" checked={limitationsChecked} required={accepted} onChange={(event) => setLimitationsChecked(event.target.checked)} /> Limitations and unresolved reasons checked</label>
        <label htmlFor={`${id}-execution`}><input id={`${id}-execution`} type="checkbox" checked={executionChecked} required={accepted} onChange={(event) => setExecutionChecked(event.target.checked)} /> Execution wording checked; no unsupported execution claim</label>
        <label htmlFor={`${id}-notes`}>Review notes (required)</label>
        <textarea id={`${id}-notes`} required maxLength={5000} value={notes} onChange={(event) => setNotes(event.target.value)} />
        <label htmlFor={`${id}-disclosures`}>Dependency disclosures (optional, one per line; maximum 50)</label>
        <textarea id={`${id}-disclosures`} value={disclosures} onChange={(event) => setDisclosures(event.target.value)} />
      </fieldset>
      <AttributionFields value={attribution} onChange={setAttribution} scientists={scientists} disabled={pending || !enabled} />
      {error && <p className="records-error" role="alert">{error}</p>}
      <div className="records-actions"><button type="submit" disabled={pending || !enabled || (accepted && !acceptanceReady)}>{pending ? "Saving review…" : "Save exact-version review"}</button></div>
    </form>}
  </section>;
}
