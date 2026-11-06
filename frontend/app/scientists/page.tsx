"use client";

import React, { useEffect, useState } from "react";
import { api, Scientist } from "../lib/api";
import { useLens } from "../lib/lens";
import { useI18n } from "../lib/i18n";

export default function ScientistsPage() {
  const { isPlain } = useLens();
  const { locale, t } = useI18n();

  const [scientists, setScientists] = useState<Scientist[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function loadScientists() {
      setLoading(true);
      setError(null);
      try {
        const list = await api<Scientist[]>("/scientists", { signal: controller.signal });
        if (active) setScientists(list);
      } catch (err) {
        if (active && !(err instanceof Error && err.name === "AbortError")) {
          setError(err instanceof Error ? err.message : t("error_connection"));
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadScientists();
    return () => {
      active = false;
      controller.abort();
    };
  }, [t]);

  return (
    <main className="shell">
      {/* Header */}
      <div style={{ marginBottom: "28px" }}>
        <span className="badge badge-paper" style={{ marginBottom: "8px", borderStyle: "solid" }}>
          {locale === "hi" ? "शोध पाइपलाइन भूमिकाएं" : "Scientific Pipeline Role Registry"}
        </span>
        <h2>{locale === "hi" ? "12 विशेष वैज्ञानिक अनुसंधान भूमिकाएं" : "The 12 Research Pipeline Personas"}</h2>
        <div className="notice notice-info" style={{ marginTop: "12px" }}>
          <strong>
            {locale === "hi"
              ? "पाइपलाइन अखंडता सिद्धांत: पंजीकृत भूमिकाएं केवल स्वीकृत प्रोटोकॉल के तहत निष्पादित होती हैं।"
              : "Pipeline Integrity Architecture: Roles execute strictly against frozen protocol specifications."}
          </strong>
          <p style={{ fontSize: "14px", marginTop: "4px", margin: 0 }}>
            {isPlain
              ? (locale === "hi"
                  ? "ये 12 भूमिकाएं संपूर्ण वैज्ञानिक पुनरावृत्ति पाइपलाइन में विशिष्ट जिम्मेदारियां संभालती हैं: साहित्य से दावों का निष्कर्षण, कार्यप्रणाली ऑडिट, सैंडबॉक्स निष्पादन और विल्सन कॉन्फिडेंस स्कोरिंग।"
                  : "These 12 roles enforce modular separation of scientific responsibilities: literature extraction is isolated from protocol design, protocol design is frozen prior to execution, and sandbox execution is independently scored by statistical algorithms.")
              : "Declarative research role specifications versioned at 1.0.0. Each defines permitted tools, model routing ceilings, evidence extraction schemas, and sandbox execution boundaries to guarantee peer-review reproducibility."}
          </p>
        </div>
      </div>

      {error && <div className="notice notice-error">{error}</div>}

      {loading ? (
        <div className="card" style={{ padding: "40px", textAlign: "center" }}>
          <div className="skeleton" style={{ height: "40px", width: "50%", margin: "0 auto 16px" }} />
          <div className="skeleton" style={{ height: "24px", width: "30%", margin: "0 auto" }} />
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
          {scientists.map((sc, index) => (
            <article
              key={sc.role_id}
              className="card"
              style={{
                backgroundColor: "#FFFFFF",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                  <div>
                    <span style={{ fontSize: "12px", fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--color-peat-subtle)" }}>
                      ROLE {String(index + 1).padStart(2, "0")} · {sc.role_id.toUpperCase()}
                    </span>
                    <h3 style={{ fontSize: "var(--text-xl)", marginTop: "2px" }}>{sc.name}</h3>
                  </div>
                  <span className="badge" style={{ backgroundColor: "var(--color-chalk)", fontSize: "11px" }}>
                    v{sc.version}
                  </span>
                </div>

                <p style={{ fontWeight: 700, fontSize: "15px", color: "var(--color-teal)", marginBottom: "8px" }}>
                  {sc.specialty}
                </p>

                <p style={{ fontSize: "14px", color: "var(--color-peat)", marginBottom: "14px" }}>
                  <strong>{locale === "hi" ? "संवैधानिक जनादेश: " : "Mandate: "}</strong>
                  {sc.mandate}
                </p>

                {/* Responsibilities */}
                {sc.responsibilities && sc.responsibilities.length > 0 && (
                  <div style={{ marginBottom: "12px" }}>
                    <span style={{ fontSize: "12px", textTransform: "uppercase", fontWeight: 700, color: "var(--color-peat-subtle)" }}>
                      {locale === "hi" ? "जिम्मेदारियां" : "Responsibilities"}
                    </span>
                    <ul style={{ paddingLeft: "18px", fontSize: "13px", marginTop: "4px" }}>
                      {sc.responsibilities.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Prohibitions */}
                {sc.prohibited_actions && sc.prohibited_actions.length > 0 && (
                  <div style={{ marginBottom: "16px", backgroundColor: "var(--color-madder-light)", padding: "10px 12px", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-madder)" }}>
                    <span style={{ fontSize: "11px", textTransform: "uppercase", fontWeight: 800, color: "var(--color-madder)" }}>
                      {locale === "hi" ? "सख्त प्रतिबंध (क्या नहीं कर सकते)" : "Strict Prohibitions"}
                    </span>
                    <ul style={{ paddingLeft: "18px", fontSize: "12px", marginTop: "4px", color: "var(--color-peat)" }}>
                      {sc.prohibited_actions.map((p, idx) => (
                        <li key={idx}>✕ {p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Footer specs */}
              <div style={{ borderTop: "1px solid var(--color-rule)", paddingTop: "10px", display: "flex", justifyContent: "space-between", fontSize: "12px", color: "var(--color-peat-subtle)" }}>
                <span>
                  Availability: <strong>{sc.availability}</strong>
                </span>
                <span>
                  Permitted Tools: <strong>{sc.permitted_tools?.length ?? 0}</strong>
                </span>
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
