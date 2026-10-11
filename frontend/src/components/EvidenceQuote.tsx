"use client";

import Link from "next/link";
import { PlayCircle, Radio, SearchCheck } from "lucide-react";
import type { EpisodeEvidence, Evidence } from "@/lib/types";
import { formatDuration } from "@/lib/format";
import { SOURCE_LABELS } from "@/lib/labels";
import { AiLabel } from "./AiLabel";
import { cn } from "./ui/primitives";

/** Scroll to a transcript turn on the current page and flash it. Returns false if it isn't on the page. */
export function highlightTurn(turnIndex: number): boolean {
  if (typeof document === "undefined") return false;
  const el = document.getElementById(`turn-${turnIndex}`);
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("bv-highlight");
  // restart the animation
  void el.offsetWidth;
  el.classList.add("bv-highlight");
  return true;
}

/**
 * Verbatim evidence: original-language quote first, then the English
 * translation with an AI label, then where and when it was said.
 */
export function EvidenceQuote({
  evidence,
  checkinId,
  className,
}: {
  evidence: Evidence;
  checkinId: string;
  className?: string;
}) {
  const turn = evidence.turn_index;
  const href = turn !== null && turn !== undefined ? `/checkins/${checkinId}#turn-${turn}` : `/checkins/${checkinId}`;
  const isPostCall = evidence.source === "post_call_extraction";
  return (
    <figure className={cn("relative overflow-hidden rounded-xl border border-line bg-white p-4 shadow-card", className)}>
      <span aria-hidden className="pointer-events-none absolute -top-3 right-3 font-display text-[5.5rem] leading-none text-accent-100 select-none">
        &rdquo;
      </span>
      <blockquote className="relative flex gap-3">
        <span
          className="mt-0.5 inline-flex h-6 min-w-8 shrink-0 items-center justify-center rounded-md bg-ink px-1.5 font-mono text-sm font-semibold text-white"
          title={evidence.quote_lang === "es" ? "Original language: Spanish" : "Original language: English"}
        >
          {evidence.quote_lang.toUpperCase()}
        </span>
        <p className="min-w-0 text-base leading-7 text-ink" lang={evidence.quote_lang}>
          “{evidence.quote}”
        </p>
      </blockquote>
      {evidence.translation_en ? (
        <div className="relative mt-3 ml-11 border-l-2 border-violet-200 pl-3">
          <AiLabel>{evidence.translation_label || "AI translation, verify"}</AiLabel>
          <p className="mt-1.5 text-sm leading-6 text-ink-muted" lang="en">
            “{evidence.translation_en}”
          </p>
        </div>
      ) : null}
      <figcaption className="relative mt-3 ml-11 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-ink-subtle">
        <Link
          href={href}
          onClick={(e) => {
            if (turn !== null && turn !== undefined && highlightTurn(turn)) e.preventDefault();
          }}
          className="inline-flex items-center gap-1 rounded-md font-medium text-accent-700 underline-offset-2 hover:underline"
        >
          <PlayCircle className="size-4" aria-hidden />
          {evidence.t_s !== null && evidence.t_s !== undefined ? `${formatDuration(evidence.t_s)} in call` : "View in check-in"}
        </Link>
        {isPostCall ? (
          <span className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-1.5 text-blue-800">
            <SearchCheck className="size-3.5" aria-hidden />
            Source: post-call review, found after the call
          </span>
        ) : (
          <span className="inline-flex items-center gap-1">
            <Radio className="size-3.5" aria-hidden />
            {SOURCE_LABELS[evidence.source] ?? evidence.source}
          </span>
        )}
      </figcaption>
    </figure>
  );
}

/**
 * Site Signal episode evidence (docs/03 §5.3): the verbatim quote in its original language first, then the English
 * translation behind an `AiLabel` (every translation is an AI translation, REQ-026). Synthetic quotes come from the
 * monitoring quote bank and have no call to open; live and replay quotes link to their check-in.
 * Compact variant of `EvidenceQuote` for dense tables: same language tag and violet translation rule, no card.
 */
export function EpisodeEvidenceQuote({ evidence, className }: { evidence: EpisodeEvidence; className?: string }) {
  const synthetic = evidence.source === "synthetic";
  const checkinId = evidence.checkin_id;
  return (
    <figure className={cn("min-w-0", className)}>
      <blockquote className="flex gap-2">
        <span
          className="mt-0.5 inline-flex h-5 min-w-7 shrink-0 items-center justify-center rounded bg-ink px-1 font-mono text-sm leading-none font-semibold text-white"
          title={evidence.quote_lang === "es" ? "Original language: Spanish" : "Original language: English"}
        >
          {evidence.quote_lang.toUpperCase()}
        </span>
        <p className="min-w-0 text-sm leading-6 text-ink" lang={evidence.quote_lang}>
          “{evidence.quote}”
        </p>
      </blockquote>
      {evidence.translation_en ? (
        <div className="mt-1.5 ml-9 flex flex-wrap items-start gap-x-2 gap-y-1 border-l-2 border-violet-200 pl-2.5">
          {evidence.translation_is_ai ? (
            <AiLabel>{synthetic ? "AI-assisted translation" : "AI translation, verify"}</AiLabel>
          ) : (
            <span className="text-sm font-medium text-ink-subtle">Translation</span>
          )}
          <p className="text-sm leading-6 text-ink-muted" lang="en">
            “{evidence.translation_en}”
          </p>
        </div>
      ) : null}
      {checkinId && !synthetic ? (
        <figcaption className="mt-1.5 ml-9 text-sm">
          <Link
            href={`/checkins/${encodeURIComponent(checkinId)}`}
            className="inline-flex items-center gap-1 rounded-md font-medium text-accent-700 underline-offset-2 hover:underline"
          >
            <PlayCircle className="size-4" aria-hidden />
            {evidence.t_s !== null && evidence.t_s !== undefined ? `${formatDuration(evidence.t_s)} in call` : "View in check-in"}
          </Link>
        </figcaption>
      ) : null}
    </figure>
  );
}
