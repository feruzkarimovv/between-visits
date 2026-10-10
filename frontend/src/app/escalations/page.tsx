"use client";

import Link from "next/link";
import { useState } from "react";
import { BellRing, CheckCircle2, CircleCheckBig, Languages } from "lucide-react";
import type { Escalation, EscalationStatus } from "@/lib/types";
import { useApiMutation, useEscalations } from "@/lib/queries";
import { formatDuration, fullName } from "@/lib/format";
import { ACK_METHOD_LABELS, PAGE_CHANNEL_LABELS, REASON_LABELS } from "@/lib/labels";
import { Button, Card, CardHeader, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th, inputClass } from "@/components/ui/primitives";
import { EscalationStatusChip, LevelChip, RedFlagChip } from "@/components/chips";
import { RelativeTime } from "@/components/RelativeTime";
import { ackSeconds } from "@/components/EscalationPanel";

const LEVEL_RANK = { emergency: 0, urgent: 1, callback: 2 } as const;

function sortOpen(list: Escalation[]): Escalation[] {
  return [...list].sort((a, b) => LEVEL_RANK[a.level] - LEVEL_RANK[b.level] || b.seconds_open - a.seconds_open);
}

function sortClosed(list: Escalation[], field: "acknowledged_at" | "resolved_at"): Escalation[] {
  return [...list].sort((a, b) => (b[field] ?? "").localeCompare(a[field] ?? ""));
}

export default function EscalationsPage() {
  const open = useEscalations("open", 2000);
  const acked = useEscalations("acknowledged", 5000);
  const resolved = useEscalations("resolved", 15000);

  return (
    <>
      <PageHeader
        title="Escalations"
        subtitle="Urgent and emergency red flags page the on-call nurse. Callbacks go to the coordinator queue."
      />
      <div className="space-y-5">
        <EscalationTable
          title="Open"
          status="open"
          query={open}
          rows={sortOpen(open.data ?? [])}
          empty="No open escalations. Red flags from check-ins appear here the moment a rule fires."
        />
        <EscalationTable
          title="Acknowledged"
          status="acknowledged"
          query={acked}
          rows={sortClosed(acked.data ?? [], "acknowledged_at")}
          empty="Nothing waiting to be resolved."
        />
        <EscalationTable
          title="Resolved"
          status="resolved"
          query={resolved}
          rows={sortClosed(resolved.data ?? [], "resolved_at")}
          empty="No resolved escalations yet."
        />
      </div>
    </>
  );
}

