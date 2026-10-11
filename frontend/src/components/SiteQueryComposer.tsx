"use client";

import { useState } from "react";
import Link from "next/link";
import { CircleCheckBig, FilePenLine, MailCheck, Save, ScrollText, Send, X } from "lucide-react";
import type { SiteEpisode, SiteQuery, SiteQueryStatus } from "@/lib/types";
import { useApiMutation } from "@/lib/queries";
import { errorMessage, hasErrorCode, isApiError } from "@/lib/api";
import { formatDay } from "@/lib/format";
import { Button, Table, Td, Th, inputClass, cn } from "./ui/primitives";
import { Chip } from "./chips";
import { DataOriginBadge } from "./DataOriginBadge";
import { RelativeTime } from "./RelativeTime";

/**
 * Site query composer (WS3 F13; docs/03 §5.4, docs/06 § `/sites/[id]`, docs/10 §6.4). CRA only:
 * select `unmatched` episodes → draft (the backend renders the approved template from data/site_queries.json; the
 * draft is the template preview) → edit → "Approve and send". Nothing reaches the site before a CRA approves it, and
 * every step writes an audit row (`site_query.drafted`, `.edited`, `.approved`). 422 codes show inline.
 */

/** Template id in data/site_queries.json. An identifier only: the wording is rendered by the backend. */
const TEMPLATE_ID = "SQ_UNMATCHED_EPISODES";
const COMMITTED_RUN_ID = "sr_committed";

/** 4xx codes the composer shows inline instead of as a toast. */
const DRAFT_ERRORS = ["episode_not_eligible", "episode_not_found", "run_not_queryable", "validation_error", "site_not_found"];
const EDIT_ERRORS = ["contains_identifier", "banned_phrase", "validation_error", "not_draft"];

function invalidateKeys(siteId: string) {
  return [["site", siteId], ["sites"], ["audit"], ["site-queries"]];
}

/** An API error shown inline, with its `error.code`. */
export function InlineError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
      {isApiError(error) ? <code className="mr-1.5 font-mono text-sm">{error.code}</code> : null}
      {errorMessage(error)}
    </p>
  );
}

