"use client";

import { useNow } from "@/lib/hooks";
import { formatAbsolute, formatRelative } from "@/lib/format";

/** "21 s ago" with the absolute America/New_York time on hover. */
export function RelativeTime({ iso, className }: { iso: string | null | undefined; className?: string }) {
  const now = useNow();
  if (!iso) return <span className={className}>—</span>;
  const abs = formatAbsolute(iso);
  return (
    <time dateTime={iso} title={abs} className={["tabular", className].filter(Boolean).join(" ")}>
      {now === 0 ? abs : formatRelative(iso, now)}
    </time>
  );
}
