"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { recordsApi, type Capabilities, type Claim, type Evidence, type FindingSummary, type Protocol, type Scientist } from "../../../lib/api";
import FindingsSection from "./FindingsSection";
import GovernanceSection from "./GovernanceSection";
import ReportsSection from "./ReportsSection";
import WorkflowSection from "./WorkflowSection";
import ExecutionSection from "./ExecutionSection";
import EvaluationSection from "./EvaluationSection";

type Props = { investigationId: string; claims: Claim[]; evidence: Evidence[]; protocols: Protocol[] };

export default function InvestigationRecords(props: Props) {
  return <RecordsWorkspace key={props.investigationId} {...props} />;
}

function RecordsWorkspace({ investigationId, claims, evidence, protocols }: Props) {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [scientists, setScientists] = useState<Scientist[]>([]);
  const [findings, setFindings] = useState<FindingSummary[]>([]);
  const [capabilityError, setCapabilityError] = useState("");
  const [registryError, setRegistryError] = useState("");
  const [findingError, setFindingError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [reviewRevision, setReviewRevision] = useState(0);
  const [governanceRevision, setGovernanceRevision] = useState(0);
  const pendingFindings = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; pendingFindings.current?.abort(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setCapabilityError(""); setRegistryError("");
    recordsApi.capabilities(controller.signal).then((row) => {
      if (!controller.signal.aborted) setCapabilities(row);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) { setCapabilities(null); setCapabilityError(reason instanceof Error ? reason.message : "Could not load capabilities."); }
    });
    recordsApi.scientists(controller.signal).then((rows) => {
      if (!controller.signal.aborted) setScientists(rows);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setRegistryError(reason instanceof Error ? reason.message : "Could not load registered constitutions.");
    });
    return () => controller.abort();
  }, [revision]);

  const refreshFindings = useCallback(async () => {
    pendingFindings.current?.abort();
    const controller = new AbortController();
    pendingFindings.current = controller;
    setLoading(true); setFindingError("");
    try {
      const rows = await recordsApi.findings(investigationId, controller.signal);
      if (mounted.current && !controller.signal.aborted) setFindings(rows);
    } catch (reason) {
      if (mounted.current && !controller.signal.aborted) setFindingError(reason instanceof Error ? reason.message : "Could not load findings.");
      throw reason;
    } finally {
      if (mounted.current && !controller.signal.aborted) setLoading(false);
    }
  }, [investigationId]);

  useEffect(() => {
    if (capabilities?.traceable_findings) void refreshFindings().catch(() => undefined);
    else setLoading(false);
    return () => pendingFindings.current?.abort();
  }, [capabilities?.traceable_findings, refreshFindings]);

  return <section className="records-workspace" aria-label="Evidence-linked findings and reports">
    <header className="records-heading"><p className="eyebrow accent">Evidence-linked workbench</p><h2>Findings &amp; reports</h2><p>Human-recorded analysis, versioned citations, and immutable exports. Publication is a manual record action, not evidence of an experiment.</p></header>
    <p className="records-note">Scientist profiles remain registered constitutions, not active agents. Recorder identities are caller-asserted, not authenticated.</p>
    {capabilityError && <p className="records-error" role="alert">Capability unknown: {capabilityError}</p>}
    {registryError && <p className="records-error" role="alert">Constitution registry unavailable: {registryError} Human recording without an optional role association remains available.</p>}
    {(capabilityError || registryError) && <button type="button" onClick={() => setRevision((value) => value + 1)}>Retry capability and registry load</button>}
    {!capabilities && !capabilityError && <p role="status">Loading record capabilities…</p>}
    {capabilities && <>
      {findingError && <p className="records-error" role="alert">Finding list refresh failed: {findingError}</p>}
      {capabilities.traceable_findings && <div className="records-actions"><button type="button" disabled={loading} onClick={() => void refreshFindings().catch(() => undefined)}>{loading ? "Loading findings…" : "Refresh finding list"}</button></div>}
      <FindingsSection investigationId={investigationId} findings={findings} claims={claims} evidence={evidence} protocols={protocols} scientists={scientists} enabled={capabilities.traceable_findings} onChanged={refreshFindings} onReviewChanged={() => setReviewRevision((value) => value + 1)} />
      <ReportsSection investigationId={investigationId} findings={findings} claims={claims} scientists={scientists} reviewRevision={reviewRevision} enabled={capabilities.reports} />
      <header className="records-heading"><p className="eyebrow accent">Scientist institute</p><h2>Governed workflow &amp; assignments</h2><p>Persisted assignments, deliverables, human review gates and model-call audit records. Nothing here is simulated: each row is read from the API and survives reload.</p></header>
      <WorkflowSection investigationId={investigationId} scientists={scientists} enabled={capabilities.langgraph_workflow} onChanged={() => setGovernanceRevision((value) => value + 1)} />
      <GovernanceSection investigationId={investigationId} revision={governanceRevision} />
      <ExecutionSection investigationId={investigationId} protocols={protocols} enabled={Boolean(capabilities.experiment_runner)} />
      <EvaluationSection investigationId={investigationId} enabled={Boolean(capabilities.experiment_runner)} />
    </>}
  </section>;
}
