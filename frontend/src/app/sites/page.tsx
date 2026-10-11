"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BookOpenCheck, Building2, ExternalLink, FlaskConical, KeyRound, LineChart, Scale, UserRound } from "lucide-react";
import type { AnswerKeyResponse, SignalTier, SiteRow, SitesResponse, SiteSignalLabels, SiteSignalValidation } from "@/lib/types";
import { useAnswerKey, useHealth, useSiteEquity, useSiteValidation, useSites } from "@/lib/queries";
import { DEMO_IDENTITIES, setRole, useIdentity } from "@/lib/role";
import { errorMessage, hasErrorCode } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { roundHalfUp } from "@/lib/round";
import { Button, Card, CardHeader, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th, cn } from "@/components/ui/primitives";
import { DataOriginBadge } from "@/components/DataOriginBadge";
import { TierBadge } from "@/components/TierBadge";
import { FunnelPlot, type NotComputedMarker } from "@/components/FunnelPlot";
import { CommittedConfusionTable, FailureCaseTable, NullRatesTable, PowerTable, SensitivityTable } from "@/components/PowerTable";
import { EquityBlock } from "@/components/EquityBlock";

/**
 * `/sites` Site Signal overview (WS3 F12; docs/06 § Site Signal pages, docs/10 §6).
 * Every number, tier, reason, footer and answer-key text comes from `GET /api/sites`,
 * `GET /api/site-signal/answer-key` or `GET /api/site-signal/validation`; this file holds no result literals.
 */

/** Repository for the WHAT_IT_GETS_WRONG.md and SAP links; NEXT_PUBLIC_REPO_URL overrides the default. */
const REPO_URL = (process.env.NEXT_PUBLIC_REPO_URL || "https://github.com/feruzkarimovv/between-visits").replace(/\/$/, "");

type Tab = "signal" | "how";
const TABS: { id: Tab; label: string; icon: typeof LineChart }[] = [
  { id: "signal", label: "Signal", icon: LineChart },
  { id: "how", label: "How well it works", icon: BookOpenCheck },
];

function canViewRankings(role: string): boolean {
  return role === "cra" || role === "sponsor";
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

/** Half up on the shortest decimal string, as validation/render_numbers.py rounds the same values in the documents. */
function num(v: number | null, digits: number): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : roundHalfUp(v, digits);
}

/** `labels.footer_expected_false_look` with `{expected_false_look}` filled from the run (2 decimals, as in report.md). */
function footerText(labels: SiteSignalLabels, expected: number): string {
  return labels.footer_expected_false_look.replace("{expected_false_look}", num(expected, 2));
}

function reasonText(labels: SiteSignalLabels, row: SiteRow): string {
  const reason = row.not_computed_reason ? (labels.reasons[row.not_computed_reason] ?? row.not_computed_reason) : null;
  return reason ? `${labels.not_computed}: ${reason}` : labels.not_computed;
}

