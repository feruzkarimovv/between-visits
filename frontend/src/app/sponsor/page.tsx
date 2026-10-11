"use client";

import { useState } from "react";
import { Building2, CheckCircle2, ChevronDown, Circle, Clock3, Inbox, ShieldCheck } from "lucide-react";
import type { SponsorInboxItem, ValidCaseChecks } from "@/lib/types";
import { useSponsorInbox } from "@/lib/queries";
import { formatAbsolute, formatSpan, parseTs } from "@/lib/format";
import { RELATEDNESS_LABELS, SERIOUSNESS_LABELS } from "@/lib/labels";
import { EmptyState, ErrorState, LoadingRows, cn } from "@/components/ui/primitives";
import { GradeBadge } from "@/components/GradeBadge";
import { OriginTag } from "@/components/chips";
import { ExportDownloads } from "@/components/DownloadButton";
import { RelativeTime } from "@/components/RelativeTime";

const CHECKS: { key: keyof ValidCaseChecks; label: string }[] = [
  { key: "identifiable_patient", label: "Identifiable patient" },
  { key: "identifiable_reporter", label: "Identifiable reporter" },
  { key: "suspect_product", label: "Suspect product" },
  { key: "adverse_event", label: "Adverse event" },
];

/**
 * Mock of the sponsor's safety intake tool. Deliberately styled as a different
 * organization's product, and shows subject IDs only (no names, no phone numbers).
 */
export default function SponsorInboxPage() {
  const inbox = useSponsorInbox();
  const [open, setOpen] = useState<string | null>(null);
  const items = [...(inbox.data ?? [])].sort((a, b) => b.received_at.localeCompare(a.received_at));
  const onTime = items.filter((i) => i.on_time).length;
  const valid = items.filter((i) => CHECKS.every((c) => i.valid_case_checks[c.key])).length;

  return (
    <div className="overflow-hidden rounded-2xl border border-indigo-200 bg-white shadow-raised">
      <div className="relative overflow-hidden bg-gradient-to-r from-sponsor-950 via-sponsor-900 to-sponsor-800 px-6 py-5 text-white">
        <div
          className="pointer-events-none absolute inset-0 opacity-40 [background-image:linear-gradient(rgb(255_255_255/0.06)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255/0.06)_1px,transparent_1px)] [background-size:28px_28px] [mask-image:linear-gradient(to_left,black,transparent_70%)]"
          aria-hidden
        />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <span className="flex size-11 items-center justify-center rounded-xl bg-white text-sponsor-900 shadow-lg">
              <ShieldCheck className="size-6" aria-hidden />
            </span>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Pharmacovigilance Intake</h1>
              <div className="text-sm text-indigo-200">Sponsor safety team (mock) · Individual case safety reports</div>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/40 bg-white/10 px-3 py-1 text-sm font-medium">
            <Building2 className="size-4" aria-hidden />
            Sponsor view (mock)
          </span>
        </div>
        <dl className="relative mt-5 grid max-w-xl grid-cols-3 gap-3">
          <Kpi label="Received" value={inbox.data ? items.length : null} />
          <Kpi label="On time" value={inbox.data ? onTime : null} of={items.length} />
          <Kpi label="Valid cases" value={inbox.data ? valid : null} of={items.length} />
        </dl>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-indigo-100 bg-indigo-50/70 px-6 py-3 text-sm text-indigo-950">
        <p className="min-w-0 flex-1 basis-80">
          Received initial reports from investigator sites. Site-only data (patient names, phone numbers) is never shared: cases are identified by subject ID.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <ExportDownloads />
        </div>
      </div>

      {inbox.isPending ? (
        <LoadingRows rows={3} />
      ) : inbox.isError ? (
        <div className="p-5">
          <ErrorState error={inbox.error} onRetry={() => void inbox.refetch()} retrying={inbox.isFetching} />
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={<Inbox className="size-6" aria-hidden />} title="No reports received yet.">
          When a site investigator signs and sends a serious-event report, it lands here with its 24-hour deadline.
        </EmptyState>
      ) : (
        <ul className="divide-y divide-indigo-100">
          {items.map((it) => (
            <InboxRow key={it.sae_id} item={it} open={open === it.sae_id} onToggle={() => setOpen(open === it.sae_id ? null : it.sae_id)} />
          ))}
        </ul>
      )}
    </div>
  );
}

