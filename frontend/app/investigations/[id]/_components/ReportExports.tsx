"use client";

import { useEffect, useRef, useState } from "react";
import { downloadReportExport, recordsApi, type Report, type ReportExport, type ReportVersion } from "../../../lib/api";

export type ReportExportsProps = { investigationId: string; report: Report; version: ReportVersion };
type Format = "json" | "markdown";
type DownloadState = { pending: boolean; error: string; success: string };

function failure(reason: unknown) {
  const text = reason instanceof Error ? reason.message : "The export request failed.";
  const status = typeof reason === "object" && reason !== null && "status" in reason ? reason.status : undefined;
  if (status === 409) return `Integrity conflict (409): ${text}`;
  if (status === 413) return `Export too large (413): each format is limited to 2 MiB. ${text}`;
  return text;
}

export default function ReportExports({ investigationId, report, version }: ReportExportsProps) {
  const [exports, setExports] = useState<ReportExport[]>([]);
  const [revision, setRevision] = useState(0);
  const [listPending, setListPending] = useState(true);
  const [listError, setListError] = useState("");
  const [createPending, setCreatePending] = useState(false);
  const [createError, setCreateError] = useState("");
  const [createSuccess, setCreateSuccess] = useState("");
  const [downloads, setDownloads] = useState<Record<string, DownloadState>>({});
  const downloadLocks = useRef(new Set<string>());
  const createLock = useRef(false);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setListPending(true); setListError("");
    recordsApi.exports(investigationId, report.id, version.id, controller.signal).then((rows) => {
      if (!controller.signal.aborted) setExports(rows);
    }).catch((reason: unknown) => { if (!controller.signal.aborted) setListError(failure(reason)); })
      .finally(() => { if (!controller.signal.aborted) setListPending(false); });
    return () => controller.abort();
  }, [investigationId, report.id, version.id, revision]);

  function metadataError(item: ReportExport) {
    if (item.investigation_id !== investigationId || item.report_version_id !== version.id) return "Export metadata belongs to a different investigation or report version.";
    if (item.report_content_hash !== version.content_hash) return "Export report hash does not match this saved report version. Downloads are blocked.";
    return "";
  }

  async function create() {
    if (createLock.current || exports.length || listPending || listError) return;
    createLock.current = true; setCreatePending(true); setCreateError(""); setCreateSuccess("");
    const signal = lifetime.current?.signal;
    try {
      const item = await recordsApi.createExport(investigationId, report.id, version.id);
      if (signal?.aborted) return;
      const invalid = metadataError(item);
      if (invalid) throw new Error(`The returned export metadata could not be accepted: ${invalid} Refresh the stored export list before retrying.`);
      setExports((current) => [...current.filter((row) => row.id !== item.id), item]);
      setCreateSuccess(`Stored JSON/Markdown pair ${item.id} is available. Repeating creation on the server returns this same pair.`);
      setRevision((value) => value + 1);
    } catch (reason) { if (!signal?.aborted) setCreateError(failure(reason)); }
    finally { createLock.current = false; if (!signal?.aborted) setCreatePending(false); }
  }

  async function download(item: ReportExport, format: Format) {
    const key = `${item.id}:${format}`;
    if (downloadLocks.current.has(key)) return;
    const invalid = metadataError(item);
    if (invalid) { setDownloads((current) => ({ ...current, [key]: { pending: false, error: invalid, success: "" } })); return; }
    downloadLocks.current.add(key);
    setDownloads((current) => ({ ...current, [key]: { pending: true, error: "", success: "" } }));
    const signal = lifetime.current?.signal;
    try {
      await downloadReportExport(investigationId, report.id, item, format, signal);
      if (!signal?.aborted) setDownloads((current) => ({ ...current, [key]: { pending: false, error: "", success: "Byte length and SHA-256 verified; download started." } }));
    } catch (reason) {
      if (!signal?.aborted) setDownloads((current) => ({ ...current, [key]: { pending: false, error: failure(reason), success: "" } }));
    } finally { downloadLocks.current.delete(key); }
  }

  return <section className="records-panel" aria-label="Stored report exports">
    <h4>Stored exports for saved version {version.version_number}</h4>
    <p className="records-note">Listing exports only reads metadata. Creating the JSON/Markdown pair is an explicit action, stored once per version. Downloads use the stored bytes and verify their length and SHA-256 before starting an attachment download.</p>
    <p className="records-hash">Report SHA-256: {version.content_hash}</p>
    <p className="records-note">Exports are immutable analysis/record snapshots. They do not contain current publication status; consult the append-only lifecycle events.</p>
    {report.status === "withdrawn" && <p className="records-note" role="status">This report is withdrawn. Previously stored exports remain available as historical records; downloading one does not restore publication.</p>}
    <div className="records-actions">
      <button type="button" disabled={listPending || createPending} onClick={() => setRevision((value) => value + 1)}>{listPending ? "Loading export metadata…" : "Refresh export list"}</button>
      <button type="button" disabled={listPending || createPending || Boolean(listError) || exports.length > 0} onClick={() => void create()}>{createPending ? "Creating stored export pair…" : exports.length ? "Stored pair already exists" : "Create stored JSON + Markdown pair"}</button>
    </div>
    {listError && <p className="records-error" role="alert">Export list refresh failed: {listError}{createSuccess ? " Export creation succeeded; the returned metadata is preserved below." : ""}</p>}
    {createError && <p className="records-error" role="alert">Export creation failed: {createError}</p>}
    {createSuccess && <p className="records-success" role="status">{createSuccess}</p>}
    {!listPending && !listError && !exports.length && <p className="records-note">No stored exports for this version. Create the pair explicitly to make verified downloads available.</p>}
    {exports.length > 1 && <p className="records-error" role="alert">More than one stored export pair was returned for this version. Refresh and investigate the metadata; only one pair per version is expected.</p>}
    {exports.map((item) => {
      const invalid = metadataError(item);
      return <article className="records-card" key={item.id}>
        <h5>Export pair {item.id}</h5>
        <p className="records-meta">Version: {item.report_version_id} · Created: {item.created_at}</p>
        <p className="records-hash">Pinned report SHA-256: {item.report_content_hash}</p>
        {invalid && <p className="records-error" role="alert">{invalid}</p>}
        {(["json", "markdown"] as const).map((format) => {
          const key = `${item.id}:${format}`;
          const state = downloads[key];
          const label = format === "json" ? "JSON" : "Markdown";
          const size = format === "json" ? item.json_size_bytes : item.markdown_size_bytes;
          const hash = format === "json" ? item.json_sha256 : item.markdown_sha256;
          return <div className="records-card" key={format}>
            <p className="records-meta">{label} · {size} bytes</p><p className="records-hash">{label} SHA-256: {hash}</p>
            <button type="button" aria-label={`Verify and download ${label} export ${item.id} for report version ${version.version_number}`} disabled={Boolean(invalid) || state?.pending} onClick={() => void download(item, format)}>{state?.pending ? `Verifying ${label} bytes…` : `Verify and download ${label}`}</button>
            {state?.error && <p className="records-error" role="alert">{label} download failed: {state.error}</p>}
            {state?.success && <p className="records-success" role="status">{label}: {state.success}</p>}
          </div>;
        })}
      </article>;
    })}
  </section>;
}
