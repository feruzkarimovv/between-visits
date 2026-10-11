"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, ArrowUpRight, BellRing, CheckCircle2, CircleCheckBig, Languages, PhoneCall, RotateCcw, Siren, Timer } from "lucide-react";
import type { Escalation, EscalationStatus } from "@/lib/types";
import { useApiMutation, useEscalations } from "@/lib/queries";
import { formatDuration, fullName } from "@/lib/format";
import { ACK_METHOD_LABELS, PAGE_CHANNEL_LABELS, REASON_LABELS } from "@/lib/labels";
import { Avatar, Button, Card, CardHeader, EmptyState, ErrorState, LoadingRows, PageHeader, inputClass, cn } from "@/components/ui/primitives";
import { EscalationStatusChip, LevelChip, LiveDot, RedFlagChip } from "@/components/chips";
import { RelativeTime } from "@/components/RelativeTime";
import { ackSeconds } from "@/components/EscalationPanel";

const LEVEL_RANK = { emergency: 0, urgent: 1, callback: 2 } as const;

function sortOpen(list: Escalation[]): Escalation[] {
  return [...list].sort((a, b) => LEVEL_RANK[a.level] - LEVEL_RANK[b.level] || b.seconds_open - a.seconds_open);
}

function sortClosed(list: Escalation[], field: "acknowledged_at" | "resolved_at"): Escalation[] {
  return [...list].sort((a, b) => (b[field] ?? "").localeCompare(a[field] ?? ""));
}

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
}

export default function EscalationsPage() {
  const open = useEscalations("open", 2000);
  const acked = useEscalations("acknowledged", 5000);
  const resolved = useEscalations("resolved", 15000);
  const openRows = sortOpen(open.data ?? []);
  const closed = [...(acked.data ?? []), ...(resolved.data ?? [])].filter((e) => e.level !== "callback");
  const ackTimes = closed.map(ackSeconds).filter((s): s is number => s !== null);
  const med = median(ackTimes);

  return (
    <>
      <PageHeader
        eyebrow="Nurse paging"
        title="Escalations"
        subtitle="Urgent and emergency red flags page the on-call nurse within seconds and keep re-paging until someone acknowledges. Callbacks go to the coordinator queue."
        actions={
          <dl className="flex flex-wrap gap-2">
            <SummaryStat label="Open" value={open.data ? openRows.length : null} tone={openRows.some((e) => e.level === "emergency") ? "red" : openRows.some((e) => e.level === "urgent") ? "amber" : undefined} />
            <SummaryStat label="Acknowledged" value={acked.data ? acked.data.length : null} />
            <SummaryStat label="Resolved" value={resolved.data ? resolved.data.length : null} />
            <SummaryStat
              label="Median time to acknowledge"
              value={med}
              suffix=" s"
              icon={<Timer className="size-4 text-green-700" aria-hidden />}
              title={ackTimes.length ? `Across ${ackTimes.length} paged escalation${ackTimes.length === 1 ? "" : "s"}` : "No acknowledged pages yet"}
            />
          </dl>
        }
      />

      <section aria-labelledby="open-heading" className="mb-6">
        <div className="mb-3 flex items-center gap-2">
          <h2 id="open-heading" className="text-base font-semibold text-ink">
            Open
          </h2>
          <span className="rounded-full bg-gray-200/80 px-2 text-sm font-medium text-ink-muted tabular">{open.data ? openRows.length : "…"}</span>
        </div>
        {open.isPending ? (
          <Card>
            <LoadingRows rows={2} />
          </Card>
        ) : open.isError && !open.data ? (
          <ErrorState error={open.error} onRetry={() => void open.refetch()} retrying={open.isFetching} />
        ) : openRows.length === 0 ? (
          <Card>
            <EmptyState className="py-10" icon={<CheckCircle2 className="size-6 text-green-700" aria-hidden />} title="No open escalations">
              Red flags from check-ins appear here the moment a rule fires.
            </EmptyState>
          </Card>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {openRows.map((e) => (
              <OpenCard key={e.id} e={e} />
            ))}
          </div>
        )}
      </section>

      <div className="space-y-5">
        <ClosedList title="Acknowledged" status="acknowledged" query={acked} rows={sortClosed(acked.data ?? [], "acknowledged_at")} empty="Nothing waiting to be resolved." />
        <ClosedList title="Resolved" status="resolved" query={resolved} rows={sortClosed(resolved.data ?? [], "resolved_at")} empty="No resolved escalations yet." />
      </div>
    </>
  );
}

