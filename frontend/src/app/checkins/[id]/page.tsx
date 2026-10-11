"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ClipboardCheck,
  MessageSquareText,
  Stethoscope,
  PhoneOff,
  Bot,
  User,
  Radio,
  ListChecks,
} from "lucide-react";
import { apiFetch, hasErrorCode } from "@/lib/api";
import { useApiMutation } from "@/lib/queries";
import { useNow } from "@/lib/hooks";
import type { Answer, CheckIn, CheckInDetail, DraftEntry, Finding, TranscriptTurn } from "@/lib/types";
import { formatAbsolute, formatDuration, fullName, humanize, parseTs } from "@/lib/format";
import { CHANNEL_LABELS, NURSE_TASK_LABELS, itemLabel, valueLabel } from "@/lib/labels";
import {
  Button,
  ButtonLink,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Skeleton,
  cn,
} from "@/components/ui/primitives";
import { Chip, DraftStatusChip, LanguageChip, LevelChip, PaceChip, RedFlagChip, StatusChip } from "@/components/chips";
import { GradeBadge } from "@/components/GradeBadge";
import { AiLabel } from "@/components/AiLabel";
import { EscalationPanel } from "@/components/EscalationPanel";
import { highlightTurn } from "@/components/EvidenceQuote";

const WebCallWidget = dynamic(() => import("@/components/WebCallWidget").then((m) => m.WebCallWidget), {
  ssr: false,
  loading: () => <Skeleton className="h-40 w-full" />,
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
    // 1 s while the call is live, then 5 s for 30 s while the post-call pipeline lands, then stop.
    refetchInterval: (query) => {
      const status = query.state.data?.checkin.status;
      if (!status || LIVE.has(status)) {
        terminalSince.current = null;
        return 1000;
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
    <div className="space-y-4" aria-busy="true">
      <Skeleton className="h-24 w-full" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
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
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <Link href="/" className="inline-flex items-center gap-1 text-ink-muted hover:text-ink">
          <ArrowLeft className="size-4" aria-hidden />
          Today
        </Link>
        {stale ? <span className="text-amber-800">· Connection lost, retrying… (showing last update)</span> : null}
      </div>

      <CheckInHeader checkin={checkin} detail={detail} onCancelled={onRefetch} />

      {checkin.channel === "web" ? (
        <WebCallWidget checkinId={checkin.id} subjectId={patient.subject_id} checkinStatus={checkin.status} onStarted={onRefetch} />
      ) : null}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        {/* Conversation */}
        <Card>
          <CardHeader
            title="Conversation"
            icon={<MessageSquareText className="size-4 text-ink-subtle" aria-hidden />}
            subtitle={
              effectiveView === "transcript"
                ? "Full transcript after the call. Click any evidence timestamp to jump here."
                : live
                  ? "Answers appear here as the agent records them."
                  : "Answers recorded during the call."
            }
            actions={
              hasTranscript ? (
                <div role="tablist" aria-label="Conversation view" className="flex rounded-md border border-line p-0.5">
                  {(["transcript", "answers"] as const).map((v) => (
                    <button
                      key={v}
                      role="tab"
                      aria-selected={effectiveView === v}
                      onClick={() => setView(v)}
                      className={cn(
                        "rounded px-2.5 py-1 text-sm font-medium",
                        effectiveView === v ? "bg-accent-50 text-accent-800" : "text-ink-muted hover:text-ink",
                      )}
                    >
                      {v === "transcript" ? "Transcript" : "Recorded answers"}
                    </button>
                  ))}
                </div>
              ) : null
            }
          />
          {/* Scrolls inside its own box so the escalation panel and findings stay in view during a call. */}
          <div className="max-h-[calc(100vh-15rem)] min-h-64 overflow-y-auto overscroll-contain p-4" data-conversation-scroll>
            {effectiveView === "transcript" ? (
              <TranscriptView turns={transcript} />
            ) : (
              <AnswerStream answers={answers} checkin={checkin} transcript={transcript} currentQuestion={detail.current_question ?? null} />
            )}
          </div>
        </Card>

        {/* Right column: escalation + findings */}
        <div className="space-y-4">
          {sortedEscalations.map((e) => (
            <EscalationPanel key={e.id} escalation={e} fetchedAt={fetchedAt} />
          ))}
          <Card>
            <CardHeader
              title="Findings"
              icon={<Stethoscope className="size-4 text-ink-subtle" aria-hidden />}
              subtitle="Graded by fixed CTCAE v5.0 rules, not by AI. A clinician confirms every grade."
            />
            <div className="space-y-3 p-4">
              {findings.length === 0 ? (
                <EmptyState className="py-6" title={live ? "No symptoms graded yet" : "No findings"}>
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

// ---------------------------------------------------------------- header

function CheckInHeader({ checkin, detail, onCancelled }: { checkin: CheckIn; detail: CheckInDetail; onCancelled: () => void }) {
  const now = useNow();
  const { patient } = detail;
  const live = LIVE.has(checkin.status);
  const started = parseTs(checkin.started_at);
  const elapsed =
    checkin.status === "in_progress" && started !== null && now
      ? (now - started) / 1000
      : checkin.duration_s ?? (started !== null && checkin.ended_at ? ((parseTs(checkin.ended_at) ?? started) - started) / 1000 : null);
  const speakerLabel =
    checkin.speaker === "caregiver"
      ? `Caregiver${patient.caregiver_name ? ` (${patient.caregiver_name})` : ""} answering`
      : checkin.speaker === "patient"
        ? "Patient answering"
        : "Speaker not confirmed yet";

  const cancel = useApiMutation<string, CheckIn>({
    request: (id) => ({ path: `/api/checkins/${encodeURIComponent(id)}/cancel`, init: { method: "POST" } }),
    success: "Check-in cancelled",
    invalidate: [["checkins"]],
    onSuccess: onCancelled,
  });

  return (
    <Card className={cn(live && "border-accent-200")}>
      <div className="flex flex-wrap items-start justify-between gap-4 p-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              <Link href={`/patients/${patient.id}`} className="hover:underline">
                {fullName(patient) || patient.subject_id}
              </Link>
            </h1>
            <span className="font-mono text-base text-ink-muted">{patient.subject_id}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <LanguageChip lang={checkin.language} />
            <PaceChip pace={checkin.pace} hideStandard={false} />
            <Chip tone={checkin.speaker === "caregiver" ? "blue" : "gray"} icon={<User className="size-3.5" aria-hidden />}>
              {speakerLabel}
            </Chip>
            {checkin.day_after_dose ? <Chip>Day {checkin.day_after_dose} after dose</Chip> : null}
            {checkin.channel ? (
              <Chip icon={<Radio className="size-3.5" aria-hidden />}>{CHANNEL_LABELS[checkin.channel] ?? checkin.channel}</Chip>
            ) : null}
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-3">
            <StatusChip status={checkin.status} />
            <span className="font-mono text-3xl font-semibold tabular" aria-label="Call time" title={checkin.started_at ? `Started ${formatAbsolute(checkin.started_at)}` : undefined}>
              {formatDuration(elapsed ?? 0)}
            </span>
          </div>
          {checkin.interview_state?.current && checkin.status === "in_progress" ? (
            <span className="text-sm text-ink-muted">
              Now asking: <strong className="text-ink">{itemLabel(checkin.interview_state.current)}</strong>
            </span>
          ) : null}
          {live ? (
            <Button size="sm" variant="ghost" loading={cancel.isPending} onClick={() => cancel.mutate(checkin.id)} icon={<PhoneOff className="size-4" aria-hidden />}>
              Cancel check-in
            </Button>
          ) : null}
        </div>
      </div>
      {checkin.summary_en ? (
        <div className="border-t border-line px-4 py-3">
          <div className="flex flex-wrap items-start gap-2">
            <AiLabel>AI summary</AiLabel>
            <p className="min-w-0 flex-1 text-sm leading-6 text-ink-muted">{checkin.summary_en}</p>
          </div>
        </div>
      ) : null}
    </Card>
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
      <EmptyState className="py-8" icon={<Bot className="size-6" aria-hidden />} title={checkin.status === "dialing" ? "Dialing…" : live ? "Call connected" : "No answers recorded"}>
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
          <li key={a.id} className="bv-enter rounded-lg border border-line bg-white">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-gray-50 px-3 py-1.5 text-sm">
              <span className="font-medium text-ink-muted">{itemLabel(a.item_code)}</span>
              <span className="flex items-center gap-2 text-ink-subtle">
                {a.reporter === "caregiver" ? <Chip tone="blue">Caregiver</Chip> : null}
                {a.source === "post_call_extraction" ? <Chip tone="blue">Found after the call</Chip> : null}
                {a.t_s !== null && a.t_s !== undefined ? (
                  <button
                    type="button"
                    className="tabular text-accent-700 hover:underline disabled:no-underline"
                    disabled={!turn}
                    onClick={() => turn && highlightTurn(turn.i)}
                  >
                    {formatDuration(a.t_s)}
                  </button>
                ) : (
                  <span className="tabular" title={formatAbsolute(a.created_at)}>
                    {formatAbsolute(a.created_at).split(", ").pop()?.replace(/ [A-Z]{2,4}$/, "")}
                  </span>
                )}
              </span>
            </div>
            <div className="flex flex-wrap items-end justify-between gap-3 px-3 py-2.5">
              <p className="min-w-0 flex-1 text-[15px] leading-6 text-ink" lang={a.quote_lang}>
                “{a.verbatim_quote}”
              </p>
              <span className="rounded-md bg-accent-50 px-2 py-0.5 text-sm font-semibold text-accent-900 ring-1 ring-accent-200">
                {valueLabel(a)}
              </span>
            </div>
          </li>
        );
      })}
      {live ? (
        <li className="flex items-start gap-2 rounded-lg border border-dashed border-line px-3 py-2.5 text-sm text-ink-subtle">
          <span className="flex gap-1" aria-hidden>
            <span className="size-1.5 animate-bounce rounded-full bg-ink-subtle [animation-delay:-0.3s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-ink-subtle [animation-delay:-0.15s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-ink-subtle" />
          </span>
          <span className="min-w-0">
            {checkin.interview_state?.current ? (
              <>
                <span className="font-medium text-ink-muted">Asking: {itemLabel(checkin.interview_state.current)}</span>
                {currentQuestion ? (
                  <span className="mt-0.5 block text-ink-subtle italic" lang={checkin.language}>
                    “{currentQuestion}” <span className="not-italic">(approved wording)</span>
                  </span>
                ) : null}
              </>
            ) : (
              "Listening…"
            )}
          </span>
        </li>
      ) : null}
      <li ref={endRef} aria-hidden className="h-px" />
    </ol>
  );
}

function TranscriptView({ turns }: { turns: TranscriptTurn[] }) {
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
    <ol className="space-y-1">
      {turns.map((t) => (
        <li
          key={t.i}
          id={`turn-${t.i}`}
          className={cn("grid scroll-mt-24 grid-cols-[3.5rem_1.5rem_minmax(0,1fr)] gap-2 rounded-md px-2 py-2", t.role === "user" && "bg-accent-50/50")}
        >
          <span className="pt-0.5 font-mono text-sm text-ink-subtle tabular">{formatDuration(t.t_s)}</span>
          <span className="pt-0.5 text-ink-subtle" title={t.role === "agent" ? "Agent (AI)" : "Patient / caregiver"}>
            {t.role === "agent" ? <Bot className="size-4" aria-label="Agent" /> : <User className="size-4" aria-label="Patient" />}
          </span>
          <p className={cn("text-[15px] leading-6", t.role === "agent" ? "text-ink-muted" : "font-medium text-ink")} lang={t.lang ?? undefined}>
            {t.text}
          </p>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------- findings

function FindingCard({ finding: f, answers, transcript }: { finding: Finding; answers: Answer[]; transcript: TranscriptTurn[] }) {
  const termAnswers = answers.filter((a) => (a.term ?? "") === f.term);
  const high = (f.provisional_grade ?? 0) >= 3;
  const inputs = Object.entries(f.inputs ?? {});
  return (
    <article className={cn("bv-enter rounded-lg border p-3", high ? "border-amber-300 bg-amber-50/40" : "border-line bg-white")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-ink">{f.term}</h3>
        <div className="flex flex-wrap items-center gap-1.5">
          {f.escalation_level !== "none" ? <LevelChip level={f.escalation_level} /> : null}
          <GradeBadge grade={f.provisional_grade} />
        </div>
      </div>

      {termAnswers.length ? (
        <ul className="mt-2 space-y-1 text-sm">
          {termAnswers.map((a) => {
            const turn = transcript.length ? turnForAnswer(a, transcript) : undefined;
            return (
              <li key={a.id} className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-ink-subtle">{itemLabel(a.item_code)}:</span>
                <strong className="text-ink">{valueLabel(a)}</strong>
                <button
                  type="button"
                  disabled={!turn}
                  onClick={() => turn && highlightTurn(turn.i)}
                  className="text-left text-ink-muted italic enabled:hover:text-accent-800 enabled:hover:underline"
                  lang={a.quote_lang}
                >
                  “{a.verbatim_quote}”
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {inputs.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {inputs.map(([k, v]) => (
            <span key={k} className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-sm text-ink-muted">
              {k} = {String(v)}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-2 text-sm">
        {f.grade_basis === "rule" && f.rule_text ? (
          <p className="text-ink-muted">
            <span className="font-medium text-ink">Rule {f.rule_id}</span> (CTCAE v5.0): {f.rule_text}
          </p>
        ) : (
          <p className="text-ink-muted">No CTCAE rule can grade this from phone answers. A clinician assigns the grade.</p>
        )}
      </div>

      {f.red_flag_ids.length ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-sm text-ink-subtle">Red flags:</span>
          {f.red_flag_ids.map((id) => (
            <RedFlagChip key={id} id={id} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

// ---------------------------------------------------------------- drafts

function draftTitle(d: DraftEntry): string {
  if (d.kind === "AE") return d.payload.term;
  if (d.kind === "CM") return d.payload.medication_name;
  return NURSE_TASK_LABELS[d.payload.category] ?? humanize(d.payload.category);
}

function DraftsSection({ checkin, drafts }: { checkin: CheckIn; drafts: DraftEntry[] }) {
  const live = LIVE.has(checkin.status);
  const pending = drafts.filter((d) => d.status === "draft").length;
  return (
    <Card>
      <CardHeader
        title="Drafts created"
        icon={<ListChecks className="size-4 text-ink-subtle" aria-hidden />}
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
          className="py-6"
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
        <ul className="divide-y divide-line">
          {drafts.map((d) => (
            <li key={d.id} className="bv-enter flex flex-wrap items-center gap-3 px-4 py-2.5">
              <Chip tone={d.kind === "NURSE_TASK" ? "blue" : "gray"}>{d.kind === "NURSE_TASK" ? "Nurse task" : d.kind}</Chip>
              <span className="font-medium text-ink">{draftTitle(d)}</span>
              {d.kind === "AE" ? <GradeBadge grade={d.payload.provisional_grade} /> : null}
              <span className="text-sm text-ink-subtle">
                {d.evidence.length} evidence quote{d.evidence.length === 1 ? "" : "s"}
              </span>
              <span className="ml-auto">
                <DraftStatusChip status={d.status} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
