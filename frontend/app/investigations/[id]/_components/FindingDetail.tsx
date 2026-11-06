"use client";

import { useId } from "react";
import type { Finding, FindingVersion } from "../../../lib/api";
import { AttributionDisplay } from "./AttributionFields";
import { NumericSourceSpan } from "./CitationDrawer";

export type FindingDetailProps = {
  finding: Finding;
  version: FindingVersion;
  onVersionChange: (versionId: string) => void;
  onCitation: (citationKey: string, trigger: HTMLButtonElement) => void;
  onEdit?: () => void;
  onReview?: () => void;
  enabled?: boolean;
};

export default function FindingDetail({ finding, version, onVersionChange, onCitation, onEdit, onReview, enabled = true }: FindingDetailProps) {
  const id = useId();
  const definition = version.finding;
  const links = new Map(version.evidence_links.map((link) => [link.citation_key, link]));
  return <article className="records-panel" aria-labelledby={`${id}-title`}>
    <div className="records-row">
      <div><p className="records-meta">{definition.record_kind.replaceAll("_", " ")} · version {version.version_number}</p><h3 id={`${id}-title`}>{definition.title}</h3></div>
      <div className="records-actions">
        {onEdit && <button type="button" onClick={onEdit} disabled={!enabled}>Create new version from this version</button>}
        {onReview && <button type="button" onClick={onReview} disabled={!enabled}>Review this exact version</button>}
      </div>
    </div>
    <label htmlFor={`${id}-version`}>Finding version history</label>
    <select id={`${id}-version`} value={version.id} onChange={(event) => onVersionChange(event.target.value)}>
      {[...finding.versions].sort((a, b) => b.version_number - a.version_number).map((item) => <option key={item.id} value={item.id}>Version {item.version_number} · {item.finding.title} · {item.content_hash}</option>)}
    </select>
    <p className="records-meta">Version ID: {version.id} · Parent version: {version.parent_version_id ?? "None (initial version)"} · Created: {version.created_at}</p>
    <p className="records-hash">Exact content hash: {version.content_hash}</p>
    <p className="records-meta">Claim: {definition.claim_id ?? "No claim linked"} · Protocol version: {definition.protocol_version_id ?? "No protocol linked"}</p>
    <h4>Assertions</h4>
    {definition.assertions.map((assertion) => <section className="records-card" key={assertion.key} aria-label={`Assertion ${assertion.key}`}>
      <p className="records-meta">{assertion.key} · {assertion.assertion_kind.replaceAll("_", " ")} · {assertion.grounding.replaceAll("_", " ")}</p>
      <p>{assertion.text}</p>
      {assertion.grounding === "unresolved" && <p className="records-note">Unresolved reason: {assertion.unresolved_reason ?? "Missing from stored record"}</p>}
      <div className="records-actions">
        {assertion.citation_keys.map((key) => <button type="button" key={key} disabled={!links.has(key)} onClick={(event) => onCitation(key, event.currentTarget)}>Citation {key}{!links.has(key) ? " (snapshot missing)" : ` · ${links.get(key)?.relationship}`}</button>)}
      </div>
      {!assertion.citation_keys.length && <p className="records-note">No citations recorded for this assertion.</p>}
      {assertion.numbers.map((number, index) => <div key={index}>
        <p className="records-meta">Numeric assertion · citation {number.citation_key}</p>
        <NumericSourceSpan number={number} quote={links.get(number.citation_key)?.source_snapshot_json.quoted_text} />
        {links.has(number.citation_key) && <button type="button" onClick={(event) => onCitation(number.citation_key, event.currentTarget)}>Inspect numeric citation {number.citation_key}</button>}
      </div>)}
    </section>)}
    <h4>Citation relationships</h4>
    {version.evidence_links.length ? version.evidence_links.map((link) => <div className="records-card" key={link.id}>
      <button type="button" onClick={(event) => onCitation(link.citation_key, event.currentTarget)}>Open citation {link.citation_key}</button>
      <p><strong>{link.relationship}</strong> · {link.rationale}</p>
      <p className="records-hash">Snapshot hash: {link.snapshot_hash}</p>
    </div>) : <p className="records-note">No evidence links recorded.</p>}
    <h4>Limitations</h4>
    {definition.limitations.length ? <ul>{definition.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul> : <p className="records-note">No limitations recorded. This does not establish that none exist.</p>}
    <h4>Original recorder attribution</h4>
    <AttributionDisplay value={version.attribution} />
  </article>;
}
