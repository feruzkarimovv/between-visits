"use client";

import Link from "next/link";
import { Quote, PlayCircle } from "lucide-react";
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
    <figure className={cn("rounded-md border border-line bg-gray-50/60 p-3", className)}>
      <blockquote className="flex gap-2">
        <Quote className="mt-0.5 size-4 shrink-0 text-ink-subtle" aria-hidden />
        <p className="text-[15px] leading-6 text-ink" lang={evidence.quote_lang}>
          <span className="mr-1.5 rounded bg-white px-1.5 py-0.5 align-middle font-mono text-sm text-ink-subtle ring-1 ring-line">
            {evidence.quote_lang.toUpperCase()}
          </span>
          “{evidence.quote}”
        </p>
      </blockquote>
      {evidence.translation_en ? (
        <div className="mt-2 ml-6 flex flex-wrap items-start gap-2">
          <AiLabel>{evidence.translation_label || "AI translation, verify"}</AiLabel>
          <p className="text-sm leading-6 text-ink-muted" lang="en">
            “{evidence.translation_en}”
          </p>
        </div>
      ) : null}
      <figcaption className="mt-2 ml-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-subtle">
        <Link
          href={href}
          onClick={(e) => {
            if (turn !== null && turn !== undefined && highlightTurn(turn)) e.preventDefault();
          }}
          className="inline-flex items-center gap-1 font-medium text-accent-700 underline-offset-2 hover:underline"
        >
          <PlayCircle className="size-4" aria-hidden />
          {evidence.t_s !== null && evidence.t_s !== undefined ? `${formatDuration(evidence.t_s)} in call` : "View in check-in"}
        </Link>
        {isPostCall ? (
          <span className="rounded border border-blue-200 bg-blue-50 px-1.5 text-blue-800">
            Source: post-call review, found after the call
          </span>
        ) : (
          <span>{SOURCE_LABELS[evidence.source] ?? evidence.source}</span>
        )}
      </figcaption>
    </figure>
  );
}

/**
 * Site Signal episode evidence (docs/03 §5.3): the verbatim quote in its original language first, then the English
 * translation behind an `AiLabel` (every translation is an AI translation, REQ-026). Synthetic quotes come from the
 * monitoring quote bank and have no call to open; live and replay quotes link to their check-in.
 */
export function EpisodeEvidenceQuote({ evidence, className }: { evidence: EpisodeEvidence; className?: string }) {
  const synthetic = evidence.source === "synthetic";
  const checkinId = evidence.checkin_id;
  return (
    <figure className={cn("min-w-0", className)}>
      <blockquote className="flex gap-1.5">
        <Quote className="mt-1 size-3.5 shrink-0 text-ink-subtle" aria-hidden />
        <p className="text-sm leading-6 text-ink" lang={evidence.quote_lang}>
          <span className="mr-1.5 rounded bg-white px-1 py-px align-middle font-mono text-xs text-ink-subtle ring-1 ring-line">
            {evidence.quote_lang.toUpperCase()}
          </span>
          “{evidence.quote}”
        </p>
      </blockquote>
      {evidence.translation_en ? (
        <div className="mt-1 ml-5 flex flex-wrap items-start gap-x-2 gap-y-1">
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
        <figcaption className="mt-1 ml-5 text-sm">
          <Link
            href={`/checkins/${encodeURIComponent(checkinId)}`}
            className="inline-flex items-center gap-1 font-medium text-accent-700 underline-offset-2 hover:underline"
          >
            <PlayCircle className="size-4" aria-hidden />
            {evidence.t_s !== null && evidence.t_s !== undefined ? `${formatDuration(evidence.t_s)} in call` : "View in check-in"}
          </Link>
        </figcaption>
      ) : null}
    </figure>
  );
}