function Kpi({ label, value, of }: { label: string; value: number | null; of?: number }) {
  return (
    <div className="rounded-xl border border-white/15 bg-white/[0.07] px-3 py-2 backdrop-blur">
      <dt className="text-sm text-indigo-200">{label}</dt>
      <dd className="text-2xl font-bold tabular">
        {value ?? "—"}
        {typeof of === "number" && value !== null ? <span className="text-base font-medium text-indigo-200"> / {of}</span> : null}
      </dd>
    </div>
  );
}

function InboxRow({ item, open, onToggle }: { item: SponsorInboxItem; open: boolean; onToggle: () => void }) {
  const received = parseTs(item.received_at);
  const due = parseTs(item.due_at);
  const margin = typeof item.seconds_before_deadline === "number" ? item.seconds_before_deadline : received !== null && due !== null ? (due - received) / 1000 : null;
  const valid = CHECKS.every((c) => item.valid_case_checks[c.key]);
  return (
    <li className={cn(open && "bg-indigo-50/30")}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="grid w-full grid-cols-[1.25rem_minmax(0,1fr)] gap-x-4 gap-y-3 px-6 py-4 text-left transition-colors hover:bg-indigo-50/50 md:grid-cols-[1.25rem_minmax(0,2fr)_minmax(0,2fr)_auto]"
      >
        <span className="pt-1 text-indigo-700">
          <ChevronDown className={cn("size-5 transition-transform", !open && "-rotate-90")} aria-hidden />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-ink">{item.event_term}</span>
            <GradeBadge grade={item.provisional_grade} />
            <OriginTag />
          </div>
          <div className="mt-1 text-sm text-ink-muted">
            <span className="font-mono font-medium text-ink">{item.subject_id}</span> · {item.study} · site {item.site} ·{" "}
            {item.seriousness_criteria.map((c) => SERIOUSNESS_LABELS[c]).join(", ") || "seriousness not given"}
          </div>
        </div>
        <div className="col-start-2 grid grid-cols-2 gap-x-3 gap-y-1 md:col-start-auto">
          {CHECKS.map((c) => (
            <span key={c.key} className={cn("inline-flex items-center gap-1.5 text-sm", item.valid_case_checks[c.key] ? "text-green-800" : "text-ink-subtle")}>
              {item.valid_case_checks[c.key] ? <CheckCircle2 className="size-4 shrink-0" aria-hidden /> : <Circle className="size-4 shrink-0" aria-hidden />}
              {c.label}
              <span className="sr-only">{item.valid_case_checks[c.key] ? "present" : "missing"}</span>
            </span>
          ))}
        </div>
        <div className="col-start-2 flex flex-col items-start gap-1 md:col-start-auto md:items-end">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-semibold",
              item.on_time ? "bg-green-700 text-white" : "bg-red-700 text-white",
            )}
          >
            <Clock3 className="size-3.5" aria-hidden />
            {item.on_time ? "On time" : "Late"}
            {margin !== null ? ` · ${formatSpan(Math.abs(margin))} ${margin >= 0 ? "early" : "late"}` : ""}
          </span>
          <span className="text-sm text-ink-subtle">
            Received <RelativeTime iso={item.received_at} />
          </span>
        </div>
      </button>
      {open ? (
        <div className="grid gap-5 border-t border-indigo-100 bg-indigo-50/40 px-6 py-5 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] md:pl-15">
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <Item label="Report ID">
              <span className="font-mono">{item.sae_id}</span>
            </Item>
            <Item label="Valid case">{valid ? "Yes (4 of 4)" : "Incomplete"}</Item>
            <Item label="Received">{formatAbsolute(item.received_at)}</Item>
            <Item label="Deadline">{formatAbsolute(item.due_at)}</Item>
            <Item label="Relatedness">{item.relatedness ? RELATEDNESS_LABELS[item.relatedness] : "—"}</Item>
            <Item label="Grade">{item.provisional_grade === null ? "Not graded" : `${item.provisional_grade} (provisional)`}</Item>
          </dl>
          <div>
            <div className="mb-1.5 text-sm font-medium text-ink-subtle">Narrative (signed by site investigator, read-only)</div>
            <p className="rounded-xl border border-indigo-100 bg-white p-4 text-[15px] leading-7 text-ink shadow-card">{item.narrative}</p>
          </div>
        </div>
      ) : null}
    </li>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-ink-subtle">{label}</dt>
      <dd className="mt-0.5 font-medium break-words text-ink">{children}</dd>
    </div>
  );
}
