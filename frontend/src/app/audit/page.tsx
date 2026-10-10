"use client";

import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight, ScrollText } from "lucide-react";
import { useAudit } from "@/lib/queries";
import { formatAbsolute, humanize } from "@/lib/format";
import { Card, EmptyState, ErrorState, LoadingRows, PageHeader, Table, Td, Th, inputClass, cn } from "@/components/ui/primitives";
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
  const q = useAudit();
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
        title="Audit trail"
        subtitle="Append-only. Every human action and every automated decision, newest first."
        actions={
          <input type="search" aria-label="Filter audit events" placeholder="Filter by action, actor or ID" className={cn(inputClass, "w-72")} value={filter} onChange={(e) => setFilter(e.target.value)} />
        }
      />
      <Card>
        {q.isPending ? (
          <LoadingRows rows={8} />
        ) : q.isError ? (
          <div className="p-4">
            <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState icon={<ScrollText className="size-6" aria-hidden />} title={filter ? "No events match this filter." : "No audit events yet."}>
            {filter ? null : "Events appear as soon as anyone (or the agent) records, confirms, acknowledges or signs something."}
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-8">
                  <span className="sr-only">Expand</span>
                </Th>
                <Th>Time</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Entity</Th>
                <Th>Note</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => {
                const isOpen = open.has(a.id);
                const hasDiff = a.before !== null || a.after !== null;
                return (
                  <Fragment key={a.id}>
                    <tr className="hover:bg-gray-50">
                      <Td>
                        {hasDiff ? (
                          <button type="button" onClick={() => toggle(a.id)} aria-expanded={isOpen} aria-label={isOpen ? "Hide change" : "Show change"} className="rounded p-0.5 text-ink-muted hover:bg-gray-100">
                            {isOpen ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
                          </button>
                        ) : null}
                      </Td>
                      <Td className="whitespace-nowrap">
                        <RelativeTime iso={a.ts} />
                      </Td>
                      <Td className="whitespace-nowrap">
                        <span className="font-medium">{a.actor}</span> <Chip tone={ROLE_TONE[a.role] ?? "gray"}>{humanize(a.role)}</Chip>
                      </Td>
                      <Td>
                        <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-sm">{a.action}</code>
                      </Td>
                      <Td className="whitespace-nowrap">
                        <span className="text-ink-muted">{a.entity_type}</span> <span className="font-mono text-sm">{a.entity_id}</span>
                      </Td>
                      <Td className="max-w-xs text-ink-muted">{a.note ?? ""}</Td>
                    </tr>
                    {isOpen ? (
                      <tr>
                        <Td colSpan={6} className="bg-gray-50">
                          <div className="grid gap-3 md:grid-cols-2">
                            <Diff label="Before" value={a.before} tone="red" />
                            <Diff label="After" value={a.after} tone="green" />
                          </div>
                          <p className="mt-2 text-sm text-ink-subtle">{formatAbsolute(a.ts)}</p>
                        </Td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function Diff({ label, value, tone }: { label: string; value: unknown; tone: "red" | "green" }) {
  return (
    <div>
      <div className={cn("mb-1 text-sm font-medium", tone === "red" ? "text-red-800" : "text-green-800")}>{label}</div>
      <pre className={cn("max-h-72 overflow-auto rounded-md border p-2 font-mono text-sm leading-5 whitespace-pre-wrap", tone === "red" ? "border-red-200 bg-red-50/50" : "border-green-200 bg-green-50/50")}>
        {value === null || value === undefined ? "—" : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
