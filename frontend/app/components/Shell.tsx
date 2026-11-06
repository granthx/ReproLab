"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLens } from "../lib/lens";
import { useI18n } from "../lib/i18n";
import { useAuth, STANDARD_TOKENS, UserRole } from "../lib/auth";

type ShellProps = {
  children: React.ReactNode;
};

export function Shell({ children }: ShellProps) {
  const pathname = usePathname();
  const { lens, isPlain, toggleLens } = useLens();
  const { locale, toggleLocale, t } = useI18n();
  const { user, role, loginAs, setCustomToken } = useAuth();
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [customTokenInput, setCustomTokenInput] = useState("");

  const isActive = (path: string) => {
    if (path === "/" && pathname === "/") return true;
    if (path !== "/" && pathname.startsWith(path)) return true;
    return false;
  };

  return (
    <div className="shell-root" style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      {/* Topbar */}
      <header className="topbar">
        <div className="shell" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "16px" }}>
          {/* Brand */}
          <Link href="/" className="brand-lockup">
            <div className="brand-badge" aria-hidden="true">RL</div>
            <div className="brand-titles">
              <span className="brand-eyebrow">{t("institute_subtitle")}</span>
              <h1>Repro<span>Lab</span></h1>
            </div>
          </Link>

          {/* Navigation */}
          <nav className="main-nav" aria-label="Main Navigation">
            <Link href="/" className={isActive("/") ? "active" : ""}>
              {t("nav_home")}
            </Link>
            <Link href="/investigations" className={isActive("/investigations") ? "active" : ""}>
              {t("nav_investigations")}
            </Link>
            <Link href="/papers" className={isActive("/papers") ? "active" : ""}>
              {t("nav_papers")}
            </Link>
            <Link href="/scientists" className={isActive("/scientists") ? "active" : ""}>
              {t("nav_scientists")}
            </Link>
            <Link href="/status" className={isActive("/status") ? "active" : ""}>
              {t("nav_status")}
            </Link>
          </nav>

          {/* Header Controls: Lens + Lang + Role */}
          <div className="header-controls">
            {/* The Signature Lens Switch */}
            <button
              type="button"
              className="lens-switch-button"
              onClick={toggleLens}
              aria-pressed={lens === "technical"}
              title={t("lens_tooltip")}
            >
              <span className={`lens-pill ${isPlain ? "active" : ""}`}>
                {t("lens_plain")}
              </span>
              <span className={`lens-pill ${!isPlain ? "active" : ""}`}>
                {t("lens_technical")}
              </span>
            </button>

            {/* Language Toggle */}
            <button
              type="button"
              className="lang-toggle-button"
              onClick={toggleLocale}
              title={locale === "en" ? "हिंदी में बदलें" : "Switch to English"}
              aria-label="Language Switcher"
            >
              {locale === "en" ? "हिंदी" : "EN"}
            </button>

            {/* Role Badge & Switcher */}
            <button
              type="button"
              className="role-badge-button"
              onClick={() => setRoleModalOpen(true)}
              title={t("role_switch_prompt")}
            >
              <span className={`role-dot ${role}`} aria-hidden="true" />
              <span>{STANDARD_TOKENS[role]?.label || role}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div style={{ flex: 1, padding: "24px 0" }}>
        {children}
      </div>

      {/* Footer */}
      <footer style={{ borderTop: "var(--border-thick)", backgroundColor: "var(--color-chalk)", padding: "24px 0", marginTop: "auto" }}>
        <div className="shell" style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "16px", fontSize: "14px" }}>
          <div>
            <strong>ReproLab</strong> · Evidence before inference · The Glass Box for Computational Science
          </div>
          <div style={{ display: "flex", gap: "16px", color: "var(--color-peat-subtle)" }}>
            <span>Lens: <strong>{lens}</strong></span>
            <span>Language: <strong>{locale.toUpperCase()}</strong></span>
            <span>Role: <strong>{role}</strong></span>
          </div>
        </div>
      </footer>

      {/* Role / Authentication Switcher Modal */}
      {roleModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="role-modal-title"
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(38, 28, 20, 0.65)",
            backdropFilter: "blur(2px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px",
            zIndex: 1000,
          }}
          onClick={() => setRoleModalOpen(false)}
        >
          <div
            className="card"
            style={{ maxWidth: "480px", width: "100%", backgroundColor: "var(--color-paper)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3 id="role-modal-title">{t("role_switch_prompt")}</h3>
              <button
                type="button"
                className="btn-secondary"
                style={{ minHeight: "36px", height: "36px", padding: "4px 10px" }}
                onClick={() => setRoleModalOpen(false)}
              >
                ✕
              </button>
            </div>

            <p style={{ fontSize: "14px", color: "var(--color-peat-subtle)", marginBottom: "16px" }}>
              {t("role_read_only_notice")}
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "20px" }}>
              {(["viewer", "operator", "admin"] as UserRole[]).map((r) => {
                const info = STANDARD_TOKENS[r];
                const selected = role === r;
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={async () => {
                      await loginAs(r);
                      setRoleModalOpen(false);
                    }}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "12px",
                      padding: "12px 16px",
                      borderRadius: "var(--radius-card)",
                      border: selected ? "2px solid var(--color-teal)" : "2px solid var(--color-peat)",
                      backgroundColor: selected ? "var(--color-teal-light)" : "#FFFFFF",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span className={`role-dot ${r}`} style={{ marginTop: "4px" }} />
                    <div>
                      <strong style={{ display: "block", fontSize: "16px" }}>{info.label}</strong>
                      <span style={{ fontSize: "13px", color: "var(--color-peat-subtle)" }}>{info.desc}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            <form
              onSubmit={async (e) => {
                e.preventDefault();
                if (customTokenInput.trim()) {
                  await setCustomToken(customTokenInput.trim());
                  setCustomTokenInput("");
                  setRoleModalOpen(false);
                }
              }}
              style={{ borderTop: "1px solid var(--color-rule)", paddingTop: "16px" }}
            >
              <label className="form-label" htmlFor="custom-token-input">Custom Bearer Token / API Key</label>
              <div style={{ display: "flex", gap: "8px" }}>
                <input
                  id="custom-token-input"
                  className="form-input"
                  type="password"
                  placeholder="Paste token or key…"
                  value={customTokenInput}
                  onChange={(e) => setCustomTokenInput(e.target.value)}
                />
                <button type="submit" className="btn-primary" style={{ whiteSpace: "nowrap" }}>
                  Save
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

