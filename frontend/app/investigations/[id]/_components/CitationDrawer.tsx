"use client";

import { useEffect, useId, useRef } from "react";
import type { EvidenceSnapshot, FindingEvidenceLink, NumericAssertion } from "../../../lib/api";

export type CitationDrawerProps = {
  citation: FindingEvidenceLink | null;
  numbers?: NumericAssertion[];
  onClose: () => void;
  returnFocus?: HTMLElement | null;
};

export function CodePointQuote({ quote }: { quote: string | null | undefined }) {
  if (typeof quote !== "string" || !quote.length) return <p className="records-note">No quoted source text recorded. Numeric source spans are unavailable.</p>;
  const points = Array.from(quote);
  return <>
    <pre className="records-note">{quote}</pre>
    <p className="records-meta">{points.length} Unicode code points. Offsets are zero-based; start is inclusive and end is exclusive.</p>
    <details>
      <summary>Inspect quotation code-point indices</summary>
      <div className="records-card" aria-label="Quotation with Unicode code-point indices">
        {points.map((point, index) => <span key={index} className="records-meta">[{index}] {JSON.stringify(point)}{" "}</span>)}
      </div>
    </details>
  </>;
}

export function NumericSourceSpan({ number, quote }: { number: NumericAssertion; quote: string | null | undefined }) {
  const points = typeof quote === "string" ? Array.from(quote) : null;
  const valid = points !== null && Number.isInteger(number.source_start) && Number.isInteger(number.source_end)
    && number.source_start >= 0 && number.source_end > number.source_start && number.source_end <= points.length;
  const selected = valid ? points.slice(number.source_start, number.source_end).join("") : null;
  return <div className="records-card">
    <p><strong>{number.metric_name}</strong>: <code>{number.value}</code> {number.unit}</p>
    <p>Recorded lexeme: <code>{number.source_lexeme}</code> · normalization: {number.normalization}</p>
    <p>Code-point span: [{number.source_start ?? "missing"}, {number.source_end ?? "missing"})</p>
    {selected === null ? <p className="records-error">Source span unavailable: quotation or valid offsets are missing. No span is inferred.</p> : <>
      <p>Exact snapshot span: <mark>{selected}</mark></p>
      {selected !== number.source_lexeme && <p className="records-error">The recorded lexeme does not match this snapshot span.</p>}
    </>}
    <p>Context: {number.context}</p>
    <p>Uncertainty as reported: {number.uncertainty_as_reported ?? "Not recorded"}</p>
  </div>;
}

export default function CitationDrawer({ citation, numbers = [], onClose, returnFocus }: CitationDrawerProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  const focusTarget = useRef(returnFocus);
  focusTarget.current = returnFocus;

  useEffect(() => {
    if (!citation || !dialog.current) return;
    const node = dialog.current;
    const trigger = focusTarget.current ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    const previousOverflow = document.body.style.overflow;
    if (!node.open) node.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      if (node.open) node.close();
      document.body.style.overflow = previousOverflow;
      if (trigger?.isConnected) trigger.focus();
    };
  }, [citation?.id]);

  const snapshot: EvidenceSnapshot | null = citation?.source_snapshot_json ?? null;
  return <dialog ref={dialog} className="records-panel" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`} onCancel={(event) => { event.preventDefault(); onClose(); }}>
    {citation && snapshot && <>
      <div className="records-actions"><h3 id={`${id}-title`}>Citation {citation.citation_key}</h3><button type="button" onClick={onClose} autoFocus>Close citation</button></div>
      <p id={`${id}-description`} className="records-note">Immutable source snapshot captured for this finding version. Escape closes this dialog.</p>
      <p>Relationship: <strong>{citation.relationship}</strong></p>
      <p>Rationale: {citation.rationale}</p>
      <p className="records-meta">Evidence item: {citation.evidence_item_id} · Pinned evidence review: {citation.evidence_review_id ?? "None"}</p>
      <p className="records-hash">Snapshot hash: {citation.snapshot_hash}</p>
      <p>Source locator: {snapshot.source_locator ?? "Not recorded"}</p>
      <p>Source URL: {snapshot.source_url ?? "Not recorded"}</p>
      <p className="records-hash">Source SHA-256: {snapshot.sha256 ?? "Not recorded"}</p>
      <p className="records-meta">Snapshot verification status: {snapshot.verification_status ?? "Not recorded"}</p>
      <p>Verification notes: {snapshot.verification_notes ?? "Not recorded"}</p>
      <h4>Snapshot quotation</h4>
      <CodePointQuote quote={snapshot.quoted_text} />
      <h4>Numeric source spans</h4>
      {numbers.length ? numbers.map((number, index) => <NumericSourceSpan key={index} number={number} quote={snapshot.quoted_text} />) : <p className="records-note">No numeric spans recorded for this citation. None are inferred from the quotation.</p>}
      {snapshot.evidence_review && <details><summary>Pinned evidence review snapshot</summary><pre>{JSON.stringify(snapshot.evidence_review, null, 2)}</pre></details>}
      <details><summary>Complete stored source snapshot</summary><pre>{JSON.stringify(snapshot, null, 2)}</pre></details>
    </>}
  </dialog>;
}
