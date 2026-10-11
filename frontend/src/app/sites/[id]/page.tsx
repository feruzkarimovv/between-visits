"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Building2, FilePenLine, Layers, ListChecks, MailCheck, UserRound } from "lucide-react";
import type { PagedStratum, SiteDetail, SiteQuery, SiteSignalLabels, SiteStrata } from "@/lib/types";
import { useSiteDetail, useSites } from "@/lib/queries";
import { DEMO_IDENTITIES, setRole, useIdentity } from "@/lib/role";
import { errorMessage, hasErrorCode } from "@/lib/api";
import { Button, ButtonLink, Card, CardHeader, EmptyState, ErrorState, Field, LoadingRows, PageHeader, Table, Td, Th } from "@/components/ui/primitives";
import { DataOriginBadge } from "@/components/DataOriginBadge";
import { TierBadge } from "@/components/TierBadge";
import { EpisodeTable } from "@/components/EpisodeTable";
import { SiteQueryComposer, SiteQueryList } from "@/components/SiteQueryComposer";

/**
 * `/sites/[id]` Site drill-down (WS3 F13; docs/06 § Site Signal pages, docs/03 §5.3–5.4, docs/10 §6).
 * Every number, tier and reason comes from `GET /api/sites/{site_id}` (labels from `GET /api/sites`); this file
 * holds no result literals. Query actions are CRA only; the sponsor reads.
 */

function pct(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : `${Math.round(v * 100)}%`;
}

function num(v: number | null | undefined, digits: number): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(digits);
}

const STRATUM_LABELS: Record<string, string> = {
  en: "English",
  es: "Spanish",
  standard: "Standard pace",
  extra_time: "Extra time",
};

export default function SiteDetailPage() {
  const params = useParams<{ id: string }>();
  const siteId = params?.id ?? "";
  const identity = useIdentity();
  const canView = identity.role === "cra" || identity.role === "sponsor";
  const q = useSiteDetail(siteId, canView);
  const sites = useSites(canView);

  return (
    <>
      <div className="mb-3">
        <Link href="/sites" className="inline-flex items-center gap-1 text-sm font-medium text-accent-700 hover:underline">
          <ArrowLeft className="size-4" aria-hidden />
          All sites
        </Link>
      </div>
      {!canView ? (
        <>
          <PageHeader title={`Site ${siteId}`} />
          <RoleNotice />
        </>
      ) : q.isPending ? (
        <Card>
          <LoadingRows rows={6} />
        </Card>
      ) : q.isError ? (
        <>
          <PageHeader title={`Site ${siteId}`} />
          {hasErrorCode(q.error, "wrong_role") ? (
            <RoleNotice />
          ) : hasErrorCode(q.error, "site_signal_unavailable") ? (
            <Card>
              <div className="p-4">
                <TierBadge tier="not_computed" labels={null} unavailableText={errorMessage(q.error)} className="whitespace-normal" />
              </div>
            </Card>
          ) : hasErrorCode(q.error, "site_not_found", "signal_run_not_found") ? (
            <Card>
              <EmptyState
                icon={<Building2 className="size-6" aria-hidden />}
                title="Site not found"
                action={<ButtonLink href="/sites">All sites</ButtonLink>}
              >
                {errorMessage(q.error)}
              </EmptyState>
            </Card>
          ) : (
            <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
          )}
        </>
      ) : (
        <SiteView data={q.data} labels={sites.data?.labels ?? null} labelsError={sites.isError ? errorMessage(sites.error) : null} isCra={identity.role === "cra"} />
      )}
    </>
  );
}

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
        Site drill-downs are a sponsor-side monitoring view for the CRA and sponsor roles. Site staff roles do not see them.
      </EmptyState>
    </Card>
  );
}

