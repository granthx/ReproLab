"use client";

import { useEffect, useId, useState } from "react";
import { recordsApi, type Claim, type FindingSummary, type Report, type ReportEvent, type ReportVersion, type Scientist } from "../../../lib/api";
import ReportComposer from "./ReportComposer";
import ReportPreview from "./ReportPreview";
import ReportLifecycle from "./ReportLifecycle";
import ReportExports from "./ReportExports";

export type ReportsSectionProps = {
  investigationId: string;
  findings: FindingSummary[];
  claims: Claim[];
  scientists: Scientist[];
  reviewRevision?: number;
  enabled?: boolean;
};

function latestVersion(report: Report) {
  return report.versions.reduce<ReportVersion | undefined>((latest, version) => !latest || version.version_number > latest.version_number ? version : latest, undefined);
}

function mergeReport(current: Report | undefined, incoming: Report): Report {
  const events = Array.from(new Map([...(current?.events ?? []), ...incoming.events].map((event) => [event.id, event])).values()).sort((a, b) => a.sequence_number - b.sequence_number);
  const versions = Array.from(new Map([...(current?.versions ?? []), ...incoming.versions].map((version) => [version.id, version])).values()).sort((a, b) => a.version_number - b.version_number);
  const last = events[events.length - 1];
  const status = incoming.status === "withdrawn" || current?.status === "withdrawn" || last?.event_type === "withdrawn" ? "withdrawn"
    : incoming.status === "published" || current?.status === "published" || last?.event_type === "published" ? "published" : incoming.status;
  return { ...incoming, status, versions, events };
}

export default function ReportsSection({ enabled = true, ...props }: ReportsSectionProps) {
  if (!enabled) return <section className="records-panel" aria-label="Reports"><h3>Reports</h3><p className="records-note">Analysis/record reports are unavailable for this workspace.</p></section>;
  return <ReportsWorkspace key={props.investigationId} {...props} />;
}