export default function SitesPage() {
  const identity = useIdentity();
  const canView = canViewRankings(identity.role);
  const health = useHealth();
  const sites = useSites(canView);
  const [tab, setTab] = useState<Tab>("signal");

  const run = sites.data?.run;
  const signalHealth = health.data?.site_signal;
  const sapCommit = run?.sap_tag_commit ?? signalHealth?.sap_tag_commit ?? null;
  const generatedAt = run?.generated_at ?? signalHealth?.generated_at ?? null;
  const origin = run?.data_origin ?? signalHealth?.data_origin ?? "SIMULATED";

  return (
    <>
      <PageHeader
        eyebrow="Sponsor-side monitoring"
        title="Site Signal"
        subtitle="Episodes patients reported on calls, compared with each site's AE log: a reason to look, not a finding. Thresholds fixed from the pre-registered null."
      />

      <Card className="mb-5 px-5 py-3.5">
        <dl className="flex flex-wrap gap-x-10 gap-y-3 text-sm">
          <Meta label="Analysis plan">
            <span className="font-medium text-ink">sap-v1</span>{" "}
            {sapCommit ? (
              <code className="rounded-md bg-gray-100 px-1.5 py-0.5 font-mono text-sm text-ink ring-1 ring-line ring-inset">
                {sapCommit.slice(0, 7)}
              </code>
            ) : (
              <span className="text-ink-subtle">tag unavailable</span>
            )}
          </Meta>
          {generatedAt ? <Meta label="Run">{formatDate(generatedAt)}</Meta> : null}
          <Meta label="Data">
            <DataOriginBadge origin={origin} />
          </Meta>
        </dl>
      </Card>

      <div
        role="tablist"
        aria-label="Site Signal views"
        className="mb-5 inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-gray-100/80 p-1"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`sites-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`sites-panel-${id}`}
            onClick={() => setTab(id)}
            className={cn(
              "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-3.5 text-sm font-medium whitespace-nowrap transition-colors",
              tab === id ? "bg-white text-ink shadow-card ring-1 ring-line" : "text-ink-muted hover:text-ink",
            )}
          >
            <Icon className={cn("size-4", tab === id ? "text-accent-700" : "text-ink-subtle")} aria-hidden />
            {label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`sites-panel-${tab}`} aria-labelledby={`sites-tab-${tab}`} className="min-w-0">
        {tab === "signal" ? (
          !canView ? (
            <RoleNotice />
          ) : sites.isPending ? (
            <Card>
              <LoadingRows rows={6} />
            </Card>
          ) : sites.isError ? (
            hasErrorCode(sites.error, "wrong_role") ? (
              <RoleNotice />
            ) : hasErrorCode(sites.error, "site_signal_unavailable") ? (
              <UnavailableCard message={errorMessage(sites.error)} />
            ) : (
              <ErrorState error={sites.error} onRetry={() => void sites.refetch()} retrying={sites.isFetching} />
            )
          ) : (
            <SignalTab data={sites.data} />
          )
        ) : (
          <HowWellItWorksTab canView={canView} />
        )}
      </div>
    </>
  );
}

/** Coordinators and investigators see this instead of the rankings (docs/10 §6, 403 `wrong_role`). */
function RoleNotice({ title = "Switch to CRA to view site rankings." }: { title?: string }) {
  const qc = useQueryClient();
  const cra = DEMO_IDENTITIES.cra;
  return (
    <Card>
      <EmptyState
        icon={<UserRound className="size-6" aria-hidden />}
        title={title}
        action={
          <Button
            variant="primary"
            onClick={() => {
              setRole(cra.role);
              toast.message(`Demo role: ${cra.label} · ${cra.user}`);
              void qc.invalidateQueries();
            }}
          >
            Switch to {cra.label}
          </Button>
        }
      >
        Site rankings and the equity analysis are sponsor-side monitoring views for the CRA and sponsor roles. Site staff roles
        do not see them.
      </EmptyState>
    </Card>
  );
}

/** 503 `site_signal_unavailable`: nothing ranks, every site is grey "not computed"; never empty-as-fine. */
function UnavailableCard({ message }: { message: string }) {
  return (
    <Card>
      <CardHeader title="Sites" icon={<Building2 className="size-4" aria-hidden />} />
      <div className="p-5">
        <TierBadge tier="not_computed" labels={null} unavailableText={message} className="whitespace-normal" />
      </div>
    </Card>
  );
}

function SignalTab({ data }: { data: SitesResponse }) {
  const { run, labels, funnel, sites } = data;
  const [revealed, setRevealed] = useState(false);
  const answerKey = useAnswerKey(revealed);

  const notComputed: NotComputedMarker[] = sites
    .filter((s) => s.tier === "not_computed")
    .map((s) => ({ site_id: s.site_id, reason: reasonText(labels, s) }));
  const studyReason = run.study_not_computed_reason
    ? (labels.reasons[run.study_not_computed_reason] ?? run.study_not_computed_reason)
    : null;

  return (
    <div className="space-y-6">
      {studyReason ? (
        <div
          className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-5 py-3.5 text-sm leading-6 text-slate-700 shadow-card"
          role="status"
        >
          <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-white text-slate-600 ring-1 ring-slate-200">
            <Building2 className="size-4" aria-hidden />
          </span>
          <p>
            <span className="font-semibold">{labels.not_computed}:</span> {studyReason}
          </p>
        </div>
      ) : null}

      <TierSummary sites={sites} labels={labels} />

      <Card className="overflow-hidden">
        <CardHeader
          title="Funnel"
          icon={<LineChart className="size-4" aria-hidden />}
          subtitle="Each computed site's observed over expected matched episodes (O/E) against its expected count (E). Sites below a lower limit get that tier."
          actions={<DataOriginBadge origin={run.data_origin} />}
          className="flex-wrap"
        />
        <div className="p-5">
          <FunnelPlot
            points={funnel.points}
            limits={funnel.limits}
            notComputed={notComputed}
            labels={labels}
            legendNote={
              <span className="tabular font-medium text-ink">
                {run.n_computed_sites} of {sites.length} sites computed
              </span>
            }
          />
        </div>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader
          title="Sites, ranked"
          icon={<Building2 className="size-4" aria-hidden />}
          subtitle="Computed sites by adjusted score, then sites not computed. Open a site for its episodes and quotes."
          className="flex-wrap"
          actions={
            <Button
              size="sm"
              variant={revealed ? "primary" : "secondary"}
              aria-pressed={revealed}
              icon={<KeyRound className="size-4" aria-hidden />}
              onClick={() => setRevealed((v) => !v)}
            >
              {revealed ? "Hide answer key" : "Reveal answer key"}
            </Button>
          }
        />
        {revealed ? <AnswerKeyNote q={answerKey} /> : null}
        <RankedTable sites={sites} labels={labels} answerKey={revealed ? answerKey.data : undefined} />
        <footer className="space-y-1 border-t border-line bg-gray-50/70 px-5 py-3.5 text-sm leading-6 text-ink-muted">
          <p className="font-medium text-ink">{labels.footer}</p>
          <p>{footerText(labels, run.expected_false_look_flags_per_study)}</p>
        </footer>
      </Card>
    </div>
  );
}

function AnswerKeyNote({ q }: { q: ReturnType<typeof useAnswerKey> }) {
  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-gray-50/70 px-5 py-3 text-sm leading-6 text-ink-muted"
      role="status"
    >
      {q.isPending ? (
        <span>Loading the answer key…</span>
      ) : q.isError ? (
        <span className="text-ink">{errorMessage(q.error)}</span>
      ) : (
        <>
          <DataOriginBadge origin={q.data.data_origin} />
          <span>
            Answer key of the committed simulated study: what was planted at each site. It is committed with the outputs for
            transparency; compare it with each indicator&apos;s tier.
          </span>
        </>
      )}
    </div>
  );
}

function RankedTable({
  sites,
  labels,
  answerKey,
}: {
  sites: SiteRow[];
  labels: SiteSignalLabels;
  answerKey: AnswerKeyResponse | undefined;
}) {
  const keyBySite = new Map((answerKey?.answer_key ?? []).map((a) => [a.site_id, a.label]));
  // `relative`: the badges' sr-only text is absolutely positioned; keep it inside the scroll box so it cannot widen the page.
  return (
    <Table className="relative">
      <caption className="sr-only">Sites ranked by the capture-discordance indicator</caption>
      <thead>
        <tr>
          <Th>Site</Th>
          {answerKey ? <Th>Answer key</Th> : null}
          <Th className="text-right">Patients</Th>
          <Th className="text-right">Evaluable</Th>
          <Th className="text-right">Pending</Th>
          <Th className="text-right">Paged</Th>
          <Th className="text-right">Coverage</Th>
          <Th className="text-right">O/E</Th>
          <Th>Tier</Th>
          <Th>Rate KRI</Th>
          <Th>simaerep classic (legacy)</Th>
          <Th className="text-right">Open queries</Th>
          <Th>Origin</Th>
        </tr>
      </thead>
      <tbody>
        {sites.map((s) => {
          const grey = s.tier === "not_computed";
          const key = keyBySite.get(s.site_id);
          return (
            <tr
              key={s.site_id}
              className={cn("transition-colors", grey ? "bg-slate-50/80 text-slate-500" : "hover:bg-gray-50/80")}
              data-site={s.site_id}
              data-tier={s.tier}
            >
              <Td className="min-w-56">
                <Link
                  href={`/sites/${encodeURIComponent(s.site_id)}`}
                  className="font-mono font-semibold text-accent-800 hover:underline"
                >
                  {s.site_id}
                </Link>
                <div className={cn("text-sm", grey ? "text-slate-500" : "text-ink-subtle")}>{s.name}</div>
              </Td>
              {answerKey ? (
                <Td className="min-w-40 font-medium text-ink">{key ? (labels.answer_key[key] ?? "—") : "—"}</Td>
              ) : null}
              <Td className="tabular text-right">{s.n_patients}</Td>
              <Td className="tabular text-right">{s.n_episodes_evaluable}</Td>
              <Td className="tabular text-right">{s.n_pending}</Td>
              <Td className="tabular text-right">{s.n_paged}</Td>
              <Td className="tabular text-right">{pct(s.call_completion)}</Td>
              <Td className="tabular text-right font-medium">{num(s.oe_ratio, 2)}</Td>
              <Td className={cn(grey && "min-w-72")}>
                <TierBadge tier={s.tier} reason={s.not_computed_reason} labels={labels} />
              </Td>
              <Td>
                <ComparatorTier tier={s.comparators.rate_kri.tier} labels={labels} />
              </Td>
              <Td>
                <ComparatorTier tier={s.comparators.simaerep_classic.tier} labels={labels} />
              </Td>
              <Td className="tabular text-right">{s.open_queries}</Td>
              <Td>
                <DataOriginBadge origin={s.data_origin} />
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

function ComparatorTier({ tier, labels }: { tier: SignalTier; labels: SiteSignalLabels }) {
  return <TierBadge tier={tier} labels={labels} reasonDisplay="tooltip" />;
}

/**
 * "How well it works" (any role; WS3 F16): every block is rendered from `GET /api/site-signal/validation`
 * (validation/site_signal/summary.json) and, for CRA and sponsor, the equity block from `GET /api/site-signal/equity`.
 * No number is typed here or in `PowerTable`; all of it is SIMULATED.
 */
function HowWellItWorksTab({ canView }: { canView: boolean }) {
  const q = useSiteValidation();
  const docsHref = `${REPO_URL}/blob/main/docs/11-site-signal-sap.md`;
  const wrongHref = `${REPO_URL}/blob/main/WHAT_IT_GETS_WRONG.md`;

  if (q.isPending) {
    return (
      <Card>
        <LoadingRows rows={4} />
      </Card>
    );
  }
  if (q.isError) {
    if (hasErrorCode(q.error, "no_validation_run")) {
      return (
        <Card>
          <EmptyState icon={<BookOpenCheck className="size-6" aria-hidden />} title="Validation not run yet.">
            The operating characteristics come from the pre-registered plan,{" "}
            <RepoLink href={docsHref} path="docs/11-site-signal-sap.md" />.
          </EmptyState>
        </Card>
      );
    }
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />;
  }

  const v = q.data;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="How well it works"
          icon={<BookOpenCheck className="size-4" aria-hidden />}
          subtitle="Operating characteristics of the three indicators in simulated studies at the sap-v1 design."
          actions={<DataOriginBadge origin={v.data_origin} />}
          className="flex-wrap"
        />
        <div className="mx-5 mt-4 flex gap-3 rounded-xl border border-dashed border-slate-400 bg-slate-50/70 p-4 text-sm leading-6 text-ink-muted">
          <FlaskConical className="mt-1 size-4 shrink-0 text-slate-600" aria-hidden />
          <div className="space-y-2">
          <p>
            Every number on this tab is <span className="font-semibold text-ink">SIMULATED</span>: both data streams and the
            planted sites come from the simulation in the pre-registered plan. Capture discordance is a reason to look, not a
            finding. Rates carry their Monte Carlo standard error (MC SE); numbers are rounded for display only.
          </p>
          <p>
            The only non-circular validation is a retrospective analysis of trials with paired patient-reported and
            clinician-reported (CTCAE) data and site IDs.
          </p>
          </div>
        </div>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 px-5 py-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <Meta label="sap-v1 tag commit">
            <code className="font-mono">{v.sap_tag_commit.slice(0, 7)}</code>
          </Meta>
          <Meta label="Code commit">
            <code className="font-mono">{v.code_commit.slice(0, 7)}</code>
          </Meta>
          <Meta label="Generated">{formatDate(v.generated_at)}</Meta>
          <Meta label="What it gets wrong">
            <RepoLink href={wrongHref} path="WHAT_IT_GETS_WRONG.md" />
          </Meta>
        </dl>
      </Card>

      <PowerTable v={v} />
      <NullRatesTable v={v} />
      <FailureCaseTable v={v} />
      <SensitivityTable v={v} />
      <CommittedConfusionTable v={v} />
      {canView ? <EquitySection validation={v} /> : <RoleNotice title="Switch to CRA to view the equity analysis." />}
    </div>
  );
}

/** Equity block (cra, sponsor): the cut Equity tab's odds ratios, from `GET /api/site-signal/equity`. */
function EquitySection({ validation }: { validation: SiteSignalValidation }) {
  const q = useSiteEquity();
  if (q.isPending) {
    return (
      <Card>
        <LoadingRows rows={3} />
      </Card>
    );
  }
  if (q.isError) {
    if (hasErrorCode(q.error, "wrong_role")) return <RoleNotice title="Switch to CRA to view the equity analysis." />;
    if (hasErrorCode(q.error, "no_equity_run")) {
      return (
        <Card>
          <EmptyState icon={<Scale className="size-6" aria-hidden />} title="Equity analysis not run yet.">
            {errorMessage(q.error)}
          </EmptyState>
        </Card>
      );
    }
    return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />;
  }
  return <EquityBlock equity={q.data} validation={validation} />;
}

function RepoLink({ href, path }: { href: string; path: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md font-medium break-all text-accent-700 hover:underline"
    >
      {path} <ExternalLink className="size-3.5 shrink-0" aria-hidden />
    </a>
  );
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-ink-subtle">{label}</dt>
      <dd className="mt-0.5 flex flex-wrap items-center gap-1.5 font-medium text-ink">{children}</dd>
    </div>
  );
}

/**
 * Sites per tier in the committed run, each under the tier's own slate badge and API label. The counts are taken
 * from the `sites` rows of `GET /api/sites`; nothing here is typed.
 */
function TierSummary({ sites, labels }: { sites: SiteRow[]; labels: SiteSignalLabels }) {
  const tiers: SignalTier[] = ["watch", "look", "none", "not_computed"];
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-4" aria-label="Sites per tier">
      {tiers.map((t) => {
        const n = sites.filter((x) => x.tier === t).length;
        return (
          <li
            key={t}
            className="flex min-w-0 items-center justify-between gap-3 rounded-2xl border border-line bg-white px-4 py-3.5 shadow-card"
            data-tier-count={t}
          >
            <TierBadge tier={t} labels={labels} />
            <span className="shrink-0 text-2xl leading-none font-semibold text-ink tabular">
              {n}
              <span className="sr-only"> {n === 1 ? "site" : "sites"}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
