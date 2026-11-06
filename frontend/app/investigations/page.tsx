"use client";

import React, { FormEvent, useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api, papersApi, Investigation, Paper } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLens } from "../lib/lens";
import { useI18n } from "../lib/i18n";
import { VerdictBadge } from "../components/VerdictBadge";
import { HashFingerprint } from "../components/HashFingerprint";
import { plainSourceKind } from "../lib/plain";

export default function InvestigationsPage() {
  const { canMutate } = useAuth();
  const { isPlain } = useLens();
  const { locale, t } = useI18n();

  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Filters
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [verdictFilter, setVerdictFilter] = useState<string>("all");

  // Create Form State
  const [name, setName] = useState("");
  const [sourceKind, setSourceKind] = useState<"synthetic_framework_test" | "paper">("synthetic_framework_test");
  const [paperId, setPaperId] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [invList, paperList] = await Promise.all([
        api<Investigation[]>("/investigations"),
        papersApi.list({ limit: 100 }),
      ]);
      setInvestigations(invList);
      setPapers(paperList);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("error_connection"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    if (sourceKind === "paper" && !paperId) {
      setError(locale === "hi" ? "कृपया एक शोध पत्र चुनें।" : "Please select a stored paper for a paper investigation.");
      return;
    }

    setCreating(true);
    setError(null);
    setNotice(null);

    try {
      const created = await api<Investigation>("/investigations", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          source_kind: sourceKind,
          paper_id: sourceKind === "paper" ? paperId : null,
        }),
      });
      setNotice(
        locale === "hi"
          ? `नई जांच सफलतापूर्वक बनाई गई: ${created.name}`
          : `Investigation created successfully: ${created.name}`
      );
      setName("");
      setPaperId("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create investigation.");
    } finally {
      setCreating(false);
    }
  }

  // Filtered investigations
  const filtered = investigations.filter((inv) => {
    if (sourceFilter !== "all" && inv.source_kind !== sourceFilter) return false;
    if (verdictFilter !== "all") {
      const currentVerdict = inv.claim_assessment || "not_assessed";
      if (currentVerdict !== verdictFilter) return false;
    }
    return true;
  });

  return (
    <main className="shell">
      {/* Page Title */}
      <div style={{ marginBottom: "28px" }}>
        <span className="badge badge-paper" style={{ marginBottom: "8px", borderStyle: "solid" }}>
          {locale === "hi" ? "जांच रजिस्टर" : "Research Case Ledger"}
        </span>
        <h2>{locale === "hi" ? "वैज्ञानिक जांच मामले" : "Investigation Records"}</h2>
        <p style={{ color: "var(--color-peat-subtle)" }}>
          {isPlain
            ? (locale === "hi"
                ? "प्रत्येक जांच एक खुला, अपरिवर्तनीय मामला है। इसमें शोध पत्र के दावे, साक्ष्य, परीक्षण प्रोटोकॉल, कार्यप्रवाह और स्वतंत्र माप दर्ज होते हैं।"
                : "Every investigation documents a single scientific claim. The record preserves claims, verified evidence, frozen protocols, and empirical measurements.")
            : "Persistent investigations ledger. Distinguishes literature paper investigations from synthetic framework verification tests."}
        </p>
      </div>

      {error && <div className="notice notice-error">{error}</div>}
      {notice && <div className="notice notice-info">{notice}</div>}

      {/* Start New Investigation (Operator / Admin) */}
      <section className="card" style={{ marginBottom: "32px", backgroundColor: "#FFFFFF" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h3>{t("action_create_investigation")}</h3>
          <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 700, color: "var(--color-peat-subtle)" }}>
            {locale === "hi" ? "नया मामला" : "NEW CASE"}
          </span>
        </div>

        {!canMutate ? (
          <div className="notice notice-info">
            {locale === "hi"
              ? "दर्शक केवल जांच रिकॉर्ड देख सकते हैं। नई जांच शुरू करने के लिए शोधकर्ता भूमिका में बदलें।"
              : "Viewers can inspect all investigation records. Switch to Researcher role to start a new investigation."}
          </div>
        ) : (
          <form onSubmit={handleCreate}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", marginBottom: "16px" }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label" htmlFor="inv-name-input">
                  {locale === "hi" ? "जांच का नाम *" : "Investigation Title *"}
                </label>
                <input
                  id="inv-name-input"
                  className="form-input"
                  type="text"
                  placeholder={locale === "hi" ? "उदा. 'मॉडल 1 सटीकता का पुनः परीक्षण'" : "e.g. Tabular Benchmark Reproduction"}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={500}
                />
              </div>

              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label" htmlFor="inv-source-select">
                  {locale === "hi" ? "स्रोत वर्गीकरण *" : "Source Classification *"}
                </label>
                <select
                  id="inv-source-select"
                  className="form-select"
                  value={sourceKind}
                  onChange={(e) => setSourceKind(e.target.value as any)}
                >
                  <option value="synthetic_framework_test">
                    {locale === "hi" ? "अभ्यास परीक्षण (Synthetic Framework Test)" : "Practice Run (Synthetic Framework Test)"}
                  </option>
                  <option value="paper">
                    {locale === "hi" ? "शोध पत्र जांच (Literature Paper)" : "Published Paper Investigation"}
                  </option>
                </select>
              </div>

              {sourceKind === "paper" && (
                <div className="form-group" style={{ margin: 0 }}>
                  <label className="form-label" htmlFor="inv-paper-select">
                    {locale === "hi" ? "संग्रहीत शोध पत्र चुनें *" : "Select Archived Paper *"}
                  </label>
                  <select
                    id="inv-paper-select"
                    className="form-select"
                    value={paperId}
                    onChange={(e) => setPaperId(e.target.value)}
                    required
                  >
                    <option value="">{locale === "hi" ? "— शोध पत्र चुनें —" : "— Choose a paper —"}</option>
                    {papers.map((p) => (
                      <option key={p.id} value={p.id}>{p.title}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={creating || !name.trim()}
              title={!name.trim() ? "Enter a case title to enable creation" : creating ? "Creating case..." : undefined}
            >
              {creating ? (locale === "hi" ? "बनाया जा रहा है…" : "Creating…") : t("action_create_investigation")}
            </button>
          </form>
        )}
      </section>

      {/* Filter Bar */}
      <section style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "16px", marginBottom: "20px" }}>
        <div>
          <h3>{locale === "hi" ? "जांच रजिस्टर" : "All Investigations"}</h3>
          <span style={{ fontSize: "14px", color: "var(--color-peat-subtle)" }}>
            {filtered.length} of {investigations.length} {locale === "hi" ? "मामले" : "cases"}
          </span>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "10px" }}>
          {/* Source Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <label htmlFor="filter-source" style={{ fontSize: "13px", fontWeight: 700 }}>
              {locale === "hi" ? "स्रोत:" : "Source:"}
            </label>
            <select
              id="filter-source"
              className="form-select"
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              style={{ minHeight: "36px", padding: "4px 10px", fontSize: "13px", width: "auto" }}
            >
              <option value="all">{locale === "hi" ? "सभी स्रोत" : "All Sources"}</option>
              <option value="synthetic_framework_test">{locale === "hi" ? "अभ्यास परीक्षण" : "Practice Tests"}</option>
              <option value="paper">{locale === "hi" ? "शोध पत्र" : "Papers"}</option>
            </select>
          </div>

          {/* Verdict Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <label htmlFor="filter-verdict" style={{ fontSize: "13px", fontWeight: 700 }}>
              {locale === "hi" ? "परिणाम:" : "Verdict:"}
            </label>
            <select
              id="filter-verdict"
              className="form-select"
              value={verdictFilter}
              onChange={(e) => setVerdictFilter(e.target.value)}
              style={{ minHeight: "36px", padding: "4px 10px", fontSize: "13px", width: "auto" }}
            >
              <option value="all">{locale === "hi" ? "सभी परिणाम" : "All Verdicts"}</option>
              <option value="reproduced">{locale === "hi" ? "पुनरुत्पादित" : "Reproduced"}</option>
              <option value="disconfirmed">{locale === "hi" ? "अपुष्ट" : "Disconfirmed"}</option>
              <option value="inconclusive">{locale === "hi" ? "अनिर्णायक" : "Inconclusive"}</option>
              <option value="execution_failed">{locale === "hi" ? "प्रक्रिया विफल" : "Execution Failed"}</option>
              <option value="not_assessed">{locale === "hi" ? "मूल्यांकन शेष" : "Not Assessed"}</option>
            </select>
          </div>
        </div>
      </section>

      {/* Investigations Ledger */}
      {loading ? (
        <div className="card" style={{ padding: "40px", textAlign: "center" }}>
          <div className="skeleton" style={{ height: "40px", width: "60%", margin: "0 auto 16px" }} />
          <div className="skeleton" style={{ height: "24px", width: "40%", margin: "0 auto" }} />
        </div>
      ) : filtered.length === 0 ? (
        <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
          <p style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: "8px" }}>
            {locale === "hi" ? "कोई मेल खाते मामले नहीं मिले" : "No matching investigation records found"}
          </p>
          <p style={{ color: "var(--color-peat-subtle)" }}>
            {locale === "hi" ? "कृपया अपने फ़िल्टर समायोजित करें।" : "Try adjusting your filter options above."}
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {filtered.map((inv) => {
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
                    {plainSourceKind(inv.source_kind, locale)} · {new Date(inv.updated_at).toLocaleDateString()}
                  </p>
                </div>

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
    </main>
  );
}
