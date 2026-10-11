"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Syringe, LineChart, History, Ear, Languages, Clock, StickyNote } from "lucide-react";
import { usePatient } from "@/lib/queries";
import { hasErrorCode } from "@/lib/api";
import { formatDay, formatDuration, fullName, humanize, parseTs } from "@/lib/format";
import { CHANNEL_LABELS } from "@/lib/labels";
import type { CheckIn, PatientDetail } from "@/lib/types";
import { Avatar, ButtonLink, Card, CardHeader, EmptyState, ErrorState, Field, Skeleton, Table, Td, Th, cn } from "@/components/ui/primitives";
import { CaregiverChip, Chip, LanguageChip, PaceChip, StatusChip } from "@/components/chips";
import { Sparkline } from "@/components/Sparkline";
import { RelativeTime } from "@/components/RelativeTime";
import { AiLabel } from "@/components/AiLabel";
import { GradeBadge } from "@/components/GradeBadge";
import { useNow } from "@/lib/hooks";

export default function PatientPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const q = usePatient(id);
  if (q.isPending)
    return (
      <div className="space-y-5">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-48 rounded-2xl" />
        <Skeleton className="h-40 rounded-2xl" />
        <Skeleton className="h-64 rounded-2xl" />
      </div>
    );
  if (q.isError) {
    if (hasErrorCode(q.error, "patient_not_found"))
      return (
        <Card>
          <EmptyState title="Patient not found" action={<ButtonLink href="/patients">All patients</ButtonLink>} />
        </Card>
      );
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />;
  }
  return <PatientView p={q.data} />;
}

