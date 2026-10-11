"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, FileWarning, Timer } from "lucide-react";
import type { SAEReport } from "@/lib/types";
import { useSaeList } from "@/lib/queries";
import { formatAbsolute, formatSpan, parseTs } from "@/lib/format";
import { ButtonLink, Card, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th, cn } from "@/components/ui/primitives";
import { SaeStatusChip } from "@/components/chips";
import { CountdownClock } from "@/components/CountdownClock";
import { DownloadButton } from "@/components/DownloadButton";
import { GradeBadge } from "@/components/GradeBadge";
import { RelativeTime } from "@/components/RelativeTime";

/** Reports still waiting to be sent first (soonest deadline on top), then sent reports, newest first. */
function byUrgency(a: SAEReport, b: SAEReport): number {
  const aSent = a.status === "sent";
  const bSent = b.status === "sent";
  if (aSent !== bSent) return aSent ? 1 : -1;
  if (!aSent) return (parseTs(a.due_at) ?? 0) - (parseTs(b.due_at) ?? 0);
  return (parseTs(b.sent_at) ?? 0) - (parseTs(a.sent_at) ?? 0);
}

/** Serious-event reports (any role): one row per report, each with its 24-hour clock and a CIOMS JSON download. */
export default function SaeListPage() {
  const router = useRouter();
  const q = useSaeList();
  const reports = [...(q.data ?? [])].sort(byUrgency);
  const waiting = reports.filter((r) => r.status !== "sent").length;

  return (
    <>
      <PageHeader
        eyebrow="24-hour clock"
        title="Serious-event reports"
        subtitle="Drafted when the investigator marks a confirmed side effect serious. The sponsor must receive each report within 24 hours of site awareness."
      />
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 border-b border-line bg-gray-50/70 px-5 py-2.5 text-sm text-ink-muted">
          <Timer className="size-4 text-ink-subtle" aria-hidden />
          Reports waiting to be sent come first, soonest deadline on top.
          {q.data ? (
            <span className="ml-auto shrink-0 whitespace-nowrap tabular">
              {reports.length} report{reports.length === 1 ? "" : "s"}
              {waiting ? ` · ${waiting} not sent` : ""}
            </span>
          ) : null}
        </div>
        {q.isPending ? (
          <LoadingRows rows={3} />
        ) : q.isError ? (
          <div className="p-5">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
          </div>
        ) : reports.length === 0 ? (
          <EmptyState
            icon={<FileWarning className="size-6" aria-hidden />}
            title="No serious-event reports yet."
            action={<ButtonLink href="/review?status=confirmed">Open confirmed side effects</ButtonLink>}
          >
            A report and its 24-hour clock start when the investigator marks a confirmed side effect serious in the review queue.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Subject</Th>
                <Th>Event</Th>
                <Th>Status</Th>
                <Th>Site aware</Th>
                <Th>24-hour clock</Th>
                <Th>Sent to sponsor</Th>
                <Th className="text-right">Export</Th>
                <Th>
                  <span className="sr-only">Open</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <SaeRow key={r.id} report={r} onOpen={() => router.push(`/sae/${r.id}`)} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function SaeRow({ report: r, onOpen }: { report: SAEReport; onOpen: () => void }) {
  const subject = r.patient?.subject_id ?? r.payload.patient.subject_id;
  const sent = r.status === "sent";
  const received = parseTs(r.sponsor_received_at);
  const due = parseTs(r.due_at);
  const margin = received !== null && due !== null ? (due - received) / 1000 : null;
  return (
    <tr
      className="group cursor-pointer transition-colors hover:bg-accent-50/40"
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("button, a")) return;
        onOpen();
      }}
    >
      <Td className="whitespace-nowrap">
        <Link href={`/sae/${r.id}`} className="flex items-center gap-3">
          <span
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-lg ring-1",
              sent ? "bg-gray-100 text-ink-subtle ring-line" : "bg-red-50 text-red-700 ring-red-200",
            )}
            aria-hidden
          >
            <FileWarning className="size-[18px]" />
          </span>
          <span className="leading-tight">
            <span className="block font-mono text-[15px] font-semibold text-ink group-hover:underline">{subject}</span>
            <span className="font-mono text-sm text-ink-subtle">{r.id}</span>
          </span>
        </Link>
      </Td>
      <Td>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-medium text-ink">{r.payload.reaction.term}</span>
          <GradeBadge grade={r.payload.reaction.provisional_ctcae_grade} />
        </div>
      </Td>
      <Td>
        <SaeStatusChip status={r.status} />
      </Td>
      <Td className="whitespace-nowrap tabular text-ink-muted">{formatAbsolute(r.aware_at)}</Td>
      <Td className="whitespace-nowrap">
        <CountdownClock size="sm" dueAt={r.due_at} stoppedAt={r.sponsor_received_at} />
      </Td>
      <Td>
        {r.sent_at ? (
          <div className="flex flex-col leading-tight">
            <span className="font-medium text-ink tabular">
              <RelativeTime iso={r.sent_at} />
            </span>
            {margin !== null ? (
              <span className="text-sm text-ink-subtle">
                {margin >= 0 ? `${formatSpan(margin)} before deadline` : `${formatSpan(-margin)} after deadline`}
              </span>
            ) : null}
          </div>
        ) : (
          <span className="text-ink-subtle">Not yet</span>
        )}
      </Td>
      <Td className="text-right">
        <DownloadButton path={`/api/export/sae/${encodeURIComponent(r.id)}.json`} filename={`${r.id}.json`} variant="ghost">
          Download CIOMS JSON
        </DownloadButton>
      </Td>
      <Td className="w-10">
        <ChevronRight className="size-4 text-ink-subtle transition-transform group-hover:translate-x-0.5" aria-hidden />
      </Td>
    </tr>
  );
}
