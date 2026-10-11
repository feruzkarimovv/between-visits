"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ArrowRight,
  BellRing,
  CalendarCheck,
  CheckCircle2,
  ChevronRight,
  Clapperboard,
  ClipboardCheck,
  FileWarning,
  Globe,
  Phone,
  PhoneCall,
  PlayCircle,
  Radio,
  Send,
  Siren,
  Users,
} from "lucide-react";
import type { CreateCheckInResponse, DemoScenario, ReplayResponse, ReplaySpeed, TodayRow, TodayStatus } from "@/lib/types";
import { useApiMutation, useDrafts, useEscalations, useHealth, useSaeList, useScenarios, useTodayCheckins } from "@/lib/queries";
import { DISPLAY_TZ, fullName, todayInTz } from "@/lib/format";
import { saveWebSession } from "@/lib/webSession";
import { startReplayAudio, stopReplayAudio } from "@/lib/replayAudio";
import { useNow } from "@/lib/hooks";
import { useIdentity } from "@/lib/role";
import { Avatar, Button, Card, CardHeader, EmptyState, ErrorState, LoadingRows, Table, Td, Th, cn } from "@/components/ui/primitives";
import { LanguageChip, LiveDot, PaceChip, StatusChip } from "@/components/chips";
import { RelativeTime } from "@/components/RelativeTime";
import { CountdownClock } from "@/components/CountdownClock";

const LIVE = new Set(["dialing", "in_progress"]);

/** Replay playback multipliers the API accepts (docs/03 §6.2); 2 is the backend's demo-mode default. */
const SPEEDS: readonly ReplaySpeed[] = [1, 2, 4];
const DEFAULT_SPEED: ReplaySpeed = 2;
const DEMO_CALLS_OFF = "Demo mode: calls are off. Use Replay scenario.";

interface ReplayVars {
  scenarioId: string;
  speed: ReplaySpeed;
}

interface CallVars {
  patientId: string;
  firstName: string;
  channel: "phone" | "web";
  dayAfterDose: number;
}

const longDate = new Intl.DateTimeFormat("en-US", { timeZone: DISPLAY_TZ, weekday: "long", month: "long", day: "numeric" });
const hourFmt = new Intl.DateTimeFormat("en-US", { timeZone: DISPLAY_TZ, hour: "numeric", hour12: false });

