"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Mailbox, Reply, ScrollText, UserRound } from "lucide-react";
import type { Role, SiteQuery, SiteQueryDetail, SiteQueryStatus } from "@/lib/types";
import { useApiMutation, useSiteQueries, useSiteQuery, useSiteQueryResponseCodes } from "@/lib/queries";
import { DEMO_IDENTITIES, setRole, useIdentity } from "@/lib/role";
import { errorMessage, hasErrorCode } from "@/lib/api";
import { formatDay } from "@/lib/format";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingRows,
  PageHeader,
  Skeleton,
  Table,
  Td,
  Th,
  cn,
  inputClass,
} from "@/components/ui/primitives";
import { DataOriginBadge } from "@/components/DataOriginBadge";
import { RelativeTime } from "@/components/RelativeTime";
import { CloseQueryControl, InlineError, QueryStatusChip } from "@/components/SiteQueryComposer";

/**
 * `/site-inbox` Mock site inbox (WS3 F14; docs/06 § `/site-inbox`, docs/03 §5.4, docs/10 §6).
 * Stands in for the coordinator of whichever site was queried, so it lists queries for every site (optional site
 * filter). Only sent, answered and closed queries are requested and shown: drafts never appear, for any role.
 * The coordinator answers a sent query with a coded response (codes and labels from the API, which reads
 * data/site_queries.json) plus an optional note; the CRA closes answered queries; the sponsor reads. Subject IDs
 * only, and no patient quote is rendered here for any role (the API also withholds them from the coordinator).
 */

/** The statuses the inbox shows. A draft is sponsor-side until a CRA approves it. */
const INBOX_STATUSES: SiteQueryStatus[] = ["sent", "answered", "closed"];

/** 4xx codes the respond form shows inline instead of as a toast. */
const RESPOND_ERRORS = ["not_sent", "invalid_response_code", "site_query_not_found", "validation_error"];

