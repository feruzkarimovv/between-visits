import { cn } from "./ui/primitives";

/**
 * Small ring for a 0–1 share, with an optional target tick. Decorative: the
 * number and "meets target" text always sit next to it.
 */
export function RingGauge({
  value,
  target,
  tone = "accent",
  size = 56,
  className,
}: {
  value: number | null | undefined;
  target?: number;
  tone?: "accent" | "green" | "amber" | "red" | "gray";
  size?: number;
  className?: string;
}) {
  const r = 22;
  const c = 2 * Math.PI * r;
  const v = typeof value === "number" ? Math.max(0, Math.min(1, value)) : 0;
  const color = { accent: "#127d70", green: "#15803d", amber: "#d97706", red: "#dc2626", gray: "#9ba7a3" }[tone];
  const t = typeof target === "number" ? Math.max(0, Math.min(1, target)) : null;
  return (
    <svg viewBox="0 0 56 56" width={size} height={size} className={cn("shrink-0 -rotate-90", className)} aria-hidden>
      <circle cx="28" cy="28" r={r} fill="none" stroke="#e2e7e5" strokeWidth="6" />
      {typeof value === "number" ? (
        <circle
          cx="28"
          cy="28"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - v)}
          className="bv-draw"
          style={{ ["--bv-len" as string]: c, ["--bv-to" as string]: c * (1 - v) }}
        />
      ) : null}
      {t !== null && t < 1 ? (
        <line x1="28" y1="1.5" x2="28" y2="9.5" stroke="#131b1a" strokeWidth="1.6" strokeLinecap="round" transform={`rotate(${t * 360} 28 28)`} />
      ) : null}
    </svg>
  );
}
