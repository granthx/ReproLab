"use client";

import type { ReportSourceContext, ReportVersion } from "../../../lib/api";
import { AttributionDisplay } from "./AttributionFields";

export type ReportPreviewProps = { version: ReportVersion };

function TextList({ items, empty }: { items: string[]; empty: string }) {
  return items.length ? <ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p className="records-note">{empty}</p>;
}

export default function ReportPreview({ version }: ReportPreviewProps) {
  const canonical = version.canonical_content_json;
  const context: ReportSourceContext | undefined = canonical.source_context;
  if (!context?.investigation || !Array.isArray(context.claims) || !Array.isArray(context.findings)) {
    return <p className="records-error" role="alert">This saved version has no valid canonical source context. Its contents cannot be previewed.</p>;
  }
  const links = canonical.finding_links;

  return <article className="records-panel" aria-label="Saved report preview">
    <h4>{canonical.title}</h4>
    <p className="records-note">Analysis/record report. This records source analysis; publication does not assert that an experiment occurred or turn framework-test scoring into scientific evidence.</p>
    <p className="records-meta">Saved version {version.version_number} · {version.id} · {version.created_at}</p>
    <p className="records-hash">Report SHA-256: {version.content_hash}</p>
    <AttributionDisplay value={version.attribution} />

    <h5>Investigation snapshot</h5>
    <dl className="records-meta">
      <dt>Investigation</dt><dd>{context.investigation.id}</dd>
      <dt>Source kind</dt><dd>{context.investigation.source_kind}</dd>
      <dt>Paper</dt><dd>{context.investigation.paper_id ?? "None recorded"}</dd>
      <dt>Execution status</dt><dd>{context.investigation.execution_status}</dd>
      <dt>Claim assessment</dt><dd>{context.investigation.claim_assessment}</dd>
    </dl>
    <h5>Scope claims — saved snapshots</h5>
    {!context.claims.length && <p className="records-note">No scope claims selected.</p>}
    {context.claims.map((claim) => <div className="records-card" key={claim.id}>
      <p>{claim.statement}</p>
      <p className="records-meta">{claim.id} · {claim.source_kind} · {claim.source_locator ?? "No source locator"}</p>
      <p className="records-meta">Metric: {claim.metric_name} · reported: {claim.reported_value ?? "Not recorded"} · direction: {claim.metric_direction}</p>
      <p className="records-meta">Source marked published: {claim.published ? "yes" : "no"} · verification: {claim.verification_status}</p>
    </div>)}

    <h5>Exact finding selections</h5>
    {!links.length && <p className="records-note">No finding versions selected.</p>}
    {links.map((link) => {
      const snapshot = context.findings.find((item) => item.finding_version_id === link.finding_version_id);
      const valid = snapshot && snapshot.finding_content_hash === link.finding_content_hash;
      return <section className="records-card" key={link.finding_version_id}>
        <h5>{link.section} · position {link.position} · {link.disposition === "included" ? "Included" : "Excluded with reason"}</h5>
        <p className="records-meta">Finding version: {link.finding_version_id}</p>
        <p className="records-hash">Pinned finding SHA-256: {link.finding_content_hash}</p>
        {link.disposition === "excluded_with_reason" && <p><strong>Exclusion reason:</strong> {link.exclusion_reason}</p>}
        {!valid ? <p className="records-error" role="alert">The canonical finding snapshot is missing or does not match the selected hash.</p> : <>
          <p className="records-meta">Finding: {snapshot.finding_id} · {snapshot.finding.record_kind}</p>
          <h5>{snapshot.finding.title}</h5>
          <AttributionDisplay value={snapshot.attribution} />
          {link.disposition === "included" ? <>
            <p className="records-meta">Claim: {snapshot.finding.claim_id ?? "None"} · Protocol version: {snapshot.finding.protocol_version_id ?? "None"}</p>
            {snapshot.finding.assertions.map((assertion) => <div className="records-card" key={assertion.key}>
              <p className="records-meta">{assertion.key} · {assertion.assertion_kind} · {assertion.grounding}</p>
              <p>{assertion.text}</p>
              {assertion.unresolved_reason && <p><strong>Unresolved reason:</strong> {assertion.unresolved_reason}</p>}
              <p className="records-meta">Citations: {assertion.citation_keys.join(", ") || "None"}</p>
              {assertion.numbers.map((number, index) => <dl className="records-card" key={index}>
                <dt>Numeric transcription</dt><dd>{number.metric_name}: <code>{number.value}</code> {number.unit}</dd>
                <dt>Exact source lexeme</dt><dd><code>{number.source_lexeme}</code></dd>
                <dt>Citation / source span</dt><dd>{number.citation_key} · {number.source_start}:{number.source_end}</dd>
                <dt>Normalization</dt><dd>{number.normalization}</dd>
                <dt>Context</dt><dd>{number.context}</dd>
                <dt>Uncertainty as reported</dt><dd>{number.uncertainty_as_reported ?? "Not recorded"}</dd>
              </dl>)}
            </div>)}
            <h5>Finding limitations</h5>
            <TextList items={snapshot.finding.limitations} empty="None recorded." />
            <h5>Pinned citations</h5>
            {!snapshot.evidence_snapshots.length && <p className="records-note">No evidence snapshots recorded.</p>}
            {snapshot.evidence_snapshots.map((evidence) => <details className="records-card" key={evidence.citation_key}>
              <summary>Citation {evidence.citation_key} · {evidence.relationship}</summary>
              <p>{evidence.rationale}</p>
              <p className="records-hash">Snapshot SHA-256: {evidence.snapshot_hash}</p>
              <p className="records-meta">Source locator: {String(evidence.source_snapshot.source_locator ?? "Not recorded")}</p>
              <blockquote>{String(evidence.source_snapshot.quoted_text ?? "No quotation recorded")}</blockquote>
              <p className="records-meta">Source URL: {String(evidence.source_snapshot.source_url ?? "Not recorded")}</p>
              <p className="records-meta">Verification: {String(evidence.source_snapshot.verification_status ?? "Not recorded")}</p>
              <pre>{JSON.stringify(evidence.source_snapshot, null, 2)}</pre>
            </details>)}
          </> : <p className="records-note">This finding is excluded from the report body. Its pinned context remains in the canonical source record below.</p>}
        </>}
      </section>;
    })}
    <h5>Report limitations</h5>
    <TextList items={canonical.limitations} empty="None recorded." />
    <h5>Unresolved questions</h5>
    <TextList items={canonical.unresolved_questions} empty="None recorded." />
    <details className="records-card"><summary>Complete canonical source context</summary><p className="records-note">Immutable saved source data, displayed as escaped text.</p><pre>{JSON.stringify(context, null, 2)}</pre></details>
  </article>;
}
