"use client";

import { useState } from "react";
import { CircleDashed, CircleSlash, FlaskConical, Link2, PhoneCall, Repeat, Siren, Unlink, type LucideIcon } from "lucide-react";
import type { EpisodeSource, EpisodeStatus, SiteEpisode } from "@/lib/types";
import { formatDay, humanize } from "@/lib/format";
import { Table, Td, Th, cn } from "./ui/primitives";
import { Chip } from "./chips";
import { GradeBadge } from "./GradeBadge";
import { DataOriginBadge } from "./DataOriginBadge";
import { EpisodeEvidenceQuote } from "./EvidenceQuote";

/**
 * Site drill-down episode list (WS3 F13; docs/06 § `/sites/[id]`, docs/03 §5.3). One row per episode: subject ID,
 * term, provisional rule-graded grade, episode date, status, the verbatim quote (original language first, AI
 * translation labeled), source chip and `DataOriginBadge`. Status chips use the neutral slate scale: a statistical
 * status is not a clinical escalation, and nothing here reads as "fine".
 *
 * With `selectable`, `unmatched` rows get a checkbox for the site query composer; every other status is disabled,
 * because only unmatched episodes can be cited in a site query (docs/03 §5.4).
 */

const STATUS: Record<EpisodeStatus, { label: string; icon: LucideIcon; className: string; title: string }> = {
  unmatched: {
    label: "Unmatched",
    icon: Unlink,
    className: "border-slate-700 bg-white text-slate-900",
    title: "Evaluable, not paged, and no matching entry in the site's AE log.",
  },
  matched: {
    label: "Matched",
    icon: Link2,
    className: "border-slate-200 bg-slate-50 font-normal text-slate-700",
    title: "A matching entry exists in the site's AE log.",
  },
  pending: {
    label: "Pending",
    icon: CircleDashed,
    className: "border-slate-200 bg-slate-100 font-normal text-slate-500",
    title: "The site's entry window had not passed at the data cut, so this episode is not counted either way.",
  },
  paged: {
    label: "Paged: separate stratum",
    icon: Siren,
    className: "border-slate-300 bg-white font-normal text-slate-700",
    title: "The call paged the on-call nurse. Paged episodes are a separate descriptive stratum, never in O or E.",
  },
  not_evaluated: {
    label: "Not evaluated",
    icon: CircleSlash,
    className: "border-slate-200 bg-slate-100 font-normal text-slate-500",
    title: "No comparison rate for this episode's cell, or the site is not compared.",
  },
};

const SOURCE: Record<EpisodeSource, { label: string; icon: LucideIcon; title: string; className?: string }> = {
  live_call: { label: "Live call", icon: PhoneCall, title: "Said on a live call processed by the app." },
  replay: { label: "Replay", icon: Repeat, title: "Said on a replayed call processed by the app's real handlers." },
  synthetic: {
    label: "Synthetic",
    icon: FlaskConical,
    title: "Simulated quote from the monitoring quote bank (phrasing written with AI assistance). Not a real patient.",
    className: "border-dashed border-slate-400 bg-white text-slate-700",
  },
};

const FILTERS: (EpisodeStatus | "all")[] = ["all", "unmatched", "matched", "pending", "paged", "not_evaluated"];

export function EpisodeStatusChip({ status, pagedLevel }: { status: EpisodeStatus; pagedLevel?: string | null }) {
  const s = STATUS[status];
  if (!s) return <Chip tone="gray">{humanize(status)}</Chip>;
  const Icon = s.icon;
  const title = status === "paged" && pagedLevel ? `${s.title} Page level: ${pagedLevel}.` : s.title;
  return (
    <Chip className={s.className} title={title} icon={<Icon className="size-3.5" aria-hidden />}>
      {s.label}
    </Chip>
  );
}

export function SourceChip({ source }: { source: EpisodeSource }) {
  const s = SOURCE[source];
  if (!s) return <Chip tone="gray">{humanize(source)}</Chip>;
  const Icon = s.icon;
  return (
    <Chip tone="gray" className={s.className} title={s.title} icon={<Icon className="size-3.5" aria-hidden />}>
      {s.label}
    </Chip>
  );
}

