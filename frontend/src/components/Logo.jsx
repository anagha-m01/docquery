import React from "react";

export default function Logo({ size = 64, className = "" }) {
  return (
    <div
      className={`docquery-logo ${className}`}
      style={{ width: size, height: size, display: "inline-block" }}
      aria-label="DocQuery Logo"
    >
      <svg
        viewBox="0 0 80 80"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="docquery-logo-svg"
        style={{ width: "100%", height: "100%", overflow: "visible" }}
      >
        <defs>
          <linearGradient id="dqDocGrad" x1="16" y1="8" x2="56" y2="64" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#1a1930" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#0d0d16" stopOpacity="0.98" />
          </linearGradient>

          <linearGradient id="dqDocBorder" x1="16" y1="8" x2="56" y2="64" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#7c6fff" />
            <stop offset="50%" stopColor="#9084f9" />
            <stop offset="100%" stopColor="#ff6f91" />
          </linearGradient>

          <linearGradient id="dqFoldGrad" x1="42" y1="8" x2="56" y2="22" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#a78bfa" />
            <stop offset="100%" stopColor="#7c6fff" />
          </linearGradient>

          <linearGradient id="dqLensBorder" x1="33" y1="33" x2="63" y2="63" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#4fffb0" />
            <stop offset="45%" stopColor="#7c6fff" />
            <stop offset="100%" stopColor="#ff6f91" />
          </linearGradient>

          <linearGradient id="dqTailGrad" x1="58" y1="58" x2="70" y2="70" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#7c6fff" />
            <stop offset="100%" stopColor="#ff6f91" />
          </linearGradient>

          <linearGradient id="dqSparkleGrad" x1="40" y1="40" x2="56" y2="56" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="40%" stopColor="#e0e7ff" />
            <stop offset="100%" stopColor="#4fffb0" />
          </linearGradient>

          <linearGradient id="dqLine1" x1="22" y1="26" x2="38" y2="26" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#7c6fff" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#a78bfa" stopOpacity="0.4" />
          </linearGradient>

          <linearGradient id="dqLine2" x1="22" y1="33" x2="42" y2="33" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ff6f91" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#f472b6" stopOpacity="0.4" />
          </linearGradient>

          <linearGradient id="dqLine3" x1="22" y1="40" x2="34" y2="40" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#4fffb0" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#34d399" stopOpacity="0.4" />
          </linearGradient>

          <filter id="dqGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#7c6fff" floodOpacity="0.4" />
          </filter>

          <filter id="dqLensGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#4fffb0" floodOpacity="0.35" />
          </filter>
        </defs>

        {/* Ambient Glow Backing */}
        <circle cx="40" cy="40" r="26" fill="#7c6fff" opacity="0.14" filter="blur(14px)" />

        {/* Document Body */}
        <path
          d="M 21 8 L 42 8 L 56 22 L 56 57 Q 56 62 51 62 L 21 62 Q 16 62 16 57 L 16 13 Q 16 8 21 8 Z"
          fill="url(#dqDocGrad)"
          stroke="url(#dqDocBorder)"
          strokeWidth="2.5"
          filter="url(#dqGlow)"
        />

        {/* Document Fold Flap */}
        <path
          d="M 42 8 L 42 18 Q 42 22 46 22 L 56 22 Z"
          fill="url(#dqFoldGrad)"
          stroke="url(#dqDocBorder)"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />

        {/* Document Structured Data Stream Lines */}
        <rect x="22" y="27" width="16" height="3" rx="1.5" fill="url(#dqLine1)" />
        <rect x="22" y="34" width="22" height="3" rx="1.5" fill="url(#dqLine2)" />
        <rect x="22" y="41" width="14" height="3" rx="1.5" fill="url(#dqLine3)" />
        <rect x="22" y="48" width="18" height="3" rx="1.5" fill="url(#dqLine1)" opacity="0.6" />

        {/* Query Lens (Outer Q-Ring) */}
        <circle
          cx="48"
          cy="48"
          r="16"
          fill="#111118"
          stroke="url(#dqLensBorder)"
          strokeWidth="3.5"
          filter="url(#dqLensGlow)"
        />

        {/* Query Lens Glass Reflection */}
        <path
          d="M 38 42 A 12 12 0 0 1 54 38"
          stroke="#ffffff"
          strokeWidth="1.5"
          strokeLinecap="round"
          opacity="0.3"
        />

        {/* Query Lens Tail (forming Q) */}
        <path
          d="M 59 59 L 70 70"
          stroke="url(#dqTailGrad)"
          strokeWidth="4.5"
          strokeLinecap="round"
        />

        {/* AI Sparkle Node inside Lens */}
        <path
          className="dq-sparkle"
          d="M 48 39 Q 48 48 39 48 Q 48 48 48 57 Q 48 48 57 48 Q 48 48 48 39 Z"
          fill="url(#dqSparkleGrad)"
        />

        {/* Accent Star */}
        <path
          d="M 12 18 Q 12 21 9 21 Q 12 21 12 24 Q 12 21 15 21 Q 12 21 12 18 Z"
          fill="#ff6f91"
          opacity="0.85"
        />
      </svg>
    </div>
  );
}
