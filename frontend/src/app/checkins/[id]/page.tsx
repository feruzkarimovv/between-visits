"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  Bot,
  ClipboardCheck,
  FastForward,
  Clock,
  Languages,
  ListChecks,
  MessageSquareText,
  PhoneOff,
  Quote,
  Radio,
  Scale,
  Stethoscope,
  User,
  UserCheck,
  WifiOff,
} from "lucide-react";
import { apiFetch, hasErrorCode } from "@/lib/api";
import { useApiMutation } from "@/lib/queries";
import { useNow } from "@/lib/hooks";
import type { Answer, CheckIn, CheckInDetail, DraftEntry, FinishResponse, Finding, TranscriptTurn } from "@/lib/types";
import { stopReplayAudio } from "@/lib/replayAudio";
import { formatAbsolute, formatDuration, fullName, humanize, parseTs } from "@/lib/format";
import { CHANNEL_LABELS, itemLabel, valueLabel } from "@/lib/labels";
import { Avatar, Button, ButtonLink, Card, CardHeader, EmptyState, ErrorState, Segmented, Skeleton, cn } from "@/components/ui/primitives";
import { Chip, DraftStatusChip, LevelChip, LiveDot, RedFlagChip } from "@/components/chips";
import { GradeBadge } from "@/components/GradeBadge";
import { AiLabel } from "@/components/AiLabel";
import { EscalationPanel, ackSeconds } from "@/components/EscalationPanel";
import { highlightTurn } from "@/components/EvidenceQuote";
import { DraftKindIcon, KIND_LABEL, draftTitle } from "@/components/DraftKind";

const WebCallWidget = dynamic(() => import("@/components/WebCallWidget").then((m) => m.WebCallWidget), {
  ssr: false,
  loading: () => <Skeleton className="h-40 w-full rounded-2xl" />,
});

const LIVE = new Set(["dialing", "in_progress"]);
const POST_CALL_WINDOW_MS = 30_000;

export default function CheckInPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const terminalSince = useRef<number | null>(null);

  const q = useQuery({
    queryKey: ["checkin", id],
    queryFn: () => apiFetch<CheckInDetail>(`/api/checkins/${encodeURIComponent(id)}`),
    enabled: !!id,
    retry: (n, e) => !hasErrorCode(e, "checkin_not_found") && n < 2,
    // 1 s while the call is live, 2 s until post-call is done, then 5 s for 30 s, then stop.
    refetchInterval: (query) => {
      const status = query.state.data?.checkin.status;
      if (!status || LIVE.has(status)) {
        terminalSince.current = null;
        return 1000;
      }
      const postcall = query.state.data?.checkin.postcall_status;
      if (status === "completed" && postcall !== "done" && postcall !== "failed") {
        terminalSince.current = null;
        return 2000;
      }
      if (terminalSince.current === null) terminalSince.current = Date.now();
      return Date.now() - terminalSince.current < POST_CALL_WINDOW_MS ? 5000 : false;
    },
    refetchIntervalInBackground: true,
  });

  if (q.isPending) return <LoadingCheckIn />;
  if (q.isError && !q.data) {
    if (hasErrorCode(q.error, "checkin_not_found"))
      return (
        <Card>
          <EmptyState title="Check-in not found" action={<ButtonLink href="/">Back to Today</ButtonLink>}>
            No check-in with ID <code className="font-mono">{id}</code>.
          </EmptyState>
        </Card>
      );
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />;
  }

  return <CheckInView detail={q.data} fetchedAt={q.dataUpdatedAt} onRefetch={() => void q.refetch()} stale={q.isError} />;
}

function LoadingCheckIn() {
  return (
    <div className="space-y-5" aria-busy="true">
      <Skeleton className="h-5 w-24" />
      <div className="h-72 animate-pulse rounded-3xl bg-rail/90" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Skeleton className="h-96 rounded-2xl" />
        <Skeleton className="h-96 rounded-2xl" />
      </div>
    </div>
  );
}