function SummaryStat({
  label,
  value,
  suffix,
  tone,
  icon,
  title,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  tone?: "red" | "amber";
  icon?: React.ReactNode;
  title?: string;
}) {
  return (
    <div
      title={title}
      className={cn(
        "min-w-24 rounded-xl border px-3 py-2 shadow-card",
        tone === "red" ? "border-red-300 bg-red-50" : tone === "amber" ? "border-amber-300 bg-amber-50" : "border-line bg-white",
      )}
    >
      <dt className="text-sm text-ink-subtle">{label}</dt>
      <dd className="flex items-center gap-1.5 text-2xl leading-tight font-semibold tracking-tight text-ink tabular">
        {icon}
        {value === null ? "—" : `${value}${suffix ?? ""}`}
      </dd>
    </div>
  );
}

// ---------------------------------------------------------------- open

function useEscalationActions(e: Escalation, onResolved?: () => void) {
  const ack = useApiMutation<string, Escalation>({
    request: (id) => ({ path: `/api/escalations/${encodeURIComponent(id)}/ack`, init: { method: "POST", body: {} } }),
    success: "Escalation acknowledged",
    invalidate: [["escalations"], ["checkin"]],
  });
  const resolve = useApiMutation<{ id: string; note: string }, Escalation>({
    request: (v) => ({ path: `/api/escalations/${encodeURIComponent(v.id)}/resolve`, init: { method: "POST", body: { note: v.note } } }),
    success: "Escalation resolved",
    invalidate: [["escalations"], ["checkin"]],
    onSuccess: onResolved,
  });
  return { ack, resolve, id: e.id };
}

