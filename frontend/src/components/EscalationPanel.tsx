"use client";

import { BellRing, CheckCircle2, Languages, RotateCcw, Siren, PhoneCall, ShieldAlert } from "lucide-react";
import type { Escalation } from "@/lib/types";
import { useApiMutation } from "@/lib/queries";
import { useNow } from "@/lib/hooks";
import { formatAbsolute, formatDuration, parseTs } from "@/lib/format";
import { ACK_METHOD_LABELS, PAGE_CHANNEL_LABELS, REASON_LABELS } from "@/lib/labels";
import { LevelChip, LiveDot, RedFlagChip } from "./chips";
import { Button, cn } from "./ui/primitives";

/** Seconds from page to acknowledgment, from timestamps when we have both. */
export function ackSeconds(e: Escalation): number | null {
  if (typeof e.seconds_to_ack === "number") return Math.round(e.seconds_to_ack);
  const start = parseTs(e.paged_at ?? e.created_at ?? null);
  const ack = parseTs(e.acknowledged_at ?? null);
  if (start !== null && ack !== null) return Math.max(0, Math.round((ack - start) / 1000));
  return e.status !== "open" ? e.seconds_open : null;
}

type StepState = "done" | "active" | "waiting";

function Step({
  state,
  tone = "neutral",
  icon,
  title,
  children,
  last,
}: {
  state: StepState;
  tone?: "neutral" | "red" | "amber" | "green" | "blue";
  icon: React.ReactNode;
  title: React.ReactNode;
  children?: React.ReactNode;
  last?: boolean;
}) {
  const dot = {
    neutral: "bg-ink text-white",
    red: "bg-red-700 text-white",
    amber: "bg-amber-400 text-amber-950",
    green: "bg-green-700 text-white",
    blue: "bg-blue-700 text-white",
  }[tone];
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      {!last ? <span className={cn("absolute top-7 bottom-0 left-[13px] w-px", state === "done" ? "bg-line-strong" : "border-l border-dashed border-line-strong")} aria-hidden /> : null}
      <span
        className={cn(
          "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full ring-4 ring-white",
          state === "waiting" ? "border border-dashed border-gray-400 bg-white text-ink-subtle" : dot,
          state === "active" && "bv-breathe",
        )}
      >
        {icon}
      </span>
      <div className="min-w-0 pt-0.5 text-sm leading-6">
        <div className="font-medium text-ink">{title}</div>
        {children ? <div className="text-ink-muted">{children}</div> : null}
      </div>
    </li>
  );
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
  const levelTone = emergency ? "red" : callback ? "blue" : "amber";

  const frame = !open
    ? "border-green-300"
    : emergency
      ? "border-red-600 bv-breathe [--bv-glow:rgb(220_38_38/0.35)]"
      : callback
        ? "border-blue-200"
        : "border-amber-400 bv-breathe [--bv-glow:rgb(245_158_11/0.4)]";

  const band = !open
    ? "bg-green-50 text-green-900 border-green-200"
    : emergency
      ? "bg-red-700 text-white border-red-800"
      : callback
        ? "bg-blue-50 text-blue-900 border-blue-200"
        : "bg-amber-400 text-amber-950 border-amber-500";

  return (
    <section aria-label={`${e.level} escalation`} className={cn("bv-enter overflow-hidden rounded-2xl border-2 bg-white shadow-raised transition-colors duration-500", frame)}>
      <header className={cn("flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5", band)}>
        <div className="flex items-center gap-2 font-semibold">
          {emergency ? <Siren className="size-5" aria-hidden /> : callback ? <PhoneCall className="size-5" aria-hidden /> : <BellRing className="size-5" aria-hidden />}
          <span className="text-[15px]">
            {emergency ? "Emergency" : callback ? "Callback" : "Urgent"} escalation
          </span>
        </div>
        {open ? (
          <span className="inline-flex items-center gap-2 text-sm font-semibold tabular" aria-live="off">
            {!callback ? <LiveDot tone={emergency ? "live" : "red"} className={emergency ? "[&>span]:bg-white" : undefined} /> : null}
            Open {formatDuration(liveOpen)}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
            <CheckCircle2 className="size-4" aria-hidden />
            {e.status === "resolved" ? "Resolved" : "Acknowledged"}
          </span>
        )}
      </header>

      <div className="p-4">
        {!open && ackIn !== null ? (
          <div className="mb-4 flex items-center gap-4 rounded-xl bg-gradient-to-br from-green-700 to-green-800 px-4 py-3 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)]">
            <div className="flex items-baseline gap-1">
              <span className="text-5xl leading-none font-semibold tracking-tighter tabular">{ackIn}</span>
              <span className="text-lg font-medium">s</span>
            </div>
            <div className="min-w-0 text-[15px] leading-snug">
              <strong className="block">Acknowledged in {ackIn} s</strong>
              <span className="text-white/85">
                {e.acknowledged_by ? `by ${e.acknowledged_by}` : ""}
                {e.ack_method ? ` via ${ACK_METHOD_LABELS[e.ack_method]}` : ""}
                {e.status === "resolved" ? " · resolved" : ""}
              </span>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-1.5">
          <LevelChip level={e.level} />
          {e.red_flag_ids?.map((id) => <RedFlagChip key={id} id={id} />)}
        </div>

        {e.summary_en ? <p className="mt-3 text-[15px] leading-6 text-ink">{e.summary_en}</p> : null}

        <ol className="mt-4">
          <Step state="done" tone={levelTone} icon={<ShieldAlert className="size-3.5" aria-hidden />} title={e.reason ? REASON_LABELS[e.reason] : "Escalation raised"}>
            <span title={formatAbsolute(e.created_at)}>Level set by fixed escalation rules, not by AI</span>
          </Step>
          {e.paged_at ? (
            <Step state="done" tone={levelTone} icon={<BellRing className="size-3.5" aria-hidden />} title={<>Paged {e.page_target_name}</>}>
              <span title={formatAbsolute(e.paged_at)}>
                by {PAGE_CHANNEL_LABELS[e.page_channel ?? ""] ?? e.page_channel ?? "page"}
                <span className="tabular">{pagedAgo === null ? "" : ` · ${formatDuration(pagedAgo)} ago`}</span>
              </span>
            </Step>
          ) : callback ? (
            <Step state="done" tone="blue" icon={<PhoneCall className="size-3.5" aria-hidden />} title="Sent to the coordinator queue">
              Not paged: callback tasks go to the coordinator queue.
            </Step>
          ) : null}
          {e.repage_count > 0 ? (
            <Step state="done" tone="amber" icon={<RotateCcw className="size-3.5" aria-hidden />} title={`Re-paged ${e.repage_count} time${e.repage_count === 1 ? "" : "s"}`}>
              {e.repage_count >= 2 ? "Backup contact paged" : "Every 90 s until someone acknowledges"}
            </Step>
          ) : null}
          {open ? (
            <Step state="active" tone={levelTone} icon={<LiveDot tone={emergency ? "live" : "amber"} />} title="Waiting for acknowledgment" last>
              {e.paged_at ? (e.repage_count === 0 ? "No re-pages yet · re-page after 90 s" : "Re-paging until acknowledged") : "A coordinator will call back"}
            </Step>
          ) : (
            <Step state="done" tone="green" icon={<CheckCircle2 className="size-3.5" aria-hidden />} title={<span className="tabular">Acknowledged{ackIn !== null ? ` after ${ackIn} s` : ""}</span>} last>
              <span title={formatAbsolute(e.acknowledged_at)}>
                {e.acknowledged_by ?? "Study team"}
                {e.ack_method ? ` · ${ACK_METHOD_LABELS[e.ack_method]}` : ""}
              </span>
            </Step>
          )}
        </ol>

        {e.patient_language === "es" ? (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-accent-200 bg-accent-50 px-3 py-2 text-sm font-medium text-accent-900">
            <Languages className="size-4 shrink-0" aria-hidden />
            Prefers Spanish: use interpreter line
          </div>
        ) : null}

        {open ? (
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
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
        ) : null}
      </div>
    </section>
  );
}