export default function SiteInboxPage() {
  const identity = useIdentity();
  const [siteFilter, setSiteFilter] = useState("");
  const all = useSiteQueries({ statuses: INBOX_STATUSES });
  const filtered = useSiteQueries({ siteId: siteFilter || undefined, statuses: INBOX_STATUSES });
  const q = siteFilter ? filtered : all;

  const sites = [...new Set((all.data ?? []).map((x) => x.site_id))].sort();
  if (siteFilter && !sites.includes(siteFilter)) sites.push(siteFilter);
  // Defensive: the request already asks for these statuses only; a draft must never render here.
  const queries = (q.data ?? []).filter((x) => INBOX_STATUSES.includes(x.status));

  return (
    <>
      <PageHeader
        title="Site inbox"
        subtitle="Data-completeness queries a CRA approved and sent to a site. Drafts never appear here."
      />
      <MockBanner role={identity.role} user={identity.user} />
      {q.isPending ? (
        <Card>
          <LoadingRows rows={3} />
        </Card>
      ) : q.isError ? (
        hasErrorCode(q.error, "wrong_role") ? (
          <RoleNotice />
        ) : (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
        )
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <label htmlFor="site-filter" className="mb-1 block text-sm font-medium text-ink-muted">
                Site
              </label>
              <select
                id="site-filter"
                className={cn(inputClass, "w-48")}
                value={siteFilter}
                onChange={(e) => setSiteFilter(e.target.value)}
              >
                <option value="">All sites</option>
                {sites.map((s) => (
                  <option key={s} value={s}>
                    Site {s}
                  </option>
                ))}
              </select>
            </div>
            <StatusCounts queries={queries} />
          </div>
          {queries.length === 0 ? (
            <Card>
              <EmptyState icon={<Mailbox className="size-6" aria-hidden />} title="No queries in the inbox.">
                {siteFilter
                  ? `No approved queries for site ${siteFilter}.`
                  : "A query appears here once a CRA approves it on a site page (Sites, then a site)."}
              </EmptyState>
            </Card>
          ) : (
            <ul className="space-y-4" aria-label="Site queries, newest first">
              {queries.map((x) => (
                <li key={x.id}>
                  <QueryCard query={x} role={identity.role} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}

function MockBanner({ role, user }: { role: Role; user: string }) {
  const roleLine =
    role === "coordinator"
      ? `You are answering as the site coordinator (${user}). Review the source documents, then choose a coded response and add a note if useful.`
      : role === "cra"
        ? `Read-only for the CRA (${user}). You can close answered queries here or on the site page.`
        : role === "sponsor"
          ? "Read-only for the sponsor."
          : "Open as the coordinator to answer, or as the CRA or sponsor to read.";
  return (
    <div
      role="note"
      className="mb-4 flex items-start gap-3 rounded-lg border border-dashed border-slate-400 bg-slate-50 px-4 py-3"
    >
      <Mailbox className="mt-0.5 size-5 shrink-0 text-slate-600" aria-hidden />
      <div className="min-w-0 space-y-1">
        <p className="font-semibold text-ink">Mock site inbox (synthetic data)</p>
        <p className="text-sm text-ink-muted">
          Stands in for the coordinator of whichever site was queried, so it lists approved queries for every site. It is
          not an EDC or e-mail integration. Subject IDs only; patient quotes stay on the sponsor side.
        </p>
        <p className="text-sm text-ink-muted">{roleLine}</p>
      </div>
    </div>
  );
}

function StatusCounts({ queries }: { queries: SiteQuery[] }) {
  const n = (s: SiteQueryStatus) => queries.filter((x) => x.status === s).length;
  return (
    <p className="text-sm text-ink-muted tabular" aria-live="polite">
      {n("sent")} sent · {n("answered")} answered · {n("closed")} closed
    </p>
  );
}

function RoleNotice() {
  const qc = useQueryClient();
  const switchTo = (role: Role) => {
    const id = DEMO_IDENTITIES[role];
    setRole(id.role);
    toast.message(`Demo role: ${id.label} · ${id.user}`);
    void qc.invalidateQueries();
  };
  return (
    <Card>
      <EmptyState
        icon={<UserRound className="size-6" aria-hidden />}
        title="Switch to Coordinator or CRA to open the site inbox."
        action={
          <div className="flex flex-wrap justify-center gap-2">
            <Button variant="primary" onClick={() => switchTo("coordinator")}>
              Switch to {DEMO_IDENTITIES.coordinator.label}
            </Button>
            <Button onClick={() => switchTo("cra")}>Switch to {DEMO_IDENTITIES.cra.label}</Button>
          </div>
        }
      >
        The site coordinator answers queries here; the CRA and the sponsor read them.
      </EmptyState>
    </Card>
  );
}

function QueryCard({ query: q, role }: { query: SiteQuery; role: Role }) {
  const detail = useSiteQuery(q.id);
  return (
    <Card as="article" className="overflow-hidden">
      <div className="border-b border-line px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-ink">Site {q.site_id}</span>
          <QueryStatusChip status={q.status} />
          <DataOriginBadge origin={q.data_origin} />
          <code className="font-mono text-sm text-ink-subtle">{q.id}</code>
        </div>
        <h2 className="mt-1 text-base font-semibold text-ink">{q.title_en}</h2>
      </div>
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="min-w-0 space-y-4">
          <div className="rounded-md border border-line bg-gray-50 px-3 py-2.5 text-sm leading-6 whitespace-pre-line text-ink">
            {q.body_en}
          </div>
          <CitedEpisodes query={q} detail={detail.data} pending={detail.isPending} error={detail.isError ? detail.error : null} />
          <SiteResponse query={q} />
          {role === "coordinator" && q.status === "sent" ? <RespondForm query={q} /> : null}
          {role === "cra" && q.status === "answered" ? <CloseQueryControl query={q} /> : null}
        </div>
        <div className="space-y-3">
          <StatusTimeline query={q} />
          {role === "cra" || role === "sponsor" ? (
            <Link
              href={`/audit?entity_id=${encodeURIComponent(q.id)}`}
              className="inline-flex items-center gap-1 text-sm font-medium text-accent-700 hover:underline"
            >
              <ScrollText className="size-4" aria-hidden />
              Audit rows
            </Link>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

/** Cited subject IDs, symptoms and episode dates. Never a patient quote, for any role. */
function CitedEpisodes({
  query: q,
  detail,
  pending,
  error,
}: {
  query: SiteQuery;
  detail: SiteQueryDetail | undefined;
  pending: boolean;
  error: unknown;
}) {
  if (pending) return <Skeleton className="h-20 w-full" />;
  if (error || !detail) {
    return (
      <div className="text-sm">
        <p className="text-ink-muted">
          Cited subjects: <span className="font-mono text-ink">{q.subject_ids.join(", ")}</span>
        </p>
        <p className="text-ink-subtle">Episode dates unavailable: {errorMessage(error)}</p>
      </div>
    );
  }
  const episodes = [...detail.episodes].sort(
    (a, b) => a.episode_date.localeCompare(b.episode_date) || a.episode_id.localeCompare(b.episode_id),
  );
  return (
    <div className="rounded-md border border-line">
      <Table>
        <caption className="px-4 pt-2.5 pb-1 text-left text-sm font-semibold text-ink">
          Cited episodes ({episodes.length})
        </caption>
        <thead>
          <tr>
            <Th>Subject</Th>
            <Th>Symptom</Th>
            <Th>First reported on the call of</Th>
          </tr>
        </thead>
        <tbody>
          {episodes.map((e) => (
            <tr key={e.episode_id}>
              <Td className="font-mono whitespace-nowrap">{e.subject_id}</Td>
              <Td>{e.term}</Td>
              <Td className="tabular whitespace-nowrap">{formatDay(e.episode_date)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

function SiteResponse({ query: q }: { query: SiteQuery }) {
  if (!q.response_label_en && !q.closure_note) return null;
  return (
    <div className="space-y-2">
      {q.response_label_en ? (
        <div className="rounded-md border border-line px-3 py-2.5">
          <p className="text-sm text-ink-subtle">Site response</p>
          <p className="font-medium text-ink">{q.response_label_en}</p>
          {q.response_note ? (
            <p className="mt-0.5 text-sm whitespace-pre-line text-ink-muted">Note: {q.response_note}</p>
          ) : null}
        </div>
      ) : null}
      {q.closure_note ? (
        <div className="rounded-md border border-line px-3 py-2.5">
          <p className="text-sm text-ink-subtle">CRA closure note</p>
          <p className="text-sm whitespace-pre-line text-ink">{q.closure_note}</p>
        </div>
      ) : null}
    </div>
  );
}

function StatusTimeline({ query: q }: { query: SiteQuery }) {
  const steps = [
    { key: "sent", label: "Approved and sent by the CRA", by: q.approved_by, at: q.approved_at, waiting: null },
    { key: "answered", label: "Answered by the site", by: q.responded_by, at: q.responded_at, waiting: "Waiting for the site's response" },
    { key: "closed", label: "Closed by the CRA", by: q.closed_by, at: q.closed_at, waiting: "Waiting for the CRA's review" },
  ];
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-ink">Status timeline</h3>
      <ol className="space-y-3">
        {steps.map((s, i) => {
          const done = Boolean(s.at);
          const prevDone = i === 0 || Boolean(steps[i - 1].at);
          return (
            <li key={s.key} className="flex gap-2.5" data-step={s.key} data-done={done || undefined}>
              <span
                aria-hidden
                className={cn(
                  "mt-1.5 size-2.5 shrink-0 rounded-full border",
                  done ? "border-slate-700 bg-slate-700" : "border-slate-300 bg-white",
                )}
              />
              <div className="min-w-0 text-sm">
                <p className={cn("font-medium", done ? "text-ink" : "text-ink-subtle")}>{s.label}</p>
                {done ? (
                  <p className="text-ink-muted">
                    {s.by ? `${s.by} · ` : ""}
                    <RelativeTime iso={s.at} />
                  </p>
                ) : (
                  <p className="text-ink-subtle">{prevDone && s.waiting ? s.waiting : "Not yet"}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Coordinator only, on a sent query: one coded response (from the API) plus an optional note. */
function RespondForm({ query: q }: { query: SiteQuery }) {
  const codes = useSiteQueryResponseCodes();
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const uid = useId();
  const respond = useApiMutation<void, SiteQuery>({
    request: () => ({
      path: `/api/site-queries/${encodeURIComponent(q.id)}/respond`,
      init: { method: "POST", body: { response_code: code, note: note.trim() || null } },
    }),
    success: `Response sent for ${q.id}`,
    invalidate: [["site-queries"], ["site", q.site_id], ["sites"], ["audit"]],
    inlineErrorCodes: RESPOND_ERRORS,
  });

  return (
    <form
      className="space-y-3 rounded-md border border-slate-300 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (code) respond.mutate();
      }}
    >
      <fieldset>
        <legend className="text-sm font-semibold text-ink">Coded response</legend>
        <p className="text-sm text-ink-muted">Each code is an equally acceptable answer.</p>
        {codes.isPending ? (
          <Skeleton className="mt-2 h-24 w-full" />
        ) : codes.isError ? (
          <p role="alert" className="mt-2 text-sm text-red-800">
            Couldn&apos;t load the response codes: {errorMessage(codes.error)}
          </p>
        ) : (
          <div className="mt-2 space-y-1.5">
            {codes.data.map((c) => (
              <label key={c.code} className="flex cursor-pointer items-start gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name={`${uid}-code`}
                  value={c.code}
                  checked={code === c.code}
                  onChange={() => setCode(c.code)}
                  disabled={respond.isPending}
                  className="mt-1"
                />
                <span>{c.label_en}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>
      <div>
        <label htmlFor={`${uid}-note`} className="mb-1 block text-sm font-medium text-ink-muted">
          Note to the CRA (optional)
        </label>
        <textarea
          id={`${uid}-note`}
          className={cn(inputClass, "min-h-20")}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={respond.isPending}
        />
      </div>
      <InlineError error={respond.isError && hasErrorCode(respond.error, ...RESPOND_ERRORS) ? respond.error : null} />
      <Button
        type="submit"
        variant="primary"
        icon={<Reply className="size-4" aria-hidden />}
        disabled={!code || codes.isError}
        loading={respond.isPending}
      >
        Send response
      </Button>
    </form>
  );
}
