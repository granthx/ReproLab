"use client";

import { type FormEvent, useId, useRef, useState } from "react";
import { recordsApi, type Claim, type Evidence, type FindingAssertion, type FindingDefinition, type FindingVersion, type NumericAssertion, type Protocol, type Scientist } from "../../../lib/api";
import AttributionFields, { emptyAttribution } from "./AttributionFields";
import { CodePointQuote } from "./CitationDrawer";

export type FindingEditorProps = {
  investigationId: string;
  claims: Claim[];
  evidence: Evidence[];
  protocols: Protocol[];
  scientists: Scientist[];
  parentVersion?: FindingVersion | null;
  onSaved: (version: FindingVersion) => Promise<void> | void;
  onCancel: () => void;
  enabled?: boolean;
};

type DraftNumber = Omit<NumericAssertion, "source_start" | "source_end"> & { rowId: number; source_start: string; source_end: string };
type DraftAssertion = Omit<FindingAssertion, "assertion_kind" | "grounding" | "numbers"> & {
  rowId: number;
  assertion_kind: FindingAssertion["assertion_kind"] | "";
  grounding: FindingAssertion["grounding"] | "";
  numbers: DraftNumber[];
};
type DraftLink = FindingDefinition["evidence_links"][number] & { rowId: number };

const RECORD_KINDS: FindingDefinition["record_kind"][] = ["observation", "interpretation", "limitation", "unresolved_question", "resolution_note"];
const DECIMAL = /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/;

export default function FindingEditor(props: FindingEditorProps) {
  return <EditorDraft key={`${props.investigationId}:${props.parentVersion?.id ?? "new"}`} {...props} />;
}