export function EpisodeTable({
  episodes,
  selectable = false,
  selected,
  onSelectedChange,
}: {
  episodes: SiteEpisode[];
  /** CRA only: unmatched rows can be selected for a site query. */
  selectable?: boolean;
  selected?: ReadonlySet<string>;
  onSelectedChange?: (next: Set<string>) => void;
}) {
  const [filter, setFilter] = useState<EpisodeStatus | "all">("all");

  // Site 101: MEASURED live and replay episodes first (the API already orders them; keep it stable here too).
  const ordered = [...episodes].sort(
    (a, b) => Number(b.data_origin === "MEASURED") - Number(a.data_origin === "MEASURED"),
  );
  const counts = new Map<EpisodeStatus | "all", number>([["all", episodes.length]]);
  for (const e of episodes) counts.set(e.status, (counts.get(e.status) ?? 0) + 1);
  const rows = filter === "all" ? ordered : ordered.filter((e) => e.status === filter);

  const canSelect = selectable && !!selected && !!onSelectedChange;
  const eligibleInView = rows.filter((e) => e.status === "unmatched").map((e) => e.episode_id);
  const allInViewSelected = eligibleInView.length > 0 && eligibleInView.every((id) => selected?.has(id));

  const toggle = (id: string) => {
    if (!selected || !onSelectedChange) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange(next);
  };
  const toggleAll = () => {
    if (!selected || !onSelectedChange) return;
    const next = new Set(selected);
    for (const id of eligibleInView) {
      if (allInViewSelected) next.delete(id);
      else next.add(id);
    }
    onSelectedChange(next);
  };

  return (
    <div>
      <div role="group" aria-label="Filter episodes by status" className="flex flex-wrap gap-1.5 border-b border-line px-4 py-2.5">
        {FILTERS.map((f) => {
          const n = counts.get(f) ?? 0;
          if (f !== "all" && n === 0) return null;
          return (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-sm whitespace-nowrap",
                filter === f ? "border-slate-800 bg-slate-800 text-white" : "border-line bg-white text-ink-muted hover:text-ink",
              )}
            >
              {f === "all" ? "All" : STATUS[f].label} <span className="tabular">{n}</span>
            </button>
          );
        })}
      </div>
      <Table className="relative">
        <caption className="sr-only">Episodes at this site with their status and verbatim evidence</caption>
        <thead>
          <tr>
            {canSelect ? (
              <Th className="w-10">
                <input
                  type="checkbox"
                  className="size-4 align-middle"
                  aria-label="Select every unmatched episode shown"
                  checked={allInViewSelected}
                  disabled={eligibleInView.length === 0}
                  onChange={toggleAll}
                />
              </Th>
            ) : null}
            <Th>Subject</Th>
            <Th>Term</Th>
            <Th>Grade</Th>
            <Th>Episode date</Th>
            <Th>Status</Th>
            <Th>Evidence</Th>
            <Th>Source</Th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <Td colSpan={canSelect ? 8 : 7} className="py-6 text-center text-ink-muted">
                No episodes with this status.
              </Td>
            </tr>
          ) : (
            rows.map((e) => {
              const eligible = e.status === "unmatched";
              const greyed = e.status === "pending";
              const isSelected = !!selected?.has(e.episode_id);
              return (
                <tr
                  key={e.episode_id}
                  data-episode={e.episode_id}
                  data-status={e.status}
                  className={cn(
                    "align-top",
                    greyed && "bg-slate-50 text-slate-500 *:opacity-60",
                    isSelected && "bg-slate-100",
                  )}
                >
                  {canSelect ? (
                    <Td className="align-top">
                      <input
                        type="checkbox"
                        className="mt-1 size-4"
                        checked={isSelected}
                        disabled={!eligible}
                        onChange={() => toggle(e.episode_id)}
                        aria-label={
                          eligible
                            ? `Cite ${e.subject_id} ${e.term} ${e.episode_date} in a site query`
                            : `${e.subject_id} ${e.term} cannot be cited: ${STATUS[e.status]?.label ?? e.status}`
                        }
                        title={eligible ? undefined : "Only unmatched episodes can be cited in a site query."}
                      />
                    </Td>
                  ) : null}
                  <Td className="align-top font-mono text-sm whitespace-nowrap">{e.subject_id}</Td>
                  <Td className="align-top">
                    <div className="font-medium whitespace-nowrap">{e.term}</div>
                    <div className="text-sm text-ink-subtle">{e.kind === "worsened" ? "Worsened" : "New"}</div>
                  </Td>
                  <Td className="align-top">
                    <GradeBadge grade={e.grade} />
                    <div className="mt-0.5 text-sm text-ink-subtle">rule-graded</div>
                  </Td>
                  <Td className="tabular align-top whitespace-nowrap">{formatDay(e.episode_date)}</Td>
                  <Td className="align-top">
                    <EpisodeStatusChip status={e.status} pagedLevel={e.paged_level} />
                  </Td>
                  <Td className="min-w-72 align-top">
                    <EpisodeEvidenceQuote evidence={e.evidence} />
                  </Td>
                  <Td className="align-top">
                    <div className="flex flex-col items-start gap-1.5">
                      <SourceChip source={e.evidence.source} />
                      <DataOriginBadge origin={e.data_origin} />
                    </div>
                  </Td>
                </tr>
              );
            })
          )}
        </tbody>
      </Table>
    </div>
  );
}
