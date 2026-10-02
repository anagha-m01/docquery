import React from "react";

/**
 * A plain, flat monogram mark — no gradients, no glow/drop-shadow filters.
 * Intentionally simple: a rounded square in the accent color with a "D"
 * wordmark-style glyph, so it reads as a clean product icon rather than
 * an AI-generated logo.
 */
export default function Logo({ size = 40, className = "" }) {
  return (
    <div
      className={`docquery-logo ${className}`}
      style={{ width: size, height: size, display: "inline-block" }}
      aria-label="DocQuery logo"
    >
      <svg
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ width: "100%", height: "100%" }}
      >
        <rect width="40" height="40" rx="10" fill="var(--accent)" />
        <path
          d="M13 11h6.5c4.7 0 7.5 3 7.5 9s-2.8 9-7.5 9H13V11Z"
          stroke="var(--accent-contrast)"
          strokeWidth="2.4"
          strokeLinejoin="round"
          fill="none"
        />
        <circle
          cx="20"
          cy="20"
          r="1.6"
          fill="var(--accent-contrast)"
        />
      </svg>
    </div>
  );
}