function greeting(now: number): string {
  const h = Number(hourFmt.format(now)) % 24;
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function TodayPage() {
  const router = useRouter();
  const now = useNow();
  const identity = useIdentity();
  const date = todayInTz(now || undefined);
  const today = useTodayCheckins(date);
  const health = useHealth();
  const demoMode = health.data?.demo_mode === true;
  const scenarios = useScenarios(demoMode);
  const [scenarioId, setScenarioId] = useState<string>("");
  const [speed, setSpeed] = useState<ReplaySpeed>(DEFAULT_SPEED);

  const call = useApiMutation<CallVars, CreateCheckInResponse>({
    request: (v) => ({
      path: `/api/patients/${encodeURIComponent(v.patientId)}/checkins`,
      init: { method: "POST", body: { channel: v.channel, day_after_dose: v.dayAfterDose } },
    }),
    success: (_r, v) => (v.channel === "web" ? `Browser call ready for ${v.firstName}` : `Calling ${v.firstName}…`),
    invalidate: [["checkins"], ["patients"]],
    onSuccess: (r) => {
      if (r.web_session) saveWebSession(r.checkin.id, r.web_session);
      router.push(`/checkins/${r.checkin.id}`);
    },
  });

  const replay = useApiMutation<ReplayVars, ReplayResponse>({
    request: (v) => ({
      path: `/api/demo/replay/${encodeURIComponent(v.scenarioId)}?speed=${v.speed}`,
      init: { method: "POST" },
    }),
    success: (_r, v) => `Replay started at ${v.speed}x`,
    invalidate: [["checkins"]],
    onSuccess: (r) => router.push(`/checkins/${r.checkin_id}`),
  });

  const scenarioList = scenarios.data ?? [];
  const selectedScenario = scenarioId || scenarioList[0]?.id || "";
  const rows = today.data ?? [];
  const firstName = identity.role === "sponsor" ? "" : identity.user.startsWith("Dr.") ? identity.user : identity.user.split(" ")[0];
  const rowProps = (row: TodayRow): RowProps => ({
    row,
    demoMode,
    phoneNote: health.data?.phone_calls_note ?? null,
    webNote: health.data?.browser_calls_note ?? null,
    pendingChannel: call.isPending && call.variables?.patientId === row.patient.id ? call.variables.channel : null,
    anyPending: call.isPending,
    onCall: (channel) =>
      call.mutate({
        patientId: row.patient.id,
        firstName: row.patient.first_name ?? row.patient.subject_id,
        channel,
        dayAfterDose: row.day_after_dose ?? row.patient.next_due?.day_after_dose ?? 1,
      }),
    onOpen: () => {
      if (row.id) router.push(`/checkins/${row.id}`);
    },
  });

  return (
    <>
      <section className="relative mb-6 overflow-hidden rounded-3xl border border-line bg-white shadow-card">
        <div className="bv-grid-light pointer-events-none absolute inset-y-0 right-0 w-1/2 [mask-image:linear-gradient(to_left,black,transparent)]" aria-hidden />
        <div className="relative grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,25rem)] lg:items-center">
          <div className="min-w-0">
            <div className="text-sm font-medium text-accent-700 tabular">{now ? longDate.format(now) : " "}</div>
            <h1 className="mt-1 font-display text-[2.75rem] leading-[1.05] text-ink">
              {now ? `${greeting(now)}${firstName ? `, ${firstName}` : ""}` : "Today"}
            </h1>
            <p className="mt-2 max-w-xl text-[15px] leading-6 text-ink-muted">
              {today.data
                ? `${rows.length} check-in${rows.length === 1 ? "" : "s"} on today's list. Patients are called 1, 3 and 7 days after each dose, in their language and at their pace.`
                : "Patients are called 1, 3 and 7 days after each dose, in their language and at their pace."}
            </p>
          </div>
          {demoMode && scenarioList.length > 0 ? (
            <ReplayPanel
              scenarios={scenarioList}
              selected={selectedScenario}
              onSelect={setScenarioId}
              speed={speed}
              onSpeed={setSpeed}
              pending={replay.isPending}
              onReplay={() => {
                // start the sound inside the click (autoplay rules); the replay's t=0 follows within a request
                const sc = scenarioList.find((s) => s.id === selectedScenario);
                if (sc?.audio_url) startReplayAudio(sc.audio_url, { title: sc.title, speed });
                replay.mutate({ scenarioId: selectedScenario, speed }, { onError: () => stopReplayAudio() });
              }}
            />
          ) : null}
        </div>
        <div className="relative border-t border-line bg-gray-50/60 px-6 py-5 sm:px-8">
          <ProgressStrip rows={today.data ? rows : null} />
        </div>
      </section>

      <AttentionStrip />

      <Card>
        <CardHeader
          title="Check-ins due today"
          icon={<CalendarCheck className="size-4" aria-hidden />}
          subtitle={
            // the backend's reason when browser calls are off (always in demo mode), else how calls run
            health.data?.browser_calls_note ??
            (demoMode
              ? DEMO_CALLS_OFF
              : health.data?.phone_calls_enabled
                ? "Call by phone, or run the same check-in in the browser."
                : "Check-ins run in the browser with the same voice agent. Phone calling is off until a phone number is connected.")
          }
        />
        {today.isPending ? (
          <LoadingRows rows={5} />
        ) : today.isError ? (
          <div className="p-5">
            <ErrorState error={today.error} onRetry={() => void today.refetch()} retrying={today.isFetching} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={<CalendarCheck className="size-6" aria-hidden />} title="No check-ins due today.">
            Patients appear here 1, 3 and 7 days after a dose.
          </EmptyState>
        ) : (
          <>
            {/* phones: one card per patient */}
            <ul className="divide-y divide-line md:hidden">
              {rows.map((row) => (
                <TodayCard key={row.id ?? row.patient.id} {...rowProps(row)} />
              ))}
            </ul>
            <Table className="hidden md:block">
              <thead>
                <tr>
                  <Th>Patient</Th>
                  <Th>Day after dose</Th>
                  <Th>Language · pace</Th>
                  <Th>Caregiver</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <TodayTableRow key={row.id ?? row.patient.id} {...rowProps(row)} />
                ))}
              </tbody>
            </Table>
          </>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------- replay

function ReplayPanel({
  scenarios,
  selected,
  onSelect,
  speed,
  onSpeed,
  pending,
  onReplay,
}: {
  scenarios: DemoScenario[];
  selected: string;
  onSelect: (id: string) => void;
  speed: ReplaySpeed;
  onSpeed: (speed: ReplaySpeed) => void;
  pending: boolean;
  onReplay: () => void;
}) {
  return (
    <div className="on-dark relative overflow-hidden rounded-2xl bg-rail p-4 text-rail-ink shadow-raised">
      <div className="bv-grid pointer-events-none absolute inset-0 opacity-60" aria-hidden />
      <div className="relative">
        <div className="flex items-center gap-2 text-sm font-medium text-live">
          <Clapperboard className="size-4" aria-hidden />
          Demo mode · scripted calls{scenarios.some((s) => s.audio_url) ? " with voice" : ""}
        </div>
        <p className="mt-1 text-sm leading-5 text-rail-muted">Drives the same rules, paging and drafts as a live call.</p>
        <div className="mt-3 flex flex-col gap-2">
          <label htmlFor="scenario" className="sr-only">
            Demo mode scenario
          </label>
          <select
            id="scenario"
            value={selected}
            onChange={(e) => onSelect(e.target.value)}
            className="bv-select h-10 w-full min-w-0 cursor-pointer rounded-lg border border-rail-line bg-rail-raised px-3 text-sm text-rail-ink"
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title} ({Math.round(s.duration_s / 60)} min)
              </option>
            ))}
          </select>
          <SpeedSelector value={speed} onChange={onSpeed} disabled={pending} />
          <Button
            variant="primary"
            className="w-full border-live/40 bg-accent-600 hover:bg-accent-500"
            icon={<PlayCircle className="size-4" aria-hidden />}
            loading={pending}
            disabled={!selected}
            onClick={onReplay}
          >
            Replay scenario
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 1x / 2x / 4x replay speed as native radio buttons (arrow keys move the choice). */
function SpeedSelector({
  value,
  onChange,
  disabled,
}: {
  value: ReplaySpeed;
  onChange: (speed: ReplaySpeed) => void;
  disabled?: boolean;
}) {
  return (
    <div role="radiogroup" aria-labelledby="replay-speed-label" className="flex items-center justify-between gap-3">
      <span id="replay-speed-label" className="text-sm font-medium text-rail-muted">
        Speed
      </span>
      <div className="inline-flex rounded-lg border border-rail-line bg-rail-raised p-0.5">
        {SPEEDS.map((s) => (
          <label
            key={s}
            className={cn(
              "flex h-7 cursor-pointer items-center rounded-md px-3 text-sm font-medium tabular transition-colors",
              "has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-live",
              value === s ? "bg-rail-ink text-rail" : "text-rail-muted hover:text-rail-ink",
              disabled && "cursor-not-allowed opacity-55",
            )}
          >
            <input
              type="radio"
              name="replay-speed"
              value={s}
              checked={value === s}
              disabled={disabled}
              onChange={() => onChange(s)}
              className="sr-only"
            />
            {`${s}x`}
          </label>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- attention

type AttentionTone = "red" | "amber" | "blue" | "green" | "accent";

const ATTENTION_TONES: Record<AttentionTone, { tile: string; ring: string }> = {
  red: { tile: "bg-red-700 text-white", ring: "border-red-300 bg-red-50/60 hover:border-red-400" },
  amber: { tile: "bg-amber-400 text-amber-950", ring: "border-amber-300 bg-amber-50/60 hover:border-amber-400" },
  blue: { tile: "bg-blue-100 text-blue-800", ring: "border-blue-200 bg-blue-50/40 hover:border-blue-300" },
  green: { tile: "bg-green-100 text-green-800", ring: "border-line bg-white hover:border-gray-400/70" },
  accent: { tile: "bg-accent-100 text-accent-800", ring: "border-line bg-white hover:border-gray-400/70" },
};

function AttentionCard({
  href,
  icon,
  tone,
  label,
  title,
  detail,
}: {
  href: string;
  icon: React.ReactNode;
  tone: AttentionTone;
  label: string;
  title: React.ReactNode;
  detail?: React.ReactNode;
}) {
  const t = ATTENTION_TONES[tone];
  return (
    <Link href={href} className={cn("group flex items-center gap-4 rounded-2xl border p-4 shadow-card transition-colors", t.ring)}>
      <span className={cn("flex size-11 shrink-0 items-center justify-center rounded-xl", t.tile)}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm text-ink-subtle">{label}</span>
        <span className="block truncate text-[15px] font-semibold text-ink">{title}</span>
        {detail ? <span className="mt-0.5 block text-sm text-ink-muted">{detail}</span> : null}
      </span>
      <ChevronRight className="size-5 shrink-0 text-ink-subtle transition-transform group-hover:translate-x-0.5" aria-hidden />
    </Link>
  );
}

/** What needs a human right now: open escalations, drafts to review, sponsor reports on the clock. */
function AttentionStrip() {
  const escalations = useEscalations("open", 2000);
  const drafts = useDrafts({ status: "draft", kind: "", patient_id: "", checkin_id: "" }, 10_000);
  const saes = useSaeList();

  const open = escalations.data ?? [];
  const emergency = open.filter((e) => e.level === "emergency").length;
  const urgent = open.filter((e) => e.level === "urgent").length;
  const callbacks = open.filter((e) => e.level === "callback").length;
  const pendingDrafts = drafts.data?.length ?? null;
  const pendingSae = (saes.data ?? []).filter((s) => s.status !== "sent").sort((a, b) => a.due_at.localeCompare(b.due_at));
  const sentSae = (saes.data ?? []).filter((s) => s.status === "sent").length;
  const next = pendingSae[0];

  const esc =
    emergency > 0
      ? { tone: "red" as const, icon: <Siren className="size-5" aria-hidden />, title: `${emergency} emergency open`, detail: urgent || callbacks ? `${urgent ? `${urgent} urgent` : ""}${urgent && callbacks ? " · " : ""}${callbacks ? `${callbacks} callback${callbacks === 1 ? "" : "s"}` : ""}` : "Nurse paged" }
      : urgent > 0
        ? { tone: "amber" as const, icon: <BellRing className="size-5" aria-hidden />, title: `${urgent} urgent escalation${urgent === 1 ? "" : "s"} open`, detail: callbacks ? `${callbacks} callback${callbacks === 1 ? "" : "s"} waiting too` : "Nurse paged, waiting for acknowledgment" }
        : callbacks > 0
          ? { tone: "blue" as const, icon: <PhoneCall className="size-5" aria-hidden />, title: `${callbacks} callback${callbacks === 1 ? "" : "s"} waiting`, detail: "Coordinator to call back" }
          : { tone: "green" as const, icon: <CheckCircle2 className="size-5" aria-hidden />, title: escalations.data ? "No open escalations" : "Checking…", detail: "Red flags page the nurse within seconds" };

  return (
    <div className="mb-6 grid gap-3 md:grid-cols-3">
      <AttentionCard href="/escalations" label="Escalations" tone={esc.tone} icon={esc.icon} title={esc.title} detail={esc.detail} />
      <AttentionCard
        href="/review"
        label="Review queue"
        tone={pendingDrafts ? "accent" : "green"}
        icon={pendingDrafts ? <ClipboardCheck className="size-5" aria-hidden /> : <CheckCircle2 className="size-5" aria-hidden />}
        title={pendingDrafts === null ? "Checking…" : pendingDrafts ? `${pendingDrafts} draft${pendingDrafts === 1 ? "" : "s"} to review` : "Nothing waiting"}
        detail="Side effects, medications and nurse tasks"
      />
      {next ? (
        <AttentionCard
          href={`/sae/${next.id}`}
          label="Sponsor report"
          tone="amber"
          icon={<FileWarning className="size-5" aria-hidden />}
          title={`${next.payload.reaction.term} · ${next.status === "signed" ? "signed, not sent" : "draft"}`}
          detail={<CountdownClock size="sm" dueAt={next.due_at} />}
        />
      ) : (
        <AttentionCard
          href="/sponsor"
          label="Sponsor reports"
          tone="green"
          icon={<Send className="size-5" aria-hidden />}
          title={saes.data ? "None on the clock" : "Checking…"}
          detail={sentSae ? `${sentSae} serious-event report${sentSae === 1 ? "" : "s"} sent` : "Serious events get a 24-hour clock"}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- progress

type Bucket = "completed" | "live" | "attention" | "due" | "cancelled";

const BUCKET_OF: Record<TodayStatus, Bucket> = {
  completed: "completed",
  dialing: "live",
  in_progress: "live",
  no_answer: "attention",
  failed: "attention",
  due: "due",
  scheduled: "due",
  cancelled: "cancelled",
};

const BUCKETS: { key: Bucket; label: string; bar: string; dot: string }[] = [
  { key: "completed", label: "Completed", bar: "bg-green-600", dot: "bg-green-600" },
  { key: "live", label: "Live now", bar: "bg-accent-500", dot: "bg-accent-500" },
  { key: "attention", label: "No answer or failed", bar: "bg-amber-400", dot: "bg-amber-400" },
  { key: "due", label: "Due, not yet called", bar: "bg-gray-300", dot: "bg-gray-300" },
  { key: "cancelled", label: "Cancelled", bar: "bg-gray-200", dot: "bg-gray-200" },
];

function ProgressStrip({ rows }: { rows: TodayRow[] | null }) {
  const counts: Record<Bucket, number> = { completed: 0, live: 0, attention: 0, due: 0, cancelled: 0 };
  for (const r of rows ?? []) counts[BUCKET_OF[r.status] ?? "due"] += 1;
  const total = rows?.length ?? 0;
  const shown = BUCKETS.filter((b) => b.key === "completed" || b.key === "live" || b.key === "due" || counts[b.key] > 0);

  return (
    <div className="grid gap-4 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-center lg:gap-8">
      <div className="flex items-baseline gap-2">
        <span className="text-[2.5rem] leading-none font-semibold tracking-tighter text-ink tabular">{rows ? counts.completed : "—"}</span>
        <span className="text-[15px] text-ink-muted">
          of <span className="font-semibold text-ink tabular">{rows ? total : "—"}</span> check-ins done
        </span>
      </div>
      <div className="min-w-0">
        <div
          className="flex h-2.5 w-full gap-1 overflow-hidden rounded-full"
          role="img"
          aria-label={rows ? shown.map((b) => `${b.label}: ${counts[b.key]}`).join(", ") : "Loading"}
        >
          {rows && total > 0 ? (
            BUCKETS.filter((b) => counts[b.key] > 0).map((b) => (
              <span
                key={b.key}
                className={cn("h-full rounded-full transition-[flex-grow] duration-700", b.bar, b.key === "live" && "animate-pulse")}
                style={{ flexGrow: counts[b.key] }}
              />
            ))
          ) : (
            <span className="h-full flex-1 rounded-full bg-gray-200" />
          )}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-ink-muted">
          {shown.map((b) => (
            <li key={b.key} className="inline-flex items-center gap-2">
              {b.key === "live" && counts.live > 0 ? <LiveDot /> : <span className={cn("size-2 rounded-full", b.dot)} aria-hidden />}
              {b.label}
              <span className="font-semibold text-ink tabular">{rows ? counts[b.key] : "—"}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- rows

interface RowProps {
  row: TodayRow;
  demoMode: boolean;
  phoneNote: string | null;
  webNote: string | null;
  pendingChannel: "phone" | "web" | null;
  anyPending: boolean;
  onCall: (channel: "phone" | "web") => void;
  onOpen: () => void;
}

/** 1 · 3 · 7: which scheduled check-in after the dose this is. */
function DayDots({ day }: { day: number | null | undefined }) {
  if (!day) return <span className="text-ink-subtle">—</span>;
  return (
    <span className="inline-flex items-center gap-2.5 whitespace-nowrap">
      <span className="font-medium text-ink tabular">Day {day}</span>
      <span className="flex items-center gap-1" aria-hidden>
        {[1, 3, 7].map((d) => (
          <span
            key={d}
            className={cn(
              "flex h-5 min-w-5 items-center justify-center rounded-md px-1 text-sm tabular",
              d === day ? "bg-ink text-white" : d < day ? "bg-gray-200 text-ink-muted" : "border border-dashed border-gray-300 text-ink-subtle",
            )}
          >
            {d}
          </span>
        ))}
      </span>
    </span>
  );
}

function PatientCell({ row }: { row: TodayRow }) {
  const isLive = LIVE.has(row.status);
  const name = fullName(row.patient) || row.patient.subject_id;
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span className="relative shrink-0">
        <Avatar name={name} seed={row.patient.id} />
        {isLive ? (
          <span className="absolute -right-0.5 -bottom-0.5 flex size-3.5 items-center justify-center rounded-full bg-white">
            <LiveDot />
          </span>
        ) : null}
      </span>
      <div className="min-w-0 leading-tight">
        <Link href={`/patients/${row.patient.id}`} className="block truncate text-[15px] font-semibold text-ink hover:underline">
          {name}
        </Link>
        {row.id ? (
          <Link href={`/checkins/${row.id}`} className="font-mono text-sm text-ink-subtle hover:text-accent-700 hover:underline">
            {row.patient.subject_id}
          </Link>
        ) : (
          <span className="font-mono text-sm text-ink-subtle">{row.patient.subject_id}</span>
        )}
      </div>
    </div>
  );
}

function RowActions({ row, demoMode, phoneNote, webNote, pendingChannel, anyPending, onCall, onOpen, stretch }: RowProps & { stretch?: boolean }) {
  const isLive = LIVE.has(row.status);
  // In demo mode every call is off (docs/03 §6.2); outside it, a configuration note can turn browser calls off.
  const webOff = demoMode || !!webNote;
  const webReason = demoMode ? "Off in demo mode" : webNote ? "Browser calls off" : null;
  const webReasonId = `web-off-${stretch ? "card" : "row"}-${row.patient.id}`;
  if (isLive && row.id)
    return (
      <Button size="sm" variant="primary" className={stretch ? "flex-1" : undefined} onClick={onOpen} icon={<Radio className="size-4" aria-hidden />}>
        Open live call
        <ArrowRight className="size-4" aria-hidden />
      </Button>
    );
  return (
    <>
      {!demoMode && !phoneNote ? (
        <span title={phoneNote ?? undefined} className={stretch ? "flex flex-1" : undefined}>
          <Button
            size="sm"
            variant="secondary"
            className={stretch ? "flex-1" : undefined}
            icon={<Phone className="size-4" aria-hidden />}
            loading={pendingChannel === "phone"}
            disabled={anyPending || !!phoneNote}
            onClick={() => onCall("phone")}
          >
            Call phone
          </Button>
        </span>
      ) : null}
      <span
        className={cn("flex flex-col gap-0.5", stretch ? "flex-1 items-stretch" : "items-end")}
        title={webOff ? (webNote ?? DEMO_CALLS_OFF) : undefined}
      >
        <Button
          size="sm"
          variant={row.status === "due" && !webOff ? "soft" : "secondary"}
          icon={<Globe className="size-4" aria-hidden />}
          loading={pendingChannel === "web"}
          disabled={anyPending || webOff}
          aria-describedby={webReason ? webReasonId : undefined}
          onClick={() => onCall("web")}
        >
          Call in browser
        </Button>
        {webReason ? (
          <span id={webReasonId} className={cn("text-sm whitespace-nowrap text-ink-subtle", stretch && "text-center")}>
            {webReason}
          </span>
        ) : null}
      </span>
    </>
  );
}

function StatusCell({ row }: { row: TodayRow }) {
  const isLive = LIVE.has(row.status);
  return (
    <div className="flex flex-col items-start gap-1">
      <StatusChip status={row.status} />
      {row.started_at && !isLive ? (
        <span className="text-sm text-ink-subtle">
          <RelativeTime iso={row.started_at} />
        </span>
      ) : null}
    </div>
  );
}

function TodayTableRow(props: RowProps) {
  const { row, onOpen } = props;
  const isLive = LIVE.has(row.status);
  const clickable = !!row.id;
  return (
    <tr
      className={cn("group transition-colors", clickable && "cursor-pointer hover:bg-accent-50/40", isLive && "bg-accent-50/60")}
      onClick={(e) => {
        if (!clickable) return;
        if ((e.target as HTMLElement).closest("button, a, select")) return;
        onOpen();
      }}
    >
      <Td>
        <PatientCell row={row} />
      </Td>
      <Td>
        <DayDots day={row.day_after_dose} />
      </Td>
      <Td>
        <div className="flex flex-wrap gap-1.5">
          <LanguageChip lang={row.patient.language} />
          <PaceChip pace={row.patient.pace} />
        </div>
      </Td>
      <Td>
        {row.patient.caregiver_name ? (
          <span className="inline-flex items-center gap-1.5 text-ink-muted" title={`Caregiver: ${row.patient.caregiver_name}`}>
            <Users className="size-4 text-ink-subtle" aria-hidden />
            {row.patient.caregiver_name}
          </span>
        ) : (
          <span className="text-ink-subtle">—</span>
        )}
      </Td>
      <Td>
        <StatusCell row={row} />
      </Td>
      <Td>
        <div className="flex items-center justify-end gap-2">
          <RowActions {...props} />
        </div>
      </Td>
    </tr>
  );
}

function TodayCard(props: RowProps) {
  const { row } = props;
  const isLive = LIVE.has(row.status);
  return (
    <li className={cn("space-y-3 px-4 py-4", isLive && "bg-accent-50/60")}>
      <div className="flex items-start justify-between gap-3">
        <PatientCell row={row} />
        <StatusCell row={row} />
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <DayDots day={row.day_after_dose} />
        <LanguageChip lang={row.patient.language} />
        <PaceChip pace={row.patient.pace} />
        {row.patient.caregiver_name ? (
          <span className="inline-flex items-center gap-1 text-sm text-ink-muted" title={`Caregiver: ${row.patient.caregiver_name}`}>
            <Users className="size-4 text-ink-subtle" aria-hidden />
            {row.patient.caregiver_name}
          </span>
        ) : null}
      </div>
      <div className="flex gap-2">
        <RowActions {...props} stretch />
      </div>
    </li>
  );
}