function CheckInView({
  detail,
  fetchedAt,
  onRefetch,
  stale,
}: {
  detail: CheckInDetail;
  fetchedAt: number;
  onRefetch: () => void;
  stale: boolean;
}) {
  const { checkin, patient, answers, findings, escalations, drafts, transcript } = detail;
  const live = LIVE.has(checkin.status);
  const hasTranscript = transcript.length > 0;
  const [view, setView] = useState<"auto" | "answers" | "transcript">("auto");
  const effectiveView = view === "auto" ? (hasTranscript ? "transcript" : "answers") : view;

  const sortedEscalations = useMemo(() => {
    const rank = { emergency: 0, urgent: 1, callback: 2 } as const;
    return [...escalations].sort((a, b) => rank[a.level] - rank[b.level]);
  }, [escalations]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Link href="/" className="inline-flex items-center gap-1.5 rounded-md font-medium text-ink-muted hover:text-ink">
          <ArrowLeft className="size-4" aria-hidden />
          Today
        </Link>
        <span className="text-line-strong" aria-hidden>
          /
        </span>
        <span className="text-ink-subtle">Check-in {checkin.id}</span>
        {stale ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-2 py-px font-medium text-amber-900">
            <WifiOff className="size-3.5" aria-hidden />
            Connection lost, retrying… (showing last update)
          </span>
        ) : null}
      </div>

      <CallConsole detail={detail} onCancelled={onRefetch} />

      {checkin.summary_en ? (
        <div className="bv-enter flex flex-col items-start gap-2 rounded-2xl border border-dashed border-violet-300 bg-gradient-to-r from-violet-50/80 to-white px-5 py-4 sm:flex-row sm:gap-3">
          <AiLabel className="sm:mt-1">AI summary</AiLabel>
          <p className="min-w-0 flex-1 text-[15px] leading-7 text-ink">{checkin.summary_en}</p>
        </div>
      ) : null}

      {checkin.channel === "web" ? (
        <WebCallWidget checkinId={checkin.id} subjectId={patient.subject_id} checkinStatus={checkin.status} onStarted={onRefetch} />
      ) : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        {/* Conversation */}
        <Card className="overflow-hidden">
          <CardHeader
            title="Conversation"
            icon={<MessageSquareText className="size-4" aria-hidden />}
            subtitle={
              effectiveView === "transcript"
                ? "Full transcript after the call. Click any evidence timestamp to jump here."
                : live
                  ? "Answers appear here as the agent records them."
                  : "Answers recorded during the call."
            }
            actions={
              hasTranscript ? (
                <Segmented
                  label="Conversation view"
                  size="sm"
                  value={effectiveView}
                  onChange={(v) => setView(v)}
                  options={[
                    { value: "transcript", label: "Transcript" },
                    { value: "answers", label: "Recorded answers", count: answers.length },
                  ]}
                />
              ) : null
            }
          />
          {/* Scrolls inside its own box so the escalation panel and findings stay in view during a call. */}
          <div className="bv-scroll relative max-h-[calc(100vh-14rem)] min-h-72 overflow-y-auto overscroll-contain bg-gradient-to-b from-gray-50/70 to-white p-4 sm:p-5" data-conversation-scroll>
            {effectiveView === "transcript" ? (
              <TranscriptView turns={transcript} patientName={fullName(patient) || patient.subject_id} patientSeed={patient.id} />
            ) : (
              <AnswerStream answers={answers} checkin={checkin} transcript={transcript} currentQuestion={detail.current_question ?? null} />
            )}
          </div>
        </Card>

        {/* Right column: escalation + findings */}
        <div className="space-y-5">
          {sortedEscalations.map((e) => (
            <EscalationPanel key={e.id} escalation={e} fetchedAt={fetchedAt} />
          ))}
          <Card>
            <CardHeader
              title="Findings"
              icon={<Stethoscope className="size-4" aria-hidden />}
              subtitle="Graded by fixed CTCAE v5.0 rules, not by AI. A clinician confirms every grade."
            />
            <div className="space-y-3 p-4">
              {findings.length === 0 ? (
                <EmptyState className="py-8" icon={<Scale className="size-6" aria-hidden />} title={live ? "No symptoms graded yet" : "No findings"}>
                  {live ? "Findings appear as soon as an answer is recorded." : "Nothing in this check-in matched a symptom rule."}
                </EmptyState>
              ) : (
                findings.map((f) => <FindingCard key={f.id ?? f.term} finding={f} answers={answers} transcript={transcript} />)
              )}
            </div>
          </Card>
        </div>
      </div>

      <DraftsSection checkin={checkin} drafts={drafts} />
    </div>
  );
}

// ---------------------------------------------------------------- call console

