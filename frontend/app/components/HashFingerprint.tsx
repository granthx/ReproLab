"use client";

import React, { useState } from "react";
import { useLens } from "../lib/lens";

type HashFingerprintProps = {
  hash: string | null | undefined;
  label?: string;
  forceFull?: boolean;
};

// Deterministically generate 8 visual colors from a SHA-256 string
function hashToColors(hash: string): string[] {
  if (!hash || hash.length < 16) {
    return Array(8).fill("#D6D8CF");
  }
  const colors: string[] = [];
  for (let i = 0; i < 8; i++) {
    const sub = hash.slice(i * 2, i * 2 + 2);
    const byte = parseInt(sub, 16) || 0;
    const hue = Math.round((byte * 360) / 255);
    const sat = 70 + (byte % 20);
    const light = 40 + (byte % 25);
    colors.push(`hsl(${hue}, ${sat}%, ${light}%)`);
  }
  return colors;
}

export function HashFingerprint({ hash, label, forceFull = false }: HashFingerprintProps) {
  const { isPlain } = useLens();
  const [copied, setCopied] = useState(false);

  if (!hash) {
    return <span style={{ color: "var(--color-peat-muted)", fontSize: "13px" }}>No hash recorded</span>;
  }

  const colors = hashToColors(hash);

  const handleCopy = async () => {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(hash);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // Fallback
    }
  };

  return (
    <span
      className="hash-fingerprint-wrapper"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "8px",
        fontFamily: "var(--font-mono)",
        fontSize: "13px",
      }}
    >
      {/* 8-cell color strip */}
      <span
        className="fingerprint-strip"
        title={`Visual Fingerprint for SHA-256: ${hash}`}
        aria-hidden="true"
        style={{
          display: "inline-flex",
          border: "1px solid var(--color-peat)",
          borderRadius: "3px",
          overflow: "hidden",
          height: "14px",
          boxShadow: "1px 1px 0px var(--color-peat)",
        }}
      >
        {colors.map((c, idx) => (
          <span
            key={idx}
            className="fingerprint-cell"
            style={{
              width: "7px",
              height: "14px",
              backgroundColor: c,
              display: "inline-block",
            }}
          />
        ))}
      </span>

      {/* Hex display & Copy button */}
      {(!isPlain || forceFull) ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <code
            style={{
              backgroundColor: "var(--color-paper)",
              padding: "2px 6px",
              borderRadius: "3px",
              border: "1px solid var(--color-rule)",
              fontWeight: 600,
              fontSize: "12px",
              letterSpacing: "0.02em",
            }}
          >
            {hash.slice(0, 10)}…{hash.slice(-8)}
          </code>
          <button
            type="button"
            onClick={handleCopy}
            className="btn-secondary"
            style={{
              minHeight: "28px",
              height: "28px",
              padding: "2px 8px",
              fontSize: "11px",
              boxShadow: "none",
            }}
            title={`Copy full hash: ${hash}`}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </span>
      ) : (
        <span style={{ fontSize: "13px", color: "var(--color-peat-subtle)", fontFamily: "var(--font-body)" }}>
          {label || "Fingerprint verified"}
        </span>
      )}
    </span>
  );
}