function PatientView({ p }: { p: PatientDetail }) {
  const baseline = Object.entries(p.baseline ?? {});
  const name = fullName(p) || p.subject_id;
  return (
    <div className="space-y-5">
      <Link href="/patients" className="inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden />
        Patients
      </Link>

      <Card className="relative overflow-hidden">
        <div className="bv-grid-light pointer-events-none absolute inset-y-0 right-0 w-1/2 [mask-image:linear-gradient(to_left,black,transparent)]" aria-hidden />
        <div className="relative flex flex-wrap items-center gap-5 p-6">
          <Avatar name={name} seed={p.id} size="xl" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h1 className="font-display text-[2.5rem] leading-[1.05] text-ink">{name}</h1>
              <span className="font-mono text-base text-ink-subtle">{p.subject_id}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <LanguageChip lang={p.language} long />
              <PaceChip pace={p.pace} hideStandard={false} />
              {p.hearing === "hard_of_hearing" ? <Chip icon={<Ear className="size-3.5" aria-hidden />}>Hard of hearing</Chip> : null}
              {p.open_escalations > 0 ? <Chip tone="amber">{p.open_escalations} open escalation{p.open_escalations === 1 ? "" : "s"}</Chip> : null}
            </div>
          </div>
        </div>
        <dl className="relative grid grid-cols-2 gap-x-6 gap-y-4 border-t border-line bg-gray-50/50 px-6 py-5 sm:grid-cols-3 lg:grid-cols-6">
          <Field label="Age · sex">
            {p.age} · {p.sex}
          </Field>
          <Field label="Language">
            <span className="inline-flex items-center gap-1.5">
              <Languages className="size-4 text-ink-subtle" aria-hidden />
              {p.language === "es" ? "Spanish" : "English"}
            </span>
          </Field>
          <Field label="Pace">
            <span className="inline-flex items-center gap-1.5">
              <Clock className="size-4 text-ink-subtle" aria-hidden />
              {p.pace === "extra_time" ? "Extra time" : "Standard"}
            </span>
          </Field>
          <Field label="Hearing">{humanize(p.hearing)}</Field>
          <Field label="Caregiver">
            {p.caregiver_name ? (
              <span className="flex flex-col items-start gap-1">
                <CaregiverChip name={p.caregiver_name} relation={p.caregiver_relation} />
                <span className="text-sm font-normal text-ink-subtle">{p.caregiver_may_answer ? "May answer" : "May not answer"}</span>
              </span>
            ) : (
              "None"
            )}
          </Field>
          <Field label="Baseline">{baseline.length ? baseline.map(([k, v]) => `${humanize(k)}: ${v}`).join("; ") : "—"}</Field>
        </dl>
        {p.notes ? (
          <p className="relative flex items-start gap-2 border-t border-line px-6 py-4 text-sm leading-6 text-ink-muted">
            <StickyNote className="mt-0.5 size-4 shrink-0 text-ink-subtle" aria-hidden />
            {p.notes}
          </p>
        ) : null}
      </Card>

      <DoseTimeline p={p} />

      <Card>
        <CardHeader
          title="Provisional grade over time"
          icon={<LineChart className="size-4" aria-hidden />}
          subtitle="One point per check-in, by CTCAE term. Dashed teal lines mark doses; the amber band is grade 3 and above. Hollow dots = not graded by rule."
        />
        {p.timeline.length === 0 ? (
          <EmptyState className="py-8" icon={<LineChart className="size-6" aria-hidden />} title="No graded symptoms yet.">
            Small charts appear here after the first completed check-in.
          </EmptyState>
        ) : (
          <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-3">
            {p.timeline.map((t) => {
              const last = [...t.points].reverse().find((pt) => pt.provisional_grade !== null);
              const high = (last?.provisional_grade ?? 0) >= 3;
              return (
                <div key={t.term} className={cn("rounded-xl border p-4", high ? "border-amber-200 bg-gradient-to-b from-amber-50/60 to-white" : "border-line bg-white")}>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[15px] font-semibold text-ink">{t.term}</span>
                    {last ? <GradeBadge grade={last.provisional_grade} /> : <span className="text-sm text-ink-subtle">Not graded</span>}
                  </div>
                  <Sparkline term={t.term} points={t.points} doseDates={p.dose_dates} />
                  <div className="mt-2 text-sm text-ink-subtle">Latest {last ? `grade ${last.provisional_grade} (provisional)` : "not graded"}</div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card className="overflow-hidden">
        <CardHeader title="Check-ins" icon={<History className="size-4" aria-hidden />} subtitle="Newest first" />
        {p.checkins.length === 0 ? (
          <EmptyState className="py-8" title="No check-ins yet.">
            Check-ins are scheduled 1, 3 and 7 days after each dose.
          </EmptyState>
        ) : (
          <CheckinTable rows={p.checkins} />
        )}
      </Card>
    </div>
  );
}

const dotTone = (status: string) =>
  status === "completed" ? "bg-green-600" : status === "no_answer" || status === "failed" ? "bg-amber-500" : LIVE_SET.has(status) ? "bg-accent-500" : "bg-gray-400";

const LIVE_SET = new Set(["dialing", "in_progress"]);

function DoseTimeline({ p }: { p: PatientDetail }) {
  const now = useNow();
  const doses = p.dose_dates.map((d) => Date.parse(`${d}T12:00:00Z`)).filter((n) => !Number.isNaN(n));
  const cis = p.checkins
    .map((c) => ({ c, t: parseTs(c.started_at ?? c.scheduled_for ?? c.created_at) }))
    .filter((x): x is { c: CheckIn; t: number } => x.t !== null);
  const all = [...doses, ...cis.map((x) => x.t)];
  if (!all.length) return null;
  const min = Math.min(...all) - 86_400_000;
  const max = Math.max(...all, now || 0) + 86_400_000;
  const frac = (t: number) => (t - min) / (max - min);
  const pos = (t: number) => `${frac(t) * 100}%`;
  return (
    <Card>
      <CardHeader
        title="Dose timeline"
        icon={<Syringe className="size-4" aria-hidden />}
        subtitle="Doses and the 1, 3 and 7 day check-ins after each. Hover for dates; click a dot to open the check-in."
      />
      <div className="overflow-x-auto px-6 pt-4 pb-6">
        <div className="relative min-w-[36rem]">
          {/* dose + today labels */}
          <div className="relative h-14">
            {doses.map((d, i) => (
              <div key={d} className="absolute bottom-0 flex -translate-x-1/2 flex-col items-center" style={{ left: pos(d) }}>
                <span className="rounded-full bg-accent-700 px-2.5 py-0.5 text-sm font-medium whitespace-nowrap text-white shadow-card">
                  Dose {i + 1} · {formatDay(new Date(d).toISOString())}
                </span>
                <span className="h-4 w-px bg-accent-700" aria-hidden />
              </div>
            ))}
            {now ? (
              <div className="absolute bottom-0 flex -translate-x-1/2 flex-col items-center" style={{ left: pos(now) }}>
                <span className="text-sm font-medium text-ink-muted">Today</span>
                <span className="h-4 border-l border-dashed border-ink-subtle" aria-hidden />
              </div>
            ) : null}
          </div>
          {/* track */}
          <div className="relative h-3 rounded-full bg-gray-100 ring-1 ring-line ring-inset">
            {now ? <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-accent-100 to-accent-200" style={{ width: pos(now) }} aria-hidden /> : null}
            {doses.map((d) => (
              <span
                key={d}
                className="absolute top-1/2 flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-accent-700 text-white ring-4 ring-white"
                style={{ left: pos(d) }}
                aria-hidden
              >
                <Syringe className="size-3.5" />
              </span>
            ))}
            {cis.map(({ c, t }) => (
              <Link
                key={c.id}
                href={`/checkins/${c.id}`}
                title={`Day ${c.day_after_dose ?? "?"} check-in · ${humanize(c.status)} · ${formatDay(new Date(t).toISOString())}`}
                className={cn("absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full ring-4 ring-white transition-transform hover:scale-125", dotTone(c.status))}
                style={{ left: pos(t) }}
              >
                <span className="sr-only">
                  Day {c.day_after_dose} check-in, {humanize(c.status)}
                </span>
              </Link>
            ))}
          </div>
          {/* check-in day labels */}
          <div className="relative mt-2 h-6" aria-hidden>
            {cis.map(({ c, t }) => (
              <span key={c.id} className="absolute -translate-x-1/2 text-sm font-medium whitespace-nowrap text-ink-subtle" style={{ left: pos(t) }}>
                D{c.day_after_dose ?? "?"}
              </span>
            ))}
          </div>
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-muted">
          <li className="inline-flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-green-600" aria-hidden /> Completed
          </li>
          <li className="inline-flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-amber-500" aria-hidden /> No answer or failed
          </li>
          <li className="inline-flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-gray-400" aria-hidden /> Scheduled or cancelled
          </li>
        </ul>
      </div>
    </Card>
  );
}

function CheckinTable({ rows }: { rows: CheckIn[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>When</Th>
          <Th>Day after dose</Th>
          <Th>Channel</Th>
          <Th>Status</Th>
          <Th>Duration</Th>
          <Th>Summary</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.id} className="transition-colors hover:bg-accent-50/40">
            <Td className="whitespace-nowrap">
              <Link href={`/checkins/${c.id}`} className="font-medium text-accent-700 hover:underline">
                {c.started_at ? <RelativeTime iso={c.started_at} /> : formatDay(c.scheduled_for ?? c.created_at)}
              </Link>
            </Td>
            <Td className="tabular">{c.day_after_dose ? `Day ${c.day_after_dose}` : "—"}</Td>
            <Td className="whitespace-nowrap text-ink-muted">{CHANNEL_LABELS[c.channel] ?? c.channel}</Td>
            <Td>
              <StatusChip status={c.status} />
            </Td>
            <Td className="font-mono tabular">{c.duration_s ? formatDuration(c.duration_s) : "—"}</Td>
            <Td className="max-w-lg text-ink-muted">
              {c.summary_en ? (
                <span className="flex items-start gap-2">
                  <AiLabel>AI summary</AiLabel>
                  <span className="line-clamp-2 leading-6">{c.summary_en}</span>
                </span>
              ) : (
                "—"
              )}
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
