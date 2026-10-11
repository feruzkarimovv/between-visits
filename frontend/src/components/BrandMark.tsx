"use client";

import { useId } from "react";

/**
 * Between Visits mark: two visits (dots) bridged by a voice waveform (the call
 * in between). Decorative; the wordmark next to it carries the name.
 */
export function BrandMark({ className = "size-8", live = false }: { className?: string; live?: boolean }) {
  const gradient = `bv-mark-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" className={`shrink-0 ${className}`} aria-hidden>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#14897a" />
          <stop offset="1" stopColor="#0a4a44" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
      <rect x="0.5" y="0.5" width="31" height="31" rx="8.5" fill="none" stroke="#ffffff" strokeOpacity="0.14" />
      <circle cx="7.5" cy="16" r="2.6" fill="#ffffff" />
      <circle cx="24.5" cy="16" r="2.6" fill="#ffffff" />
      <g className={live ? "bv-wave" : undefined} fill="#5eead4">
        <rect x="11.6" y="12.5" width="2" height="7" rx="1" style={live ? { animationDelay: "-0.3s" } : undefined} />
        <rect x="15" y="9.5" width="2" height="13" rx="1" style={live ? { animationDelay: "-0.6s" } : undefined} />
        <rect x="18.4" y="11.5" width="2" height="9" rx="1" style={live ? { animationDelay: "-0.9s" } : undefined} />
      </g>
    </svg>
  );
}