function EscalationTable({
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
    <Card>
      <CardHeader
        title={
          <>
            {title}
            <span className="ml-1 rounded-full bg-gray-100 px-2 text-sm font-medium text-ink-muted tabular">{query.data ? rows.length : "…"}</span>
          </>
        }
        icon={status === "open" ? <BellRing className="size-4 text-ink-subtle" aria-hidden /> : status === "acknowledged" ? <CheckCircle2 className="size-4 text-ink-subtle" aria-hidden /> : <CircleCheckBig className="size-4 text-ink-subtle" aria-hidden />}
      />
      {query.isPending ? (
        <LoadingRows rows={2} />
      ) : query.isError && !query.data ? (
        <div className="p-4">
          <ErrorState error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState className="py-7" title={empty} />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Level</Th>
              <Th>Patient</Th>
              <Th>Red flags · summary</Th>
              <Th>Paged</Th>
              <Th>{status === "open" ? "Open for" : "Acknowledged"}</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <EscalationRow key={e.id} e={e} />
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

function EscalationRow({ e }: { e: Escalation }) {
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const ack = useApiMutation<string, Escalation>({
    request: (id) => ({ path: `/api/escalations/${encodeURIComponent(id)}/ack`, init: { method: "POST", body: {} } }),
    success: "Escalation acknowledged",
    invalidate: [["escalations"], ["checkin"]],
  });
  const resolve = useApiMutation<{ id: string; note: string }, Escalation>({
    request: (v) => ({ path: `/api/escalations/${encodeURIComponent(v.id)}/resolve`, init: { method: "POST", body: { note: v.note } } }),
    success: "Escalation resolved",
    invalidate: [["escalations"], ["checkin"]],
    onSuccess: () => {
      setResolving(false);
      setNote("");
    },
  });
  const ackIn = ackSeconds(e);

  return (
    <>
      <tr className="align-top">
        <Td className="align-top">
          <LevelChip level={e.level} strong={e.status === "open"} />
        </Td>
        <Td className="align-top">
          {e.patient ? (
            <div>
              <Link href={`/patients/${e.patient.id}`} className="font-medium text-ink hover:underline">
                {fullName(e.patient) || e.patient.subject_id}
              </Link>
              <div className="font-mono text-sm text-ink-subtle">{e.patient.subject_id}</div>
            </div>
          ) : (
            <span className="text-ink-subtle">{e.patient_id ?? "—"}</span>
          )}
          {e.patient_language === "es" ? (
            <div className="mt-1 inline-flex items-center gap-1 text-sm text-accent-800">
              <Languages className="size-3.5" aria-hidden />
              Prefers Spanish
            </div>
          ) : null}
        </Td>
        <Td className="max-w-md align-top">
          {e.red_flag_ids?.length ? (
            <div className="mb-1 flex flex-wrap gap-1">
              {e.red_flag_ids.map((id) => (
                <RedFlagChip key={id} id={id} />
              ))}
            </div>
          ) : null}
          <p className="text-sm text-ink">{e.summary_en || (e.reason ? REASON_LABELS[e.reason] : "—")}</p>
          <div className="mt-1 flex flex-wrap gap-x-3 text-sm text-ink-subtle">
            {e.reason ? <span>{REASON_LABELS[e.reason]}</span> : null}
            {e.checkin_id ? (
              <Link href={`/checkins/${e.checkin_id}`} className="text-accent-700 hover:underline">
                Open check-in
              </Link>
            ) : null}
          </div>
          {e.resolution_note ? <p className="mt-1 text-sm text-ink-muted">Resolution: {e.resolution_note}</p> : null}
        </Td>
        <Td className="align-top whitespace-nowrap">
          {e.paged_at ? (
            <>
              <RelativeTime iso={e.paged_at} />
              <div className="text-sm text-ink-subtle">
                {e.page_target_name} · {PAGE_CHANNEL_LABELS[e.page_channel ?? ""] ?? e.page_channel ?? "page"}
              </div>
              {e.repage_count > 0 ? <div className="text-sm font-medium text-amber-900">Re-paged ×{e.repage_count}</div> : null}
            </>
          ) : (
            <span className="text-sm text-ink-subtle">Not paged (callback)</span>
          )}
        </Td>
        <Td className="align-top whitespace-nowrap">
          {e.status === "open" ? (
            <span className="font-semibold tabular text-ink">{formatDuration(e.seconds_open)}</span>
          ) : (
            <>
              <div className="flex items-center gap-1.5">
                <EscalationStatusChip status={e.status} />
              </div>
              <div className="mt-1 text-sm text-ink-muted">
                {ackIn !== null ? <span className="tabular">in {ackIn} s</span> : null}
                {e.acknowledged_by ? ` · ${e.acknowledged_by}` : ""}
                {e.ack_method ? ` · ${ACK_METHOD_LABELS[e.ack_method]}` : ""}
              </div>
              {e.acknowledged_at ? (
                <div className="text-sm text-ink-subtle">
                  <RelativeTime iso={e.acknowledged_at} />
                </div>
              ) : null}
            </>
          )}
        </Td>
        <Td className="align-top">
          <div className="flex justify-end gap-2">
            {e.status === "open" ? (
              <Button size="sm" variant="primary" loading={ack.isPending} onClick={() => ack.mutate(e.id)}>
                Acknowledge
              </Button>
            ) : null}
            {e.status !== "resolved" ? (
              <Button size="sm" variant="secondary" onClick={() => setResolving((v) => !v)} aria-expanded={resolving}>
                Resolve…
              </Button>
            ) : null}
          </div>
        </Td>
      </tr>
      {resolving ? (
        <tr>
          <Td colSpan={6} className="bg-gray-50">
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(ev) => {
                ev.preventDefault();
                if (note.trim()) resolve.mutate({ id: e.id, note: note.trim() });
              }}
            >
              <div className="min-w-64 flex-1">
                <label htmlFor={`note-${e.id}`} className="mb-1 block text-sm font-medium text-ink-muted">
                  Resolution note (what the team did)
                </label>
                <input
                  id={`note-${e.id}`}
                  className={inputClass}
                  value={note}
                  onChange={(ev) => setNote(ev.target.value)}
                  placeholder="e.g. Nurse spoke with patient, follow-up arranged"
                  autoFocus
                />
              </div>
              <Button type="submit" variant="primary" loading={resolve.isPending} disabled={!note.trim()}>
                Resolve
              </Button>
              <Button variant="ghost" onClick={() => setResolving(false)}>
                Cancel
              </Button>
            </form>
          </Td>
        </tr>
      ) : null}
    </>
  );
}
