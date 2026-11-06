"use client";

import React, { useId } from "react";

type TheRailProps = {
  claimed: number | null;
  measured: number | null;
  lower: number | null;
  upper: number | null;
  metricName?: string;
  sampleSize?: number | null;
  locale?: "en" | "hi";
};

export function TheRail({
  claimed,
  measured,
  lower,
  upper,
  metricName = "accuracy",
  sampleSize,
  locale = "en",
}: TheRailProps) {
  const patternId = useId();

  // Rail geometry: width 600, height 96, margins 40 to 560
  const startX = 40;
  const endX = 560;
  const width = endX - startX;
  const railY = 48;

  const clampPct = (val: number | null) => {
    if (val === null || val === undefined || !Number.isFinite(val)) return null;
    return Math.max(0, Math.min(1, val));
  };

  const toX = (val: number) => startX + val * width;

  const claimedPct = clampPct(claimed);
  const measuredPct = clampPct(measured);
  const lowerPct = clampPct(lower);
  const upperPct = clampPct(upper);

  const claimedX = claimedPct !== null ? toX(claimedPct) : null;
  const measuredX = measuredPct !== null ? toX(measuredPct) : null;
  const lowerX = lowerPct !== null ? toX(lowerPct) : null;
  const upperX = upperPct !== null ? toX(upperPct) : null;

  const hasInterval = lowerX !== null && upperX !== null && upperX >= lowerX;
  const intervalWidth = hasInterval ? Math.max(4, upperX! - lowerX!) : 0;

  const accessibleLabel = claimedPct !== null && measuredPct !== null && lowerPct !== null && upperPct !== null
    ? (locale === "hi"
        ? `सांख्यिकीय पैमाना: शोध पत्र का दावा ${(claimedPct * 100).toFixed(1)}%, मापा गया परिणाम ${(measuredPct * 100).toFixed(1)}%, और 95% विश्वास अंतराल ${(lowerPct * 100).toFixed(1)}% से ${(upperPct * 100).toFixed(1)}% तक।`
        : `Statistical Rail: Claimed ${(claimedPct * 100).toFixed(1)}%, measured ${(measuredPct * 100).toFixed(1)}%, 95% Wilson confidence interval ${(lowerPct * 100).toFixed(1)}% to ${(upperPct * 100).toFixed(1)}%.`)
    : "Statistical Rail comparison";

  return (
    <div className="the-rail-container" role="img" aria-label={accessibleLabel} style={{ width: "100%", margin: "16px 0" }}>
      <svg
        viewBox="0 0 600 96"
        style={{ width: "100%", height: "auto", overflow: "visible" }}
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <pattern
            id={`rail-hatch-${patternId}`}
            width="8"
            height="8"
            patternTransform="rotate(45 0 0)"
            patternUnits="userSpaceOnUse"
          >
            <line x1="0" y1="0" x2="0" y2="8" stroke="#0B7A75" strokeWidth="2.5" />
          </pattern>
        </defs>

        {/* Base Rail Track */}
        <line x1={startX} y1={railY} x2={endX} y2={railY} stroke="#261C14" strokeWidth="4" strokeLinecap="round" />

        {/* Ticks & Percentage Labels */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((t) => {
          const x = toX(t);
          return (
            <g key={t}>
              <line x1={x} y1={railY - 6} x2={x} y2={railY + 6} stroke="#261C14" strokeWidth="2" />
              <text
                x={x}
                y={railY + 22}
                textAnchor="middle"
                fontSize="12"
                fontFamily="var(--font-mono)"
                fontWeight="700"
                fill="#5E5248"
              >
                {Math.round(t * 100)}%
              </text>
            </g>
          );
        })}

        {/* 95% Wilson Confidence Interval Band */}
        {hasInterval && (
          <g>
            <rect
              x={lowerX!}
              y={railY - 14}
              width={intervalWidth}
              height={28}
              fill={`url(#rail-hatch-${patternId})`}
              stroke="#0B7A75"
              strokeWidth="2"
              rx="3"
              opacity="0.85"
            />
            {/* Interval End Caps */}
            <line x1={lowerX!} y1={railY - 16} x2={lowerX!} y2={railY + 16} stroke="#0B7A75" strokeWidth="2.5" />
            <line x1={upperX!} y1={railY - 16} x2={upperX!} y2={railY + 16} stroke="#0B7A75" strokeWidth="2.5" />
            <text
              x={(lowerX! + upperX!) / 2}
              y={railY + 38}
              textAnchor="middle"
              fontSize="11"
              fontFamily="var(--font-display)"
              fontWeight="700"
              fill="#0B7A75"
            >
              {locale === "hi" ? "95% विश्वास अंतराल" : "95% Wilson Interval"}
            </text>
          </g>
        )}

        {/* Claimed Value Marker (Saffron Solid Indicator) */}
        {claimedX !== null && (
          <g>
            <line
              x1={claimedX}
              y1={railY - 24}
              x2={claimedX}
              y2={railY + 14}
              stroke="#F5A800"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <polygon
              points={`${claimedX},${railY - 10} ${claimedX - 6},${railY - 24} ${claimedX + 6},${railY - 24}`}
              fill="#F5A800"
              stroke="#261C14"
              strokeWidth="1.5"
            />
            <text
              x={claimedX}
              y={railY - 28}
              textAnchor="middle"
              fontSize="12"
              fontFamily="var(--font-display)"
              fontWeight="800"
              fill="#261C14"
            >
              {locale === "hi" ? "दावा" : "Claim"}: {(claimedPct! * 100).toFixed(1)}%
            </text>
          </g>
        )}

        {/* Measured Value Diamond Marker (Teal) */}
        {measuredX !== null && (
          <g>
            <circle cx={measuredX} cy={railY} r="7" fill="#0B7A75" stroke="#261C14" strokeWidth="2" />
            <circle cx={measuredX} cy={railY} r="3" fill="#FFFFFF" />
            <text
              x={measuredX}
              y={railY - 12}
              textAnchor="middle"
              fontSize="12"
              fontFamily="var(--font-mono)"
              fontWeight="800"
              fill="#0B7A75"
            >
              {(measuredPct! * 100).toFixed(1)}%
            </text>
          </g>
        )}
      </svg>

      {/* Legend & Details */}
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "8px", marginTop: "4px", fontSize: "14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {claimedPct !== null && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <span style={{ width: "12px", height: "4px", backgroundColor: "var(--color-saffron)", display: "inline-block", border: "1px solid #261C14" }} />
              <strong>{locale === "hi" ? "दावा किया गया परिणाम" : "Claimed Metric"}:</strong> {(claimedPct * 100).toFixed(1)}%
            </span>
          )}
          {measuredPct !== null && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <span style={{ width: "10px", height: "10px", borderRadius: "50%", backgroundColor: "var(--color-teal)", display: "inline-block", border: "1px solid #261C14" }} />
              <strong>{locale === "hi" ? "मापा गया परिणाम" : "Independent Measurement"}:</strong> {(measuredPct * 100).toFixed(1)}%
            </span>
          )}
        </div>
        {lowerPct !== null && upperPct !== null && (
          <span style={{ color: "var(--color-peat-subtle)" }}>
            {locale === "hi" ? "विश्वसनीय सीमा" : "Honest Range"}: <code>{(lowerPct * 100).toFixed(1)}% – {(upperPct * 100).toFixed(1)}%</code>
            {sampleSize ? ` (N=${sampleSize})` : ""}
          </span>
        )}
      </div>
    </div>
  );
}