function SiteView({
  data,
  labels,
  labelsError,
  isCra,
}: {
  data: SiteDetail;
  labels: SiteSignalLabels | null;
  labelsError: string | null;
  isCra: boolean;
}) {
  const { site, signal, episodes, strata, paged_stratum, queries } = data;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [draft, setDraft] = useState<SiteQuery | null>(null);
  // Keep the open draft in step with the polled list (another tab may have approved it).
  const serverDraft = draft ? queries.find((x) => x.id === draft.id) : undefined;
  const activeDraft = serverDraft ? (serverDraft.status === "draft" ? serverDraft : null) : draft;
  const nMeasured = episodes.filter((e) => e.data_origin === "MEASURED").length;

  return (
    <div className="space-y-5">
      <PageHeader
        title={`Site ${site.site_id}`}
        subtitle={
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <DataOriginBadge origin={site.data_origin} />
            <span className="font-medium text-ink">{site.name}</span>
            <span>{site.region}</span>
          </div>
        }
      />

      <Card>
        <CardHeader
          title="Site"
          icon={<Building2 className="size-4 text-ink-subtle" aria-hidden />}
          actions={<DataOriginBadge origin={signal.data_origin} />}
          className="flex-wrap"
        />
        <div className="space-y-4 p-4">
          <div>
            <p className="mb-1 text-sm text-ink-subtle">Capture discordance tier</p>
            {labels ? (
              <TierBadge tier={signal.tier} reason={signal.not_computed_reason} labels={labels} />
            ) : (
              <TierBadge tier="not_computed" labels={null} unavailableText={labelsError ?? "Loading tier labels…"} />
            )}
            {labels ? <p className="mt-1.5 text-sm font-medium text-ink">{labels.footer}</p> : null}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <Field label="Patients">{site.n_patients}</Field>
            <Field label="Spanish share">{pct(site.spanish_share)}</Field>
            <Field label="Extra-time share">{pct(site.extra_time_share)}</Field>
            <Field label="Call completion">{pct(site.call_completion)}</Field>
            <Field label="Evaluable episodes">{signal.n_episodes_evaluable}</Field>
            <Field label="Pending">{signal.n_pending}</Field>
            <Field label="Paged">{signal.n_paged}</Field>
            <Field label="Observed / expected (O/E)">
              {num(signal.O, 0)} / {num(signal.E, 1)} ({num(signal.oe_ratio, 2)})
            </Field>
            <Field label="Rate KRI" className="col-span-2 sm:col-span-1">
              {labels ? <TierBadge tier={signal.comparators.rate_kri.tier} labels={labels} reasonDisplay="tooltip" /> : "—"}
            </Field>
            <Field label="simaerep classic (legacy)" className="col-span-2 sm:col-span-1">
              {labels ? <TierBadge tier={signal.comparators.simaerep_classic.tier} labels={labels} reasonDisplay="tooltip" /> : "—"}
            </Field>
          </dl>
          {site.is_live_site ? (
            <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              Live bridge site: episodes from calls processed by the app ({nMeasured} now) are listed first with a MEASURED
              badge. They are never pooled into this site&apos;s simulated O/E.
            </p>
          ) : null}
        </div>
      </Card>

      {strata || paged_stratum ? <StrataCard strata={strata} paged={paged_stratum} /> : null}

      <Card>
        <CardHeader
          title="Site queries"
          icon={<MailCheck className="size-4 text-ink-subtle" aria-hidden />}
          subtitle="Templated data-completeness requests. A CRA approves every query before it reaches the site."
          className="flex-wrap"
        />
        {isCra ? (
          <div className="border-b border-line">
            <h3 className="flex items-center gap-2 px-4 pt-3 text-sm font-semibold text-ink">
              <FilePenLine className="size-4 text-ink-subtle" aria-hidden />
              {activeDraft ? "Draft" : "New query"}
            </h3>
            <SiteQueryComposer
              siteId={site.site_id}
              episodes={episodes}
              selected={selected}
              onSelectedChange={setSelected}
              draft={activeDraft}
              onDraftChange={setDraft}
            />
          </div>
        ) : (
          <p className="border-b border-line px-4 py-3 text-sm text-ink-muted">Only the CRA drafts, edits and approves site queries.</p>
        )}
        <SiteQueryList queries={queries} canEdit={isCra} onEdit={(x) => setDraft(x)} />
      </Card>

      <Card>
        <CardHeader
          title="Episodes"
          icon={<ListChecks className="size-4 text-ink-subtle" aria-hidden />}
          subtitle="Each episode with its verbatim quote in the original language. Pending episodes are greyed and never counted as missed; paged episodes are a separate stratum."
          className="flex-wrap"
        />
        <EpisodeTable episodes={episodes} selectable={isCra && !activeDraft} selected={selected} onSelectedChange={setSelected} />
      </Card>
    </div>
  );
}

function StrataCard({ strata, paged }: { strata: SiteStrata | null; paged: PagedStratum | null }) {
  const groups: { title: string; rows: [string, { evaluable: number; matched: number }][] }[] = strata
    ? [
        { title: "Language", rows: Object.entries(strata.language) },
        { title: "Pace", rows: Object.entries(strata.pace) },
      ]
    : [];
  return (
    <Card>
      <CardHeader
        title="Strata"
        icon={<Layers className="size-4 text-ink-subtle" aria-hidden />}
        subtitle="Episodes in the O/E set (evaluable, not paged) by language and pace, and the paged stratum, which is never in O or E."
        actions={<DataOriginBadge origin="SIMULATED" />}
        className="flex-wrap"
      />
      <div className="grid gap-4 p-4 md:grid-cols-3">
        {groups.map((g) => (
          <Table key={g.title} className="rounded-md border border-line">
            <caption className="sr-only">{g.title} strata</caption>
            <thead>
              <tr>
                <Th>{g.title}</Th>
                <Th className="text-right">Evaluable</Th>
                <Th className="text-right">Matched</Th>
              </tr>
            </thead>
            <tbody>
              {g.rows.map(([key, c]) => (
                <tr key={key}>
                  <Td>{STRATUM_LABELS[key] ?? key}</Td>
                  <Td className="tabular text-right">{c.evaluable}</Td>
                  <Td className="tabular text-right">{c.matched}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ))}
        {paged ? (
          <Table className="rounded-md border border-line">
            <caption className="sr-only">Paged stratum</caption>
            <thead>
              <tr>
                <Th>Stratum</Th>
                <Th className="text-right">Episodes</Th>
                <Th className="text-right">Matched</Th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <Td>Paged: separate stratum</Td>
                <Td className="tabular text-right">{paged.n}</Td>
                <Td className="tabular text-right">{paged.matched}</Td>
              </tr>
            </tbody>
          </Table>
        ) : null}
      </div>
    </Card>
  );
}
