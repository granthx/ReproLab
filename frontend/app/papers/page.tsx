"use client";

import React, { ChangeEvent, FormEvent, useEffect, useState, useCallback } from "react";
import { API_URL, papersApi, Paper } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLens } from "../lib/lens";
import { useI18n } from "../lib/i18n";
import { HashFingerprint } from "../components/HashFingerprint";

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
  } catch {
    return iso;
  }
}

const PAGE_SIZE = 10;

export default function PapersPage() {
  const { canMutate, role } = useAuth();
  const { isPlain } = useLens();
  const { locale, t } = useI18n();

  const [papers, setPapers] = useState<Paper[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadPapers = useCallback(async (targetPage: number) => {
    setLoading(true);
    setError(null);
    try {
      const [list, countRes] = await Promise.all([
        papersApi.list({ limit: PAGE_SIZE, offset: targetPage * PAGE_SIZE }),
        papersApi.count(),
      ]);
      setPapers(list);
      setTotalCount(countRes.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("error_connection"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadPapers(page);
  }, [page, loadPapers]);

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError(locale === "hi" ? "कृपया अपलोड करने के लिए एक PDF फ़ाइल चुनें।" : "Select a PDF file before uploading.");
      return;
    }
    setUploading(true);
    setError(null);
    setNotice(null);

    const formData = new FormData();
    formData.append("file", file);
    if (title.trim()) {
      formData.append("title", title.trim());
    }

    try {
      // Get active token if any
      const token = typeof window !== "undefined" ? window.localStorage.getItem("reprolab_auth_token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API_URL}/papers`, {
        method: "POST",
        headers,
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || (locale === "hi" ? "दस्तावेज़ अपलोड करने में विफलता।" : "Failed to upload document."));
      }

      setNotice(
        data.created
          ? (locale === "hi" ? "शोध पत्र सुरक्षित संग्रह में जोड़ दिया गया है।" : "Paper stored in private archive.")
          : (locale === "hi" ? "सूचना: यह PDF पहले से ही संग्रह में मौजूद है (डुप्लिकेट)।" : "Notice: This exact PDF is already in the archive (duplicate bytes).")
      );
      setTitle("");
      setFile(null);
      const input = document.getElementById("paper-upload-input") as HTMLInputElement | null;
      if (input) input.value = "";
      await loadPapers(0);
      setPage(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : (locale === "hi" ? "अपलोड विफल रहा।" : "Upload failed."));
    } finally {
      setUploading(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  return (
    <main className="shell">
      {/* Header */}
      <div style={{ marginBottom: "28px" }}>
        <span className="badge badge-paper" style={{ marginBottom: "8px", borderStyle: "solid" }}>
          {locale === "hi" ? "प्राथमिक साहित्य संग्रह" : "Primary Literature Archive"}
        </span>
        <h2>{locale === "hi" ? "शोध पत्र संग्रह एवं साक्ष्य स्रोत" : "Paper Archive & Document Vault"}</h2>
        <p style={{ color: "var(--color-peat-subtle)" }}>
          {isPlain
            ? (locale === "hi"
                ? "यहां सभी मूल वैज्ञानिक शोध पत्र सुरक्षित रूप से संगृहीत हैं। प्रत्येक दस्तावेज़ की एक विशिष्ट सुरक्षा पहचान (SHA-256) होती है।"
                : "Every paper is stored immutably in content-addressed storage. Storing a paper records its text without implying any scientific agreement or automated reproduction.")
            : "Cryptographically verified, content-addressed research papers. PDFs are hashed with SHA-256 upon intake and deduplicated by byte stream."}
        </p>
      </div>

      {/* Upload Panel (Operator/Admin) */}
      <section className="card" style={{ marginBottom: "32px", backgroundColor: "#FFFFFF" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h3>{t("action_archive_paper")}</h3>
          <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 700, color: "var(--color-peat-subtle)" }}>
            {locale === "hi" ? "अधिकतम आकार: 25 MB" : "PDF ONLY · MAX 25 MB"}
          </span>
        </div>

        {!canMutate ? (
          <div className="notice notice-info">
            {locale === "hi"
              ? "आप 'दर्शक' (Viewer) भूमिका में हैं। आप सभी दस्तावेज़ पढ़ और डाउनलोड कर सकते हैं। नए दस्तावेज़ अपलोड करने के लिए शोधकर्ता भूमिका में बदलें।"
              : "You are signed in as a Viewer. You can inspect and download any paper. Operators can upload new papers."}
          </div>
        ) : (
          <form onSubmit={handleUpload}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", marginBottom: "16px" }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label" htmlFor="paper-upload-input">
                  {locale === "hi" ? "PDF फ़ाइल चुनें *" : "Choose PDF Document *"}
                </label>
                <input
                  id="paper-upload-input"
                  className="form-input"
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(e: ChangeEvent<HTMLInputElement>) => {
                    setFile(e.target.files?.[0] || null);
                    setError(null);
                  }}
                  required
                />
              </div>

              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label" htmlFor="paper-title-input">
                  {locale === "hi" ? "शीर्षक (वैकल्पिक)" : "Display Title (Optional)"}
                </label>
                <input
                  id="paper-title-input"
                  className="form-input"
                  type="text"
                  placeholder={locale === "hi" ? "फ़ाइल नाम का उपयोग किया जाएगा" : "Defaults to original filename"}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={500}
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={uploading || !file}
              title={!file ? "Select a PDF file to archive" : uploading ? "Uploading paper..." : undefined}
            >
              {uploading ? t("action_uploading") : t("action_archive_paper")}
            </button>
          </form>
        )}

        {notice && <div className="notice notice-info" style={{ marginTop: "16px" }}>{notice}</div>}
        {error && <div className="notice notice-error" style={{ marginTop: "16px" }}>{error}</div>}
      </section>

      {/* Archive Ledger */}
      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h3>{locale === "hi" ? "संग्रहीत दस्तावेज़" : "Archived Papers"}</h3>
            <span style={{ fontSize: "14px", color: "var(--color-peat-subtle)" }}>
              {totalCount} {locale === "hi" ? "दस्तावेज़ कुल" : "total records"}
            </span>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <button
                type="button"
                className="btn-secondary"
                disabled={page === 0 || loading}
                title={page === 0 ? "Already on first page" : loading ? "Loading..." : undefined}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                style={{ minHeight: "36px", padding: "4px 12px", fontSize: "13px" }}
              >
                ← {locale === "hi" ? "पिछला" : "Prev"}
              </button>
              <span style={{ fontSize: "13px", fontWeight: 700 }}>
                {page + 1} / {totalPages}
              </span>
              <button
                type="button"
                className="btn-secondary"
                disabled={page >= totalPages - 1 || loading}
                title={page >= totalPages - 1 ? "Already on last page" : loading ? "Loading..." : undefined}
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                style={{ minHeight: "36px", padding: "4px 12px", fontSize: "13px" }}
              >
                {locale === "hi" ? "अगला" : "Next"} →
              </button>
            </div>
          )}
        </div>

        {loading ? (
          <div className="card" style={{ padding: "40px", textAlign: "center" }}>
            <div className="skeleton" style={{ height: "40px", width: "60%", margin: "0 auto 16px" }} />
            <div className="skeleton" style={{ height: "24px", width: "40%", margin: "0 auto" }} />
          </div>
        ) : papers.length === 0 ? (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: "var(--text-lg)", fontWeight: 700, marginBottom: "8px" }}>
              {t("empty_no_papers")}
            </p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {papers.map((paper) => (
              <article
                key={paper.id}
                className="card"
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "16px",
                  padding: "16px 20px",
                  backgroundColor: "#FFFFFF",
                }}
              >
                <div style={{ flex: "1 1 320px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                    <span className="badge" style={{ backgroundColor: "var(--color-chalk)" }}>PDF</span>
                    <HashFingerprint hash={paper.sha256} />
                  </div>
                  <h4 style={{ fontSize: "17px", marginBottom: "4px" }}>{paper.title}</h4>
                  <p style={{ fontSize: "13px", color: "var(--color-peat-subtle)", margin: 0 }}>
                    {paper.original_filename} · {formatBytes(paper.file_size)} · {formatDate(paper.created_at)}
                  </p>
                </div>

                <div>
                  <a
                    href={papersApi.downloadUrl(paper.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-secondary"
                    style={{ fontSize: "13px", minHeight: "38px" }}
                  >
                    {locale === "hi" ? "PDF डाउनलोड करें ↗" : "Download PDF ↗"}
                  </a>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
