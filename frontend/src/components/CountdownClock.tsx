"use client";

import { Timer } from "lucide-react";
import { useNow } from "@/lib/hooks";
import { formatAbsolute, parseTs } from "@/lib/format";
import { cn } from "./ui/primitives";

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

  return (
    <div className={cn("rounded-lg border-2 px-5 py-4", toneClass)} role="timer" aria-live="off">
      <div className="flex items-center gap-2 text-sm font-medium opacity-90">
        <Timer className="size-4" aria-hidden />
        {stopped ? "Reporting clock stopped" : label}
      </div>
      <div className="mt-1 font-mono text-4xl font-semibold tracking-tight tabular sm:text-5xl">
        {now === 0 && !stopped ? "--:--:--" : overdue ? `-${hms(-remaining)}` : hms(remaining)}
      </div>
      <div className="mt-1 text-sm opacity-90">
        {stopped
          ? overdue
            ? `Received after the deadline (${formatAbsolute(dueAt)})`
            : `Received with ${hms(remaining)} to spare · deadline ${formatAbsolute(dueAt)}`
          : `Due ${formatAbsolute(dueAt)} (24 h after site awareness)`}
      </div>
    </div>
  );
}