function OpenCard({ e }: { e: Escalation }) {
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const { ack, resolve } = useEscalationActions(e, () => {
    setResolving(false);
    setNote("");
  });
  const emergency = e.level === "emergency";
  const callback = e.level === "callback";
  const name = e.patient ? fullName(e.patient) || e.patient.subject_id : e.patient_id ?? "Patient";

  return (
    <article
      className={cn(
        "bv-enter overflow-hidden rounded-2xl border-2 bg-white shadow-raised",
        emergency ? "bv-breathe border-red-600 [--bv-glow:rgb(220_38_38/0.3)]" : callback ? "border-blue-200" : "bv-breathe border-amber-400 [--bv-glow:rgb(245_158_11/0.35)]",
      )}
    >
      <header
        className={cn(
          "flex flex-wrap items-center justify-between gap-2 px-4 py-2.5",
          emergency ? "bg-red-700 text-white" : callback ? "border-b border-blue-200 bg-blue-50 text-blue-900" : "bg-amber-400 text-amber-950",
        )}
      >
        <span className="inline-flex items-center gap-2 font-semibold">
          {emergency ? <Siren className="size-5" aria-hidden /> : callback ? <PhoneCall className="size-5" aria-hidden /> : <BellRing className="size-5" aria-hidden />}
          {emergency ? "Emergency" : callback ? "Callback" : "Urgent"}
          <span className="font-normal opacity-90">· {e.reason ? REASON_LABELS[e.reason] : "Escalation"}</span>
        </span>
        <span className="inline-flex items-center gap-2 text-sm font-semibold tabular">
          {!callback ? <LiveDot tone={emergency ? "live" : "red"} className={emergency ? "[&>span]:bg-white" : undefined} /> : null}
          Open {formatDuration(e.seconds_open)}
        </span>
      </header>
      <div className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          {e.patient ? (
            <Link href={`/patients/${e.patient.id}`} className="group flex items-center gap-3">
              <Avatar name={name} seed={e.patient.id} />
              <span className="leading-tight">
                <span className="block text-[15px] font-semibold text-ink group-hover:underline">{name}</span>
                <span className="font-mono text-sm text-ink-subtle">{e.patient.subject_id}</span>
              </span>
            </Link>
          ) : (
            <span className="text-ink-subtle">{e.patient_id ?? "—"}</span>
          )}
          {e.checkin_id ? (
            <Link href={`/checkins/${e.checkin_id}`} className="inline-flex items-center gap-0.5 rounded text-sm font-medium text-accent-700 hover:underline">
              Open check-in
              <ArrowUpRight className="size-3.5" aria-hidden />
            </Link>
          ) : null}
        </div>
        {e.red_flag_ids?.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {e.red_flag_ids.map((id) => (
              <RedFlagChip key={id} id={id} />
            ))}
          </div>
        ) : null}
        <p className="mt-3 text-[15px] leading-6 text-ink">{e.summary_en || (e.reason ? REASON_LABELS[e.reason] : "—")}</p>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-muted">
          {e.paged_at ? (
            <span className="inline-flex items-center gap-1.5">
              <BellRing className="size-4 text-ink-subtle" aria-hidden />
              Paged {e.page_target_name} by {PAGE_CHANNEL_LABELS[e.page_channel ?? ""] ?? e.page_channel ?? "page"} · <RelativeTime iso={e.paged_at} />
            </span>
          ) : (
            <span>Not paged (callback)</span>
          )}
          {e.repage_count > 0 ? (
            <span className="inline-flex items-center gap-1.5 font-medium text-amber-900">
              <RotateCcw className="size-4" aria-hidden />
              Re-paged ×{e.repage_count}
            </span>
          ) : null}
          {e.patient_language === "es" ? (
            <span className="inline-flex items-center gap-1.5 font-medium text-accent-800">
              <Languages className="size-4" aria-hidden />
              Prefers Spanish
            </span>
          ) : null}
        </div>
      </div>
      <div className="border-t border-line bg-gray-50/80 px-4 py-3">
        {resolving ? (
          <ResolveForm
            id={e.id}
            note={note}
            setNote={setNote}
            pending={resolve.isPending}
            onSubmit={() => note.trim() && resolve.mutate({ id: e.id, note: note.trim() })}
            onCancel={() => setResolving(false)}
          />
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button variant={emergency ? "danger" : "primary"} loading={ack.isPending} onClick={() => ack.mutate(e.id)} icon={<CheckCircle2 className="size-4" aria-hidden />}>
              Acknowledge
            </Button>
            <Button variant="secondary" onClick={() => setResolving(true)} aria-expanded={resolving}>
              Resolve…
            </Button>
          </div>
        )}
      </div>
    </article>
  );
}

function ResolveForm({
  id,
  note,
  setNote,
  pending,
  onSubmit,
  onCancel,
}: {
  id: string;
  note: string;
  setNote: (v: string) => void;
  pending: boolean;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(ev) => {
        ev.preventDefault();
        onSubmit();
      }}
    >
      <div className="min-w-56 flex-1">
        <label htmlFor={`note-${id}`} className="mb-1.5 block text-sm font-medium text-ink-muted">
          Resolution note (what the team did)
        </label>
        <input id={`note-${id}`} className={inputClass} value={note} onChange={(ev) => setNote(ev.target.value)} placeholder="e.g. Nurse spoke with patient, follow-up arranged" autoFocus />
      </div>
      <Button type="submit" variant="primary" loading={pending} disabled={!note.trim()}>
        Resolve
      </Button>
      <Button variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
    </form>
  );
}

// ---------------------------------------------------------------- closed

