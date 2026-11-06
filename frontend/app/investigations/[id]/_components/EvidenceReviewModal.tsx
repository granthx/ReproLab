"use client";

import React, { useState, FormEvent } from "react";
import { api } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import { useI18n } from "../../../lib/i18n";

type EvidenceReviewModalProps = {
  evidenceId: string;
  evidenceLocator: string;
  isOpen: boolean;
  onClose: () => void;
  onReviewed: () => Promise<void>;
};

export function EvidenceReviewModal({
  evidenceId,
  evidenceLocator,
  isOpen,
  onClose,
  onReviewed,
}: EvidenceReviewModalProps) {
  const { user } = useAuth();
  const { locale, t } = useI18n();

  const [outcome, setOutcome] = useState<"accepted_for_protocol" | "rejected" | "unresolved">("accepted_for_protocol");
  const [reviewerLabel, setReviewerLabel] = useState(user?.username || "Researcher");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!notes.trim()) {
      setError(locale === "hi" ? "कृपया समीक्षा नोट्स दर्ज करें।" : "Review notes are required.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await api(`/evidence/${encodeURIComponent(evidenceId)}/reviews`, {
        method: "POST",
        body: JSON.stringify({
          review_method: "manual_review",
          outcome,
          reviewer_label: reviewerLabel.trim() || "Researcher",
          notes: notes.trim(),
        }),
      });
      await onReviewed();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record review.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="review-modal-title"
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
      onClick={onClose}
    >
      <div
        className="card"
        style={{ maxWidth: "520px", width: "100%", backgroundColor: "var(--color-paper)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h3 id="review-modal-title">{t("action_record_review")}</h3>
          <button
            type="button"
            className="btn-secondary"
            style={{ minHeight: "36px", height: "36px", padding: "4px 10px" }}
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <p style={{ fontSize: "14px", color: "var(--color-peat-subtle)", marginBottom: "16px" }}>
          {locale === "hi"
            ? `साक्ष्य मद: ${evidenceLocator} के लिए एक प्रामाणिक मानव समीक्षा दर्ज करें। यह स्वचालित सत्यापन नहीं है।`
            : `Record an attributed human review for: ${evidenceLocator}. Manual review is not automated source verification.`}
        </p>

        {error && <div className="notice notice-error" style={{ marginBottom: "16px" }}>{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="review-outcome-select">
              {locale === "hi" ? "समीक्षा परिणाम *" : "Review Outcome *"}
            </label>
            <select
              id="review-outcome-select"
              className="form-select"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as any)}
            >
              <option value="accepted_for_protocol">
                {locale === "hi" ? "स्वीकृत (प्रोटोकॉल के लिए उपयुक्त)" : "Accepted for Protocol"}
              </option>
              <option value="rejected">
                {locale === "hi" ? "अस्वीकृत (गलत या अनुपयुक्त)" : "Rejected (Invalid / Contradictory)"}
              </option>
              <option value="unresolved">
                {locale === "hi" ? "अनिर्णीत (अतिरिक्त साक्ष्य आवश्यक)" : "Unresolved (Ambiguous / Needs Inquiry)"}
              </option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="reviewer-label-input">
              {locale === "hi" ? "समीक्षक का नाम / पदनाम *" : "Reviewer Name / Label *"}
            </label>
            <input
              id="reviewer-label-input"
              className="form-input"
              type="text"
              value={reviewerLabel}
              onChange={(e) => setReviewerLabel(e.target.value)}
              required
              maxLength={120}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="review-notes-textarea">
              {locale === "hi" ? "समीक्षा नोट्स एवं औचित्य *" : "Review Notes & Rationale *"}
            </label>
            <textarea
              id="review-notes-textarea"
              className="form-textarea"
              placeholder={locale === "hi" ? "साक्ष्य की प्रामाणिकता और संदर्भ के बारे में विस्तृत टिप्पणी दर्ज करें…" : "Detail how this evidence was verified against the primary document…"}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              required
            />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "20px" }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={submitting}
              title={submitting ? "Review submission in progress..." : undefined}
            >
              {locale === "hi" ? "रद्द करें" : "Cancel"}
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={submitting || !notes.trim()}
              title={!notes.trim() ? "Review notes are required" : submitting ? "Recording review..." : undefined}
            >
              {submitting ? (locale === "hi" ? "दर्ज हो रहा है…" : "Recording…") : t("action_record_review")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
