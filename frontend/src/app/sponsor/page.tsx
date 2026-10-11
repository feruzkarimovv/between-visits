"use client";

import { useState } from "react";
import { Building2, CheckCircle2, ChevronDown, ChevronRight, Circle, Inbox, ShieldCheck } from "lucide-react";
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

  return (
    <div className="overflow-hidden rounded-xl border border-indigo-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 bg-sponsor-900 px-5 py-4 text-white">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-md bg-white/15">
            <ShieldCheck className="size-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Pharmacovigilance Intake</h1>
            <div className="text-sm text-indigo-200">Sponsor safety team (mock) · Individual case safety reports</div>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-white/40 px-3 py-1 text-sm font-medium">
          <Building2 className="size-4" aria-hidden />
          Sponsor view (mock)
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-indigo-100 bg-indigo-50/60 px-5 py-2.5 text-sm text-indigo-950">
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
        <div className="p-4">
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

function InboxRow({ item, open, onToggle }: { item: SponsorInboxItem; open: boolean; onToggle: () => void }) {
  const received = parseTs(item.received_at);
  const due = parseTs(item.due_at);
  const margin = typeof item.seconds_before_deadline === "number" ? item.seconds_before_deadline : received !== null && due !== null ? (due - received) / 1000 : null;
  const valid = CHECKS.every((c) => item.valid_case_checks[c.key]);
  return (
    <li>
      <button type="button" onClick={onToggle} aria-expanded={open} className="grid w-full grid-cols-[1.25rem_minmax(0,1fr)] gap-3 px-5 py-3.5 text-left hover:bg-indigo-50/40 md:grid-cols-[1.25rem_minmax(0,2fr)_minmax(0,2fr)_auto]">
        <span className="pt-0.5 text-indigo-700">{open ? <ChevronDown className="size-5" aria-hidden /> : <ChevronRight className="size-5" aria-hidden />}</span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-ink">{item.event_term}</span>
            <GradeBadge grade={item.provisional_grade} />
            <OriginTag />
          </div>
          <div className="mt-0.5 text-sm text-ink-muted">
            <span className="font-mono">{item.subject_id}</span> · {item.study} · site {item.site} · {item.seriousness_criteria.map((c) => SERIOUSNESS_LABELS[c]).join(", ") || "seriousness not given"}
          </div>
        </div>
        <div className="col-start-2 flex flex-wrap gap-x-3 gap-y-1 md:col-start-auto">
          {CHECKS.map((c) => (
            <span key={c.key} className={cn("inline-flex items-center gap-1 text-sm", item.valid_case_checks[c.key] ? "text-green-800" : "text-ink-subtle")}>
              {item.valid_case_checks[c.key] ? <CheckCircle2 className="size-4" aria-hidden /> : <Circle className="size-4" aria-hidden />}
              {c.label}
              <span className="sr-only">{item.valid_case_checks[c.key] ? "present" : "missing"}</span>
            </span>
          ))}
        </div>
        <div className="col-start-2 flex flex-col items-start gap-1 md:col-start-auto md:items-end">
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2.5 py-0.5 text-sm font-semibold",
              item.on_time ? "border-green-300 bg-green-50 text-green-800" : "border-red-300 bg-red-50 text-red-800",
            )}
          >
            {item.on_time ? "On time" : "Late"}
            {margin !== null ? ` · ${formatSpan(Math.abs(margin))} ${margin >= 0 ? "early" : "late"}` : ""}
          </span>
          <span className="text-sm text-ink-subtle">
            Received <RelativeTime iso={item.received_at} />
          </span>
        </div>
      </button>
      {open ? (
        <div className="grid gap-4 border-t border-indigo-100 bg-indigo-50/30 px-5 py-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] md:pl-13">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Item label="Report ID">{item.sae_id}</Item>
            <Item label="Valid case">{valid ? "Yes (4 of 4)" : "Incomplete"}</Item>
            <Item label="Received">{formatAbsolute(item.received_at)}</Item>
            <Item label="Deadline">{formatAbsolute(item.due_at)}</Item>
            <Item label="Relatedness">{item.relatedness ? RELATEDNESS_LABELS[item.relatedness] : "—"}</Item>
            <Item label="Grade">{item.provisional_grade === null ? "Not graded" : `${item.provisional_grade} (provisional)`}</Item>
          </dl>
          <div>
            <div className="mb-1 text-sm font-medium text-ink-subtle">Narrative (signed by site investigator, read-only)</div>
            <p className="rounded-md border border-indigo-100 bg-white p-3 text-sm leading-6 text-ink">{item.narrative}</p>
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
      <dd className="font-medium break-words text-ink">{children}</dd>
    </div>
  );
}
