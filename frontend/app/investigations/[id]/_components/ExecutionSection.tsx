"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  executionApi,
  type ExperimentJob,
  type Protocol,
  type Scientist,
} from "../../../lib/api";
import {
  StatusBadge,
  chainStatus,
  formatTime,
  humanize,
  shortId,
} from "./GovernanceStatus";

type Props = {
  investigationId: string;
  protocols: Protocol[];
  enabled?: boolean;
  onChanged?: () => void;
};

export default function ExecutionSection(props: Props) {
  return <ExecutionWorkspace key={props.investigationId} {...props} />;
}

function ExecutionWorkspace({
  investigationId,
  protocols,
  enabled = true,
  onChanged,
}: Props) {
  const headingId = useId();
  const [jobs, setJobs] = useState<ExperimentJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [cancellingId, setCancellingId] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [openJobId, setOpenJobId] = useState<string>("");
  const [streamOpenJobs, setStreamOpenJobs] = useState<Record<string, boolean>>({});
  const [revision, setRevision] = useState(0);

  // Form states
  const frozenProtocols = useMemo(
    () => protocols.filter((p) => p.status === "frozen"),
    [protocols]
  );
  const [selectedProtocolId, setSelectedProtocolId] = useState<string>("");
  const [submissionKey, setSubmissionKey] = useState<string>("");
  const [recorderId, setRecorderId] = useState("operator-1");
  const [recorderLabel, setRecorderLabel] = useState("Execution operator");

  useEffect(() => {
    if (frozenProtocols.length > 0 && !selectedProtocolId) {
      setSelectedProtocolId(frozenProtocols[0].id);
    }
  }, [frozenProtocols, selectedProtocolId]);

  useEffect(() => {
    setSubmissionKey(`job-${Date.now().toString(36)}`);
  }, [revision]);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    executionApi
      .jobs(investigationId, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) {
          setJobs(rows);
          if (rows.length > 0 && !openJobId) {
            setOpenJobId(rows[rows.length - 1].id);
          }
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load experiment jobs."
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [investigationId, enabled, revision]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProtocolId || !submissionKey) return;
    setSubmitting(true);
    setActionError("");
    try {
      const created = await executionApi.submit(investigationId, {
        protocol_version_id: selectedProtocolId,
        submission_key: submissionKey.trim(),
        attribution: {
          recorder_id: recorderId.trim() || "operator-1",
          recorder_label: recorderLabel.trim() || "Execution operator",
        },
      });
      setOpenJobId(created.id);
      setRevision((v) => v + 1);
      onChanged?.();
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to submit experiment job."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (job: ExperimentJob) => {
    if (!cancelReason.trim()) return;
    setCancellingId(job.id);
    setActionError("");
    try {
      await executionApi.cancel(investigationId, job.id, {
        expected_lifecycle_version: job.lifecycle_version,
        reason: cancelReason.trim(),
        attribution: {
          recorder_id: recorderId.trim() || "operator-1",
          recorder_label: recorderLabel.trim() || "Execution operator",
        },
      });
      setCancelReason("");
      setRevision((v) => v + 1);
      onChanged?.();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to cancel job."
      );
    } finally {
      setCancellingId("");
    }
  };

  return (
    <section className="records-panel" aria-labelledby={headingId}>
      <div className="records-row">
        <div>
          <h3 id={headingId}>Isolated experiment execution &amp; production scorer</h3>
          <p className="records-note">
            Stage 6 offline, hermetic runner environment with zero network access and credential isolation.
            Metrics are independently recomputed by trusted scorers from ingested artifacts, never accepted from raw self-reports.
          </p>
        </div>
        <div className="records-actions">
          <button
            type="button"
            disabled={loading}
            onClick={() => setRevision((v) => v + 1)}
          >
            {loading ? "Refreshing jobs…" : "Refresh jobs"}
          </button>
        </div>
      </div>

      {error && (
        <p className="records-error" role="alert">
          {error}
        </p>
      )}
      {actionError && (
        <p className="records-error" role="alert">
          {actionError}
        </p>
      )}

      {/* Submission Form */}
      <div className="gov-action-panel mt-4">
        <h4>Submit experiment job</h4>
        {frozenProtocols.length === 0 ? (
          <p className="records-note">
            No frozen protocols available in this investigation. In accordance with ReproLab governance,
            experiment jobs may only be launched against <strong>frozen protocols</strong>.
            Review and freeze a protocol in the Protocols section to execute jobs.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="gov-form">
            <div className="gov-form-grid">
              <label>
                <span>Frozen Protocol</span>
                <select
                  value={selectedProtocolId}
                  onChange={(e) => setSelectedProtocolId(e.target.value)}
                  disabled={submitting}
                >
                  {frozenProtocols.map((p) => (
                    <option key={p.id} value={p.id}>
                      Protocol v{p.version_number} ({p.protocol?.experiment_type || shortId(p.id)})
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Submission Key (Idempotency)</span>
                <input
                  type="text"
                  value={submissionKey}
                  onChange={(e) => setSubmissionKey(e.target.value)}
                  disabled={submitting}
                  required
                />
              </label>

              <label>
                <span>Recorder ID</span>
                <input
                  type="text"
                  value={recorderId}
                  onChange={(e) => setRecorderId(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <label>
                <span>Recorder Label</span>
                <input
                  type="text"
                  value={recorderLabel}
                  onChange={(e) => setRecorderLabel(e.target.value)}
                  disabled={submitting}
                />
              </label>
            </div>

            <div className="records-actions mt-3">
              <button
                type="submit"
                disabled={submitting || !selectedProtocolId || !submissionKey}
                className="gov-primary-btn"
              >
                {submitting ? "Executing in hermetic sandbox…" : "Run isolated experiment"}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Jobs List */}
      <div className="gov-section-group mt-6">
        <h4>Recorded experiment jobs ({jobs.length})</h4>
        {!loading && jobs.length === 0 && (
          <p className="records-note">No experiment jobs submitted yet.</p>
        )}

        <div className="space-y-4 mt-3">
          {jobs.map((job) => {
            const isOpen = openJobId === job.id;
            return (
              <div key={job.id} className="gov-card">
                <div
                  className="gov-card-header cursor-pointer flex justify-between items-center"
                  onClick={() => setOpenJobId(isOpen ? "" : job.id)}
                >
                  <div className="flex items-center gap-3">
                    <StatusBadge status={job.status} />
                    <span className="font-semibold text-sm">
                      {job.submission_key}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      ID: {shortId(job.id)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      Protocol: {shortId(job.protocol_version_id)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isOpen) setOpenJobId(job.id);
                        setStreamOpenJobs((prev) => ({ ...prev, [job.id]: !prev[job.id] }));
                      }}
                      className="text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-2.5 py-1 rounded border border-zinc-700"
                    >
                      {streamOpenJobs[job.id] ? "Hide Live Terminal" : "Stream Logs (SSE)"}
                    </button>
                    <span className="text-xs text-muted-foreground">
                      {formatTime(job.created_at)}
                    </span>
                    <button
                      type="button"
                      className="text-xs text-primary underline"
                    >
                      {isOpen ? "Hide details" : "View details"}
                    </button>
                  </div>
                </div>

                {isOpen && (
                  <div className="gov-card-body border-t mt-3 pt-3">
                    {/* Job Metadata */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs mb-4">
                      <div>
                        <span className="text-muted-foreground block">
                          Execution Bundle Hash
                        </span>
                        <code className="text-[11px]">
                          {shortId(job.execution_bundle_hash)}
                        </code>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">
                          Lifecycle Version
                        </span>
                        <span>{job.lifecycle_version}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">
                          Attempts Recorded
                        </span>
                        <span>{job.attempts?.length || 0}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">
                          Measurements Recorded
                        </span>
                        <span>{job.measurements?.length || 0}</span>
                      </div>
                    </div>

                    {/* Live SSE Streaming Terminal */}
                    {streamOpenJobs[job.id] && (
                      <LiveStreamingTerminal
                        investigationId={investigationId}
                        jobId={job.id}
                      />
                    )}

                    {/* Cancellation UI for active jobs */}
                    {["queued", "running"].includes(job.status) && (
                      <div className="gov-cancellation-box p-3 bg-red-500/10 border border-red-500/20 rounded mb-4">
                        <span className="text-xs font-semibold block mb-1">
                          Cancel active experiment job
                        </span>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            placeholder="Reason for cancellation…"
                            value={cancelReason}
                            onChange={(e) => setCancelReason(e.target.value)}
                            className="text-xs flex-1"
                          />
                          <button
                            type="button"
                            onClick={() => handleCancel(job)}
                            disabled={cancellingId === job.id || !cancelReason.trim()}
                            className="text-xs bg-red-600 text-white px-3 py-1 rounded"
                          >
                            {cancellingId === job.id ? "Cancelling…" : "Cancel job"}
                          </button>
                        </div>
                      </div>
                    )}

                    {job.cancellation_reason && (
                      <p className="text-xs text-red-500 mb-4">
                        <strong>Cancellation reason:</strong> {job.cancellation_reason}
                      </p>
                    )}

                    {/* Production Measurements */}
                    {job.measurements && job.measurements.length > 0 && (
                      <div className="gov-measurements mb-4">
                        <h5 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                          Production Scorer Measurements (Wilson Score Interval)
                        </h5>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {job.measurements.map((m) => (
                            <div
                              key={m.id}
                              className="p-3 bg-card border rounded text-xs"
                            >
                              <div className="flex justify-between items-center mb-1">
                                <span className="font-semibold capitalize">
                                  {m.metric_name}
                                </span>
                                <span className="font-mono text-sm font-bold text-primary">
                                  {(m.value * 100).toFixed(1)}%
                                </span>
                              </div>
                              <div className="space-y-1 text-muted-foreground">
                                <div>
                                  <strong>95% Confidence Interval:</strong> [
                                  {(m.interval_lower * 100).toFixed(2)}%,{" "}
                                  {(m.interval_upper * 100).toFixed(2)}%]
                                </div>
                                <div>
                                  <strong>Sample size:</strong> {m.sample_size} (
                                  {m.analysis_unit})
                                </div>
                                <div>
                                  <strong>Scorer:</strong> {m.scorer_version}
                                </div>
                                <div>
                                  <strong>Prediction SHA-256:</strong>{" "}
                                  <code>{shortId(m.prediction_artifact_sha256)}</code>
                                </div>
                                <div>
                                  <strong>Manifest SHA-256:</strong>{" "}
                                  <code>{shortId(m.manifest_artifact_sha256)}</code>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Attempt Records */}
                    {job.attempts && job.attempts.length > 0 && (
                      <div className="gov-attempts mb-4">
                        <h5 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                          Execution Attempts
                        </h5>
                        <div className="space-y-3">
                          {job.attempts.map((att) => (
                            <div
                              key={att.id}
                              className="p-3 bg-card border rounded text-xs"
                            >
                              <div className="flex justify-between items-center mb-2">
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold">
                                    Attempt #{att.attempt_number}
                                  </span>
                                  <StatusBadge status={att.status} />
                                  {att.exit_code !== null && (
                                    <span className="text-muted-foreground">
                                      Exit code: {att.exit_code}
                                    </span>
                                  )}
                                </div>
                                <span className="text-muted-foreground">
                                  {formatTime(att.started_at)}
                                </span>
                              </div>

                              {att.resource_usage_json && (
                                <div className="flex gap-4 text-muted-foreground mb-2">
                                  {att.resource_usage_json.wall_time_seconds !== undefined && (
                                    <span>
                                      Wall time:{" "}
                                      {att.resource_usage_json.wall_time_seconds.toFixed(2)}s
                                    </span>
                                  )}
                                  {att.resource_usage_json.cpu_user_seconds !== undefined && (
                                    <span>
                                      CPU time:{" "}
                                      {att.resource_usage_json.cpu_user_seconds.toFixed(2)}s
                                    </span>
                                  )}
                                  {att.resource_usage_json.peak_memory_bytes !== undefined && (
                                    <span>
                                      Peak memory:{" "}
                                      {(
                                        att.resource_usage_json.peak_memory_bytes /
                                        (1024 * 1024)
                                      ).toFixed(1)}{" "}
                                      MiB
                                    </span>
                                  )}
                                </div>
                              )}

                              {att.stdout_excerpt && (
                                <div className="mt-2">
                                  <span className="text-muted-foreground block text-[11px]">
                                    Standard Output:
                                  </span>
                                  <pre className="p-2 bg-muted rounded font-mono text-[11px] overflow-x-auto max-h-32">
                                    {att.stdout_excerpt}
                                  </pre>
                                </div>
                              )}

                              {att.stderr_excerpt && (
                                <div className="mt-2">
                                  <span className="text-muted-foreground block text-[11px] text-red-500">
                                    Standard Error:
                                  </span>
                                  <pre className="p-2 bg-red-950/20 text-red-400 rounded font-mono text-[11px] overflow-x-auto max-h-32">
                                    {att.stderr_excerpt}
                                  </pre>
                                </div>
                              )}

                              {att.output_artifact_ids && att.output_artifact_ids.length > 0 && (
                                <div className="mt-2 text-muted-foreground">
                                  <strong>Ingested Artifacts:</strong>{" "}
                                  {att.output_artifact_ids.map((id) => shortId(id)).join(", ")}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function LiveStreamingTerminal({
  investigationId,
  jobId,
}: {
  investigationId: string;
  jobId: string;
}) {
  const [logs, setLogs] = useState<{ id: number; stream: string; text: string }[]>([]);
  const [streamStatus, setStreamStatus] = useState<"connecting" | "live" | "completed" | "error">("connecting");
  const [autoScroll, setAutoScroll] = useState(true);
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const logIdSeq = useRef(0);

  useEffect(() => {
    const url = executionApi.streamUrl(investigationId, jobId);
    const es = new EventSource(url);

    setStreamStatus("connecting");

    const pushLog = (stream: string, text: string) => {
      setLogs((prev) => [...prev, { id: ++logIdSeq.current, stream, text }]);
    };

    es.addEventListener("connected", (evt) => {
      setStreamStatus("live");
      try {
        const data = JSON.parse(evt.data);
        pushLog("system", `Connected to SSE stream for job ${shortId(data.job_id)} (status: ${data.status})`);
      } catch {
        pushLog("system", "Connected to live execution stream.");
      }
    });

    es.addEventListener("execution_event", (evt) => {
      try {
        const data = JSON.parse(evt.data);
        pushLog("event", `[EVENT #${data.sequence_number}] ${data.event_type}`);
      } catch {
        pushLog("event", evt.data);
      }
    });

    es.addEventListener("attempt", (evt) => {
      try {
        const data = JSON.parse(evt.data);
        pushLog("system", `[ATTEMPT #${data.attempt_number}] Status: ${data.status} (exit: ${data.exit_code ?? "running"})`);
      } catch {
        pushLog("system", evt.data);
      }
    });

    es.addEventListener("log", (evt) => {
      try {
        const data = JSON.parse(evt.data);
        pushLog(data.stream || "stdout", data.text);
      } catch {
        pushLog("stdout", evt.data);
      }
    });

    es.addEventListener("measurement", (evt) => {
      try {
        const data = JSON.parse(evt.data);
        pushLog("measurement", `[MEASUREMENT] ${data.metric_name}: ${(data.value * 100).toFixed(1)}% (95% Wilson CI: [${(data.interval_lower * 100).toFixed(2)}%, ${(data.interval_upper * 100).toFixed(2)}%])`);
      } catch {
        pushLog("measurement", evt.data);
      }
    });

    es.addEventListener("done", () => {
      setStreamStatus("completed");
      pushLog("system", "Execution log stream closed (process completed).");
      es.close();
    });

    es.onerror = () => {
      setStreamStatus("error");
      pushLog("error", "EventSource stream disconnected or completed.");
      es.close();
    };

    return () => {
      es.close();
    };
  }, [investigationId, jobId]);

  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  return (
    <div className="live-terminal-container mt-3 mb-4 rounded-lg overflow-hidden border border-zinc-800 bg-zinc-950 text-zinc-100 font-mono text-xs">
      <div className="flex items-center justify-between px-3 py-2 bg-zinc-900 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${
              streamStatus === "live"
                ? "bg-emerald-400 animate-pulse"
                : streamStatus === "connecting"
                ? "bg-amber-400 animate-pulse"
                : streamStatus === "completed"
                ? "bg-blue-400"
                : "bg-red-400"
            }`}
          />
          <span className="font-semibold uppercase tracking-wider text-[11px]">
            {streamStatus === "live"
              ? "Live SSE Sandbox Terminal"
              : streamStatus === "connecting"
              ? "Connecting SSE…"
              : streamStatus === "completed"
              ? "Terminal Replay Complete"
              : "Stream Closed"}
          </span>
          <span className="text-zinc-500 text-[10px]">({logs.length} lines)</span>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <label className="flex items-center gap-1 cursor-pointer text-zinc-400 hover:text-zinc-200">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            Auto-scroll
          </label>
          <button
            type="button"
            onClick={() => setLogs([])}
            className="text-zinc-400 hover:text-zinc-200 underline"
          >
            Clear
          </button>
        </div>
      </div>
      <div className="p-3 max-h-64 overflow-y-auto space-y-1 select-text">
        {logs.length === 0 ? (
          <div className="text-zinc-500 italic">Listening for sandbox container execution logs…</div>
        ) : (
          logs.map((item) => {
            let color = "text-zinc-300";
            if (item.stream === "system") color = "text-cyan-400 font-semibold";
            else if (item.stream === "event") color = "text-purple-400";
            else if (item.stream === "measurement") color = "text-emerald-400 font-bold";
            else if (item.stream === "stderr" || item.stream === "error") color = "text-rose-400";
            return (
              <div key={item.id} className={`leading-relaxed break-all ${color}`}>
                <span className="text-zinc-600 select-none mr-2 font-mono text-[10px]">
                  {String(item.id).padStart(3, "0")}
                </span>
                {item.text}
              </div>
            );
          })
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
}
