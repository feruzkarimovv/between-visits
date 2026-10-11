"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BookOpenCheck, Building2, ExternalLink, KeyRound, LineChart, UserRound } from "lucide-react";
import type { AnswerKeyResponse, SignalTier, SiteRow, SitesResponse, SiteSignalLabels } from "@/lib/types";
import { useAnswerKey, useHealth, useSiteValidation, useSites } from "@/lib/queries";
import { DEMO_IDENTITIES, setRole, useIdentity } from "@/lib/role";
import { errorMessage, hasErrorCode } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Button, Card, CardHeader, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th, cn } from "@/components/ui/primitives";
import { DataOriginBadge } from "@/components/DataOriginBadge";
import { TierBadge } from "@/components/TierBadge";
import { FunnelPlot, type NotComputedMarker } from "@/components/FunnelPlot";

/**
 * `/sites` Site Signal overview (WS3 F12; docs/06 § Site Signal pages, docs/10 §6).
 * Every number, tier, reason, footer and answer-key text comes from `GET /api/sites`,
 * `GET /api/site-signal/answer-key` or `GET /api/site-signal/validation`; this file holds no result literals.
 */

const REPO_URL = (process.env.NEXT_PUBLIC_REPO_URL || "").replace(/\/$/, "");

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

function num(v: number | null, digits: number): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(digits);
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
        title="Site Signal"
        subtitle={
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <DataOriginBadge origin={origin} />
            <span>
              <span className="font-medium text-ink">sap-v1</span>{" "}
              {sapCommit ? <code className="font-mono text-sm">{sapCommit.slice(0, 7)}</code> : "tag unavailable"}
              {generatedAt ? <> · run {formatDate(generatedAt)}</> : null}
            </span>
            <span>Thresholds fixed from the pre-registered null.</span>
          </div>
        }
      />

      <div role="tablist" aria-label="Site Signal views" className="mb-4 flex max-w-full overflow-x-auto border-b border-line">
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
              "-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap",
              tab === id ? "border-accent-700 text-accent-800" : "border-transparent text-ink-muted hover:text-ink",
            )}
          >
            <Icon className="size-4" aria-hidden />
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
          <HowWellItWorksTab />
        )}
      </div>
    </>
  );
}

/** Coordinators and investigators see this instead of the rankings (docs/10 §6, 403 `wrong_role`). */
function RoleNotice() {
  const qc = useQueryClient();
  const cra = DEMO_IDENTITIES.cra;
  return (
    <Card>
      <EmptyState
        icon={<UserRound className="size-6" aria-hidden />}
        title="Switch to CRA to view site rankings."
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
        Site rankings are a sponsor-side monitoring view for the CRA and sponsor roles. Site staff roles do not see them.
      </EmptyState>
    </Card>
  );
}

/** 503 `site_signal_unavailable`: nothing ranks, every site is grey "not computed"; never empty-as-fine. */
function UnavailableCard({ message }: { message: string }) {
  return (
    <Card>
      <CardHeader title="Sites" icon={<Building2 className="size-4 text-ink-subtle" aria-hidden />} />
      <div className="p-4">
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
    <div className="space-y-5">
      {studyReason ? (
        <div className="rounded-lg border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700" role="status">
          <span className="font-medium">{labels.not_computed}:</span> {studyReason}
        </div>
      ) : null}

      <Card>
        <CardHeader
          title="Funnel"
          icon={<LineChart className="size-4 text-ink-subtle" aria-hidden />}
          subtitle="Each computed site's observed over expected matched episodes (O/E) against its expected count (E). Sites below a lower limit get that tier."
          actions={<DataOriginBadge origin={run.data_origin} />}
          className="flex-wrap"
        />
        <div className="p-4">
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

      <Card>
        <CardHeader
          title="Sites, ranked"
          icon={<Building2 className="size-4 text-ink-subtle" aria-hidden />}
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
        <footer className="space-y-1 border-t border-line px-4 py-3 text-sm text-ink-muted">
          <p className="font-medium text-ink">{labels.footer}</p>
          <p>{footerText(labels, run.expected_false_look_flags_per_study)}</p>
        </footer>
      </Card>
    </div>
  );
}

function AnswerKeyNote({ q }: { q: ReturnType<typeof useAnswerKey> }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-slate-50 px-4 py-2.5 text-sm text-ink-muted" role="status">
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
            <tr key={s.site_id} className={cn(grey && "bg-slate-50 text-slate-500")} data-site={s.site_id} data-tier={s.tier}>
              <Td className="min-w-48">
                <Link href={`/sites/${encodeURIComponent(s.site_id)}`} className="font-medium text-accent-800 hover:underline">
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
              <Td className="tabular text-right">{num(s.oe_ratio, 2)}</Td>
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

/** "How well it works": validation provenance from `GET /api/site-signal/validation` (any role). */
function HowWellItWorksTab() {
  const q = useSiteValidation();
  const docsHref = REPO_URL ? `${REPO_URL}/blob/main/docs/11-site-signal-sap.md` : null;
  const wrongHref = REPO_URL ? `${REPO_URL}/blob/main/WHAT_IT_GETS_WRONG.md` : null;

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
    <Card>
      <CardHeader
        title="How well it works"
        icon={<BookOpenCheck className="size-4 text-ink-subtle" aria-hidden />}
        subtitle="Operating characteristics from simulated studies at the sap-v1 design."
        actions={<DataOriginBadge origin={v.data_origin} />}
        className="flex-wrap"
      />
      <dl className="grid grid-cols-1 gap-3 p-4 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-ink-subtle">sap-v1 tag commit</dt>
          <dd className="font-mono text-ink">{v.sap_tag_commit.slice(0, 7)}</dd>
        </div>
        <div>
          <dt className="text-ink-subtle">Generated</dt>
          <dd className="text-ink">{formatDate(v.generated_at)}</dd>
        </div>
        <div>
          <dt className="text-ink-subtle">Limits</dt>
          <dd className="text-ink">
            <RepoLink href={wrongHref} path="WHAT_IT_GETS_WRONG.md" />
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function RepoLink({ href, path }: { href: string | null; path: string }) {
  return href ? (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-accent-700 hover:underline">
      {path} <ExternalLink className="size-3.5" aria-hidden />
    </a>
  ) : (
    <code className="font-mono text-sm">{path}</code>
  );
}
