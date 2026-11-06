"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { recordsApi, type AttributionInput, type Claim, type Finding, type FindingSummary, type Report, type ReportDefinition, type ReportSelection, type ReportVersion, type Scientist } from "../../../lib/api";
import AttributionFields, { emptyAttribution } from "./AttributionFields";

export type ReportComposerProps = {
  investigationId: string;
  findings: FindingSummary[];
  claims: Claim[];
  scientists: Scientist[];
  report?: Report;
  parentVersion?: ReportVersion;
  onSaved: (report: Report, version: ReportVersion) => void;
  onClose: () => void;
};

function definitionFrom(version?: ReportVersion): ReportDefinition {
  return version ? {
    report_kind: "analysis_record", title: version.title,
    scope_claim_ids: [...version.scope_claim_ids],
    finding_links: version.finding_links.map((link) => ({
      finding_version_id: link.finding_version_id, finding_content_hash: link.finding_content_hash,
      section: link.section, position: link.position,
      disposition: link.disposition as ReportSelection["disposition"], exclusion_reason: link.exclusion_reason,
    })),
    limitations: [...version.limitations], unresolved_questions: [...version.unresolved_questions],
  } : { report_kind: "analysis_record", title: "", scope_claim_ids: [], finding_links: [], limitations: [], unresolved_questions: [] };
}

const message = (reason: unknown) => reason instanceof Error ? reason.message : "The request failed.";
const lines = (value: string) => value.split("\n").map((line) => line.trim()).filter(Boolean);

