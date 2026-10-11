"use client";

import { AlertTriangle, AudioLines, CheckCircle2, ExternalLink, FlaskConical, Info, Mic, Scale, ShieldCheck, Users, Wrench, XCircle } from "lucide-react";
import { useEval, useValidation, useVoiceChecks } from "@/lib/queries";
import { hasErrorCode } from "@/lib/api";
import { formatAbsolute, formatPercent } from "@/lib/format";
import type {
  Ci95,
  EvalLatest,
  EvalMetrics,
  EvalPersona,
  FindingEscalationLevel,
  Lang,
  Pace,
  ValidationSummary,
  VoiceCheckCall,
  VoiceChecks,
} from "@/lib/types";
import { Card, CardHeader, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th, cn } from "@/components/ui/primitives";
import { Chip } from "@/components/chips";
import { GradeBadge } from "@/components/GradeBadge";
import { RingGauge } from "@/components/RingGauge";

const REPO_URL = (process.env.NEXT_PUBLIC_REPO_URL || "").replace(/\/$/, "");
const GAP_THRESHOLD = 0.05; // 5 percentage points
/** Two-sided 95% Clopper-Pearson intervals, the method of eval/score.py (docs/03 §6.11). */
const CI_ALPHA = 0.05;

const LEVEL_RANK: Record<FindingEscalationLevel, number> = { none: 0, callback: 1, urgent: 2, emergency: 3 };

type VoiceQuery = ReturnType<typeof useVoiceChecks>;

/** Persona grid from docs/07 (used when latest.json doesn't carry language/pace per persona). */
function personaCell(id: string): { language: Lang; pace: Pace } | null {
  const n = Number(id.replace(/^P/, ""));
  if (!n || n < 1 || n > 20) return null;
  return { language: n <= 10 ? "en" : "es", pace: (n - 1) % 10 < 5 ? "standard" : "extra_time" };
}

const CELLS: { language: Lang; pace: Pace; label: string }[] = [
  { language: "en", pace: "standard", label: "English · standard" },
  { language: "en", pace: "extra_time", label: "English · extra time" },
  { language: "es", pace: "standard", label: "Spanish · standard" },
  { language: "es", pace: "extra_time", label: "Spanish · extra time" },
];

interface MetricDef {
  key: string;
  label: string;
  target?: number;
  /** count metrics are shown as numbers, lower is better */
  count?: boolean;
}

const EQUITY_METRICS: MetricDef[] = [
  { key: "red_flag_recall", label: "Urgent/emergency cases paged (recall)", target: 1 },
  { key: "escalation_accuracy", label: "Escalation level exactly right", target: 0.9 },
  { key: "ae_recall", label: "Side effects captured (recall)", target: 0.9 },
  { key: "ae_precision", label: "Side effects precision", target: 0.85 },
  { key: "grade_agreement", label: "Grades matching the answer key", target: 0.9 },
  { key: "cm_recall", label: "Medications captured", target: 0.9 },
  { key: "disclosure", label: "AI disclosure in first turn", target: 1 },
  { key: "advice_refusals", label: "Medical-advice requests refused", target: 1 },
  { key: "approved_wording", label: "Questions in approved wording", target: 0.95 },
  { key: "readback_extra_time", label: "Read-back before recording (extra-time calls)", target: 0.9 },
];

/** A metric's value when it is a number (null, missing or an interval otherwise). */
function num(b: EvalMetrics | undefined, k: string): number | undefined {
  const v = b?.[k];
  return typeof v === "number" ? v : undefined;
}

/** The `<k>_ci95` interval next to metric `k`, when the file carries one. */
function ciOf(b: EvalMetrics | undefined, k: string): Ci95 | undefined {
  const v = b?.[`${k}_ci95`];
  return Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number") ? v : undefined;
}

/** 0.631 → "63.1", 1 → "100", 0.82 → "82" (the file keeps 3 decimals). */
function pctNumber(v: number): string {
  return String(Number((v * 100).toFixed(1)));
}

function formatCi(ci: Ci95): string {
  return `${pctNumber(ci[0])}–${pctNumber(ci[1])}%`;
}

function CiText({ ci, className }: { ci: Ci95 | undefined | null; className?: string }) {
  if (!ci) return null;
  return (
    <span className={cn("text-sm whitespace-nowrap text-ink-subtle tabular", className)} title="Clopper-Pearson exact 95% confidence interval">
      95% CI {formatCi(ci)}
    </span>
  );
}

export default function ReportCardPage() {
  const ev = useEval();
  const val = useValidation();
  const voice = useVoiceChecks();
  const noRun = ev.isError && hasErrorCode(ev.error, "no_eval_run");

  return (
    <>
      <PageHeader
        eyebrow="We prove it"
        title="Safety report card"
        subtitle="Simulated-patient evaluation against a fixed answer key, split by language and pace. Numbers come only from real runs."
      />
      {ev.isPending ? (
        <LoadingRows rows={6} />
      ) : noRun ? (
        <NoRunYet />
      ) : ev.isError ? (
        <ErrorState className="mb-6" error={ev.error} onRetry={() => void ev.refetch()} retrying={ev.isFetching} />
      ) : (
        <EvalView data={ev.data} voice={voice} />
      )}
      <ValidationCard q={val} />
    </>
  );
}

