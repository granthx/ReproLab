"use client";

import React, { FormEvent, use, useCallback, useEffect, useRef, useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import {
  api,
  API_URL,
  Claim,
  Evidence,
  EvidenceReview,
  Investigation,
  Protocol,
  ResearchArtifact,
  ExperimentJob,
  ScientificEvaluation,
  executionApi,
  evaluationApi,
} from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useLens } from "../../lib/lens";
import { useI18n } from "../../lib/i18n";
import { TheRail } from "../../components/TheRail";
import { HashFingerprint } from "../../components/HashFingerprint";
import { VerdictBadge } from "../../components/VerdictBadge";
import { EvidenceReviewModal } from "./_components/EvidenceReviewModal";
import { plainClaim, plainMeasurement, plainProtocolStatus, plainSourceKind, plainVerdict } from "../../lib/plain";

// Lazy-loaded section components for tabbed views
import WorkflowSection from "./_components/WorkflowSection";
import ExecutionSection from "./_components/ExecutionSection";
import EvaluationSection from "./_components/EvaluationSection";
import GovernanceSection from "./_components/GovernanceSection";
import FindingsSection from "./_components/FindingsSection";
import ReportsSection from "./_components/ReportsSection";

type TabId =
  | "overview"
  | "evidence"
  | "protocol"
  | "findings"
  | "reports"
  | "workflow"
  | "execution"
  | "evaluation"
  | "governance"
  | "files";

const TABS: { id: TabId; labelEn: string; labelHi: string }[] = [
  { id: "overview", labelEn: "Overview", labelHi: "अवलोकन" },
  { id: "evidence", labelEn: "Claims & Evidence", labelHi: "दावे व साक्ष्य" },
  { id: "protocol", labelEn: "Protocols", labelHi: "प्रोटोकॉल" },
  { id: "findings", labelEn: "Findings", labelHi: "निष्कर्ष" },
  { id: "reports", labelEn: "Reports", labelHi: "रिपोर्ट्स" },
  { id: "workflow", labelEn: "Pipeline (14 Stages)", labelHi: "पुनरुत्पादन कार्यप्रवाह" },
  { id: "execution", labelEn: "Execution Jobs", labelHi: "परीक्षण" },
  { id: "evaluation", labelEn: "Evaluation", labelHi: "वैज्ञानिक मूल्यांकन" },
  { id: "governance", labelEn: "Role Assignments", labelHi: "कार्य व भूमिका आवंटन" },
  { id: "files", labelEn: "Files & Artifacts", labelHi: "फ़ाइलें व अवशेष" },
];

export default function InvestigationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Suspense fallback={<div className="shell"><div className="empty-state">Loading investigation…</div></div>}>
      <InvestigationWorkspace investigationId={id} />
    </Suspense>
  );
}

