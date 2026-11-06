"use client";

import React from "react";
import { useLens } from "../lib/lens";
import { useI18n } from "../lib/i18n";
import { plainVerdict } from "../lib/plain";

type VerdictBadgeProps = {
  verdict: string | null | undefined;
  size?: "sm" | "md" | "lg";
};

export function VerdictBadge({ verdict, size = "md" }: VerdictBadgeProps) {
  const { isPlain } = useLens();
  const { locale } = useI18n();

  const v = verdict || "not_assessed";
  const { label, explanation } = plainVerdict(v, locale);

  const getBadgeStyle = () => {
    switch (v) {
      case "reproduced":
        return {
          bg: "var(--color-teal)",
          color: "#FFFFFF",
          glyph: "✓",
          border: "2px solid var(--color-peat)",
          pattern: "none",
        };
      case "disconfirmed":
        return {
          bg: "var(--color-madder)",
          color: "#FFFFFF",
          glyph: "✕",
          border: "2px solid var(--color-peat)",
          pattern: "repeating-linear-gradient(45deg, transparent, transparent 6px, rgba(0,0,0,0.2) 6px, rgba(0,0,0,0.2) 12px)",
        };
      case "inconclusive":
        return {
          bg: "var(--color-saffron)",
          color: "var(--color-peat)",
          glyph: "?",
          border: "2px solid var(--color-peat)",
          pattern: "radial-gradient(circle, rgba(0,0,0,0.2) 1.5px, transparent 1.5px) 0 0 / 8px 8px",
        };
      case "execution_failed":
        return {
          bg: "var(--color-chalk)",
          color: "var(--color-peat)",
          glyph: "⚠",
          border: "2px dashed var(--color-peat)",
          pattern: "none",
        };
      default:
        return {
          bg: "var(--color-paper)",
          color: "var(--color-peat-subtle)",
          glyph: "○",
          border: "1px solid var(--color-rule-dark)",
          pattern: "none",
        };
    }
  };

  const style = getBadgeStyle();
  const pad = size === "lg" ? "8px 16px" : size === "sm" ? "2px 8px" : "4px 12px";
  const fontSize = size === "lg" ? "var(--text-base)" : size === "sm" ? "var(--text-xs)" : "var(--text-sm)";

  return (
    <span
      className={`verdict-badge verdict-${v}`}
      title={explanation}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: pad,
        fontSize: fontSize,
        fontFamily: "var(--font-display)",
        fontWeight: 800,
        backgroundColor: style.bg,
        backgroundImage: style.pattern,
        color: style.color,
        border: style.border,
        borderRadius: "var(--radius-pill)",
        boxShadow: "2px 2px 0px var(--color-peat)",
        letterSpacing: "0.02em",
        textTransform: "uppercase",
      }}
    >
      <span aria-hidden="true" style={{ fontWeight: 900 }}>{style.glyph}</span>
      <span>{label}</span>
    </span>
  );
}

