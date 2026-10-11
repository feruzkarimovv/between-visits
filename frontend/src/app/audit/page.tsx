"use client";

import { Fragment, Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Bot, ChevronDown, Lock, ScrollText, Search, Server, X } from "lucide-react";
import { useAudit } from "@/lib/queries";
import { formatAbsolute, humanize } from "@/lib/format";
import { Avatar, Card, EmptyState, ErrorState, LoadingRows, PageHeader, inputClass, cn } from "@/components/ui/primitives";
import { Chip } from "@/components/chips";
import { RelativeTime } from "@/components/RelativeTime";

const ROLE_TONE: Record<string, "gray" | "blue" | "violet" | "green" | "accent"> = {
  coordinator: "accent",
  investigator: "blue",
  nurse: "green",
  agent: "violet",
  system: "gray",
  sponsor: "gray",
};

export default function AuditPage() {
  return (
    <Suspense fallback={<LoadingRows rows={8} />}>
      <AuditView />
    </Suspense>
  );
}

/** `/audit?entity_id=sq_...` shows one entity's rows (for example a site query's, linked from `/sites/[id]`). */
function AuditView() {
  const entityId = useSearchParams().get("entity_id") || undefined;
  const q = useAudit(entityId);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const rows = (q.data ?? []).filter((a) => {
    if (!filter) return true;
    const f = filter.toLowerCase();
    return [a.action, a.actor, a.entity_id, a.entity_type, a.checkin_id ?? ""].some((v) => v.toLowerCase().includes(f));
  });
  const toggle = (id: string) => {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpen(next);
  };

  return (
    <>
      <PageHeader
        eyebrow="Nothing final without a human"
        title="Audit trail"
        subtitle="Append-only. Every human action and every automated decision, newest first."
        actions={
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden />
            <input
              type="search"
              aria-label="Filter audit events"
              placeholder="Filter by action, actor or ID"
              className={cn(inputClass, "h-10 w-80 max-w-full pl-9")}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
        }
      />
      {entityId ? (
        <p className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-accent-200 bg-accent-50/60 px-4 py-2.5 text-sm text-ink-muted" role="status">
          Showing the audit rows for <code className="rounded-md bg-white px-1.5 py-0.5 font-mono text-sm text-ink ring-1 ring-line">{entityId}</code>
          <Link href="/audit" className="ml-auto inline-flex items-center gap-1 font-medium text-accent-700 hover:underline">
            <X className="size-3.5" aria-hidden />
            Show all events
          </Link>
        </p>
      ) : null}
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 border-b border-line bg-gray-50/70 px-5 py-2.5 text-sm text-ink-muted">
          <Lock className="size-4 text-ink-subtle" aria-hidden />
          Events can be added, never edited or deleted.
          {q.data ? (
            <span className="ml-auto shrink-0 whitespace-nowrap tabular">
              {rows.length} event{rows.length === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>
        {q.isPending ? (
          <LoadingRows rows={8} />
        ) : q.isError ? (
          <div className="p-5">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={<ScrollText className="size-6" aria-hidden />} title={filter ? "No events match this filter." : "No audit events yet."}>
            {filter ? null : "Events appear as soon as anyone (or the agent) records, confirms, acknowledges or signs something."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto py-3">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="sr-only">
                <tr>
                  <th scope="col">Actor</th>
                  <th scope="col">Event</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a, i) => {
                  const isOpen = open.has(a.id);
                  const hasDiff = a.before !== null || a.after !== null;
                  const machine = a.role === "agent" || a.role === "system";
                  const first = i === 0;
                  const last = i === rows.length - 1;
                  return (
                    <Fragment key={a.id}>
                      <tr>
                        <td className="relative w-[4.5rem] py-1 pr-0 pl-7 align-top">
                          <TimelineLine top={!first} bottom={!last} />
                          <span className="relative z-10 mt-3 inline-flex rounded-full ring-4 ring-white">
                            {machine ? (
                              <span className={cn("flex size-8 items-center justify-center rounded-full", a.role === "agent" ? "bg-violet-100 text-violet-800" : "bg-gray-100 text-ink-muted")}>
                                {a.role === "agent" ? <Bot className="size-4" aria-hidden /> : <Server className="size-4" aria-hidden />}
                              </span>
                            ) : (
                              <Avatar name={a.actor.replace(/^Dr\.\s*/, "")} seed={a.role} size="sm" />
                            )}
                          </span>
                        </td>
                        <td className="py-1 pr-5 align-top">
                          <div className={cn("flex flex-wrap items-start gap-x-4 gap-y-2 rounded-xl px-2 py-3 transition-colors", hasDiff && "hover:bg-gray-50")}>
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                <span className="font-semibold text-ink">{a.actor}</span>
                                <Chip tone={ROLE_TONE[a.role] ?? "gray"}>{humanize(a.role)}</Chip>
                                <code className="rounded-md bg-gray-100 px-1.5 py-0.5 font-mono text-sm font-medium text-ink ring-1 ring-line ring-inset">{a.action}</code>
                                <span className="text-sm text-ink-muted">
                                  {a.entity_type} <span className="font-mono">{a.entity_id}</span>
                                </span>
                              </div>
                              {a.note ? <p className="mt-1 text-sm leading-6 text-ink-muted">“{a.note}”</p> : null}
                            </div>
                            <div className="flex items-center gap-2 text-sm whitespace-nowrap text-ink-subtle">
                              <RelativeTime iso={a.ts} />
                              {hasDiff ? (
                                <button
                                  type="button"
                                  onClick={() => toggle(a.id)}
                                  aria-expanded={isOpen}
                                  aria-label={isOpen ? "Hide change" : "Show change"}
                                  className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-accent-700 hover:bg-accent-50"
                                >
                                  Change
                                  <ChevronDown className={cn("size-4 transition-transform", isOpen && "rotate-180")} aria-hidden />
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </td>
                      </tr>
                      {isOpen ? (
                        <tr>
                          <td className="relative pl-7" aria-hidden>
                            {last ? null : <TimelineLine top bottom />}
                          </td>
                          <td className="pr-5 pb-2">
                            <div className="ml-2 rounded-xl border border-line bg-gray-50/70 p-3">
                              <div className="grid gap-3 md:grid-cols-2">
                                <Diff label="Before" value={a.before} tone="red" />
                                <Diff label="After" value={a.after} tone="green" />
                              </div>
                              <p className="mt-2 text-sm text-ink-subtle">{formatAbsolute(a.ts)}</p>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

/** The vertical rule that joins the avatars; it starts and stops at the first and last avatar's centre (32 px down). */
function TimelineLine({ top, bottom }: { top: boolean; bottom: boolean }) {
  if (!top && !bottom) return null;
  return <span className={cn("absolute left-[2.75rem] w-px bg-line", top ? "top-0" : "top-8", bottom ? "bottom-0" : "h-8")} aria-hidden />;
}

function Diff({ label, value, tone }: { label: string; value: unknown; tone: "red" | "green" }) {
  return (
    <div>
      <div className={cn("mb-1 text-sm font-medium", tone === "red" ? "text-red-800" : "text-green-800")}>{label}</div>
      <pre className={cn("max-h-72 overflow-auto rounded-lg border p-2.5 font-mono text-sm leading-5 whitespace-pre-wrap", tone === "red" ? "border-red-200 bg-red-50/60" : "border-green-200 bg-green-50/60")}>
        {value === null || value === undefined ? "—" : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
