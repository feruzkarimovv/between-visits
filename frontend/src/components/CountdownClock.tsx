"use client";

import { Timer } from "lucide-react";
import { useNow } from "@/lib/hooks";
import { formatAbsolute, parseTs } from "@/lib/format";
import { cn } from "./ui/primitives";

const DAY_S = 24 * 3600;

function hms(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(sec)}`;
}

/**
 * 24-hour reporting clock. Neutral above 6 h, amber under 6 h, red under 1 h.
 * When `stoppedAt` is set (report received), the clock freezes and shows the margin.
 * The ring shows the share of the 24 hours still left.
 */
export function CountdownClock({
  dueAt,
  stoppedAt,
  size = "lg",
  label = "Time left to report to sponsor",
}: {
  dueAt: string;
  stoppedAt?: string | null;
  size?: "sm" | "lg";
  label?: string;
}) {
  const now = useNow();
  const due = parseTs(dueAt) ?? 0;
  const end = parseTs(stoppedAt ?? null) ?? now;
  const remaining = (due - end) / 1000;
  const stopped = !!stoppedAt;
  const overdue = remaining < 0;
  const tone = stopped
    ? overdue
      ? "red"
      : "green"
    : overdue || remaining < 3600
      ? "red"
      : remaining < 6 * 3600
        ? "amber"
        : "neutral";

  const toneClass = {
    neutral: "border-line bg-white text-ink",
    amber: "border-amber-400 bg-amber-50 text-amber-950",
    red: "border-red-500 bg-red-50 text-red-900",
    green: "border-green-400 bg-green-50 text-green-900",
  }[tone];

  if (size === "sm") {
    return (
      <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-sm font-medium tabular", toneClass)} title={`Due ${formatAbsolute(dueAt)}`}>
        <Timer className="size-3.5" aria-hidden />
        {stopped ? (overdue ? "Late" : "On time") : now === 0 ? "--:--:--" : overdue ? `Overdue ${hms(-remaining)}` : `${hms(remaining)} left`}
      </span>
    );
  }

  const ready = now !== 0 || stopped;
  const fraction = ready ? Math.max(0, Math.min(1, remaining / DAY_S)) : 1;
  const r = 52;
  const c = 2 * Math.PI * r;
  const stroke = { neutral: "#0d655b", amber: "#d97706", red: "#dc2626", green: "#15803d" }[tone];
  const track = { neutral: "#e2e7e5", amber: "#fde68a", red: "#fecaca", green: "#bbf7d0" }[tone];

  return (
    <div className={cn("flex h-full flex-col justify-center gap-5 rounded-2xl border-2 px-5 py-5 shadow-card sm:flex-row sm:items-center", toneClass)} role="timer" aria-live="off">
      <div className="relative mx-auto size-32 shrink-0 sm:mx-0">
        <svg viewBox="0 0 120 120" className="size-full -rotate-90" aria-hidden>
          <circle cx="60" cy="60" r={r} fill="none" stroke={track} strokeWidth="9" />
          <circle
            cx="60"
            cy="60"
            r={r}
            fill="none"
            stroke={stroke}
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - fraction)}
            className="transition-[stroke-dashoffset] duration-1000 ease-linear"
          />
          {Array.from({ length: 24 }, (_, i) => (
            <line
              key={i}
              x1="60"
              y1="4"
              x2="60"
              y2={i % 6 === 0 ? "10" : "7"}
              stroke="currentColor"
              strokeOpacity={i % 6 === 0 ? 0.35 : 0.15}
              strokeWidth="1.5"
              transform={`rotate(${i * 15} 60 60)`}
            />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <Timer className="size-4 opacity-60" aria-hidden />
          <span className="mt-0.5 text-[1.75rem] leading-none font-semibold tracking-tight tabular">{ready ? `${Math.max(0, Math.floor(remaining / 3600))}h` : "24h"}</span>
          <span className="text-sm opacity-75">{stopped ? "to spare" : "left"}</span>
        </div>
      </div>
      <div className="min-w-0 text-center sm:text-left">
        <div className="flex items-center justify-center gap-2 text-sm font-medium opacity-90 sm:justify-start">{stopped ? "Reporting clock stopped" : label}</div>
        <div className="mt-1 font-mono text-4xl font-semibold tracking-tight tabular xl:text-[2.75rem]">
          {now === 0 && !stopped ? "--:--:--" : overdue ? `-${hms(-remaining)}` : hms(remaining)}
        </div>
        <div className="mt-1.5 text-sm leading-5 opacity-90">
          {stopped
            ? overdue
              ? `Received after the deadline (${formatAbsolute(dueAt)})`
              : `Received with ${hms(remaining)} to spare · deadline ${formatAbsolute(dueAt)}`
            : `Due ${formatAbsolute(dueAt)} (24 h after site awareness)`}
        </div>
      </div>
    </div>
  );
}
