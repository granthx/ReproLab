"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api, operationsApi, HealthDiagnostics } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLens } from "../lib/lens";
import { useI18n } from "../lib/i18n";
import { HashFingerprint } from "../components/HashFingerprint";

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

type ReadyResponse = {
  status: string;
  database?: string;
  storage?: string;
};

type BackupRecord = {
  id: string;
  backup_id: string;
  manifest_sha256: string;
  database_dump_sha256: string;
  artifact_count: number;
  total_bytes: number;
  status: string;
  created_at: string;
};

export default function StatusPage() {
  const { canMutate, isAdmin } = useAuth();
  const { isPlain } = useLens();
  const { locale, t } = useI18n();

  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<HealthDiagnostics | null>(null);
  const [backups, setBackups] = useState<BackupRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [backingUp, setBackingUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rRes, dRes, bRes] = await Promise.all([
        api<ReadyResponse>("/health/ready").catch(() => ({ status: "error" })),
        operationsApi.diagnostics().catch(() => null),
        operationsApi.backups().catch(() => []),
      ]);
      setReady(rRes);
      setDiagnostics(dRes);
      setBackups(bRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("error_connection"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  async function handleBackup() {
    setBackingUp(true);
    setError(null);
    setNotice(null);
    try {
      const res = await operationsApi.backup();
      setNotice(
        locale === "hi"
          ? `बैकअप सफलतापूर्वक तैयार किया गया! ID: ${res.backup_id}`
          : `Coordinated backup created successfully! ID: ${res.backup_id}`
      );
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backup trigger failed.");
    } finally {
      setBackingUp(false);
    }
  }

  const isHealthy = ready?.status === "ready";

  return (
    <main className="shell">
      {/* Header */}
      <div style={{ marginBottom: "28px" }}>
        <span className="badge badge-paper" style={{ marginBottom: "8px", borderStyle: "solid" }}>
          {locale === "hi" ? "प्रणाली स्वास्थ्य एवं परिचालन" : "System Health & Reliability"}
        </span>
        <h2>{locale === "hi" ? "प्रणाली स्थिति एवं आपदा रिकवरी" : "System Status & Reliability Monitor"}</h2>
        <p style={{ color: "var(--color-peat-subtle)" }}>
          {isPlain
            ? (locale === "hi"
                ? "यह पृष्ठ संस्थान के डेटाबेस, स्टोरेज और सर्वर स्वास्थ्य की वास्तविक स्थिति दिखाता है। कोई भी रहस्य छुपाया नहीं जाता।"
                : "Real-time health and cryptographic integrity of ReproLab services, database connections, and storage archives.")
            : "Operational telemetry: database pool health, content-addressed storage statistics, deep readiness probes, and coordinated backup bundles."}
        </p>
      </div>

      {error && <div className="notice notice-error">{error}</div>}
      {notice && <div className="notice notice-info">{notice}</div>}

      {/* Health Probes Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", marginBottom: "28px" }}>
        {/* Core Readiness */}
        <div className="card" style={{ backgroundColor: "#FFFFFF" }}>
          <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 700, color: "var(--color-peat-subtle)" }}>
            {locale === "hi" ? "सर्वर तत्परता" : "Service Readiness"}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "8px", marginBottom: "8px" }}>
            <span
              style={{
                width: "12px",
                height: "12px",
                borderRadius: "50%",
                backgroundColor: isHealthy ? "var(--color-teal)" : "var(--color-madder)",
                display: "inline-block",
              }}
            />
            <strong style={{ fontSize: "var(--text-xl)" }}>
              {isHealthy ? (locale === "hi" ? "तैयार एवं सक्रिय" : "Ready & Operational") : "Unhealthy / Degraded"}
            </strong>
          </div>
          <small style={{ color: "var(--color-peat-subtle)" }}>
            Database: {ready?.database || "ok"} · Storage: {ready?.storage || "ok"}
          </small>
        </div>

        {/* Uptime */}
        <div className="card" style={{ backgroundColor: "#FFFFFF" }}>
          <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 700, color: "var(--color-peat-subtle)" }}>
            {locale === "hi" ? "सक्रिय समय" : "Service Uptime"}
          </span>
          <strong style={{ display: "block", fontSize: "var(--text-xl)", marginTop: "8px", fontFamily: "var(--font-mono)" }}>
            {diagnostics ? formatUptime(diagnostics.uptime_seconds) : "—"}
          </strong>
          <small style={{ color: "var(--color-peat-subtle)" }}>
            Server time: {diagnostics?.server_time ? new Date(diagnostics.server_time).toLocaleTimeString() : "—"}
          </small>
        </div>

        {/* Storage Stats */}
        <div className="card" style={{ backgroundColor: "#FFFFFF" }}>
          <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 700, color: "var(--color-peat-subtle)" }}>
            {locale === "hi" ? "सुरक्षित स्टोरेज" : "Storage Archive"}
          </span>
          <strong style={{ display: "block", fontSize: "var(--text-xl)", marginTop: "8px", fontFamily: "var(--font-mono)" }}>
            {diagnostics ? formatBytes(diagnostics.storage.total_bytes) : "—"}
          </strong>
          <small style={{ color: "var(--color-peat-subtle)" }}>
            {diagnostics?.storage.total_files || 0} {locale === "hi" ? "सत्यापित फ़ाइलें" : "content-addressed files"}
          </small>
        </div>
      </div>

      {/* Aggregate Entity Counts */}
      {diagnostics && (
        <section className="card" style={{ marginBottom: "32px", backgroundColor: "var(--color-paper)" }}>
          <h3 style={{ marginBottom: "16px" }}>{locale === "hi" ? "प्रणाली अभिलेख गणना" : "Institute Record Inventory"}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "16px" }}>
            <div>
              <span style={{ fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
                {locale === "hi" ? "शोध पत्र" : "Source Papers"}
              </span>
              <strong style={{ display: "block", fontSize: "22px", fontFamily: "var(--font-mono)" }}>
                {diagnostics.counts.papers}
              </strong>
            </div>
            <div>
              <span style={{ fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
                {locale === "hi" ? "जांच मामले" : "Investigations"}
              </span>
              <strong style={{ display: "block", fontSize: "22px", fontFamily: "var(--font-mono)" }}>
                {diagnostics.counts.investigations}
              </strong>
            </div>
            <div>
              <span style={{ fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
                {locale === "hi" ? "कार्यप्रवाह" : "Workflow Runs"}
              </span>
              <strong style={{ display: "block", fontSize: "22px", fontFamily: "var(--font-mono)" }}>
                {diagnostics.counts.workflow_runs}
              </strong>
            </div>
            <div>
              <span style={{ fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
                {locale === "hi" ? "प्रयोग परीक्षण" : "Experiment Jobs"}
              </span>
              <strong style={{ display: "block", fontSize: "22px", fontFamily: "var(--font-mono)" }}>
                {diagnostics.counts.experiment_jobs}
              </strong>
            </div>
            <div>
              <span style={{ fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
                {locale === "hi" ? "वैज्ञानिक मूल्यांकन" : "Evaluations"}
              </span>
              <strong style={{ display: "block", fontSize: "22px", fontFamily: "var(--font-mono)" }}>
                {diagnostics.counts.scientific_evaluations}
              </strong>
            </div>
            <div>
              <span style={{ fontSize: "12px", color: "var(--color-peat-subtle)", fontWeight: 700 }}>
                {locale === "hi" ? "सुरक्षित बैकअप" : "System Backups"}
              </span>
              <strong style={{ display: "block", fontSize: "22px", fontFamily: "var(--font-mono)" }}>
                {diagnostics.counts.system_backups}
              </strong>
            </div>
          </div>
        </section>
      )}

      {/* Backups & Recovery */}
      <section className="card" style={{ backgroundColor: "#FFFFFF" }}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "16px", marginBottom: "16px" }}>
          <div>
            <h3>{locale === "hi" ? "समन्वित सुरक्षा बैकअप" : "Cryptographic System Backups"}</h3>
            <p style={{ fontSize: "14px", color: "var(--color-peat-subtle)", margin: 0 }}>
              {isPlain
                ? (locale === "hi"
                    ? "डेटाबेस और फ़ाइलों का एक साथ अपरिवर्तनीय बैकअप बंडल तैयार किया जाता है, जिसे किसी भी समय सत्यापित किया जा सकता है।"
                    : "Atomic backup bundles linking database state and storage files with cryptographic SHA-256 manifests.")
                : "Coordinated database dump and artifact archive with pre-restore and post-restore referential integrity checks."}
            </p>
          </div>

          {canMutate && (
            <button
              type="button"
              className="btn-primary"
              disabled={backingUp}
              title={backingUp ? "Backup is currently being created..." : undefined}
              onClick={handleBackup}
            >
              {backingUp
                ? (locale === "hi" ? "बैकअप तैयार हो रहा है…" : "Creating Backup…")
                : (locale === "hi" ? "नया बैकअप बनाएं" : "Create Coordinated Backup")}
            </button>
          )}
        </div>

        {backups.length === 0 ? (
          <p style={{ color: "var(--color-peat-subtle)", padding: "20px 0" }}>
            {locale === "hi" ? "अभी तक कोई बैकअप दर्ज नहीं है।" : "No system backup bundles created yet."}
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {backups.map((b) => (
              <div
                key={b.id}
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "12px",
                  padding: "12px 16px",
                  border: "1px solid var(--color-rule)",
                  borderRadius: "var(--radius-sm)",
                  backgroundColor: "var(--color-paper)",
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                    <span className="badge" style={{ backgroundColor: "var(--color-teal-light)", color: "var(--color-teal)" }}>
                      {b.status}
                    </span>
                    <strong style={{ fontFamily: "var(--font-mono)", fontSize: "14px" }}>{b.backup_id}</strong>
                    <HashFingerprint hash={b.manifest_sha256} label="Manifest Hash" />
                  </div>
                  <small style={{ color: "var(--color-peat-subtle)" }}>
                    {b.artifact_count} artifacts · {formatBytes(b.total_bytes)} · {new Date(b.created_at).toLocaleString()}
                  </small>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