function ReportsWorkspace({ investigationId, findings, claims, scientists, reviewRevision }: Omit<ReportsSectionProps, "enabled">) {
  const headingId = useId();
  const [reports, setReports] = useState<Report[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [revision, setRevision] = useState(0);
  const [listPending, setListPending] = useState(true);
  const [listError, setListError] = useState("");
  const [detailPending, setDetailPending] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [success, setSuccess] = useState("");
  const [composer, setComposer] = useState<{ report?: Report; parentVersion?: ReportVersion } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setListPending(true); setListError("");
    recordsApi.reports(investigationId, controller.signal).then((rows) => {
      if (controller.signal.aborted) return;
      setReports((current) => rows.map((row) => mergeReport(current.find((item) => item.id === row.id), row)));
      setSelectedId((current) => rows.some((row) => row.id === current) ? current : rows[0]?.id ?? "");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setListError(reason instanceof Error ? reason.message : "Could not load reports.");
    }).finally(() => { if (!controller.signal.aborted) setListPending(false); });
    return () => controller.abort();
  }, [investigationId, revision]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    setDetailPending(true); setDetailError("");
    recordsApi.report(investigationId, selectedId, controller.signal).then((row) => {
      if (!controller.signal.aborted) setReports((current) => current.map((item) => item.id === row.id ? mergeReport(item, row) : item));
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setDetailError(reason instanceof Error ? reason.message : "Could not refresh selected report.");
    }).finally(() => { if (!controller.signal.aborted) setDetailPending(false); });
    return () => controller.abort();
  }, [investigationId, selectedId, revision]);

  const report = reports.find((row) => row.id === selectedId);
  const latest = report ? latestVersion(report) : undefined;
  const version = selectedVersionId ? report?.versions.find((row) => row.id === selectedVersionId) : latest;
  const composerReport = composer?.report ? reports.find((row) => row.id === composer.report?.id) ?? composer.report : undefined;

  useEffect(() => {
    // Pin the initial choice once per report. A refresh discovering a newer
    // version must not change the publication target or discard lifecycle input.
    if (report) setSelectedVersionId((current) => report.versions.some((item) => item.id === current) ? current : latestVersion(report)?.id ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  function refreshed(row: Report) {
    setReports((current) => current.map((item) => item.id === row.id ? mergeReport(item, row) : item));
  }

  function saved(row: Report, persisted: ReportVersion) {
    setReports((current) => current.some((item) => item.id === row.id) ? current.map((item) => item.id === row.id ? mergeReport(item, row) : item) : [...current, row]);
    setSelectedId(row.id); setSelectedVersionId(persisted.id);
    setSuccess(`Saved report version ${persisted.version_number} (${persisted.id}).`);
    setRevision((value) => value + 1);
  }

  function eventRecorded(event: ReportEvent) {
    setReports((current) => current.map((row) => row.id === event.report_id ? {
      ...row, status: event.event_type === "withdrawn" ? "withdrawn" : "published",
      events: [...row.events.filter((item) => item.id !== event.id), event],
    } : row));
    setSuccess(`Recorded ${event.event_type} event ${event.id} for version ${event.report_version_id}.`);
    setRevision((value) => value + 1);
  }

  return <section className="records-panel" aria-labelledby={headingId}>
    <div className="records-row"><h3 id={headingId}>Analysis/record reports</h3><div className="records-actions"><button type="button" disabled={Boolean(composer)} onClick={() => { setComposer({}); setSuccess(""); }}>New report</button><button type="button" disabled={listPending || detailPending} onClick={() => setRevision((value) => value + 1)}>{listPending ? "Refreshing reports…" : "Refresh reports"}</button></div></div>
    <p className="records-note">Immutable source-analysis versions with manually recorded publication and withdrawal events.</p>
    {success && <p className="records-success" role="status">{success}</p>}
    {listError && <p className="records-error" role="alert">Report list refresh failed: {listError}{success ? " The action above succeeded; its persisted response remains available." : ""}</p>}
    {detailError && <p className="records-error" role="alert">Selected report refresh failed: {detailError}{success ? " The saved action succeeded." : ""}</p>}
    {listPending && !reports.length && <p className="records-note" role="status">Loading reports…</p>}
    {!listPending && !listError && !reports.length && <p className="records-note">No reports saved. Create a report to choose scope and exact finding versions.</p>}
    {reports.length > 0 && <div className="records-row">
      <label>Report<select value={selectedId} disabled={Boolean(composer)} onChange={(event) => { setSelectedId(event.target.value); setSelectedVersionId(""); setSuccess(""); }}>{reports.map((row) => <option key={row.id} value={row.id}>{latestVersion(row)?.title ?? row.id} · {row.status}</option>)}</select></label>
      {report && <label>Saved version<select value={version?.id ?? ""} disabled={Boolean(composer)} onChange={(event) => setSelectedVersionId(event.target.value)}>{[...report.versions].sort((a, b) => b.version_number - a.version_number).map((item) => <option key={item.id} value={item.id}>v{item.version_number} · {item.title}{item.id === latest?.id ? " · latest saved" : ""}</option>)}</select></label>}
    </div>}
    {composer && <ReportComposer key={composer.parentVersion?.id ?? "new"} investigationId={investigationId} findings={findings} claims={claims} scientists={scientists} report={composerReport} parentVersion={composer.parentVersion} onSaved={saved} onClose={() => setComposer(null)} />}
    {report && version && <>
      <p className="records-meta">Report {report.id} · overall lifecycle: <strong>{report.status}</strong> · viewing saved version {version.version_number}{version.id !== latest?.id ? " (older saved version)" : ""}</p>
      <div className="records-actions"><button type="button" disabled={Boolean(composer) || detailPending || report.status !== "draft" || version.id !== latest?.id} onClick={() => setComposer({ report, parentVersion: version })}>Revise latest saved version</button></div>
      {report.status !== "draft" && <p className="records-note">This {report.status} report is read-only.</p>}
      <ReportPreview version={version} />
      <ReportLifecycle key={`${report.id}:${version.id}`} investigationId={investigationId} report={report} version={version} scientists={scientists} reviewRevision={reviewRevision} onEvent={eventRecorded} onRefresh={refreshed} />
      <ReportExports key={`${report.id}:${version.id}`} investigationId={investigationId} report={report} version={version} />
    </>}
  </section>;
}