function ConsoleTag({ icon, children, title }: { icon?: React.ReactNode; children: React.ReactNode; title?: string }) {
  return (
    <span title={title} className="inline-flex items-center gap-1.5 rounded-full border border-white/12 bg-white/[0.06] px-2.5 py-0.5 text-sm font-medium whitespace-nowrap text-rail-ink">
      {icon}
      {children}
    </span>
  );
}

const STATUS_TEXT: Record<string, string> = {
  dialing: "Dialing",
  in_progress: "In call",
  completed: "Call completed",
  no_answer: "No answer",
  failed: "Call failed",
  cancelled: "Cancelled",
  scheduled: "Scheduled",
};

function CallConsole({ detail, onCancelled }: { detail: CheckInDetail; onCancelled: () => void }) {
  const now = useNow();
  const { checkin, patient } = detail;
  const live = LIVE.has(checkin.status);
  const inCall = checkin.status === "in_progress";
  const started = parseTs(checkin.started_at);
  const elapsed =
    inCall && started !== null && now
      ? (now - started) / 1000
      : checkin.duration_s ?? (started !== null && checkin.ended_at ? ((parseTs(checkin.ended_at) ?? started) - started) / 1000 : null);
  const speakerLabel =
    checkin.speaker === "caregiver"
      ? `Caregiver${patient.caregiver_name ? ` (${patient.caregiver_name})` : ""} answering`
      : checkin.speaker === "patient"
        ? "Patient answering"
        : "Speaker not confirmed yet";
  const name = fullName(patient) || patient.subject_id;
  const current = checkin.interview_state?.current;

  const cancel = useApiMutation<string, CheckIn>({
    request: (id) => ({ path: `/api/checkins/${encodeURIComponent(id)}/cancel`, init: { method: "POST" } }),
    success: "Check-in cancelled",
    invalidate: [["checkins"]],
    onSuccess: onCancelled,
  });
  // Replay only: play the rest of the scenario at once, so everything it produces shows now (docs/03 §6.12).
  const finish = useApiMutation<string, FinishResponse>({
    request: (id) => ({ path: `/api/checkins/${encodeURIComponent(id)}/finish`, init: { method: "POST" } }),
    success: "Finishing the call: results, pages and drafts appear in a moment",
    invalidate: [["checkins"], ["checkin", checkin.id], ["drafts"], ["escalations"]],
    onSuccess: onCancelled,
  });

  return (
    <section
      aria-label="Call"
      className="on-dark relative overflow-hidden rounded-3xl border border-rail-line bg-rail text-rail-ink shadow-pop"
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(90%_120%_at_0%_0%,rgb(20_137_122/0.35)_0%,transparent_55%),radial-gradient(60%_90%_at_100%_100%,rgb(94_234_212/0.10)_0%,transparent_60%)]" aria-hidden />
      <div className="bv-grid pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent_85%)]" aria-hidden />

      <div className="relative grid gap-6 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex min-w-0 items-start gap-4">
          <span className="relative hidden sm:block">
            <Avatar name={name} seed={patient.id} size="xl" className="ring-2 ring-white/20" />
            {inCall ? (
              <span className="absolute -right-0.5 -bottom-0.5 flex size-5 items-center justify-center rounded-full bg-rail">
                <LiveDot tone="live" />
              </span>
            ) : null}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h1 className="font-display text-[2.6rem] leading-[1.05] text-white">
                <Link href={`/patients/${patient.id}`} className="rounded-md underline-offset-4 hover:underline">
                  {name}
                </Link>
              </h1>
              <span className="font-mono text-base text-rail-muted">{patient.subject_id}</span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <ConsoleTag icon={<Languages className="size-3.5 text-live" aria-hidden />} title={checkin.language === "es" ? "Spanish" : "English"}>
                {checkin.language === "es" ? "Spanish" : "English"}
              </ConsoleTag>
              <ConsoleTag icon={<Clock className="size-3.5 text-live" aria-hidden />}>{checkin.pace === "extra_time" ? "Extra time" : "Standard pace"}</ConsoleTag>
              <ConsoleTag icon={<User className="size-3.5 text-live" aria-hidden />}>{speakerLabel}</ConsoleTag>
              {checkin.day_after_dose ? <ConsoleTag>Day {checkin.day_after_dose} after dose</ConsoleTag> : null}
              {checkin.channel ? (
                <ConsoleTag icon={<Radio className="size-3.5 text-live" aria-hidden />}>{CHANNEL_LABELS[checkin.channel] ?? checkin.channel}</ConsoleTag>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex flex-row items-center justify-between gap-4 lg:flex-col lg:items-end lg:justify-start">
          <div className="flex items-center gap-2 text-sm font-semibold">
            {live ? <LiveDot tone="live" /> : <span className={cn("size-2 rounded-full", checkin.status === "completed" ? "bg-green-400" : "bg-rail-muted")} aria-hidden />}
            <span className={live ? "text-live" : "text-rail-ink"}>{STATUS_TEXT[checkin.status] ?? humanize(checkin.status)}</span>
          </div>
          <span
            className="font-mono text-5xl leading-none font-semibold tracking-tight text-white tabular sm:text-6xl"
            aria-label="Call time"
            title={checkin.started_at ? `Started ${formatAbsolute(checkin.started_at)}` : undefined}
          >
            {formatDuration(elapsed ?? 0)}
          </span>
          {live ? (
            <div className="flex flex-wrap items-center justify-end gap-2">
              {checkin.channel === "replay" && inCall ? (
                <Button
                  size="sm"
                  variant="primary"
                  className="border-live/40 bg-accent-600 hover:bg-accent-500"
                  loading={finish.isPending}
                  onClick={() => {
                    stopReplayAudio();
                    finish.mutate(checkin.id);
                  }}
                  icon={<FastForward className="size-4" aria-hidden />}
                >
                  Finish now
                </Button>
              ) : null}
              <Button size="sm" variant="dark" loading={cancel.isPending} onClick={() => cancel.mutate(checkin.id)} icon={<PhoneOff className="size-4" aria-hidden />}>
                Cancel check-in
              </Button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="relative px-5 sm:px-7">
        <Waveform active={inCall} />
        <div className="mt-3 min-h-12">
          {inCall && current ? (
            <p className="text-[15px] leading-6">
              <span className="text-rail-muted">Now asking · </span>
              <strong className="font-semibold text-white">{itemLabel(current)}</strong>
              {detail.current_question ? (
                <span className="mt-0.5 block text-rail-ink/90 italic" lang={checkin.language}>
                  “{detail.current_question}” <span className="text-rail-muted not-italic">(approved wording)</span>
                </span>
              ) : null}
            </p>
          ) : checkin.status === "dialing" ? (
            <p className="text-[15px] text-rail-muted">
              {checkin.channel === "web" ? "Waiting for the browser call to start." : "Waiting for the patient to pick up."}
            </p>
          ) : inCall ? (
            <p className="text-[15px] text-rail-muted">Disclosing AI, offering a person, confirming identity…</p>
          ) : (
            <p className="text-[15px] text-rail-muted">
              {checkin.status === "completed"
                ? `Call ended${checkin.ended_at ? ` · ${formatAbsolute(checkin.ended_at)}` : ""}.`
                : `${STATUS_TEXT[checkin.status] ?? humanize(checkin.status)}.`}
            </p>
          )}
        </div>
      </div>

      <Pipeline detail={detail} />
    </section>
  );
}

/** Decorative voice activity. Deterministic heights so server and client agree. */
function Waveform({ active }: { active: boolean }) {
  const bars = 128;
  return (
    <div className={cn("flex h-14 items-center gap-[3px] overflow-hidden", active && "bv-wave")} aria-hidden>
      {Array.from({ length: bars }, (_, i) => {
        const h = 0.18 + 0.82 * Math.abs(Math.sin(i * 0.61) * Math.cos(i * 0.17 + 0.4));
        return (
          <span
            key={i}
            className={cn("w-full max-w-1.5 min-w-[2px] flex-1 rounded-full", active ? "bg-live/80" : "bg-white/15")}
            style={{
              height: `${Math.round((active ? h : 0.12 + h * 0.18) * 100)}%`,
              animationDelay: active ? `${-((i * 137) % 1100)}ms` : undefined,
              animationDuration: active ? `${900 + ((i * 53) % 500)}ms` : undefined,
            }}
          />
        );
      })}
    </div>
  );
}

type PipeState = "waiting" | "active" | "done" | "alert" | "stopped";

function PipeStep({
  n,
  icon,
  title,
  state,
  tone = "live",
  children,
}: {
  n: number;
  icon: React.ReactNode;
  title: string;
  state: PipeState;
  tone?: "live" | "red" | "amber" | "green";
  children: React.ReactNode;
}) {
  const ring = {
    waiting: "border-white/15 text-rail-muted",
    stopped: "border-white/15 text-rail-muted",
    active: "border-live/60 text-live",
    done: "border-live/40 bg-live/10 text-live",
    alert: tone === "red" ? "border-red-400 bg-red-500/20 text-red-200" : "border-amber-300 bg-amber-400/20 text-amber-200",
  }[state];
  const done = state === "done" && tone === "green";
  return (
    <li className="relative min-w-0 flex-1">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "relative flex size-10 shrink-0 items-center justify-center rounded-xl border",
            done ? "border-green-400/50 bg-green-500/15 text-green-300" : ring,
            state === "active" && "bv-breathe [--bv-glow:rgb(94_234_212/0.35)]",
            state === "alert" && (tone === "red" ? "bv-breathe [--bv-glow:rgb(248_113_113/0.45)]" : "bv-breathe [--bv-glow:rgb(251_191_36/0.45)]"),
          )}
        >
          {icon}
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-mono text-rail-muted">0{n}</span>
            <span className="font-semibold text-white">{title}</span>
          </div>
          <div className="mt-0.5 text-sm leading-5 text-rail-ink/85">{children}</div>
        </div>
      </div>
    </li>
  );
}

function Pipeline({ detail }: { detail: CheckInDetail }) {
  const { checkin, answers, findings, escalations, drafts, transcript } = detail;
  const live = LIVE.has(checkin.status);
  const inCall = checkin.status === "in_progress";
  const ended = !live;

  // 1 · listen
  const listenState: PipeState =
    checkin.status === "dialing" ? "waiting" : inCall ? "active" : checkin.status === "completed" ? "done" : "stopped";
  const listenText =
    checkin.status === "dialing"
      ? "Waiting to connect"
      : inCall
        ? `Listening · ${answers.length} answer${answers.length === 1 ? "" : "s"} recorded`
        : checkin.status === "completed"
          ? `${answers.length} answer${answers.length === 1 ? "" : "s"}${transcript.length ? ` · ${transcript.length} transcript turns` : ""}`
          : STATUS_TEXT[checkin.status] ?? humanize(checkin.status);

  // 2 · grade
  const graded = findings.filter((f) => typeof f.provisional_grade === "number");
  const top = [...graded].sort((a, b) => (b.provisional_grade ?? 0) - (a.provisional_grade ?? 0))[0];
  const gradeState: PipeState = findings.length === 0 ? (ended && checkin.status === "completed" ? "done" : "waiting") : (top?.provisional_grade ?? 0) >= 3 ? "alert" : "done";
  const gradeText =
    findings.length === 0
      ? live
        ? "No symptoms graded yet"
        : "No symptom matched a rule"
      : top
        ? `${top.term} · grade ${top.provisional_grade} (provisional)${findings.length > 1 ? ` · +${findings.length - 1} more` : ""}`
        : `${findings.length} finding${findings.length === 1 ? "" : "s"} for a clinician to grade`;

  // 3 · decide
  const openPaged = escalations.filter((e) => e.status === "open" && e.level !== "callback");
  const openCallbacks = escalations.filter((e) => e.status === "open" && e.level === "callback");
  const closed = escalations.filter((e) => e.status !== "open");
  const pending = drafts.filter((d) => d.status === "draft").length;
  let decideState: PipeState = "waiting";
  let decideTone: "live" | "red" | "amber" | "green" = "live";
  let decideText: React.ReactNode;
  if (openPaged.length) {
    const emergency = openPaged.some((e) => e.level === "emergency");
    decideState = "alert";
    decideTone = emergency ? "red" : "amber";
    decideText = `${emergency ? "Emergency" : "Urgent"}: nurse paged, waiting for acknowledgment`;
  } else if (closed.length) {
    const fastest = closed.map(ackSeconds).filter((s): s is number => s !== null);
    decideState = "done";
    decideTone = "green";
    decideText = fastest.length ? `Nurse acknowledged in ${Math.min(...fastest)} s${pending ? ` · ${pending} draft${pending === 1 ? "" : "s"} to review` : ""}` : "Acknowledged";
  } else if (openCallbacks.length) {
    decideState = "active";
    decideText = "Callback queued for the coordinator";
  } else if (pending) {
    decideState = "active";
    decideText = `${pending} draft${pending === 1 ? "" : "s"} waiting for the study team`;
  } else {
    decideText = live ? "No red flags so far" : checkin.status === "completed" && checkin.postcall_status !== "done" ? "Post-call review running…" : "Nothing waiting";
  }

  return (
    <ol className="relative mt-5 flex flex-col gap-4 border-t border-white/10 bg-black/20 px-5 py-5 sm:px-7 md:flex-row md:items-start md:gap-6" aria-label="AI listens, rules grade, humans decide">
      <PipeStep n={1} icon={<AudioLines className="size-5" aria-hidden />} title="AI listens" state={listenState}>
        {listenText}
      </PipeStep>
      <ArrowRight className="hidden size-4 shrink-0 self-center text-white/25 md:block" aria-hidden />
      <PipeStep n={2} icon={<Scale className="size-5" aria-hidden />} title="Rules grade" state={gradeState} tone="amber">
        {gradeText}
      </PipeStep>
      <ArrowRight className="hidden size-4 shrink-0 self-center text-white/25 md:block" aria-hidden />
      <PipeStep n={3} icon={<UserCheck className="size-5" aria-hidden />} title="Humans decide" state={decideState} tone={decideTone}>
        {decideText}
      </PipeStep>
    </ol>
  );
}

// ---------------------------------------------------------------- conversation

function turnForAnswer(a: Answer, transcript: TranscriptTurn[]): TranscriptTurn | undefined {
  return (
    transcript.find((t) => t.role === "user" && t.text.trim() === a.verbatim_quote.trim()) ??
    (a.t_s !== null && a.t_s !== undefined ? transcript.find((t) => t.role === "user" && Math.abs((t.t_s ?? -99) - (a.t_s ?? 0)) < 1) : undefined)
  );
}

function AnswerStream({
  answers,
  checkin,
  transcript,
  currentQuestion,
}: {
  answers: Answer[];
  checkin: CheckIn;
  transcript: TranscriptTurn[];
  currentQuestion: string | null;
}) {
  const live = LIVE.has(checkin.status);
  const endRef = useRef<HTMLLIElement>(null);
  const count = answers.length;
  useEffect(() => {
    if (!live || count === 0) return;
    // scroll only the conversation box, never the page
    const box = endRef.current?.closest("[data-conversation-scroll]");
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
  }, [count, live]);

  if (answers.length === 0) {
    return (
      <EmptyState
        className="py-10"
        icon={<Bot className="size-6" aria-hidden />}
        title={checkin.status === "dialing" ? "Dialing…" : live ? "Call connected" : "No answers recorded"}
      >
        {checkin.status === "dialing"
          ? checkin.channel === "web"
            ? "Press Start call in the browser call panel to begin."
            : "Waiting for the patient to pick up."
          : live
            ? "The agent has disclosed it is an AI and is confirming identity. Answers appear here as they are recorded."
            : "This check-in has no recorded answers."}
      </EmptyState>
    );
  }

  return (
    <ol className="space-y-3">
      {answers.map((a) => {
        const turn = transcript.length ? turnForAnswer(a, transcript) : undefined;
        return (
          <li key={a.id} className="animate-bubble rounded-xl border border-line bg-white shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3 text-sm">
              <span className="font-medium text-ink-subtle">{itemLabel(a.item_code)}</span>
              <span className="flex items-center gap-2 text-ink-subtle">
                {a.reporter === "caregiver" ? <Chip tone="blue">Caregiver</Chip> : null}
                {a.source === "post_call_extraction" ? <Chip tone="blue">Found after the call</Chip> : null}
                {a.t_s !== null && a.t_s !== undefined ? (
                  <button
                    type="button"
                    className="rounded font-mono tabular text-accent-700 enabled:hover:underline disabled:text-ink-subtle"
                    disabled={!turn}
                    onClick={() => turn && highlightTurn(turn.i)}
                  >
                    {formatDuration(a.t_s)}
                  </button>
                ) : (
                  <span className="font-mono tabular" title={formatAbsolute(a.created_at)}>
                    {formatAbsolute(a.created_at).split(", ").pop()?.replace(/ [A-Z]{2,4}$/, "")}
                  </span>
                )}
              </span>
            </div>
            <div className="flex flex-wrap items-end justify-between gap-3 px-4 pt-1.5 pb-3.5">
              <p className="min-w-0 flex-1 text-base leading-7 text-ink" lang={a.quote_lang}>
                “{a.verbatim_quote}”
              </p>
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-accent-700 px-2.5 py-1 text-sm font-semibold text-white shadow-card">
                <ArrowRight className="size-3.5 opacity-70" aria-hidden />
                {valueLabel(a)}
              </span>
            </div>
          </li>
        );
      })}
      {live ? (
        <li className="flex items-start gap-3 rounded-xl border border-dashed border-accent-300 bg-accent-50/50 px-4 py-3 text-sm">
          <span className="mt-1.5 flex gap-1" aria-hidden>
            <span className="size-1.5 animate-bounce rounded-full bg-accent-600 [animation-delay:-0.3s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-accent-600 [animation-delay:-0.15s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-accent-600" />
          </span>
          <span className="min-w-0">
            {checkin.interview_state?.current ? (
              <>
                <span className="font-semibold text-accent-900">Asking: {itemLabel(checkin.interview_state.current)}</span>
                {currentQuestion ? (
                  <span className="mt-0.5 block text-ink-muted italic" lang={checkin.language}>
                    “{currentQuestion}” <span className="not-italic">(approved wording)</span>
                  </span>
                ) : null}
              </>
            ) : (
              <span className="text-ink-muted">Listening…</span>
            )}
          </span>
        </li>
      ) : null}
      <li ref={endRef} aria-hidden className="h-px" />
    </ol>
  );
}

function TranscriptView({ turns, patientName, patientSeed }: { turns: TranscriptTurn[]; patientName: string; patientSeed: string }) {
  const done = useRef(false);
  useEffect(() => {
    if (done.current || turns.length === 0) return;
    const m = window.location.hash.match(/^#turn-(\d+)$/);
    if (m) {
      done.current = true;
      // wait a frame for layout
      requestAnimationFrame(() => highlightTurn(Number(m[1])));
    }
  }, [turns.length]);

  return (
    <ol className="space-y-2">
      {turns.map((t) => {
        const agent = t.role === "agent";
        return (
          <li key={t.i} id={`turn-${t.i}`} className={cn("flex scroll-mt-24 gap-3 rounded-xl px-1.5 py-1.5", !agent && "flex-row-reverse")}>
            {agent ? (
              <span className="mt-6 flex size-8 shrink-0 items-center justify-center rounded-full bg-ink text-white" title="Agent (AI)">
                <Bot className="size-4" aria-label="Agent" />
              </span>
            ) : (
              <span className="mt-6" title="Patient / caregiver">
                <Avatar name={patientName} seed={patientSeed} size="sm" />
                <span className="sr-only">Patient</span>
              </span>
            )}
            <div className={cn("flex max-w-[85%] min-w-0 flex-col", agent ? "items-start" : "items-end")}>
              <span className="mb-1 flex items-center gap-2 px-1 text-sm text-ink-subtle">
                <span className="font-medium">{agent ? "Agent (AI)" : patientName}</span>
                <span className="font-mono tabular">{formatDuration(t.t_s)}</span>
              </span>
              <p
                className={cn(
                  "rounded-2xl px-4 py-2.5 text-[15px] leading-6",
                  agent ? "rounded-tl-md border border-line bg-white text-ink-muted shadow-card" : "rounded-tr-md bg-accent-700 font-medium text-white shadow-card",
                )}
                lang={t.lang ?? undefined}
              >
                {t.text}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------- findings

function FindingCard({ finding: f, answers, transcript }: { finding: Finding; answers: Answer[]; transcript: TranscriptTurn[] }) {
  const termAnswers = answers.filter((a) => (a.term ?? "") === f.term);
  const high = (f.provisional_grade ?? 0) >= 3;
  const inputs = Object.entries(f.inputs ?? {});
  return (
    <article className={cn("bv-enter rounded-xl border p-4", high ? "border-amber-300 bg-gradient-to-b from-amber-50/80 to-white" : "border-line bg-white")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-ink">{f.term}</h3>
        <div className="flex flex-wrap items-center gap-1.5">
          {f.escalation_level !== "none" ? <LevelChip level={f.escalation_level} /> : null}
          <GradeBadge grade={f.provisional_grade} />
        </div>
      </div>

      {termAnswers.length ? (
        <ul className="mt-3 space-y-2 text-sm">
          {termAnswers.map((a) => {
            const turn = transcript.length ? turnForAnswer(a, transcript) : undefined;
            return (
              <li key={a.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-ink-subtle">{itemLabel(a.item_code)}</span>
                <strong className="text-ink">{valueLabel(a)}</strong>
                <button
                  type="button"
                  disabled={!turn}
                  onClick={() => turn && highlightTurn(turn.i)}
                  className="rounded text-left text-ink-muted italic enabled:hover:text-accent-800 enabled:hover:underline"
                  lang={a.quote_lang}
                >
                  “{a.verbatim_quote}”
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      <div className="mt-3 rounded-lg border border-line bg-gray-50/80 p-3 text-sm">
        {inputs.length ? (
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            {inputs.map(([k, v]) => (
              <code key={k} className="rounded-md bg-white px-1.5 py-0.5 font-mono text-sm text-ink-muted ring-1 ring-line">
                {k} = {String(v)}
              </code>
            ))}
            <ArrowRight className="size-4 text-ink-subtle" aria-hidden />
            {f.grade_basis === "rule" && f.rule_id ? <span className="font-mono font-medium text-ink">{f.rule_id}</span> : null}
          </div>
        ) : null}
        {f.grade_basis === "rule" && f.rule_text ? (
          <p className="leading-6 text-ink-muted">
            {inputs.length ? null : <span className="font-medium text-ink">Rule {f.rule_id} </span>}
            <span className="font-medium text-ink">CTCAE v5.0:</span> {f.rule_text}
          </p>
        ) : (
          <p className="leading-6 text-ink-muted">No CTCAE rule can grade this from phone answers. A clinician assigns the grade.</p>
        )}
      </div>

      {f.red_flag_ids.length ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-sm text-ink-subtle">Red flags</span>
          {f.red_flag_ids.map((id) => (
            <RedFlagChip key={id} id={id} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

// ---------------------------------------------------------------- drafts

function DraftsSection({ checkin, drafts }: { checkin: CheckIn; drafts: DraftEntry[] }) {
  const live = LIVE.has(checkin.status);
  const pending = drafts.filter((d) => d.status === "draft").length;
  return (
    <Card>
      <CardHeader
        title="Drafts created"
        icon={<ListChecks className="size-4" aria-hidden />}
        subtitle="Nothing is final until a person on the study team confirms it."
        actions={
          drafts.length ? (
            <ButtonLink href={`/review?checkin_id=${encodeURIComponent(checkin.id)}`} variant="primary" size="sm" icon={<ClipboardCheck className="size-4" aria-hidden />}>
              Review {pending ? `${pending} draft${pending === 1 ? "" : "s"}` : "drafts"}
            </ButtonLink>
          ) : null
        }
      />
      {drafts.length === 0 ? (
        <EmptyState
          className="py-8"
          title={
            live
              ? "Drafts are created after the call"
              : checkin.status === "completed" && checkin.postcall_status === "failed"
                ? "Post-call review failed"
                : checkin.status === "completed" && checkin.postcall_status !== "done"
                  ? "Post-call review running…"
                  : "No drafts"
          }
        >
          {live
            ? "When the call ends, the post-call pipeline turns answers into draft side-effect, medication and nurse-task entries with evidence."
            : checkin.status === "completed" && checkin.postcall_status === "failed"
              ? "The backend escalated this for a human to review the call. Check Escalations and the transcript."
              : checkin.status === "completed" && checkin.postcall_status !== "done"
                ? "Draft entries usually appear within a few seconds of the call ending."
                : "This check-in didn't produce any draft entries."}
        </EmptyState>
      ) : (
        <ul className="grid gap-px overflow-hidden rounded-b-2xl sm:grid-cols-2 xl:grid-cols-3">
          {drafts.map((d) => (
            <li key={d.id} className="bv-enter flex items-start gap-3 bg-white px-5 py-4 outline outline-1 outline-line">
              <DraftKindIcon kind={d.kind} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-sm text-ink-subtle">
                  {d.kind !== "NURSE_TASK" ? (
                    <span className="rounded-md bg-gray-100 px-1.5 font-mono text-sm font-medium text-ink-muted ring-1 ring-line">{d.kind}</span>
                  ) : null}
                  {KIND_LABEL[d.kind]}
                </div>
                <div className="truncate text-[15px] font-semibold text-ink">{draftTitle(d)}</div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {d.kind === "AE" ? <GradeBadge grade={d.payload.provisional_grade} /> : null}
                  <span className="inline-flex items-center gap-1 text-sm text-ink-subtle">
                    <Quote className="size-3.5" aria-hidden />
                    {d.evidence.length} evidence quote{d.evidence.length === 1 ? "" : "s"}
                  </span>
                </div>
              </div>
              <DraftStatusChip status={d.status} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