function ClosedList({
  title,
  status,
  query,
  rows,
  empty,
}: {
  title: string;
  status: EscalationStatus;
  query: ReturnType<typeof useEscalations>;
  rows: Escalation[];
  empty: string;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title={
          <>
            {title}
            <span className="rounded-full bg-gray-100 px-2 text-sm font-medium text-ink-muted tabular">{query.data ? rows.length : "…"}</span>
          </>
        }
        icon={status === "acknowledged" ? <CheckCircle2 className="size-4" aria-hidden /> : <CircleCheckBig className="size-4" aria-hidden />}
      />
      {query.isPending ? (
        <LoadingRows rows={2} />
      ) : query.isError && !query.data ? (
        <div className="p-5">
          <ErrorState error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState className="py-8" title={empty} />
      ) : (
        <ul className="divide-y divide-line/80">
          {rows.map((e) => (
            <ClosedRow key={e.id} e={e} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function ClosedRow({ e }: { e: Escalation }) {
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const { resolve } = useEscalationActions(e, () => {
    setResolving(false);
    setNote("");
  });
  const ackIn = ackSeconds(e);
  const name = e.patient ? fullName(e.patient) || e.patient.subject_id : e.patient_id ?? "—";

  return (
    <li className="px-5 py-4">
      <div className="grid items-start gap-x-5 gap-y-3 lg:grid-cols-[9rem_minmax(0,13rem)_minmax(0,1fr)_12rem_auto]">
        <div>
          <LevelChip level={e.level} />
        </div>
        <div className="flex items-center gap-2.5">
          {e.patient ? <Avatar name={name} seed={e.patient.id} size="sm" /> : null}
          <span className="min-w-0 leading-tight">
            {e.patient ? (
              <Link href={`/patients/${e.patient.id}`} className="block truncate font-medium text-ink hover:underline">
                {name}
              </Link>
            ) : (
              <span className="text-ink-subtle">{name}</span>
            )}
            {e.patient ? <span className="font-mono text-sm text-ink-subtle">{e.patient.subject_id}</span> : null}
          </span>
        </div>
        <div className="min-w-0">
          {e.red_flag_ids?.length ? (
            <div className="mb-1.5 flex flex-wrap gap-1">
              {e.red_flag_ids.map((id) => (
                <RedFlagChip key={id} id={id} />
              ))}
            </div>
          ) : null}
          <p className="text-sm leading-6 text-ink">{e.summary_en || (e.reason ? REASON_LABELS[e.reason] : "—")}</p>
          <div className="mt-0.5 flex flex-wrap gap-x-3 text-sm text-ink-subtle">
            {e.reason ? <span>{REASON_LABELS[e.reason]}</span> : null}
            {e.checkin_id ? (
              <Link href={`/checkins/${e.checkin_id}`} className="rounded text-accent-700 hover:underline">
                Open check-in
              </Link>
            ) : null}
            {e.patient_language === "es" ? (
              <span className="inline-flex items-center gap-1 text-accent-800">
                <Languages className="size-3.5" aria-hidden />
                Prefers Spanish
              </span>
            ) : null}
          </div>
          {e.resolution_note ? (
            <p className="mt-2 rounded-lg bg-gray-50 px-3 py-1.5 text-sm text-ink-muted">
              <strong className="font-medium text-ink">Resolution:</strong> {e.resolution_note}
            </p>
          ) : null}
        </div>
        <div className="text-sm">
          <div className="flex items-center gap-1.5">
            <EscalationStatusChip status={e.status} />
          </div>
          <div className="mt-1 text-ink-muted">
            {ackIn !== null ? <span className="font-semibold text-green-800 tabular">in {ackIn} s</span> : null}
            {e.acknowledged_by ? ` · ${e.acknowledged_by}` : ""}
            {e.ack_method ? ` · ${ACK_METHOD_LABELS[e.ack_method]}` : ""}
          </div>
          {e.acknowledged_at ? (
            <div className="text-ink-subtle">
              <RelativeTime iso={e.acknowledged_at} />
            </div>
          ) : e.paged_at ? null : (
            <div className="text-ink-subtle">Not paged (callback)</div>
          )}
          {e.repage_count > 0 ? (
            <div className="inline-flex items-center gap-1 font-medium text-amber-900">
              <AlertTriangle className="size-3.5" aria-hidden />
              Re-paged ×{e.repage_count}
            </div>
          ) : null}
        </div>
        <div className="flex justify-end">
          {e.status !== "resolved" ? (
            <Button size="sm" variant="secondary" onClick={() => setResolving((v) => !v)} aria-expanded={resolving}>
              Resolve…
            </Button>
          ) : null}
        </div>
      </div>
      {resolving ? (
        <div className="mt-3 rounded-xl bg-gray-50 p-3">
          <ResolveForm
            id={e.id}
            note={note}
            setNote={setNote}
            pending={resolve.isPending}
            onSubmit={() => note.trim() && resolve.mutate({ id: e.id, note: note.trim() })}
            onCancel={() => setResolving(false)}
          />
        </div>
      ) : null}
    </li>
  );
}
