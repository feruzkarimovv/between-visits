"use client";

import { BellRing, CheckCircle2, Languages, RotateCcw, Siren, PhoneCall } from "lucide-react";
import type { Escalation } from "@/lib/types";
import { useApiMutation } from "@/lib/queries";
import { useNow } from "@/lib/hooks";
import { formatAbsolute, formatDuration, parseTs } from "@/lib/format";
import { ACK_METHOD_LABELS, PAGE_CHANNEL_LABELS, REASON_LABELS } from "@/lib/labels";
import { LevelChip, RedFlagChip } from "./chips";
import { Button, cn } from "./ui/primitives";

/** Seconds from page to acknowledgment, from timestamps when we have both. */
export function ackSeconds(e: Escalation): number | null {
  if (typeof e.seconds_to_ack === "number") return Math.round(e.seconds_to_ack);
  const start = parseTs(e.paged_at ?? e.created_at ?? null);
  const ack = parseTs(e.acknowledged_at ?? null);
  if (start !== null && ack !== null) return Math.max(0, Math.round((ack - start) / 1000));
  return e.status !== "open" ? e.seconds_open : null;
}

/**
 * Live escalation card on the check-in page: counts up while open,
 * turns green with "Acknowledged in N s" when the nurse taps Acknowledge.
 * `fetchedAt` is when the data was fetched, so the counter keeps ticking
 * between polls without trusting the browser clock against the server's.
 */
export function EscalationPanel({ escalation: e, fetchedAt }: { escalation: Escalation; fetchedAt: number }) {
  const now = useNow();
  const ack = useApiMutation<string, Escalation>({
    request: (id) => ({ path: `/api/escalations/${encodeURIComponent(id)}/ack`, init: { method: "POST", body: {} } }),
    success: "Escalation acknowledged",
    invalidate: [["checkin"], ["escalations"]],
  });

  const open = e.status === "open";
  const liveOpen = open ? e.seconds_open + Math.max(0, ((now || fetchedAt) - fetchedAt) / 1000) : null;
  const pagedAgo = e.paged_at && now ? (now - (parseTs(e.paged_at) ?? now)) / 1000 : null;
  const ackIn = ackSeconds(e);
  const emergency = e.level === "emergency";
  const callback = e.level === "callback";

  const frame = !open
    ? "border-green-300 bg-green-50/60"
    : emergency
      ? "border-red-600 bg-red-50"
      : callback
        ? "border-blue-200 bg-blue-50/60"
        : "border-amber-400 bg-amber-50";

  return (
    <section aria-label={`${e.level} escalation`} className={cn("rounded-lg border-2 p-4 transition-colors duration-500", frame)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn(open && !callback && "animate-pulse")}>
            <LevelChip level={e.level} strong={open} />
          </span>
          <span className="text-sm font-medium text-ink-muted">{e.reason ? REASON_LABELS[e.reason] : "Escalation"}</span>
        </div>
        {open ? (
          <div className="flex items-center gap-1.5 text-sm font-semibold text-ink tabular" aria-live="off">
            {emergency ? <Siren className="size-4 text-red-700" aria-hidden /> : callback ? <PhoneCall className="size-4 text-blue-700" aria-hidden /> : <BellRing className="size-4 text-amber-700" aria-hidden />}
            Open {formatDuration(liveOpen)}
          </div>
        ) : null}
      </div>

      {e.red_flag_ids?.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {e.red_flag_ids.map((id) => (
            <RedFlagChip key={id} id={id} />
          ))}
        </div>
      ) : null}

      {e.summary_en ? <p className="mt-3 text-[15px] leading-6 text-ink">{e.summary_en}</p> : null}

      <dl className="mt-3 space-y-1.5 text-sm">
        {e.paged_at ? (
          <div className="flex flex-wrap items-center gap-x-2 text-ink">
            <BellRing className="size-4 text-ink-subtle" aria-hidden />
            <span title={formatAbsolute(e.paged_at)}>
              Paged <strong>{e.page_target_name}</strong> by {PAGE_CHANNEL_LABELS[e.page_channel ?? ""] ?? e.page_channel ?? "page"}{" "}
              <span className="tabular">{pagedAgo === null ? "" : `${formatDuration(pagedAgo)} ago`}</span>
            </span>
          </div>
        ) : callback ? (
          <div className="text-ink-muted">Not paged: callback tasks go to the coordinator queue.</div>
        ) : null}
        {e.repage_count > 0 ? (
          <div className="flex items-center gap-2 font-medium text-amber-900">
            <RotateCcw className="size-4" aria-hidden />
            Re-paged {e.repage_count} time{e.repage_count === 1 ? "" : "s"}
            {e.repage_count >= 2 ? " · backup contact paged" : ""}
          </div>
        ) : e.paged_at ? (
          <div className="flex items-center gap-2 text-ink-subtle">
            <RotateCcw className="size-4" aria-hidden />
            No re-pages
          </div>
        ) : null}
        {e.patient_language === "es" ? (
          <div className="flex items-center gap-2 font-medium text-accent-800">
            <Languages className="size-4" aria-hidden />
            Prefers Spanish: use interpreter line
          </div>
        ) : null}
      </dl>

      {open ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            variant={emergency ? "danger" : "primary"}
            loading={ack.isPending}
            onClick={() => ack.mutate(e.id)}
            icon={<CheckCircle2 className="size-4" aria-hidden />}
          >
            Acknowledge
          </Button>
          <span className="text-sm text-ink-subtle">Fallback if the nurse can&apos;t use the push button.</span>
        </div>
      ) : (
        <div className="mt-4 flex items-center gap-2 rounded-md bg-green-700 px-3 py-2.5 text-white">
          <CheckCircle2 className="size-5 shrink-0" aria-hidden />
          <div className="text-[15px] leading-snug">
            <strong className="tabular">Acknowledged in {ackIn ?? "—"} s</strong>
            {e.acknowledged_by ? ` by ${e.acknowledged_by}` : ""}
            {e.ack_method ? ` via ${ACK_METHOD_LABELS[e.ack_method]}` : ""}
            {e.status === "resolved" ? " · resolved" : ""}
          </div>
        </div>
      )}
    </section>
  );
}
