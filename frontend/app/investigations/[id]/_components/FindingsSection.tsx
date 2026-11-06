"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { recordsApi, type Claim, type Evidence, type Finding, type FindingSummary, type FindingVersion, type Protocol, type RecordReview, type Scientist } from "../../../lib/api";
import { AttributionDisplay } from "./AttributionFields";
import CitationDrawer from "./CitationDrawer";
import FindingDetail from "./FindingDetail";
import FindingEditor from "./FindingEditor";
import FindingReviewForm from "./FindingReviewForm";

export type FindingsSectionProps = {
  investigationId: string;
  findings: FindingSummary[];
  claims: Claim[];
  evidence: Evidence[];
  protocols: Protocol[];
  scientists: Scientist[];
  onChanged: () => Promise<void> | void;
  onReviewChanged?: () => void;
  enabled?: boolean;
};

type DetailState = { findingId: string; record: Finding | null; pending: boolean; error: string };
type ReviewState = { target: string; rows: RecordReview[]; pending: boolean; error: string };
const targetKey = (version: FindingVersion) => `${version.id}:${version.content_hash}`;

export default function FindingsSection({ enabled = true, ...props }: FindingsSectionProps) {
  if (!enabled) return <section className="records-panel" aria-label="Findings"><h3>Findings</h3><p className="records-note">Traceable findings are unavailable for this workspace.</p></section>;
  return <FindingsWorkspace key={props.investigationId} {...props} />;
}