function InvestigationWorkspace({ investigationId: id }: { investigationId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentTab = (searchParams.get("tab") as TabId) || "overview";

  const { canMutate } = useAuth();
  const { isPlain } = useLens();
  const { locale, t } = useI18n();

  // Core Data States
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [protocols, setProtocols] = useState<Protocol[]>([]);
  const [artifacts, setArtifacts] = useState<ResearchArtifact[]>([]);
  const [jobs, setJobs] = useState<ExperimentJob[]>([]);
  const [evaluations, setEvaluations] = useState<ScientificEvaluation[]>([]);
  const [reviews, setReviews] = useState<Record<string, EvidenceReview[]>>({});

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Review Modal State
  const [reviewModalItem, setReviewModalItem] = useState<Evidence | null>(null);

  // Form States
  const [claimText, setClaimText] = useState("");
  const [metricName, setMetricName] = useState("accuracy");
  const [metricDirection, setMetricDirection] = useState<"maximize" | "minimize">("maximize");
  const [reportedValue, setReportedValue] = useState("0.75");
  const [claimLocator, setClaimLocator] = useState("");
  const [publishedClaim, setPublishedClaim] = useState(false);

  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [evidenceLocator, setEvidenceLocator] = useState("");
  const [evidenceQuote, setEvidenceQuote] = useState("");
  const [selectedClaimId, setSelectedClaimId] = useState<string>("");

  const [protocolJson, setProtocolJson] = useState("");
  const [parentProtocolId, setParentProtocolId] = useState<string>("");

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [inv, claimRows, evRows, protoRows, artRows, jobRows, evalRows] = await Promise.all([
        api<Investigation>(`/investigations/${id}`),
        api<Claim[]>(`/investigations/${id}/claims`),
        api<Evidence[]>(`/investigations/${id}/evidence`),
        api<Protocol[]>(`/investigations/${id}/protocols`),
        api<ResearchArtifact[]>(`/investigations/${id}/artifacts`).catch(() => []),
        executionApi.jobs(id).catch(() => []),
        evaluationApi.list(id).catch(() => []),
      ]);

      setInvestigation(inv);
      setClaims(claimRows);
      setEvidence(evRows);
      setProtocols(protoRows);
      setArtifacts(artRows);
      setJobs(jobRows);
      setEvaluations(evalRows);

      if (claimRows.length > 0 && !selectedClaimId) {
        setSelectedClaimId(claimRows[0].id);
      }

      // Load reviews for each evidence item
      const reviewEntries = await Promise.all(
        evRows.map(async (ev) => {
          try {
            const rList = await api<EvidenceReview[]>(`/investigations/${id}/evidence/${ev.id}/reviews`);
            return [ev.id, rList] as const;
          } catch {
            return [ev.id, []] as const;
          }
        })
      );
      setReviews(Object.fromEntries(reviewEntries));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("error_connection"));
    } finally {
      setLoading(false);
    }
  }, [id, t, selectedClaimId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // Tab switcher
  const setTab = (tab: TabId) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.push(`?${params.toString()}`);
  };

  // Add Claim Form Handler
  async function handleAddClaim(e: FormEvent) {
    e.preventDefault();
    if (!claimText.trim() || !claimLocator.trim()) {
      setError(locale === "hi" ? "दावा और साक्ष्य संदर्भ (Locator) अनिवार्य हैं।" : "Claim statement and source locator are required.");
      return;
    }

    const raw = reportedValue.trim();
    let numVal: number | null = null;
    if (raw) {
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) {
        setError(locale === "hi" ? "दावा किया गया मान एक वैध संख्या होनी चाहिए।" : "Reported value must be a valid number or left blank.");
        return;
      }
      numVal = parsed;
    }

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api(`/investigations/${id}/claims`, {
        method: "POST",
        body: JSON.stringify({
          statement: claimText.trim(),
          metric_name: metricName.trim(),
          metric_direction: metricDirection,
          reported_value: numVal,
          source_kind: investigation?.source_kind,
          source_locator: claimLocator.trim(),
          published: publishedClaim,
        }),
      });
      setNotice(locale === "hi" ? "दावा सफलतापूर्वक दर्ज किया गया।" : "Claim recorded successfully.");
      setClaimText("");
      setClaimLocator("");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record claim.");
    } finally {
      setBusy(false);
    }
  }

  // Add Evidence Form Handler
  async function handleAddEvidence(e: FormEvent) {
    e.preventDefault();
    if (!evidenceLocator.trim()) {
      setError(locale === "hi" ? "साक्ष्य संदर्भ (Locator) अनिवार्य है।" : "Evidence locator is required.");
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api(`/investigations/${id}/evidence`, {
        method: "POST",
        body: JSON.stringify({
          claim_id: selectedClaimId || null,
          source_url: evidenceUrl.trim() || null,
          source_locator: evidenceLocator.trim(),
          quoted_text: evidenceQuote.trim() || null,
        }),
      });
      setNotice(locale === "hi" ? "साक्ष्य सफलतापूर्वक दर्ज किया गया।" : "Evidence recorded successfully.");
      setEvidenceUrl("");
      setEvidenceLocator("");
      setEvidenceQuote("");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record evidence.");
    } finally {
      setBusy(false);
    }
  }

  // Protocol Actions
  async function handleApproveProtocol(protoId: string) {
    setBusy(true);
    setError(null);
    try {
      await api(`/protocols/${protoId}/approve`, {
        method: "POST",
        body: JSON.stringify({ approved_by: "Operator Reviewer" }),
      });
      setNotice(locale === "hi" ? "प्रोटोकॉल स्वीकृत हो गया।" : "Protocol approved.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Protocol approval failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleFreezeProtocol(protoId: string) {
    setBusy(true);
    setError(null);
    try {
      await api(`/protocols/${protoId}/freeze`, { method: "POST" });
      setNotice(locale === "hi" ? "प्रोटोकॉल अपरिवर्तनीय रूप से स्थिर (Frozen) कर दिया गया।" : "Protocol frozen permanently.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Protocol freeze failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateProtocolFromJson(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const parsed = JSON.parse(protocolJson);
      await api(`/investigations/${id}/protocols`, {
        method: "POST",
        body: JSON.stringify({
          protocol: parsed,
          parent_protocol_id: parentProtocolId || null,
        }),
      });
      setNotice(locale === "hi" ? "नया प्रोटोकॉल संस्करण तैयार किया गया।" : "Protocol version created successfully.");
      setProtocolJson("");
      setParentProtocolId("");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid JSON or protocol rejected.");
    } finally {
      setBusy(false);
    }
  }

  // Get Primary Measurement for The Rail
  const primaryMeasurement = jobs.flatMap((j) => j.measurements || [])[0] || null;
  const primaryClaim = claims[0] || null;
  const latestEvaluation = evaluations[0] || null;
  const latestVerdict = latestEvaluation?.verdict || investigation?.claim_assessment;

  if (loading && !investigation) {
    return (
      <main className="shell">
        <div className="card" style={{ padding: "48px", textAlign: "center" }}>
          <div className="skeleton" style={{ height: "40px", width: "50%", margin: "0 auto 16px" }} />
          <div className="skeleton" style={{ height: "24px", width: "30%", margin: "0 auto" }} />
        </div>
      </main>
    );
  }

  if (!investigation) {
    return (
      <main className="shell">
        <div className="notice notice-error">
          {error || (locale === "hi" ? "जांच मामला नहीं मिला।" : "Investigation record not found.")}
        </div>
        <Link href="/investigations" className="btn-secondary">
          ← {locale === "hi" ? "वापस जाएं" : "Back to Ledger"}
        </Link>
      </main>
    );
  }

  const isSynthetic = investigation.source_kind === "synthetic_framework_test";

  return (
    <main className="shell">
      {/* Back to Ledger & Case Headline Header */}
      <div style={{ marginBottom: "20px" }}>
        <Link href="/investigations" style={{ textDecoration: "none", color: "var(--color-peat-subtle)", fontSize: "14px", fontWeight: 700 }}>
          ← {locale === "hi" ? "जांच सूची पर लौटें" : "Investigation Ledger"}
        </Link>

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: "16px", marginTop: "8px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
              <span className={`badge ${isSynthetic ? "badge-practice" : "badge-paper"}`}>
                {isSynthetic ? t("badge_practice_run") : t("badge_literature_paper")}
              </span>
              <HashFingerprint hash={investigation.id.replace(/-/g, "").repeat(2).slice(0, 64)} label="Case Fingerprint" />
            </div>
            <h2>{investigation.name}</h2>
            <p style={{ color: "var(--color-peat-subtle)", fontSize: "14px" }}>
              {plainSourceKind(investigation.source_kind, locale)} · Created: {new Date(investigation.created_at).toLocaleDateString()}
            </p>
          </div>

          {/* Separation of Software Process Status from Scientific Verdict (Rule 1) */}
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "12px" }}>
            {/* Technical Execution Status */}
            <div className="card" style={{ padding: "8px 14px", backgroundColor: "#FFFFFF", boxShadow: "var(--shadow-hard-sm)" }}>
              <span style={{ fontSize: "11px", textTransform: "uppercase", fontWeight: 800, color: "var(--color-peat-subtle)", display: "block" }}>
                {locale === "hi" ? "सॉफ्टवेयर प्रक्रिया" : "Process State"}
              </span>
              <strong style={{ fontSize: "14px", textTransform: "capitalize" }}>
                {investigation.execution_status.replace(/_/g, " ")}
              </strong>
            </div>

            {/* Scientific Empirical Verdict */}
            <div>
              <span style={{ fontSize: "11px", textTransform: "uppercase", fontWeight: 800, color: "var(--color-peat-subtle)", display: "block", marginBottom: "2px" }}>
                {locale === "hi" ? "वैज्ञानिक निष्कर्ष" : "Scientific Verdict"}
              </span>
              <VerdictBadge verdict={latestVerdict} size="md" />
            </div>
          </div>
        </div>
      </div>

      {error && <div className="notice notice-error">{error}</div>}
      {notice && <div className="notice notice-info">{notice}</div>}

      {/* Case Navigation Tabs */}
      <nav className="case-tabs" aria-label="Investigation Sections">
        {TABS.map((tab) => {
          const active = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              className={`case-tab-link ${active ? "active" : ""}`}
              onClick={() => setTab(tab.id)}
            >
              {locale === "hi" ? tab.labelHi : tab.labelEn}
            </button>
          );
        })}
      </nav>

      {/* =========================================================================
          TAB 1: OVERVIEW (Honest headline, The Rail, Verdict, "Who did what")
          ========================================================================= */}
      {currentTab === "overview" && (
        <section>
          {/* Honest Headline Block */}
          <div className="card" style={{ marginBottom: "24px", backgroundColor: "#FFFFFF" }}>
            <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 800, color: "var(--color-peat-subtle)" }}>
              {locale === "hi" ? "मामला सारांश" : "Case Assessment Summary"}
            </span>
            <div style={{ margin: "12px 0 16px" }}>
              <VerdictBadge verdict={latestVerdict} size="lg" />
            </div>
            <p style={{ fontSize: "var(--text-lg)", lineHeight: 1.6, color: "var(--color-peat)" }}>
              {isPlain ? (
                primaryMeasurement ? (
                  plainMeasurement(primaryMeasurement, locale)
                ) : primaryClaim ? (
                  plainClaim(primaryClaim, locale)
                ) : (
                  locale === "hi"
                    ? "इस जांच के लिए अभी तक कोई दावा या प्रयोग माप दर्ज नहीं हुआ है।"
                    : "No claim or empirical measurements have been recorded yet."
                )
              ) : (
                latestEvaluation ? (
                  `Evaluation v${latestEvaluation.evaluation_version}: Verdict=${latestEvaluation.verdict}, Extraction=${latestEvaluation.extraction_quality_score}, Technical=${latestEvaluation.technical_reproducibility_score}, Verification=${latestEvaluation.claim_verification_score}.`
                ) : (
                  `Status=${investigation.status}, Execution=${investigation.execution_status}, ClaimAssessment=${investigation.claim_assessment}.`
                )
              )}
            </p>

            {isSynthetic && (
              <div className="notice notice-warning" style={{ marginTop: "16px" }}>
                <strong>{t("badge_practice_run")}</strong>
                <p style={{ fontSize: "14px", margin: "4px 0 0" }}>
                  {locale === "hi"
                    ? "यह मामला रेप्रोलैब प्रणाली और सांख्यिकीय गणनाओं का परीक्षण करने के लिए एक अंतर्निहित कृत्रिम डेटासेट का उपयोग करता है। यह वास्तविक विज्ञान का प्रमाण नहीं है।"
                    : "This case uses a synthetic benchmark dataset to verify runner isolation and statistical calculation pipelines. Its numbers prove nothing about real-world scientific literature."}
                </p>
              </div>
            )}
          </div>

          {/* The Rail: Visual Comparison Gauge */}
          <div className="card" style={{ marginBottom: "24px", backgroundColor: "#FFFFFF" }}>
            <h3>{t("section_the_rail")}</h3>
            <p style={{ fontSize: "14px", color: "var(--color-peat-subtle)" }}>
              {locale === "hi"
                ? "यह पैमाना शोध पत्र के दावे और स्वतंत्र रूप से मापे गए परिणाम की 95% विश्वसनीय सीमा (Wilson Interval) की सीधी तुलना करता है।"
                : "Answers 'did we land where the paper claimed?' at a glance. Shows claimed metric tick vs measured 95% Wilson confidence interval band."}
            </p>
            <TheRail
              claimed={primaryClaim?.reported_value ?? null}
              measured={primaryMeasurement?.value ?? null}
              lower={primaryMeasurement?.interval_lower ?? null}
              upper={primaryMeasurement?.interval_upper ?? null}
              sampleSize={primaryMeasurement?.sample_size ?? null}
              locale={locale}
            />
          </div>

          {/* Pipeline Attribution & Task Ledger */}
          <div className="card" style={{ backgroundColor: "var(--color-paper)" }}>
            <h3 style={{ marginBottom: "12px" }}>
              {locale === "hi" ? "शोध चरण एवं कार्य प्रगति विवरण" : "Pipeline Attribution & Task Ledger"}
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "12px" }}>
              <div style={{ padding: "12px", border: "1px solid var(--color-rule)", borderRadius: "var(--radius-sm)", backgroundColor: "#FFFFFF" }}>
                <strong>Dr. Atlas &amp; Dr. Quill</strong>
                <p style={{ fontSize: "13px", color: "var(--color-peat-subtle)", margin: "4px 0 0" }}>
                  {claims.length} claims extracted with locators.
                </p>
              </div>
              <div style={{ padding: "12px", border: "1px solid var(--color-rule)", borderRadius: "var(--radius-sm)", backgroundColor: "#FFFFFF" }}>
                <strong>Dr. Sagan &amp; Dr. Hypatia</strong>
                <p style={{ fontSize: "13px", color: "var(--color-peat-subtle)", margin: "4px 0 0" }}>
                  {evidence.length} evidence items inspected and reviewed.
                </p>
              </div>
              <div style={{ padding: "12px", border: "1px solid var(--color-rule)", borderRadius: "var(--radius-sm)", backgroundColor: "#FFFFFF" }}>
                <strong>Dr. Turing &amp; Dr. Curie</strong>
                <p style={{ fontSize: "13px", color: "var(--color-peat-subtle)", margin: "4px 0 0" }}>
                  {protocols.length} protocol specifications authored.
                </p>
              </div>
              <div style={{ padding: "12px", border: "1px solid var(--color-rule)", borderRadius: "var(--radius-sm)", backgroundColor: "#FFFFFF" }}>
                <strong>Dr. Faraday &amp; Dr. Fisher</strong>
                <p style={{ fontSize: "13px", color: "var(--color-peat-subtle)", margin: "4px 0 0" }}>
                  {jobs.length} execution jobs; {jobs.flatMap((j) => j.measurements || []).length} production measurements.
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* =========================================================================
          TAB 2: CLAIMS & EVIDENCE
          ========================================================================= */}
      {currentTab === "evidence" && (
        <section>
          {/* Claims List */}
          <div className="card" style={{ marginBottom: "24px", backgroundColor: "#FFFFFF" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3>{locale === "hi" ? "दावा रजिस्टर" : "Extracted Claims"}</h3>
              <span style={{ fontSize: "13px", fontWeight: 700 }}>{claims.length} claims</span>
            </div>

            {claims.length === 0 ? (
              <p style={{ color: "var(--color-peat-subtle)" }}>{t("empty_no_claims")}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "20px" }}>
                {claims.map((c) => (
                  <div key={c.id} style={{ padding: "12px 16px", border: "1px solid var(--color-rule)", borderRadius: "var(--radius-sm)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <strong>{c.statement}</strong>
                      <span className="badge" style={{ backgroundColor: "var(--color-chalk)" }}>
                        {c.metric_name} ({c.metric_direction})
                      </span>
                    </div>
                    <small style={{ color: "var(--color-peat-subtle)" }}>
                      Reported: <code>{c.reported_value !== null ? c.reported_value : "Not Stated"}</code> · Locator: <code>{c.source_locator || "None"}</code>
                    </small>
                  </div>
                ))}
              </div>
            )}

            {/* Add Claim Form */}
            {canMutate && (
              <form onSubmit={handleAddClaim} style={{ borderTop: "1px solid var(--color-rule)", paddingTop: "16px" }}>
                <h4 style={{ marginBottom: "12px" }}>{t("action_add_claim")}</h4>
                <div className="form-group">
                  <label className="form-label" htmlFor="claim-stmt-input">Claim Statement *</label>
                  <textarea
                    id="claim-stmt-input"
                    className="form-textarea"
                    placeholder="Enter explicit scientific claim from the paper…"
                    value={claimText}
                    onChange={(e) => setClaimText(e.target.value)}
                    required
                  />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px" }}>
                  <div className="form-group">
                    <label className="form-label" htmlFor="claim-metric-input">Metric Name *</label>
                    <input
                      id="claim-metric-input"
                      className="form-input"
                      type="text"
                      value={metricName}
                      onChange={(e) => setMetricName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="claim-dir-select">Metric Direction *</label>
                    <select
                      id="claim-dir-select"
                      className="form-select"
                      value={metricDirection}
                      onChange={(e) => setMetricDirection(e.target.value as any)}
                    >
                      <option value="maximize">Maximize (Higher is better)</option>
                      <option value="minimize">Minimize (Lower is better)</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="claim-val-input">Reported Value (e.g. 0.75)</label>
                    <input
                      id="claim-val-input"
                      className="form-input"
                      type="text"
                      placeholder="Blank for not stated"
                      value={reportedValue}
                      onChange={(e) => setReportedValue(e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="claim-loc-input">Source Locator *</label>
                    <input
                      id="claim-loc-input"
                      className="form-input"
                      type="text"
                      placeholder="e.g. Page 4, Table 2"
                      value={claimLocator}
                      onChange={(e) => setClaimLocator(e.target.value)}
                      required
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={busy}
                  title={busy ? "Processing request..." : undefined}
                >
                  {busy ? "Saving…" : t("action_add_claim")}
                </button>
              </form>
            )}
          </div>

          {/* Evidence List */}
          <div className="card" style={{ backgroundColor: "#FFFFFF" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3>{t("section_evidence_register")}</h3>
              <span style={{ fontSize: "13px", fontWeight: 700 }}>{evidence.length} items</span>
            </div>

            {evidence.length === 0 ? (
              <p style={{ color: "var(--color-peat-subtle)" }}>{t("empty_no_evidence")}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
                {evidence.map((ev) => {
                  const evReviews = reviews[ev.id] || [];
                  return (
                    <article key={ev.id} style={{ padding: "14px 18px", border: "1px solid var(--color-rule)", borderRadius: "var(--radius-sm)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                        <strong style={{ fontSize: "16px" }}>{ev.source_locator}</strong>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span className="badge" style={{ backgroundColor: "var(--color-paper)" }}>
                            {ev.verification_status}
                          </span>
                          {canMutate && (
                            <button
                              type="button"
                              className="btn-secondary"
                              style={{ minHeight: "32px", height: "32px", padding: "2px 10px", fontSize: "12px" }}
                              onClick={() => setReviewModalItem(ev)}
                            >
                              {t("action_record_review")}
                            </button>
                          )}
                        </div>
                      </div>
                      <p style={{ fontStyle: "italic", fontSize: "14px", margin: "6px 0", color: "var(--color-peat)" }}>
                        &ldquo;{ev.quoted_text || "No quotation recorded."}&rdquo;
                      </p>
                      <small style={{ color: "var(--color-peat-subtle)" }}>
                        URL: {ev.source_url || "None"} · Reviews on record: {evReviews.length}
                      </small>

                      {evReviews.length > 0 && (
                        <details style={{ marginTop: "8px", fontSize: "13px" }}>
                          <summary style={{ cursor: "pointer", fontWeight: 600 }}>Review History ({evReviews.length})</summary>
                          <div style={{ marginTop: "6px", display: "flex", flexDirection: "column", gap: "6px" }}>
                            {evReviews.map((r) => (
                              <div key={r.id} style={{ padding: "6px 10px", backgroundColor: "var(--color-paper)", borderRadius: "3px" }}>
                                <strong>{r.outcome}</strong> by {r.reviewer_label || r.reviewer_id} ({new Date(r.reviewed_at).toLocaleDateString()}):
                                <p style={{ margin: "2px 0 0" }}>{r.notes}</p>
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                    </article>
                  );
                })}
              </div>
            )}

            {/* Add Evidence Form */}
            {canMutate && (
              <form onSubmit={handleAddEvidence} style={{ borderTop: "1px solid var(--color-rule)", paddingTop: "16px" }}>
                <h4 style={{ marginBottom: "12px" }}>{t("action_add_evidence")}</h4>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px", marginBottom: "12px" }}>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label" htmlFor="ev-claim-select">Target Claim</label>
                    <select
                      id="ev-claim-select"
                      className="form-select"
                      value={selectedClaimId}
                      onChange={(e) => setSelectedClaimId(e.target.value)}
                    >
                      <option value="">— Unlinked / All claims —</option>
                      {claims.map((c) => (
                        <option key={c.id} value={c.id}>{c.statement.slice(0, 50)}…</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label" htmlFor="ev-locator-input">Source Locator *</label>
                    <input
                      id="ev-locator-input"
                      className="form-input"
                      type="text"
                      placeholder="e.g. Page 3, Section 4.1"
                      value={evidenceLocator}
                      onChange={(e) => setEvidenceLocator(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label" htmlFor="ev-url-input">Source URL</label>
                    <input
                      id="ev-url-input"
                      className="form-input"
                      type="url"
                      placeholder="https://..."
                      value={evidenceUrl}
                      onChange={(e) => setEvidenceUrl(e.target.value)}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="ev-quote-textarea">Quoted Text from Document</label>
                  <textarea
                    id="ev-quote-textarea"
                    className="form-textarea"
                    placeholder="Exact excerpt from the paper…"
                    value={evidenceQuote}
                    onChange={(e) => setEvidenceQuote(e.target.value)}
                  />
                </div>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={busy}
                  title={busy ? "Processing request..." : undefined}
                >
                  {busy ? "Saving…" : t("action_add_evidence")}
                </button>
              </form>
            )}
          </div>

          {/* Modal */}
          {reviewModalItem && (
            <EvidenceReviewModal
              evidenceId={reviewModalItem.id}
              evidenceLocator={reviewModalItem.source_locator}
              isOpen={Boolean(reviewModalItem)}
              onClose={() => setReviewModalItem(null)}
              onReviewed={loadAll}
            />
          )}
        </section>
      )}

      {/* =========================================================================
          TAB 3: PROTOCOLS
          ========================================================================= */}
      {currentTab === "protocol" && (
        <section>
          <div className="card" style={{ marginBottom: "24px", backgroundColor: "#FFFFFF" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3>{t("section_protocol_spec")}</h3>
              <span style={{ fontSize: "13px", fontWeight: 700 }}>{protocols.length} versions</span>
            </div>

            {protocols.length === 0 ? (
              <p style={{ color: "var(--color-peat-subtle)" }}>{t("empty_no_protocols")}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginBottom: "24px" }}>
                {protocols.map((proto) => (
                  <article key={proto.id} style={{ padding: "16px", border: "var(--border-thick)", borderRadius: "var(--radius-card)", backgroundColor: "var(--color-paper)" }}>
                    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
                      <div>
                        <strong style={{ fontSize: "17px" }}>Protocol Version {proto.version_number}</strong>
                        <span className={`badge ${proto.status === "frozen" ? "badge-paper" : "badge-practice"}`} style={{ marginLeft: "8px" }}>
                          {proto.status}
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: "8px" }}>
                        {canMutate && proto.status === "draft" && (
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ minHeight: "36px", height: "36px", padding: "4px 12px", fontSize: "13px" }}
                            onClick={() => handleApproveProtocol(proto.id)}
                            disabled={busy}
                            title={busy ? "Processing..." : undefined}
                          >
                            {t("action_approve_protocol")}
                          </button>
                        )}
                        {canMutate && proto.status === "approved" && (
                          <button
                            type="button"
                            className="btn-primary"
                            style={{ minHeight: "36px", height: "36px", padding: "4px 12px", fontSize: "13px" }}
                            onClick={() => handleFreezeProtocol(proto.id)}
                            disabled={busy}
                            title={busy ? "Processing..." : undefined}
                          >
                            {t("action_freeze_protocol")}
                          </button>
                        )}
                        {canMutate && (
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ minHeight: "36px", height: "36px", padding: "4px 12px", fontSize: "13px" }}
                            onClick={() => {
                              setParentProtocolId(proto.id);
                              setProtocolJson(JSON.stringify(proto.protocol, null, 2));
                            }}
                          >
                            {t("action_new_protocol_version")}
                          </button>
                        )}
                      </div>
                    </div>

                    <div style={{ marginBottom: "8px" }}>
                      <HashFingerprint hash={proto.protocol_hash} label="Protocol Hash" forceFull />
                    </div>

                    <p style={{ fontSize: "14px", color: "var(--color-peat-subtle)" }}>
                      {plainProtocolStatus(proto, locale)}
                    </p>

                    <details style={{ marginTop: "10px", fontSize: "13px" }}>
                      <summary style={{ cursor: "pointer", fontWeight: 600 }}>Inspect Canonical JSON</summary>
                      <pre style={{ padding: "12px", backgroundColor: "#FFFFFF", border: "1px solid var(--color-rule)", borderRadius: "4px", overflowX: "auto", marginTop: "6px" }}>
                        {JSON.stringify(proto.protocol, null, 2)}
                      </pre>
                    </details>
                  </article>
                ))}
              </div>
            )}

            {/* Author Protocol JSON */}
            {canMutate && (
              <form onSubmit={handleCreateProtocolFromJson} style={{ borderTop: "1px solid var(--color-rule)", paddingTop: "16px" }}>
                <h4>Author or Branch Protocol Specification</h4>
                {parentProtocolId && (
                  <p style={{ fontSize: "13px", color: "var(--color-teal)", margin: "4px 0 8px" }}>
                    Branching from parent protocol ID: <code>{parentProtocolId}</code>
                  </p>
                )}
                <div className="form-group">
                  <label className="form-label" htmlFor="proto-json-textarea">Protocol Definition JSON *</label>
                  <textarea
                    id="proto-json-textarea"
                    className="form-textarea"
                    style={{ minHeight: "180px", fontFamily: "var(--font-mono)", fontSize: "13px" }}
                    placeholder='{"source_kind": "synthetic_framework_test", ...}'
                    value={protocolJson}
                    onChange={(e) => setProtocolJson(e.target.value)}
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={busy || !protocolJson.trim()}
                  title={!protocolJson.trim() ? "Enter a protocol definition JSON to enable" : busy ? "Validating & Creating..." : undefined}
                >
                  {busy ? "Validating & Creating…" : "Create Protocol Version"}
                </button>
              </form>
            )}
          </div>
        </section>
      )}

      {/* =========================================================================
          TAB 4: FINDINGS
          ========================================================================= */}
      {currentTab === "findings" && (
        <section>
          <FindingsSection
            investigationId={id}
            findings={[]}
            claims={claims}
            evidence={evidence}
            protocols={protocols}
            scientists={[]}
            onChanged={loadAll}
            enabled={true}
          />
        </section>
      )}

      {/* =========================================================================
          TAB 5: REPORTS
          ========================================================================= */}
      {currentTab === "reports" && (
        <section>
          <ReportsSection
            investigationId={id}
            findings={[]}
            claims={claims}
            scientists={[]}
            enabled={true}
          />
        </section>
      )}

      {/* =========================================================================
          TAB 6: WORKFLOW (14-Node LangGraph Reproduction Pipeline)
          ========================================================================= */}
      {currentTab === "workflow" && (
        <section>
          <WorkflowSection
            investigationId={id}
            scientists={[]}
            enabled={true}
            onChanged={loadAll}
          />
        </section>
      )}

      {/* =========================================================================
          TAB 7: EXECUTION JOBS & PRODUCTION SCORER
          ========================================================================= */}
      {currentTab === "execution" && (
        <section>
          <ExecutionSection
            investigationId={id}
            protocols={protocols}
            enabled={true}
            onChanged={loadAll}
          />
        </section>
      )}

      {/* =========================================================================
          TAB 8: EVALUATION (Tri-Partite Scientific Evaluation Gauges)
          ========================================================================= */}
      {currentTab === "evaluation" && (
        <section>
          <EvaluationSection
            investigationId={id}
            jobs={jobs}
            enabled={true}
          />
        </section>
      )}

      {/* =========================================================================
          TAB 9: GOVERNANCE (Assignments, Deliverables, Review Delegations)
          ========================================================================= */}
      {currentTab === "governance" && (
        <section>
          <GovernanceSection
            investigationId={id}
            revision={0}
          />
        </section>
      )}

      {/* =========================================================================
          TAB 10: FILES & ARTIFACTS
          ========================================================================= */}
      {currentTab === "files" && (
        <section>
          <div className="card" style={{ backgroundColor: "#FFFFFF" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3>Private Research Artifacts</h3>
              <span style={{ fontSize: "13px", fontWeight: 700 }}>{artifacts.length} artifacts</span>
            </div>

            {artifacts.length === 0 ? (
              <p style={{ color: "var(--color-peat-subtle)" }}>No research artifacts recorded yet for this case.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {artifacts.map((art) => (
                  <article key={art.id} style={{ padding: "12px 16px", border: "1px solid var(--color-rule)", borderRadius: "var(--radius-sm)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                      <strong style={{ fontSize: "15px" }}>{art.kind.replace(/_/g, " ")}</strong>
                      <a
                        href={`${API_URL}/investigations/${id}/artifacts/${art.id}/download`}
                        target="_blank"
                        rel="noreferrer"
                        className="btn-secondary"
                        style={{ minHeight: "32px", height: "32px", padding: "2px 10px", fontSize: "12px" }}
                      >
                        Download Verified Bytes ↗
                      </a>
                    </div>
                    <div style={{ marginBottom: "6px" }}>
                      <HashFingerprint hash={art.sha256} forceFull />
                    </div>
                    <small style={{ color: "var(--color-peat-subtle)" }}>
                      {art.size_bytes} bytes · Producer: {art.producer}
                    </small>
                  </article>
                ))}
              </div>
            )}
          </div>
        </section>
      )}
    </main>
  );
}
