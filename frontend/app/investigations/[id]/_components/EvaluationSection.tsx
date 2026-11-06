"use client";

import { useEffect, useState, useTransition } from "react";
import {
  evaluationApi,
  executionApi,
  type ExperimentJob,
  type ScientificEvaluation,
} from "../../../lib/api";

type Props = {
  investigationId: string;
  jobs?: ExperimentJob[];
  enabled?: boolean;
};

export default function EvaluationSection({ investigationId, jobs: propJobs, enabled = true }: Props) {
  const [evaluations, setEvaluations] = useState<ScientificEvaluation[]>([]);
  const [jobs, setJobs] = useState<ExperimentJob[]>(propJobs || []);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [summaryNotes, setSummaryNotes] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const loadData = async () => {
    try {
      const [evalData, jobsData] = await Promise.all([
        evaluationApi.list(investigationId),
        propJobs ? Promise.resolve(propJobs) : executionApi.jobs(investigationId).catch(() => []),
      ]);
      setEvaluations(evalData);
      setJobs(jobsData);
      const completed = jobsData.filter((j: ExperimentJob) => j.status === "completed");
      if (completed.length > 0 && !selectedJobId) {
        setSelectedJobId(completed[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evaluations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (enabled) {
      loadData();
    }
  }, [investigationId, enabled]);

  const completedJobs = jobs.filter((j: ExperimentJob) => j.status === "completed");

  const handleRunEvaluation = () => {
    startTransition(async () => {
      try {
        setError(null);
        await evaluationApi.create(investigationId, {
          job_id: selectedJobId || undefined,
          summary_notes: summaryNotes || undefined,
        });
        await loadData();
        setSummaryNotes("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Evaluation failed");
      }
    });
  };

  const getVerdictBadge = (verdict: string) => {
    switch (verdict) {
      case "reproduced":
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">Reproduced</span>;
      case "disconfirmed":
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300">Disconfirmed</span>;
      case "inconclusive":
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">Inconclusive</span>;
      case "execution_failed":
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-300">Execution Failed</span>;
      default:
        return <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-zinc-100 text-zinc-800 border border-zinc-300">{verdict}</span>;
    }
  };

  return (
    <section className="mt-8 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between border-b border-zinc-100 pb-4">
        <div>
          <h3 className="text-lg font-bold text-zinc-900">Scientific Evaluation Framework</h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            Independent three-tier verification separating extraction quality, technical reproducibility, and scientific claim validity.
          </p>
        </div>
      </div>

      {/* Core Principle Alert */}
      <div className="mt-4 rounded-lg bg-indigo-50 border border-indigo-200 p-3.5 text-xs text-indigo-900 leading-relaxed">
        <strong className="font-semibold text-indigo-950">Scientific Integrity Rule:</strong> Software execution completion does not validate a hypothesis, and execution crashes do not falsify a claim. All evaluation verdicts are strictly grounded in independent trusted scorers and Wilson score intervals.
      </div>

      {/* Evaluation Trigger Control */}
      <div className="mt-5 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-700">Trigger New Evaluation</h4>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">Experiment Job</label>
            <select
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              className="w-full text-xs rounded border border-zinc-300 bg-white px-2.5 py-1.5 focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Latest / Auto-detect</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.id.slice(0, 8)}... ({j.status}) - {j.submission_key}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">Operator Notes</label>
            <input
              type="text"
              placeholder="Optional evaluation context..."
              value={summaryNotes}
              onChange={(e) => setSummaryNotes(e.target.value)}
              className="w-full text-xs rounded border border-zinc-300 bg-white px-2.5 py-1.5 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleRunEvaluation}
              disabled={isPending}
              className="w-full rounded bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition"
            >
              {isPending ? "Evaluating..." : "Run Scientific Evaluation"}
            </button>
          </div>
        </div>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </div>

      {/* Evaluations History List */}
      <div className="mt-6">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-700 mb-3">Evaluation Records ({evaluations.length})</h4>
        {loading ? (
          <p className="text-xs text-zinc-500">Loading evaluation history...</p>
        ) : evaluations.length === 0 ? (
          <p className="text-xs text-zinc-400 italic">No scientific evaluations have been recorded for this investigation yet.</p>
        ) : (
          <div className="space-y-4">
            {evaluations.map((ev) => {
              const claimBreakdown = ev.claim_verification_breakdown as Record<string, any>;
              return (
                <div key={ev.id} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm hover:border-zinc-300 transition">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 pb-3">
                    <div className="flex items-center gap-2.5">
                      {getVerdictBadge(ev.verdict)}
                      <span className="text-xs font-mono text-zinc-500">ID: {ev.id.slice(0, 8)}</span>
                      <span className="text-xs text-zinc-400">v{ev.evaluation_version}</span>
                    </div>
                    <span className="text-xs text-zinc-400">{new Date(ev.evaluated_at).toLocaleString()}</span>
                  </div>

                  {/* Tri-Partite Pillars Grid */}
                  <div className="mt-3.5 grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* Pillar 1 */}
                    <div className="rounded border border-zinc-100 bg-zinc-50 p-2.5">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-xs font-medium text-zinc-700">1. Extraction Quality</span>
                        <span className="text-xs font-bold text-zinc-900">{Math.round(ev.extraction_quality_score * 100)}%</span>
                      </div>
                      <div className="w-full bg-zinc-200 rounded-full h-1.5 mb-2">
                        <div className="bg-indigo-600 h-1.5 rounded-full" style={{ width: `${ev.extraction_quality_score * 100}%` }}></div>
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-tight">Claim metric and frozen protocol completeness fidelity.</p>
                    </div>

                    {/* Pillar 2 */}
                    <div className="rounded border border-zinc-100 bg-zinc-50 p-2.5">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-xs font-medium text-zinc-700">2. Technical Reproducibility</span>
                        <span className="text-xs font-bold text-zinc-900">{Math.round(ev.technical_reproducibility_score * 100)}%</span>
                      </div>
                      <div className="w-full bg-zinc-200 rounded-full h-1.5 mb-2">
                        <div className="bg-emerald-600 h-1.5 rounded-full" style={{ width: `${ev.technical_reproducibility_score * 100}%` }}></div>
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-tight">Hermetic sandbox exit code, prediction and manifest generation.</p>
                    </div>

                    {/* Pillar 3 */}
                    <div className="rounded border border-zinc-100 bg-zinc-50 p-2.5">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-xs font-medium text-zinc-700">3. Claim Verification</span>
                        <span className="text-xs font-bold text-zinc-900">{Math.round(ev.claim_verification_score * 100)}%</span>
                      </div>
                      <div className="w-full bg-zinc-200 rounded-full h-1.5 mb-2">
                        <div className="bg-blue-600 h-1.5 rounded-full" style={{ width: `${ev.claim_verification_score * 100}%` }}></div>
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-tight">Wilson 95% interval overlap against original claimed value.</p>
                    </div>
                  </div>

                  {/* Statistical Details */}
                  {claimBreakdown && (
                    <div className="mt-3 rounded bg-zinc-50 border border-zinc-200 p-2.5 text-xs text-zinc-700">
                      <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
                        <div>
                          <span className="text-zinc-500">Claimed Value:</span>{" "}
                          <strong className="font-semibold text-zinc-900">{claimBreakdown.claimed_value ?? "N/A"}</strong>
                        </div>
                        <div>
                          <span className="text-zinc-500">Measured Value:</span>{" "}
                          <strong className="font-semibold text-zinc-900">
                            {typeof claimBreakdown.measured_value === "number" ? claimBreakdown.measured_value.toFixed(4) : "N/A"}
                          </strong>
                        </div>
                        {claimBreakdown.interval_lower !== null && claimBreakdown.interval_upper !== null && (
                          <div>
                            <span className="text-zinc-500">95% Wilson CI:</span>{" "}
                            <span className="font-mono text-zinc-900">
                              [{claimBreakdown.interval_lower.toFixed(4)}, {claimBreakdown.interval_upper.toFixed(4)}]
                            </span>
                          </div>
                        )}
                        <div>
                          <span className="text-zinc-500">Sample Size:</span>{" "}
                          <span className="text-zinc-900">{claimBreakdown.sample_size ?? "N/A"}</span>
                        </div>
                      </div>
                      {claimBreakdown.verdict_reason && (
                        <p className="mt-2 text-zinc-600 text-[11px] leading-relaxed border-t border-zinc-200 pt-1.5">
                          <strong className="text-zinc-800">Verification Analysis:</strong> {claimBreakdown.verdict_reason}
                        </p>
                      )}
                    </div>
                  )}

                  {ev.summary_notes && (
                    <p className="mt-2 text-xs text-zinc-500 italic">Notes: {ev.summary_notes}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
