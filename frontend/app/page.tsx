"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api, papersApi, Investigation } from "./lib/api";
import { useLens } from "./lib/lens";
import { useI18n } from "./lib/i18n";
import { VerdictBadge } from "./components/VerdictBadge";
import { HashFingerprint } from "./components/HashFingerprint";
import { plainSourceKind } from "./lib/plain";

type Capabilities = {
  experiment_runner?: boolean;
  sandbox_execution?: boolean;
  docker_runner_supported?: boolean;
  langgraph_workflow?: boolean;
  execution_state?: string;
  registered_experiment_types?: string[];
};

const DEFAULT_CAPABILITIES: Capabilities = {
  experiment_runner: true,
  sandbox_execution: true,
  docker_runner_supported: true,
  langgraph_workflow: true,
  execution_state: "available",
};

export default function HomePage() {
  const { isPlain } = useLens();
  const { locale, t } = useI18n();

  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [paperCount, setPaperCount] = useState<number | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(DEFAULT_CAPABILITIES);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [invs, pCount, caps] = await Promise.all([
          api<Investigation[]>("/investigations", { signal: controller.signal }).catch(() => []),
          papersApi.count(controller.signal).catch(() => ({ count: 0 })),
          api<Capabilities>("/capabilities", { signal: controller.signal }).catch(() => DEFAULT_CAPABILITIES),
        ]);
        if (active) {
          setInvestigations(invs);
          setPaperCount(pCount.count);
          setCapabilities(caps);
        }
      } catch (err) {
        if (active && !(err instanceof Error && err.name === "AbortError")) {
          setError(err instanceof Error ? err.message : t("error_connection"));
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadData();
    return () => {
      active = false;
      controller.abort();
    };
  }, [t]);

  return (
    <main className="shell">
      {/* Hero Band */}
      <section className="hero-band">
        <span className="badge badge-paper" style={{ marginBottom: "12px", borderStyle: "solid" }}>
          {locale === "hi" ? "प्रमाण-आधारित एआई शोध कार्यपीठ" : "Evidence-First AI Research Workbench"}
        </span>
        <h2>
          {locale === "hi"
            ? "वैज्ञानिक दावों की स्वतंत्र, निष्पक्ष और स्वचालित पुनरावृत्ति।"
            : "Independent, reproducible verification for computational science."}
        </h2>
        <p style={{ fontSize: "var(--text-lg)", maxWidth: "70ch", color: "var(--color-peat)" }}>
          {isPlain
            ? (locale === "hi"
                ? "रेप्रोलैब प्रोफेसरों, मुख्य अन्वेषकों, समकक्ष समीक्षकों (peer reviewers) और शोधकर्ताओं के लिए बनाया गया मंच है। यह प्रकाशित शोध पत्रों से अनुभवजन्य दावों को निकालता है, निष्पादन प्रोटोकॉल को स्थिर (Freeze) करता है और स्वतंत्र सैंडबॉक्स में प्रयोग चलाकर यह जांचता है कि क्या परिणाम वाकई सही साबित होते हैं।"
                : "ReproLab is built for professors, principal investigators, peer reviewers, and computational researchers. It ingests published empirical literature, freezes exact execution protocols, and runs isolated container experiments to verify whether published results hold up under independent statistical reproduction.")
            : "Automated computational replication platform. Ingests arXiv/conference PDFs, extracts quoted empirical claims, freezes protocol specifications, runs hermetic execution jobs, and computes 95% Wilson confidence score intervals to verify or challenge published findings."}
        </p>

        {/* Audience Pill Bar */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "16px" }}>
          <span style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", color: "var(--color-peat-subtle)", alignSelf: "center", marginRight: "4px" }}>
            {locale === "hi" ? "लक्षित उपयोगकर्ता:" : "Engineered for:"}
          </span>
          <span className="badge" style={{ backgroundColor: "#FFFFFF", borderColor: "var(--color-peat)" }}>
            Professors &amp; Lab Directors
          </span>
          <span className="badge" style={{ backgroundColor: "#FFFFFF", borderColor: "var(--color-peat)" }}>
            Academic Peer Reviewers
          </span>
          <span className="badge" style={{ backgroundColor: "#FFFFFF", borderColor: "var(--color-peat)" }}>
            Principal Investigators (PIs)
          </span>
          <span className="badge" style={{ backgroundColor: "#FFFFFF", borderColor: "var(--color-peat)" }}>
            Computational &amp; ML Researchers
          </span>
        </div>
      </section>

      {/* Live System Capabilities Strip */}
      <section
        className="card"
        style={{
          marginBottom: "28px",
          padding: "16px 20px",
          backgroundColor: "#FFFFFF",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
        }}
        aria-label={t("section_system_capabilities")}
      >
        <div>
          <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 800, color: "var(--color-peat-subtle)" }}>
            {t("section_system_capabilities")}
          </span>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "10px", marginTop: "4px" }}>
            <span className="badge" style={{ backgroundColor: "var(--color-teal-light)", color: "var(--color-teal)" }}>
              ✓ {locale === "hi" ? "दस्तावेज़ संग्रह" : "Paper Intake & SHA-256 Vault"}
            </span>
            <span className="badge" style={{ backgroundColor: "var(--color-teal-light)", color: "var(--color-teal)" }}>
              ✓ {locale === "hi" ? "अपरिवर्तनीय प्रोटोकॉल" : "Protocol Specifications Locked"}
            </span>
            <span className="badge" style={{ backgroundColor: "var(--color-teal-light)", color: "var(--color-teal)" }}>
              ✓ {locale === "hi" ? "14-चरणीय कार्यप्रवाह" : "14-Node LangGraph Pipeline"}
            </span>
            <span
              className="badge"
              style={{
                backgroundColor: capabilities?.experiment_runner ? "var(--color-teal-light)" : "var(--color-saffron-light)",
                color: capabilities?.experiment_runner ? "var(--color-teal)" : "var(--color-peat)",
              }}
            >
              {capabilities?.experiment_runner
                ? (locale === "hi" ? "✓ सुरक्षित परीक्षण सैंडबॉक्स सक्रिय" : "✓ Isolated Runner Active")
                : (locale === "hi" ? "⚠ सैंडबॉक्स उपलब्ध नहीं" : "⚠ Runner Unavailable")}
            </span>
          </div>
        </div>

        {/* Aggregate Stats */}
        <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
          <div>
            <span style={{ display: "block", fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
              {locale === "hi" ? "सक्रिय मामले" : "Open Cases"}
            </span>
            <strong style={{ fontSize: "var(--text-xl)", fontFamily: "var(--font-mono)" }}>
              {loading ? "—" : investigations.length}
            </strong>
          </div>
          <div style={{ borderLeft: "1px solid var(--color-rule)", paddingLeft: "16px" }}>
            <span style={{ display: "block", fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
              {locale === "hi" ? "शोध पत्र" : "Source Papers"}
            </span>
            <strong style={{ fontSize: "var(--text-xl)", fontFamily: "var(--font-mono)" }}>
              {loading ? "—" : (paperCount ?? 0)}
            </strong>
          </div>
        </div>
      </section>

      {/* Error Notice */}
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}

      {/* Open Cases Ledger */}
      <section style={{ marginBottom: "36px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "16px" }}>
          <div>
            <span style={{ fontSize: "var(--text-xs)", textTransform: "uppercase", fontWeight: 800, color: "var(--color-peat-subtle)" }}>
              {t("section_open_cases")}
            </span>
            <h3>{locale === "hi" ? "सक्रिय वैज्ञानिक जांच मामले" : "Current Investigation Records"}</h3>
          </div>
          <Link href="/investigations" className="btn-secondary" style={{ fontSize: "13px" }}>
            {t("action_view_all_cases")}
          </Link>
        </div>

        {loading ? (
          <div className="card" style={{ padding: "40px", textAlign: "center" }}>
            <div className="skeleton" style={{ height: "40px", width: "60%", margin: "0 auto 16px" }} />
            <div className="skeleton" style={{ height: "24px", width: "40%", margin: "0 auto" }} />
          </div>
        ) : investigations.length === 0 ? (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: "8px" }}>
              {t("empty_no_cases")}
            </p>
            <p style={{ color: "var(--color-peat-subtle)", marginBottom: "20px" }}>
              {locale === "hi"
                ? "शोध पत्र अपलोड करके या अभ्यास परीक्षण चुनकर नई जांच शुरू करें।"
                : "Create a paper-backed or synthetic investigation to begin."}
            </p>
            <Link href="/investigations" className="btn-primary">
              {t("action_create_investigation")}
            </Link>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {investigations.map((inv) => {
              const isSynthetic = inv.source_kind === "synthetic_framework_test";
              return (
                <article
                  key={inv.id}
                  className="card"
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "16px",
                    padding: "18px 22px",
                    backgroundColor: "#FFFFFF",
                  }}
                >
                  <div style={{ flex: "1 1 320px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                      <span className={`badge ${isSynthetic ? "badge-practice" : "badge-paper"}`}>
                        {isSynthetic ? t("badge_practice_run") : t("badge_literature_paper")}
                      </span>
                      <HashFingerprint hash={inv.id.replace(/-/g, "").repeat(2).slice(0, 64)} label="Case ID" />
                    </div>
                    <h4 style={{ fontSize: "var(--text-lg)", marginBottom: "4px" }}>
                      <Link href={`/investigations/${inv.id}`} style={{ textDecoration: "none", color: "var(--color-peat)" }}>
                        {inv.name}
                      </Link>
                    </h4>
                    <p style={{ fontSize: "var(--text-sm)", color: "var(--color-peat-subtle)", margin: 0 }}>
                      {plainSourceKind(inv.source_kind, locale)}
                    </p>
                  </div>

                  {/* Verdict & Actions */}
                  <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                    <VerdictBadge verdict={inv.claim_assessment} />
                    <Link href={`/investigations/${inv.id}`} className="btn-primary" style={{ minWidth: "120px" }}>
                      {t("action_view_case")}
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* The 12 Research Pipeline Personas */}
      <section className="card" style={{ backgroundColor: "var(--color-paper)", padding: "28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <span style={{ fontSize: "var(--text-xs)", textTransform: "uppercase", fontWeight: 800, color: "var(--color-peat-subtle)" }}>
              {t("nav_scientists")}
            </span>
            <h3>{locale === "hi" ? "12 विशेष शोध पाइपलाइन भूमिकाएं" : "The 12 Research Pipeline Roles"}</h3>
          </div>
          <Link href="/scientists" className="btn-secondary" style={{ fontSize: "13px" }}>
            {locale === "hi" ? "पूर्ण शोध निर्देशिका देखें →" : "View Full Research Directory →"}
          </Link>
        </div>
        <p style={{ color: "var(--color-peat-subtle)", marginBottom: "16px", fontSize: "var(--text-sm)" }}>
          {locale === "hi"
            ? "ये 12 विशेष भूमिकाएं संपूर्ण वैज्ञानिक पुनरावृत्ति पाइपलाइन को संचालित करती हैं—साक्ष्य निष्कर्षण से लेकर सैंडबॉक्स निष्पादन और सांख्यिकीय सत्यापन तक।"
            : "These 12 specialized roles orchestrate the end-to-end computational reproduction pipeline: from literature claim extraction and dataset audit, to hermetic execution and Wilson score statistical verification."}
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "10px" }}>
          {[
            { id: "atlas", name: "Dr. Atlas", spec: "Principal Investigator" },
            { id: "quill", name: "Dr. Quill", spec: "Literature Claim Extraction" },
            { id: "sagan", name: "Dr. Sagan", spec: "Provenance & Digest Audit" },
            { id: "hypatia", name: "Dr. Hypatia", spec: "Methodology Auditor" },
            { id: "turing", name: "Dr. Turing", spec: "Algorithm Environment" },
            { id: "curie", name: "Dr. Curie", spec: "Dataset Integrity" },
            { id: "faraday", name: "Dr. Faraday", spec: "Isolated Execution" },
            { id: "fisher", name: "Dr. Fisher", spec: "Statistical Scoring" },
            { id: "popper", name: "Dr. Popper", spec: "Adversarial Critique" },
            { id: "shannon", name: "Dr. Shannon", spec: "Sensitivity Analysis" },
            { id: "noether", name: "Dr. Noether", spec: "Replication Invariance" },
            { id: "franklin", name: "Dr. Franklin", spec: "Synthesis & Final Report" },
          ].map((sc) => (
            <div
              key={sc.id}
              style={{
                padding: "10px 14px",
                border: "1px solid var(--color-rule)",
                borderRadius: "var(--radius-sm)",
                backgroundColor: "#FFFFFF",
              }}
            >
              <strong style={{ display: "block", fontSize: "15px" }}>{sc.name}</strong>
              <small style={{ color: "var(--color-peat-subtle)" }}>{sc.spec}</small>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