function FindingsWorkspace({ investigationId, findings, claims, evidence, protocols, scientists, onChanged, onReviewChanged }: Omit<FindingsSectionProps, "enabled">) {
  const id = useId();
  const [selectedId, setSelectedId] = useState(findings[0]?.id ?? "");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [detail, setDetail] = useState<DetailState>({ findingId: "", record: null, pending: false, error: "" });
  const [reviews, setReviews] = useState<ReviewState>({ target: "", rows: [], pending: false, error: "" });
  const [detailRevision, setDetailRevision] = useState(0);
  const [reviewRevision, setReviewRevision] = useState(0);
  const [reviewTarget, setReviewTarget] = useState<string | null>(null);
  const [editor, setEditor] = useState<{ parent: FindingVersion | null } | null>(null);
  const [citation, setCitation] = useState<{ target: string; key: string; trigger: HTMLButtonElement } | null>(null);
  const [success, setSuccess] = useState("");
  const detailController = useRef<AbortController | null>(null);
  const reviewController = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const selectedRef = useRef(selectedId);
  const versionRef = useRef(selectedVersionId);
  const currentTarget = useRef("");
  const notifiedReviews = useRef(new Set<string>());
  selectedRef.current = selectedId;
  versionRef.current = selectedVersionId;

  const record = detail.findingId === selectedId && detail.record?.id === selectedId ? detail.record : null;
  const version = record?.versions.find((item) => item.id === selectedVersionId);
  const target = version ? targetKey(version) : "";
  currentTarget.current = target;
  const summaryVersion = findings.find((item) => item.id === selectedId)?.latest_version_id;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; detailController.current?.abort(); reviewController.current?.abort(); };
  }, []);

  useEffect(() => {
    setSelectedId((current) => findings.some((item) => item.id === current) ? current : findings[0]?.id ?? "");
  }, [findings]);

  useEffect(() => {
    detailController.current?.abort();
    if (!selectedId) { setDetail({ findingId: "", record: null, pending: false, error: "" }); return; }
    const controller = new AbortController();
    detailController.current = controller;
    setDetail((current) => ({ findingId: selectedId, record: current.findingId === selectedId ? current.record : null, pending: true, error: "" }));
    recordsApi.finding(investigationId, selectedId, controller.signal).then((row) => {
      if (controller.signal.aborted || selectedRef.current !== selectedId) return;
      if (row.id !== selectedId || row.investigation_id !== investigationId || !row.versions.length) throw new Error("The response does not contain versions for this investigation's selected finding.");
      const latest = row.versions.reduce((latest, item) => item.version_number > latest.version_number ? item : latest);
      setSelectedVersionId(row.versions.some((item) => item.id === versionRef.current) ? versionRef.current : latest.id);
      setDetail({ findingId: selectedId, record: row, pending: false, error: "" });
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted && selectedRef.current === selectedId) setDetail((current) => ({ findingId: selectedId, record: current.findingId === selectedId ? current.record : null, pending: false, error: reason instanceof Error ? reason.message : "Could not load this finding." }));
    });
    return () => controller.abort();
  }, [investigationId, selectedId, summaryVersion, detailRevision]);

  const loadReviews = useCallback(async (selected: FindingVersion) => {
    reviewController.current?.abort();
    const controller = new AbortController();
    reviewController.current = controller;
    const key = targetKey(selected);
    const isCurrent = () => mounted.current && !controller.signal.aborted && currentTarget.current === key && reviewController.current === controller;
    if (isCurrent()) setReviews({ target: key, rows: [], pending: true, error: "" });
    try {
      const rows = await recordsApi.findingReviews(investigationId, selected.finding_id, selected.id, controller.signal);
      if (!isCurrent()) return;
      if (rows.some((row) => row.finding_version_id !== selected.id || row.target_content_hash !== selected.content_hash || row.investigation_id !== investigationId)) throw new Error("Review response did not match the exact selected version and hash.");
      setReviews({ target: key, rows, pending: false, error: "" });
    } catch (reason) {
      if (!isCurrent()) return;
      setReviews({ target: key, rows: [], pending: false, error: reason instanceof Error ? reason.message : "Could not load reviews." });
      throw reason;
    }
  }, [investigationId]);

  useEffect(() => {
    if (!version) { reviewController.current?.abort(); setReviews({ target: "", rows: [], pending: false, error: "" }); return; }
    void loadReviews(version).catch(() => undefined);
    return () => reviewController.current?.abort();
  }, [version, reviewRevision, loadReviews]);

  function selectFinding(findingId: string) {
    detailController.current?.abort(); reviewController.current?.abort();
    setSelectedId(findingId); setSelectedVersionId(""); setReviewTarget(null); setCitation(null); setSuccess("");
  }

  function selectVersion(versionId: string) {
    reviewController.current?.abort();
    setSelectedVersionId(versionId); setReviewTarget(null); setCitation(null); setSuccess("");
  }

  async function findingSaved(persisted: FindingVersion) {
    if (!mounted.current) return;
    await onChanged();
    if (!mounted.current) return;
    setSelectedId(persisted.finding_id); setSelectedVersionId(persisted.id);
    setReviewTarget(null); setCitation(null); setEditor(null);
    setSuccess(`Saved finding version ${persisted.version_number} (${persisted.id}).`);
    setDetailRevision((value) => value + 1);
  }

  async function reviewSaved(review: RecordReview, selected: FindingVersion) {
    if (!mounted.current) return;
    if (!notifiedReviews.current.has(review.id)) {
      onReviewChanged?.();
      notifiedReviews.current.add(review.id);
    }
    if (!mounted.current || currentTarget.current !== targetKey(selected)) return;
    setSuccess(`Saved ${review.outcome.replaceAll("_", " ")} review ${review.id} for version ${selected.version_number}.`);
    await loadReviews(selected);
  }

  const selectedCitation = citation?.target === target ? version?.evidence_links.find((link) => link.citation_key === citation.key) ?? null : null;
  const citationNumbers = selectedCitation && version ? version.finding.assertions.flatMap((assertion) => assertion.numbers.filter((number) => number.citation_key === selectedCitation.citation_key)) : [];
  const matchingReviews = reviews.target === target ? reviews : null;
  const detailPending = Boolean(selectedId) && (detail.findingId !== selectedId || detail.pending);

  return <section className="records-panel" aria-labelledby={`${id}-heading`}>
    <div className="records-row"><h3 id={`${id}-heading`}>Findings</h3><div className="records-actions"><button type="button" disabled={Boolean(editor)} onClick={() => { setEditor({ parent: null }); setReviewTarget(null); setCitation(null); setSuccess(""); }}>New finding</button>{selectedId && <button type="button" disabled={detailPending || Boolean(editor)} onClick={() => { setCitation(null); setDetailRevision((value) => value + 1); }}>{detailPending ? "Loading finding…" : "Refresh selected finding"}</button>}</div></div>
    <p className="records-note">Manually entered, evidence-linked analysis records. Versions and reviews retain their exact content hashes and source snapshots.</p>
    {success && <p className="records-success" role="status">{success}</p>}
    {!findings.length && <p className="records-note">No findings recorded yet. Choose New finding to enter a finding and its attribution.</p>}
    {findings.length > 0 && <><label htmlFor={`${id}-selection`}>Selected finding</label><select id={`${id}-selection`} disabled={Boolean(editor)} value={selectedId} onChange={(event) => selectFinding(event.target.value)}>{findings.map((finding) => <option key={finding.id} value={finding.id}>{finding.title} · latest version {finding.latest_version_number}</option>)}</select></>}
    {editor && <FindingEditor investigationId={investigationId} claims={claims} evidence={evidence} protocols={protocols} scientists={scientists} parentVersion={editor.parent} onSaved={findingSaved} onCancel={() => setEditor(null)} />}
    {!editor && <>
      {detailPending && <p className="records-note" role="status">Loading selected finding…</p>}
      {detail.findingId === selectedId && detail.error && <div className="records-error" role="alert"><p>Finding load failed: {detail.error}</p><button type="button" disabled={detailPending} onClick={() => setDetailRevision((value) => value + 1)}>Retry finding load</button></div>}
      {record && version && <>
        <FindingDetail finding={record} version={version} onVersionChange={selectVersion} onCitation={(key, trigger) => setCitation({ target, key, trigger })} onEdit={() => { setEditor({ parent: version }); setReviewTarget(null); setCitation(null); setSuccess(""); }} onReview={() => setReviewTarget(target)} />
        {reviewTarget === target && <FindingReviewForm investigationId={investigationId} findingId={record.id} version={version} scientists={scientists} onSaved={(review) => reviewSaved(review, version)} />}
        <section className="records-panel" aria-labelledby={`${id}-reviews`}>
          <div className="records-row"><h4 id={`${id}-reviews`}>Reviews of this exact version</h4><button type="button" disabled={!matchingReviews || matchingReviews.pending} onClick={() => setReviewRevision((value) => value + 1)}>Refresh reviews</button></div>
          <p className="records-hash">Target hash: {version.content_hash}</p>
          {(!matchingReviews || matchingReviews.pending) && <p className="records-note" role="status">Loading exact-version reviews…</p>}
          {matchingReviews?.error && <p className="records-error" role="alert">Review refresh failed: {matchingReviews.error}</p>}
          {matchingReviews && !matchingReviews.pending && !matchingReviews.error && !matchingReviews.rows.length && <p className="records-note">No reviews recorded for this version.</p>}
          {matchingReviews?.rows.map((review) => <article className="records-card" key={review.id}>
            <h5>{review.outcome.replaceAll("_", " ")}</h5>
            <p className="records-meta">{review.review_method} · {review.reviewed_at} · Review {review.id}</p>
            <p className="records-hash">Reviewed hash: {review.target_content_hash}</p>
            <p>{review.notes}</p>
            <ul><li>Citations checked: {review.citations_checked ? "Yes" : "No"}</li><li>Numeric transcription checked: {review.numeric_transcription_checked === null ? "Not applicable / not recorded" : review.numeric_transcription_checked ? "Yes" : "No"}</li><li>Limitations checked: {review.limitations_checked ? "Yes" : "No"}</li><li>Execution wording checked: {review.execution_wording_checked ? "Yes" : "No"}</li></ul>
            <h6>Dependency disclosures</h6>{review.dependency_disclosures.length ? <ul>{review.dependency_disclosures.map((disclosure, index) => <li key={index}>{disclosure}</li>)}</ul> : <p className="records-note">No dependency disclosures recorded.</p>}
            <AttributionDisplay value={review.reviewer_attribution} />
          </article>)}
        </section>
      </>}
    </>}
    <CitationDrawer citation={selectedCitation} numbers={citationNumbers} returnFocus={citation?.trigger} onClose={() => setCitation(null)} />
  </section>;
}