export function SiteQueryComposer({
  siteId,
  episodes,
  selected,
  onSelectedChange,
  draft,
  onDraftChange,
}: {
  siteId: string;
  episodes: SiteEpisode[];
  selected: ReadonlySet<string>;
  onSelectedChange: (next: Set<string>) => void;
  /** The draft being edited, if any. */
  draft: SiteQuery | null;
  onDraftChange: (next: SiteQuery | null) => void;
}) {
  const chosen = episodes
    .filter((e) => selected.has(e.episode_id))
    .sort((a, b) => a.episode_date.localeCompare(b.episode_date));

  const create = useApiMutation<void, SiteQuery>({
    request: () => ({
      path: "/api/site-queries",
      init: {
        method: "POST",
        body: { site_id: siteId, episode_ids: chosen.map((e) => e.episode_id), template_id: TEMPLATE_ID, signal_run_id: COMMITTED_RUN_ID },
      },
    }),
    success: "Draft created. Review and edit it, then approve.",
    invalidate: invalidateKeys(siteId),
    inlineErrorCodes: DRAFT_ERRORS,
    onSuccess: (q) => {
      onDraftChange(q);
      onSelectedChange(new Set());
    },
  });

  if (draft) {
    return <DraftEditor key={draft.id} siteId={siteId} draft={draft} onDraftChange={onDraftChange} />;
  }

  return (
    <div className="space-y-3 p-4">
      <p className="text-sm text-ink-muted">
        Select <span className="font-medium text-ink">Unmatched</span> episodes in the table below to cite them. Other statuses
        cannot be cited. The draft shows the approved template text for review; nothing reaches the site until you approve it.
      </p>
      {chosen.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Selected episodes">
          {chosen.map((e) => (
            <li key={e.episode_id}>
              <Chip tone="gray" className="font-normal">
                <span className="font-mono">{e.subject_id}</span> · {e.term} · {formatDay(e.episode_date)}
                <button
                  type="button"
                  className="ml-0.5 rounded-full p-0.5 text-ink-subtle hover:bg-gray-200 hover:text-ink"
                  aria-label={`Remove ${e.subject_id} ${e.term}`}
                  onClick={() => {
                    const next = new Set(selected);
                    next.delete(e.episode_id);
                    onSelectedChange(next);
                  }}
                >
                  <X className="size-3" aria-hidden />
                </button>
              </Chip>
            </li>
          ))}
        </ul>
      ) : null}
      <InlineError error={create.isError && hasErrorCode(create.error, ...DRAFT_ERRORS) ? create.error : null} />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          icon={<FilePenLine className="size-4" aria-hidden />}
          disabled={chosen.length === 0}
          loading={create.isPending}
          onClick={() => create.mutate()}
        >
          Draft query{chosen.length > 0 ? ` (${chosen.length})` : ""}
        </Button>
        {chosen.length > 0 ? (
          <Button variant="ghost" size="sm" onClick={() => onSelectedChange(new Set())}>
            Clear selection
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function DraftEditor({
  siteId,
  draft,
  onDraftChange,
}: {
  siteId: string;
  draft: SiteQuery;
  onDraftChange: (next: SiteQuery | null) => void;
}) {
  const [body, setBody] = useState(draft.body_en);
  const [note, setNote] = useState("");
  const dirty = body !== draft.body_en;
  const qid = encodeURIComponent(draft.id);

  const save = useApiMutation<void, SiteQuery>({
    request: () => ({ path: `/api/site-queries/${qid}`, init: { method: "PATCH", body: { body_en: body, note: note.trim() || null } } }),
    success: "Edit saved",
    invalidate: invalidateKeys(siteId),
    inlineErrorCodes: EDIT_ERRORS,
    onSuccess: (q) => {
      setNote("");
      onDraftChange(q);
    },
  });
  const approve = useApiMutation<void, SiteQuery>({
    request: () => ({ path: `/api/site-queries/${qid}/approve`, init: { method: "POST", body: {} } }),
    success: "Approved and sent to the mock site inbox",
    invalidate: invalidateKeys(siteId),
    inlineErrorCodes: ["not_draft"],
    onSuccess: () => onDraftChange(null),
  });

  const busy = save.isPending || approve.isPending;
  const error = save.isError ? save.error : approve.isError ? approve.error : null;

  const approveAndSend = async () => {
    try {
      // An unsaved edit is saved first (site_query.edited), so the approved text is exactly what is on screen.
      if (dirty) await save.mutateAsync();
      await approve.mutateAsync();
    } catch {
      // Shown inline (422/409 codes) or toasted by useApiMutation.
    }
  };

  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <QueryStatusChip status={draft.status} />
        <DataOriginBadge origin={draft.data_origin} />
        <code className="font-mono text-sm text-ink-subtle">{draft.id}</code>
        {draft.edited ? <span className="text-sm text-ink-subtle">edited</span> : null}
      </div>
      <div>
        <p className="text-sm text-ink-subtle">Template preview · {draft.template_id}</p>
        <h3 className="mt-0.5 text-base font-semibold text-ink">{draft.title_en}</h3>
        <p className="mt-1 text-sm text-ink-muted">
          Cites <span className="font-mono text-ink">{draft.subject_ids.join(", ")}</span> ({draft.episode_ids.length}{" "}
          {draft.episode_ids.length === 1 ? "episode" : "episodes"}). Subject IDs only.
        </p>
      </div>
      <div>
        <label htmlFor={`body-${draft.id}`} className="mb-1 block text-sm font-medium text-ink-muted">
          Query text (English)
        </label>
        <textarea
          id={`body-${draft.id}`}
          className={cn(inputClass, "min-h-56 font-sans leading-6")}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          disabled={busy}
        />
      </div>
      <div>
        <label htmlFor={`note-${draft.id}`} className="mb-1 block text-sm font-medium text-ink-muted">
          Edit note (optional, kept in the audit row)
        </label>
        <input
          id={`note-${draft.id}`}
          className={inputClass}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={busy}
          placeholder="Why you changed the text"
        />
      </div>
      <InlineError error={error} />
      <div className="flex flex-wrap items-center gap-2">
        <Button icon={<Save className="size-4" aria-hidden />} disabled={!dirty || busy} loading={save.isPending && !approve.isPending} onClick={() => save.mutate()}>
          Save edit
        </Button>
        <Button
          variant="primary"
          icon={<Send className="size-4" aria-hidden />}
          disabled={busy || body.trim() === ""}
          loading={approve.isPending}
          onClick={() => void approveAndSend()}
        >
          Approve and send
        </Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => onDraftChange(null)}>
          Close editor
        </Button>
        {dirty ? <span className="text-sm text-ink-subtle">Unsaved edit: saved first when you approve.</span> : null}
      </div>
      <p className="text-sm text-ink-subtle">
        A CRA approves every site query. Approval sends it to the mock site inbox and writes an audit row. The draft stays in
        the list below until it is approved.
      </p>
    </div>
  );
}

const QUERY_STATUS: Record<SiteQueryStatus, { label: string; className: string }> = {
  draft: { label: "Draft", className: "border-dashed border-slate-400 bg-white text-slate-700" },
  sent: { label: "Sent", className: "border-slate-700 bg-white text-slate-900" },
  answered: { label: "Answered", className: "border-slate-300 bg-slate-100 text-slate-800" },
  closed: { label: "Closed", className: "border-slate-200 bg-slate-50 font-normal text-slate-600" },
};

/**
 * CRA closes an answered query (`POST /api/site-queries/{id}/close`, audit `site_query.closed`), with an optional
 * closure note. Used on `/sites/[id]` and in the mock site inbox (`/site-inbox`).
 */
export function CloseQueryControl({ query, compact = false }: { query: SiteQuery; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const close = useApiMutation<void, SiteQuery>({
    request: () => ({
      path: `/api/site-queries/${encodeURIComponent(query.id)}/close`,
      init: { method: "POST", body: { note: note.trim() || null } },
    }),
    success: `Query ${query.id} closed`,
    invalidate: invalidateKeys(query.site_id),
    inlineErrorCodes: ["not_answered", "site_query_not_found"],
    onSuccess: () => {
      setOpen(false);
      setNote("");
    },
  });

  if (query.status !== "answered") return null;
  if (!open) {
    return (
      <Button size="sm" icon={<CircleCheckBig className="size-4" aria-hidden />} onClick={() => setOpen(true)}>
        Close query
      </Button>
    );
  }
  const noteId = `close-note-${query.id}`;
  return (
    <div className={cn("w-full space-y-2", compact ? "min-w-56" : "max-w-xl")}>
      <div>
        <label htmlFor={noteId} className="mb-1 block text-sm font-medium text-ink-muted">
          Closure note (optional, kept in the audit row)
        </label>
        <input
          id={noteId}
          className={inputClass}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={close.isPending}
          placeholder="For example: Explained; no entry needed"
        />
      </div>
      <InlineError error={close.isError && hasErrorCode(close.error, "not_answered", "site_query_not_found") ? close.error : null} />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          icon={<CircleCheckBig className="size-4" aria-hidden />}
          loading={close.isPending}
          onClick={() => close.mutate()}
        >
          Confirm close
        </Button>
        <Button size="sm" variant="ghost" disabled={close.isPending} onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function QueryStatusChip({ status }: { status: SiteQueryStatus }) {
  const s = QUERY_STATUS[status] ?? { label: status, className: "" };
  return (
    <Chip tone="gray" className={s.className}>
      {s.label}
    </Chip>
  );
}

/** The site's queries in every status, newest first, each linking to its audit rows. */
export function SiteQueryList({
  queries,
  canEdit,
  onEdit,
}: {
  queries: SiteQuery[];
  canEdit: boolean;
  onEdit: (q: SiteQuery) => void;
}) {
  if (queries.length === 0) {
    return (
      <p className="flex items-center gap-2 px-4 py-6 text-sm text-ink-muted">
        <MailCheck className="size-4 text-ink-subtle" aria-hidden />
        No site queries for this site yet.
      </p>
    );
  }
  return (
    <Table className="relative">
      <caption className="sr-only">Site queries for this site, newest first</caption>
      <thead>
        <tr>
          <Th>Query</Th>
          <Th>Status</Th>
          <Th>Subjects</Th>
          <Th>Drafted</Th>
          <Th>Approved</Th>
          <Th>Site response</Th>
          <Th>
            <span className="sr-only">Actions</span>
          </Th>
        </tr>
      </thead>
      <tbody>
        {queries.map((q) => (
          <tr key={q.id} data-query={q.id} data-status={q.status} className="align-top">
            <Td className="min-w-56 align-top">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm">{q.id}</span>
                <DataOriginBadge origin={q.data_origin} />
              </div>
              <div className="text-sm text-ink-muted">{q.title_en}</div>
              {q.edited ? <div className="text-sm text-ink-subtle">edited by the CRA</div> : null}
            </Td>
            <Td className="align-top">
              <QueryStatusChip status={q.status} />
            </Td>
            <Td className="align-top font-mono text-sm">
              {q.subject_ids.map((sid) => (
                <div key={sid} className="whitespace-nowrap">
                  {sid}
                </div>
              ))}
            </Td>
            <Td className="align-top text-sm whitespace-nowrap">
              <div>{q.created_by}</div>
              <RelativeTime iso={q.created_at} />
            </Td>
            <Td className="align-top text-sm whitespace-nowrap">
              {q.approved_at ? (
                <>
                  <div>{q.approved_by}</div>
                  <RelativeTime iso={q.approved_at} />
                </>
              ) : (
                <span className="text-ink-subtle">Not yet</span>
              )}
            </Td>
            <Td className="min-w-40 align-top text-sm">
              {q.response_label_en ? (
                <>
                  <div className="font-medium">{q.response_label_en}</div>
                  {q.response_note ? <div className="text-ink-muted">{q.response_note}</div> : null}
                </>
              ) : (
                <span className="text-ink-subtle">None</span>
              )}
            </Td>
            <Td className="align-top">
              <div className="flex flex-col items-start gap-1.5">
                <Link
                  href={`/audit?entity_id=${encodeURIComponent(q.id)}`}
                  className="inline-flex items-center gap-1 text-sm font-medium whitespace-nowrap text-accent-700 hover:underline"
                >
                  <ScrollText className="size-4" aria-hidden />
                  Audit rows
                </Link>
                {canEdit && q.status === "draft" ? (
                  <Button size="sm" icon={<FilePenLine className="size-4" aria-hidden />} onClick={() => onEdit(q)}>
                    Continue editing
                  </Button>
                ) : null}
                {canEdit && q.status === "answered" ? <CloseQueryControl query={q} compact /> : null}
              </div>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