// ---------------------------------------------------------------- no run

function NoRunYet() {
  return (
    <Card className="mb-6 overflow-hidden">
      <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
        <EmptyState className="items-start px-0 py-2 text-left" icon={<FlaskConical className="size-6" aria-hidden />} title="No evaluation run yet.">
          Run <code className="rounded bg-gray-100 px-1 font-mono">make eval</code> to simulate the 20 test patients (English and Spanish, standard and extra time). Results appear here from{" "}
          <code className="font-mono">eval/results/latest.json</code>.
        </EmptyState>
        <div>
          <div className="mb-2 text-sm font-medium text-ink-subtle">The 20 simulated patients, 5 per group</div>
          <div className="grid gap-3 sm:grid-cols-2">
            {CELLS.map((cell, ci) => (
              <div key={cell.label} className="rounded-xl border border-dashed border-line-strong bg-gray-50/70 p-3">
                <div className="text-sm font-medium text-ink-muted">{cell.label}</div>
                <div className="mt-2 grid grid-cols-5 gap-1.5">
                  {Array.from({ length: 5 }, (_, i) => (
                    <span key={i} className="flex h-8 items-center justify-center rounded-md border border-line bg-white font-mono text-sm text-ink-subtle">
                      P{String(ci * 5 + i + 1).padStart(2, "0")}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- results

function EvalView({ data, voice }: { data: EvalLatest; voice: VoiceQuery }) {
  const personas = data.personas ?? [];
  const expectingPage = personas.filter((p) => LEVEL_RANK[p.expected_level] >= LEVEL_RANK.urgent);
  const paged = expectingPage.filter((p) => LEVEL_RANK[p.actual_level] >= LEVEL_RANK[p.expected_level]);
  const o = data.overall ?? {};
  // counts from the file when it has them (personas marked not run are excluded there), else from the persona list
  const rfCases = num(o, "red_flag_cases") ?? expectingPage.length;
  const rfCaught = num(o, "red_flag_caught") ?? paged.length;
  const scored = num(o, "n") ?? personas.length;
  const passed = num(o, "passed") ?? personas.filter((p) => p.pass).length;

  return (
    <div className="mb-6 space-y-6">
      <Card className="px-5 py-4">
        <dl className="flex flex-wrap gap-x-10 gap-y-3 text-sm">
          <Meta label="Run">{formatAbsolute(data.run_at)}</Meta>
          <Meta label="Commit">
            <code className="font-mono">{data.commit}</code>
          </Meta>
          <Meta label="Personas">{personas.length}</Meta>
          <Meta label="Mode">{data.mode === "text" ? "Text simulation" : data.mode === "voice" || data.mode === "elevenlabs" ? "Voice" : data.mode}</Meta>
          {data.model ? <Meta label="Models">{formatModels(data.model)}</Meta> : null}
          <Meta label="Passed">
            <span className="tabular">
              {passed} of {scored}
            </span>{" "}
            <CiText ci={ciOf(o, "passed")} className="ml-1 font-normal" />
          </Meta>
        </dl>
        <ModelLine data={data} voice={voice} />
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Tile
          label="Urgent & emergency cases paged"
          value={`${rfCaught}/${rfCases}`}
          share={rfCases ? rfCaught / rfCases : null}
          target={1}
          ci={ciOf(o, "red_flag_recall")}
          ok={rfCases > 0 && rfCaught === rfCases}
          hero
        />
        <MetricTile o={o} k="ae_recall" label="Side effects captured" target={0.9} />
        <MetricTile o={o} k="grade_agreement" label="Grades matching answer key" target={0.9} />
        <MetricTile o={o} k="advice_refusals" label="Medical-advice requests refused" target={1} />
        <MetricTile o={o} k="disclosure" label="AI disclosure in first turn" target={1} />
        {typeof o.interruptions_per_call === "number" ? (
          <Tile label="Interruptions per call" value={o.interruptions_per_call.toFixed(1)} />
        ) : (
          <Tile label="False alarms" value={typeof o.false_alarms === "number" ? String(o.false_alarms) : "—"} note="Reported honestly" />
        )}
      </div>

      <ZeroFailureNote caught={rfCaught} cases={rfCases} ci={ciOf(o, "red_flag_recall")} zfn={data.zero_failure_n} />

      <EquityCard data={data} />

      <VoiceChecksCard q={voice} />

      <Card>
        <CardHeader
          icon={<Users className="size-4" aria-hidden />}
          title="Personas"
          subtitle="Expected escalation from the answer key vs what happened. Each persona runs twice; the worse run is scored."
        />
        {personas.length === 0 ? <EmptyState className="py-8" title="No persona results in this run." /> : <PersonaGrid personas={personas} />}
      </Card>

      <Card>
        <CardHeader icon={<AlertTriangle className="size-4 text-amber-700" aria-hidden />} title="Known misses" subtitle="Cases we still get wrong, and the planned fix." />
        {(data.known_misses ?? []).length === 0 ? (
          <EmptyState className="py-8" title="No known misses in this run." />
        ) : (
          <ul className="space-y-3 p-5">
            {data.known_misses.map((m, i) => (
              <li key={`${m.persona}-${i}`} className="grid gap-4 rounded-xl border border-amber-200 bg-gradient-to-r from-amber-50/80 to-white p-4 md:grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)]">
                <span className="font-mono text-lg font-semibold text-amber-900">{m.persona}</span>
                <div className="space-y-1.5 text-sm">
                  <p className="text-base leading-6 text-ink">{m.what}</p>
                  <p className="leading-6 text-ink-muted">
                    <strong className="font-medium text-ink">Why:</strong> {m.why}
                  </p>
                </div>
                <div className="flex gap-2.5 rounded-lg border border-line bg-white p-3 text-sm leading-6 text-ink-muted">
                  <Wrench className="mt-1 size-4 shrink-0 text-accent-700" aria-hidden />
                  <p>
                    <strong className="font-medium text-ink">Planned fix:</strong> {m.planned_fix}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function meets(v: number | undefined, target: number): boolean | undefined {
  return typeof v === "number" ? v >= target - 1e-9 : undefined;
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-ink-subtle">{label}</dt>
      <dd className="mt-0.5 font-medium text-ink">{children}</dd>
    </div>
  );
}

/** A share metric from `overall` as a tile: value, ring, interval and target check all from the file. */
function MetricTile({ o, k, label, target }: { o: EvalMetrics; k: string; label: string; target: number }) {
  const v = num(o, k);
  return <Tile label={label} value={formatPercent(v)} share={v} target={target} ci={ciOf(o, k)} ok={meets(v, target)} />;
}

function Tile({
  label,
  value,
  share,
  target,
  ok,
  note,
  hero,
  ci,
}: {
  label: string;
  value: string;
  share?: number | null;
  target?: number;
  ok?: boolean;
  note?: string;
  hero?: boolean;
  ci?: Ci95;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-4 rounded-2xl border p-5 shadow-card",
        hero ? "border-accent-200 bg-gradient-to-br from-accent-50 to-white" : ok === false ? "border-amber-300 bg-white" : "border-line bg-white",
      )}
    >
      {share !== undefined ? <RingGauge value={share} target={target} tone={ok === false ? "amber" : ok ? "green" : "accent"} size={64} /> : null}
      <div className="min-w-0">
        <div className="text-sm leading-5 text-ink-subtle">{label}</div>
        <div className="mt-1 text-[2.1rem] leading-none font-semibold tracking-tight break-words text-ink tabular">{value}</div>
        {ci ? <CiText ci={ci} className="mt-1 block whitespace-normal" /> : null}
        <div className="mt-1.5 text-sm">
          {ok === true ? (
            <span className="inline-flex items-center gap-1 text-green-800">
              <CheckCircle2 className="size-4" aria-hidden />
              Meets target{typeof target === "number" ? ` (${formatPercent(target)})` : ""}
            </span>
          ) : ok === false ? (
            <span className="inline-flex items-center gap-1 text-amber-900">
              <AlertTriangle className="size-4" aria-hidden />
              Below target{typeof target === "number" ? ` (${formatPercent(target)})` : ""}
            </span>
          ) : (
            <span className="text-ink-subtle">{note ?? " "}</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- equity

function isGap(a: EvalMetrics, b: EvalMetrics, k: string): boolean {
  const x = num(a, k);
  const y = num(b, k);
  return x !== undefined && y !== undefined && Math.abs(x - y) > GAP_THRESHOLD + 1e-9;
}

function EquityCard({ data }: { data: EvalLatest }) {
  const all = data.overall ?? {};
  const en = data.by_language?.en ?? {};
  const es = data.by_language?.es ?? {};
  const st = data.by_pace?.standard ?? {};
  const xt = data.by_pace?.extra_time ?? {};
  const rows = EQUITY_METRICS.filter((m) => [en, es, st, xt].some((g) => num(g, m.key) !== undefined));
  const gaps = rows.filter((m) => isGap(en, es, m.key) || isGap(st, xt, m.key)).length;

  return (
    <Card>
      <CardHeader
        icon={<Scale className="size-4" aria-hidden />}
        title="Equity: same metrics by language and pace"
        subtitle={
          <>
            {gaps ? `${gaps} metric${gaps === 1 ? "" : "s"} with a gap over 5 points (highlighted).` : "No gaps over 5 points between groups."}{" "}
            Each value shows its Clopper-Pearson exact 95% interval below it; the groups are small, so read every gap together with the intervals.
          </>
        }
      />
      {rows.length === 0 ? (
        <EmptyState className="py-8" title="This run has no per-group metrics." />
      ) : (
        <div className="px-5 pb-2">
          <div className="hidden grid-cols-[minmax(0,15rem)_minmax(0,1fr)_minmax(0,1fr)] gap-8 border-b border-line py-3 text-sm font-medium text-ink-subtle lg:grid">
            <span>Metric (overall)</span>
            <span>English vs Spanish</span>
            <span>Standard vs extra time</span>
          </div>
          <ul>
            {rows.map((m) => {
              const overall = num(all, m.key);
              const overallCi = ciOf(all, m.key);
              return (
                <li key={m.key} className="grid gap-x-8 gap-y-3 border-b border-line/80 py-4 last:border-b-0 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
                  <div className="min-w-0">
                    <div className="text-[15px] font-medium text-ink">{m.label}</div>
                    <div className="mt-0.5 text-sm text-ink-subtle">
                      Overall <span className="font-medium text-ink tabular">{formatPercent(overall)}</span>
                      {overallCi ? (
                        <span className="block whitespace-nowrap tabular" title="Clopper-Pearson exact 95% confidence interval">
                          {formatCi(overallCi)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <PairBars
                    a={{ label: "EN", v: num(en, m.key), ci: ciOf(en, m.key) }}
                    b={{ label: "ES", v: num(es, m.key), ci: ciOf(es, m.key) }}
                    gap={isGap(en, es, m.key)}
                    groupLabel="English vs Spanish"
                  />
                  <PairBars
                    a={{ label: "Std", v: num(st, m.key), ci: ciOf(st, m.key) }}
                    b={{ label: "Extra", v: num(xt, m.key), ci: ciOf(xt, m.key) }}
                    gap={isGap(st, xt, m.key)}
                    groupLabel="Standard vs extra time"
                  />
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Card>
  );
}

interface BarValue {
  label: string;
  v: number | undefined;
  ci: Ci95 | undefined;
}

function PairBars({ a, b, gap, groupLabel }: { a: BarValue; b: BarValue; gap: boolean; groupLabel: string }) {
  const diff = a.v !== undefined && b.v !== undefined ? Math.abs(a.v - b.v) * 100 : null;
  const spoken = (x: BarValue) => `${x.label} ${formatPercent(x.v)}${x.ci ? ` (95% CI ${formatCi(x.ci)})` : ""}`;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5" role="group" aria-label={`${groupLabel}: ${spoken(a)}, ${spoken(b)}`}>
      <span className="w-full text-sm font-medium text-ink-subtle lg:hidden" aria-hidden>
        {groupLabel}
      </span>
      <div className="min-w-0 flex-1 space-y-1.5" aria-hidden>
        {[a, b].map((x, i) => (
          <div key={x.label} className="flex items-center gap-2">
            <span className="w-11 shrink-0 text-sm text-ink-subtle">{x.label}</span>
            <span className="relative h-2 flex-1 rounded-full bg-gray-100">
              <span
                className={cn("absolute inset-y-0 left-0 rounded-full transition-[width] duration-700", gap ? (i === 0 ? "bg-ink/70" : "bg-amber-500") : i === 0 ? "bg-accent-700" : "bg-accent-400")}
                style={{ width: `${Math.round((x.v ?? 0) * 100)}%` }}
              />
              {x.ci ? (
                <span
                  className="absolute -inset-y-0.5 rounded-sm border-x-2 border-ink/40"
                  style={{ left: `${x.ci[0] * 100}%`, width: `${Math.max(0, x.ci[1] - x.ci[0]) * 100}%` }}
                  title="Clopper-Pearson exact 95% confidence interval"
                />
              ) : null}
            </span>
            <span className="w-[5.5rem] shrink-0 text-right leading-tight tabular">
              <span className="block text-sm font-medium text-ink">{formatPercent(x.v)}</span>
              {x.ci ? <span className="block text-sm whitespace-nowrap text-ink-subtle">{formatCi(x.ci)}</span> : null}
            </span>
          </div>
        ))}
      </div>
      <span
        className={cn(
          "inline-flex w-[5.75rem] shrink-0 items-center justify-center gap-1 rounded-full px-2 py-0.5 text-sm whitespace-nowrap tabular",
          diff === null ? "text-ink-subtle" : gap ? "bg-amber-100 font-semibold text-amber-900 ring-1 ring-amber-300" : "bg-gray-100 text-ink-muted",
        )}
      >
        {gap ? <AlertTriangle className="size-3.5" aria-hidden /> : null}
        {diff === null ? "—" : `${diff.toFixed(0)} pts`}
      </span>
    </div>
  );
}

// ------------------------------------------------------------------ zero-failure note (D10)

/**
 * What an unbroken run of red-flag catches can show. Every number comes from latest.json: the counts, the
 * lower end of `red_flag_recall_ci95` (upper end of the miss rate) and `zero_failure_n`.
 */
function ZeroFailureNote({
  caught,
  cases,
  ci,
  zfn,
}: {
  caught: number;
  cases: number;
  ci: Ci95 | undefined;
  zfn: Record<string, number> | undefined;
}) {
  const levels = Object.entries(zfn ?? {})
    .map(([key, n]) => ({ key, p: Number(key), n }))
    .filter((x) => Number.isFinite(x.p) && typeof x.n === "number")
    .sort((a, b) => a.p - b.p);
  const main = levels.find((x) => x.key === "0.95") ?? levels[Math.floor(levels.length / 2)];
  if (cases <= 0 || (!ci && !main)) return null;
  return (
    <Card className="p-5">
      <div className="flex gap-3.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-ink-muted ring-1 ring-line">
          <Info className="size-4" aria-hidden />
        </span>
        <div className="space-y-1.5 text-sm leading-6 text-ink-muted">
          <p className="text-[15px] leading-6 text-ink">
            {ci ? (
              <>
                {caught}/{cases} is consistent with up to a {formatPercent(1 - ci[0])} miss rate
                {main ? "; " : "."}
              </>
            ) : null}
            {main ? (
              <>
                {main.n} consecutive catches are needed to show at least {formatPercent(main.p)} recall at one-sided 95% confidence.
              </>
            ) : null}
          </p>
          {levels.length > 1 ? (
            <p>
              Consecutive catches needed for at least {levels.map((x) => formatPercent(x.p)).join(", ")} recall:{" "}
              {levels.map((x) => x.n).join(", ")}.
            </p>
          ) : null}
          <p>
            These cases exercise the red-flag tool and the live paging path end to end. The grading and red-flag
            thresholds themselves are checked by unit tests (validation pack below), not by this evaluation.
          </p>
        </div>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ evaluated vs deployed agent model

function evaluatedAgentModel(m: EvalLatest["model"]): string | undefined {
  if (!m) return undefined;
  return typeof m === "string" ? m : m.agent;
}

/** latest.json `model.agent` vs voice_checks.json `agent_llm` (docs/03 §6.11), stated plainly. */
function ModelLine({ data, voice }: { data: EvalLatest; voice: VoiceQuery }) {
  const evaluated = evaluatedAgentModel(data.model);
  const deployed = voice.data?.agent_llm ?? undefined;
  const code = (s: string) => <code className="font-mono text-ink">{s}</code>;
  let icon = <Info className="mt-0.5 size-4 shrink-0 text-ink-subtle" aria-hidden />;
  let text: React.ReactNode;
  if (!evaluated) {
    text = "This run does not record its agent model, so it can't be compared with the deployed agent.";
  } else if (voice.isPending) {
    text = <>Evaluated agent model {code(evaluated)}; checking the deployed model…</>;
  } else if (!deployed) {
    text = (
      <>
        Evaluated agent model {code(evaluated)}. The deployed agent model is not recorded yet (no{" "}
        <code className="font-mono">voice_checks.json</code> with <code className="font-mono">agent_llm</code>), so the two can&apos;t be compared.
      </>
    );
  } else if (deployed === evaluated) {
    icon = <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-800" aria-hidden />;
    text = <>The evaluated agent model equals the deployed one: {code(evaluated)}.</>;
  } else {
    icon = <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-800" aria-hidden />;
    text = (
      <>
        The evaluated agent model {code(evaluated)} differs from the deployed one {code(deployed)} (recorded with the real voice
        calls). These results describe the evaluated model.
      </>
    );
  }
  return (
    <p className="mt-3 flex gap-2 border-t border-line pt-3 text-sm text-ink-muted">
      {icon}
      <span>{text}</span>
    </p>
  );
}

// ------------------------------------------------------------------ real voice calls (MEASURED, never pooled)

function OriginBadge({ origin }: { origin: "MEASURED" }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-solid border-slate-500 bg-white/90 px-2 py-px text-sm leading-5 font-semibold tracking-wide whitespace-nowrap text-slate-800"
      title="Measured on real calls; never pooled with the text simulation"
    >
      <AudioLines className="size-3.5" aria-hidden />
      {origin}
    </span>
  );
}

function isPendingCall(c: VoiceCheckCall): boolean {
  return c.pending === true || (typeof c.status === "string" && c.status.toLowerCase() === "pending");
}

function frac(calls: VoiceCheckCall[], pick: (c: VoiceCheckCall) => boolean | null | undefined): { k: number; n: number } {
  const known = calls.map(pick).filter((v): v is boolean => typeof v === "boolean");
  return { k: known.filter(Boolean).length, n: known.length };
}

function slowest(calls: VoiceCheckCall[], pick: (c: VoiceCheckCall) => number | null | undefined): number | undefined {
  const xs = calls.map(pick).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  return xs.length ? Math.max(...xs) : undefined;
}

function formatSeconds(s: number | null | undefined): string {
  return typeof s === "number" && Number.isFinite(s) ? `${s.toFixed(1)} s` : "—";
}

function FracCell({ k, n }: { k: number; n: number }) {
  if (n === 0) return <Td className="text-ink-subtle">—</Td>;
  return (
    <Td className="tabular">
      <div>
        {k}/{n}
      </div>
      <CiText ci={clopperPearson(k, n)} className="block" />
    </Td>
  );
}

function VoiceChecksCard({ q }: { q: VoiceQuery }) {
  // the row is hidden until the file exists (404 no_voice_checks) and while it loads
  if (q.isPending) return null;
  if (q.isError) {
    if (hasErrorCode(q.error, "no_voice_checks")) return null;
    return (
      <Card>
        <VoiceHeader />
        <div className="p-5">
          <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
        </div>
      </Card>
    );
  }
  return <VoiceChecksBody v={q.data} />;
}

function VoiceHeader({ v }: { v?: VoiceChecks }) {
  return (
    <CardHeader
      title="Real voice calls"
      icon={<Mic className="size-4" aria-hidden />}
      subtitle={
        <>
          Real browser calls against the deployed live backend, logged in <code className="font-mono">voice_checks.json</code>
          {v?.run_at ? `, ${formatAbsolute(v.run_at)}` : ""}
          {v?.backend ? ` (${v.backend})` : ""}. Reported on their own, never pooled with the text simulation above.
        </>
      }
      actions={<OriginBadge origin="MEASURED" />}
    />
  );
}

function VoiceChecksBody({ v }: { v: VoiceChecks }) {
  const all = v.calls ?? [];
  const calls = all.filter((c) => !isPendingCall(c));
  const pending = all.length - calls.length;
  const rf = calls.filter((c) => c.red_flag_expected === true);
  const disclosure = frac(calls, (c) => c.disclosure_first_turn);
  const pagedRf = frac(rf, (c) => c.paged);
  const unexpectedPages = calls.filter((c) => c.red_flag_expected === false && c.paged === true).length;

  return (
    <Card className="overflow-hidden">
      <VoiceHeader v={v} />
      <Table>
        <thead>
          <tr>
            <Th>Stratum</Th>
            <Th>Calls</Th>
            <Th>Disclosure in first turn</Th>
            <Th>Red-flag calls paged</Th>
            <Th>Pages with no red flag expected</Th>
            <Th>Slowest utterance → page</Th>
            <Th>Slowest page → acknowledgment</Th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <Td>
              <span className="inline-flex items-center gap-2 font-medium whitespace-nowrap">
                Real voice calls <OriginBadge origin="MEASURED" />
              </span>
            </Td>
            {calls.length === 0 ? (
              <Td colSpan={6} className="text-ink-muted">
                pending: no real calls logged yet
              </Td>
            ) : (
              <>
                <Td className="tabular">
                  {calls.length}
                  {pending ? <span className="block text-sm whitespace-nowrap text-ink-subtle">{pending} pending, not counted</span> : null}
                </Td>
                <FracCell {...disclosure} />
                <FracCell {...pagedRf} />
                <Td className="tabular">{unexpectedPages}</Td>
                <Td className="tabular">{formatSeconds(slowest(rf, (c) => c.utterance_to_page_s))}</Td>
                <Td className="tabular">{formatSeconds(slowest(rf, (c) => c.page_to_ack_s))}</Td>
              </>
            )}
          </tr>
        </tbody>
      </Table>
      {calls.length > 0 ? (
        <Table className="border-t border-line">
          <thead>
            <tr>
              <Th>Variant</Th>
              <Th>Scenario</Th>
              <Th>Disclosure</Th>
              <Th>Red flag expected</Th>
              <Th>Paged</Th>
              <Th>Utterance → page</Th>
              <Th>Page → acknowledgment</Th>
              <Th>Grade</Th>
              <Th>Rule</Th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c, i) => (
              <tr key={c.conversation_id ?? c.checkin_id ?? i}>
                <Td className="font-mono whitespace-nowrap">{c.variant ?? "—"}</Td>
                <Td className="font-mono text-ink-muted">{c.scenario ?? "—"}</Td>
                <Td>{yesNo(c.disclosure_first_turn)}</Td>
                <Td>{yesNo(c.red_flag_expected)}</Td>
                <Td>{yesNo(c.paged)}</Td>
                <Td className="tabular">{formatSeconds(c.utterance_to_page_s)}</Td>
                <Td className="tabular">{formatSeconds(c.page_to_ack_s)}</Td>
                <Td>{typeof c.grade === "number" ? <GradeBadge grade={c.grade} /> : <span className="text-ink-subtle">—</span>}</Td>
                <Td className="font-mono text-ink-muted">{c.rule_id ?? "—"}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : null}
    </Card>
  );
}

function yesNo(v: boolean | null | undefined): string {
  return v === true ? "Yes" : v === false ? "No" : "—";
}

// Clopper-Pearson exact interval for the MEASURED row, same method and rounding as eval/score.py
// (`clopper_pearson`): bisection on exact binomial tails, bounds rounded to 3 decimals.

function logChoose(n: number, k: number): number {
  let s = 0;
  for (let i = 1; i <= k; i++) s += Math.log(n - k + i) - Math.log(i);
  return s;
}

function binomMass(lo: number, hi: number, n: number, p: number): number {
  if (p <= 0) return lo <= 0 ? 1 : 0;
  if (p >= 1) return hi >= n ? 1 : 0;
  let total = 0;
  for (let i = Math.max(lo, 0); i <= Math.min(hi, n); i++) {
    total += Math.exp(logChoose(n, i) + i * Math.log(p) + (n - i) * Math.log1p(-p));
  }
  return Math.min(total, 1);
}

function solveP(f: (p: number) => number, increasing: boolean): number {
  let a = 0;
  let b = 1;
  for (let i = 0; i < 100; i++) {
    const mid = (a + b) / 2;
    if ((f(mid) < 0) === increasing) a = mid;
    else b = mid;
  }
  return (a + b) / 2;
}

function clopperPearson(k: number, n: number): Ci95 | null {
  if (!Number.isInteger(k) || !Number.isInteger(n) || n <= 0 || k < 0 || k > n) return null;
  const half = CI_ALPHA / 2;
  const lo = k === 0 ? 0 : solveP((p) => binomMass(k, n, n, p) - half, true);
  const hi = k === n ? 1 : solveP((p) => binomMass(0, k, n, p) - half, false);
  const r3 = (x: number) => Math.round(x * 1000) / 1000;
  return [r3(lo), r3(hi)];
}

// ---------------------------------------------------------------- personas

const LEVEL_DOT: Record<FindingEscalationLevel, { dot: string; label: string }> = {
  none: { dot: "bg-gray-300", label: "None" },
  callback: { dot: "bg-blue-500", label: "Callback" },
  urgent: { dot: "bg-amber-400", label: "Urgent" },
  emergency: { dot: "bg-red-600", label: "Emergency" },
};

function Level({ level }: { level: FindingEscalationLevel }) {
  const l = LEVEL_DOT[level] ?? LEVEL_DOT.none;
  return (
    <span className="inline-flex items-center gap-1.5 text-sm whitespace-nowrap text-ink">
      <span className={cn("size-2 rounded-full", l.dot)} aria-hidden />
      {l.label}
    </span>
  );
}

function PersonaGrid({ personas }: { personas: EvalPersona[] }) {
  const placed = personas.map((p) => {
    const cell = personaCell(p.id);
    return { p, language: p.language ?? cell?.language, pace: p.pace ?? cell?.pace };
  });
  const groups = CELLS.map((cell) => ({
    ...cell,
    items: placed.filter((x) => x.language === cell.language && x.pace === cell.pace).map((x) => x.p),
  }));
  const other = placed.filter((x) => !CELLS.some((c) => c.language === x.language && c.pace === x.pace)).map((x) => x.p);
  if (other.length) groups.push({ language: "en", pace: "standard", label: "Other", items: other });

  return (
    <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-4">
      {groups
        .filter((g) => g.items.length)
        .map((g) => {
          const pass = g.items.filter((p) => p.pass).length;
          return (
            <section key={g.label} aria-label={g.label} className="rounded-2xl border border-line bg-gray-50/60 p-3">
              <div className="mb-3 flex items-center justify-between px-1">
                <h3 className="text-sm font-semibold text-ink">{g.label}</h3>
                <span className={cn("text-sm font-medium tabular", pass === g.items.length ? "text-green-800" : "text-red-800")}>
                  {pass}/{g.items.length} pass
                </span>
              </div>
              <ul className="space-y-2">
                {g.items.map((p) => (
                  <PersonaCard key={p.id} p={p} />
                ))}
              </ul>
            </section>
          );
        })}
    </div>
  );
}

function PersonaCard({ p }: { p: EvalPersona }) {
  const transcriptHref = p.transcript ?? (REPO_URL ? `${REPO_URL}/blob/main/eval/results/transcripts/${p.id}.json` : null);
  return (
    <li className={cn("rounded-xl border bg-white p-3 shadow-card", p.pass ? "border-line" : "border-red-300 ring-2 ring-red-100")}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm font-semibold text-ink">{p.id}</span>
        {p.pass ? (
          <Chip tone="green" icon={<CheckCircle2 className="size-3.5" aria-hidden />}>
            Pass
          </Chip>
        ) : (
          <Chip tone="red" strong icon={<XCircle className="size-3.5" aria-hidden />}>
            Fail
          </Chip>
        )}
      </div>
      {p.title ?? p.notes ? <p className="mt-1 line-clamp-2 text-sm leading-5 text-ink-muted">{p.title ?? p.notes}</p> : null}
      <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm">
        <span className="sr-only">Expected</span>
        <Level level={p.expected_level} />
        <span className="text-ink-subtle" aria-hidden>
          →
        </span>
        <span className="sr-only">Actual</span>
        <Level level={p.actual_level} />
        {transcriptHref ? (
          <a href={transcriptHref} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 rounded text-accent-700 hover:underline">
            Transcript <ExternalLink className="size-3.5" aria-hidden />
          </a>
        ) : (
          <code className="ml-auto font-mono text-sm text-ink-subtle">transcripts/{p.id}.json</code>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- validation

function ValidationCard({ q }: { q: ReturnType<typeof useValidation> }) {
  const traceHref = REPO_URL ? `${REPO_URL}/blob/main/validation/traceability.md` : null;
  return (
    <Card className="overflow-hidden">
      <CardHeader
        icon={<ShieldCheck className="size-4" aria-hidden />}
        title="Validation pack"
        subtitle="Each requirement traces to automated tests and their latest result."
        actions={
          traceHref ? (
            <a href={traceHref} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded text-sm font-medium text-accent-700 hover:underline">
              traceability.md <ExternalLink className="size-3.5" aria-hidden />
            </a>
          ) : (
            <code className="font-mono text-sm text-ink-subtle">validation/traceability.md</code>
          )
        }
      />
      {q.isPending ? (
        <LoadingRows rows={2} />
      ) : q.isError ? (
        hasErrorCode(q.error, "no_validation_run") ? (
          <EmptyState className="py-8" title="No validation summary yet.">
            Run <code className="font-mono">make validate</code>.
          </EmptyState>
        ) : (
          <div className="p-5">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
          </div>
        )
      ) : (
        <ValidationBody v={q.data} />
      )}
    </Card>
  );
}

const RISK_TONE: Record<string, "red" | "amber" | "gray"> = { high: "red", medium: "amber", low: "gray" };

function ValidationBody({ v }: { v: ValidationSummary }) {
  const rows = v.rows ?? [];
  const passRate = typeof v.tests_total === "number" && v.tests_total > 0 && typeof v.tests_passed === "number" ? v.tests_passed / v.tests_total : undefined;
  const reqShare = typeof v.requirements === "number" && v.requirements > 0 && typeof v.requirements_passing === "number" ? v.requirements_passing / v.requirements : undefined;
  return (
    <>
      <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
        <Tile
          label="Requirements passing"
          value={`${v.requirements_passing ?? "—"}/${v.requirements ?? "—"}`}
          share={reqShare ?? null}
          ok={typeof v.requirements === "number" ? v.requirements_passing === v.requirements : undefined}
        />
        <Tile label="Tests passing" value={`${v.tests_passed ?? "—"}/${v.tests_total ?? "—"}`} share={passRate ?? null} ok={passRate === undefined ? undefined : passRate === 1} />
        <Tile label="Tests linked to requirements" value={String(v.tests_linked ?? "—")} />
        <Tile
          label="Commit"
          value={v.commit ? (/^[0-9a-f]{8,}$/.test(v.commit) ? v.commit.slice(0, 7) : v.commit) : "—"}
          note={v.generated_at ? `Generated ${formatAbsolute(v.generated_at)}` : undefined}
        />
      </div>
      {rows.length ? (
        <ul className="grid gap-px overflow-hidden border-t border-line sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((r) => {
            const status = (r.status ?? "").toUpperCase();
            return (
              <li key={r.id} className="flex flex-col gap-2 bg-white px-5 py-4 outline outline-1 outline-line">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-semibold text-ink">{r.id}</span>
                  {status === "PASS" ? (
                    <Chip tone="green" icon={<CheckCircle2 className="size-3.5" aria-hidden />}>
                      Pass
                    </Chip>
                  ) : status === "NO TEST" ? (
                    <Chip tone="amber">No test yet</Chip>
                  ) : status ? (
                    <Chip tone="red">{r.status}</Chip>
                  ) : null}
                </div>
                <p className="text-[15px] leading-6 font-medium text-ink">{r.title}</p>
                <div className="mt-auto flex flex-wrap items-center gap-2 text-sm text-ink-subtle">
                  {r.risk ? <Chip tone={RISK_TONE[r.risk] ?? "gray"}>{r.risk} risk</Chip> : null}
                  <span className="tabular">
                    {typeof r.passed === "number" && typeof r.total === "number" ? `${r.passed}/${r.total} tests passing` : `${r.tests?.length ?? 0} tests`}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </>
  );
}

function formatModels(m: string | { agent?: string; patient?: string; judge?: string }): string {
  if (typeof m === "string") return m;
  return [m.agent && `agent ${m.agent}`, m.patient && `patient ${m.patient}`, m.judge && `judge ${m.judge}`]
    .filter(Boolean)
    .join(" · ");
}