export default function ReportComposer({ investigationId, findings, claims, scientists, report, parentVersion, onSaved, onClose }: ReportComposerProps) {
  const [draft, setDraft] = useState<ReportDefinition>(() => definitionFrom(parentVersion));
  const [limitations, setLimitations] = useState(() => parentVersion?.limitations.join("\n") ?? "");
  const [questions, setQuestions] = useState(() => parentVersion?.unresolved_questions.join("\n") ?? "");
  const [attribution, setAttribution] = useState<AttributionInput>(emptyAttribution);
  const [findingId, setFindingId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [histories, setHistories] = useState<Record<string, Finding>>({});
  const [historyPending, setHistoryPending] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historyRevision, setHistoryRevision] = useState(0);
  const [pickError, setPickError] = useState("");
  const [savePending, setSavePending] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [staleReason, setStaleReason] = useState("");
  const saving = useRef(false);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!findingId) return;
    const controller = new AbortController();
    setHistoryPending(true); setHistoryError("");
    recordsApi.finding(investigationId, findingId, controller.signal).then((finding) => {
      if (!controller.signal.aborted) setHistories((current) => ({ ...current, [findingId]: finding }));
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setHistoryError(message(reason));
    }).finally(() => { if (!controller.signal.aborted) setHistoryPending(false); });
    return () => controller.abort();
  }, [investigationId, findingId, historyRevision]);

  const latest = report?.versions.reduce<ReportVersion | undefined>((current, item) => !current || item.version_number > current.version_number ? item : current, undefined);
  const readOnlyReason = staleReason || (report && (report.status !== "draft" || !parentVersion || parentVersion.id !== latest?.id)
    ? "Revisions require a draft report and its latest saved version as parent. This draft is read-only; close and reopen from the latest version." : "");
  const disabled = savePending || Boolean(readOnlyReason);
  const history = findingId ? histories[findingId] : undefined;
  const candidate = history?.versions.find((item) => item.id === versionId);

  function updateLink(index: number, change: Partial<ReportSelection>) {
    setDraft((current) => ({ ...current, finding_links: current.finding_links.map((link, at) => at === index ? { ...link, ...change } : link) }));
  }

  function addSelection() {
    setPickError("");
    if (!candidate || historyPending || historyError) { setPickError("Choose an exact saved finding version from a loaded history."); return; }
    if (draft.finding_links.some((link) => link.finding_version_id === candidate.id)) { setPickError("That exact finding version is already selected. Distinct versions of the same finding may be selected explicitly."); return; }
    setDraft((current) => ({ ...current, finding_links: [...current.finding_links, {
      finding_version_id: candidate.id, finding_content_hash: candidate.content_hash,
      section: "", position: 0, disposition: "included", exclusion_reason: null,
    }] }));
    setVersionId("");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving.current || readOnlyReason) return;
    setSaveError("");
    const version: ReportDefinition = { ...draft, limitations: lines(limitations), unresolved_questions: lines(questions) };
    const versions = new Set<string>();
    const positions = new Set<string>();
    let invalid = !version.title.trim() ? "A nonblank title is required." : "";
    if (!attribution.recorder_label.trim() || (attribution.associated_role_id && !attribution.role_association_note?.trim())) invalid = "Record human attribution and a role association note when a role is selected.";
    for (const link of version.finding_links) {
      if (!link.section.trim() || link.section.length > 120 || !Number.isSafeInteger(link.position) || link.position < 0) invalid = "Each selection needs a nonblank section (at most 120 characters) and an integer position of zero or greater.";
      if (!/^[0-9a-f]{64}$/.test(link.finding_content_hash)) invalid = "Each selection must pin an exact saved finding hash.";
      if (link.disposition === "excluded_with_reason" && !link.exclusion_reason?.trim()) invalid = "Every excluded selection needs a reason.";
      if (versions.has(link.finding_version_id)) invalid = "The same finding version cannot be selected twice.";
      const position = JSON.stringify([link.section, link.position]);
      if (positions.has(position)) invalid = "Section and position pairs must be unique.";
      versions.add(link.finding_version_id); positions.add(position);
    }
    if (invalid) { setSaveError(invalid); return; }
    saving.current = true; setSavePending(true);
    const signal = lifetime.current?.signal;
    let savedReport: Report;
    let savedVersion: ReportVersion;
    try {
      if (report && parentVersion) {
        const fresh = await recordsApi.report(investigationId, report.id, signal);
        const freshLatest = fresh.versions.reduce<ReportVersion | undefined>((current, item) => !current || item.version_number > current.version_number ? item : current, undefined);
        if (fresh.status !== "draft" || freshLatest?.id !== parentVersion.id) {
          const reason = "The report is no longer a draft with this latest parent. Your unsaved draft is preserved; close and reopen the latest version before revising.";
          setStaleReason(reason); throw new Error(reason);
        }
        savedVersion = await recordsApi.createReportVersion(investigationId, report.id, { attribution, parent_version_id: parentVersion.id, version });
        savedReport = { ...fresh, versions: [...fresh.versions, savedVersion] };
      } else {
        savedReport = await recordsApi.createReport(investigationId, { attribution, version });
        const persisted = savedReport.versions.reduce<ReportVersion | undefined>((current, item) => !current || item.version_number > current.version_number ? item : current, undefined);
        if (!persisted) throw new Error("The save response did not contain a persisted report version. Refresh reports before retrying.");
        savedVersion = persisted;
      }
    } catch (reason) {
      if (!signal?.aborted) { setSaveError(message(reason)); setSavePending(false); }
      saving.current = false;
      return;
    }
    saving.current = false;
    if (signal?.aborted) return;
    // The persisted response is handed off before any optional parent refresh.
    onSaved(savedReport, savedVersion);
    onClose();
  }

  return <section className="records-panel" aria-label="Report composer">
    <h4>{report ? `Revise report from version ${parentVersion?.version_number}` : "New analysis/record report"}</h4>
    <p className="records-note">Choose scope and exact saved finding versions explicitly. Findings are never automatically added or upgraded.</p>
    {readOnlyReason && <p className="records-note" role="status">{readOnlyReason}</p>}
    <form className="records-form" onSubmit={save}>
      <fieldset disabled={disabled}>
        <legend>Report definition</legend>
        <label>Title<input value={draft.title} maxLength={500} required onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} /></label>
        <fieldset><legend>Scope claims</legend>
          {!claims.length && <p className="records-note">No claims available. An empty scope can be saved explicitly.</p>}
          {claims.map((claim) => <label className="records-row" key={claim.id}><input type="checkbox" checked={draft.scope_claim_ids.includes(claim.id)} onChange={(event) => setDraft((current) => ({ ...current, scope_claim_ids: event.target.checked ? [...current.scope_claim_ids, claim.id] : current.scope_claim_ids.filter((id) => id !== claim.id) }))} />{claim.statement} <span className="records-meta">{claim.id}</span></label>)}
          {draft.scope_claim_ids.filter((id) => !claims.some((claim) => claim.id === id)).map((id) => <label className="records-row" key={id}><input type="checkbox" checked onChange={() => setDraft((current) => ({ ...current, scope_claim_ids: current.scope_claim_ids.filter((item) => item !== id) }))} />Previously scoped claim: {id}</label>)}
        </fieldset>
        <fieldset><legend>Add an exact finding version</legend>
          <label>Finding<select value={findingId} onChange={(event) => { setFindingId(event.target.value); setVersionId(""); setPickError(""); }}><option value="">Choose a finding</option>{findings.map((finding) => <option value={finding.id} key={finding.id}>{finding.title} · latest v{finding.latest_version_number}</option>)}</select></label>
          {historyPending && <p className="records-note" role="status">Loading finding version history…</p>}
          {historyError && <div className="records-error" role="alert">History load failed: {historyError} <button type="button" onClick={() => setHistoryRevision((value) => value + 1)}>Retry history</button></div>}
          <label>Saved version<select value={versionId} disabled={!history || historyPending || Boolean(historyError)} onChange={(event) => setVersionId(event.target.value)}><option value="">Choose an exact version</option>{[...(history?.versions ?? [])].sort((a, b) => b.version_number - a.version_number).map((version) => <option value={version.id} key={version.id}>v{version.version_number} · {version.finding.title} · {version.content_hash}</option>)}</select></label>
          {candidate && <p className="records-hash">Selected finding version {candidate.id} · SHA-256 {candidate.content_hash}</p>}
          <button type="button" disabled={!candidate || historyPending || Boolean(historyError) || draft.finding_links.length >= 500} onClick={addSelection}>Add selected version</button>
          {pickError && <p className="records-error" role="alert">{pickError}</p>}
        </fieldset>
        <h5>Selected findings ({draft.finding_links.length})</h5>
        {!draft.finding_links.length && <p className="records-note">No findings selected. Drafts may be empty; publication requires at least one included finding.</p>}
        {draft.finding_links.map((link, index) => {
          const pinned = parentVersion?.canonical_content_json.source_context?.findings.find((item) => item.finding_version_id === link.finding_version_id);
          const loaded = Object.values(histories).find((finding) => finding.versions.some((version) => version.id === link.finding_version_id));
          const loadedVersion = loaded?.versions.find((version) => version.id === link.finding_version_id);
          const summary = findings.find((finding) => finding.id === (pinned?.finding_id ?? loaded?.id));
          const historyLatest = loaded?.versions.reduce<(typeof loaded.versions)[number] | undefined>((latest, item) => !latest || item.version_number > latest.version_number ? item : latest, undefined);
          const newestNumber = Math.max(summary?.latest_version_number ?? 0, historyLatest?.version_number ?? 0);
          const newerAvailable = loadedVersion ? newestNumber > loadedVersion.version_number : summary && summary.latest_version_id !== link.finding_version_id;
          return <fieldset className="records-card" key={link.finding_version_id}>
            <legend>Selection {index + 1}: {pinned?.finding.title ?? loaded?.versions.find((version) => version.id === link.finding_version_id)?.finding.title ?? link.finding_version_id}</legend>
            <p className="records-meta">Exact version: {link.finding_version_id}</p><p className="records-hash">Finding SHA-256: {link.finding_content_hash}</p>
            {newerAvailable && <p className="records-note">Newer finding available (v{newestNumber}). This selection remains pinned; choose another version explicitly to change it.</p>}
            <div className="records-row"><label>Section<input value={link.section} maxLength={120} required onChange={(event) => updateLink(index, { section: event.target.value })} /></label><label>Position<input type="number" min={0} step={1} required value={Number.isNaN(link.position) ? "" : link.position} onChange={(event) => updateLink(index, { position: event.target.value === "" ? NaN : Number(event.target.value) })} /></label></div>
            <label>Disposition<select value={link.disposition} onChange={(event) => updateLink(index, { disposition: event.target.value as ReportSelection["disposition"], exclusion_reason: event.target.value === "included" ? null : "" })}><option value="included">Included</option><option value="excluded_with_reason">Excluded with reason</option></select></label>
            {link.disposition === "excluded_with_reason" && <label>Exclusion reason<textarea required maxLength={5000} value={link.exclusion_reason ?? ""} onChange={(event) => updateLink(index, { exclusion_reason: event.target.value })} /></label>}
            <button type="button" onClick={() => setDraft((current) => ({ ...current, finding_links: current.finding_links.filter((_, at) => at !== index) }))}>Remove selection {index + 1}</button>
          </fieldset>;
        })}
        <label>Report limitations (one per line)<textarea value={limitations} onChange={(event) => setLimitations(event.target.value)} /></label>
        <label>Unresolved questions (one per line)<textarea value={questions} onChange={(event) => setQuestions(event.target.value)} /></label>
        <AttributionFields value={attribution} onChange={setAttribution} scientists={scientists} disabled={disabled} />
      </fieldset>
      <details className="records-card"><summary>Unsaved draft summary</summary><p>Title: {draft.title || "Untitled"}</p><p>Scope claims: {draft.scope_claim_ids.length} · exact finding selections: {draft.finding_links.length} · included: {draft.finding_links.filter((link) => link.disposition === "included").length}</p><p className="records-note">Unsaved definition only. Canonical source snapshots and report integrity metadata are returned after persistence.</p></details>
      {saveError && <p className="records-error" role="alert">Save failed: {saveError}</p>}
      <div className="records-actions"><button type="submit" disabled={disabled}>{savePending ? "Saving report…" : "Save report version"}</button><button type="button" onClick={onClose} disabled={savePending}>Cancel</button></div>
    </form>
  </section>;
}