function EditorDraft({ investigationId, claims, evidence, protocols, scientists, parentVersion = null, onSaved, onCancel, enabled = true }: FindingEditorProps) {
  const id = useId();
  const rowCounter = useRef(0);
  const nextId = () => ++rowCounter.current;
  function blankAssertion(): DraftAssertion {
    return { rowId: nextId(), key: "", assertion_kind: "", text: "", grounding: "", citation_keys: [], numbers: [], unresolved_reason: null };
  }
  function blankNumber(): DraftNumber {
    return { rowId: nextId(), metric_name: "", value: "", unit: "", citation_key: "", source_start: "", source_end: "", source_lexeme: "", normalization: "identity", context: "", uncertainty_as_reported: null };
  }
  const [recordKind, setRecordKind] = useState<FindingDefinition["record_kind"] | "">(parentVersion?.finding.record_kind ?? "");
  const [title, setTitle] = useState(parentVersion?.finding.title ?? "");
  const [claimId, setClaimId] = useState(parentVersion?.finding.claim_id ?? "");
  const [protocolId, setProtocolId] = useState(parentVersion?.finding.protocol_version_id ?? "");
  const [assertions, setAssertions] = useState<DraftAssertion[]>(() => parentVersion ? parentVersion.finding.assertions.map((assertion) => ({
    ...assertion, rowId: nextId(), numbers: assertion.numbers.map((number) => ({ ...number, rowId: nextId(), source_start: String(number.source_start), source_end: String(number.source_end) })),
  })) : [blankAssertion()]);
  const [links, setLinks] = useState<DraftLink[]>(() => parentVersion?.finding.evidence_links.map((link) => ({ ...link, rowId: nextId() })) ?? []);
  const [limitations, setLimitations] = useState(() => parentVersion?.finding.limitations.map((text) => ({ rowId: nextId(), text })) ?? []);
  const [attribution, setAttribution] = useState(emptyAttribution);
  const [pending, setPending] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [refreshError, setRefreshError] = useState("");
  const [saved, setSaved] = useState<FindingVersion | null>(null);
  const lock = useRef(false);
  const refreshLock = useRef(false);

  function updateAssertion(rowId: number, patch: Partial<DraftAssertion>) {
    setAssertions((rows) => rows.map((row) => row.rowId === rowId ? { ...row, ...patch } : row));
  }
  function updateNumber(assertionId: number, numberId: number, patch: Partial<DraftNumber>) {
    setAssertions((rows) => rows.map((row) => row.rowId === assertionId ? { ...row, numbers: row.numbers.map((number) => number.rowId === numberId ? { ...number, ...patch } : number) } : row));
  }
  function updateLink(rowId: number, patch: Partial<DraftLink>) {
    setLinks((rows) => rows.map((row) => row.rowId === rowId ? { ...row, ...patch } : row));
  }

  function definition(): FindingDefinition {
    if (!recordKind || !title.trim()) throw new Error("A record kind and title are required.");
    if (!attribution.recorder_label.trim() || (attribution.associated_role_id && !attribution.role_association_note?.trim())) throw new Error("Provide a human recorder label and a note for any associated role.");
    if (parentVersion && (parentVersion.investigation_id !== investigationId || !parentVersion.id || !parentVersion.finding_id)) throw new Error("The explicit parent version does not belong to this investigation.");
    if (claimId && !claims.some((claim) => claim.id === claimId && claim.investigation_id === investigationId)) throw new Error("Select an available claim in this investigation.");
    if (protocolId && !protocols.some((protocol) => protocol.id === protocolId && protocol.investigation_id === investigationId)) throw new Error("Select an available protocol version in this investigation.");
    const linkKeys = new Set<string>();
    const evidenceIds = new Set<string>();
    const evidenceLinks: FindingDefinition["evidence_links"] = links.map((link) => {
      if (!/^[A-Z][A-Z0-9_]{0,31}$/.test(link.key) || linkKeys.has(link.key)) throw new Error("Citation keys must be unique uppercase identifiers (maximum 32 characters).");
      linkKeys.add(link.key);
      const item = evidence.find((item) => item.id === link.evidence_item_id && item.investigation_id === investigationId);
      if (!item || evidenceIds.has(item.id)) throw new Error("Explicitly select a different available evidence item for each citation.");
      if (claimId && item.claim_id && item.claim_id !== claimId) throw new Error(`Citation ${link.key} belongs to another claim.`);
      if (!link.rationale.trim()) throw new Error(`Citation ${link.key} requires a rationale.`);
      evidenceIds.add(item.id);
      return { key: link.key, evidence_item_id: item.id, evidence_review_id: link.evidence_review_id ?? null, relationship: link.relationship, rationale: link.rationale };
    });
    const assertionKeys = new Set<string>();
    const findingAssertions: FindingAssertion[] = assertions.map((assertion) => {
      if (!/^[a-z][a-z0-9_]{0,31}$/.test(assertion.key) || assertionKeys.has(assertion.key)) throw new Error("Assertion keys must be unique lowercase identifiers (maximum 32 characters).");
      assertionKeys.add(assertion.key);
      if (!assertion.assertion_kind || !assertion.grounding || !assertion.text.trim()) throw new Error(`Assertion ${assertion.key} requires kind, text, and grounding.`);
      if (assertion.citation_keys.some((key) => !linkKeys.has(key))) throw new Error(`Assertion ${assertion.key} has a missing citation. Remove or replace that reference.`);
      if (assertion.grounding === "source_grounded" && !assertion.citation_keys.length) throw new Error(`Source-grounded assertion ${assertion.key} requires a selected citation.`);
      if (assertion.grounding === "unresolved" && (!assertion.unresolved_reason?.trim() || assertion.numbers.length)) throw new Error(`Unresolved assertion ${assertion.key} requires a reason and cannot contain numbers. Remove numeric rows before changing grounding.`);
      const numbers: NumericAssertion[] = assertion.numbers.map((number) => {
        if (!number.metric_name.trim() || !number.unit.trim() || !number.context.trim() || !DECIMAL.test(number.value)) throw new Error(`Numeric fields for ${assertion.key} require a metric, an unrounded decimal string, a unit, and context.`);
        if (!assertion.citation_keys.includes(number.citation_key)) throw new Error(`Select one of assertion ${assertion.key}'s citations for each numeric row.`);
        const link = links.find((link) => link.key === number.citation_key);
        const quote = evidence.find((item) => item.id === link?.evidence_item_id)?.quoted_text;
        const points = typeof quote === "string" ? Array.from(quote) : [];
        if (!/^\d+$/.test(number.source_start) || !/^\d+$/.test(number.source_end)) throw new Error("Numeric source offsets must be explicitly entered nonnegative integer code-point indices.");
        const start = Number(number.source_start);
        const end = Number(number.source_end);
        if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || end <= start || end > points.length || !number.source_lexeme || points.slice(start, end).join("") !== number.source_lexeme) throw new Error(`Numeric source span for ${assertion.key} must exactly match the selected evidence quotation using Unicode code-point offsets.`);
        if (number.normalization === "percent_to_fraction" && !number.source_lexeme.trim().endsWith("%")) throw new Error("Percent-to-fraction normalization requires a source lexeme ending in %. Enter the normalized value explicitly.");
        return { metric_name: number.metric_name, value: number.value, unit: number.unit, citation_key: number.citation_key, source_start: start, source_end: end, source_lexeme: number.source_lexeme, normalization: number.normalization, context: number.context, uncertainty_as_reported: number.uncertainty_as_reported || null };
      });
      return { key: assertion.key, assertion_kind: assertion.assertion_kind, text: assertion.text, grounding: assertion.grounding, citation_keys: assertion.citation_keys, numbers, unresolved_reason: assertion.grounding === "unresolved" ? assertion.unresolved_reason : null };
    });
    if (!findingAssertions.length) throw new Error("At least one assertion is required.");
    if (limitations.some((limitation) => !limitation.text.trim())) throw new Error("Fill in or remove each limitation row.");
    return { record_kind: recordKind, title, claim_id: claimId || null, protocol_version_id: protocolId || null, assertions: findingAssertions, evidence_links: evidenceLinks, limitations: limitations.map((limitation) => limitation.text) };
  }

  async function refresh(version: FindingVersion) {
    if (refreshLock.current) return;
    refreshLock.current = true; setRefreshing(true); setRefreshError("");
    try { await onSaved(version); }
    catch (reason) { setRefreshError(`Finding saved, but refreshing the view failed: ${reason instanceof Error ? reason.message : "Could not refresh."} Retry refresh; this will not create another version.`); }
    finally { refreshLock.current = false; setRefreshing(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || saved || !enabled) return;
    setError("");
    let finding: FindingDefinition;
    try { finding = definition(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Check the finding fields."); return; }
    lock.current = true; setPending(true);
    let version: FindingVersion;
    try {
      if (parentVersion) {
        version = await recordsApi.createFindingVersion(investigationId, parentVersion.finding_id, { attribution, finding, parent_version_id: parentVersion.id });
      } else {
        const created = await recordsApi.createFinding(investigationId, { attribution, finding });
        version = created.versions.reduce((latest, item) => item.version_number > latest.version_number ? item : latest);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the finding. Your draft is preserved.");
      lock.current = false; setPending(false); return;
    }
    setSaved(version);
    setRecordKind(""); setTitle(""); setClaimId(""); setProtocolId(""); setAssertions([blankAssertion()]); setLinks([]); setLimitations([]); setAttribution(emptyAttribution());
    await refresh(version);
    lock.current = false; setPending(false);
  }

  return <section className="records-panel" aria-labelledby={`${id}-heading`}>
    <h3 id={`${id}-heading`}>{parentVersion ? "Create a new finding version" : "New finding"}</h3>
    {parentVersion && <div className="records-card"><p>Explicit parent: version {parentVersion.version_number} · {parentVersion.id}</p><p className="records-hash">Parent content hash: {parentVersion.content_hash}</p><p className="records-note">This appends a version based on the selected version. Evidence will be snapshotted from the currently selected evidence items when saved.</p></div>}
    {saved ? <>
      <p className="records-success" role="status">Finding version {saved.version_number} saved · {saved.id}</p>
      <p className="records-hash">{saved.content_hash}</p>
      {refreshError && <p className="records-error" role="alert">{refreshError}</p>}
      <div className="records-actions">{refreshError && <button type="button" disabled={pending || refreshing} onClick={() => void refresh(saved)}>{refreshing ? "Refreshing…" : "Retry refresh"}</button>}<button type="button" disabled={pending || refreshing} onClick={onCancel}>Close editor</button></div>
    </> : <form className="records-form" onSubmit={submit}>
      <fieldset disabled={pending || !enabled}>
        <legend>Finding definition</legend>
        <label htmlFor={`${id}-kind`}>Record kind (required)</label>
        <select id={`${id}-kind`} value={recordKind} required onChange={(event) => setRecordKind(event.target.value as typeof recordKind)}><option value="">Select a record kind</option>{RECORD_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select>
        <label htmlFor={`${id}-title`}>Finding title (required)</label>
        <input id={`${id}-title`} value={title} required maxLength={500} onChange={(event) => setTitle(event.target.value)} />
        <div className="records-row">
          <div><label htmlFor={`${id}-claim`}>Linked claim (optional)</label><select id={`${id}-claim`} value={claimId} onChange={(event) => setClaimId(event.target.value)}><option value="">No claim linked</option>{claimId && !claims.some((claim) => claim.id === claimId) && <option value={claimId} disabled>{claimId} (unavailable)</option>}{claims.map((claim) => <option key={claim.id} value={claim.id}>{claim.statement}</option>)}</select></div>
          <div><label htmlFor={`${id}-protocol`}>Linked protocol version (optional)</label><select id={`${id}-protocol`} value={protocolId} onChange={(event) => setProtocolId(event.target.value)}><option value="">No protocol linked</option>{protocolId && !protocols.some((protocol) => protocol.id === protocolId) && <option value={protocolId} disabled>{protocolId} (unavailable)</option>}{protocols.map((protocol) => <option key={protocol.id} value={protocol.id}>Version {protocol.version_number} · {protocol.id}</option>)}</select></div>
        </div>
      </fieldset>
      <fieldset disabled={pending || !enabled}>
        <legend>Evidence citations</legend>
        <p className="records-note">Select evidence explicitly and explain its relationship. New citations have no pinned evidence review. Existing pins from the parent are shown below.</p>
        {links.map((link, index) => {
          const prefix = `${id}-link-${link.rowId}`;
          const item = evidence.find((item) => item.id === link.evidence_item_id);
          return <fieldset className="records-card" key={link.rowId}>
            <legend>Citation {index + 1}</legend>
            <label htmlFor={`${prefix}-key`}>Citation key {index + 1} (uppercase identifier)</label>
            <input id={`${prefix}-key`} required maxLength={32} pattern="[A-Z][A-Z0-9_]{0,31}" value={link.key} onChange={(event) => updateLink(link.rowId, { key: event.target.value })} />
            <label htmlFor={`${prefix}-evidence`}>Evidence item for citation {index + 1}</label>
            <select id={`${prefix}-evidence`} required value={link.evidence_item_id} onChange={(event) => updateLink(link.rowId, { evidence_item_id: event.target.value, evidence_review_id: null })}>
              <option value="">Select evidence explicitly</option>
              {link.evidence_item_id && !item && <option value={link.evidence_item_id} disabled>{link.evidence_item_id} (unavailable)</option>}
              {evidence.map((candidate) => <option key={candidate.id} value={candidate.id} disabled={links.some((other) => other.rowId !== link.rowId && other.evidence_item_id === candidate.id)}>{candidate.source_locator} · {candidate.id}</option>)}
            </select>
            <label htmlFor={`${prefix}-relationship`}>Relationship for citation {index + 1}</label>
            <select id={`${prefix}-relationship`} value={link.relationship} onChange={(event) => updateLink(link.rowId, { relationship: event.target.value as DraftLink["relationship"] })}><option value="context">Context</option><option value="supports">Supports</option><option value="contradicts">Contradicts</option></select>
            <label htmlFor={`${prefix}-rationale`}>Rationale for citation {index + 1} (required)</label>
            <textarea id={`${prefix}-rationale`} required maxLength={5000} value={link.rationale} onChange={(event) => updateLink(link.rowId, { rationale: event.target.value })} />
            <p className="records-meta">Pinned evidence review: {link.evidence_review_id ?? "None"}</p>
            {link.evidence_review_id && <button type="button" onClick={() => updateLink(link.rowId, { evidence_review_id: null })}>Remove pinned review from citation {index + 1}</button>}
            {item && <><p className="records-meta">Current evidence quotation for the new snapshot · {item.source_locator}</p><CodePointQuote quote={item.quoted_text} /></>}
            <button type="button" onClick={() => setLinks((rows) => rows.filter((row) => row.rowId !== link.rowId))}>Remove citation {index + 1}</button>
          </fieldset>;
        })}
        <button type="button" disabled={links.length >= 100 || !evidence.length} onClick={() => setLinks((rows) => [...rows, { rowId: nextId(), key: "", evidence_item_id: "", evidence_review_id: null, relationship: "context", rationale: "" }])}>Add evidence citation</button>
        {!evidence.length && <p className="records-note">No evidence items are available. Unresolved assertions can still be recorded with an explicit reason and no numeric assertions.</p>}
      </fieldset>
      {/* Assertion and numeric rows follow the same structured schema sent to the API. */}
      <fieldset disabled={pending || !enabled}>
        <legend>Assertions</legend>
        {assertions.map((assertion, index) => {
          const prefix = `${id}-assertion-${assertion.rowId}`;
          return <fieldset className="records-card" key={assertion.rowId}>
            <legend>Assertion {index + 1}</legend>
            <label htmlFor={`${prefix}-key`}>Assertion key {index + 1} (lowercase identifier)</label>
            <input id={`${prefix}-key`} required maxLength={32} pattern="[a-z][a-z0-9_]{0,31}" value={assertion.key} onChange={(event) => updateAssertion(assertion.rowId, { key: event.target.value })} />
            <label htmlFor={`${prefix}-kind`}>Assertion kind {index + 1}</label>
            <select id={`${prefix}-kind`} required value={assertion.assertion_kind} onChange={(event) => updateAssertion(assertion.rowId, { assertion_kind: event.target.value as DraftAssertion["assertion_kind"] })}><option value="">Select an assertion kind</option><option value="source_reported">Source reported</option><option value="interpretation">Interpretation</option><option value="uncertainty">Uncertainty</option></select>
            <label htmlFor={`${prefix}-text`}>Assertion text {index + 1}</label>
            <textarea id={`${prefix}-text`} required maxLength={10000} value={assertion.text} onChange={(event) => updateAssertion(assertion.rowId, { text: event.target.value })} />
            <label htmlFor={`${prefix}-grounding`}>Grounding for assertion {index + 1}</label>
            <select id={`${prefix}-grounding`} required value={assertion.grounding} onChange={(event) => updateAssertion(assertion.rowId, { grounding: event.target.value as DraftAssertion["grounding"] })}><option value="">Select grounding</option><option value="source_grounded">Source grounded</option><option value="unresolved" disabled={assertion.numbers.length > 0}>Unresolved (no numeric assertions)</option></select>
            {assertion.grounding === "unresolved" && <><label htmlFor={`${prefix}-reason`}>Unresolved reason for assertion {index + 1} (required)</label><textarea id={`${prefix}-reason`} required maxLength={5000} value={assertion.unresolved_reason ?? ""} onChange={(event) => updateAssertion(assertion.rowId, { unresolved_reason: event.target.value })} /></>}
            <fieldset><legend>Citations for assertion {index + 1}{assertion.grounding === "source_grounded" ? " (select at least one)" : " (optional)"}</legend>
              {links.filter((link) => link.key).map((link) => <label key={link.rowId} htmlFor={`${prefix}-citation-${link.rowId}`}><input type="checkbox" id={`${prefix}-citation-${link.rowId}`} checked={assertion.citation_keys.includes(link.key)} disabled={!assertion.citation_keys.includes(link.key) && assertion.citation_keys.length >= 50} onChange={(event) => updateAssertion(assertion.rowId, { citation_keys: event.target.checked ? Array.from(new Set([...assertion.citation_keys, link.key])) : assertion.citation_keys.filter((key) => key !== link.key) })} /> {link.key} · {link.relationship}</label>)}
              {assertion.citation_keys.filter((key) => !links.some((link) => link.key === key)).map((key) => <p className="records-error" key={key}>Missing citation {key} <button type="button" onClick={() => updateAssertion(assertion.rowId, { citation_keys: assertion.citation_keys.filter((item) => item !== key) })}>Remove missing reference {key}</button></p>)}
              {!links.some((link) => link.key) && <p className="records-note">Add and name a citation above to select it here.</p>}
            </fieldset>
            {assertion.numbers.map((number, numberIndex) => {
              const numericPrefix = `${prefix}-number-${number.rowId}`;
              const numericLink = links.find((link) => link.key === number.citation_key);
              const quote = evidence.find((item) => item.id === numericLink?.evidence_item_id)?.quoted_text;
              const points = quote ? Array.from(quote) : [];
              const start = /^\d+$/.test(number.source_start) ? Number(number.source_start) : null;
              const end = /^\d+$/.test(number.source_end) ? Number(number.source_end) : null;
              const span = start !== null && end !== null && end > start && end <= points.length ? points.slice(start, end).join("") : null;
              return <fieldset className="records-card" key={number.rowId}>
                <legend>Numeric assertion {index + 1}.{numberIndex + 1}</legend>
                <p className="records-note">Enter strings exactly; values are never inferred, converted, or rounded. Only offsets are parsed as integer indices.</p>
                <label htmlFor={`${numericPrefix}-metric`}>Metric name</label><input id={`${numericPrefix}-metric`} required maxLength={120} value={number.metric_name} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { metric_name: event.target.value })} />
                <label htmlFor={`${numericPrefix}-value`}>Numeric value (decimal string)</label><input id={`${numericPrefix}-value`} type="text" required maxLength={80} value={number.value} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { value: event.target.value })} />
                <label htmlFor={`${numericPrefix}-unit`}>Unit</label><input id={`${numericPrefix}-unit`} required maxLength={80} value={number.unit} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { unit: event.target.value })} />
                <label htmlFor={`${numericPrefix}-citation`}>Numeric source citation</label><select id={`${numericPrefix}-citation`} required value={number.citation_key} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { citation_key: event.target.value })}><option value="">Select an assertion citation</option>{number.citation_key && !assertion.citation_keys.includes(number.citation_key) && <option value={number.citation_key} disabled>{number.citation_key} (not selected for assertion)</option>}{assertion.citation_keys.map((key) => <option key={key} value={key}>{key}</option>)}</select>
                <CodePointQuote quote={quote} />
                <div className="records-row"><div><label htmlFor={`${numericPrefix}-start`}>Source start (code point, inclusive)</label><input id={`${numericPrefix}-start`} type="text" inputMode="numeric" pattern="[0-9]+" required value={number.source_start} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { source_start: event.target.value })} /></div><div><label htmlFor={`${numericPrefix}-end`}>Source end (code point, exclusive)</label><input id={`${numericPrefix}-end`} type="text" inputMode="numeric" pattern="[0-9]+" required value={number.source_end} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { source_end: event.target.value })} /></div></div>
                <p className={span === null ? "records-note" : "records-meta"}>Selected source span: {span === null ? "Unavailable — enter valid offsets and select quoted evidence. No span is inferred." : <mark>{span}</mark>}</p>
                <label htmlFor={`${numericPrefix}-lexeme`}>Exact source lexeme</label><input id={`${numericPrefix}-lexeme`} required maxLength={200} value={number.source_lexeme} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { source_lexeme: event.target.value })} />
                {span !== null && number.source_lexeme && span !== number.source_lexeme && <p className="records-error">Source lexeme does not match the selected span.</p>}
                <label htmlFor={`${numericPrefix}-normalization`}>Normalization</label><select id={`${numericPrefix}-normalization`} value={number.normalization} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { normalization: event.target.value as NumericAssertion["normalization"] })}><option value="identity">Identity</option><option value="percent_to_fraction">Percent to fraction (enter resulting value explicitly)</option></select>
                <label htmlFor={`${numericPrefix}-context`}>Numeric context (required)</label><textarea id={`${numericPrefix}-context`} required maxLength={2000} value={number.context} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { context: event.target.value })} />
                <label htmlFor={`${numericPrefix}-uncertainty`}>Uncertainty as reported (optional)</label><textarea id={`${numericPrefix}-uncertainty`} maxLength={2000} value={number.uncertainty_as_reported ?? ""} onChange={(event) => updateNumber(assertion.rowId, number.rowId, { uncertainty_as_reported: event.target.value || null })} />
                <button type="button" onClick={() => updateAssertion(assertion.rowId, { numbers: assertion.numbers.filter((item) => item.rowId !== number.rowId) })}>Remove numeric assertion {index + 1}.{numberIndex + 1}</button>
              </fieldset>;
            })}
            <div className="records-actions"><button type="button" disabled={assertion.grounding !== "source_grounded" || assertion.numbers.length >= 50} onClick={() => updateAssertion(assertion.rowId, { numbers: [...assertion.numbers, blankNumber()] })}>Add numeric assertion to assertion {index + 1}</button><button type="button" disabled={assertions.length <= 1} onClick={() => setAssertions((rows) => rows.filter((row) => row.rowId !== assertion.rowId))}>Remove assertion {index + 1}</button></div>
            {assertion.numbers.length > 0 && <p className="records-note">Remove numeric rows before choosing unresolved grounding.</p>}
          </fieldset>;
        })}
        <button type="button" disabled={assertions.length >= 100} onClick={() => setAssertions((rows) => [...rows, blankAssertion()])}>Add assertion</button>
      </fieldset>
      <fieldset disabled={pending || !enabled}><legend>Limitations</legend>
        {limitations.map((limitation, index) => <div className="records-card" key={limitation.rowId}><label htmlFor={`${id}-limitation-${limitation.rowId}`}>Limitation {index + 1}</label><textarea id={`${id}-limitation-${limitation.rowId}`} required value={limitation.text} onChange={(event) => setLimitations((rows) => rows.map((row) => row.rowId === limitation.rowId ? { ...row, text: event.target.value } : row))} /><button type="button" onClick={() => setLimitations((rows) => rows.filter((row) => row.rowId !== limitation.rowId))}>Remove limitation {index + 1}</button></div>)}
        <button type="button" disabled={limitations.length >= 100} onClick={() => setLimitations((rows) => [...rows, { rowId: nextId(), text: "" }])}>Add limitation</button>
      </fieldset>
      <AttributionFields value={attribution} onChange={setAttribution} scientists={scientists} disabled={pending || !enabled} />
      {error && <p className="records-error" role="alert">{error}</p>}
      <div className="records-actions"><button type="submit" disabled={pending || !enabled}>{pending ? "Saving finding…" : parentVersion ? "Save new finding version" : "Save finding"}</button><button type="button" disabled={pending} onClick={onCancel}>Cancel editor</button></div>
    </form>}
  </section>;
}
