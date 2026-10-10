"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Syringe, LineChart } from "lucide-react";
import { usePatient } from "@/lib/queries";
import { isApiError } from "@/lib/api";
import { formatDay, formatDuration, fullName, humanize, parseTs } from "@/lib/format";
import { CHANNEL_LABELS } from "@/lib/labels";
import type { CheckIn, PatientDetail } from "@/lib/types";
import { ButtonLink, Card, CardHeader, EmptyState, ErrorState, Field, Skeleton, Table, Td, Th } from "@/components/ui/primitives";
import { CaregiverChip, Chip, LanguageChip, PaceChip, StatusChip } from "@/components/chips";
import { Sparkline } from "@/components/Sparkline";
import { RelativeTime } from "@/components/RelativeTime";
import { AiLabel } from "@/components/AiLabel";
import { useNow } from "@/lib/hooks";

export default function PatientPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const q = usePatient(id);
  if (q.isPending)
    return (
      <div className="space-y-4">
        <Skeleton className="h-36" />
        <Skeleton className="h-64" />
      </div>
    );
  if (q.isError) {
    if (isApiError(q.error) && q.error.status === 404)
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
  return (
    <div className="space-y-4">
      <Link href="/patients" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden />
        Patients
      </Link>

      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{fullName(p)}</h1>
          <span className="font-mono text-base text-ink-muted">{p.subject_id}</span>
          <div className="flex flex-wrap gap-1.5">
            <LanguageChip lang={p.language} />
            <PaceChip pace={p.pace} hideStandard={false} />
            {p.open_escalations > 0 ? <Chip tone="amber">{p.open_escalations} open escalation{p.open_escalations === 1 ? "" : "s"}</Chip> : null}
          </div>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Field label="Age · sex">
            {p.age} · {p.sex}
          </Field>
          <Field label="Language">{p.language === "es" ? "Spanish" : "English"}</Field>
          <Field label="Pace">{p.pace === "extra_time" ? "Extra time" : "Standard"}</Field>
          <Field label="Hearing">{humanize(p.hearing)}</Field>
          <Field label="Caregiver">
            {p.caregiver_name ? (
              <span className="flex flex-col items-start gap-0.5">
                <CaregiverChip name={p.caregiver_name} relation={p.caregiver_relation} />
                <span className="font-normal text-ink-subtle">{p.caregiver_may_answer ? "May answer" : "May not answer"}</span>
              </span>
            ) : (
              "None"
            )}
          </Field>
          <Field label="Baseline">{baseline.length ? baseline.map(([k, v]) => `${humanize(k)}: ${v}`).join("; ") : "—"}</Field>
        </dl>
        {p.notes ? <p className="mt-4 rounded-md bg-gray-50 px-3 py-2 text-sm text-ink-muted">{p.notes}</p> : null}
      </Card>

      <DoseTimeline p={p} />

      <Card>
        <CardHeader
          title="Provisional grade over time"
          icon={<LineChart className="size-4 text-ink-subtle" aria-hidden />}
          subtitle="One point per check-in, by CTCAE term. Dashed teal lines mark doses; the amber line marks grade 3. Hollow dots = not graded by rule."
        />
        {p.timeline.length === 0 ? (
          <EmptyState className="py-7" title="No graded symptoms yet.">
            Small charts appear here after the first completed check-in.
          </EmptyState>
        ) : (
          <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
            {p.timeline.map((t) => {
              const last = [...t.points].reverse().find((pt) => pt.provisional_grade !== null);
              return (
                <div key={t.term} className="rounded-md border border-line p-3">
                  <div className="mb-1 flex items-baseline justify-between gap-2">
                    <span className="font-medium">{t.term}</span>
                    <span className="text-sm text-ink-subtle">
                      {last ? `Latest grade ${last.provisional_grade} (provisional)` : "Not graded"}
                    </span>
                  </div>
                  <Sparkline term={t.term} points={t.points} doseDates={p.dose_dates} />
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Check-ins" subtitle="Newest first" />
        {p.checkins.length === 0 ? (
          <EmptyState className="py-7" title="No check-ins yet.">
            Check-ins are scheduled 1, 3 and 7 days after each dose.
          </EmptyState>
        ) : (
          <CheckinTable rows={p.checkins} />
        )}
      </Card>
    </div>
  );
}

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
  const pos = (t: number) => `${((t - min) / (max - min)) * 100}%`;
  return (
    <Card>
      <CardHeader title="Dose timeline" icon={<Syringe className="size-4 text-ink-subtle" aria-hidden />} subtitle="Doses and check-ins (dots). Hover for dates." />
      <div className="px-6 pt-8 pb-10">
        <div className="relative h-1 rounded bg-gray-200">
          {doses.map((d) => (
            <div key={d} className="absolute -top-6 -translate-x-1/2 text-center" style={{ left: pos(d) }}>
              <div className="text-sm font-medium whitespace-nowrap text-accent-800">Dose {formatDay(new Date(d).toISOString())}</div>
              <div className="mx-auto mt-0.5 h-6 w-0.5 bg-accent-700" />
            </div>
          ))}
          {cis.map(({ c, t }) => (
            <Link
              key={c.id}
              href={`/checkins/${c.id}`}
              title={`Day ${c.day_after_dose ?? "?"} check-in · ${humanize(c.status)}`}
              className={`absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white ring-1 ${c.status === "completed" ? "bg-green-600 ring-green-700" : c.status === "no_answer" || c.status === "failed" ? "bg-amber-500 ring-amber-600" : "bg-gray-400 ring-gray-500"}`}
              style={{ left: pos(t) }}
            >
              <span className="sr-only">Day {c.day_after_dose} check-in</span>
            </Link>
          ))}
          {now ? (
            <div className="absolute top-3 -translate-x-1/2 text-sm whitespace-nowrap text-ink-subtle" style={{ left: pos(now) }}>
              ▲ today
            </div>
          ) : null}
        </div>
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
          <tr key={c.id} className="hover:bg-gray-50">
            <Td className="whitespace-nowrap">
              <Link href={`/checkins/${c.id}`} className="font-medium text-accent-800 hover:underline">
                {c.started_at ? <RelativeTime iso={c.started_at} /> : formatDay(c.scheduled_for ?? c.created_at)}
              </Link>
            </Td>
            <Td className="tabular">{c.day_after_dose ?? "—"}</Td>
            <Td>{CHANNEL_LABELS[c.channel] ?? c.channel}</Td>
            <Td>
              <StatusChip status={c.status} />
            </Td>
            <Td className="tabular">{c.duration_s ? formatDuration(c.duration_s) : "—"}</Td>
            <Td className="max-w-md text-ink-muted">{c.summary_en ? (
                <span className="flex items-start gap-2">
                  <AiLabel>AI summary</AiLabel>
                  <span className="line-clamp-2">{c.summary_en}</span>
                </span>
              ) : (
                "—"
              )}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
